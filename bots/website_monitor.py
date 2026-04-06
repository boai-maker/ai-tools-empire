"""
Bot 2: Website Monitor
Monitors aitoolsempire.co health and uptime.
"""
import logging
import time
from datetime import datetime

import requests

from config import config
from bots.shared.db_helpers import log_bot_event, upsert_bot_state
from bots.shared.notifier import notify

logger = logging.getLogger(__name__)

BOT_NAME = "website_monitor"
TIMEOUT = 15  # seconds per request


def check_homepage() -> dict:
    """
    GET request to SITE_URL. Returns status dict.
    """
    url = config.SITE_URL
    result = {"url": url, "status_code": None, "response_time_ms": None, "ok": False, "error": None}

    try:
        start = time.time()
        resp = requests.get(url, timeout=TIMEOUT, allow_redirects=True)
        elapsed_ms = int((time.time() - start) * 1000)

        result["status_code"] = resp.status_code
        result["response_time_ms"] = elapsed_ms
        result["ok"] = resp.status_code == 200
        if resp.status_code != 200:
            result["error"] = f"HTTP {resp.status_code}"
    except requests.Timeout:
        result["error"] = "Request timed out"
    except requests.ConnectionError as e:
        result["error"] = f"Connection error: {str(e)[:100]}"
    except Exception as e:
        result["error"] = f"Unexpected error: {str(e)[:100]}"

    return result


def check_key_pages() -> list:
    """
    Checks /articles, /tools, /newsletter pages.
    Returns list of check result dicts.
    """
    paths = ["/articles", "/tools", "/newsletter"]
    results = []

    for path in paths:
        url = config.SITE_URL.rstrip("/") + path
        result = {"url": url, "status_code": None, "response_time_ms": None, "ok": False, "error": None}

        try:
            start = time.time()
            resp = requests.get(url, timeout=TIMEOUT, allow_redirects=True)
            elapsed_ms = int((time.time() - start) * 1000)

            result["status_code"] = resp.status_code
            result["response_time_ms"] = elapsed_ms
            # 200 or 404 (page may not exist) is acceptable — flag anything 5xx as down
            result["ok"] = resp.status_code < 500
            if resp.status_code >= 500:
                result["error"] = f"Server error HTTP {resp.status_code}"
        except requests.Timeout:
            result["error"] = "Request timed out"
        except requests.ConnectionError as e:
            result["error"] = f"Connection error: {str(e)[:100]}"
        except Exception as e:
            result["error"] = f"Unexpected error: {str(e)[:100]}"

        results.append(result)

    return results


def check_sitemap() -> bool:
    """
    Checks if /sitemap.xml returns 200. Returns True if ok.
    """
    url = config.SITE_URL.rstrip("/") + "/sitemap.xml"
    try:
        resp = requests.get(url, timeout=TIMEOUT, allow_redirects=True)
        return resp.status_code == 200
    except Exception as e:
        logger.warning(f"Sitemap check failed: {e}")
        return False


def run_website_monitor() -> bool:
    """
    Runs all health checks. Logs results. Sends alert if anything is down.
    Saves last_run to bot_state. Returns True if all ok.
    """
    logger.info("Website Monitor: starting checks")
    all_ok = True

    try:
        homepage = check_homepage()
        key_pages = check_key_pages()
        sitemap_ok = check_sitemap()

        issues = []

        if not homepage["ok"]:
            all_ok = False
            msg = f"Homepage DOWN — {homepage.get('error') or homepage.get('status_code')}"
            issues.append(msg)
            logger.error(msg)

        for page in key_pages:
            if not page["ok"]:
                all_ok = False
                msg = f"Page DOWN: {page['url']} — {page.get('error') or page.get('status_code')}"
                issues.append(msg)
                logger.warning(msg)

        if not sitemap_ok:
            # Don't mark all_ok False for sitemap — just log
            logger.warning("Sitemap.xml not accessible")

        if issues:
            alert_msg = "SITE ALERT:\n" + "\n".join(issues)
            notify(alert_msg, level="error", use_telegram=True, use_email=True)
            log_bot_event(BOT_NAME, "site_down", alert_msg)
        else:
            response_time = homepage.get("response_time_ms", "?")
            log_bot_event(
                BOT_NAME,
                "check_ok",
                f"All pages OK. Homepage response: {response_time}ms. Sitemap: {sitemap_ok}"
            )
            logger.info(f"Website Monitor: all OK ({response_time}ms)")

    except Exception as e:
        logger.error(f"Website Monitor error: {e}")
        log_bot_event(BOT_NAME, "error", str(e))
        all_ok = False

    upsert_bot_state(BOT_NAME, "last_run", datetime.utcnow().isoformat())
    upsert_bot_state(BOT_NAME, "last_status", "ok" if all_ok else "issues_found")
    return all_ok
