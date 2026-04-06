"""
Welcome sequence runner.
Reads email_0N_*.md files, formats them, and sends via email_sender._send_email().

Sequence schedule (hours after subscribe):
  Email 1:  0h  — Welcome + Kit
  Email 2: 72h  — Writesonic (Week 2)
  Email 3: 120h — Surfer SEO (Week 3)
  Email 4: 168h — ElevenLabs + Pictory (Week 4)
  Email 5: 240h — Full stack + monetize (Week 5)

Called by scheduler.py or directly:
    python -m automation.sequences.runner --email user@example.com --seq 1
"""
import re
import logging
import markdown
from pathlib import Path
from urllib.parse import quote

from config import config

log = logging.getLogger(__name__)
SEQ_DIR = Path(__file__).parent

# Delay in hours for each sequence step (index = seq number - 1)
DELAYS_HOURS = [0, 72, 120, 168, 240]


def _load_email(seq_num: int) -> dict:
    """Parse a sequence markdown file. Returns {subject, preview_text, html_body}."""
    files = sorted(SEQ_DIR.glob(f"email_0{seq_num}_*.md"))
    if not files:
        raise FileNotFoundError(f"No sequence file for seq {seq_num}")
    raw = files[0].read_text()

    # Parse YAML-ish frontmatter between --- delimiters
    fm_match = re.match(r"^---\n(.+?)\n---\n(.+)$", raw, re.DOTALL)
    if not fm_match:
        raise ValueError(f"Bad frontmatter in {files[0]}")

    frontmatter, body = fm_match.group(1), fm_match.group(2)

    def fm_val(key):
        m = re.search(rf'^{key}:\s*"?(.+?)"?\s*$', frontmatter, re.MULTILINE)
        return m.group(1).strip('"') if m else ""

    return {
        "subject": fm_val("subject"),
        "preview_text": fm_val("preview_text"),
        "html_body": markdown.markdown(body, extensions=["tables"]),
        "delay_hours": DELAYS_HOURS[seq_num - 1],
    }


def _wrap_html(inner_html: str, preview_text: str) -> str:
    """Wrap body content in a clean email shell."""
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f1f5f9;margin:0;padding:20px}}
  .wrap{{max-width:600px;margin:0 auto;background:white;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.07)}}
  .hdr{{background:linear-gradient(135deg,#6366f1,#8b5cf6);padding:28px 32px}}
  .hdr a{{color:white;font-weight:700;font-size:20px;text-decoration:none}}
  .body{{padding:32px;color:#334155;line-height:1.7;font-size:15px}}
  .body h2,.body h3{{color:#1e293b}}
  .body a{{color:#6366f1;font-weight:600}}
  .body table{{width:100%;border-collapse:collapse;margin:16px 0}}
  .body th{{background:#6366f1;color:white;padding:10px;text-align:left;font-size:13px}}
  .body td{{padding:9px 10px;border-bottom:1px solid #e2e8f0;font-size:14px}}
  .body tr:nth-child(even) td{{background:#f8fafc}}
  .ftr{{background:#f8fafc;padding:16px 32px;text-align:center;border-top:1px solid #e2e8f0}}
  .ftr p{{color:#94a3b8;font-size:12px;margin:4px 0}}
  .ftr a{{color:#6366f1;text-decoration:none}}
</style>
</head>
<body>
<!-- preview: {preview_text} -->
<div class="wrap">
  <div class="hdr"><a href="{config.SITE_URL}">{config.SITE_NAME}</a></div>
  <div class="body">{inner_html}</div>
  <div class="ftr">
    <p>You subscribed at <a href="{config.SITE_URL}">{config.SITE_URL}</a></p>
  </div>
</div>
</body>
</html>"""


def send_sequence_email(to_email: str, to_name: str, seq_num: int) -> bool:
    """Send one sequence email (1-5) to a single subscriber."""
    from automation.email_sender import _send_email
    try:
        data = _load_email(seq_num)
        body_with_vars = data["html_body"].replace(
            "{name}", to_name or "there"
        ).replace(
            "{email_encoded}", quote(to_email)
        ).replace(
            "{site_url}", config.SITE_URL
        ).replace(
            "{site_name}", config.SITE_NAME
        )
        html = _wrap_html(body_with_vars, data["preview_text"])
        return _send_email(to=[to_email], subject=data["subject"], html=html)
    except Exception as e:
        log.error(f"Sequence email {seq_num} failed for {to_email}: {e}")
        return False


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", default="there")
    parser.add_argument("--seq", type=int, required=True, choices=range(1, 6))
    args = parser.parse_args()
    ok = send_sequence_email(args.email, args.name, args.seq)
    print("Sent" if ok else "Failed")
