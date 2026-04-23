"""
Tracerfy Lead Bot — generates pre-traced wholesale leads in one shot.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Workflow per run:
  1. POST /v1/api/lead-builder/execute/ with geography + requested_count
  2. Poll /v1/api/lead-builder/<id>/ until status=complete
  3. Download the result CSV
  4. Ingest each row into the wholesale CRM (upsert by address)
  5. Telegram summary

Every lead comes pre-traced with owner name, phone(s), email(s), motivation
signals (absentee, tax_delinquent, high_equity, pre_foreclosure, etc.) — so the
owner_outreach_bot can actually contact them instead of getting hallucinated
emails from Claude.

Cost: 5 credits (~$0.10) per lead. Tight rate limit (20s between API calls).
"""
import csv
import io
import os
import sys
import time
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from bots.shared.standards import get_logger, tg, STATE_DIR
from bots.shared.crm_client import crm

log = get_logger("tracerfy_lead_bot")

TOKEN       = os.getenv("TRACERFY_TOKEN", "")
API_BASE    = "https://tracerfy.com/v1/api"
STATE_FILE  = os.path.join(STATE_DIR, "tracerfy_lead_bot.json")

# Target market: Atlanta metro. Expand once pipeline proven.
DEFAULT_GEOGRAPHY = {
    "mode":   "city",
    "cities": ["Atlanta"],
    "states": ["GA"],
}
REQUESTED_COUNT        = 25    # leads per run
POLL_INTERVAL_SECONDS  = 25    # Tracerfy rate-limits at 20s — pad to 25
MAX_POLL_ATTEMPTS      = 12    # up to 5 minutes total


def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type":  "application/json",
    }


def get_balance() -> Optional[int]:
    try:
        r = requests.get(f"{API_BASE}/analytics/", headers=_headers(), timeout=15)
        if r.ok:
            return r.json().get("balance")
    except Exception as e:
        log.warning(f"balance check failed: {e}")
    return None


def request_leads(geography: Dict, count: int) -> Optional[int]:
    """Kick off a Lead Builder run. Returns lead_builder_id on success."""
    body = {"geography": geography, "requested_count": count}
    try:
        r = requests.post(
            f"{API_BASE}/lead-builder/execute/",
            headers=_headers(), json=body, timeout=30,
        )
        if r.status_code == 202:
            data = r.json()
            log.info(f"Lead Builder queued: id={data.get('id')} max_credits={data.get('max_credit_cost')}")
            return data.get("id")
        log.error(f"Lead Builder POST {r.status_code}: {r.text[:300]}")
    except Exception as e:
        log.error(f"Lead Builder request error: {e}")
    return None


def poll_queue(lead_id: int) -> Optional[str]:
    """Poll until complete. Returns download_url or None on timeout/failure."""
    for attempt in range(MAX_POLL_ATTEMPTS):
        time.sleep(POLL_INTERVAL_SECONDS)
        try:
            r = requests.get(f"{API_BASE}/lead-builder/{lead_id}/", headers=_headers(), timeout=15)
            if not r.ok:
                log.warning(f"poll #{attempt+1} {lead_id}: HTTP {r.status_code}")
                continue
            data   = r.json()
            status = data.get("status")
            log.info(f"poll #{attempt+1} {lead_id}: status={status} progress={data.get('progress_percent')}%")
            if status == "complete":
                return data.get("download_url")
            if status in ("failed", "error"):
                log.error(f"Lead Builder {lead_id} failed: {data.get('error_message')}")
                return None
        except Exception as e:
            log.warning(f"poll error: {e}")
    log.warning(f"Lead Builder {lead_id} timed out after {MAX_POLL_ATTEMPTS * POLL_INTERVAL_SECONDS}s")
    return None


def download_csv(url: str) -> List[Dict]:
    try:
        r = requests.get(url, timeout=30)
        if not r.ok:
            log.error(f"CSV download HTTP {r.status_code}")
            return []
        reader = csv.DictReader(io.StringIO(r.text))
        return list(reader)
    except Exception as e:
        log.error(f"CSV download error: {e}")
        return []


def _clean(value: str) -> str:
    return (value or "").strip()


def _best_contact(row: Dict) -> Dict[str, str]:
    """Pick the first non-empty phone/email from the Tracerfy columns."""
    phone = ""
    for k in ("mobile_1", "mobile_2", "mobile_3", "primary_phone", "landline_1", "landline_2"):
        val = _clean(row.get(k, ""))
        if val:
            phone = val
            break
    email = ""
    for k in ("email_1", "email_2", "email_3"):
        val = _clean(row.get(k, ""))
        if val:
            email = val
            break
    return {"phone": phone, "email": email}


def _distress_signals(row: Dict) -> List[str]:
    """Extract motivation/distress tags from Tracerfy flags."""
    tags = []
    flag_map = {
        "absentee_owner":  "absentee",
        "tax_delinquent":  "tax_delinquent",
        "pre_foreclosure": "pre_foreclosure",
        "free_clear":      "free_and_clear",
        "high_equity":     "high_equity",
        "inherited":       "inherited",
        "death":           "death",
        "judgment":        "judgment",
        "vacant":          "vacant",
        "corporate_owned": "corporate_owner",
    }
    for key, tag in flag_map.items():
        if _clean(row.get(key, "")).lower() == "true":
            tags.append(tag)
    return tags


def _motivation_score(tags: List[str]) -> int:
    """Rough 0-100 motivation score from distress flags."""
    weights = {
        "pre_foreclosure": 35,
        "tax_delinquent":  25,
        "absentee":        20,
        "high_equity":     10,
        "vacant":          10,
        "inherited":       15,
        "death":           10,
        "judgment":        10,
        "free_and_clear":   5,
    }
    return min(100, sum(weights.get(t, 0) for t in tags))


def _row_to_crm_payload(row: Dict) -> Optional[Dict]:
    address = _clean(row.get("address", ""))
    if not address:
        return None

    contact    = _best_contact(row)
    tags       = _distress_signals(row)
    motivation = _motivation_score(tags)

    owner_first = _clean(row.get("owner_1_first_name", ""))
    owner_last  = _clean(row.get("owner_1_last_name", ""))
    owner_name  = f"{owner_first} {owner_last}".strip()

    # Parse estimated_value as int
    est_value = _clean(row.get("estimated_value", "0")) or "0"
    try:
        arv_int = int(float(est_value))
    except ValueError:
        arv_int = 0

    # Parse beds/baths
    try:
        beds = int(_clean(row.get("beds", "0")) or "0")
    except ValueError:
        beds = 0
    try:
        baths = float(_clean(row.get("baths", "0")) or "0")
    except ValueError:
        baths = 0.0

    return {
        "address":           address,
        "city":              _clean(row.get("city", "")),
        "state":             _clean(row.get("state", "")),
        "zip":               _clean(row.get("zip_code", "")),
        "market":            _clean(row.get("city", "")),
        "source":            "Tracerfy",
        "source_url":        f"APN:{_clean(row.get('apn', ''))}",
        "arv":               arv_int,
        "beds":              beds,
        "baths":             baths,
        "sqft":              int(_clean(row.get("building_size_sqft", "0")) or "0"),
        "lot_sqft":          int(_clean(row.get("lot_size_sqft", "0")) or "0"),
        "year_built":        int(_clean(row.get("year_built", "0")) or "0"),
        "property_type":     _clean(row.get("property_type", "")),
        "seller_name":       owner_name,
        "contact_name":      owner_name,
        "seller_phone":      contact["phone"],
        "contact_phone":     contact["phone"],
        "seller_email":      contact["email"],
        "contact_email":     contact["email"],
        "distress_signals":  ",".join(tags),
        "motivation_score":  motivation,
        "status":            "hot" if motivation >= 40 else "new",  # NOTE: upsert will still PATCH existing rows — see _row_to_crm_payload caller. Mitigation: skip status on update. See upsert call.
        "notes":             f"Tracerfy import {motivation}/100 motivation. Tags: {', '.join(tags) or 'none'}. Mail: {_clean(row.get('mail_address',''))}, {_clean(row.get('mail_city',''))}, {_clean(row.get('mail_state',''))}",
    }


def ingest_into_crm(rows: List[Dict]) -> Dict:
    created, updated, skipped, hot = 0, 0, 0, 0
    for row in rows:
        if _clean(row.get("has_contact", "")).lower() != "true":
            # Don't burn outreach budget on leads with no contact info
            skipped += 1
            continue
        payload = _row_to_crm_payload(row)
        if not payload:
            skipped += 1
            continue
        existing = crm.find_property(payload.get("address", ""))
        if existing:
            # Don't clobber status on re-import — only patch data fields
            payload.pop("status", None)
        result = crm.upsert_property(payload)
        if not result:
            skipped += 1
            continue
        if result.get("_action") == "created":
            created += 1
        else:
            updated += 1
        if payload.get("status") == "hot":
            hot += 1
    return {"created": created, "updated": updated, "skipped_no_contact": skipped, "hot": hot}


def run() -> Dict:
    if not TOKEN:
        log.error("TRACERFY_TOKEN not set in .env")
        return {"error": "no_token"}

    balance_before = get_balance()
    if balance_before is not None and balance_before < REQUESTED_COUNT * 5:
        msg = f"Tracerfy balance low: {balance_before} credits. Need ~{REQUESTED_COUNT * 5}."
        log.warning(msg)
        tg(f"⚠️ {msg}", level="warning")
        return {"error": "low_balance", "balance": balance_before}

    log.info(f"Starting Tracerfy lead run — requesting {REQUESTED_COUNT} leads. Balance: {balance_before}")

    lead_id = request_leads(DEFAULT_GEOGRAPHY, REQUESTED_COUNT)
    if not lead_id:
        tg("❌ Tracerfy Lead Builder request failed", level="error")
        return {"error": "request_failed"}

    download_url = poll_queue(lead_id)
    if not download_url:
        tg(f"⚠️ Tracerfy Lead Builder queue {lead_id} timed out", level="warning")
        return {"error": "poll_timeout", "lead_id": lead_id}

    rows = download_csv(download_url)
    log.info(f"Downloaded {len(rows)} rows from queue {lead_id}")

    stats = ingest_into_crm(rows)
    balance_after = get_balance()
    credits_used  = (balance_before or 0) - (balance_after or 0)

    summary = (
        f"<b>🏠 Tracerfy Lead Run — Complete</b>\n\n"
        f"Queue #{lead_id}\n"
        f"Leads ingested: {stats['created']} new, {stats['updated']} updated\n"
        f"Hot prospects (motivation ≥ 40): {stats['hot']}\n"
        f"Skipped (no contact): {stats['skipped_no_contact']}\n\n"
        f"Credits used: {credits_used} | Balance: {balance_after}"
    )
    tg(summary, level="info")
    log.info(f"Run complete: {stats}, credits_used={credits_used}, balance_after={balance_after}")

    return {
        "lead_id":        lead_id,
        "rows_downloaded": len(rows),
        "balance_before":  balance_before,
        "balance_after":   balance_after,
        "credits_used":    credits_used,
        **stats,
    }


if __name__ == "__main__":
    result = run()
    print(result)
