"""
SMTP email sender using Gmail for all bots.
"""
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from config import config

logger = logging.getLogger(__name__)


def send_email(
    to: str,
    subject: str,
    body_html: str,
    body_text: str = None
) -> bool:
    """
    Send a single email via SMTP. Returns True on success, False on failure.
    """
    if not config.SMTP_USER or not config.SMTP_PASSWORD:
        logger.warning("SMTP credentials not configured — skipping send_email")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{config.FROM_NAME} <{config.SMTP_USER}>"
        msg["To"] = to

        if body_text:
            msg.attach(MIMEText(body_text, "plain"))

        msg.attach(MIMEText(body_html, "html"))

        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(config.SMTP_USER, config.SMTP_PASSWORD)
            server.sendmail(config.SMTP_USER, to, msg.as_string())

        logger.info(f"Email sent to {to}: {subject}")
        return True

    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"SMTP auth error sending to {to}: {e}")
        return False
    except smtplib.SMTPException as e:
        logger.error(f"SMTP error sending to {to}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending email to {to}: {e}")
        return False


def send_bulk_email(recipients: list, subject: str, body_html: str) -> dict:
    """
    Send the same email to a list of recipient email strings.
    Returns {"sent": n, "failed": n}.
    """
    sent = 0
    failed = 0

    if not recipients:
        return {"sent": 0, "failed": 0}

    if not config.SMTP_USER or not config.SMTP_PASSWORD:
        logger.warning("SMTP credentials not configured — skipping send_bulk_email")
        return {"sent": 0, "failed": len(recipients)}

    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(config.SMTP_USER, config.SMTP_PASSWORD)

            for recipient in recipients:
                try:
                    msg = MIMEMultipart("alternative")
                    msg["Subject"] = subject
                    msg["From"] = f"{config.FROM_NAME} <{config.SMTP_USER}>"
                    msg["To"] = recipient
                    msg.attach(MIMEText(body_html, "html"))
                    server.sendmail(config.SMTP_USER, recipient, msg.as_string())
                    sent += 1
                    logger.debug(f"Bulk email sent to {recipient}")
                except Exception as e:
                    logger.error(f"Failed to send bulk email to {recipient}: {e}")
                    failed += 1

    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"SMTP auth error in bulk send: {e}")
        return {"sent": 0, "failed": len(recipients)}
    except Exception as e:
        logger.error(f"Bulk email connection error: {e}")
        return {"sent": sent, "failed": len(recipients) - sent}

    logger.info(f"Bulk email complete — sent: {sent}, failed: {failed}")
    return {"sent": sent, "failed": failed}
