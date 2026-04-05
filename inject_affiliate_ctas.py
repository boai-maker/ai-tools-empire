"""
inject_affiliate_ctas.py
Injects inline affiliate CTA boxes directly into article HTML content.
Targets the highest-ROI placements: after 2nd paragraph, after 5th paragraph,
and at the end of the article body.
Run once — idempotent (checks for existing injections before adding).
"""

import sqlite3
import re
from bs4 import BeautifulSoup

# Category → best affiliate tool mapping
CATEGORY_TOOL_MAP = {
    "writing":      ["jasper", "copyai", "writesonic"],
    "seo":          ["semrush", "surfer"],
    "video":        ["pictory", "invideo", "descript"],
    "audio":        ["elevenlabs", "murf", "speechify"],
    "productivity": ["getresponse", "hubspot", "fireflies"],
    "image":        ["jasper"],  # fallback
}

# Tool display info for CTA boxes
TOOL_INFO = {
    "jasper":      {"name": "Jasper AI",    "badge": "Most Popular",  "desc": "The #1 AI writing tool for content teams — 30% recurring commission", "btn": "Start Free Trial →", "color": "#f97316"},
    "copyai":      {"name": "Copy.ai",      "badge": "Best Value",    "desc": "45% recurring commission — best free plan in AI writing", "btn": "Try Copy.ai Free →", "color": "#8b5cf6"},
    "writesonic":  {"name": "Writesonic",   "badge": "Best for SEO",  "desc": "AI writing + SEO content in one platform — 30% recurring", "btn": "Try Writesonic →", "color": "#06b6d4"},
    "semrush":     {"name": "Semrush",      "badge": "$200/Sale",     "desc": "All-in-one SEO platform — highest flat commission at $200 per sale", "btn": "Start 7-Day Free Trial →", "color": "#ff642a"},
    "surfer":      {"name": "Surfer SEO",   "badge": "Best SEO Tool", "desc": "AI-powered SEO optimization — 25% recurring commission", "btn": "Try Surfer SEO →", "color": "#6366f1"},
    "pictory":     {"name": "Pictory AI",   "badge": "Best AI Video", "desc": "Turn any article into a video — 50% first month commission", "btn": "Try Pictory Free →", "color": "#ec4899"},
    "invideo":     {"name": "InVideo AI",   "badge": "Easiest Video", "desc": "Create pro videos from text — 50% first payment commission", "btn": "Try InVideo Free →", "color": "#f59e0b"},
    "descript":    {"name": "Descript",     "badge": "Best Creator",  "desc": "Edit video like a Google Doc — 15% recurring commission", "btn": "Try Descript Free →", "color": "#10b981"},
    "elevenlabs":  {"name": "ElevenLabs",   "badge": "Most Realistic","desc": "Ultra-realistic AI voice cloning — 22% recurring commission", "btn": "Try ElevenLabs Free →", "color": "#3b82f6"},
    "murf":        {"name": "Murf AI",      "badge": "Best Voiceover","desc": "Professional AI voiceovers — 30% recurring commission", "btn": "Try Murf Free →", "color": "#7c3aed"},
    "speechify":   {"name": "Speechify",    "badge": "50% Commission","desc": "Read 4.5x faster with AI audio — 50% per sale ($139 avg)", "btn": "Try Speechify Free →", "color": "#059669"},
    "getresponse": {"name": "GetResponse",  "badge": "40% Recurring", "desc": "AI email marketing + automation — 40% recurring for 12 months", "btn": "Try GetResponse Free →", "color": "#0ea5e9"},
    "hubspot":     {"name": "HubSpot",      "badge": "Top CRM",       "desc": "AI-powered CRM — 30% recurring for 12 months", "btn": "Try HubSpot Free →", "color": "#ff7a59"},
    "fireflies":   {"name": "Fireflies AI", "badge": "Best Meeting AI","desc": "AI meeting notetaker — 30% recurring commission", "btn": "Try Fireflies Free →", "color": "#14b8a6"},
}

# Featured tool overrides for specific article IDs (articles without featured_tool)
ARTICLE_FEATURED_TOOL_OVERRIDES = {
    24: "jasper",
    28: "getresponse",
    33: "jasper",
    36: "jasper",
    38: "jasper",
    48: "getresponse",
    49: "getresponse",
    50: "getresponse",
}

CTA_MARKER = "<!-- affiliate-cta-injected -->"

def build_cta_box(tool_key: str, position: str = "mid") -> str:
    """Build a styled inline affiliate CTA box."""
    info = TOOL_INFO.get(tool_key)
    if not info:
        return ""
    color = info["color"]
    bg_light = "rgba(99,102,241,0.06)" if position == "mid" else "rgba(0,0,0,0.03)"
    return f"""
{CTA_MARKER}
<div style="margin:32px 0;padding:24px 28px;background:{bg_light};border:1px solid {color}33;border-left:4px solid {color};border-radius:12px;font-family:inherit;">
  <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">
    <span style="background:{color};color:#fff;font-size:11px;font-weight:700;padding:3px 10px;border-radius:20px;letter-spacing:0.5px;text-transform:uppercase;">{info['badge']}</span>
    <strong style="font-size:16px;color:#1e1b4b;">{info['name']}</strong>
  </div>
  <p style="margin:0 0 16px 0;color:#374151;font-size:15px;">{info['desc']}</p>
  <a href="/go/{tool_key}" class="affiliate-link" data-tool="{tool_key}" target="_blank" rel="noopener sponsored"
     style="display:inline-block;background:{color};color:#fff;font-weight:700;padding:11px 24px;border-radius:8px;text-decoration:none;font-size:15px;">
    {info['btn']}
  </a>
</div>
"""

def inject_ctas_into_content(content: str, primary_tool: str, secondary_tool: str = None) -> str:
    """Inject CTA boxes after 2nd and 5th paragraphs, plus end-of-article box."""
    if CTA_MARKER in content:
        return content  # Already injected — skip

    soup = BeautifulSoup(content, "html.parser")
    paragraphs = soup.find_all("p")

    if len(paragraphs) < 3:
        return content  # Too short to inject safely

    # Injection 1: after 2nd paragraph (early hook)
    target_p2 = paragraphs[1]
    cta1_html = build_cta_box(primary_tool, "mid")
    cta1_tag = BeautifulSoup(cta1_html, "html.parser")
    target_p2.insert_after(cta1_tag)

    # Refresh paragraph list after modification
    soup = BeautifulSoup(str(soup), "html.parser")
    paragraphs = soup.find_all("p")

    # Injection 2: after 5th paragraph (mid-article momentum)
    if len(paragraphs) >= 6 and secondary_tool and secondary_tool != primary_tool:
        target_p5 = paragraphs[4]
        cta2_html = build_cta_box(secondary_tool, "mid")
        cta2_tag = BeautifulSoup(cta2_html, "html.parser")
        target_p5.insert_after(cta2_tag)

    # Injection 3: end-of-article CTA (closing conversion)
    result_html = str(soup)
    end_cta = build_cta_box(primary_tool, "end")
    # Append before last closing tag
    result_html = result_html + end_cta

    return result_html


def main():
    conn = sqlite3.connect("/Users/kennethbonnet/ai-tools-empire/data.db")
    c = conn.cursor()

    c.execute("SELECT id, title, category, featured_tool, content FROM articles")
    articles = c.fetchall()

    updated = 0
    skipped = 0
    for art_id, title, category, featured_tool, content in articles:
        # Determine primary tool
        primary = featured_tool or ARTICLE_FEATURED_TOOL_OVERRIDES.get(art_id)
        if not primary:
            tools = CATEGORY_TOOL_MAP.get(category, ["jasper"])
            primary = tools[0]

        # Determine secondary tool (different from primary)
        cat_tools = CATEGORY_TOOL_MAP.get(category, ["jasper"])
        secondary = None
        for t in cat_tools:
            if t != primary:
                secondary = t
                break

        # Check if already injected
        if CTA_MARKER in (content or ""):
            skipped += 1
            continue

        new_content = inject_ctas_into_content(content or "", primary, secondary)
        if new_content != content:
            # Also update featured_tool if missing
            if not featured_tool and art_id in ARTICLE_FEATURED_TOOL_OVERRIDES:
                c.execute(
                    "UPDATE articles SET content=?, featured_tool=? WHERE id=?",
                    (new_content, ARTICLE_FEATURED_TOOL_OVERRIDES[art_id], art_id)
                )
            else:
                c.execute("UPDATE articles SET content=? WHERE id=?", (new_content, art_id))
            updated += 1
            print(f"  ✓ [{art_id}] {title[:60]} — {primary}/{secondary}")
        else:
            skipped += 1

    conn.commit()
    conn.close()
    print(f"\nDone: {updated} articles updated, {skipped} skipped.")


if __name__ == "__main__":
    main()
