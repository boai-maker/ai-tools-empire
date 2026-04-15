"""
Surplus Funds County Scraper — finds unclaimed tax sale overages.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Scrapes county websites for surplus fund lists (tax deed overages).
Each entry = a former property owner who is owed money they don't know about.

Runs daily. New leads go into the surplus_leads table and trigger
the skip trace → outreach → claim pipeline.

Starting markets: Georgia (top counties) + Florida (all 67 counties publish online).
"""
import os
import sys
import re
import json
import sqlite3
import requests
from datetime import datetime
from typing import List, Dict, Optional
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from bots.shared.standards import get_logger, tg, load_state, save_state, STATE_DIR

log = get_logger("surplus_scraper")

DB_PATH = os.path.join(STATE_DIR, "surplus_funds.db")
STATE_FILE = os.path.join(STATE_DIR, "surplus_scraper.json")

# ── County sources ───────────────────────────────────────────────────────────
# Each entry: name, state, URL, scrape_type (html_table, pdf, api)
COUNTY_SOURCES = [
    # Georgia
    {"county": "DeKalb", "state": "GA", "url": "https://publicaccess.dekalbtax.org/forms/htmlframe.aspx?mode=content/search/tax_sale_listing.html", "type": "html"},
    {"county": "Gwinnett", "state": "GA", "url": "https://www.gwinnettcounty.com/web/gwinnett/departments/taxcommissioner/propertytaxes/taxsales", "type": "html"},
    {"county": "Chatham", "state": "GA", "url": "https://tax.chathamcountyga.gov/ExcessFunds", "type": "html"},
    # Florida — high volume
    {"county": "Lee", "state": "FL", "url": "https://www.leeclerk.org/recordings/tax-deed-surplus", "type": "html"},
    {"county": "Hillsborough", "state": "FL", "url": "https://www.hillsclerk.com/Court-Proceedings/Tax-Deeds/Surplus-Funds", "type": "html"},
    {"county": "Duval", "state": "FL", "url": "https://www.duvalclerk.com/courts/tax-deeds/surplus", "type": "html"},
    {"county": "Orange", "state": "FL", "url": "https://www.occompt.com/tax-collector/services/tax-deed-surplus/", "type": "html"},
    {"county": "Pinellas", "state": "FL", "url": "https://www.pinellasclerk.org/aspInclude2/ASPInclude.asp?pageName=taxSurplus.htm", "type": "html"},
    # Ohio — no fee cap
    {"county": "Cuyahoga", "state": "OH", "url": "https://fiscalofficer.cuyahogacounty.us/en-US/surplus-funds.aspx", "type": "html"},
    {"county": "Franklin", "state": "OH", "url": "https://sheriff.franklincountyohio.gov/services/real-estate/surplus-funds", "type": "html"},
    # Florida expanded
    {"county": "Miami-Dade", "state": "FL", "url": "https://www.miamidade.gov/global/economy/surplus-funds.page", "type": "html"},
    {"county": "Broward", "state": "FL", "url": "https://www.broward.org/RecordsTaxesTreasury/Records/Pages/TaxDeedSales.aspx", "type": "html"},
    {"county": "Palm Beach", "state": "FL", "url": "https://www.mypalmbeachclerk.com/divisions/court-operations/foreclosures/surplus-funds", "type": "html"},
    {"county": "Polk", "state": "FL", "url": "https://www.polktaxes.com/tax-deed-sales/", "type": "html"},
    {"county": "Brevard", "state": "FL", "url": "https://brevardclerk.us/tax-deed-sales", "type": "html"},
    {"county": "Volusia", "state": "FL", "url": "https://www.volusia.org/services/financial-and-administrative-services/revenue-division/tax-deed-sales.stml", "type": "html"},
    {"county": "Pasco", "state": "FL", "url": "https://www.pascoclerk.com/departments/court-services/tax-deed-sales/", "type": "html"},
    {"county": "Marion", "state": "FL", "url": "https://www.marioncountyclerk.org/tax-deed-sales/", "type": "html"},
    # Georgia expanded
    {"county": "Fulton", "state": "GA", "url": "https://www.fultoncountytaxes.org/property-taxes/tax-sales.aspx", "type": "html"},
    {"county": "Clayton", "state": "GA", "url": "https://www.claytoncountyga.gov/government/tax-commissioner/tax-sales", "type": "html"},
    {"county": "Cobb", "state": "GA", "url": "https://www.cobbtax.org/TaxSale/TaxSaleSearch", "type": "html"},
    {"county": "Bibb", "state": "GA", "url": "https://www.maconbibb.us/tax-commissioner/tax-sales/", "type": "html"},
    # Ohio expanded
    {"county": "Hamilton", "state": "OH", "url": "https://www.hamiltoncountyauditor.org/real-estate/tax-sale", "type": "html"},
    {"county": "Summit", "state": "OH", "url": "https://fiscaloffice.summitoh.net/index.php/tax-lien-sale", "type": "html"},
    {"county": "Montgomery", "state": "OH", "url": "https://www.mcohio.org/government/elected_officials/treasurer/tax_sales.php", "type": "html"},
    {"county": "Lucas", "state": "OH", "url": "https://co.lucas.oh.us/2476/Tax-Foreclosure-Sale-Listing", "type": "html"},
]


def init_db():
    """Create the surplus funds database."""
    db = sqlite3.connect(DB_PATH)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS surplus_leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            county TEXT NOT NULL,
            state TEXT NOT NULL,
            case_number TEXT,
            property_address TEXT,
            former_owner TEXT,
            surplus_amount REAL,
            sale_date TEXT,
            status TEXT DEFAULT 'new',
            -- Skip trace results
            owner_phone TEXT,
            owner_email TEXT,
            owner_current_address TEXT,
            -- Outreach tracking
            first_contact_date TEXT,
            last_contact_date TEXT,
            contact_count INTEGER DEFAULT 0,
            contact_method TEXT,
            -- Deal tracking
            agreement_signed INTEGER DEFAULT 0,
            agreement_date TEXT,
            fee_percentage REAL,
            fee_amount REAL,
            claim_filed INTEGER DEFAULT 0,
            claim_date TEXT,
            claim_paid INTEGER DEFAULT 0,
            paid_date TEXT,
            paid_amount REAL,
            -- Meta
            source_url TEXT,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_surplus_status ON surplus_leads(status);
        CREATE INDEX IF NOT EXISTS idx_surplus_county ON surplus_leads(county, state);
        CREATE INDEX IF NOT EXISTS idx_surplus_amount ON surplus_leads(surplus_amount DESC);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_surplus_dedup ON surplus_leads(county, state, case_number);
    """)
    db.commit()
    db.close()
    log.info("Surplus DB initialized")


def scrape_county(source: Dict) -> List[Dict]:
    """
    Scrape a single county's surplus funds page.
    Returns list of lead dicts.
    """
    county = source["county"]
    state = source["state"]
    url = source["url"]

    log.info(f"Scraping {county} County, {state}: {url}")

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }
        r = requests.get(url, headers=headers, timeout=30)
        if r.status_code != 200:
            log.warning(f"{county} {state}: HTTP {r.status_code}")
            return []

        soup = BeautifulSoup(r.text, "html.parser")
        leads = []

        # Try to find tables with surplus data
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            if len(rows) < 2:
                continue

            # Check if this looks like a surplus funds table
            header_text = " ".join(rows[0].get_text().lower().split())
            if any(kw in header_text for kw in ["surplus", "excess", "amount", "owner", "case", "deed"]):
                for row in rows[1:]:
                    cells = row.find_all(["td", "th"])
                    if len(cells) < 3:
                        continue

                    cell_texts = [c.get_text(strip=True) for c in cells]

                    # Try to extract data — format varies by county
                    lead = _parse_row(cell_texts, county, state, url)
                    if lead and lead.get("surplus_amount", 0) > 0:
                        leads.append(lead)

        # If no tables found, try to extract from text/lists
        if not leads:
            leads = _parse_text_content(soup, county, state, url)

        log.info(f"{county} {state}: found {len(leads)} leads")
        return leads

    except Exception as e:
        log.warning(f"{county} {state} scrape failed: {e}")
        return []


def _parse_row(cells: List[str], county: str, state: str, url: str) -> Optional[Dict]:
    """Try to parse a table row into a surplus lead."""
    # Look for dollar amounts
    amounts = []
    for c in cells:
        match = re.search(r'\$?([\d,]+\.?\d*)', c.replace(',', ''))
        if match:
            try:
                val = float(match.group(1).replace(',', ''))
                if val > 100:  # Likely a surplus amount
                    amounts.append(val)
            except ValueError:
                pass

    if not amounts:
        return None

    # Look for case numbers
    case_num = None
    for c in cells:
        if re.search(r'20\d{2}\w{3,}', c) or re.search(r'\d{4}-\d+', c):
            case_num = c.strip()
            break

    # Look for addresses
    address = None
    for c in cells:
        if any(kw in c.upper() for kw in ["ST", "AVE", "DR", "RD", "BLVD", "LN", "CT", "WAY", "PL"]):
            address = c.strip()
            break

    # Look for names (likely the longest non-numeric, non-address cell)
    owner = None
    for c in cells:
        if len(c) > 5 and not re.search(r'^\$', c) and not re.search(r'^\d{4}', c) and c != address:
            if not any(kw in c.upper() for kw in ["ST", "AVE", "DR", "RD", "BLVD"]):
                owner = c.strip()
                break

    return {
        "county": county,
        "state": state,
        "case_number": case_num or "",
        "property_address": address or "",
        "former_owner": owner or "",
        "surplus_amount": max(amounts) if amounts else 0,
        "source_url": url,
    }


def _parse_text_content(soup: BeautifulSoup, county: str, state: str, url: str) -> List[Dict]:
    """Fallback: try to extract surplus data from non-table content."""
    leads = []
    text = soup.get_text()

    # Look for patterns like "Case 2024xxx ... $XX,XXX.XX"
    pattern = r'(20\d{2}\w{5,15}).*?\$\s*([\d,]+\.?\d{0,2})'
    matches = re.findall(pattern, text)

    for case_num, amount_str in matches:
        try:
            amount = float(amount_str.replace(',', ''))
            if amount > 500:
                leads.append({
                    "county": county,
                    "state": state,
                    "case_number": case_num,
                    "surplus_amount": amount,
                    "source_url": url,
                    "former_owner": "",
                    "property_address": "",
                })
        except ValueError:
            pass

    return leads


def save_leads(leads: List[Dict]) -> Dict:
    """Save leads to database, dedup by case number."""
    db = sqlite3.connect(DB_PATH)
    c = db.cursor()

    added = 0
    skipped = 0

    for lead in leads:
        try:
            c.execute("""
                INSERT OR IGNORE INTO surplus_leads
                (county, state, case_number, property_address, former_owner,
                 surplus_amount, source_url, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'new')
            """, (
                lead.get("county", ""),
                lead.get("state", ""),
                lead.get("case_number", ""),
                lead.get("property_address", ""),
                lead.get("former_owner", ""),
                lead.get("surplus_amount", 0),
                lead.get("source_url", ""),
            ))
            if c.rowcount > 0:
                added += 1
            else:
                skipped += 1
        except Exception as e:
            log.warning(f"Save lead failed: {e}")
            skipped += 1

    db.commit()
    db.close()
    return {"added": added, "skipped": skipped}


def get_stats() -> Dict:
    """Get current surplus funds stats."""
    db = sqlite3.connect(DB_PATH)
    c = db.cursor()

    c.execute("SELECT COUNT(*) FROM surplus_leads")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM surplus_leads WHERE status='new'")
    new = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM surplus_leads WHERE status='contacted'")
    contacted = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM surplus_leads WHERE agreement_signed=1")
    signed = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM surplus_leads WHERE claim_filed=1")
    filed = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM surplus_leads WHERE claim_paid=1")
    paid = c.fetchone()[0]
    c.execute("SELECT SUM(surplus_amount) FROM surplus_leads")
    total_amount = c.fetchone()[0] or 0
    c.execute("SELECT SUM(surplus_amount) FROM surplus_leads WHERE status='new'")
    new_amount = c.fetchone()[0] or 0

    db.close()
    return {
        "total_leads": total,
        "new": new,
        "contacted": contacted,
        "signed": signed,
        "filed": filed,
        "paid": paid,
        "total_surplus_value": round(total_amount, 2),
        "new_surplus_value": round(new_amount, 2),
    }


def run_scraper() -> Dict:
    """Main entry: scrape all counties, save leads, report."""
    init_db()

    all_leads = []
    counties_scraped = 0
    counties_failed = 0

    for source in COUNTY_SOURCES:
        try:
            leads = scrape_county(source)
            all_leads.extend(leads)
            counties_scraped += 1
        except Exception as e:
            log.warning(f"County failed: {source['county']} {source['state']}: {e}")
            counties_failed += 1

    # Save to DB
    result = save_leads(all_leads)

    # Get stats
    stats = get_stats()

    # Update state
    state = load_state(STATE_FILE)
    state["last_run"] = datetime.utcnow().isoformat()
    state["counties_scraped"] = counties_scraped
    state["leads_found_last_run"] = len(all_leads)
    state["leads_added_last_run"] = result["added"]
    save_state(STATE_FILE, state)

    # Telegram alert
    tg(
        f"<b>💰 Surplus Funds Scraper</b>\n"
        f"Counties scraped: {counties_scraped}/{len(COUNTY_SOURCES)}\n"
        f"Leads found: {len(all_leads)}\n"
        f"New leads added: {result['added']}\n"
        f"Total in pipeline: {stats['total_leads']}\n"
        f"Total surplus value: ${stats['total_surplus_value']:,.2f}\n"
        f"New surplus value: ${stats['new_surplus_value']:,.2f}",
        level="money",
    )

    return {
        "counties_scraped": counties_scraped,
        "counties_failed": counties_failed,
        "leads_found": len(all_leads),
        "leads_added": result["added"],
        "leads_skipped": result["skipped"],
        "stats": stats,
    }


if __name__ == "__main__":
    result = run_scraper()
    print(json.dumps(result, indent=2))
