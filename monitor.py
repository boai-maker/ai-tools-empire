#!/usr/bin/env python3
"""
AI Tools Empire - Daily Monitoring Bot
Queries the DB, checks affiliate status, and sends a formatted daily report via Resend.
"""

import sqlite3
import sys
import os
from datetime import datetime, date
from pathlib import Path

# Add project root to path so config and affiliate imports work
sys.path.insert(0, str(Path(__file__).parent))

from config import config

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

DB_PATH = Path(__file__).parent / "data.db"


def get_db_stats() -> dict:
    """Pull all site statistics from the SQLite database."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    stats = {}

    # Total articles published
    cur.execute("SELECT COUNT(*) as total FROM articles WHERE status = 'published'")
    stats["total_published"] = cur.fetchone()["total"]

    cur.execute("SELECT COUNT(*) as total FROM articles")
    stats["total_articles"] = cur.fetchone()["total"]

    # Articles by category
    cur.execute(
        "SELECT category, COUNT(*) as cnt FROM articles GROUP BY category ORDER BY cnt DESC"
    )
    stats["by_category"] = [dict(row) for row in cur.fetchall()]

    # Articles by featured_tool
    cur.execute(
        "SELECT featured_tool, COUNT(*) as cnt FROM articles "
        "WHERE featured_tool IS NOT NULL AND featured_tool != '' "
        "GROUP BY featured_tool ORDER BY cnt DESC"
    )
    stats["by_featured_tool"] = [dict(row) for row in cur.fetchall()]

    # Articles missing featured_tool
    cur.execute(
        "SELECT COUNT(*) as cnt FROM articles "
        "WHERE featured_tool IS NULL OR featured_tool = ''"
    )
    stats["missing_featured_tool"] = cur.fetchone()["cnt"]

    # Most recently added articles (last 5)
    cur.execute(
        "SELECT title, category, featured_tool, created_at, views, affiliate_clicks "
        "FROM articles ORDER BY created_at DESC LIMIT 5"
    )
    stats["recent_articles"] = [dict(row) for row in cur.fetchall()]

    # Total views and affiliate clicks
    cur.execute(
        "SELECT COALESCE(SUM(views), 0) as total_views, "
        "COALESCE(SUM(affiliate_clicks), 0) as total_clicks FROM articles"
    )
    row = cur.fetchone()
    stats["total_views"] = row["total_views"]
    stats["total_clicks"] = row["total_clicks"]

    # Subscriber count
    try:
        cur.execute("SELECT COUNT(*) as cnt FROM subscribers")
        stats["subscribers"] = cur.fetchone()["cnt"]
    except Exception:
        stats["subscribers"] = 0

    # Content queue
    try:
        cur.execute("SELECT COUNT(*) as cnt FROM content_queue")
        stats["queued_content"] = cur.fetchone()["cnt"]
    except Exception:
        stats["queued_content"] = 0

    conn.close()
    return stats


# ---------------------------------------------------------------------------
# Affiliate helpers
# ---------------------------------------------------------------------------

PLACEHOLDER_PATTERNS = ("YOUR", "")


def is_placeholder(affiliate_id: str) -> bool:
    """Return True if the affiliate ID is still a placeholder or empty."""
    if not affiliate_id:
        return True
    upper = affiliate_id.upper()
    return upper.startswith("YOUR")


def get_affiliate_status() -> list:
    """
    Compare config AFFILIATE_IDS against affiliate/links.py programs
    and return a status list sorted by revenue potential.
    """
    try:
        from affiliate.links import AFFILIATE_PROGRAMS
    except ImportError:
        AFFILIATE_PROGRAMS = {}

    affiliate_ids = config.AFFILIATE_IDS
    rows = []

    for key, program in AFFILIATE_PROGRAMS.items():
        aff_id = affiliate_ids.get(key, "")
        placeholder = is_placeholder(aff_id)
        monthly_est = program.get("monthly_est_commission", 0)
        commission = program.get("commission", "—")

        if placeholder:
            status = "missing"
        else:
            status = "active"

        rows.append({
            "key": key,
            "name": program.get("name", key),
            "category": program.get("category", "—"),
            "commission": commission,
            "monthly_est": monthly_est,
            "status": status,
            "affiliate_id": aff_id if not placeholder else "",
        })

    # Sort: active first, then by revenue potential descending
    rows.sort(key=lambda r: (0 if r["status"] == "active" else 1, -r["monthly_est"]))
    return rows


# ---------------------------------------------------------------------------
# Revenue estimate
# ---------------------------------------------------------------------------

def get_revenue_estimates(affiliate_rows: list) -> dict:
    """Calculate conservative monthly revenue estimates based on active programs."""
    active_monthly = sum(r["monthly_est"] for r in affiliate_rows if r["status"] == "active")
    potential_monthly = sum(r["monthly_est"] for r in affiliate_rows)
    missing_monthly = potential_monthly - active_monthly

    return {
        "active_monthly": active_monthly,
        "potential_monthly": potential_monthly,
        "missing_monthly": missing_monthly,
        "active_weekly": round(active_monthly / 4.33, 2),
        "active_daily": round(active_monthly / 30, 2),
    }


# ---------------------------------------------------------------------------
# TO-DO list generator
# ---------------------------------------------------------------------------

def generate_todo_list(stats: dict, affiliate_rows: list) -> list:
    """Generate a prioritized to-do list based on current state."""
    todos = []

    # HIGH: Missing affiliate IDs
    missing = [r for r in affiliate_rows if r["status"] == "missing"]
    high_revenue_missing = sorted(missing, key=lambda r: -r["monthly_est"])
    for r in high_revenue_missing[:5]:
        todos.append({
            "priority": "HIGH",
            "task": f"Register & activate {r['name']} affiliate program",
            "detail": f"Est. +${r['monthly_est']}/mo | Commission: {r['commission']}",
            "category": "affiliate",
        })

    # HIGH: PartnerStack / Impact programs to accept contracts
    partnerstack_tools = ["semrush", "surfer", "getresponse", "hubspot"]
    impact_tools = ["jasper", "copyai"]
    pending_contracts = [
        r["name"] for r in missing
        if r["key"] in partnerstack_tools + impact_tools
    ]
    if pending_contracts:
        todos.append({
            "priority": "HIGH",
            "task": "Accept pending PartnerStack/Impact contracts",
            "detail": f"Check dashboards for: {', '.join(pending_contracts)}",
            "category": "platform",
        })

    # MEDIUM: Articles missing featured_tool
    if stats["missing_featured_tool"] > 0:
        todos.append({
            "priority": "MEDIUM",
            "task": f"Assign featured_tool to {stats['missing_featured_tool']} articles",
            "detail": "Run inject_affiliate_ctas.py or update via admin panel",
            "category": "content",
        })

    # MEDIUM: Category gaps — check which affiliate programs have no articles
    covered_tools = {r["featured_tool"] for r in stats.get("recent_articles", [])}
    tool_counts = {r["featured_tool"]: r["cnt"] for r in stats.get("by_featured_tool", [])}
    active_tools = [r["key"] for r in affiliate_rows if r["status"] == "active"]
    under_covered = [t for t in active_tools if tool_counts.get(t, 0) < 2]
    if under_covered:
        todos.append({
            "priority": "MEDIUM",
            "task": f"Write more articles for under-covered tools: {', '.join(under_covered[:4])}",
            "detail": "Aim for at least 3-5 articles per active affiliate program",
            "category": "content",
        })

    # MEDIUM: Suggested next articles based on high-commission gaps
    article_suggestions = [
        ("Jasper AI vs ChatGPT 2026: Which AI Writer Is Better?", "writing", "jasper"),
        ("Best AI Tools for Freelancers in 2026 (Tried & Tested)", "productivity", None),
        ("Speechify Review 2026: Is the $139/Year Plan Worth It?", "audio", "speechify"),
        ("Semrush vs Ahrefs 2026: The Definitive SEO Tool Comparison", "seo", "semrush"),
        ("ElevenLabs vs Murf AI: Best AI Voice Tool for YouTubers?", "audio", "elevenlabs"),
        ("HubSpot CRM Review 2026: Is the Free Plan Actually Free?", "productivity", "hubspot"),
        ("Webflow vs WordPress 2026: Which Is Better for Your Site?", "productivity", "webflow"),
        ("Kit (ConvertKit) Review 2026: Best Email Platform for Creators?", "productivity", "kit"),
    ]
    existing_slugs_raw = [r.get("title", "").lower() for r in stats.get("recent_articles", [])]
    for title, cat, tool in article_suggestions[:4]:
        todos.append({
            "priority": "MEDIUM",
            "task": f"Write: {title}",
            "detail": f"Category: {cat}" + (f" | Tool: {tool}" if tool else ""),
            "category": "content",
        })

    # LOW: Newsletter setup
    if stats.get("subscribers", 0) == 0:
        todos.append({
            "priority": "LOW",
            "task": "Set up opt-in form and start capturing email subscribers",
            "detail": "Add newsletter signup to homepage and article pages",
            "category": "growth",
        })

    # LOW: SEO & site tasks
    todos.append({
        "priority": "LOW",
        "task": "Submit sitemap to Google Search Console",
        "detail": f"URL: {config.SITE_URL}/sitemap.xml",
        "category": "seo",
    })
    todos.append({
        "priority": "LOW",
        "task": "Set up Google Analytics 4 and verify Search Console",
        "detail": "Add GOOGLE_SITE_VERIFICATION to .env once verified",
        "category": "seo",
    })

    return todos


# ---------------------------------------------------------------------------
# HTML email builder
# ---------------------------------------------------------------------------

def build_html_email(stats: dict, affiliate_rows: list, revenue: dict, todos: list, report_date: str) -> str:
    """Build a beautiful HTML email report."""

    # --- Affiliate table rows ---
    aff_table_rows = ""
    for r in affiliate_rows:
        if r["status"] == "active":
            badge = '<span style="color:#16a34a;font-weight:700;">✅ Active</span>'
        else:
            badge = '<span style="color:#dc2626;font-weight:700;">❌ Missing</span>'

        aff_table_rows += f"""
        <tr style="border-bottom:1px solid #e5e7eb;">
            <td style="padding:10px 12px;font-weight:600;">{r['name']}</td>
            <td style="padding:10px 12px;text-transform:capitalize;">{r['category']}</td>
            <td style="padding:10px 12px;">{r['commission']}</td>
            <td style="padding:10px 12px;text-align:right;color:#6b7280;">~${r['monthly_est']}/mo</td>
            <td style="padding:10px 12px;text-align:center;">{badge}</td>
        </tr>"""

    # --- Category breakdown rows ---
    cat_rows = ""
    for c in stats["by_category"]:
        cat_rows += f"""
        <tr style="border-bottom:1px solid #f3f4f6;">
            <td style="padding:8px 12px;text-transform:capitalize;">{c.get('category') or 'Uncategorized'}</td>
            <td style="padding:8px 12px;text-align:right;font-weight:600;">{c['cnt']}</td>
        </tr>"""

    # --- Recent articles rows ---
    recent_rows = ""
    for a in stats["recent_articles"]:
        tool_str = a.get("featured_tool") or '<em style="color:#9ca3af;">—</em>'
        created = (a.get("created_at") or "")[:10]
        recent_rows += f"""
        <tr style="border-bottom:1px solid #f3f4f6;">
            <td style="padding:8px 12px;font-size:13px;">{a['title'][:70]}{'…' if len(a['title']) > 70 else ''}</td>
            <td style="padding:8px 12px;text-transform:capitalize;">{a.get('category') or '—'}</td>
            <td style="padding:8px 12px;">{tool_str}</td>
            <td style="padding:8px 12px;color:#6b7280;font-size:12px;">{created}</td>
        </tr>"""

    # --- To-do list rows ---
    priority_colors = {
        "HIGH": ("#dc2626", "#fef2f2"),
        "MEDIUM": ("#d97706", "#fffbeb"),
        "LOW": ("#2563eb", "#eff6ff"),
    }
    todo_html = ""
    for t in todos:
        color, bg = priority_colors.get(t["priority"], ("#6b7280", "#f9fafb"))
        todo_html += f"""
        <div style="background:{bg};border-left:4px solid {color};border-radius:6px;padding:12px 16px;margin-bottom:10px;">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:8px;">
                <span style="font-weight:700;font-size:14px;">{t['task']}</span>
                <span style="background:{color};color:#fff;font-size:11px;font-weight:700;padding:2px 8px;border-radius:999px;white-space:nowrap;">{t['priority']}</span>
            </div>
            <div style="color:#4b5563;font-size:13px;margin-top:4px;">{t['detail']}</div>
        </div>"""

    # --- Revenue summary ---
    active_count = sum(1 for r in affiliate_rows if r["status"] == "active")
    missing_count = sum(1 for r in affiliate_rows if r["status"] == "missing")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width,initial-scale=1.0" />
<title>AI Tools Empire Daily Report - {report_date}</title>
</head>
<body style="margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f1f5f9;">

<div style="max-width:720px;margin:32px auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">

  <!-- Header -->
  <div style="background:linear-gradient(135deg,#0f172a 0%,#1e3a5f 100%);padding:32px 40px;text-align:center;">
    <div style="font-size:36px;margin-bottom:8px;">🤖</div>
    <h1 style="color:#fff;margin:0;font-size:24px;font-weight:800;letter-spacing:-0.5px;">AI Tools Empire</h1>
    <p style="color:#94a3b8;margin:6px 0 0;font-size:14px;">Daily Operations Report &bull; {report_date}</p>
  </div>

  <!-- Revenue Banner -->
  <div style="background:linear-gradient(90deg,#14532d,#166534);padding:20px 40px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:16px;">
    <div style="text-align:center;flex:1;">
      <div style="color:#bbf7d0;font-size:12px;text-transform:uppercase;letter-spacing:1px;font-weight:600;">Active Monthly Est.</div>
      <div style="color:#fff;font-size:28px;font-weight:800;">${revenue['active_monthly']:,}</div>
    </div>
    <div style="text-align:center;flex:1;">
      <div style="color:#bbf7d0;font-size:12px;text-transform:uppercase;letter-spacing:1px;font-weight:600;">Full Potential</div>
      <div style="color:#4ade80;font-size:28px;font-weight:800;">${revenue['potential_monthly']:,}</div>
    </div>
    <div style="text-align:center;flex:1;">
      <div style="color:#bbf7d0;font-size:12px;text-transform:uppercase;letter-spacing:1px;font-weight:600;">Unlocked Daily</div>
      <div style="color:#fff;font-size:28px;font-weight:800;">${revenue['active_daily']}</div>
    </div>
  </div>

  <div style="padding:32px 40px;">

    <!-- Site Stats -->
    <h2 style="margin:0 0 16px;font-size:18px;font-weight:700;color:#0f172a;border-bottom:2px solid #e2e8f0;padding-bottom:8px;">📊 Site Statistics</h2>
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:28px;">
      <div style="background:#f8fafc;border-radius:8px;padding:16px;text-align:center;">
        <div style="font-size:28px;font-weight:800;color:#0f172a;">{stats['total_articles']}</div>
        <div style="color:#64748b;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;margin-top:4px;">Total Articles</div>
      </div>
      <div style="background:#f8fafc;border-radius:8px;padding:16px;text-align:center;">
        <div style="font-size:28px;font-weight:800;color:#0f172a;">{stats['subscribers']}</div>
        <div style="color:#64748b;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;margin-top:4px;">Subscribers</div>
      </div>
      <div style="background:#f8fafc;border-radius:8px;padding:16px;text-align:center;">
        <div style="font-size:28px;font-weight:800;color:#{'dc2626' if stats['missing_featured_tool'] > 0 else '16a34a'};">{stats['missing_featured_tool']}</div>
        <div style="color:#64748b;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;margin-top:4px;">Missing Tool Tag</div>
      </div>
    </div>

    <!-- Articles by Category -->
    <h2 style="margin:0 0 12px;font-size:18px;font-weight:700;color:#0f172a;border-bottom:2px solid #e2e8f0;padding-bottom:8px;">📁 Articles by Category</h2>
    <table style="width:100%;border-collapse:collapse;margin-bottom:28px;font-size:14px;">
      <thead>
        <tr style="background:#f8fafc;">
          <th style="padding:10px 12px;text-align:left;font-weight:600;color:#374151;">Category</th>
          <th style="padding:10px 12px;text-align:right;font-weight:600;color:#374151;">Articles</th>
        </tr>
      </thead>
      <tbody>{cat_rows}</tbody>
    </table>

    <!-- Recent Articles -->
    <h2 style="margin:0 0 12px;font-size:18px;font-weight:700;color:#0f172a;border-bottom:2px solid #e2e8f0;padding-bottom:8px;">🕐 Recently Added Articles</h2>
    <table style="width:100%;border-collapse:collapse;margin-bottom:28px;font-size:13px;">
      <thead>
        <tr style="background:#f8fafc;">
          <th style="padding:10px 12px;text-align:left;font-weight:600;color:#374151;">Title</th>
          <th style="padding:10px 12px;text-align:left;font-weight:600;color:#374151;">Category</th>
          <th style="padding:10px 12px;text-align:left;font-weight:600;color:#374151;">Tool</th>
          <th style="padding:10px 12px;text-align:left;font-weight:600;color:#374151;">Date</th>
        </tr>
      </thead>
      <tbody>{recent_rows}</tbody>
    </table>

    <!-- Affiliate Status -->
    <h2 style="margin:0 0 12px;font-size:18px;font-weight:700;color:#0f172a;border-bottom:2px solid #e2e8f0;padding-bottom:8px;">🔗 Affiliate Program Status ({active_count} active / {missing_count} missing)</h2>
    <table style="width:100%;border-collapse:collapse;margin-bottom:28px;font-size:13px;">
      <thead>
        <tr style="background:#f8fafc;">
          <th style="padding:10px 12px;text-align:left;font-weight:600;color:#374151;">Program</th>
          <th style="padding:10px 12px;text-align:left;font-weight:600;color:#374151;">Category</th>
          <th style="padding:10px 12px;text-align:left;font-weight:600;color:#374151;">Commission</th>
          <th style="padding:10px 12px;text-align:right;font-weight:600;color:#374151;">Monthly Est.</th>
          <th style="padding:10px 12px;text-align:center;font-weight:600;color:#374151;">Status</th>
        </tr>
      </thead>
      <tbody>{aff_table_rows}</tbody>
    </table>

    <!-- Revenue gap callout -->
    <div style="background:#fef2f2;border-left:4px solid #dc2626;border-radius:6px;padding:14px 18px;margin-bottom:28px;">
      <strong style="color:#dc2626;">💸 Revenue Gap:</strong>
      <span style="color:#7f1d1d;margin-left:6px;">
        Activating all missing affiliate programs could add <strong>${revenue['missing_monthly']:,}/month</strong> in additional revenue.
      </span>
    </div>

    <!-- Prioritized To-Do List -->
    <h2 style="margin:0 0 16px;font-size:18px;font-weight:700;color:#0f172a;border-bottom:2px solid #e2e8f0;padding-bottom:8px;">✅ Prioritized To-Do List</h2>
    {todo_html}

  </div>

  <!-- Footer -->
  <div style="background:#f8fafc;padding:20px 40px;text-align:center;border-top:1px solid #e2e8f0;">
    <p style="color:#94a3b8;font-size:12px;margin:0;">
      AI Tools Empire &bull; {config.SITE_URL} &bull; Report generated {report_date}
    </p>
    <p style="color:#cbd5e1;font-size:11px;margin:6px 0 0;">
      This report is sent daily at 8:00 AM to boaibot@icloud.com
    </p>
  </div>

</div>
</body>
</html>"""

    return html


# ---------------------------------------------------------------------------
# Console report printer
# ---------------------------------------------------------------------------

def print_console_report(stats: dict, affiliate_rows: list, revenue: dict, todos: list, report_date: str):
    """Print a formatted text report to console."""
    separator = "=" * 70
    thin = "-" * 70

    print(f"\n{separator}")
    print(f"  🤖  AI TOOLS EMPIRE DAILY REPORT — {report_date}")
    print(separator)

    # Site stats
    print("\n📊 SITE STATISTICS")
    print(thin)
    print(f"  Total Articles:        {stats['total_articles']}")
    print(f"  Published:             {stats['total_published']}")
    print(f"  Missing Tool Tag:      {stats['missing_featured_tool']}")
    print(f"  Subscribers:           {stats['subscribers']}")
    print(f"  Content in Queue:      {stats['queued_content']}")

    print("\n📁 ARTICLES BY CATEGORY")
    print(thin)
    for c in stats["by_category"]:
        cat = (c.get("category") or "Uncategorized").ljust(20)
        print(f"  {cat} {c['cnt']} articles")

    print("\n🕐 RECENTLY ADDED ARTICLES")
    print(thin)
    for a in stats["recent_articles"]:
        title = a["title"][:55]
        tool = a.get("featured_tool") or "—"
        print(f"  [{(a.get('created_at') or '')[:10]}] {title:<56} tool={tool}")

    print("\n🔗 AFFILIATE PROGRAM STATUS")
    print(thin)
    for r in affiliate_rows:
        icon = "✅" if r["status"] == "active" else "❌"
        name = r["name"].ljust(22)
        comm = r["commission"][:28].ljust(30)
        print(f"  {icon} {name} {comm} ~${r['monthly_est']}/mo")

    print(f"\n💰 REVENUE ESTIMATES")
    print(thin)
    print(f"  Active Monthly:        ${revenue['active_monthly']:,}")
    print(f"  Full Potential:        ${revenue['potential_monthly']:,}")
    print(f"  Missing (gap):         ${revenue['missing_monthly']:,}")
    print(f"  Active Daily:          ${revenue['active_daily']}")

    print("\n✅ PRIORITIZED TO-DO LIST")
    print(thin)
    for t in todos:
        priority_icon = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🔵"}.get(t["priority"], "⚪")
        print(f"\n  {priority_icon} [{t['priority']}] {t['task']}")
        print(f"     → {t['detail']}")

    print(f"\n{separator}\n")


# ---------------------------------------------------------------------------
# Email sender
# ---------------------------------------------------------------------------

def send_email(html_body: str, report_date: str) -> bool:
    """Send the report via Resend API."""
    api_key = config.RESEND_API_KEY
    if not api_key:
        print("⚠️  RESEND_API_KEY not set — skipping email send.")
        return False

    try:
        import resend
    except ImportError:
        print("⚠️  resend package not installed — run: pip install resend")
        return False

    resend.api_key = api_key

    params = {
        "from": f"{config.FROM_NAME} <{config.FROM_EMAIL}>",
        "to": ["boaibot@icloud.com"],
        "subject": f"🤖 AI Tools Empire Daily Report - {report_date}",
        "html": html_body,
    }

    try:
        resp = resend.Emails.send(params)
        print(f"✅ Email sent successfully! ID: {getattr(resp, 'id', resp)}")
        return True
    except Exception as e:
        print(f"❌ Failed to send email: {e}")
        return False


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main():
    report_date = date.today().strftime("%B %d, %Y")
    print(f"Running AI Tools Empire monitor for {report_date}...")

    # Gather data
    stats = get_db_stats()
    affiliate_rows = get_affiliate_status()
    revenue = get_revenue_estimates(affiliate_rows)
    todos = generate_todo_list(stats, affiliate_rows)

    # Print to console
    print_console_report(stats, affiliate_rows, revenue, todos, report_date)

    # Build HTML
    html = build_html_email(stats, affiliate_rows, revenue, todos, report_date)

    # Send email
    send_email(html, report_date)

    print("Monitor run complete.")


if __name__ == "__main__":
    main()
