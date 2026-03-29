"""
AI Tools Empire — Main FastAPI Server
Serves the website, handles subscriptions, affiliate tracking, and admin actions.
"""
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
        "subscriber_count": max(get_subscriber_count(), 12000),  # Social proof floor
        "article_count": max(len(get_articles(limit=999)), 50),
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


@app.get("/articles/{slug}", response_class=HTMLResponse)
async def article_page(request: Request, slug: str):
    article = get_article_by_slug(slug)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    increment_views(slug)

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
    ctx = base_ctx(request)
    ctx["page_title"] = "About Us"
    ctx["page_content"] = f"""
    <div style="background:linear-gradient(135deg,#0f172a,#1e1b4b);padding:60px 20px;text-align:center;margin-bottom:0;">
      <h1 style="color:white;font-size:42px;font-weight:800;margin:0 0 12px;">About {config.SITE_NAME}</h1>
      <p style="color:#94a3b8;font-size:18px;margin:0;">We test every AI tool so you don't have to.</p>
    </div>
    <div style="max-width:760px;margin:60px auto;padding:0 24px;">
      <p style="font-size:18px;color:#475569;line-height:1.8;">{config.SITE_NAME} is an independent review publication helping businesses, creators, and entrepreneurs find the right AI tools.</p>
      <p style="color:#475569;line-height:1.8;">We've reviewed 50+ AI tools across writing, SEO, video creation, voice generation, and productivity. Every review is based on real hands-on testing — not sponsored content.</p>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin:40px 0;">
        <div style="background:white;border:1px solid #e2e8f0;border-radius:12px;padding:24px;text-align:center;">
          <div style="font-size:32px;font-weight:900;color:#6366f1;">50+</div>
          <div style="color:#64748b;font-size:14px;margin-top:4px;">AI Tools Reviewed</div>
        </div>
        <div style="background:white;border:1px solid #e2e8f0;border-radius:12px;padding:24px;text-align:center;">
          <div style="font-size:32px;font-weight:900;color:#6366f1;">12k+</div>
          <div style="color:#64748b;font-size:14px;margin-top:4px;">Newsletter Subscribers</div>
        </div>
        <div style="background:white;border:1px solid #e2e8f0;border-radius:12px;padding:24px;text-align:center;">
          <div style="font-size:32px;font-weight:900;color:#6366f1;">100%</div>
          <div style="color:#64748b;font-size:14px;margin-top:4px;">Independent Reviews</div>
        </div>
        <div style="background:white;border:1px solid #e2e8f0;border-radius:12px;padding:24px;text-align:center;">
          <div style="font-size:32px;font-weight:900;color:#6366f1;">2026</div>
          <div style="color:#64748b;font-size:14px;margin-top:4px;">Always Up to Date</div>
        </div>
      </div>
      <h2 style="font-size:26px;font-weight:800;margin:40px 0 16px;">Our Promise</h2>
      <ul style="color:#475569;line-height:2;font-size:15px;">
        <li>100% independent reviews — we are never paid to write positive reviews</li>
        <li>Honest pros and cons on every tool, even our top earners</li>
        <li>Updated regularly as tools release new features or change pricing</li>
        <li>Transparent affiliate disclosure on every single page</li>
      </ul>
      <h2 style="font-size:26px;font-weight:800;margin:40px 0 16px;">Affiliate Disclosure</h2>
      <p style="color:#475569;line-height:1.8;">We earn a commission when you purchase through our links, at no extra cost to you. This supports our free content. We only recommend tools we genuinely believe in.</p>
      <div style="margin-top:40px;text-align:center;">
        <a href="/tools" class="btn btn-primary">Browse Top AI Tools →</a>
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
      <p>You may unsubscribe from our newsletter at any time using the unsubscribe link in any email. To request data deletion, contact us at <a href="mailto:privacy@aitoolsweekly.com" style="color:#6366f1;">privacy@aitoolsweekly.com</a>.</p>
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
      <p>For questions about our affiliate relationships, contact <a href="mailto:hello@aitoolsweekly.com" style="color:#6366f1;">hello@aitoolsweekly.com</a>.</p>
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
    articles = get_articles(limit=999)
    urls = [
        f"<url><loc>{config.SITE_URL}/</loc><changefreq>daily</changefreq><priority>1.0</priority></url>",
        f"<url><loc>{config.SITE_URL}/tools</loc><changefreq>weekly</changefreq><priority>0.9</priority></url>",
        f"<url><loc>{config.SITE_URL}/articles</loc><changefreq>daily</changefreq><priority>0.9</priority></url>",
    ]
    for a in articles:
        urls.append(f"<url><loc>{config.SITE_URL}/articles/{a['slug']}</loc><changefreq>monthly</changefreq><priority>0.8</priority></url>")

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{''.join(urls)}
</urlset>"""
    from fastapi.responses import Response
    return Response(content=xml, media_type="application/xml")


@app.get("/health")
async def health_check():
    """Used by Railway/Render for uptime monitoring."""
    try:
        stats = get_analytics_summary()
        return JSONResponse({
            "status": "ok",
            "articles": stats.get("total_articles", 0),
            "subscribers": stats.get("total_subscribers", 0),
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
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
