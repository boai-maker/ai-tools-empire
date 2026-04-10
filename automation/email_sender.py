"""
Automated email system — dual-backend: Resend (preferred) + Gmail SMTP (fallback).
Activates the moment either RESEND_API_KEY or SMTP_USER+SMTP_PASSWORD is set in .env.

- Welcome sequence for new subscribers
- Weekly newsletter (sent every Monday)
- Click tracking via affiliate links
"""
import logging
import smtplib
import ssl
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import config
from database.db import (
    get_subscribers, get_articles, mark_welcome_sent,
    get_subscriber_count
)
from affiliate.links import AFFILIATE_PROGRAMS

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Backend detection
# ---------------------------------------------------------------------------

def _has_resend() -> bool:
    return bool(config.RESEND_API_KEY)

def _has_smtp() -> bool:
    return bool(config.SMTP_USER and config.SMTP_PASSWORD)

# ---------------------------------------------------------------------------
# Core send helper — tries Resend, falls back to SMTP
# ---------------------------------------------------------------------------

def _send_email(to: list[str], subject: str, html: str) -> bool:
    """Send an email via Resend or Gmail SMTP. Returns True on success."""
    if _has_resend():
        return _send_via_resend(to, subject, html)
    elif _has_smtp():
        return _send_via_smtp(to, subject, html)
    else:
        log.warning(
            "Email not sent — no backend configured. "
            "Add RESEND_API_KEY or SMTP_USER+SMTP_PASSWORD to .env"
        )
        return False


def _send_via_resend(to: list[str], subject: str, html: str) -> bool:
    try:
        import resend as resend_lib
        resend_lib.api_key = config.RESEND_API_KEY
        resend_lib.Emails.send({
            "from": f"{config.FROM_NAME} <{config.FROM_EMAIL}>",
            "to": to,
            "subject": subject,
            "html": html,
        })
        log.info(f"Resend: sent to {to}")
        return True
    except Exception as e:
        log.error(f"Resend failed: {e}")
        if _has_smtp():
            log.info("Falling back to SMTP...")
            return _send_via_smtp(to, subject, html)
        return False


def _send_via_smtp(to: list[str], subject: str, html: str) -> bool:
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{config.FROM_NAME} <{config.SMTP_USER}>"
        msg["To"] = ", ".join(to)
        msg.attach(MIMEText(html, "html"))

        ctx = ssl.create_default_context()
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
            server.ehlo()
            server.starttls(context=ctx)
            server.login(config.SMTP_USER, config.SMTP_PASSWORD)
            server.sendmail(config.SMTP_USER, to, msg.as_string())

        log.info(f"SMTP: sent to {to}")
        return True
    except Exception as e:
        log.error(f"SMTP failed: {e}")
        return False

# ---------------------------------------------------------------------------
# Email templates
# ---------------------------------------------------------------------------

WELCOME_EMAIL_HTML = """
<!DOCTYPE html>
<html>
<head>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f8fafc; margin: 0; padding: 20px; }}
  .container {{ max-width: 600px; margin: 0 auto; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.07); }}
  .header {{ background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%); padding: 40px 32px; text-align: center; }}
  .header h1 {{ color: white; margin: 0; font-size: 28px; font-weight: 700; }}
  .header p {{ color: rgba(255,255,255,0.85); margin: 8px 0 0; font-size: 16px; }}
  .body {{ padding: 32px; }}
  .body h2 {{ color: #1e293b; font-size: 22px; margin-top: 0; }}
  .body p {{ color: #475569; line-height: 1.6; }}
  .tool-card {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 12px 0; }}
  .tool-card h3 {{ margin: 0 0 4px; color: #1e293b; font-size: 16px; }}
  .tool-card p {{ margin: 0 0 10px; color: #64748b; font-size: 14px; }}
  .tool-card a {{ background: #6366f1; color: white; padding: 8px 16px; border-radius: 6px; text-decoration: none; font-size: 14px; font-weight: 600; }}
  .cta-box {{ background: linear-gradient(135deg, #f0f9ff, #e0f2fe); border: 1px solid #bae6fd; border-radius: 10px; padding: 24px; text-align: center; margin: 24px 0; }}
  .cta-box h3 {{ color: #0369a1; margin: 0 0 8px; }}
  .cta-box p {{ color: #0c4a6e; margin: 0 0 16px; font-size: 14px; }}
  .footer {{ background: #f8fafc; padding: 20px 32px; text-align: center; border-top: 1px solid #e2e8f0; }}
  .footer p {{ color: #94a3b8; font-size: 12px; margin: 4px 0; }}
  .footer a {{ color: #6366f1; text-decoration: none; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>Welcome to {site_name}!</h1>
    <p>Your weekly guide to the best AI tools</p>
  </div>
  <div class="body">
    <h2>Hey {name}, you're in! Here's your free kit.</h2>
    <p>Thanks for subscribing to <strong>{site_name}</strong>. Your <strong>Free AI Tools Starter Kit</strong> is ready — it covers 7 tools that pay for themselves and how to use each one in the first 7 weeks.</p>

    <div class="cta-box">
      <h3>🎁 Get Your Free Starter Kit</h3>
      <p>7 tools · step-by-step guide · completely free</p>
      <a href="{site_url}/free-ai-kit" style="background:#6366f1;color:white;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:700;font-size:15px;">View Your Free Kit →</a>
    </div>

    <p style="margin-top:24px;">Every Monday I'll also send:</p>
    <ul style="color:#475569;line-height:1.8">
      <li>In-depth reviews of AI tools across writing, SEO, video, and voice</li>
      <li>Head-to-head comparisons — no sponsored rankings</li>
      <li>Pricing change alerts before they hit</li>
    </ul>

    <p style="margin-top:24px;"><strong>3 tools from your kit worth starting today:</strong></p>

    <div class="tool-card">
      <h3>Grammarly — AI Writing Assistant</h3>
      <p>Fixes grammar, rewrites unclear sentences, adjusts tone. Free tier forever — install the browser extension.</p>
      <a href="{grammarly_url}" target="_blank">Get Grammarly Free</a>
    </div>

    <div class="tool-card">
      <h3>Surfer SEO — Rank Faster with AI</h3>
      <p>Tells you exactly what to write to outrank competitors. 7-day free trial available.</p>
      <a href="{surfer_url}" target="_blank">Try Surfer SEO</a>
    </div>

    <div class="tool-card">
      <h3>ElevenLabs — AI Voice Generation</h3>
      <p>Turn any text into realistic audio. 10,000 characters free every month — no credit card.</p>
      <a href="{elevenlabs_url}" target="_blank">Try ElevenLabs Free</a>
    </div>

    <p>See you Monday!</p>
    <p style="color:#64748b;font-size:14px">— The {site_name} Team</p>
  </div>
  <div class="footer">
    <p>You subscribed at <a href="{site_url}">{site_url}</a></p>
    <p><a href="{site_url}/unsubscribe?email={email_encoded}">Unsubscribe</a> · <a href="{site_url}/privacy">Privacy Policy</a></p>
  </div>
</div>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def send_welcome_email(subscriber_email: str, subscriber_name: str = "there") -> bool:
    """Send welcome email to a new subscriber."""
    from urllib.parse import quote
    html = WELCOME_EMAIL_HTML.format(
        site_name=config.SITE_NAME,
        site_url=config.SITE_URL,
        name=subscriber_name if subscriber_name else "there",
        grammarly_url=AFFILIATE_PROGRAMS["grammarly"]["signup_url"],
        surfer_url=AFFILIATE_PROGRAMS["surfer"]["signup_url"],
        elevenlabs_url=AFFILIATE_PROGRAMS["elevenlabs"]["signup_url"],
        email_encoded=quote(subscriber_email),
    )

    ok = _send_email(
        to=[subscriber_email],
        subject=f"Welcome to {config.SITE_NAME} — Your AI tools guide starts here",
        html=html,
    )
    if ok:
        mark_welcome_sent(subscriber_email)
        log.info(f"Welcome email sent to {subscriber_email}")
    else:
        log.error(f"Failed to send welcome email to {subscriber_email}")
    return ok


def send_welcome_to_pending() -> int:
    """Send welcome emails to any subscribers who haven't received one yet."""
    from database.db import get_conn
    conn = get_conn()
    pending = conn.execute("""
        SELECT email, name FROM subscribers WHERE welcome_sent=0 AND status='active'
    """).fetchall()
    conn.close()

    sent = 0
    for sub in pending:
        if send_welcome_email(sub["email"], sub["name"]):
            sent += 1
    log.info(f"Pending welcome emails sent: {sent}")
    return sent


def generate_newsletter_html(articles: list, week_num: int) -> str:
    """Build the weekly newsletter HTML from recent articles."""
    article_blocks = ""
    for article in articles[:5]:
        tool_key = article.get("featured_tool", "")
        cta = ""
        if tool_key and tool_key in AFFILIATE_PROGRAMS:
            t = AFFILIATE_PROGRAMS[tool_key]
            cta = (
                f'<p><a href="{t["signup_url"]}" '
                f'style="background:#6366f1;color:white;padding:8px 16px;border-radius:6px;'
                f'text-decoration:none;font-size:13px;font-weight:600">Try {t["name"]} Free</a></p>'
            )

        article_blocks += f"""
        <div style="border-bottom:1px solid #e2e8f0;padding:20px 0;">
          <h3 style="margin:0 0 8px;font-size:18px;">
            <a href="{config.SITE_URL}/articles/{article['slug']}" style="color:#1e293b;text-decoration:none;">
              {article['title']}
            </a>
          </h3>
          <p style="color:#64748b;margin:0 0 12px;line-height:1.6;font-size:14px;">{article.get('meta_description', '')}</p>
          <a href="{config.SITE_URL}/articles/{article['slug']}" style="color:#6366f1;font-size:13px;font-weight:600;text-decoration:none;">Read Full Article</a>
          {cta}
        </div>
        """

    featured = ["semrush", "jasper", "elevenlabs"]
    deals_blocks = ""
    for fk in featured:
        if fk in AFFILIATE_PROGRAMS:
            t = AFFILIATE_PROGRAMS[fk]
            deals_blocks += f"""
            <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:14px;margin:10px 0;">
              <strong style="color:#1e293b;font-size:15px;">{t['name']}</strong><br>
              <span style="color:#64748b;font-size:13px;">{t['description'][:80]}...</span><br>
              <a href="{t['signup_url']}" style="display:inline-block;margin-top:8px;background:#10b981;color:white;padding:7px 14px;border-radius:6px;text-decoration:none;font-size:13px;font-weight:600;">Try Free</a>
            </div>
            """

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
</head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f1f5f9;margin:0;padding:20px;">
<div style="max-width:600px;margin:0 auto;">

  <div style="background:linear-gradient(135deg,#6366f1,#8b5cf6);border-radius:12px 12px 0 0;padding:32px;text-align:center;">
    <h1 style="color:white;margin:0;font-size:24px;">{config.SITE_NAME}</h1>
    <p style="color:rgba(255,255,255,0.85);margin:8px 0 0;font-size:14px;">Week {week_num} &middot; {datetime.now().strftime('%B %d, %Y')}</p>
  </div>

  <div style="background:white;padding:32px;border-radius:0 0 12px 12px;">

    <h2 style="color:#1e293b;font-size:20px;margin-top:0;">This Week's Top AI Tool Guides</h2>
    {article_blocks}

    <h2 style="color:#1e293b;font-size:20px;margin-top:28px;">Tools Worth Trying This Week</h2>
    <p style="color:#64748b;font-size:14px;margin-top:-8px;">Editors' picks — all have free trials:</p>
    {deals_blocks}

    <div style="background:#fefce8;border:1px solid #fde047;border-radius:8px;padding:16px;margin:24px 0;">
      <p style="color:#713f12;margin:0;font-size:14px;">
        <strong>Tip of the week:</strong> If you're evaluating AI writing tools, start with the free trials before committing.
        Most offer 7–14 days — enough time to judge output quality on your actual use case.
        <a href="{config.SITE_URL}/best-ai-writing-tools" style="color:#6366f1;">See our writing tools comparison</a>
      </p>
    </div>

    <p style="color:#94a3b8;font-size:13px;margin-top:24px;">
      — The {config.SITE_NAME} Team<br>
      <a href="{config.SITE_URL}" style="color:#6366f1;">{config.SITE_URL}</a>
    </p>
  </div>

  <div style="text-align:center;padding:16px;">
    <p style="color:#94a3b8;font-size:12px;margin:4px 0;">
      You're receiving this because you subscribed at {config.SITE_URL}<br>
      <a href="{config.SITE_URL}/unsubscribe" style="color:#6366f1;">Unsubscribe</a>
    </p>
  </div>
</div>
</body>
</html>"""


def send_weekly_newsletter() -> int:
    """Send weekly newsletter to all active subscribers. Called every Monday by scheduler."""
    articles = get_articles(limit=5)
    if not articles:
        log.warning("No articles to feature in newsletter")
        return 0

    week_num = datetime.now().isocalendar()[1]
    html = generate_newsletter_html(articles, week_num)
    subscribers = get_subscribers(status='active')

    if not subscribers:
        log.info("No active subscribers yet")
        return 0

    emails = [s["email"] for s in subscribers]
    subject = f"[Week {week_num}] {articles[0]['title']} + more AI tool news"

    sent = 0
    # Batch 50 at a time to respect rate limits
    for i in range(0, len(emails), 50):
        batch = emails[i:i + 50]
        if _send_email(to=batch, subject=subject, html=html):
            sent += len(batch)
            log.info(f"Newsletter batch sent: {len(batch)} emails")
        else:
            log.error(f"Newsletter batch failed for {batch}")

    log.info(f"Newsletter sent to {sent}/{len(emails)} subscribers")
    return sent
