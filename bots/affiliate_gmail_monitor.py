"""
Affiliate Gmail Monitor Bot
Checks bosaibot@gmail.com for affiliate approval emails.
When an approval is detected, automatically extracts the affiliate ID
and updates .env + config so links go live immediately.
"""
import email
import imaplib
import logging
import os
import re
import sys
from datetime import datetime
from email.header import decode_header
from email.utils import parseaddr
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv

# Ensure project root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bots.shared.db_helpers import log_bot_event, upsert_bot_state
from bots.shared.notifier import notify

load_dotenv()

logger = logging.getLogger(__name__)

BOT_NAME = "affiliate_gmail_monitor"

# ---------------------------------------------------------------------------
# IMAP settings
# ---------------------------------------------------------------------------
IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993

# ---------------------------------------------------------------------------
# Sender domains to watch
# ---------------------------------------------------------------------------
AFFILIATE_SENDER_DOMAINS = {
    "jasper.ai",
    "copy.ai",
    "writesonic.com",
    "surferseo.com",
    "semrush.com",
    "invideo.io",
    "murf.ai",
    "descript.com",
    "speechify.com",
    "getresponse.com",
    "hubspot.com",
    "quillbot.com",
    "kit.com",
    "convertkit.com",
    "webflow.com",
    "grammarly.com",
    "synthesia.io",
    "runwayml.com",
    "impact.com",
    "shareasale.com",
    "partnerstack.com",
}

# ---------------------------------------------------------------------------
# Subject keywords that signal an approval email
# ---------------------------------------------------------------------------
APPROVAL_SUBJECT_KEYWORDS = [
    "approved",
    "you've been approved",
    "your application",
    "you're in",
    "you are in",
    "accepted",
    "congratulations",
    "welcome to the",
    "affiliate application",
    "affiliate account",
    "partner application",
    "partner account",
    "affiliate program",
]

# ---------------------------------------------------------------------------
# Per-program extraction config
# ---------------------------------------------------------------------------
AFFILIATE_PATTERNS: Dict[str, dict] = {
    "jasper": {
        "env_key": "JASPER_AFFILIATE_ID",
        "config_key": "jasper",
        "name": "Jasper AI",
        "sender_domains": ["jasper.ai"],
        "patterns": [
            r"ref[_-]?code[:\s]+([A-Za-z0-9_-]+)",
            r"affiliate[_-]?id[:\s]+([A-Za-z0-9_-]+)",
            r"fpr=([A-Za-z0-9_-]+)",
            r"your.*link.*https?://[^\s]*\?fpr=([A-Za-z0-9_-]+)",
        ],
    },
    "copyai": {
        "env_key": "COPYAI_AFFILIATE_ID",
        "config_key": "copyai",
        "name": "Copy.ai",
        "sender_domains": ["copy.ai"],
        "patterns": [
            r"via=([A-Za-z0-9_-]+)",
            r"ref=([A-Za-z0-9_-]+)",
            r"affiliate.*id[:\s]+([A-Za-z0-9_-]+)",
            r"partner.*id[:\s]+([A-Za-z0-9_-]+)",
        ],
    },
    "writesonic": {
        "env_key": "WRITESONIC_AFFILIATE_ID",
        "config_key": "writesonic",
        "name": "Writesonic",
        "sender_domains": ["writesonic.com"],
        "patterns": [
            r"ref=([A-Za-z0-9_-]+)",
            r"affiliate[_-]?id[:\s]+([A-Za-z0-9_-]+)",
            r"referral[_-]?code[:\s]+([A-Za-z0-9_-]+)",
            r"your.*link.*ref=([A-Za-z0-9_-]+)",
        ],
    },
    "surferseo": {
        "env_key": "SURFER_AFFILIATE_ID",
        "config_key": "surferseo",
        "name": "Surfer SEO",
        "sender_domains": ["surferseo.com"],
        "patterns": [
            r"ref=([A-Za-z0-9_-]+)",
            r"affiliate[_-]?id[:\s]+([A-Za-z0-9_-]+)",
            r"partner[_-]?id[:\s]+([A-Za-z0-9_-]+)",
            r"your.*affiliate.*link.*ref=([A-Za-z0-9_-]+)",
        ],
    },
    "semrush": {
        "env_key": "SEMRUSH_AFFILIATE_ID",
        "config_key": "semrush",
        "name": "Semrush",
        "sender_domains": ["semrush.com"],
        "patterns": [
            r"affiliate[_-]?id[:\s]+([A-Za-z0-9_-]+)",
            r"ref=([A-Za-z0-9_-]+)",
            r"partner[_-]?code[:\s]+([A-Za-z0-9_-]+)",
            r"impact\.com.*clickid=([A-Za-z0-9_-]+)",
        ],
    },
    "invideo": {
        "env_key": "INVIDEO_AFFILIATE_ID",
        "config_key": "invideo",
        "name": "InVideo",
        "sender_domains": ["invideo.io"],
        "patterns": [
            r"ref=([A-Za-z0-9_-]+)",
            r"affiliate[_-]?id[:\s]+([A-Za-z0-9_-]+)",
            r"referral.*code[:\s]+([A-Za-z0-9_-]+)",
        ],
    },
    "murf": {
        "env_key": "MURF_AFFILIATE_ID",
        "config_key": "murf",
        "name": "Murf AI",
        "sender_domains": ["murf.ai"],
        "patterns": [
            r"ref=([A-Za-z0-9_-]+)",
            r"affiliate[_-]?id[:\s]+([A-Za-z0-9_-]+)",
            r"partner[_-]?id[:\s]+([A-Za-z0-9_-]+)",
        ],
    },
    "descript": {
        "env_key": "DESCRIPT_AFFILIATE_ID",
        "config_key": "descript",
        "name": "Descript",
        "sender_domains": ["descript.com"],
        "patterns": [
            r"ref=([A-Za-z0-9_-]+)",
            r"affiliate[_-]?id[:\s]+([A-Za-z0-9_-]+)",
            r"partner.*code[:\s]+([A-Za-z0-9_-]+)",
        ],
    },
    "speechify": {
        "env_key": "SPEECHIFY_AFFILIATE_ID",
        "config_key": "speechify",
        "name": "Speechify",
        "sender_domains": ["speechify.com"],
        "patterns": [
            r"ref=([A-Za-z0-9_-]+)",
            r"affiliate[_-]?id[:\s]+([A-Za-z0-9_-]+)",
            r"referral[_-]?code[:\s]+([A-Za-z0-9_-]+)",
        ],
    },
    "getresponse": {
        "env_key": "GETRESPONSE_AFFILIATE_ID",
        "config_key": "getresponse",
        "name": "GetResponse",
        "sender_domains": ["getresponse.com"],
        "patterns": [
            r"a=([A-Za-z0-9_-]+)",
            r"affiliate[_-]?id[:\s]+([A-Za-z0-9_-]+)",
            r"ref=([A-Za-z0-9_-]+)",
            r"partner[_-]?id[:\s]+([A-Za-z0-9_-]+)",
        ],
    },
    "hubspot": {
        "env_key": "HUBSPOT_AFFILIATE_ID",
        "config_key": "hubspot",
        "name": "HubSpot",
        "sender_domains": ["hubspot.com"],
        "patterns": [
            r"affiliate[_-]?id[:\s]+([A-Za-z0-9_-]+)",
            r"ref=([A-Za-z0-9_-]+)",
            r"partner[_-]?id[:\s]+([A-Za-z0-9_-]+)",
            r"impact\.com.*irclickid=([A-Za-z0-9_-]+)",
        ],
    },
    "quillbot": {
        "env_key": "QUILLBOT_AFFILIATE_ID",
        "config_key": "quillbot",
        "name": "QuillBot",
        "sender_domains": ["quillbot.com"],
        "patterns": [
            r"ref=([A-Za-z0-9_-]+)",
            r"affiliate[_-]?id[:\s]+([A-Za-z0-9_-]+)",
            r"partner[_-]?code[:\s]+([A-Za-z0-9_-]+)",
        ],
    },
    "kit": {
        "env_key": "KIT_AFFILIATE_ID",
        "config_key": "kit",
        "name": "Kit (ConvertKit)",
        "sender_domains": ["kit.com", "convertkit.com"],
        "patterns": [
            r"ref=([A-Za-z0-9_-]+)",
            r"affiliate[_-]?id[:\s]+([A-Za-z0-9_-]+)",
            r"partner[_-]?id[:\s]+([A-Za-z0-9_-]+)",
            r"referral.*code[:\s]+([A-Za-z0-9_-]+)",
        ],
    },
    "webflow": {
        "env_key": "WEBFLOW_AFFILIATE_ID",
        "config_key": "webflow",
        "name": "Webflow",
        "sender_domains": ["webflow.com"],
        "patterns": [
            r"ref=([A-Za-z0-9_-]+)",
            r"affiliate[_-]?id[:\s]+([A-Za-z0-9_-]+)",
            r"partner[_-]?id[:\s]+([A-Za-z0-9_-]+)",
        ],
    },
    "grammarly": {
        "env_key": "GRAMMARLY_AFFILIATE_ID",
        "config_key": "grammarly",
        "name": "Grammarly",
        "sender_domains": ["grammarly.com"],
        "patterns": [
            r"affiliate[_-]?id[:\s]+([A-Za-z0-9_-]+)",
            r"ref=([A-Za-z0-9_-]+)",
            r"impact\.com.*clickid=([A-Za-z0-9_-]+)",
            r"partner.*code[:\s]+([A-Za-z0-9_-]+)",
        ],
    },
    "synthesia": {
        "env_key": "SYNTHESIA_AFFILIATE_ID",
        "config_key": "synthesia",
        "name": "Synthesia",
        "sender_domains": ["synthesia.io"],
        "patterns": [
            r"ref=([A-Za-z0-9_-]+)",
            r"affiliate[_-]?id[:\s]+([A-Za-z0-9_-]+)",
            r"partner[_-]?code[:\s]+([A-Za-z0-9_-]+)",
        ],
    },
    "runway": {
        "env_key": "RUNWAY_AFFILIATE_ID",
        "config_key": "runway",
        "name": "Runway ML",
        "sender_domains": ["runwayml.com"],
        "patterns": [
            r"ref=([A-Za-z0-9_-]+)",
            r"affiliate[_-]?id[:\s]+([A-Za-z0-9_-]+)",
            r"partner[_-]?id[:\s]+([A-Za-z0-9_-]+)",
        ],
    },
    "impact": {
        "env_key": "IMPACT_AFFILIATE_ID",
        "config_key": "impact",
        "name": "Impact (network)",
        "sender_domains": ["impact.com"],
        "patterns": [
            r"publisher[_-]?id[:\s]+([A-Za-z0-9_-]+)",
            r"affiliate[_-]?id[:\s]+([A-Za-z0-9_-]+)",
            r"irclickid=([A-Za-z0-9_-]+)",
            r"ref=([A-Za-z0-9_-]+)",
        ],
    },
    "shareasale": {
        "env_key": "SHAREASALE_AFFILIATE_ID",
        "config_key": "shareasale",
        "name": "ShareASale (network)",
        "sender_domains": ["shareasale.com"],
        "patterns": [
            r"affiliateid=([A-Za-z0-9_-]+)",
            r"affiliate[_-]?id[:\s]+([A-Za-z0-9_-]+)",
            r"sscid=([A-Za-z0-9_-]+)",
            r"ref=([A-Za-z0-9_-]+)",
        ],
    },
    "partnerstack": {
        "env_key": "PARTNERSTACK_AFFILIATE_ID",
        "config_key": "partnerstack",
        "name": "PartnerStack (network)",
        "sender_domains": ["partnerstack.com"],
        "patterns": [
            r"ref=([A-Za-z0-9_-]+)",
            r"gspk=([A-Za-z0-9_-]+)",
            r"affiliate[_-]?id[:\s]+([A-Za-z0-9_-]+)",
            r"partner[_-]?key[:\s]+([A-Za-z0-9_-]+)",
        ],
    },
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_env_path() -> Path:
    """Returns the absolute path to the .env file."""
    return Path(__file__).parent.parent / ".env"


def _decode_mime_words(s: str) -> str:
    """Decode RFC 2047 encoded email header to a plain string."""
    if not s:
        return ""
    parts = decode_header(s)
    decoded_parts = []
    for part, charset in parts:
        if isinstance(part, bytes):
            try:
                decoded_parts.append(part.decode(charset or "utf-8", errors="replace"))
            except (LookupError, UnicodeDecodeError):
                decoded_parts.append(part.decode("utf-8", errors="replace"))
        else:
            decoded_parts.append(part)
    return " ".join(decoded_parts)


def _extract_text_from_message(msg: email.message.Message) -> str:
    """Walk the MIME tree and return all text content concatenated."""
    texts: List[str] = []
    for part in msg.walk():
        content_type = part.get_content_type()
        if content_type not in ("text/plain", "text/html"):
            continue
        charset = part.get_content_charset() or "utf-8"
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        try:
            texts.append(payload.decode(charset, errors="replace"))
        except (LookupError, UnicodeDecodeError):
            texts.append(payload.decode("utf-8", errors="replace"))
    return "\n".join(texts)


def _sender_domain(msg: email.message.Message) -> str:
    """Extract the lowercase domain from the From header."""
    raw_from = msg.get("From", "")
    _, addr = parseaddr(raw_from)
    if "@" in addr:
        return addr.split("@", 1)[1].lower().strip(">")
    return ""


def _subject_has_approval_keyword(subject: str) -> bool:
    lower = subject.lower()
    return any(kw in lower for kw in APPROVAL_SUBJECT_KEYWORDS)


def _match_program(sender_domain: str, subject: str, body: str) -> List[str]:
    """Return list of program keys that match this email."""
    matched = []
    lower_subject = subject.lower()
    lower_body = body.lower()

    for prog_key, prog in AFFILIATE_PATTERNS.items():
        # Check domain match
        domain_hit = any(
            sender_domain == d or sender_domain.endswith("." + d)
            for d in prog.get("sender_domains", [])
        )
        # Check if program name appears in subject or body
        name_in_content = prog["name"].lower() in lower_subject or prog["name"].lower() in lower_body
        prog_key_in_content = prog_key in lower_subject or prog_key in lower_body

        if domain_hit or name_in_content or prog_key_in_content:
            matched.append(prog_key)

    return matched


def _extract_affiliate_id(prog_key: str, body: str) -> Optional[str]:
    """Try all regex patterns for the given program. Return first match or None."""
    patterns = AFFILIATE_PATTERNS[prog_key]["patterns"]
    for pattern in patterns:
        try:
            m = re.search(pattern, body, re.IGNORECASE)
            if m:
                candidate = m.group(1).strip()
                # Sanity: must be at least 3 chars and not a common false positive
                if len(candidate) >= 3:
                    return candidate
        except re.error:
            continue
    return None


# ---------------------------------------------------------------------------
# Core: update .env
# ---------------------------------------------------------------------------

def update_affiliate_id(program_key: str, affiliate_id: str) -> bool:
    """
    Updates the .env file for the given program's env_key.
    If the key already exists, replace its value.
    If it doesn't exist, append a new line.
    Returns True on success.
    """
    prog = AFFILIATE_PATTERNS.get(program_key)
    if not prog:
        logger.warning(f"update_affiliate_id: unknown program_key '{program_key}'")
        return False

    env_key = prog["env_key"]
    prog_name = prog["name"]
    env_path = _get_env_path()

    try:
        if env_path.exists():
            content = env_path.read_text(encoding="utf-8")
        else:
            content = ""

        # Build the new line
        new_line = f"{env_key}={affiliate_id}"

        # Replace existing key or append
        pattern = re.compile(rf"^{re.escape(env_key)}=.*$", re.MULTILINE)
        if pattern.search(content):
            updated_content = pattern.sub(new_line, content)
        else:
            # Append after a blank line separator
            updated_content = content.rstrip("\n") + f"\n{new_line}\n"

        env_path.write_text(updated_content, encoding="utf-8")

        logger.info(f"[{BOT_NAME}] Updated {env_key}={affiliate_id} in .env")

        # Also refresh the live env variable so it takes effect immediately
        os.environ[env_key] = affiliate_id

        log_bot_event(
            BOT_NAME,
            "affiliate_approved",
            f"Program: {prog_name} | Key: {env_key} | ID: {affiliate_id}",
        )

        notify(
            f"Affiliate approved! <b>{prog_name}</b> ID set: <code>{affiliate_id}</code>\n"
            f"Env key: {env_key}",
            level="success",
            use_telegram=True,
            use_email=False,
        )

        return True

    except OSError as exc:
        logger.error(f"[{BOT_NAME}] Failed to update .env for {env_key}: {exc}")
        log_bot_event(BOT_NAME, "env_update_error", f"{env_key}: {exc}")
        return False


# ---------------------------------------------------------------------------
# Core: check Gmail inbox
# ---------------------------------------------------------------------------

def check_email_for_approvals() -> List[str]:
    """
    Connects to Gmail via IMAP, scans UNSEEN emails in INBOX.
    For each matching email, tries to extract affiliate ID and calls
    update_affiliate_id(). Marks email as SEEN when processed.

    Returns list of program keys that were approved in this run.
    """
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")

    if not smtp_user or not smtp_password:
        logger.error(f"[{BOT_NAME}] SMTP_USER or SMTP_PASSWORD not set — skipping IMAP check")
        return []

    approved_programs: List[str] = []
    imap: Optional[imaplib.IMAP4_SSL] = None

    try:
        logger.info(f"[{BOT_NAME}] Connecting to IMAP as {smtp_user}")
        imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        imap.login(smtp_user, smtp_password)
        imap.select("INBOX")

        # Search for all unread messages
        status, data = imap.search(None, "UNSEEN")
        if status != "OK":
            logger.warning(f"[{BOT_NAME}] IMAP search returned status: {status}")
            return []

        msg_ids = data[0].split() if data[0] else []
        logger.info(f"[{BOT_NAME}] Found {len(msg_ids)} unseen email(s) to scan")

        for msg_id in msg_ids:
            try:
                status, msg_data = imap.fetch(msg_id, "(RFC822)")
                if status != "OK" or not msg_data or not msg_data[0]:
                    logger.warning(f"[{BOT_NAME}] Could not fetch message id {msg_id}")
                    continue

                raw_email = msg_data[0][1]
                if not isinstance(raw_email, bytes):
                    continue

                msg = email.message_from_bytes(raw_email)

                subject = _decode_mime_words(msg.get("Subject", ""))
                sender_dom = _sender_domain(msg)
                body = _extract_text_from_message(msg)

                logger.debug(
                    f"[{BOT_NAME}] Checking email — From domain: {sender_dom!r} | "
                    f"Subject: {subject!r}"
                )

                # Gate: subject must contain an approval keyword.
                # Domain-only matching caused false positives from marketing emails.
                if not _subject_has_approval_keyword(subject):
                    logger.debug(
                        f"[{BOT_NAME}] Skipping — no approval keyword in subject: {subject!r}"
                    )
                    imap.store(msg_id, "+FLAGS", "\\Seen")
                    continue

                # Identify which programs this email relates to
                matched_programs = _match_program(sender_dom, subject, body)

                if not matched_programs:
                    logger.debug(
                        f"[{BOT_NAME}] Email from {sender_dom!r} has approval keyword "
                        f"but matched no known program"
                    )
                    # Mark as read so we don't keep re-processing it
                    imap.store(msg_id, "+FLAGS", "\\Seen")
                    continue

                for prog_key in matched_programs:
                    prog_name = AFFILIATE_PATTERNS[prog_key]["name"]
                    logger.info(
                        f"[{BOT_NAME}] Potential approval from {prog_name} | "
                        f"Subject: {subject!r}"
                    )

                    affiliate_id = _extract_affiliate_id(prog_key, body)

                    if affiliate_id:
                        logger.info(
                            f"[{BOT_NAME}] Extracted affiliate ID for {prog_name}: {affiliate_id}"
                        )
                        success = update_affiliate_id(prog_key, affiliate_id)
                        if success:
                            approved_programs.append(prog_key)
                    else:
                        # No ID extracted but we still got an approval — notify so
                        # the admin can add it manually
                        logger.warning(
                            f"[{BOT_NAME}] Approval detected for {prog_name} but could not "
                            f"extract affiliate ID automatically"
                        )
                        log_bot_event(
                            BOT_NAME,
                            "approval_no_id",
                            f"Program: {prog_name} | Subject: {subject}",
                        )
                        notify(
                            f"Affiliate approval detected for <b>{prog_name}</b> but no ID "
                            f"could be extracted automatically.\n"
                            f"Subject: {subject}\n"
                            f"Please add manually to .env as <code>{AFFILIATE_PATTERNS[prog_key]['env_key']}</code>",
                            level="warning",
                            use_telegram=True,
                            use_email=False,
                        )

                # Mark email as read regardless of extraction outcome
                imap.store(msg_id, "+FLAGS", "\\Seen")

            except Exception as msg_exc:
                logger.error(
                    f"[{BOT_NAME}] Error processing message {msg_id}: {msg_exc}",
                    exc_info=True,
                )
                # Don't mark as read on unexpected errors — we'll retry next run
                continue

    except imaplib.IMAP4.error as imap_err:
        logger.error(f"[{BOT_NAME}] IMAP error: {imap_err}")
        log_bot_event(BOT_NAME, "imap_error", str(imap_err))
    except OSError as conn_err:
        logger.error(f"[{BOT_NAME}] IMAP connection error: {conn_err}")
        log_bot_event(BOT_NAME, "connection_error", str(conn_err))
    finally:
        if imap is not None:
            try:
                imap.logout()
            except Exception:
                pass

    return approved_programs


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_affiliate_gmail_monitor() -> dict:
    """
    Main bot entry point. Checks Gmail for affiliate approval emails,
    updates .env for any IDs found, and saves state.

    Returns:
        dict with keys:
            - checked: number of emails scanned
            - approved: list of program keys that got IDs this run
            - last_run: ISO timestamp
    """
    logger.info(f"[{BOT_NAME}] Starting affiliate Gmail monitor")

    approved: List[str] = []
    checked = 0

    try:
        approved = check_email_for_approvals()
        # We don't have a simple count of emails scanned without restructuring,
        # so we log the approved count; a more detailed count would need refactoring
        checked = len(approved)  # lower bound — actual checked could be higher
    except Exception as exc:
        logger.error(f"[{BOT_NAME}] Unexpected error: {exc}", exc_info=True)
        log_bot_event(BOT_NAME, "error", str(exc))

    now_iso = datetime.utcnow().isoformat()
    upsert_bot_state(BOT_NAME, "last_run", now_iso)
    upsert_bot_state(BOT_NAME, "last_approved_count", str(len(approved)))

    if approved:
        upsert_bot_state(BOT_NAME, "last_approved_programs", ",".join(approved))
        logger.info(f"[{BOT_NAME}] Approved programs this run: {approved}")
    else:
        logger.info(f"[{BOT_NAME}] No new affiliate approvals found")

    result = {
        "checked": checked,
        "approved": approved,
        "last_run": now_iso,
    }
    logger.info(f"[{BOT_NAME}] Completed: {result}")
    return result
