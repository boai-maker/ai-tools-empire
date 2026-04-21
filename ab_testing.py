"""
Minimal A/B testing framework for aitoolsempire.co.

Usage in a FastAPI route:

    from ab_testing import ensure_visitor_id, get_variant, record_event

    @app.get("/")
    async def homepage(request: Request, response: Response):
        vid = ensure_visitor_id(request, response)
        hero_cta = get_variant(vid, "hero-cta-v1", ["control", "drop_tools", "save_money"])
        record_event(vid, "hero-cta-v1", hero_cta, "view")
        ...

Usage in a Jinja2 template (requires the `ab` global registered):

    {% set cta = ab('hero-cta-v1', 'control', 'drop_tools', 'save_money') %}
    {% if cta == 'drop_tools' %}
      Tell me your stack, I'll say what to drop.
    {% elif cta == 'save_money' %}
      See what you can cut from your AI budget.
    {% else %}
      Get the free cheatsheet.
    {% endif %}

Design notes:
- Assignment is hash-based, sticky, no DB write on read. Writes happen only
  on events (view, click, signup).
- `visitor_id` is a UUID-ish token stored in a year-long cookie. No PII.
- Weights can be uniform (default) or per-variant (JSON in `experiments.weights`).
- All 3 tables are created lazily on first use.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import time
from typing import List, Optional

DB_PATH     = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.db")
COOKIE_NAME = "aite_vid"
COOKIE_TTL  = 365 * 24 * 3600   # 1 year

# ── Schema ────────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS experiments (
    id          TEXT PRIMARY KEY,
    variants    TEXT NOT NULL,               -- JSON array of variant names
    weights     TEXT,                        -- JSON {variant: weight} or null = uniform
    active      INTEGER DEFAULT 1,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS experiment_assignments (
    visitor_id      TEXT NOT NULL,
    experiment_id   TEXT NOT NULL,
    variant         TEXT NOT NULL,
    assigned_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (visitor_id, experiment_id)
);

CREATE TABLE IF NOT EXISTS experiment_events (
    visitor_id      TEXT NOT NULL,
    experiment_id   TEXT NOT NULL,
    variant         TEXT NOT NULL,
    event_name      TEXT NOT NULL,           -- 'view', 'click', 'signup', etc.
    event_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_exp_events_expid ON experiment_events(experiment_id);
CREATE INDEX IF NOT EXISTS idx_exp_events_vid   ON experiment_events(visitor_id);
"""

_schema_ready = False


def _conn() -> sqlite3.Connection:
    global _schema_ready
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    if not _schema_ready:
        conn.executescript(_SCHEMA)
        conn.commit()
        _schema_ready = True
    return conn


# ── Visitor ID cookie ─────────────────────────────────────────────────────────

def ensure_visitor_id(request, response) -> str:
    """Get or mint a visitor_id. Sets the cookie on response if new."""
    existing = request.cookies.get(COOKIE_NAME)
    if existing and len(existing) >= 16:
        return existing
    vid = secrets.token_urlsafe(24)
    response.set_cookie(
        COOKIE_NAME,
        vid,
        max_age=COOKIE_TTL,
        httponly=True,
        samesite="lax",
        secure=True,        # aitoolsempire.co is HTTPS in prod
    )
    return vid


# ── Variant assignment ────────────────────────────────────────────────────────

def get_variant(visitor_id: str, experiment_id: str, variants: List[str],
                weights: Optional[List[float]] = None,
                record_assignment: bool = True) -> str:
    """
    Deterministic, sticky variant assignment.

    Same (visitor_id, experiment_id) always returns the same variant even after
    a deploy. Writes a row to experiment_assignments the first time we see
    the pairing (unless record_assignment=False).
    """
    if not variants:
        return "control"

    # Hash visitor_id + experiment_id to a float 0..1 then bucket by weights
    h = hashlib.sha256(f"{visitor_id}::{experiment_id}".encode()).digest()
    bucket = int.from_bytes(h[:4], "big") / 0xFFFFFFFF

    if weights and len(weights) == len(variants):
        total = sum(weights)
        cutoffs = [sum(weights[:i + 1]) / total for i in range(len(weights))]
    else:
        n = len(variants)
        cutoffs = [(i + 1) / n for i in range(n)]

    variant = variants[-1]
    for v, cut in zip(variants, cutoffs):
        if bucket <= cut:
            variant = v
            break

    if record_assignment:
        try:
            conn = _conn()
            conn.execute(
                "INSERT OR IGNORE INTO experiment_assignments (visitor_id, experiment_id, variant) VALUES (?, ?, ?)",
                (visitor_id, experiment_id, variant),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

    return variant


# ── Event recording ───────────────────────────────────────────────────────────

def record_event(visitor_id: str, experiment_id: str, variant: str, event_name: str) -> None:
    """Log a view/click/signup/custom event. Fire-and-forget on error."""
    try:
        conn = _conn()
        conn.execute(
            "INSERT INTO experiment_events (visitor_id, experiment_id, variant, event_name) VALUES (?, ?, ?, ?)",
            (visitor_id, experiment_id, variant, event_name),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


# ── Reporting ─────────────────────────────────────────────────────────────────

def _wilson_ci(successes: int, trials: int, z: float = 1.96):
    """Wilson score 95% CI. Hand-rolled so no scipy dep needed."""
    if trials == 0:
        return (0.0, 0.0, 0.0)
    p = successes / trials
    denom = 1 + z * z / trials
    center = (p + z * z / (2 * trials)) / denom
    halfwidth = z * ((p * (1 - p) + z * z / (4 * trials)) / trials) ** 0.5 / denom
    return (p, max(0.0, center - halfwidth), min(1.0, center + halfwidth))


def summarize(experiment_id: str) -> dict:
    """
    Per-variant summary for one experiment. Returns:
      {
        "experiment_id": "...",
        "variants": [
          {
            "variant": "control",
            "assignments": 120,
            "views": 120,
            "clicks": 14,
            "signups": 3,
            "click_rate": (pct, lo, hi),
            "signup_rate": (pct, lo, hi)
          }, ...
        ]
      }
    """
    conn = _conn()

    assignments = {
        row["variant"]: row["n"]
        for row in conn.execute(
            "SELECT variant, COUNT(*) AS n FROM experiment_assignments WHERE experiment_id = ? GROUP BY variant",
            (experiment_id,),
        ).fetchall()
    }

    events: dict = {}
    for row in conn.execute(
        """
        SELECT variant, event_name, COUNT(*) AS n
        FROM experiment_events
        WHERE experiment_id = ?
        GROUP BY variant, event_name
        """,
        (experiment_id,),
    ).fetchall():
        events.setdefault(row["variant"], {})[row["event_name"]] = row["n"]

    conn.close()

    variants_summary = []
    for variant, n_assign in assignments.items():
        ev     = events.get(variant, {})
        views  = ev.get("view", 0) or n_assign
        clicks = ev.get("click", 0)
        signups = ev.get("signup", 0)
        variants_summary.append({
            "variant":     variant,
            "assignments": n_assign,
            "views":       views,
            "clicks":      clicks,
            "signups":     signups,
            "click_rate":  _wilson_ci(clicks, views),
            "signup_rate": _wilson_ci(signups, views),
        })

    # If events show variants not yet in assignments (rare), surface them too
    for variant in events:
        if variant not in assignments:
            ev = events[variant]
            variants_summary.append({
                "variant":     variant,
                "assignments": 0,
                "views":       ev.get("view", 0),
                "clicks":      ev.get("click", 0),
                "signups":     ev.get("signup", 0),
                "click_rate":  _wilson_ci(ev.get("click", 0), ev.get("view", 1)),
                "signup_rate": _wilson_ci(ev.get("signup", 0), ev.get("view", 1)),
            })

    return {
        "experiment_id": experiment_id,
        "variants":      sorted(variants_summary, key=lambda x: x["variant"]),
    }


# ── Jinja2 glue ────────────────────────────────────────────────────────────────

def register_jinja(templates, request_getter):
    """Register an `ab()` global on the Jinja env.

    request_getter is a callable that returns the current request (FastAPI
    doesn't pass it into templates by default — in our setup every ctx has
    `request`, so we rely on that).

    Usage in a handler:
        ctx = base_ctx(request)
        ctx['request'] = request   # already happens via Jinja2Templates
        return templates.TemplateResponse('index.html', ctx)
    """
    def ab(exp_id: str, *variants: str) -> str:
        # This is called during template render, so we don't have direct
        # access to the response object. We only read the cookie here;
        # the middleware in main.py actually sets it on first load.
        try:
            req = request_getter()
        except Exception:
            return variants[0] if variants else "control"
        vid = req.cookies.get(COOKIE_NAME, "") or "anon"
        if not variants:
            return "control"
        return get_variant(vid, exp_id, list(variants), record_assignment=True)

    templates.env.globals["ab"] = ab


__all__ = [
    "COOKIE_NAME",
    "ensure_visitor_id",
    "get_variant",
    "record_event",
    "summarize",
    "register_jinja",
]
