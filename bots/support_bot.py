"""
Bot 9: Customer Support / Chat Bot
Handles support automation and FAQ generation.
"""
import logging
from datetime import datetime

from bots.shared.ai_client import ask_claude
from bots.shared.db_helpers import log_bot_event, upsert_bot_state
from database.db import get_conn
from config import config

logger = logging.getLogger(__name__)

BOT_NAME = "support_bot"


def _ensure_contact_submissions_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS contact_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT,
            message TEXT NOT NULL,
            responded INTEGER DEFAULT 0,
            draft_response TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()


def generate_faq_content() -> list:
    """
    Uses Claude to generate 10 FAQ items for the AI tools comparison site.
    Returns list of {question, answer}.
    """
    prompt = """Generate 10 frequently asked questions (FAQs) with detailed answers for AI Tools Empire (aitoolsempire.co), an AI tool review and comparison site.

Cover topics like:
- How to choose the right AI tool
- Pricing and free trials
- Comparisons between popular tools
- Getting started with AI tools
- Privacy and data security
- Affiliate disclosure

For each FAQ:
QUESTION: [the question]
ANSWER: [2-4 sentence detailed answer]
---

Write all 10 FAQs in this format."""

    response = ask_claude(prompt, max_tokens=2500)

    faqs = []
    if not response:
        return faqs

    blocks = response.split("---")
    for block in blocks:
        block = block.strip()
        if not block:
            continue

        faq = {"question": "", "answer": ""}
        for line in block.split("\n"):
            stripped = line.strip()
            if stripped.startswith("QUESTION:"):
                faq["question"] = stripped[9:].strip()
            elif stripped.startswith("ANSWER:"):
                faq["answer"] = stripped[7:].strip()

        if faq["question"] and faq["answer"]:
            faqs.append(faq)

    return faqs[:10]


def draft_support_response(inquiry: str) -> str:
    """
    Drafts a helpful support response in Kenny's voice.
    """
    prompt = f"""Draft a helpful, friendly customer support response for AI Tools Empire.

Customer inquiry:
{inquiry}

Guidelines:
- Respond as Kenny, the founder of AI Tools Empire
- Friendly, knowledgeable, and genuine tone
- Address the specific question/concern directly
- If it's about a tool, mention you can find the full review at aitoolsempire.co
- If it's a technical issue, offer to help troubleshoot
- Keep it concise (3-5 sentences unless detail is needed)
- End with an offer to help further

Write ONLY the email response body (no subject line, no "Hi [name]" opener — just the response content)."""

    system = (
        "You are Kenny, founder of AI Tools Empire. You've personally tested hundreds of AI tools "
        "and love helping people find the right ones for their needs. Your tone is conversational, "
        "knowledgeable, and genuinely helpful — not corporate or robotic."
    )

    response = ask_claude(prompt, system=system, max_tokens=600)
    return response or "Thank you for reaching out! I'll look into this and get back to you shortly. - Kenny"


def check_contact_form_submissions() -> list:
    """
    Queries contact_submissions table for unresponded items.
    Returns list of submission dicts.
    """
    try:
        conn = get_conn()
        _ensure_contact_submissions_table(conn)
        rows = conn.execute(
            "SELECT * FROM contact_submissions WHERE responded=0 ORDER BY created_at ASC LIMIT 20"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"check_contact_form_submissions error: {e}")
        return []


def run_support_bot() -> dict:
    """
    Checks for unresponded contact forms, drafts responses.
    Does NOT auto-send — logs drafts for admin review.
    Returns summary dict.
    """
    logger.info("Support Bot: starting run")

    result = {
        "unresponded_submissions": 0,
        "drafts_created": 0,
    }

    try:
        submissions = check_contact_form_submissions()
        result["unresponded_submissions"] = len(submissions)

        if not submissions:
            logger.info("Support Bot: no unresponded submissions")
            upsert_bot_state(BOT_NAME, "last_run", datetime.utcnow().isoformat())
            return result

        logger.info(f"Support Bot: found {len(submissions)} unresponded submissions")

        for sub in submissions:
            try:
                inquiry = sub.get("message", "")
                if not inquiry:
                    continue

                draft = draft_support_response(inquiry)

                # Store draft response — do NOT auto-send
                conn = get_conn()
                _ensure_contact_submissions_table(conn)
                conn.execute(
                    "UPDATE contact_submissions SET draft_response=? WHERE id=?",
                    (draft, sub["id"])
                )
                conn.commit()
                conn.close()

                result["drafts_created"] += 1
                logger.info(f"Draft created for submission {sub['id']} from {sub.get('email', 'unknown')}")

            except Exception as e:
                logger.error(f"Error drafting response for submission {sub.get('id')}: {e}")

        log_bot_event(
            BOT_NAME,
            "drafts_created",
            f"Created {result['drafts_created']} draft responses from {len(submissions)} submissions"
        )

    except Exception as e:
        logger.error(f"Support Bot error: {e}")
        log_bot_event(BOT_NAME, "error", str(e))

    upsert_bot_state(BOT_NAME, "last_run", datetime.utcnow().isoformat())
    return result
