"""
Owner Outreach Bot — finds agent/owner emails and sends cash offers.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
For each CRM property without a contact email:
  1. Web search for listing agent by address
  2. Find agent's email via web search
  3. Send a cash offer email
  4. Update CRM with contact info + status = "offered"
  5. Alert via Telegram

Rate limited: 2 emails per minute to avoid Gmail throttling.
"""
import os
import sys
import re
import time
import sqlite3
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from bots.shared.standards import get_logger, tg, load_state, save_state, STATE_DIR
from bots.shared.ai_client import ask_claude

log = get_logger("owner_outreach")

STATE_FILE = os.path.join(STATE_DIR, "owner_outreach.json")
CRM_DB = "/Users/kennethbonnet/Desktop/wholesale-re/crm/crm.db"
SMTP_USER = os.getenv("SMTP_USER", "bosaibot@gmail.com")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")


def find_agent_email(address: str, city: str, state: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Use Claude to find the listing agent name and email for a property.
    Returns (agent_name, agent_email, agent_company) or (None, None, None).
    """
    prompt = f"""I need to find the listing agent or property owner contact for this property:
{address}

Search your knowledge for:
1. Who is the listing agent for this address? (Check Zillow, Realtor.com, Redfin, MLS)
2. What is the agent's email address?
3. What brokerage are they with?

If you can't find the specific agent, try to find the owner from public tax records for {city}, {state}.

Common email patterns for real estate agents:
- firstname@brokerage.com
- firstnamelastname@gmail.com
- firstname.lastname@kw.com (for Keller Williams)

Return ONLY a JSON object:
{{"agent_name": "...", "agent_email": "...", "agent_company": "...", "confidence": "high/medium/low"}}

If you truly cannot determine any contact info, return:
{{"agent_name": null, "agent_email": null, "agent_company": null, "confidence": "none"}}"""

    raw = ask_claude(prompt, max_tokens=300)
    if not raw:
        return None, None, None

    try:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            data = __import__("json").loads(match.group(0))
            name = data.get("agent_name")
            email = data.get("agent_email")
            company = data.get("agent_company")
            conf = data.get("confidence", "none")
            if email and conf != "none":
                log.info(f"Found contact for {address}: {name} ({email}) [{conf}]")
                return name, email, company
    except Exception as e:
        log.warning(f"Parse failed for {address}: {e}")

    return None, None, None


def send_offer_email(to_email: str, agent_name: str, address: str, price: int, arv: int) -> bool:
    """Send a cash offer email to the agent/owner. Offer is 5-10K below asking.
    Falls back to arv when price is missing (Tracerfy leads don't have an asking price)."""
    if not SMTP_PASSWORD:
        log.warning("No SMTP_PASSWORD")
        return False

    # Tracerfy leads have estimated_value (arv) but no listing price. Use arv as baseline.
    baseline = price or arv or 0
    if not baseline:
        log.warning(f"No price or arv for {address} — skipping (can't compute offer)")
        return False

    import random
    discount = random.randint(5000, 10000)
    offer_price = max(baseline - discount, 1000)

    name_greeting = agent_name.split()[0] if agent_name else "there"

    # Tracerfy leads have no list price — phrase the email as an unsolicited offer
    is_unsolicited = not price
    subject = f"Cash Offer ${offer_price:,} — {address}"
    if is_unsolicited:
        body_intro = f"I'd like to submit a cash offer of ${offer_price:,} for {address}."
    else:
        body_intro = f"I came across {address} listed at ${price:,} and I'd like to submit a cash offer of ${offer_price:,}."
    body = f"""Hi {name_greeting},

{body_intro}

I'm a local investor and can close quickly — typically 14-21 days. No contingencies, no financing delays. 

This is a firm offer. I'm ready to sign a purchase agreement today if the seller is willing to move forward.

A few questions:
- Is the seller flexible on timeline?
- Are there any existing offers?
- Can you send the seller's disclosure?

I'd appreciate a quick response — I'm actively closing deals this week.

Kenneth Bonnet
AI Tools Empire | Real Estate Division
bosaibot@gmail.com
"""

    try:
        msg = MIMEMultipart()
        msg["Subject"] = subject
        msg["From"] = f"Kenneth Bonnet <{SMTP_USER}>"
        msg["To"] = to_email
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP("smtp.gmail.com", 587) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASSWORD)
            s.send_message(msg)

        log.info(f"Offer sent: {address} → {to_email}")
        return True
    except Exception as e:
        log.warning(f"Email failed for {address}: {e}")
        return False


def update_crm(prop_id: int, agent_name: str, agent_email: str, agent_company: str):
    """Update CRM with contact info and mark as offered."""
    db = sqlite3.connect(CRM_DB)
    db.execute("""
        UPDATE properties SET
            contact_name = ?,
            contact_email = ?,
            contact_company = ?,
            status = 'offered',
            notes = 'Auto-offer sent by outreach bot'
        WHERE id = ?
    """, (agent_name, agent_email, agent_company, prop_id))
    db.commit()
    db.close()


def run_outreach(batch_size: int = 25) -> Dict:
    """Process a batch of properties: find contacts, send offers, update CRM."""
    db = sqlite3.connect(CRM_DB)
    db.row_factory = sqlite3.Row
    c = db.cursor()

    # Pull outreach-eligible properties: NOT yet offered/closed, motivation-sorted.
    # Properties with contact_email go straight to send; without go through find_agent_email.
    # "No contact found" notes are skipped for 48h.
    c.execute("""
        SELECT id, address, city, state, price, arv, beds, baths,
               contact_name, contact_email, seller_name, seller_email,
               motivation_score
        FROM properties
        WHERE status NOT IN ('offered', 'closed', 'rejected', 'under_contract', 'assigned')
          AND (
              notes IS NULL
              OR notes = ''
              OR notes NOT LIKE 'No contact found; retry after %'
              OR substr(notes, 32, 19) < datetime('now')
          )
        ORDER BY
            CASE WHEN motivation_score IS NOT NULL THEN motivation_score ELSE 0 END DESC,
            CASE WHEN spread IS NOT NULL THEN spread ELSE 0 END DESC,
            price ASC
        LIMIT ?
    """, (batch_size,))
    props = [dict(r) for r in c.fetchall()]
    db.close()

    if not props:
        log.info("No properties need outreach")
        return {"processed": 0, "emailed": 0, "no_contact": 0}

    log.info(f"Processing {len(props)} properties for outreach...")

    emailed = 0
    no_contact = 0
    results = []

    for p in props:
        address = p["address"]
        city = p.get("city", "")
        state = p.get("state", "")
        price = p.get("price", 0)
        arv = p.get("arv", 0)

        # Prefer an already-known contact (e.g. from Tracerfy); else try to find one.
        existing_email = (p.get("contact_email") or p.get("seller_email") or "").strip()
        existing_name  = (p.get("contact_name")  or p.get("seller_name")  or "").strip()

        if existing_email:
            name, email, company = existing_name, existing_email, None
            log.info(f"Using existing contact for {address}: {email}")
        else:
            name, email, company = find_agent_email(address, city, state)

        if email:
            # Send offer
            sent = send_offer_email(email, name or "Property Agent", address, price, arv)
            if sent:
                update_crm(p["id"], name, email, company)
                emailed += 1
                results.append(f"✅ {address[:30]} → {email}")
            else:
                results.append(f"❌ {address[:30]} — email failed")

            # Rate limit: max 3/min (Gmail safe)
            time.sleep(20)
        else:
            no_contact += 1
            results.append(f"⚠️ {address[:30]} — no contact found")
            # Mark with timestamp so it's eligible for retry after 48h (not "permanent")
            db2 = sqlite3.connect(CRM_DB)
            db2.execute(
                "UPDATE properties SET notes = 'No contact found; retry after ' || datetime('now', '+2 days'), last_action = datetime('now') WHERE id = ?",
                (p["id"],),
            )
            db2.commit()
            db2.close()
            time.sleep(2)

    # Telegram summary
    summary = "\n".join(results[:15])
    tg(
        f"<b>📧 Outreach Bot — Batch Complete</b>\n\n"
        f"Processed: {len(props)}\n"
        f"Offers sent: {emailed}\n"
        f"No contact found: {no_contact}\n\n"
        f"{summary}",
        level="deal",
    )

    return {"processed": len(props), "emailed": emailed, "no_contact": no_contact}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=int, default=10)
    args = parser.parse_args()
    result = run_outreach(args.batch)
    print(result)
