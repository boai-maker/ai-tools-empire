"""
Beehiiv subscription client — minimal wrapper so every /subscribe and
/stack-audit/submit signup gets pushed into beehiiv for automation.

Docs: https://developers.beehiiv.com/api-reference/subscriptions

Env vars:
  BEEHIIV_API_KEY  (required)
  BEEHIIV_PUB_ID   (required — UUID, we prepend `pub_` automatically)
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import requests

log = logging.getLogger(__name__)

API_BASE   = "https://api.beehiiv.com/v2"
API_KEY    = os.getenv("BEEHIIV_API_KEY", "").strip()
PUB_ID_RAW = os.getenv("BEEHIIV_PUB_ID", "").strip()

# Beehiiv expects `pub_<uuid>` on URLs. Accept either form in .env.
PUB_ID = PUB_ID_RAW if PUB_ID_RAW.startswith("pub_") else f"pub_{PUB_ID_RAW}"


def _enabled() -> bool:
    return bool(API_KEY) and bool(PUB_ID_RAW)


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type":  "application/json",
    }


def subscribe(
    email: str,
    *,
    utm_source: Optional[str]   = None,
    utm_medium: Optional[str]   = None,
    utm_campaign: Optional[str] = None,
    referring_site: Optional[str] = None,
    send_welcome_email: bool = True,
    reactivate_existing: bool = True,
    custom_fields: Optional[dict] = None,
) -> tuple[bool, str]:
    """
    Create (or reactivate) a subscriber. Returns (ok, message).

    Fire-and-forget from the caller's perspective — never raises.
    """
    if not _enabled():
        return False, "beehiiv_not_configured"
    if not email or "@" not in email:
        return False, "invalid_email"

    payload = {
        "email": email.strip().lower(),
        "reactivate_existing": reactivate_existing,
        "send_welcome_email":  send_welcome_email,
    }
    if utm_source:     payload["utm_source"]     = utm_source
    if utm_medium:     payload["utm_medium"]     = utm_medium
    if utm_campaign:   payload["utm_campaign"]   = utm_campaign
    if referring_site: payload["referring_site"] = referring_site
    if custom_fields:  payload["custom_fields"]  = [
        {"name": k, "value": v} for k, v in custom_fields.items()
    ]

    try:
        r = requests.post(
            f"{API_BASE}/publications/{PUB_ID}/subscriptions",
            headers=_headers(),
            json=payload,
            timeout=8,
        )
        if r.ok:
            log.info(f"beehiiv subscribed {email} (source={utm_source})")
            return True, "ok"
        log.warning(f"beehiiv subscribe failed {email}: HTTP {r.status_code} {r.text[:300]}")
        return False, f"http_{r.status_code}"
    except Exception as e:
        log.warning(f"beehiiv subscribe exception {email}: {e}")
        return False, str(e)


def publication_info() -> Optional[dict]:
    """Return basic publication metadata or None on failure. Used for health checks."""
    if not _enabled():
        return None
    try:
        r = requests.get(
            f"{API_BASE}/publications/{PUB_ID}",
            headers=_headers(),
            timeout=8,
        )
        if r.ok:
            return r.json().get("data")
    except Exception:
        pass
    return None


__all__ = ["subscribe", "publication_info"]
