"""
Surplus Funds Pipeline — the autonomous money machine.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Processes new surplus leads through the full pipeline:
  1. Skip trace former owner (Tracerfy API)
  2. Send outreach (email + direct mail via Lob)
  3. Generate fee agreement (PDF)
  4. Send for e-signature (DocuSign)
  5. File claim with county
  6. Track to payment

Runs every 4 hours. Respects 48hr email rules.
"""
import os
import sys
import json
import time
import random
import sqlite3
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env"))

import requests as req

from bots.shared.standards import get_logger, tg, load_state, save_state, STATE_DIR

log = get_logger("surplus_pipeline")

DB_PATH = os.path.join(STATE_DIR, "surplus_funds.db")
TRACERFY_KEY = os.getenv("TRACERFY_API_KEY", "")
SMTP_USER = os.getenv("SMTP_USER", "bosaibot@gmail.com")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")

# Fee percentages by state
STATE_FEES = {
    "GA": 0.15,  # 15% cap under $25K
    "FL": 0.15,  # 15% within 90 days
    "OH": 0.25,  # No cap — take 25%
    "DEFAULT": 0.20,
}

MIN_SURPLUS_AMOUNT = 2000  # Don't waste time on tiny amounts


# ── Skip Tracing ─────────────────────────────────────────────────────────────

def skip_trace_lead(lead: Dict) -> Dict:
    """Skip trace a surplus lead via Tracerfy API."""
    if not TRACERFY_KEY:
        return {}

    name = lead.get("former_owner", "").strip()
    # Skip companies/LLCs — can't skip trace those
    if any(kw in name.upper() for kw in ["LLC", "INC", "CORP", "COMPANY", "PROPERTIES", "GROUP", "HOLDINGS", "EST"]):
        log.info(f"Skip trace skipped — corporate/estate: {name}")
        return {}

    parts = [p for p in name.split() if p not in ("JR", "SR", "II", "III", "IV", "ETAL")]
    if len(parts) < 2:
        log.info(f"Skip trace skipped — insufficient name: {name}")
        return {}

    # County records usually format as "LAST FIRST MIDDLE"
    # Detect: if first part is all caps and looks like a last name
    last = parts[0]
    first = parts[1] if len(parts) > 1 else ""
    # If there's a middle initial/name, skip it
    log.info(f"Name parsed: '{name}' → first='{first}' last='{last}'")

    if not first or not last:
        return {}

    county = lead.get("county", "")
    state = lead.get("state", "")
    address = lead.get("property_address", "")

    data = [{
        "first_name": first,
        "last_name": last,
        "street": address or county,
        "city": county,
        "state": state,
        "mail_address": address or county,
        "mail_city": county,
        "mail_state": state,
        "mail_zip": "30000" if state == "GA" else "",
    }]

    try:
        r = req.post(
            "https://tracerfy.com/v1/api/trace/",
            headers={"Authorization": f"Bearer {TRACERFY_KEY}"},
            data={
                "json_data": json.dumps(data),
                "first_name_column": "first_name",
                "last_name_column": "last_name",
                "address_column": "street",
                "city_column": "city",
                "state_column": "state",
                "mail_address_column": "mail_address",
                "mail_city_column": "mail_city",
                "mail_state_column": "mail_state",
                "mail_zip_column": "mail_zip",
            },
            timeout=30,
        )

        if r.status_code != 200:
            log.warning(f"Tracerfy error {r.status_code}: {r.text[:200]}")
            return {}

        queue_id = r.json().get("queue_id")
        log.info(f"Skip trace queued: {queue_id} for {name}")

        # Wait for results
        time.sleep(35)

        queues_r = req.get(
            "https://tracerfy.com/v1/api/queues/",
            headers={"Authorization": f"Bearer {TRACERFY_KEY}"},
            timeout=30,
        )

        for q in queues_r.json():
            if q["id"] == queue_id and q.get("download_url"):
                csv_r = req.get(q["download_url"], timeout=30)
                lines = csv_r.text.strip().split("\n")
                if len(lines) >= 2:
                    import csv
                    from io import StringIO
                    reader = csv.DictReader(StringIO(csv_r.text))
                    for row in reader:
                        result = {
                            "phone": row.get("primary_phone") or row.get("Mobile-1") or "",
                            "email": row.get("Email-1") or "",
                            "address": row.get("mail_address") or "",
                        }
                        log.info(f"Skip trace result for {name}: phone={result['phone']}, email={result['email']}")
                        return result

        return {}
    except Exception as e:
        log.warning(f"Skip trace failed: {e}")
        return {}


# ── Outreach ─────────────────────────────────────────────────────────────────

def send_surplus_email(lead: Dict) -> bool:
    """Send surplus funds notification email to former owner."""
    if not SMTP_PASSWORD:
        return False

    email = lead.get("owner_email", "")
    if not email:
        return False

    owner_name = lead.get("former_owner", "Former Property Owner")
    first_name = owner_name.split()[0] if owner_name else "there"
    amount = lead.get("surplus_amount", 0)
    county = lead.get("county", "")
    state = lead.get("state", "")
    address = lead.get("property_address", "your former property")

    subject = f"You May Be Owed ${amount:,.2f} — {county} County Surplus Funds"

    body = f"""Hi {first_name},

I'm reaching out because I found unclaimed surplus funds in your name from a property tax sale in {county} County, {state}.

According to county records, there is approximately ${amount:,.2f} in surplus funds from the sale of {address}. This money belongs to you as the former property owner, but the county will not contact you about it.

I specialize in helping people recover these funds. My service is completely free upfront — I only get paid if you get paid. My fee is {int(STATE_FEES.get(state, STATE_FEES['DEFAULT']) * 100)}% of the recovered amount, and you receive the rest.

Here's what happens next if you're interested:
1. I verify your claim eligibility (takes 24 hours)
2. I prepare and file all the paperwork with the county
3. The county processes the claim (typically 30-90 days)
4. You receive your money via check or wire transfer

There is no cost to you unless the claim is successful. You have nothing to lose.

Would you like me to start the process? Simply reply to this email and I'll get everything moving.

Kenneth Bonnet
AI Tools Empire | Asset Recovery Division
bosaibot@gmail.com
"""

    try:
        msg = MIMEMultipart()
        msg["Subject"] = subject
        msg["From"] = f"Kenneth Bonnet <{SMTP_USER}>"
        msg["To"] = email
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP("smtp.gmail.com", 587) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASSWORD)
            s.send_message(msg)

        log.info(f"Surplus email sent: {owner_name} ({email}) — ${amount:,.2f}")
        return True
    except Exception as e:
        log.warning(f"Surplus email failed: {e}")
        return False


# ── Pipeline Processing ──────────────────────────────────────────────────────

def process_new_leads(batch_size: int = 10) -> Dict:
    """Process new surplus leads: skip trace → email outreach."""
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    c = db.cursor()

    # Get new leads with surplus > minimum, prioritize highest amounts
    c.execute("""
        SELECT * FROM surplus_leads
        WHERE status = 'new'
          AND surplus_amount >= ?
          AND former_owner != ''
        ORDER BY surplus_amount DESC
        LIMIT ?
    """, (MIN_SURPLUS_AMOUNT, batch_size))

    leads = [dict(r) for r in c.fetchall()]
    db.close()

    if not leads:
        log.info("No new surplus leads to process")
        return {"processed": 0, "traced": 0, "emailed": 0}

    log.info(f"Processing {len(leads)} surplus leads (${sum(l['surplus_amount'] for l in leads):,.2f} total)")

    traced = 0
    emailed = 0

    for lead in leads:
        # Skip trace
        trace = skip_trace_lead(lead)

        db = sqlite3.connect(DB_PATH)
        if trace.get("phone") or trace.get("email"):
            db.execute("""
                UPDATE surplus_leads SET
                    owner_phone = ?,
                    owner_email = ?,
                    owner_current_address = ?,
                    status = 'traced',
                    updated_at = ?
                WHERE id = ?
            """, (
                trace.get("phone", ""),
                trace.get("email", ""),
                trace.get("address", ""),
                datetime.utcnow().isoformat(),
                lead["id"],
            ))
            traced += 1

            # Send email if we got one
            if trace.get("email"):
                lead["owner_email"] = trace["email"]
                sent = send_surplus_email(lead)
                if sent:
                    db.execute("""
                        UPDATE surplus_leads SET
                            status = 'contacted',
                            first_contact_date = ?,
                            last_contact_date = ?,
                            contact_count = 1,
                            contact_method = 'email',
                            updated_at = ?
                        WHERE id = ?
                    """, (
                        datetime.utcnow().isoformat(),
                        datetime.utcnow().isoformat(),
                        datetime.utcnow().isoformat(),
                        lead["id"],
                    ))
                    emailed += 1
                    time.sleep(30)  # Rate limit
        else:
            # Mark as trace_failed — might need manual lookup
            db.execute("""
                UPDATE surplus_leads SET status = 'trace_failed', updated_at = ?
                WHERE id = ?
            """, (datetime.utcnow().isoformat(), lead["id"]))

        db.commit()
        db.close()

    return {"processed": len(leads), "traced": traced, "emailed": emailed}


def process_followups() -> Dict:
    """Send follow-up emails (48hr minimum spacing)."""
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    c = db.cursor()

    cutoff = (datetime.utcnow() - timedelta(hours=48)).isoformat()

    c.execute("""
        SELECT * FROM surplus_leads
        WHERE status = 'contacted'
          AND owner_email != ''
          AND last_contact_date < ?
          AND contact_count < 5
          AND agreement_signed = 0
        ORDER BY surplus_amount DESC
        LIMIT 5
    """, (cutoff,))

    leads = [dict(r) for r in c.fetchall()]
    db.close()

    sent = 0
    for lead in leads:
        ok = send_surplus_email(lead)
        if ok:
            db = sqlite3.connect(DB_PATH)
            db.execute("""
                UPDATE surplus_leads SET
                    last_contact_date = ?,
                    contact_count = contact_count + 1,
                    updated_at = ?
                WHERE id = ?
            """, (datetime.utcnow().isoformat(), datetime.utcnow().isoformat(), lead["id"]))
            db.commit()
            db.close()
            sent += 1
            time.sleep(30)

    return {"followups_sent": sent}


def run_pipeline() -> Dict:
    """Full pipeline run: process new leads + follow ups."""
    from bots.surplus_funds.scraper import get_stats

    # Process new leads
    new_result = process_new_leads(batch_size=10)

    # Process follow-ups
    followup_result = process_followups()

    # Get stats
    stats = get_stats()

    # Telegram summary
    tg(
        f"<b>💰 Surplus Funds Pipeline</b>\n"
        f"New leads processed: {new_result['processed']}\n"
        f"Skip traced: {new_result['traced']}\n"
        f"Emails sent: {new_result['emailed']}\n"
        f"Follow-ups sent: {followup_result['followups_sent']}\n"
        f"━━━━━━━━━━━━\n"
        f"Pipeline: {stats['total_leads']} leads | ${stats['total_surplus_value']:,.2f}\n"
        f"Contacted: {stats['contacted']} | Signed: {stats['signed']} | Filed: {stats['filed']}",
        level="money",
    )

    return {**new_result, **followup_result, "stats": stats}


if __name__ == "__main__":
    result = run_pipeline()
    print(json.dumps(result, indent=2))


# ── Direct Mail via Lob API ──────────────────────────────────────────────────

LOB_API_KEY = os.getenv("LOB_API_KEY_TEST", os.getenv("LOB_API_KEY_LIVE", ""))

def send_surplus_letter(lead: Dict) -> bool:
    """Send a physical letter to the former owner via Lob.com API."""
    if not LOB_API_KEY:
        log.warning("No LOB_API_KEY")
        return False

    owner_address = lead.get("owner_current_address", "")
    if not owner_address:
        owner_address = lead.get("property_address", "")
    if not owner_address:
        return False

    owner_name = lead.get("former_owner", "Current Resident")
    amount = lead.get("surplus_amount", 0)
    county = lead.get("county", "")
    state = lead.get("state", "")
    fee_pct = int(STATE_FEES.get(state, STATE_FEES["DEFAULT"]) * 100)

    letter_html = f"""
    <html><body style="font-family:Georgia,serif;font-size:14px;line-height:1.6;color:#333;max-width:600px;margin:40px auto;">
    <p style="text-align:right;color:#666;">{datetime.utcnow().strftime('%B %d, %Y')}</p>
    <p>Dear {owner_name},</p>
    <p>I am writing to inform you that <strong>${amount:,.2f} in unclaimed surplus funds</strong> may be owed to you from a property tax sale in <strong>{county} County, {state}</strong>.</p>
    <p>When your former property was sold at a tax sale, the sale price exceeded the amount owed. The excess money — called "surplus funds" — is being held by the county. <strong>This money belongs to you.</strong></p>
    <p>The county will not contact you about this. Most people never find out the money exists.</p>
    <p>I specialize in helping former property owners recover these funds. My service works on a contingency basis — <strong>you pay nothing upfront</strong>. My fee is {fee_pct}% of the recovered amount, and only if the claim is successful.</p>
    <p><strong>Here is what happens next if you are interested:</strong></p>
    <ol>
    <li>I verify your eligibility (24 hours)</li>
    <li>I prepare and file all paperwork with the county</li>
    <li>The county processes the claim (30-90 days)</li>
    <li>You receive your money</li>
    </ol>
    <p>Please contact me at your earliest convenience:</p>
    <p style="margin-left:20px;">
    <strong>Kenneth Bonnet</strong><br>
    AI Tools Empire | Asset Recovery Division<br>
    Email: bosaibot@gmail.com<br>
    </p>
    <p>This is a time-sensitive matter. Please respond within 30 days.</p>
    <p>Sincerely,<br><strong>Kenneth Bonnet</strong></p>
    </body></html>
    """

    try:
        r = req.post(
            "https://api.lob.com/v1/letters",
            auth=(LOB_API_KEY, ""),
            json={
                "description": f"Surplus funds letter — {county} {state} — ${amount:,.2f}",
                "to": {
                    "name": owner_name,
                    "address_line1": owner_address.split(",")[0].strip() if "," in owner_address else owner_address,
                    "address_city": owner_address.split(",")[1].strip() if "," in owner_address and len(owner_address.split(",")) > 1 else county,
                    "address_state": state,
                    "address_zip": "",
                },
                "from": {
                    "name": "Kenneth Bonnet",
                    "address_line1": "AI Tools Empire",
                    "address_city": "Atlanta",
                    "address_state": "GA",
                    "address_zip": "30301",
                },
                "file": letter_html,
                "color": False,
                "mail_type": "usps_first_class",
            },
            timeout=30,
        )

        if r.status_code in (200, 201):
            log.info(f"Letter sent via Lob: {owner_name} — ${amount:,.2f}")
            return True
        else:
            log.warning(f"Lob error {r.status_code}: {r.text[:200]}")
            return False
    except Exception as e:
        log.warning(f"Lob letter failed: {e}")
        return False
