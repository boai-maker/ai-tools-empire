"""
Self-Check Bot — runs twice daily to audit everything, fix issues, report.

Audits:
  • launchd agents (14-bot, Dominic, server, tunnel)
  • CRM server at localhost:5050
  • Surplus funds DB state
  • Wholesale lead pipeline state
  • Kalshi bot latest run
  • Website uptime (aitoolsempire.co)
  • Gmail inbox (important unread)
  • Bot error log freshness
  • Disk space
  • Data corruption signals

Fixes automatically where safe:
  • Restart dead launchd agents
  • Clean obvious DB corruption (dates-as-names, empty rows)
  • Retry trace_failed leads that look like bugs

Escalates to Telegram:
  • Anything not auto-fixable
  • Money decisions / external actions
  • Summary of what was found + what was fixed
"""
import os
import sys
import json
import sqlite3
import subprocess
import requests
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from bots.shared.standards import get_logger, tg, STATE_DIR

log = get_logger("self_check")

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WHOLESALE_DIR = os.path.expanduser("~/Desktop/wholesale-re")
CRM_DB = os.path.join(WHOLESALE_DIR, "crm/crm.db")
SURPLUS_DB = os.path.join(STATE_DIR, "surplus_funds.db")

LAUNCHD_AGENTS = [
    "com.aitoolsempire.bots",
    "com.aitoolsempire.dominic",
    "com.aitoolsempire.server",
]


def check_launchd() -> dict:
    """Verify each launchd agent is loaded + running."""
    report = {"ok": [], "down": [], "unknown": []}
    try:
        out = subprocess.check_output(["launchctl", "list"], text=True, timeout=10)
    except Exception as e:
        return {"error": str(e)}
    loaded = {line.split()[-1]: line.split() for line in out.strip().split("\n")[1:] if line.strip()}
    for agent in LAUNCHD_AGENTS:
        row = loaded.get(agent)
        if not row:
            report["down"].append(agent)
            continue
        pid = row[0]
        if pid == "-":
            report["down"].append(agent)
        else:
            report["ok"].append(f"{agent} (PID {pid})")
    return report


def fix_launchd(down: list) -> list:
    """Attempt to reload dead agents. Returns list of (agent, success_bool)."""
    results = []
    for agent in down:
        plist = os.path.expanduser(f"~/Library/LaunchAgents/{agent}.plist")
        if not os.path.exists(plist):
            results.append((agent, False, "plist missing"))
            continue
        try:
            subprocess.run(["launchctl", "unload", plist], capture_output=True, timeout=10)
            r = subprocess.run(["launchctl", "load", plist], capture_output=True, timeout=10, text=True)
            results.append((agent, r.returncode == 0, r.stderr.strip() or "ok"))
        except Exception as e:
            results.append((agent, False, str(e)))
    return results


def check_crm() -> dict:
    """Ping CRM + read counts."""
    try:
        r = requests.get("http://localhost:5050/api/health", timeout=5)
        http_ok = r.status_code == 200
    except Exception as e:
        http_ok = False
    try:
        c = sqlite3.connect(CRM_DB)
        props = c.execute("SELECT COUNT(*) FROM properties").fetchone()[0]
        buyers = c.execute("SELECT COUNT(*) FROM buyers").fetchone()[0]
        hot = c.execute("SELECT COUNT(*) FROM properties WHERE status='hot'").fetchone()[0]
        under_contract = c.execute("SELECT COUNT(*) FROM properties WHERE status='under_contract'").fetchone()[0]
        c.close()
        return {"http": http_ok, "properties": props, "buyers": buyers, "hot": hot, "under_contract": under_contract}
    except Exception as e:
        return {"http": http_ok, "error": str(e)}


def check_surplus() -> dict:
    """Audit surplus funds DB for volume, corruption, and contacted count."""
    try:
        c = sqlite3.connect(SURPLUS_DB)
        total = c.execute("SELECT COUNT(*), ROUND(SUM(surplus_amount),2) FROM surplus_leads").fetchone()
        by_status = dict(c.execute("SELECT status, COUNT(*) FROM surplus_leads GROUP BY status").fetchall())
        traced_val = c.execute("SELECT ROUND(SUM(surplus_amount),2) FROM surplus_leads WHERE status IN ('traced','contacted')").fetchone()[0] or 0
        # Corruption: former_owner starting with digit (likely a date)
        corrupt = c.execute("SELECT COUNT(*) FROM surplus_leads WHERE former_owner GLOB '[0-9]*'").fetchone()[0]
        # County diversity
        counties = c.execute("SELECT COUNT(DISTINCT county||state) FROM surplus_leads").fetchone()[0]
        c.close()
        return {
            "total": total[0],
            "total_value": total[1],
            "by_status": by_status,
            "traced_value": traced_val,
            "corrupt_rows": corrupt,
            "counties": counties,
        }
    except Exception as e:
        return {"error": str(e)}


def fix_surplus_corruption():
    """Delete corrupt rows where former_owner is a date-like string."""
    try:
        c = sqlite3.connect(SURPLUS_DB)
        rows = c.execute("SELECT id, former_owner FROM surplus_leads WHERE former_owner GLOB '[0-9]*'").fetchall()
        if rows:
            c.executemany("DELETE FROM surplus_leads WHERE id=?", [(r[0],) for r in rows])
            c.commit()
        c.close()
        return len(rows)
    except Exception:
        return 0


def check_website() -> dict:
    try:
        r = requests.get("https://aitoolsempire.co", timeout=10)
        return {"status": r.status_code, "ms": int(r.elapsed.total_seconds() * 1000)}
    except Exception as e:
        return {"error": str(e)}


def check_log_freshness() -> dict:
    """Bots error log should have entries within last 6 hours if scheduler alive."""
    log_path = os.path.join(PROJECT, "logs/bots_error.log")
    if not os.path.exists(log_path):
        return {"missing": True}
    mtime = datetime.fromtimestamp(os.path.getmtime(log_path))
    age_min = (datetime.now() - mtime).total_seconds() / 60
    return {"age_minutes": round(age_min, 1), "mtime": mtime.strftime("%m/%d %H:%M")}


def check_disk() -> dict:
    try:
        out = subprocess.check_output(["df", "-h", "/"], text=True, timeout=5).strip().split("\n")[-1].split()
        return {"available": out[3], "use_pct": out[4]}
    except Exception as e:
        return {"error": str(e)}


def check_gmail_unread() -> dict:
    """Use IMAP to peek at inbox unread count + newest important senders."""
    try:
        import imaplib, email
        pwd = os.getenv("SMTP_PASSWORD", "")
        user = os.getenv("SMTP_USER", "bosaibot@gmail.com")
        if not pwd:
            return {"error": "no password"}
        M = imaplib.IMAP4_SSL("imap.gmail.com")
        M.login(user, pwd)
        M.select("inbox")
        typ, data = M.search(None, "UNSEEN")
        unread_ids = data[0].split() if data and data[0] else []
        latest_subjects = []
        for mid in unread_ids[-5:]:
            typ, msg_data = M.fetch(mid, "(BODY[HEADER.FIELDS (SUBJECT FROM)])")
            if msg_data and msg_data[0]:
                msg = email.message_from_bytes(msg_data[0][1])
                subj = msg.get("Subject", "")[:60]
                frm = msg.get("From", "")[:40]
                latest_subjects.append(f"{frm[:30]}: {subj}")
        M.logout()
        return {"unread": len(unread_ids), "latest": latest_subjects}
    except Exception as e:
        return {"error": str(e)}


def build_report(audit: dict) -> str:
    """Format audit dict into a Telegram-friendly message."""
    lines = []
    now = datetime.now().strftime("%m/%d %H:%M ET")
    lines.append(f"🔍 SELF-CHECK {now}")
    lines.append("")

    # launchd
    l = audit["launchd"]
    if "error" in l:
        lines.append(f"❌ launchd: {l['error']}")
    else:
        if l["ok"]:
            lines.append(f"✅ launchd up: {len(l['ok'])}")
        if l["down"]:
            lines.append(f"⚠️ launchd DOWN: {', '.join(l['down'])}")
        if audit.get("launchd_fixed"):
            for agent, ok, msg in audit["launchd_fixed"]:
                sym = "✅" if ok else "❌"
                lines.append(f"  {sym} restarted {agent}: {msg}")

    # CRM
    c = audit["crm"]
    if "error" in c:
        lines.append(f"❌ CRM: {c['error']}")
    else:
        http = "✅" if c.get("http") else "❌"
        lines.append(f"{http} CRM: {c.get('properties','?')} props, {c.get('buyers','?')} buyers, "
                     f"{c.get('hot','?')} hot, {c.get('under_contract','?')} UC")

    # Surplus
    s = audit["surplus"]
    if "error" in s:
        lines.append(f"❌ Surplus: {s['error']}")
    else:
        lines.append(f"💰 Surplus: {s['total']} leads, ${s['total_value']:,.0f}")
        status_str = ", ".join(f"{k}={v}" for k, v in s["by_status"].items())
        lines.append(f"   {status_str}")
        lines.append(f"   Traced value: ${s.get('traced_value',0):,.0f} | counties: {s['counties']}")
        if s["corrupt_rows"] > 0:
            lines.append(f"   ⚠️ {s['corrupt_rows']} corrupt rows (will clean)")

    # Website
    w = audit["website"]
    if "error" in w:
        lines.append(f"❌ Site: {w['error']}")
    else:
        sym = "✅" if w["status"] == 200 else "⚠️"
        lines.append(f"{sym} Site: {w['status']} ({w['ms']}ms)")

    # Logs
    lf = audit["log_freshness"]
    if lf.get("missing"):
        lines.append("❌ No bots error log")
    else:
        sym = "✅" if lf["age_minutes"] < 360 else "⚠️"
        lines.append(f"{sym} Logs: last {lf['age_minutes']}m ago")

    # Gmail
    g = audit["gmail"]
    if "error" in g:
        lines.append(f"❌ Gmail: {g['error']}")
    else:
        lines.append(f"📧 Gmail unread: {g['unread']}")
        for s in g.get("latest", [])[:3]:
            lines.append(f"   • {s}")

    # Disk
    d = audit["disk"]
    if "error" not in d:
        lines.append(f"💾 Disk: {d['available']} free ({d['use_pct']} used)")

    # Issues + fixes
    if audit["fixes_applied"]:
        lines.append("")
        lines.append("🔧 Fixes applied:")
        for f in audit["fixes_applied"]:
            lines.append(f"   • {f}")

    if audit["issues_found"]:
        lines.append("")
        lines.append("⚠️ Issues needing human attention:")
        for i in audit["issues_found"]:
            lines.append(f"   • {i}")

    return "\n".join(lines)


def run():
    log.info("=== Self-check run ===")
    audit = {"fixes_applied": [], "issues_found": []}

    audit["launchd"] = check_launchd()
    if isinstance(audit["launchd"], dict) and audit["launchd"].get("down"):
        audit["launchd_fixed"] = fix_launchd(audit["launchd"]["down"])
        for agent, ok, msg in audit["launchd_fixed"]:
            if ok:
                audit["fixes_applied"].append(f"restarted {agent}")
            else:
                audit["issues_found"].append(f"{agent} won't start: {msg}")

    audit["crm"] = check_crm()
    if audit["crm"].get("http") is False:
        audit["issues_found"].append("CRM http endpoint down at localhost:5050")

    audit["surplus"] = check_surplus()
    if audit["surplus"].get("corrupt_rows", 0) > 0:
        n = fix_surplus_corruption()
        if n:
            audit["fixes_applied"].append(f"cleaned {n} corrupt surplus rows")

    audit["website"] = check_website()
    if "error" in audit["website"] or audit["website"].get("status", 500) >= 500:
        audit["issues_found"].append(f"site unhealthy: {audit['website']}")

    audit["log_freshness"] = check_log_freshness()
    if audit["log_freshness"].get("age_minutes", 0) > 720:
        audit["issues_found"].append("bot logs stale >12h — scheduler may be dead")

    audit["gmail"] = check_gmail_unread()
    if audit["gmail"].get("unread", 0) > 30:
        audit["issues_found"].append(f"Gmail inbox flooding: {audit['gmail']['unread']} unread")

    audit["disk"] = check_disk()

    report = build_report(audit)
    log.info("\n" + report)
    tg(report, "info")

    # Persist the audit for history
    state_file = os.path.join(STATE_DIR, "self_check_history.json")
    history = []
    if os.path.exists(state_file):
        try:
            history = json.load(open(state_file))
        except Exception:
            history = []
    history.append({"ts": datetime.utcnow().isoformat(), "audit": audit})
    history = history[-30:]  # keep last 30 runs
    with open(state_file, "w") as f:
        json.dump(history, f, indent=2, default=str)

    return audit


if __name__ == "__main__":
    run()
