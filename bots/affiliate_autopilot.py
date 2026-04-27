"""Affiliate Autopilot — Playwright-driven semi-automated signup runner.

Honest framing: each affiliate signup form is unique, so pure automation
isn't realistic. This bot is a CO-PILOT:

  1. Loads your profile (name, email, site URL, etc.) from
     bots/state/affiliate_profile.json
  2. Loads the list of programs to apply to from
     bots/state/affiliate_targets.json
  3. For each pending program, opens the signup URL in headed Chromium
  4. Auto-fills every input field whose name/placeholder/label looks like
     a known profile field (best-effort heuristics)
  5. Pauses, Telegram-pings you with what was filled and what's left
  6. You handle captcha / W9 / submit in the visible browser window
  7. Press ENTER in the Terminal where this is running → next program
     (or type 'skip' / 'fail' / 'q' to skip / fail / quit)
  8. Logs every status change to bots/state/affiliate_autopilot_status.json
  9. Telegram-ping summary on quit

Run:
    python3 -m bots.affiliate_autopilot
or:
    python3 -m bots.affiliate_autopilot --only koala,hostinger,fliki

The browser stays HEADED (visible) so you can see what's happening + take
over at any point. Closing the browser tab manually is treated as
"abandoned" for that program.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from playwright.sync_api import sync_playwright, Page, TimeoutError as PWTimeout

# Use the standards layer for Telegram (gracefully fall back if unavailable).
try:
    from bots.shared.standards import tg
except Exception:
    def tg(message: str, level: str = "info") -> None:
        print(f"[{level}] {message}")

PROFILE_PATH = Path(__file__).parent / "state" / "affiliate_profile.json"
TARGETS_PATH = Path(__file__).parent / "state" / "affiliate_targets.json"
STATUS_PATH = Path(__file__).parent / "state" / "affiliate_autopilot_status.json"

log = logging.getLogger("affiliate_autopilot")


# ─────────── field-name heuristics ───────────
# Map common form-field "names" / placeholders / labels → profile keys.
# Order matters: more specific patterns first.
FIELD_HEURISTICS = [
    # exact name keys
    (("first_name", "firstname", "first-name", "fname", "given-name"), "first_name"),
    (("last_name", "lastname", "last-name", "lname", "family-name", "surname"), "last_name"),
    (("full_name", "fullname", "full-name"), "full_name"),
    (("name",), "full_name"),  # generic "name" field
    (("email", "e-mail", "emailaddress"), "email"),
    (("phone", "tel", "mobile", "phonenumber"), "phone"),
    (("company", "company_name", "organization", "org", "business"), "company"),
    (("site", "website", "url", "websiteurl", "site_url", "blog", "blogurl"), "site_url"),
    (("twitter", "twitterurl", "twitterhandle"), "twitter_url"),
    (("linkedin", "linkedinurl"), "linkedin_url"),
    (("youtube", "youtubeurl", "channel"), "youtube_url"),
    (("instagram", "instagramurl"), "instagram_url"),
    (("country",), "country"),
    (("state", "region", "province"), "state"),
    (("city", "town"), "city"),
    (("address", "address1", "address_line_1", "street"), "address_line_1"),
    (("zip", "zipcode", "postalcode", "postal_code"), "postal_code"),
    (("audience", "audience_size", "monthlyvisitors", "visitors", "trafficsize", "traffic"), "monthly_visitors"),
    (("audience_description", "describe_audience", "about_audience"), "audience_description"),
    (("promotion_method", "promotional_method", "promotion", "marketing_channels"), "promotional_methods"),
    (("why", "why_promote", "why_join", "motivation"), "why_promote"),
    (("paypal", "paypal_email"), "paypal_email"),
    (("bio", "biography", "about"), "bio_short"),
]


def _to_keywords(s: str) -> str:
    return s.lower().replace("_", "").replace("-", "").replace(" ", "")


def field_match_profile_key(name: Optional[str], placeholder: Optional[str],
                            aria_label: Optional[str], label_text: Optional[str]) -> Optional[str]:
    """Inspect attributes of an <input> and pick the best profile key."""
    candidates = [_to_keywords(s) for s in (name, placeholder, aria_label, label_text) if s]
    if not candidates:
        return None
    for keywords, profile_key in FIELD_HEURISTICS:
        for cand in candidates:
            for kw in keywords:
                if kw in cand:
                    return profile_key
    return None


def fill_known_fields(page: Page, profile: dict) -> dict:
    """Walk every visible <input> on the page, attempt to fill from profile.
    Returns {filled: [{name, value}], skipped: [{name, reason}]}."""
    filled, skipped = [], []
    inputs = page.query_selector_all("input:not([type='hidden']):not([type='submit']):not([type='button'])")
    for inp in inputs:
        try:
            if not inp.is_visible():
                continue
            itype = (inp.get_attribute("type") or "text").lower()
            if itype in ("checkbox", "radio", "file", "hidden", "image", "submit", "reset", "button"):
                continue
            name = inp.get_attribute("name") or ""
            placeholder = inp.get_attribute("placeholder") or ""
            aria_label = inp.get_attribute("aria-label") or ""
            # Try associated <label>
            input_id = inp.get_attribute("id")
            label_text = ""
            if input_id:
                try:
                    lbl = page.query_selector(f"label[for='{input_id}']")
                    if lbl:
                        label_text = (lbl.inner_text() or "").strip()
                except Exception:
                    pass

            current_val = inp.input_value() if hasattr(inp, "input_value") else (inp.get_attribute("value") or "")
            if current_val.strip():
                # Already filled (e.g. browser autofill or pre-population) — skip.
                skipped.append({"name": name or placeholder or aria_label, "reason": "already_filled"})
                continue

            key = field_match_profile_key(name, placeholder, aria_label, label_text)
            if not key:
                skipped.append({"name": name or placeholder or aria_label, "reason": "no_match"})
                continue
            value = profile.get(key, "")
            if not value:
                skipped.append({"name": name, "reason": f"profile_{key}_empty"})
                continue

            # Email type? confirm it's an email-shaped value
            if itype == "email" and "@" not in value:
                skipped.append({"name": name, "reason": "value_not_email"})
                continue

            inp.fill(value)
            filled.append({"name": name or placeholder or aria_label, "key": key, "value_preview": value[:60]})
        except Exception as e:
            skipped.append({"name": name if 'name' in dir() else "?", "reason": f"fill_error: {str(e)[:80]}"})

    # textareas (e.g. "describe your audience")
    textareas = page.query_selector_all("textarea")
    for ta in textareas:
        try:
            if not ta.is_visible():
                continue
            name = ta.get_attribute("name") or ""
            placeholder = ta.get_attribute("placeholder") or ""
            aria_label = ta.get_attribute("aria-label") or ""
            input_id = ta.get_attribute("id")
            label_text = ""
            if input_id:
                lbl = page.query_selector(f"label[for='{input_id}']")
                if lbl:
                    label_text = (lbl.inner_text() or "").strip()
            current_val = ta.input_value() if hasattr(ta, "input_value") else ""
            if current_val.strip():
                skipped.append({"name": name, "reason": "already_filled"})
                continue
            key = field_match_profile_key(name, placeholder, aria_label, label_text)
            if not key:
                skipped.append({"name": name or placeholder or "<textarea>", "reason": "no_match"})
                continue
            value = profile.get(key, "")
            if not value:
                skipped.append({"name": name, "reason": f"profile_{key}_empty"})
                continue
            ta.fill(value)
            filled.append({"name": name or placeholder, "key": key, "value_preview": value[:80]})
        except Exception as e:
            skipped.append({"name": "<textarea>", "reason": f"fill_error: {str(e)[:80]}"})

    return {"filled": filled, "skipped": skipped}


def _load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text())


def _save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str))


def update_status(key: str, status: str, note: str = "") -> None:
    s = _load_json(STATUS_PATH, {})
    s[key] = {"status": status, "ts": datetime.utcnow().isoformat(), "note": note}
    _save_json(STATUS_PATH, s)


def run(only_keys: Optional[list[str]] = None, headed: bool = True) -> dict:
    profile = _load_json(PROFILE_PATH, {})
    targets_doc = _load_json(TARGETS_PATH, {"programs": []})
    if not profile or not profile.get("email"):
        msg = "affiliate_profile.json is missing or has no email — fill it before running."
        log.error(msg)
        return {"error": msg}

    queued = []
    for prog in targets_doc.get("programs", []):
        if only_keys and prog["key"] not in only_keys:
            continue
        if prog.get("status") in ("active", "blocked_partnerstack"):
            continue
        queued.append(prog)

    if not queued:
        return {"queued": 0, "note": "nothing to apply to"}

    print(f"\n🚀 Affiliate Autopilot — queued {len(queued)} program(s)\n")
    tg(f"🚀 Affiliate autopilot starting ({len(queued)} programs queued).", level="info")

    summary = {"applied": [], "skipped": [], "failed": []}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed,
                                    args=["--start-maximized", "--disable-blink-features=AutomationControlled"])
        context = browser.new_context(
            viewport=None,
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
        )

        for i, prog in enumerate(queued, 1):
            key = prog["key"]
            name = prog["name"]
            url = prog["signup_url"]
            print("\n" + "═" * 70)
            print(f"  [{i}/{len(queued)}] {name}")
            print(f"  → {url}")
            print(f"  network: {prog.get('network','?')} · commission: {prog.get('commission','?')}")
            if prog.get("notes"):
                print(f"  ⚠️  notes: {prog['notes']}")
            print("═" * 70)

            page = context.new_page()
            try:
                page.goto(url, timeout=45000, wait_until="domcontentloaded")
                page.wait_for_timeout(1500)  # let JS settle
                result = fill_known_fields(page, profile)
                f_count = len(result["filled"])
                print(f"\n  ✅ pre-filled {f_count} field(s):")
                for f in result["filled"]:
                    print(f"      • {f['name']:30s} ← profile.{f['key']}  ({f['value_preview'][:60]}…)")
                if result["skipped"]:
                    print(f"\n  ⏸  {len(result['skipped'])} field(s) couldn't be auto-filled (you'll handle them)")

                tg(
                    f"📋 <b>{name}</b> form opened — pre-filled {f_count} fields.\n"
                    f"Complete captcha/W9/submit in the browser, then press ENTER in Terminal "
                    f"(or 'skip', 'fail', 'q').",
                    level="info",
                )
                print("\n  >>> Switch to the Chromium window. Complete & submit. Then back here.")
                print("  >>> Type one of: ENTER (=applied), 'skip', 'fail', 'q' to quit.")
                ans = input("\n  next? ").strip().lower()
                if ans == "q":
                    update_status(key, "abandoned", "user quit")
                    print("\n👋 quitting autopilot.")
                    break
                if ans == "skip":
                    update_status(key, "skipped", "user skip")
                    summary["skipped"].append(name)
                    tg(f"⏭ Skipped {name}.", level="info")
                elif ans == "fail":
                    note = input("  fail reason (one line): ").strip()
                    update_status(key, "failed", note or "user marked failed")
                    summary["failed"].append(name)
                    tg(f"❌ Failed {name}: {note}", level="warning")
                else:
                    update_status(key, "applied", f"auto-filled {f_count} fields")
                    summary["applied"].append(name)
                    tg(f"✅ Applied to {name}.", level="success")
            except PWTimeout:
                update_status(key, "failed", "page timeout")
                summary["failed"].append(name)
                print(f"  🚨 page timeout for {name}")
            except Exception as e:
                update_status(key, "failed", f"exception: {str(e)[:120]}")
                summary["failed"].append(name)
                print(f"  🚨 error: {e}")
            finally:
                try:
                    page.close()
                except Exception:
                    pass

        browser.close()

    print("\n" + "═" * 70)
    print(f"\n  done. applied={len(summary['applied'])} skipped={len(summary['skipped'])} failed={len(summary['failed'])}\n")
    tg(
        f"🏁 Affiliate autopilot finished.\n"
        f"  ✅ applied: {len(summary['applied'])} ({', '.join(summary['applied']) or '—'})\n"
        f"  ⏭ skipped: {len(summary['skipped'])} ({', '.join(summary['skipped']) or '—'})\n"
        f"  ❌ failed: {len(summary['failed'])} ({', '.join(summary['failed']) or '—'})",
        level="success" if summary["applied"] else "info",
    )
    return summary


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="comma-separated list of program keys (e.g. koala,hostinger)")
    parser.add_argument("--headless", action="store_true", help="run headless (not recommended; you need to see the browser)")
    args = parser.parse_args()
    only = [k.strip() for k in args.only.split(",")] if args.only else None
    print(json.dumps(run(only_keys=only, headed=not args.headless), indent=2))


if __name__ == "__main__":
    main()
