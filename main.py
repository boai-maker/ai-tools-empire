"""
AI Tools Empire — Main FastAPI Server
Serves the website, handles subscriptions, affiliate tracking, and admin actions.
"""
import os
import hashlib
import logging
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Form, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.exception_handlers import http_exception_handler
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel

from config import config
from database.db import (
    init_db, get_articles, get_article_by_slug, increment_views,
    add_subscriber, get_subscriber_count, log_click, log_pageview,
    get_analytics_summary, get_articles, add_to_queue
)
from affiliate.links import AFFILIATE_PROGRAMS, CATEGORIES, get_monthly_revenue_estimate

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# ── App lifespan ──────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Seed content queue on first run
    try:
        from automation.content_generator import populate_initial_queue
        populate_initial_queue()
    except Exception as e:
        log.warning(f"Queue seeding skipped: {e}")
    log.info(f"✅ {config.SITE_NAME} started at {config.SITE_URL}")
    yield

app = FastAPI(title=config.SITE_NAME, lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ── Custom exception handlers ─────────────────────────────────────────────────
@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        ctx = base_ctx(request)
        ctx["popular_tools"] = dict(list(AFFILIATE_PROGRAMS.items())[:3])
        return templates.TemplateResponse("404.html", ctx, status_code=404)
    return await http_exception_handler(request, exc)

# ── HEAD method support (for health checks / load balancers) ──────────────────
@app.head("/")
async def head_homepage():
    return Response(status_code=200)

# ── Template globals ──────────────────────────────────────────────────────────
def base_ctx(request: Request) -> dict:
    return {
        "request": request,
        "site_name": config.SITE_NAME,
        "site_url": config.SITE_URL,
        "site_tagline": config.SITE_TAGLINE,
        "current_year": datetime.now().year,
        "categories": CATEGORIES,
        "google_verification": config.GOOGLE_SITE_VERIFICATION,
    }

def ip_hash(request: Request) -> str:
    ip = request.client.host if request.client else "unknown"
    return hashlib.md5(ip.encode()).hexdigest()[:16]

# ── Middleware: pageview tracking ─────────────────────────────────────────────
@app.middleware("http")
async def track_pageviews(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if not path.startswith(("/static", "/track", "/admin", "/favicon")):
        try:
            log_pageview(
                path=path,
                referrer=request.headers.get("referer", ""),
                user_agent=request.headers.get("user-agent", "")[:200],
                ip_hash=ip_hash(request),
            )
        except Exception:
            pass
    return response

# ── Pages ─────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def homepage(request: Request):
    articles = get_articles(limit=6)
    ctx = base_ctx(request)
    ctx.update({
        "articles": articles,
        "featured_tools": dict(list(AFFILIATE_PROGRAMS.items())[:6]),
        "subscriber_count": get_subscriber_count(),  # Real count — no floor
        "article_count": len(get_articles(limit=999)),  # Real count — no floor
    })
    return templates.TemplateResponse("index.html", ctx)


@app.get("/tools", response_class=HTMLResponse)
async def tools_page(request: Request, category: str = None):
    if category and category in CATEGORIES:
        tools = {k: v for k, v in AFFILIATE_PROGRAMS.items() if v["category"] == category}
    else:
        tools = AFFILIATE_PROGRAMS
        category = None
    ctx = base_ctx(request)
    ctx.update({
        "tools": tools,
        "active_category": category,
        "total_tools": len(AFFILIATE_PROGRAMS),
    })
    return templates.TemplateResponse("tools.html", ctx)


@app.get("/articles", response_class=HTMLResponse)
async def articles_page(request: Request, category: str = None, q: str = None):
    all_articles = get_articles(limit=50, category=category)
    if q:
        q_lower = q.lower()
        all_articles = [a for a in all_articles if q_lower in a["title"].lower()]
    ctx = base_ctx(request)
    ctx.update({
        "articles": all_articles,
        "active_category": category,
        "total_articles": len(all_articles),
        "top_tools": dict(list(AFFILIATE_PROGRAMS.items())[:5]),
    })
    return templates.TemplateResponse("articles.html", ctx)


@app.get("/blog/{slug}")
async def blog_redirect(slug: str):
    """Redirect /blog/ URLs to canonical /articles/ to prevent duplicate indexing."""
    return RedirectResponse(url=f"/articles/{slug}", status_code=301)

# ── SEO 301 redirects for duplicate/retired slugs ─────────────────────────────
SLUG_REDIRECTS = {
    # Jasper vs Copy.ai duplicates → canonical
    "jasper-ai-vs-copy-ai-which-is-better-in-2026": "jasper-ai-vs-copyai-2026-comparison",
    "jasper-ai-vs-copyai-which-is-better-in-2026": "jasper-ai-vs-copyai-2026-comparison",
    "jasper-ai-vs-copyai-2026-full-comparison": "jasper-ai-vs-copyai-2026-comparison",
    "copy-ai-vs-jasper-ai-2026-which-ai-writer-should-you-buy": "jasper-ai-vs-copyai-2026-comparison",
    # ElevenLabs review duplicates → canonical
    "elevenlabs-review-2026-the-best-ai-voice-cloning-tool": "elevenlabs-review-2026",
    "elevenlabs-review-2026-best-ai-voice": "elevenlabs-review-2026",
    # SEO / writing tools duplicates → canonical
    "best-ai-seo-tools-in-2026-rank-faster-with-less-work": "best-ai-seo-tools-2026-ranked",
    "surfer-seo-review-2026-worth-the-price": "surfer-seo-review-2026",
    "writesonic-review-2026-ai-writer": "writesonic-review-2026",
    "copy-ai-review-2026-honest-verdict": "copyai-review-2026",
    "best-ai-writing-tools-2026": "best-ai-writing-tools-comparison-2026",
}

@app.get("/articles/{slug}", response_class=HTMLResponse)
async def article_page(request: Request, slug: str):
    # 301 redirect retired duplicate slugs to their canonical
    if slug in SLUG_REDIRECTS:
        return RedirectResponse(url=f"/articles/{SLUG_REDIRECTS[slug]}", status_code=301)

    article = get_article_by_slug(slug)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    increment_views(slug)

    # Inject internal links for SEO
    try:
        from automation.internal_linker import inject_internal_links
        article["content"] = inject_internal_links(article["content"], slug)
    except Exception:
        pass

    # Featured tool sidebar data
    featured_tool_key = article.get("featured_tool", "")
    featured_tool_data = AFFILIATE_PROGRAMS.get(featured_tool_key)

    # Sidebar tools (exclude featured)
    sidebar_tools = {
        k: v for k, v in list(AFFILIATE_PROGRAMS.items())[:4]
        if k != featured_tool_key
    }

    # Related articles (same category)
    related = [
        a for a in get_articles(limit=10, category=article.get("category"))
        if a["slug"] != slug
    ][:3]

    ctx = base_ctx(request)
    ctx.update({
        "article": article,
        "featured_tool_data": featured_tool_data,
        "sidebar_tools": sidebar_tools,
        "related_articles": related,
    })
    return templates.TemplateResponse("article.html", ctx)


@app.get("/about", response_class=HTMLResponse)
async def about_page(request: Request):
    article_count = len(get_articles(limit=999))
    ctx = base_ctx(request)
    ctx["page_title"] = "About Us"
    ctx["page_content"] = f"""
    <div style="background:linear-gradient(135deg,#0f172a,#1e1b4b);padding:60px 20px;text-align:center;margin-bottom:0;">
      <h1 style="color:white;font-size:42px;font-weight:800;margin:0 0 12px;">About {config.SITE_NAME}</h1>
      <p style="color:#94a3b8;font-size:18px;margin:0;">Independent research on AI tools for businesses and creators.</p>
    </div>
    <div style="max-width:760px;margin:60px auto;padding:0 24px;">
      <p style="font-size:18px;color:#475569;line-height:1.8;">{config.SITE_NAME} is an independent review publication covering AI tools for writing, SEO, video, voice, and productivity.</p>
      <p style="color:#475569;line-height:1.8;">We research and review AI tools so you can make informed decisions before spending money. We cover features, real pricing, and who each tool is actually for — not rewrites of marketing pages.</p>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin:40px 0;">
        <div style="background:white;border:1px solid #e2e8f0;border-radius:12px;padding:24px;text-align:center;">
          <div style="font-size:32px;font-weight:900;color:#6366f1;">{article_count}+</div>
          <div style="color:#64748b;font-size:14px;margin-top:4px;">Articles &amp; Reviews</div>
        </div>
        <div style="background:white;border:1px solid #e2e8f0;border-radius:12px;padding:24px;text-align:center;">
          <div style="font-size:32px;font-weight:900;color:#6366f1;">17</div>
          <div style="color:#64748b;font-size:14px;margin-top:4px;">AI Tools Covered</div>
        </div>
        <div style="background:white;border:1px solid #e2e8f0;border-radius:12px;padding:24px;text-align:center;">
          <div style="font-size:32px;font-weight:900;color:#6366f1;">5</div>
          <div style="color:#64748b;font-size:14px;margin-top:4px;">Categories</div>
        </div>
        <div style="background:white;border:1px solid #e2e8f0;border-radius:12px;padding:24px;text-align:center;">
          <div style="font-size:32px;font-weight:900;color:#6366f1;">Free</div>
          <div style="color:#64748b;font-size:14px;margin-top:4px;">Weekly Newsletter</div>
        </div>
      </div>
      <h2 style="font-size:26px;font-weight:800;margin:40px 0 16px;">Our Editorial Policy</h2>
      <ul style="color:#475569;line-height:2;font-size:15px;">
        <li>We are never paid to write positive reviews — commissions come only from purchases you make</li>
        <li>We include honest limitations and cons on every tool we cover</li>
        <li>We update content when pricing, features, or our assessment changes</li>
        <li>Affiliate links are disclosed on every page where they appear</li>
      </ul>
      <h2 style="font-size:26px;font-weight:800;margin:40px 0 16px;">Affiliate Disclosure</h2>
      <p style="color:#475569;line-height:1.8;">This site earns affiliate commissions when you purchase through our links, at no extra cost to you. This supports the free content we publish. See our full <a href="/disclaimer" style="color:#6366f1;">affiliate disclaimer</a> and <a href="/how-we-test" style="color:#6366f1;">how we review</a> for details.</p>
      <div style="margin-top:40px;text-align:center;">
        <a href="/tools" class="btn btn-primary">Browse AI Tools →</a>
      </div>
    </div>
    """
    return templates.TemplateResponse("simple_page.html", ctx)


@app.get("/privacy", response_class=HTMLResponse)
async def privacy_page(request: Request):
    ctx = base_ctx(request)
    ctx["page_title"] = "Privacy Policy"
    ctx["page_content"] = f"""
    <div style="background:linear-gradient(135deg,#0f172a,#1e1b4b);padding:60px 20px;text-align:center;">
      <h1 style="color:white;font-size:40px;font-weight:800;margin:0 0 8px;">Privacy Policy</h1>
      <p style="color:#94a3b8;">Last updated: {datetime.now().strftime('%B %Y')}</p>
    </div>
    <div style="max-width:760px;margin:60px auto;padding:0 24px;color:#475569;line-height:1.8;font-size:15px;">
      <h2 style="color:#1e293b;font-size:22px;font-weight:700;margin:32px 0 12px;">Data We Collect</h2>
      <p>We collect email addresses when you subscribe to our newsletter. We also collect anonymized analytics (page views, referrers) to improve content. We do not collect personal information beyond your email.</p>
      <h2 style="color:#1e293b;font-size:22px;font-weight:700;margin:32px 0 12px;">How We Use Your Data</h2>
      <p>Your email is used only to send our weekly newsletter and welcome email. We never sell, rent, or share your data with third parties for marketing purposes.</p>
      <h2 style="color:#1e293b;font-size:22px;font-weight:700;margin:32px 0 12px;">Affiliate Links</h2>
      <p>This site contains affiliate links. When you click and purchase, we earn a commission at no extra cost to you. Affiliate programs may set their own cookies.</p>
      <h2 style="color:#1e293b;font-size:22px;font-weight:700;margin:32px 0 12px;">Cookies</h2>
      <p>We use minimal cookies for site functionality only. No advertising or tracking cookies are set by us directly.</p>
      <h2 style="color:#1e293b;font-size:22px;font-weight:700;margin:32px 0 12px;">Your Rights</h2>
      <p>You may unsubscribe from our newsletter at any time using the unsubscribe link in any email. To request data deletion, contact us at <a href="mailto:privacy@aitoolsempire.co" style="color:#6366f1;">privacy@aitoolsempire.co</a>.</p>
    </div>
    """
    return templates.TemplateResponse("simple_page.html", ctx)


@app.get("/disclaimer", response_class=HTMLResponse)
async def disclaimer_page(request: Request):
    ctx = base_ctx(request)
    ctx["page_title"] = "Affiliate Disclaimer"
    ctx["page_content"] = f"""
    <div style="background:linear-gradient(135deg,#0f172a,#1e1b4b);padding:60px 20px;text-align:center;">
      <h1 style="color:white;font-size:40px;font-weight:800;margin:0;">Affiliate Disclaimer</h1>
    </div>
    <div style="max-width:760px;margin:60px auto;padding:0 24px;color:#475569;line-height:1.8;font-size:15px;">
      <p style="font-size:17px;color:#1e293b;">{config.SITE_NAME} participates in affiliate marketing programs.</p>
      <p>When you click our links and make a purchase, we may earn a commission — <strong>at no additional cost to you.</strong></p>
      <p>We only recommend products and services we have personally tested and genuinely believe will add value to our readers. Our star ratings, review scores, and editorial opinions are never influenced by affiliate relationships.</p>
      <div style="background:#fefce8;border:1px solid #fde047;border-radius:10px;padding:20px;margin:32px 0;">
        <p style="color:#713f12;margin:0;font-size:14px;"><strong>💡 Our commitment:</strong> If we recommend a tool, it's because we think it's genuinely good — not because it pays us more. Our highest-earning affiliate program would never get a positive review it doesn't deserve.</p>
      </div>
      <p>For questions about our affiliate relationships, contact <a href="mailto:hello@aitoolsempire.co" style="color:#6366f1;">hello@aitoolsempire.co</a>.</p>
    </div>
    """
    return templates.TemplateResponse("simple_page.html", ctx)


@app.get("/contact", response_class=HTMLResponse)
async def contact_page(request: Request):
    ctx = base_ctx(request)
    return templates.TemplateResponse("contact.html", ctx)


@app.get("/services", response_class=HTMLResponse)
async def services_page(request: Request):
    ctx = base_ctx(request)
    return templates.TemplateResponse("services.html", ctx)


# ── API Endpoints ─────────────────────────────────────────────────────────────

class SubscribeRequest(BaseModel):
    email: str
    name: str = ""

@app.post("/subscribe")
async def subscribe(request: Request, body: SubscribeRequest):
    email = body.email.lower().strip()
    if not email or "@" not in email:
        return JSONResponse({"success": False, "message": "Invalid email"})

    added = add_subscriber(email, body.name, source="website")
    if not added:
        return JSONResponse({"success": True, "message": "Already subscribed!"})

    # Send welcome email in background
    try:
        from automation.email_sender import send_welcome_email
        send_welcome_email(email, body.name)
    except Exception as e:
        log.warning(f"Welcome email failed: {e}")

    return JSONResponse({"success": True, "message": "Subscribed! Check your inbox."})


@app.post("/track/click/{tool_key}")
async def track_click(tool_key: str, request: Request, source: str = ""):
    try:
        log_click(tool_key, source, ip_hash(request))
    except Exception:
        pass
    return JSONResponse({"ok": True})


@app.get("/go/{tool_key}")
async def affiliate_redirect(tool_key: str, request: Request):
    """
    Clean affiliate redirect: /go/jasper, /go/semrush, etc.
    Tracks clicks + redirects to current affiliate URL.
    Reads affiliate IDs live from env → no server restart needed after updating IDs.
    """
    # Direct URL map — reads env vars live so IDs activate without restart
    aff_url_map = {
        "jasper":     f"https://www.jasper.ai/?fpr={os.getenv('JASPER_AFFILIATE_ID', '')}",
        "copyai":     f"https://www.copy.ai/?via={os.getenv('COPYAI_AFFILIATE_ID', '')}",
        "writesonic": f"https://writesonic.com/?via={os.getenv('WRITESONIC_AFFILIATE_ID', '')}",
        "surfer":     f"https://surferseo.com/?via={os.getenv('SURFER_AFFILIATE_ID', '')}",
        "semrush":    f"https://www.semrush.com/partner/?affcode={os.getenv('SEMRUSH_AFFILIATE_ID', '')}",
        "pictory":    f"https://pictory.ai/?ref={os.getenv('PICTORY_AFFILIATE_ID', '')}",
        "invideo":    f"https://invideo.io/?ref={os.getenv('INVIDEO_AFFILIATE_ID', '')}",
        "murf":       f"https://murf.ai/?ref={os.getenv('MURF_AFFILIATE_ID', '')}",
        "elevenlabs": f"https://elevenlabs.io/?from={os.getenv('ELEVENLABS_AFFILIATE_ID', '')}",
        "descript":   f"https://www.descript.com/affiliates?ref={os.getenv('DESCRIPT_AFFILIATE_ID', '')}",
        "fireflies":   f"https://fireflies.ai/?ref={os.getenv('FIREFLIES_AFFILIATE_ID', '')}",
        "speechify":   f"https://speechify.com/affiliate/?ref={os.getenv('SPEECHIFY_AFFILIATE_ID', '')}",
        "getresponse": f"https://www.getresponse.com/?a={os.getenv('GETRESPONSE_AFFILIATE_ID', '')}",
        "hubspot":     f"https://www.hubspot.com/?hubs_signup-cta={os.getenv('HUBSPOT_AFFILIATE_ID', '')}",
        "quillbot":    f"https://quillbot.com/?utm_source=affiliate&ref={os.getenv('QUILLBOT_AFFILIATE_ID', '')}",
        "kit":         f"https://kit.com/?ref={os.getenv('KIT_AFFILIATE_ID', '')}",
        "webflow":     f"https://webflow.com/r/{os.getenv('WEBFLOW_AFFILIATE_ID', '')}",
    }
    # Fallback: clean product URL without affiliate ID if ID not set
    fallback_map = {
        "jasper": "https://www.jasper.ai/", "copyai": "https://www.copy.ai/",
        "writesonic": "https://writesonic.com/", "surfer": "https://surferseo.com/",
        "semrush": "https://www.semrush.com/", "pictory": "https://pictory.ai/",
        "invideo": "https://invideo.io/", "murf": "https://murf.ai/",
        "elevenlabs": "https://elevenlabs.io/", "descript": "https://www.descript.com/",
        "fireflies": "https://fireflies.ai/", "speechify": "https://speechify.com/",
        "getresponse": "https://www.getresponse.com/", "hubspot": "https://www.hubspot.com/",
        "quillbot": "https://quillbot.com/", "kit": "https://kit.com/",
        "webflow": "https://webflow.com/",
    }
    if tool_key not in aff_url_map:
        raise HTTPException(status_code=404, detail=f"Unknown tool: {tool_key}")
    # Use affiliate URL if ID is set, else clean fallback
    # If the stored ID is already a full URL (e.g. ElevenLabs referral link), use it directly
    aff_id = os.getenv(f"{tool_key.upper()}_AFFILIATE_ID", "")
    if aff_id and aff_id.startswith("http"):
        redirect_url = aff_id
    elif aff_id and not aff_id.startswith("YOUR"):
        redirect_url = aff_url_map[tool_key]
    else:
        redirect_url = fallback_map[tool_key]
    try:
        source = request.headers.get("referer", "direct")
        log_click(tool_key, source, ip_hash(request))
    except Exception:
        pass
    return RedirectResponse(url=redirect_url, status_code=302)


@app.get("/how-we-test", response_class=HTMLResponse)
async def how_we_test(request: Request):
    ctx = base_ctx(request)
    ctx["page_title"] = "How We Test AI Tools"
    ctx["page_content"] = """
<div style="background:linear-gradient(135deg,#0f172a,#1e1b4b);padding:60px 20px;text-align:center;">
  <h1 style="color:white;font-size:40px;font-weight:800;margin:0 0 8px;">How We Test AI Tools</h1>
  <p style="color:#94a3b8;">Our methodology for honest, independent reviews</p>
</div>
<div style="max-width:760px;margin:60px auto;padding:0 24px;color:#475569;line-height:1.8;font-size:15px;">
  <p>Every tool reviewed on AI Tools Empire goes through the same structured evaluation process. We don't accept payment for positive reviews. Our rankings are based entirely on hands-on testing.</p>
  <h2 style="color:#1e293b;font-size:22px;font-weight:700;margin:32px 0 12px;">1. Research &amp; Testing</h2>
  <p>We research each tool using official documentation, pricing pages, published user feedback, and where possible, direct product trials. Our goal is to give you an accurate picture of what each tool does, what it costs, and who it's actually for — not a rewrite of the marketing page.</p>
  <h2 style="color:#1e293b;font-size:22px;font-weight:700;margin:32px 0 12px;">2. Scoring Criteria</h2>
  <p>Each tool is scored across five dimensions:</p>
  <ul>
    <li><strong>Output Quality</strong> — Does the AI produce results you'd actually use?</li>
    <li><strong>Ease of Use</strong> — Can a non-technical user get results in under 10 minutes?</li>
    <li><strong>Value for Money</strong> — Is the pricing justified by what you get?</li>
    <li><strong>Features</strong> — Does it cover the core use cases for its category?</li>
    <li><strong>Support &amp; Reliability</strong> — Is the tool stable and is help available when needed?</li>
  </ul>
  <h2 style="color:#1e293b;font-size:22px;font-weight:700;margin:32px 0 12px;">3. Comparison Testing</h2>
  <p>Where possible, we test competing tools on the same prompt or task side-by-side. This lets us make direct comparisons rather than reviewing in isolation.</p>
  <h2 style="color:#1e293b;font-size:22px;font-weight:700;margin:32px 0 12px;">4. Pricing Verification</h2>
  <p>We check pricing directly from each tool's official pricing page. Prices change — we note when articles were last updated and recommend you verify current pricing before purchasing.</p>
  <h2 style="color:#1e293b;font-size:22px;font-weight:700;margin:32px 0 12px;">Affiliate Disclosure</h2>
  <p>Some tools on this site have affiliate programs. If you click a link and make a purchase, we may earn a commission at no extra cost to you. This never influences our ratings or recommendations — we turn down affiliate relationships with tools we wouldn't recommend to a friend.</p>
  <h2 style="color:#1e293b;font-size:22px;font-weight:700;margin:32px 0 12px;">Update Policy</h2>
  <p>AI tools change rapidly. We review and update articles when tools release major updates, change pricing, or when our testing reveals the review is no longer accurate. Each article shows its last-updated date.</p>
  <div style="margin-top:32px;padding:16px;background:#f0fdf4;border-radius:8px;border:1px solid #86efac;">
    Have a tool you'd like us to review? <a href="/contact" style="color:#6366f1;font-weight:600;">Contact us here</a>.
  </div>
</div>
"""
    return templates.TemplateResponse("simple_page.html", ctx)


# ── Best-Of Hub Pages (Agent 3: SEO Architecture) ────────────────────────────

def _best_of_page(request: Request, category: str, h1: str, intro: str, meta_desc: str):
    """Render a best-of hub page for a given tool category."""
    from affiliate.links import get_tools_by_category
    ctx = base_ctx(request)
    tools = get_tools_by_category(category)
    tool_cards = ""
    for i, (key, tool) in enumerate(tools.items(), 1):
        tool_cards += f"""
        <div style="background:white;border:1px solid #e2e8f0;border-radius:14px;padding:24px;margin-bottom:20px;display:flex;gap:20px;align-items:flex-start;">
          <div style="font-size:36px;min-width:48px;text-align:center;">#{i}</div>
          <div style="flex:1;">
            <div style="display:flex;align-items:center;gap:12px;margin-bottom:8px;">
              <h3 style="margin:0;font-size:20px;font-weight:800;color:#1e293b;">{tool['name']}</h3>
              <span style="background:#ecfdf5;color:#065f46;font-size:11px;font-weight:700;padding:3px 10px;border-radius:100px;text-transform:uppercase;">{tool.get('badge','')}</span>
            </div>
            <p style="color:#64748b;margin:0 0 14px;font-size:15px;line-height:1.6;">{tool['description']}</p>
            <div style="display:flex;gap:12px;">
              <a href="/go/{key}" style="background:#10b981;color:white;padding:10px 20px;border-radius:8px;font-weight:700;text-decoration:none;font-size:14px;">Start Free Trial →</a>
              <a href="/articles?q={tool['name']}" style="border:2px solid #6366f1;color:#6366f1;padding:10px 20px;border-radius:8px;font-weight:600;text-decoration:none;font-size:14px;">Read Review</a>
            </div>
          </div>
        </div>"""

    ctx["page_title"] = h1
    ctx["page_meta_description"] = meta_desc
    ctx["page_content"] = f"""
<div style="background:linear-gradient(135deg,#0f172a,#1e1b4b);padding:60px 20px;text-align:center;">
  <div style="display:inline-block;background:rgba(99,102,241,0.2);border:1px solid rgba(99,102,241,0.4);color:#a5b4fc;padding:6px 16px;border-radius:100px;font-size:13px;font-weight:600;margin-bottom:16px;">🔥 Updated April 2026</div>
  <h1 style="color:white;font-size:clamp(28px,4vw,42px);font-weight:800;margin:0 auto 12px;max-width:700px;line-height:1.2;">{h1}</h1>
  <p style="color:#94a3b8;font-size:17px;max-width:560px;margin:0 auto;">{intro}</p>
</div>
<div style="max-width:800px;margin:48px auto;padding:0 24px;">
  <div style="background:#fffbeb;border:1px solid #fde68a;border-radius:8px;padding:12px 16px;font-size:13px;color:#92400e;margin-bottom:32px;">
    📢 <strong>Affiliate Disclosure:</strong> We earn a commission if you purchase through our links, at no extra cost to you. Rankings are based on hands-on testing, not commissions.
  </div>
  {tool_cards}
  <div style="margin-top:40px;padding:24px;background:#f0f9ff;border-radius:12px;border:1px solid #bae6fd;text-align:center;">
    <p style="color:#0369a1;font-size:15px;margin:0 0 12px;font-weight:600;">Not sure which tool is right for you?</p>
    <a href="/contact" style="color:#6366f1;font-weight:700;text-decoration:none;">Ask us →</a> &nbsp;·&nbsp;
    <a href="/how-we-test" style="color:#6366f1;font-weight:700;text-decoration:none;">How we test →</a>
  </div>

  <!-- Newsletter CTA -->
  <div style="margin-top:32px;background:linear-gradient(135deg,#312e81,#1e1b4b);border-radius:14px;padding:36px;text-align:center;">
    <h3 style="color:white;font-size:22px;font-weight:800;margin:0 0 8px;">Get Weekly AI Tool Updates</h3>
    <p style="color:#a5b4fc;margin:0 0 20px;font-size:15px;">Tool reviews, pricing changes, and comparisons — every Monday. Free.</p>
    <form style="display:flex;gap:10px;max-width:400px;margin:0 auto;" onsubmit="handleSubscribeBestOf(event)">
      <input type="email" id="bestof-email" placeholder="your@email.com" required
             style="flex:1;padding:12px 16px;border-radius:8px;border:none;font-size:14px;">
      <button type="submit"
              style="background:#6366f1;color:white;border:none;padding:12px 20px;border-radius:8px;font-weight:700;font-size:14px;cursor:pointer;white-space:nowrap;">
        Subscribe
      </button>
    </form>
    <p style="color:#6366f1;font-size:12px;margin:12px 0 0;">No spam. Unsubscribe anytime.</p>
  </div>
</div>
<script>
async function handleSubscribeBestOf(e) {{
  e.preventDefault();
  const btn = e.target.querySelector('button');
  btn.textContent = '...'; btn.disabled = true;
  const res = await fetch('/subscribe', {{
    method: 'POST', headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{email: document.getElementById('bestof-email').value}})
  }});
  const data = await res.json();
  btn.textContent = data.success ? '✓ Subscribed!' : 'Try again';
  btn.style.background = data.success ? '#10b981' : '#ef4444';
  if (!data.success) btn.disabled = false;
}}
</script>
"""
    return templates.TemplateResponse("simple_page.html", ctx)


@app.get("/best-ai-writing-tools", response_class=HTMLResponse)
async def best_writing_tools(request: Request):
    return _best_of_page(request, "writing",
        "Best AI Writing Tools in 2026 (Tested & Ranked)",
        "We tested every major AI writing tool so you don't have to. Here's what actually works.",
        "The best AI writing tools of 2026, tested hands-on. Compare Jasper, Copy.ai, Writesonic, and QuillBot by features, pricing, and real output quality.")

@app.get("/best-ai-seo-tools", response_class=HTMLResponse)
async def best_seo_tools(request: Request):
    return _best_of_page(request, "seo",
        "Best AI SEO Tools in 2026 (Tested & Ranked)",
        "The AI SEO tools that actually move rankings. Tested on real sites, not just demo content.",
        "Best AI SEO tools of 2026 reviewed and ranked. Compare Semrush vs Surfer SEO by features, pricing, and real ranking results.")

@app.get("/best-ai-video-tools", response_class=HTMLResponse)
async def best_video_tools(request: Request):
    return _best_of_page(request, "video",
        "Best AI Video Tools in 2026 (Tested & Ranked)",
        "Create professional videos without a camera or editing skills. Here's what we actually recommend.",
        "Best AI video tools of 2026. We tested Pictory, InVideo, and Descript on real projects. See which one makes the best videos fastest.")

@app.get("/best-ai-voice-tools", response_class=HTMLResponse)
async def best_voice_tools(request: Request):
    return _best_of_page(request, "audio",
        "Best AI Voice Tools in 2026 (Tested & Ranked)",
        "Ultra-realistic AI voiceovers and text-to-speech. We ran 50+ test samples to find the winner.",
        "Best AI voice tools of 2026. We compared ElevenLabs, Murf AI, and Speechify on voice quality, pricing, and ease of use.")

@app.get("/best-ai-productivity-tools", response_class=HTMLResponse)
async def best_productivity_tools(request: Request):
    return _best_of_page(request, "productivity",
        "Best AI Productivity Tools in 2026 (Tested & Ranked)",
        "The AI tools that save real time. Ranked by ROI, not just features.",
        "Best AI productivity tools of 2026. Compare Fireflies, HubSpot, GetResponse, Kit, and Webflow — tested for real business use.")


@app.get("/unsubscribe")
async def unsubscribe(email: str = ""):
    if email:
        from database.db import get_conn
        conn = get_conn()
        conn.execute("UPDATE subscribers SET status='unsubscribed' WHERE email=?", (email.lower(),))
        conn.commit()
        conn.close()
    html = """<!DOCTYPE html><html><body style='font-family:sans-serif;text-align:center;padding:60px'>
    <h2>You've been unsubscribed.</h2><p>Sorry to see you go. <a href='/'>Return home</a></p>
    </body></html>"""
    return HTMLResponse(html)


# ── Admin Endpoints (protected) ───────────────────────────────────────────────

def verify_admin(request: Request):
    token = request.cookies.get("admin_token") or request.headers.get("X-Admin-Token")
    if token != config.ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True


@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    # Simple password check via query param for first login
    pwd = request.query_params.get("pwd", "")
    if pwd != config.ADMIN_PASSWORD:
        html = """<!DOCTYPE html><html><body style='font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;background:#f8fafc'>
        <form method='get' style='text-align:center;background:white;padding:40px;border-radius:12px;box-shadow:0 4px 20px rgba(0,0,0,0.1)'>
          <h2 style='margin:0 0 20px;'>🔐 Admin Login</h2>
          <input name='pwd' type='password' placeholder='Password' style='padding:12px 18px;border-radius:8px;border:1px solid #e2e8f0;font-size:15px;width:240px;margin-bottom:12px;display:block;'>
          <button type='submit' style='background:#6366f1;color:white;border:none;padding:12px 28px;border-radius:8px;font-size:15px;font-weight:600;cursor:pointer;width:100%'>Login</button>
        </form></body></html>"""
        return HTMLResponse(html)

    stats = get_analytics_summary()
    revenue = get_monthly_revenue_estimate()
    recent_articles = get_articles(limit=8)
    ctx = base_ctx(request)
    ctx.update({
        "stats": stats,
        "revenue": revenue,
        "recent_articles": recent_articles,
        "affiliate_programs": AFFILIATE_PROGRAMS,
    })
    return templates.TemplateResponse("dashboard.html", ctx)


@app.post("/admin/generate-content")
async def admin_generate_content(request: Request):
    pwd = request.query_params.get("pwd", request.headers.get("X-Admin-Token", ""))
    if pwd != config.ADMIN_PASSWORD:
        raise HTTPException(401)
    try:
        from automation.content_generator import run_content_generation
        result = run_content_generation(count=3)
        return JSONResponse({"message": f"Generated {result['generated']} articles", **result})
    except Exception as e:
        return JSONResponse({"message": f"Error: {str(e)}"}, status_code=500)


@app.post("/admin/send-welcomes")
async def admin_send_welcomes(request: Request):
    pwd = request.query_params.get("pwd", request.headers.get("X-Admin-Token", ""))
    if pwd != config.ADMIN_PASSWORD:
        raise HTTPException(401)
    try:
        from automation.email_sender import send_welcome_to_pending
        sent = send_welcome_to_pending()
        return JSONResponse({"message": f"Sent {sent} welcome emails", "sent": sent})
    except Exception as e:
        return JSONResponse({"message": f"Error: {str(e)}"}, status_code=500)


@app.post("/admin/send-newsletter")
async def admin_send_newsletter(request: Request):
    pwd = request.query_params.get("pwd", request.headers.get("X-Admin-Token", ""))
    if pwd != config.ADMIN_PASSWORD:
        raise HTTPException(401)
    try:
        from automation.email_sender import send_weekly_newsletter
        sent = send_weekly_newsletter()
        return JSONResponse({"message": f"Newsletter sent to {sent} subscribers", "sent": sent})
    except Exception as e:
        return JSONResponse({"message": f"Error: {str(e)}"}, status_code=500)


@app.post("/admin/post-tweet")
async def admin_post_tweet(request: Request):
    pwd = request.query_params.get("pwd", request.headers.get("X-Admin-Token", ""))
    if pwd != config.ADMIN_PASSWORD:
        raise HTTPException(401)
    try:
        from automation.social_poster import run_social_posting
        run_social_posting()
        return JSONResponse({"message": "Tweet posted successfully"})
    except Exception as e:
        return JSONResponse({"message": f"Error: {str(e)}"}, status_code=500)


@app.post("/admin/save-affiliate-ids")
async def admin_save_affiliate_ids(request: Request):
    pwd = request.query_params.get("pwd", request.headers.get("X-Admin-Token", ""))
    if pwd != config.ADMIN_PASSWORD:
        raise HTTPException(401)
    try:
        body = await request.json()
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        # Read existing .env
        with open(env_path, "r") as f:
            lines = f.readlines()

        key_map = {
            "jasper":     "JASPER_AFFILIATE_ID",
            "copyai":     "COPYAI_AFFILIATE_ID",
            "surfer":     "SURFER_AFFILIATE_ID",
            "semrush":    "SEMRUSH_AFFILIATE_ID",
            "elevenlabs": "ELEVENLABS_AFFILIATE_ID",
            "pictory":    "PICTORY_AFFILIATE_ID",
            "writesonic": "WRITESONIC_AFFILIATE_ID",
            "invideo":    "INVIDEO_AFFILIATE_ID",
            "murf":        "MURF_AFFILIATE_ID",
            "descript":    "DESCRIPT_AFFILIATE_ID",
            "fireflies":   "FIREFLIES_AFFILIATE_ID",
            "speechify":   "SPEECHIFY_AFFILIATE_ID",
            "getresponse": "GETRESPONSE_AFFILIATE_ID",
            "hubspot":     "HUBSPOT_AFFILIATE_ID",
        }

        updated = set()
        new_lines = []
        for line in lines:
            replaced = False
            for tool_key, env_key in key_map.items():
                val = body.get(tool_key, "").strip()
                if val and line.startswith(f"{env_key}="):
                    new_lines.append(f"{env_key}={val}\n")
                    updated.add(tool_key)
                    replaced = True
                    break
            if not replaced:
                new_lines.append(line)

        # Add any keys not already in the file
        for tool_key, env_key in key_map.items():
            val = body.get(tool_key, "").strip()
            if val and tool_key not in updated:
                new_lines.append(f"{env_key}={val}\n")
                updated.add(tool_key)

        with open(env_path, "w") as f:
            f.writelines(new_lines)

        # Reload config
        from dotenv import load_dotenv
        from pathlib import Path
        load_dotenv(Path(env_path), override=True)

        return JSONResponse({"message": f"✅ Saved {len(updated)} affiliate ID(s). Links are now live — no restart needed!"})
    except Exception as e:
        return JSONResponse({"message": f"Error: {str(e)}"}, status_code=500)


@app.post("/admin/add-topic")
async def admin_add_topic(request: Request, topic: str = Form(...), keywords: str = Form(""), tool_focus: str = Form("")):
    pwd = request.query_params.get("pwd", request.headers.get("X-Admin-Token", ""))
    if pwd != config.ADMIN_PASSWORD:
        raise HTTPException(401)
    add_to_queue(topic, keywords, tool_focus or None, priority=9)
    return JSONResponse({"message": f"Topic queued: {topic}"})


@app.get("/admin/service-summary")
async def admin_service_summary(request: Request):
    pwd = request.query_params.get("pwd", request.headers.get("X-Admin-Token", ""))
    if pwd != config.ADMIN_PASSWORD:
        raise HTTPException(401)
    try:
        from automation.service_seller import get_mrr_summary, PACKAGES
        summary = get_mrr_summary()
        return JSONResponse({
            "mrr": summary["mrr"],
            "weekly_revenue": summary["weekly_revenue"],
            "active_clients": summary["active_clients"],
            "packages": {k: {"name": v["name"], "price": v["price_monthly"], "posts": v["posts_per_month"]} for k, v in PACKAGES.items()},
        })
    except Exception as e:
        return JSONResponse({"message": f"Error: {str(e)}"}, status_code=500)


@app.post("/admin/export-youtube-scripts")
async def admin_export_youtube(request: Request):
    pwd = request.query_params.get("pwd", request.headers.get("X-Admin-Token", ""))
    if pwd != config.ADMIN_PASSWORD:
        raise HTTPException(401)
    try:
        from automation.youtube_engine import export_all_scripts, VIDEO_TOPICS
        count = export_all_scripts()
        return JSONResponse({"message": f"Exported {count} YouTube video scripts to data/youtube_scripts/", "count": count})
    except Exception as e:
        return JSONResponse({"message": f"Error: {str(e)}"}, status_code=500)


@app.get("/admin/reddit-guide")
async def admin_reddit_guide(request: Request):
    pwd = request.query_params.get("pwd", request.headers.get("X-Admin-Token", ""))
    if pwd != config.ADMIN_PASSWORD:
        raise HTTPException(401)
    try:
        from automation.reddit_blitz import get_weekly_posting_schedule, get_karma_building_comments, POSTS
        schedule = get_weekly_posting_schedule()
        karma_comments = get_karma_building_comments()
        return JSONResponse({
            "message": "Reddit blitz guide loaded",
            "weekly_schedule": schedule,
            "karma_comments": karma_comments,
            "total_posts_available": len(POSTS),
            "target_subreddits": 17,
        })
    except Exception as e:
        return JSONResponse({"message": f"Error: {str(e)}"}, status_code=500)


# ── RSS Feed ──────────────────────────────────────────────────────────────────
@app.get("/rss.xml")
async def rss_feed():
    articles = get_articles(limit=20)
    items = ""
    for a in articles:
        items += f"""
        <item>
          <title><![CDATA[{a['title']}]]></title>
          <link>{config.SITE_URL}/articles/{a['slug']}</link>
          <description><![CDATA[{a['meta_description']}]]></description>
          <pubDate>{a['created_at']}</pubDate>
          <guid>{config.SITE_URL}/articles/{a['slug']}</guid>
        </item>"""
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>{config.SITE_NAME}</title>
    <link>{config.SITE_URL}</link>
    <description>{config.SITE_TAGLINE}</description>
    <language>en-us</language>
    {items}
  </channel>
</rss>"""
    from fastapi.responses import Response
    return Response(content=xml, media_type="application/rss+xml")


# ── Sitemap ───────────────────────────────────────────────────────────────────
@app.get("/sitemap.xml")
async def sitemap():
    from fastapi.responses import Response
    today = datetime.now().strftime("%Y-%m-%d")
    articles = get_articles(limit=999)
    urls = [
        f"<url><loc>{config.SITE_URL}/</loc><lastmod>{today}</lastmod><changefreq>daily</changefreq><priority>1.0</priority></url>",
        f"<url><loc>{config.SITE_URL}/tools</loc><lastmod>{today}</lastmod><changefreq>weekly</changefreq><priority>0.9</priority></url>",
        f"<url><loc>{config.SITE_URL}/articles</loc><lastmod>{today}</lastmod><changefreq>daily</changefreq><priority>0.9</priority></url>",
        # Best-of hub pages
        f"<url><loc>{config.SITE_URL}/best-ai-writing-tools</loc><lastmod>{today}</lastmod><changefreq>weekly</changefreq><priority>0.9</priority></url>",
        f"<url><loc>{config.SITE_URL}/best-ai-seo-tools</loc><lastmod>{today}</lastmod><changefreq>weekly</changefreq><priority>0.9</priority></url>",
        f"<url><loc>{config.SITE_URL}/best-ai-video-tools</loc><lastmod>{today}</lastmod><changefreq>weekly</changefreq><priority>0.9</priority></url>",
        f"<url><loc>{config.SITE_URL}/best-ai-voice-tools</loc><lastmod>{today}</lastmod><changefreq>weekly</changefreq><priority>0.9</priority></url>",
        f"<url><loc>{config.SITE_URL}/best-ai-productivity-tools</loc><lastmod>{today}</lastmod><changefreq>weekly</changefreq><priority>0.9</priority></url>",
        # Static pages
        f"<url><loc>{config.SITE_URL}/about</loc><changefreq>monthly</changefreq><priority>0.7</priority></url>",
        f"<url><loc>{config.SITE_URL}/how-we-test</loc><changefreq>monthly</changefreq><priority>0.7</priority></url>",
        f"<url><loc>{config.SITE_URL}/services</loc><changefreq>monthly</changefreq><priority>0.6</priority></url>",
        f"<url><loc>{config.SITE_URL}/contact</loc><changefreq>monthly</changefreq><priority>0.5</priority></url>",
    ]
    for a in articles:
        lastmod = (a.get("updated_at") or a.get("created_at") or today)[:10]
        urls.append(
            f"<url><loc>{config.SITE_URL}/articles/{a['slug']}</loc>"
            f"<lastmod>{lastmod}</lastmod><changefreq>monthly</changefreq><priority>0.8</priority></url>"
        )

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{''.join(urls)}
</urlset>"""
    return Response(content=xml, media_type="application/xml")


@app.get("/health")
async def health_check():
    """Used by Railway/Render for uptime monitoring."""
    try:
        stats = get_analytics_summary()
        return JSONResponse({
            "status": "ok",
            "articles": stats.get("articles", 0),
            "subscribers": stats.get("subscribers", 0),
            "total_views": stats.get("total_views", 0),
            "total_clicks": stats.get("total_clicks", 0),
            "uptime": "operational",
        })
    except Exception as e:
        return JSONResponse({"status": "degraded", "error": str(e)}, status_code=200)


@app.get("/robots.txt")
async def robots_txt():
    content = """User-agent: *
Allow: /
Disallow: /admin
Disallow: /track/

Sitemap: {site_url}/sitemap.xml""".format(site_url=config.SITE_URL)
    return Response(content=content, media_type="text/plain")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
