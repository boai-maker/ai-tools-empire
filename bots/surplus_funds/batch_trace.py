"""
Batch skip-trace all 'new' surplus leads in ONE Tracerfy request.
Dramatically more efficient than one-at-a-time (avoids rate limit,
single poll, fewer credits wasted on duplicates).

Run: python3 -m bots.surplus_funds.batch_trace
"""
import os
import sys
import json
import time
import sqlite3
import csv
from io import StringIO
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env"))

import requests

from bots.shared.standards import get_logger, tg, STATE_DIR

log = get_logger("surplus_batch_trace")

DB_PATH = os.path.join(STATE_DIR, "surplus_funds.db")
KEY = os.getenv("TRACERFY_API_KEY", "")

CORP_KEYWORDS = (" LLC", " INC", " CORP", " COMPANY", " PROPERTIES", " GROUP", " HOLDINGS", " EST", " ESTATE", " TRUST")


def is_corporate(name: str) -> bool:
    up = " " + name.upper().strip() + " "
    return any(k + " " in up for k in CORP_KEYWORDS)


def parse_name(full: str):
    parts = [p for p in full.strip().split() if p not in ("JR", "SR", "II", "III", "IV", "ETAL")]
    if len(parts) < 2:
        return None, None
    # County records are "LAST FIRST [MIDDLE]"
    return parts[1], parts[0]  # first, last


def fetch_leads():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    c = db.cursor()
    c.execute(
        "SELECT * FROM surplus_leads WHERE status='new' AND surplus_amount >= 2000 "
        "AND former_owner != '' ORDER BY surplus_amount DESC"
    )
    leads = [dict(r) for r in c.fetchall()]
    db.close()
    return leads


def build_rows(leads):
    rows = []
    skipped = []
    for lead in leads:
        name = lead["former_owner"]
        if is_corporate(name):
            skipped.append((lead["id"], name, "corporate/estate"))
            continue
        first, last = parse_name(name)
        if not first or not last:
            skipped.append((lead["id"], name, "insufficient name"))
            continue
        rows.append({
            "lead_id": lead["id"],
            "first_name": first,
            "last_name": last,
            "street": lead.get("property_address", "") or lead.get("county", ""),
            "city": lead.get("county", ""),
            "state": lead.get("state", ""),
            "mail_address": lead.get("property_address", "") or lead.get("county", ""),
            "mail_city": lead.get("county", ""),
            "mail_state": lead.get("state", ""),
            "mail_zip": "30030" if lead.get("state") == "GA" else "",
        })
    return rows, skipped


def submit_batch(rows):
    """Submit rows as one Tracerfy queue. Returns queue_id."""
    # strip lead_id from upload payload
    payload = [{k: v for k, v in r.items() if k != "lead_id"} for r in rows]
    r = requests.post(
        "https://tracerfy.com/v1/api/trace/",
        headers={"Authorization": f"Bearer {KEY}"},
        data={
            "json_data": json.dumps(payload),
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
        timeout=60,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Tracerfy submit failed {r.status_code}: {r.text[:300]}")
    return r.json().get("queue_id")


def poll_queue(queue_id, rows_uploaded, max_wait_sec=300):
    """Poll queues endpoint until download_url is ready (dict-aware rate-limit handling)."""
    start = time.time()
    attempt = 0
    while time.time() - start < max_wait_sec:
        attempt += 1
        r = requests.get(
            "https://tracerfy.com/v1/api/queues/",
            headers={"Authorization": f"Bearer {KEY}"},
            timeout=30,
        )
        data = r.json()
        # Rate-limit case returns dict
        if isinstance(data, dict) and "error" in data:
            retry = 25
            log.info(f"Rate limited, waiting {retry}s (attempt {attempt})")
            time.sleep(retry)
            continue
        if isinstance(data, list):
            for q in data:
                if q.get("id") == queue_id:
                    if q.get("download_url") and not q.get("pending", True):
                        log.info(f"Queue {queue_id} ready after {int(time.time()-start)}s")
                        return q["download_url"]
                    log.info(f"Queue {queue_id} still pending (pending={q.get('pending')})")
                    break
        time.sleep(30)
    return None


def parse_results(download_url):
    r = requests.get(download_url, timeout=60)
    reader = csv.DictReader(StringIO(r.text))
    return list(reader)


def match_results_to_leads(rows, results):
    """Match trace results back to leads by first_name + last_name."""
    by_name = {}
    for row in rows:
        key = (row["first_name"].upper(), row["last_name"].upper())
        by_name[key] = row["lead_id"]
    matched = {}
    for res in results:
        key = (res.get("first_name", "").upper(), res.get("last_name", "").upper())
        lead_id = by_name.get(key)
        if lead_id is None:
            continue
        phone = (res.get("primary_phone") or res.get("Mobile-1") or res.get("Landline-1") or "").strip()
        email = (res.get("Email-1") or res.get("Email-2") or "").strip()
        addr = (res.get("mail_address") or "").strip()
        if phone or email:
            matched[lead_id] = {"phone": phone, "email": email, "address": addr}
    return matched


def update_db(matched, all_lead_ids):
    now = datetime.utcnow().isoformat()
    db = sqlite3.connect(DB_PATH)
    for lead_id in all_lead_ids:
        if lead_id in matched:
            m = matched[lead_id]
            db.execute(
                "UPDATE surplus_leads SET owner_phone=?, owner_email=?, owner_current_address=?, "
                "status='traced', updated_at=? WHERE id=?",
                (m["phone"], m["email"], m["address"], now, lead_id),
            )
        else:
            db.execute(
                "UPDATE surplus_leads SET status='trace_failed', updated_at=? WHERE id=?",
                (now, lead_id),
            )
    db.commit()
    db.close()


def main():
    log.info("=== Batch skip-trace run ===")
    leads = fetch_leads()
    log.info(f"Fetched {len(leads)} 'new' leads totaling ${sum(l['surplus_amount'] for l in leads):,.2f}")
    if not leads:
        return

    rows, skipped = build_rows(leads)
    log.info(f"Built {len(rows)} trace rows, skipped {len(skipped)} (estates/corps)")
    for sid, sname, reason in skipped:
        log.info(f"  skipped id={sid} {sname} ({reason})")
        db = sqlite3.connect(DB_PATH)
        db.execute("UPDATE surplus_leads SET status='trace_skipped', updated_at=? WHERE id=?",
                   (datetime.utcnow().isoformat(), sid))
        db.commit()
        db.close()

    if not rows:
        log.info("No traceable rows, exiting")
        return

    log.info(f"Submitting batch of {len(rows)} to Tracerfy")
    queue_id = submit_batch(rows)
    log.info(f"Queue_id = {queue_id}")

    log.info("Polling for results...")
    time.sleep(45)  # initial wait
    url = poll_queue(queue_id, len(rows), max_wait_sec=420)
    if not url:
        log.warning("Queue never resolved within timeout")
        return

    results = parse_results(url)
    log.info(f"Got {len(results)} result rows")
    matched = match_results_to_leads(rows, results)
    log.info(f"Matched {len(matched)} leads with contact info")
    for lead_id, m in matched.items():
        log.info(f"  lead {lead_id}: phone={m['phone']!r} email={m['email']!r}")

    all_ids = [r["lead_id"] for r in rows]
    update_db(matched, all_ids)
    log.info("DB updated")

    tg(f"🔎 Surplus batch trace complete\n"
       f"• Submitted: {len(rows)} leads\n"
       f"• Matched: {len(matched)} with contact\n"
       f"• Skipped (corp/estate): {len(skipped)}\n"
       f"• Queue: {queue_id}", "info")


if __name__ == "__main__":
    main()
