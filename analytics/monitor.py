"""
Site monitoring — runs hourly to detect outages, track rankings,
and alert you if anything breaks.
"""
import urllib.request
import urllib.error
import json
import logging
import os
from datetime import datetime

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# Always health-check localhost — the public domain may not be set up yet
SITE_URL = "http://localhost:8000"
ALERT_EMAIL = os.getenv("ADMIN_EMAIL", "")

HEALTH_CHECKS = [
    ("Homepage",    "/",             200),
    ("Tools page",  "/tools",        200),
    ("Articles",    "/articles",     200),
    ("Services",    "/services",     200),
    ("RSS Feed",    "/rss.xml",      200),
    ("Sitemap",     "/sitemap.xml",  200),
    ("Robots.txt",  "/robots.txt",   200),
    ("404 handler", "/nonexistent",  404),
]

def check_url(path: str, expected_status: int) -> dict:
    url = SITE_URL + path
    try:
        req = urllib.request.Request(url)
        res = urllib.request.urlopen(req, timeout=10)
        status = res.status
        body_size = len(res.read())
        ok = (status == expected_status)
        return {"url": url, "status": status, "ok": ok, "size": body_size, "error": None}
    except urllib.error.HTTPError as e:
        ok = (e.code == expected_status)
        return {"url": url, "status": e.code, "ok": ok, "size": 0, "error": None}
    except Exception as e:
        return {"url": url, "status": 0, "ok": False, "size": 0, "error": str(e)}

def run_health_check() -> dict:
    results = []
    all_ok = True
    for name, path, expected in HEALTH_CHECKS:
        result = check_url(path, expected)
        result["name"] = name
        results.append(result)
        status = "✅" if result["ok"] else "❌"
        log.info(f"{status} {name}: HTTP {result['status']} ({result['size']} bytes)")
        if not result["ok"]:
            all_ok = False
            log.error(f"HEALTH CHECK FAILED: {name} at {result['url']} — got {result['status']}, expected {expected}")

    summary = {
        "timestamp": datetime.now().isoformat(),
        "all_ok": all_ok,
        "passed": sum(1 for r in results if r["ok"]),
        "failed": sum(1 for r in results if not r["ok"]),
        "checks": results,
    }

    # Save report
    os.makedirs("data", exist_ok=True)
    with open("data/health_report.json", "w") as f:
        json.dump(summary, f, indent=2)

    return summary

def check_db_health() -> dict:
    """Check database is accessible and has expected data."""
    try:
        import sys
        sys.path.insert(0, ".")
        from database.db import get_conn
        conn = get_conn()
        articles = conn.execute("SELECT COUNT(*) FROM articles WHERE status='published'").fetchone()[0]
        subscribers = conn.execute("SELECT COUNT(*) FROM subscribers WHERE status='active'").fetchone()[0]
        clicks = conn.execute("SELECT COUNT(*) FROM affiliate_clicks").fetchone()[0]
        views = conn.execute("SELECT SUM(views) FROM articles").fetchone()[0] or 0
        conn.close()
        return {
            "ok": True,
            "articles": articles,
            "subscribers": subscribers,
            "total_clicks": clicks,
            "total_views": views,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}

def run_full_monitor():
    """Run complete monitoring check."""
    log.info(f"=== Health Check: {datetime.now().strftime('%Y-%m-%d %H:%M')} ===")

    # HTTP health checks
    http_report = run_health_check()
    log.info(f"HTTP: {http_report['passed']}/{len(HEALTH_CHECKS)} checks passed")

    # DB health
    db_report = check_db_health()
    if db_report["ok"]:
        log.info(f"DB: {db_report['articles']} articles, {db_report['subscribers']} subscribers, "
                 f"{db_report['total_clicks']} affiliate clicks, {db_report['total_views']} total views")
    else:
        log.error(f"DB check failed: {db_report.get('error')}")

    overall_ok = http_report["all_ok"] and db_report.get("ok", False)

    if not overall_ok:
        log.error("⚠️  MONITORING ALERT: Site health check failed!")
        # If Resend API key is available, send alert email
        if ALERT_EMAIL and os.getenv("RESEND_API_KEY"):
            try:
                send_alert_email(http_report, db_report)
            except Exception as e:
                log.error(f"Failed to send alert email: {e}")
    else:
        log.info("✅ All systems operational")

    return {"http": http_report, "db": db_report, "overall_ok": overall_ok}

def send_alert_email(http_report: dict, db_report: dict):
    """Send alert email when health checks fail."""
    try:
        import resend
        resend.api_key = os.getenv("RESEND_API_KEY")
        failed = [c for c in http_report["checks"] if not c["ok"]]
        body = f"""
<h2>⚠️ Site Health Alert</h2>
<p>Your AI Tools Empire site has failing health checks:</p>
<ul>
{"".join(f"<li>❌ {c['name']}: HTTP {c['status']} (expected success)</li>" for c in failed)}
</ul>
<p>Time: {http_report['timestamp']}</p>
<p>Check your server immediately.</p>
"""
        resend.Emails.send({
            "from": "alerts@aitoolsempire.co",
            "to": ALERT_EMAIL,
            "subject": f"⚠️ AI Tools Empire — {len(failed)} health check(s) failing",
            "html": body,
        })
        log.info(f"Alert email sent to {ALERT_EMAIL}")
    except Exception as e:
        log.error(f"Alert email failed: {e}")

if __name__ == "__main__":
    report = run_full_monitor()
    print(f"\n{'✅ ALL OK' if report['overall_ok'] else '❌ ISSUES DETECTED'}")
    if report["db"]["ok"]:
        print(f"Articles: {report['db']['articles']} | Subscribers: {report['db']['subscribers']} | Clicks: {report['db']['total_clicks']}")
