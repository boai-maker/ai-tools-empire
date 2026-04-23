"""
Revenue Monitor — single source of truth for every cent flowing into the empire.

Pulls from every active revenue source and produces one consolidated Telegram
report plus a JSON snapshot (bots/state/revenue_monitor.json) that other bots
and dashboards can read.

Current sources:
  1. Affiliate clicks (data.db) → estimated $ via per-tool EPC @ 2% conv
  2. Kalshi trading (~/.kalshi/kalshi_auto_state.json + history) → daily PnL + YTD
  3. Wholesale RE pipeline (~/Desktop/wholesale-re/crm/crm.db) → projected fees

Stubbed (wire in when live):
  4. Gumroad (Pipeline Hunter + future kits)
  5. Fiverr (manual entry fallback)

Run ad-hoc:
    python3 -m bots.revenue_monitor
or let the scheduler fire it once a day from run_bots.py.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from bots.shared.notifier import notify_admin
from database.db import get_conn

logger = logging.getLogger(__name__)

BOT_NAME = "revenue_monitor"
STATE_PATH = Path(__file__).parent / "state" / "revenue_monitor.json"
KALSHI_STATE = Path.home() / ".kalshi" / "kalshi_auto_state.json"
KALSHI_HISTORY = Path.home() / ".kalshi" / "kalshi_auto_history.json"
WHOLESALE_DB = Path.home() / "Desktop" / "wholesale-re" / "crm" / "crm.db"
GUMROAD_OVERRIDE = Path(__file__).parent / "state" / "gumroad_manual.json"
FIVERR_OVERRIDE = Path(__file__).parent / "state" / "fiverr_manual.json"


# ───────────────────────── Affiliate ─────────────────────────


def affiliate_stream() -> dict:
    """Actual realized + today's estimated affiliate revenue using per-tool EPC."""
    from affiliate.links import AFFILIATE_PROGRAMS

    CONVERSION = 0.02

    def epc(meta: dict) -> float:
        if meta.get("commission_flat"):
            return float(meta["commission_flat"]) * CONVERSION
        pct = meta.get("commission_pct") or 0
        return (float(meta.get("avg_sale", 0)) * pct / 100.0) * CONVERSION

    active = {k for k, v in AFFILIATE_PROGRAMS.items() if v.get("is_active") is True}

    def bucket(start_iso: str) -> dict:
        conn = get_conn()
        rows = conn.execute(
            "SELECT tool_key, COUNT(*) AS n FROM affiliate_clicks WHERE clicked_at >= ? GROUP BY tool_key",
            (start_iso,),
        ).fetchall()
        conn.close()
        mon = unatt = 0
        est_rev = lost = 0.0
        for row in rows:
            meta = AFFILIATE_PROGRAMS.get(row["tool_key"], {})
            est = row["n"] * epc(meta)
            if row["tool_key"] in active:
                mon += row["n"]
                est_rev += est
            else:
                unatt += row["n"]
                lost += est
        return {"monetized_clicks": mon, "unattributed_clicks": unatt, "est_revenue": round(est_rev, 2), "lost_potential": round(lost, 2)}

    today_start = datetime.utcnow().strftime("%Y-%m-%d 00:00:00")
    mtd_start = datetime.utcnow().replace(day=1).strftime("%Y-%m-%d 00:00:00")
    ytd_start = datetime.utcnow().replace(month=1, day=1).strftime("%Y-%m-%d 00:00:00")

    return {
        "source": "affiliate",
        "today": bucket(today_start),
        "mtd": bucket(mtd_start),
        "ytd": bucket(ytd_start),
    }


# ───────────────────────── Kalshi ────────────────────────────


def kalshi_stream() -> dict:
    """Daily PnL + historical win-rate from the kalshi_auto bot's state files."""
    today_pnl = 0.0
    trades_today = 0
    stop_triggered = False
    try:
        if KALSHI_STATE.exists():
            s = json.loads(KALSHI_STATE.read_text())
            today_pnl = float(s.get("daily_pnl") or 0)
            trades_today = len(s.get("trades") or [])
            stop_triggered = bool(s.get("stop_triggered"))
    except Exception as e:
        logger.warning(f"kalshi state read: {e}")

    total_trades = wins = 0
    ytd_start = datetime.utcnow().strftime("%Y-01-01")
    try:
        if KALSHI_HISTORY.exists():
            h = json.loads(KALSHI_HISTORY.read_text())
            for tr in h.get("trades", []):
                if tr.get("date", "") >= ytd_start:
                    total_trades += 1
                    if tr.get("won"):
                        wins += 1
    except Exception as e:
        logger.warning(f"kalshi history read: {e}")

    win_rate = (wins / total_trades) if total_trades else 0.0
    return {
        "source": "kalshi",
        "today": {"pnl": round(today_pnl, 2), "trades": trades_today, "stop": stop_triggered},
        "ytd": {"trades": total_trades, "wins": wins, "win_rate": round(win_rate, 3)},
    }


# ─────────────────────── Wholesale RE ────────────────────────


def wholesale_re_stream() -> dict:
    """Projected assignment fees in pipeline + counts by stage."""
    projected_low = projected_high = 0
    by_status: dict = {}
    count_with_email = 0
    try:
        if WHOLESALE_DB.exists():
            conn = sqlite3.connect(str(WHOLESALE_DB))
            conn.row_factory = sqlite3.Row
            for row in conn.execute("SELECT status, COUNT(*) n FROM properties GROUP BY status"):
                by_status[row["status"] or "unknown"] = row["n"]
            # Prefer explicit projections; fall back to 70%-rule math when null.
            row = conn.execute(
                """
                SELECT
                  COALESCE(SUM(
                    COALESCE(projected_spread_low,
                             MAX(arv * 0.70 - price - 10000, 0))
                  ), 0) AS low,
                  COALESCE(SUM(
                    COALESCE(projected_spread_high,
                             MAX(arv * 0.75 - price - 10000, 0))
                  ), 0) AS high
                FROM properties
                WHERE status IN ('qualified','offered','under_contract')
                  AND arv IS NOT NULL AND price IS NOT NULL
                """
            ).fetchone()
            projected_low, projected_high = int(row["low"] or 0), int(row["high"] or 0)
            count_with_email = conn.execute(
                "SELECT COUNT(*) FROM properties WHERE "
                "(seller_email IS NOT NULL AND seller_email != '') OR "
                "(contact_email IS NOT NULL AND contact_email != '')"
            ).fetchone()[0]
            conn.close()
    except Exception as e:
        logger.warning(f"wholesale_re read: {e}")
    return {
        "source": "wholesale_re",
        "by_status": by_status,
        "pipeline_projection_low": projected_low,
        "pipeline_projection_high": projected_high,
        "leads_with_email": count_with_email,
    }


# ────────────────── Manual overrides (future streams) ───────


def _manual_override(path: Path, label: str) -> dict:
    """Any JSON written to bots/state/{label}_manual.json gets included as-is.
    Use this to record Gumroad/Fiverr payouts until we wire their APIs.
    Expected shape: {"today": 0, "mtd": 0, "ytd": 0, "note": "..."}"""
    if path.exists():
        try:
            data = json.loads(path.read_text())
            return {"source": label, **data}
        except Exception as e:
            logger.warning(f"{label} override read: {e}")
    return {"source": label, "today": 0, "mtd": 0, "ytd": 0, "note": "not wired"}


# ─────────────────────────── Roll-up ─────────────────────────


def compute_snapshot() -> dict:
    affiliate = affiliate_stream()
    kalshi = kalshi_stream()
    wholesale = wholesale_re_stream()
    gumroad = _manual_override(GUMROAD_OVERRIDE, "gumroad")
    fiverr = _manual_override(FIVERR_OVERRIDE, "fiverr")

    today_total = (
        affiliate["today"]["est_revenue"]
        + kalshi["today"]["pnl"]
        + float(gumroad.get("today") or 0)
        + float(fiverr.get("today") or 0)
    )
    ytd_total = (
        affiliate["ytd"]["est_revenue"]
        + float(gumroad.get("ytd") or 0)
        + float(fiverr.get("ytd") or 0)
        # Kalshi YTD $ isn't in history.json (only win/loss) — treat separately
    )

    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "today_total_est": round(today_total, 2),
        "ytd_total_est": round(ytd_total, 2),
        "goal_daily": 100.0,
        "streams": {
            "affiliate": affiliate,
            "kalshi": kalshi,
            "wholesale_re": wholesale,
            "gumroad": gumroad,
            "fiverr": fiverr,
        },
    }


# ───────────────────── Telegram formatting ──────────────────


def format_telegram(snap: dict) -> str:
    aff = snap["streams"]["affiliate"]
    kal = snap["streams"]["kalshi"]
    who = snap["streams"]["wholesale_re"]
    gum = snap["streams"]["gumroad"]
    fiv = snap["streams"]["fiverr"]

    total = snap["today_total_est"]
    goal = snap["goal_daily"]
    pct = int(100 * total / goal) if goal else 0

    lines = [
        f"💰 <b>Revenue Snapshot — {datetime.utcnow().strftime('%a %b %d')}</b>",
        f"Today: <b>${total:,.2f}</b> / ${goal:,.0f} goal  ({pct}%)",
        "",
        "<b>Affiliate</b>",
        f"  today: ${aff['today']['est_revenue']:,.2f} "
        f"(paid {aff['today']['monetized_clicks']} / leak {aff['today']['unattributed_clicks']})",
        f"  MTD est: ${aff['mtd']['est_revenue']:,.2f}   YTD est: ${aff['ytd']['est_revenue']:,.2f}",
        f"  leaked today: ${aff['today']['lost_potential']:,.2f}",
        "",
        "<b>Kalshi</b>",
        f"  today PnL: ${kal['today']['pnl']:+,.2f}   trades: {kal['today']['trades']}"
        f"{'  [STOP]' if kal['today']['stop'] else ''}",
        f"  YTD: {kal['ytd']['wins']}/{kal['ytd']['trades']} wins ({int(kal['ytd']['win_rate']*100)}%)",
        "",
        "<b>Wholesale RE</b>",
        f"  pipeline: low ${who['pipeline_projection_low']:,} / high ${who['pipeline_projection_high']:,}",
        f"  leads w/ email: {who['leads_with_email']}   by status: "
        + ", ".join(f"{k}:{v}" for k, v in sorted(who['by_status'].items())),
        "",
        "<b>Gumroad + Fiverr</b>",
        f"  Gumroad today: ${float(gum.get('today') or 0):,.2f}   YTD: ${float(gum.get('ytd') or 0):,.2f} ({gum.get('note','')})",
        f"  Fiverr today:  ${float(fiv.get('today') or 0):,.2f}   YTD: ${float(fiv.get('ytd') or 0):,.2f} ({fiv.get('note','')})",
    ]
    return "\n".join(lines)


# ────────────────────────── Entry points ─────────────────────


def run_revenue_monitor(notify: bool = True) -> dict:
    """Compute snapshot, persist it, optionally fire Telegram."""
    snap = compute_snapshot()
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(snap, indent=2))
    if notify:
        msg = format_telegram(snap)
        notify_admin(f"💰 Revenue Snapshot — ${snap['today_total_est']:,.2f} today", msg)
    return snap


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    snap = run_revenue_monitor(notify=True)
    print(json.dumps(snap, indent=2))
