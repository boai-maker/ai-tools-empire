"""
AI Tools Empire — Main FastAPI Server
Serves the website, handles subscriptions, affiliate tracking, and admin actions.
"""
import os
import time
import html as html_lib
import hashlib
import logging
from datetime import datetime
from contextlib import asynccontextmanager
from collections import defaultdict

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

# ── Rate Limiter (in-memory) ─────────────────────────────────────────────────
_rate_buckets: dict = defaultdict(list)

def _rate_limited(ip: str, bucket: str, max_requests: int, window_seconds: int) -> bool:
    """Return True if the IP has exceeded max_requests in the rolling window."""
    key = f"{bucket}:{ip}"
    now = time.time()
    cutoff = now - window_seconds
    _rate_buckets[key] = [t for t in _rate_buckets[key] if t > cutoff]
    if len(_rate_buckets[key]) >= max_requests:
        return True
    _rate_buckets[key].append(now)
    # Evict empty keys to prevent memory leak
    if len(_rate_buckets) > 10000:
        stale = [k for k, v in _rate_buckets.items() if not v]
        for k in stale:
            del _rate_buckets[k]
    return False

# ── Subscriber count cache ───────────────────────────────────────────────────
_sub_cache = {"count": 0, "expires": 0.0}

def get_subscriber_count_cached() -> int:
    if time.time() < _sub_cache["expires"]:
        return _sub_cache["count"]
    count = get_subscriber_count()
    _sub_cache.update(count=count, expires=time.time() + 300)
    return count

# ── App lifespan ──────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Add performance indexes
    try:
        import sqlite3
        db = sqlite3.connect("data.db")
        db.execute("CREATE INDEX IF NOT EXISTS idx_articles_slug ON articles(slug)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_articles_status_created ON articles(status, created_at DESC)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_subscribers_email ON subscribers(email)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_clicks_tool ON affiliate_clicks(tool_key)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_views_path ON page_views(path)")
        db.commit()
        db.close()
        log.info("DB indexes verified")
    except Exception as e:
        log.warning(f"Index creation skipped: {e}")
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

# Register A/B helper globals on the Jinja env.
# `ab()` in templates reads the visitor_id cookie set by the middleware and
# deterministically returns a variant for the given experiment.
import contextvars
_current_request_var: contextvars.ContextVar = contextvars.ContextVar("current_request", default=None)
try:
    from ab_testing import register_jinja as _register_ab_jinja
    _register_ab_jinja(templates, lambda: _current_request_var.get())
except ImportError:
    pass

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
    # Make current request visible to the Jinja `ab()` global (cookie read)
    _tok = _current_request_var.set(request)
    try:
        response = await call_next(request)
    finally:
        _current_request_var.reset(_tok)
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
    # Security headers
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

    # A/B testing — ensure every non-static request carries a visitor_id cookie
    if not path.startswith(("/static", "/track", "/favicon")):
        try:
            from ab_testing import ensure_visitor_id
            ensure_visitor_id(request, response)
        except Exception:
            pass

    return response

# ── Pages ─────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def homepage(request: Request):
    articles = get_articles(limit=6)

    # Prioritize active-earning affiliates above the fold. Fill remaining slots
    # with the rest in original order. Added 2026-04-21 — was previously just
    # the first 6 entries, which put most traffic on $0-earning programs.
    all_tools     = list(AFFILIATE_PROGRAMS.items())
    active_tools  = [(k, v) for k, v in all_tools if v.get("is_active")]
    other_tools   = [(k, v) for k, v in all_tools if not v.get("is_active")]
    featured      = active_tools + other_tools
    featured_dict = dict(featured[:6])

    ctx = base_ctx(request)
    ctx.update({
        "articles": articles,
        "featured_tools": featured_dict,
        "subscriber_count": get_subscriber_count_cached(),
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

    # Related articles — use hand-picked related_slugs first, fallback to same category
    import json as _json2
    related = []
    raw_related = article.get("related_slugs") or ""
    if raw_related:
        try:
            related_slug_list = _json2.loads(raw_related)[:4]
            from database.db import get_conn
            conn = get_conn()
            for rs in related_slug_list:
                row = conn.execute(
                    'SELECT slug, title, meta_description, category FROM articles WHERE slug=? AND status="published"',
                    (rs,)
                ).fetchone()
                if row:
                    related.append(dict(row))
            conn.close()
        except Exception:
            pass
    if not related:
        related = [
            a for a in get_articles(limit=10, category=article.get("category"))
            if a["slug"] != slug
        ][:4]

    # Parse faq_data for template schema rendering
    import json as _json
    faq_pairs = []
    raw_faq = article.get("faq_data") or ""
    if raw_faq:
        try:
            faq_pairs = _json.loads(raw_faq)
        except Exception:
            faq_pairs = []

    # Comparison table data (for vs/comparison articles)
    comparison_data = None
    try:
        from tools.comparison_generator import get_comparison_data
        comparison_data = get_comparison_data(slug)
    except Exception:
        pass

    ctx = base_ctx(request)
    ctx.update({
        "article": article,
        "featured_tool_data": featured_tool_data,
        "sidebar_tools": sidebar_tools,
        "related_articles": related,
        "faq_pairs": faq_pairs,
        "comparison": comparison_data,
    })
    return templates.TemplateResponse("article.html", ctx)


@app.get("/free-ai-kit", response_class=HTMLResponse)
async def free_ai_kit(request: Request):
    """Standalone lead magnet page — printable / saveable as PDF."""
    return templates.TemplateResponse("lead_magnet.html", {"request": request})


@app.get("/newsletter")
async def newsletter_redirect():
    """Orphan-link catch — ~30/day were hitting /newsletter and getting 404s.
    Redirect to the stack-audit lead magnet (better offer than a bare signup form)."""
    return RedirectResponse(url="/stack-audit", status_code=301)


@app.get("/ai-stack-calculator", response_class=HTMLResponse)
async def ai_stack_calculator(request: Request):
    """Interactive calculator — shareable tool that routes users to active-earner affiliates."""
    ctx = {"request": request, "site_name": config.SITE_NAME}
    return templates.TemplateResponse("ai-stack-calculator.html", ctx)


@app.get("/stack-audit", response_class=HTMLResponse)
async def stack_audit_page(request: Request):
    """Free AI stack audit lead magnet — user pastes tools, gets 3-line audit back."""
    # Record a click event for the hero CTA experiment if the user arrived via it
    try:
        exp = request.query_params.get("utm_exp")
        var = request.query_params.get("utm_var")
        if exp and var:
            from ab_testing import record_event, COOKIE_NAME
            vid = request.cookies.get(COOKIE_NAME, "")
            if vid:
                record_event(vid, exp, var, "click")
    except Exception:
        pass
    ctx = {"request": request, "site_name": config.SITE_NAME}
    return templates.TemplateResponse("stack-audit.html", ctx)


class StackAuditRequest(BaseModel):
    email:      str
    stack:      str
    surface:    str = "stack_audit_page"
    h1_variant: str = "control"


@app.post("/stack-audit/submit")
async def stack_audit_submit(request: Request, body: StackAuditRequest):
    """Receive a stack-audit submission. Stores to DB + alerts Telegram so Kenneth can reply."""
    if _rate_limited(ip_hash(request), "stack_audit", 5, 60):
        return JSONResponse({"success": False, "message": "Too many requests. Try again in a minute."}, status_code=429)

    email = body.email.lower().strip()
    stack = body.stack.strip()
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        return JSONResponse({"success": False, "message": "Invalid email"})
    if not stack or len(stack) < 10:
        return JSONResponse({"success": False, "message": "Please paste your actual stack"})

    try:
        import sqlite3
        conn = sqlite3.connect("data.db")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stack_audits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                stack TEXT NOT NULL,
                surface TEXT,
                ip_hash TEXT,
                status TEXT DEFAULT 'awaiting_payment',
                submitted_at TEXT DEFAULT CURRENT_TIMESTAMP,
                audited_at TEXT,
                paid_at TEXT,
                gumroad_sale_id TEXT,
                audit_json TEXT,
                delivered_at TEXT
            )
        """)
        cur = conn.execute(
            "INSERT INTO stack_audits (email, stack, surface, ip_hash, status) VALUES (?, ?, ?, ?, 'awaiting_payment')",
            (email, stack, body.surface, ip_hash(request)),
        )
        audit_id = cur.lastrowid
        # Also record in subscribers so they join the newsletter
        conn.execute(
            "INSERT OR IGNORE INTO subscribers (email, source) VALUES (?, ?)",
            (email, "stack_audit"),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        return JSONResponse({"success": False, "message": "Could not save. Please email directly."}, status_code=500)

    # Push to beehiiv with a stack-audit custom field so Kenneth can filter there.
    try:
        from integrations.beehiiv import subscribe as bh_subscribe
        bh_subscribe(
            email,
            utm_source="stack_audit",
            utm_medium="lead_magnet",
            referring_site="aitoolsempire.co",
            send_welcome_email=True,
            reactivate_existing=True,
            custom_fields={"stack_snapshot": stack[:1000]},  # first 1000 chars
        )
    except Exception as e:
        pass

    # Record signup events for active experiments this visitor is in
    try:
        from ab_testing import record_event, get_variant, COOKIE_NAME
        vid = request.cookies.get(COOKIE_NAME, "")
        if vid:
            # hero-cta-v1 (homepage CTA copy)
            hero_variant = get_variant(vid, "hero-cta-v1", ["control", "money_savings"], record_assignment=False)
            record_event(vid, "hero-cta-v1", hero_variant, "signup")
            # stack-audit-h1-v1 (headline variant rendered on this page)
            if body.h1_variant in ("control", "audit_framing", "worth_it_q"):
                record_event(vid, "stack-audit-h1-v1", body.h1_variant, "signup")
    except Exception:
        pass

    # Telegram heads-up (non-blocking — best-effort)
    try:
        import requests as _rq
        tok  = os.getenv("DOMINIC_TELEGRAM_TOKEN", "")
        chat = os.getenv("DOMINIC_TELEGRAM_CHAT_ID", "")
        if tok and chat:
            msg = f"🔍 New stack audit from {email}\n\nStack:\n{stack[:500]}"
            _rq.post(
                f"https://api.telegram.org/bot{tok}/sendMessage",
                json={"chat_id": chat, "text": msg},
                timeout=4,
            )
    except Exception:
        pass

    payment_url = os.getenv("STACK_AUDIT_PAYMENT_URL", "")
    return JSONResponse({
        "success": True,
        "audit_id": audit_id,
        "payment_url": payment_url,
        "price": 99,
        "message": "Submission saved. Complete your payment to start the audit.",
    })


# ─────────── UNIFIED GUMROAD DISPATCHER ──────────────────────────
#
# Gumroad has ONE global ping URL per account, so as we add products
# (Stack Audit $99, Affiliate Service $29, Pipeline Hunter $47, future...)
# we route by `product_permalink` from the form payload. The legacy
# per-product endpoints below stay as backwards-compatible aliases.

# product slug → (handler-name, marker function path)
GUMROAD_PRODUCT_HANDLERS = {
    "euvbhm": "stack_audit",            # $99 Stack Audit
    "jpsrxd": "affiliate_service",      # $29 AI Affiliate Application Service
    "bfapw":  "pipeline_hunter",        # $47 Pipeline Hunter (no auto-fulfilment yet)
    "qszeoy": "stack_audit_templates",  # $19 Stack Audit Template Pack
}


@app.post("/gumroad-webhook")
async def gumroad_unified_webhook(request: Request):
    """Single Gumroad ping URL for ALL products. Routes by
    `product_permalink` (or `permalink`/`product_id`) so adding a new
    Gumroad product never requires updating the ping URL again.

    Configure ONCE at gumroad.com/settings/advanced → Ping endpoint:
        https://aitoolsempire.co/gumroad-webhook
    """
    from fastapi.responses import JSONResponse
    try:
        form = await request.form()
        data = dict(form)
        email = (data.get("email") or "").lower().strip()
        sale_id = data.get("sale_id") or ""
        permalink = (data.get("product_permalink") or data.get("permalink") or "").strip()
        product_id = (data.get("product_id") or "").strip()

        # Optional shared-secret check (set GUMROAD_WEBHOOK_SECRET in env
        # AND configure the same value on Gumroad's per-product webhook).
        expected_secret = os.getenv("GUMROAD_WEBHOOK_SECRET", "")
        got_secret = (
            request.headers.get("X-Gumroad-Signature")
            or data.get("url_params[secret]")
            or data.get("secret") or ""
        )
        if expected_secret and got_secret != expected_secret:
            return JSONResponse({"ok": False, "error": "signature mismatch"}, status_code=401)

        if not email:
            return JSONResponse({"ok": False, "error": "missing email"}, status_code=400)

        # Extract slug from permalink. Gumroad sends a URL like
        # https://bosaibot.gumroad.com/l/jpsrxd OR just the slug "jpsrxd".
        slug = permalink.rstrip("/").rsplit("/", 1)[-1]
        handler = GUMROAD_PRODUCT_HANDLERS.get(slug)

        log.info(f"gumroad ping email={email} slug={slug!r} sale_id={sale_id} handler={handler!r}")

        if handler == "stack_audit":
            from bots.stack_audit_engine import mark_paid_by_email
            n = mark_paid_by_email(email, gumroad_sale_id=sale_id)
            _telegram(f"💰 PAID Stack Audit ($99): {email} (sale {sale_id})")
            return JSONResponse({"ok": True, "product": "stack_audit", "marked_paid": n})

        if handler == "affiliate_service":
            import sqlite3
            conn = sqlite3.connect("data.db")
            cur = conn.execute(
                """UPDATE affiliate_service_orders
                   SET status='paid', paid_at=CURRENT_TIMESTAMP, gumroad_sale_id=?
                   WHERE email=? AND status='awaiting_payment'""",
                (sale_id, email),
            )
            n = cur.rowcount
            conn.commit()
            conn.close()
            _telegram(f"💰 PAID Affiliate Service ($29): {email} (sale {sale_id})")
            return JSONResponse({"ok": True, "product": "affiliate_service", "marked_paid": n})

        if handler == "pipeline_hunter":
            # No DB table yet — just log + Telegram so Kenneth knows to ship the file.
            _telegram(f"💰 PAID Pipeline Hunter ($47): {email} (sale {sale_id})")
            return JSONResponse({"ok": True, "product": "pipeline_hunter", "marked_paid": 0})

        if handler == "stack_audit_templates":
            # $19 self-serve template pack — Gumroad delivers the markdown
            # file natively, we just log + ping Kenneth so he can see sales.
            _telegram(f"💰 PAID Stack Audit Template Pack ($19): {email} (sale {sale_id})")
            return JSONResponse({"ok": True, "product": "stack_audit_templates", "marked_paid": 0})

        # Unknown product — alert Kenneth so he can wire a handler.
        _telegram(f"⚠️ Unrouted Gumroad sale: slug={slug!r} email={email} sale={sale_id}")
        return JSONResponse({"ok": True, "product": "unknown", "slug": slug, "marked_paid": 0})

    except Exception as e:
        log.exception("gumroad_unified_webhook failed")
        return JSONResponse({"ok": False, "error": str(e)[:200]}, status_code=500)


def _telegram(msg: str) -> None:
    """Best-effort Telegram ping — never raises."""
    try:
        import requests as _rq
        tok  = os.getenv("DOMINIC_TELEGRAM_TOKEN", "")
        chat = os.getenv("DOMINIC_TELEGRAM_CHAT_ID", "")
        if tok and chat:
            _rq.post(
                f"https://api.telegram.org/bot{tok}/sendMessage",
                json={"chat_id": chat, "text": msg},
                timeout=4,
            )
    except Exception:
        pass


@app.post("/stack-audit/gumroad-webhook")
async def stack_audit_gumroad_webhook(request: Request):
    """
    LEGACY alias. Gumroad ping URL should now point to /gumroad-webhook
    which dispatches across all products. This endpoint is kept for
    backwards compatibility with the original $99 Stack Audit setup.
    """
    from fastapi.responses import JSONResponse
    try:
        form = await request.form()
        data = dict(form)
        email = (data.get("email") or "").lower().strip()
        sale_id = data.get("sale_id") or ""
        expected_secret = os.getenv("GUMROAD_WEBHOOK_SECRET", "")
        got_secret = request.headers.get("X-Gumroad-Signature") or data.get("url_params[secret]") or data.get("secret") or ""
        if expected_secret and got_secret != expected_secret:
            return JSONResponse({"ok": False, "error": "signature mismatch"}, status_code=401)
        if not email:
            return JSONResponse({"ok": False, "error": "missing email"}, status_code=400)
        from bots.stack_audit_engine import mark_paid_by_email
        n = mark_paid_by_email(email, gumroad_sale_id=sale_id)
        return JSONResponse({"ok": True, "marked_paid": n})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)[:200]}, status_code=500)


@app.post("/admin/stack-audit/{audit_id}/mark-paid")
async def admin_mark_audit_paid(audit_id: int, request: Request):
    from fastapi.responses import JSONResponse
    pwd = request.query_params.get("pwd", "")
    if pwd != os.getenv("ADMIN_PASSWORD", ""):
        return JSONResponse({"ok": False, "error": "bad pwd"}, status_code=403)
    from bots.stack_audit_engine import mark_paid
    ok = mark_paid(audit_id, gumroad_sale_id="manual_admin")
    return JSONResponse({"ok": ok, "audit_id": audit_id})


@app.post("/admin/stack-audit/run-pending")
async def admin_run_pending_audits(request: Request):
    """Fire the audit engine immediately (for testing / manual kick)."""
    from fastapi.responses import JSONResponse
    pwd = request.query_params.get("pwd", "")
    if pwd != os.getenv("ADMIN_PASSWORD", ""):
        return JSONResponse({"ok": False, "error": "bad pwd"}, status_code=403)
    from bots.stack_audit_engine import run_pending_audits
    return JSONResponse({"ok": True, **run_pending_audits(limit=10)})


# ─────────── $29 AI TOOL APPLICATION SERVICE ──────────────────────
#
# Productizes Kenneth's affiliate_autopilot pain. Customer pays $29, we apply
# them to ~30 vetted AI affiliate programs on their behalf using the Playwright
# co-pilot already at bots/affiliate_autopilot.py.
#
# Lifecycle: form submit → 'awaiting_payment' → Gumroad webhook flips to 'paid'
# → Kenneth manually batches the applications (or future bot mode does).


class AffiliateServiceRequest(BaseModel):
    email:               str
    name:                str = ""
    site_url:            str
    niche:               str = ""
    audience_size:       str = ""        # free text, e.g. "5K newsletter, 12K twitter"
    monthly_visitors:    str = ""
    promotional_methods: str = ""
    current_affiliates:  str = ""
    notes:               str = ""
    surface:             str = "affiliate_service_page"


@app.get("/affiliate-service", response_class=HTMLResponse)
async def affiliate_service_page(request: Request):
    """Landing page + signup form for the $29 affiliate-application service."""
    payment_url = os.getenv("AFFILIATE_SERVICE_PAYMENT_URL", "")
    ctx = {
        "request": request,
        "payment_url": payment_url,
        "price": 29,
    }
    return templates.TemplateResponse("affiliate-service.html", ctx)


@app.post("/affiliate-service/submit")
async def affiliate_service_submit(request: Request, body: AffiliateServiceRequest):
    """Receive an order. Saves to DB, alerts Telegram, returns the Gumroad
    payment URL. Webhook flips status to 'paid' on Gumroad sale."""
    if _rate_limited(ip_hash(request), "affiliate_service", 5, 60):
        return JSONResponse({"success": False, "message": "Too many requests."}, status_code=429)

    email = body.email.lower().strip()
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        return JSONResponse({"success": False, "message": "Invalid email"})
    if not body.site_url or "." not in body.site_url:
        return JSONResponse({"success": False, "message": "Site URL required"})

    try:
        import sqlite3, json as _json
        conn = sqlite3.connect("data.db")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS affiliate_service_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                name TEXT,
                site_url TEXT NOT NULL,
                niche TEXT,
                audience_size TEXT,
                monthly_visitors TEXT,
                promotional_methods TEXT,
                current_affiliates TEXT,
                notes TEXT,
                surface TEXT,
                ip_hash TEXT,
                status TEXT DEFAULT 'awaiting_payment',
                submitted_at TEXT DEFAULT CURRENT_TIMESTAMP,
                paid_at TEXT,
                gumroad_sale_id TEXT,
                applications_started_at TEXT,
                applications_finished_at TEXT,
                applications_log TEXT,
                report_sent_at TEXT,
                nudged_at TEXT
            )
        """)
        cur = conn.execute(
            """INSERT INTO affiliate_service_orders
               (email, name, site_url, niche, audience_size, monthly_visitors,
                promotional_methods, current_affiliates, notes, surface, ip_hash, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'awaiting_payment')""",
            (email, body.name.strip(), body.site_url.strip(), body.niche.strip(),
             body.audience_size.strip(), body.monthly_visitors.strip(),
             body.promotional_methods.strip(), body.current_affiliates.strip(),
             body.notes.strip(), body.surface, ip_hash(request)),
        )
        order_id = cur.lastrowid
        conn.execute(
            "INSERT OR IGNORE INTO subscribers (email, name, source) VALUES (?, ?, ?)",
            (email, body.name.strip(), "affiliate_service"),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        return JSONResponse({"success": False, "message": "Could not save order."}, status_code=500)

    # Beehiiv push (single source of truth for newsletter list)
    try:
        from integrations.beehiiv import subscribe as bh_subscribe
        bh_subscribe(
            email,
            utm_source="affiliate_service",
            utm_medium="paid_product",
            referring_site="aitoolsempire.co",
            send_welcome_email=True,
            reactivate_existing=True,
            custom_fields={"affiliate_service_site": body.site_url[:200]},
        )
    except Exception:
        pass

    # Telegram heads-up so Kenneth knows a paying customer is incoming
    try:
        import requests as _rq
        tok  = os.getenv("DOMINIC_TELEGRAM_TOKEN", "")
        chat = os.getenv("DOMINIC_TELEGRAM_CHAT_ID", "")
        if tok and chat:
            msg = (f"💼 New $29 Affiliate Service order from {email}\n"
                   f"Site: {body.site_url}\n"
                   f"Niche: {body.niche or '—'}\n"
                   f"Audience: {body.audience_size or '—'}\n"
                   f"Status: awaiting_payment (id={order_id})")
            _rq.post(
                f"https://api.telegram.org/bot{tok}/sendMessage",
                json={"chat_id": chat, "text": msg},
                timeout=4,
            )
    except Exception:
        pass

    payment_url = os.getenv("AFFILIATE_SERVICE_PAYMENT_URL", "")
    return JSONResponse({
        "success": True,
        "order_id": order_id,
        "payment_url": payment_url,
        "price": 29,
        "message": "Order saved. Complete payment and we start applying within 48 hours.",
    })


@app.post("/affiliate-service/gumroad-webhook")
async def affiliate_service_gumroad_webhook(request: Request):
    """Flip the most recent awaiting_payment order for this email to 'paid'."""
    try:
        form = await request.form()
        data = dict(form)
        email = (data.get("email") or "").lower().strip()
        sale_id = data.get("sale_id") or ""
        expected_secret = os.getenv("GUMROAD_WEBHOOK_SECRET", "")
        got_secret = request.headers.get("X-Gumroad-Signature") or data.get("url_params[secret]") or data.get("secret") or ""
        if expected_secret and got_secret != expected_secret:
            return JSONResponse({"ok": False, "error": "signature mismatch"}, status_code=401)
        if not email:
            return JSONResponse({"ok": False, "error": "missing email"}, status_code=400)

        import sqlite3
        conn = sqlite3.connect("data.db")
        cur = conn.execute(
            """UPDATE affiliate_service_orders
               SET status='paid', paid_at=CURRENT_TIMESTAMP, gumroad_sale_id=?
               WHERE email = ? AND status = 'awaiting_payment'""",
            (sale_id, email),
        )
        marked = cur.rowcount
        conn.commit()
        conn.close()

        # Tell Kenneth so he can start applying or the bot mode (Phase 2) can fire
        try:
            import requests as _rq
            tok  = os.getenv("DOMINIC_TELEGRAM_TOKEN", "")
            chat = os.getenv("DOMINIC_TELEGRAM_CHAT_ID", "")
            if tok and chat and marked:
                _rq.post(
                    f"https://api.telegram.org/bot{tok}/sendMessage",
                    json={"chat_id": chat,
                          "text": f"💰 PAID $29 Affiliate Service: {email}. Start applying. Sale {sale_id}."},
                    timeout=4,
                )
        except Exception:
            pass

        return JSONResponse({"ok": True, "marked_paid": marked})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)[:200]}, status_code=500)


# ─────────── $19 STACK AUDIT TEMPLATE PACK ──────────────────────
#
# Pure self-serve digital product. Gumroad delivers the markdown file.
# We just host the landing page + slot in the dispatcher.


@app.get("/stack-audit-templates", response_class=HTMLResponse)
async def stack_audit_templates_page(request: Request):
    payment_url = os.getenv("STACK_AUDIT_TEMPLATES_PAYMENT_URL", "")
    return templates.TemplateResponse("stack-audit-templates.html", {
        "request": request,
        "payment_url": payment_url,
        "price": 19,
    })


@app.get("/pipeline-hunter", response_class=HTMLResponse)
async def pipeline_hunter_page(request: Request):
    """$47 Pipeline Hunter landing — was a 404 before today's audit. Was the
    biggest revenue leak: traffic from Indie Hackers / Show HN / Product Hunt
    posts hit a dead end."""
    payment_url = os.getenv("PIPELINE_HUNTER_PAYMENT_URL",
                            "https://bosaibot.gumroad.com/l/bfapw")
    return templates.TemplateResponse("pipeline-hunter.html", {
        "request": request,
        "payment_url": payment_url,
        "price": 47,
    })


# ─────────── ADMIN: cleanup test rows ──────────────────────────────


@app.post("/admin/stack-audits/delete")
async def admin_delete_stack_audits(request: Request):
    """Delete stack_audits rows by email pattern. Cleanup for test rows
    accumulated during deploy probes."""
    pwd = request.query_params.get("pwd", "")
    if pwd != os.getenv("ADMIN_PASSWORD", ""):
        return JSONResponse({"ok": False, "error": "bad pwd"}, status_code=403)
    body = await request.json()
    pattern = (body.get("email_like") or "").strip()
    if not pattern or "%" not in pattern:
        return JSONResponse(
            {"ok": False, "error": "email_like required and must contain % wildcard"},
            status_code=400,
        )
    import sqlite3
    conn = sqlite3.connect("data.db")
    try:
        cur = conn.execute("DELETE FROM stack_audits WHERE email LIKE ?", (pattern,))
        n = cur.rowcount
        conn.commit()
        return JSONResponse({"ok": True, "pattern": pattern, "stack_audits_deleted": n})
    finally:
        conn.close()


@app.post("/admin/affiliate-service/delete")
async def admin_delete_affiliate_service_orders(request: Request):
    """Delete affiliate_service_orders rows by email pattern. Kenneth-only.
    Used to clean up test rows like 'deploycheck1@aitoolsempire.co' that
    accumulate during deploy probes. Body: {"email_like": "deploycheck%"}"""
    pwd = request.query_params.get("pwd", "")
    if pwd != os.getenv("ADMIN_PASSWORD", ""):
        return JSONResponse({"ok": False, "error": "bad pwd"}, status_code=403)
    body = await request.json()
    pattern = (body.get("email_like") or "").strip()
    if not pattern or "%" not in pattern:
        return JSONResponse(
            {"ok": False, "error": "email_like required and must contain % wildcard"},
            status_code=400,
        )
    import sqlite3
    conn = sqlite3.connect("data.db")
    try:
        cur = conn.execute(
            "DELETE FROM affiliate_service_orders WHERE email LIKE ?",
            (pattern,),
        )
        affiliate_n = cur.rowcount
        cur2 = conn.execute(
            "DELETE FROM subscribers WHERE email LIKE ? AND source LIKE 'affiliate_service%'",
            (pattern,),
        )
        sub_n = cur2.rowcount
        conn.commit()
        return JSONResponse({
            "ok": True,
            "pattern": pattern,
            "affiliate_service_orders_deleted": affiliate_n,
            "subscribers_deleted": sub_n,
        })
    finally:
        conn.close()


@app.get("/admin/affiliate-service")
async def admin_list_affiliate_service(request: Request):
    """Admin view of all $29 service orders."""
    pwd = request.query_params.get("pwd", "")
    if pwd != os.getenv("ADMIN_PASSWORD", ""):
        return JSONResponse({"ok": False, "error": "bad pwd"}, status_code=403)
    import sqlite3
    conn = sqlite3.connect("data.db")
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """SELECT id, email, name, site_url, niche, status,
                      submitted_at, paid_at, applications_finished_at, report_sent_at
               FROM affiliate_service_orders
               ORDER BY id DESC LIMIT 100"""
        ).fetchall()
        return JSONResponse({"ok": True, "orders": [dict(r) for r in rows]})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)[:200]}, status_code=500)
    finally:
        conn.close()


# ─────────── ADMIN: Stack Audit list ──────────────────────────────


@app.get("/admin/stack-audits")
async def admin_list_audits(request: Request):
    """Admin view: all stack audit submissions."""
    from fastapi.responses import JSONResponse
    pwd = request.query_params.get("pwd", "")
    if pwd != os.getenv("ADMIN_PASSWORD", ""):
        return JSONResponse({"ok": False, "error": "bad pwd"}, status_code=403)
    import sqlite3
    conn = sqlite3.connect("data.db")
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, email, substr(stack, 1, 200) AS stack_preview, status, submitted_at, paid_at, delivered_at "
        "FROM stack_audits ORDER BY id DESC LIMIT 50"
    ).fetchall()
    conn.close()
    return JSONResponse({"ok": True, "audits": [dict(r) for r in rows]})


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


class ContactRequest(BaseModel):
    name: str
    email: str
    subject: str = "general"
    message: str

@app.post("/contact")
async def contact_submit(request: Request, body: ContactRequest):
    # Rate limit: 3 per hour per IP
    if _rate_limited(ip_hash(request), "contact", 3, 3600):
        return JSONResponse({"success": False, "message": "Too many messages. Please try again later."}, status_code=429)

    name = html_lib.escape(body.name.strip()[:100])
    email = body.email.lower().strip()
    subject = html_lib.escape(body.subject.strip()[:100])
    message = html_lib.escape(body.message.strip()[:5000])

    if not name or not email or "@" not in email or not message:
        return JSONResponse({"success": False, "message": "Please fill in all fields."})

    # Build and send email to site owner
    html_body = f"""
    <div style="font-family:-apple-system,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
      <h2 style="color:#6366f1;">New Contact Form Submission</h2>
      <table style="width:100%;border-collapse:collapse;">
        <tr><td style="padding:8px;font-weight:600;color:#64748b;">From:</td><td style="padding:8px;">{name} &lt;{email}&gt;</td></tr>
        <tr><td style="padding:8px;font-weight:600;color:#64748b;">Subject:</td><td style="padding:8px;">{subject}</td></tr>
      </table>
      <hr style="border:1px solid #e2e8f0;margin:16px 0;">
      <div style="white-space:pre-wrap;line-height:1.6;">{message}</div>
      <hr style="border:1px solid #e2e8f0;margin:16px 0;">
      <p style="font-size:12px;color:#94a3b8;">Sent from {config.SITE_NAME} contact form</p>
    </div>
    """
    try:
        from automation.email_sender import _send_via_resend, _send_via_smtp
        sent = False
        if hasattr(config, 'RESEND_API_KEY') and config.RESEND_API_KEY:
            sent = _send_via_resend([config.SMTP_USER or "bosaibot@gmail.com"], f"[Contact] {subject} — {name}", html_body)
        if not sent:
            sent = _send_via_smtp([config.SMTP_USER or "bosaibot@gmail.com"], f"[Contact] {subject} — {name}", html_body)
        if sent:
            log.info(f"Contact form sent from {email} re: {subject}")
            return JSONResponse({"success": True, "message": "Message sent! We'll reply within 24 hours."})
        else:
            log.error(f"Contact form email failed for {email}")
            return JSONResponse({"success": False, "message": "Email delivery failed. Please try again."})
    except Exception as e:
        log.error(f"Contact form error: {e}")
        return JSONResponse({"success": False, "message": "Something went wrong. Please email us directly."})


@app.get("/services", response_class=HTMLResponse)
async def services_page(request: Request):
    ctx = base_ctx(request)
    return templates.TemplateResponse("services.html", ctx)


@app.get("/resume", response_class=HTMLResponse)
async def resume_service_page(request: Request):
    """Free resume review landing page — leads into $49 rewrite service."""
    resume_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "resume-landing.html")
    try:
        return HTMLResponse(open(resume_path).read())
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Resume page not found")


# ── API Endpoints ─────────────────────────────────────────────────────────────

class SubscribeRequest(BaseModel):
    email: str
    name: str = ""
    source: str = "website"

@app.post("/subscribe")
async def subscribe(request: Request, body: SubscribeRequest):
    # Rate limit: 5 per minute per IP
    if _rate_limited(ip_hash(request), "subscribe", 5, 60):
        return JSONResponse({"success": False, "message": "Too many requests. Try again in a minute."}, status_code=429)

    email = body.email.lower().strip()
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        return JSONResponse({"success": False, "message": "Invalid email"})

    # Block obviously fake/disposable domains
    _blocked_domains = {"fake.com", "test.com", "example.com", "mailinator.com", "tempmail.com", "throwaway.email", "guerrillamail.com", "sharklasers.com"}
    domain = email.split("@")[-1]
    if domain in _blocked_domains:
        return JSONResponse({"success": False, "message": "Please use a real email address."})

    added = add_subscriber(email, body.name, source=body.source or "website")

    # Push to beehiiv so the welcome + drip fires from there (single source of truth).
    # Fire-and-forget — we still track signup locally even if beehiiv is down.
    try:
        from integrations.beehiiv import subscribe as bh_subscribe
        bh_subscribe(
            email,
            utm_source=body.source or "website",
            utm_medium="organic",
            referring_site="aitoolsempire.co",
            send_welcome_email=True,
            reactivate_existing=True,
        )
    except Exception as e:
        log.warning(f"beehiiv push failed for {email}: {e}")

    if not added:
        return JSONResponse({"success": True, "message": "Already subscribed!"})

    # Legacy local sequence (will be retired once beehiiv welcome is dialed in;
    # running both briefly ensures no signup gets silence).
    try:
        from automation.sequences.runner import send_sequence_email
        send_sequence_email(email, body.name or "there", seq_num=1)
    except Exception as e:
        log.warning(f"Sequence email 1 failed: {e}")

    try:
        from database.db import enqueue_sequence
        enqueue_sequence(email, body.name or "")
    except Exception as e:
        log.warning(f"Sequence queue failed: {e}")

    return JSONResponse({"success": True, "message": "Subscribed! Check your inbox."})


@app.post("/track/click/{tool_key}")
async def track_click(tool_key: str, request: Request, source: str = ""):
    # Rate limit: 30 per minute per IP
    if _rate_limited(ip_hash(request), "track", 30, 60):
        return JSONResponse({"ok": True})
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
        "murf":       os.getenv("MURF_AFFILIATE_URL", f"https://get.murf.ai/{os.getenv('MURF_AFFILIATE_ID', '')}"),
        "elevenlabs": f"https://elevenlabs.io/?from={os.getenv('ELEVENLABS_AFFILIATE_ID', '')}",
        "descript":   f"https://www.descript.com/affiliates?ref={os.getenv('DESCRIPT_AFFILIATE_ID', '')}",
        "fireflies":   f"https://fireflies.ai/?fpr={os.getenv('FIREFLIES_AFFILIATE_ID', '')}",
        "speechify":   f"https://speechify.com/affiliate/?ref={os.getenv('SPEECHIFY_AFFILIATE_ID', '')}",
        "getresponse": f"https://www.getresponse.com/?a={os.getenv('GETRESPONSE_AFFILIATE_ID', '')}",
        "hubspot":     f"https://www.hubspot.com/?hubs_signup-cta={os.getenv('HUBSPOT_AFFILIATE_ID', '')}",
        "quillbot":    f"https://quillbot.com/?utm_source=affiliate&ref={os.getenv('QUILLBOT_AFFILIATE_ID', '')}",
        "kit":         f"https://kit.com/?ref={os.getenv('KIT_AFFILIATE_ID', '')}",
        "webflow":     f"https://webflow.com/r/{os.getenv('WEBFLOW_AFFILIATE_ID', '')}",
        "grammarly":   f"https://www.grammarly.com/referrals/{os.getenv('GRAMMARLY_AFFILIATE_ID', '')}",
        "canva":       f"https://partner.canva.com/{os.getenv('CANVA_AFFILIATE_ID', '')}",
        "synthesia":   f"https://www.synthesia.io/?via={os.getenv('SYNTHESIA_AFFILIATE_ID', '')}",
        "runway":      f"https://runwayml.com/?ref={os.getenv('RUNWAY_AFFILIATE_ID', '')}",
        "fliki":       f"https://fliki.ai/?via={os.getenv('FLIKI_AFFILIATE_ID', '')}",
        "rytr":        f"https://rytr.me/?via={os.getenv('RYTR_AFFILIATE_ID', '')}",
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
        "webflow": "https://webflow.com/", "grammarly": "https://www.grammarly.com/",
        "canva": "https://www.canva.com/", "synthesia": "https://www.synthesia.io/",
        "runway": "https://runwayml.com/", "fliki": "https://fliki.ai/",
        "rytr": "https://rytr.me/",
    }
    if tool_key not in aff_url_map:
        raise HTTPException(status_code=404, detail=f"Unknown tool: {tool_key}")

    # WHITELIST of programs we are CONFIRMED-active in. Audit 2026-04-27 found
    # ~85% of 444 lifetime clicks went to programs with no real ID — the
    # merchant strips empty/bogus refs and we never get attribution. From now
    # on: anything not in this set → waitlist (captures email + offers active
    # alternative). Add a key here ONLY after the program has paid out at
    # least once or sent an explicit "you're approved" email.
    ACTIVE_AFFILIATES = {"rytr", "fliki", "pictory", "elevenlabs", "fireflies", "murf"}

    aff_id = os.getenv(f"{tool_key.upper()}_AFFILIATE_ID", "")
    try:
        source = request.headers.get("referer", "direct")
        log_click(tool_key, source, ip_hash(request))
    except Exception:
        pass

    if tool_key not in ACTIVE_AFFILIATES:
        # Inactive program — capture lead instead of leaking the click.
        return RedirectResponse(url=f"/waitlist/{tool_key}", status_code=302)

    # Active program — go to merchant. Append UTM so attribution survives
    # even when the affiliate cookie/referer is stripped.
    def _with_utm(url: str) -> str:
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}utm_source=ate&utm_medium={tool_key}&utm_campaign=affiliate"

    if aff_id and aff_id.startswith("http"):
        return RedirectResponse(url=_with_utm(aff_id), status_code=302)
    if aff_id and not aff_id.startswith("YOUR"):
        return RedirectResponse(url=_with_utm(aff_url_map[tool_key]), status_code=302)
    # Whitelisted but no ID configured — still go to waitlist rather than
    # leaking. (Shouldn't happen if .env is right.)
    return RedirectResponse(url=f"/waitlist/{tool_key}", status_code=302)


# Category → best monetized alternative (for waitlist upsell).
_WAITLIST_ALT_BY_CATEGORY = {
    "video": "pictory",
    "audio": "elevenlabs",
    "productivity": "fireflies",
    # writing/seo/etc. — no monetized alternative yet, just email capture
}


@app.get("/waitlist/{tool_key}", response_class=HTMLResponse)
async def waitlist_page(tool_key: str, request: Request):
    """Shown instead of redirecting to an unattributed merchant link. Captures
    email and offers a monetized alternative in the same category."""
    from affiliate.links import AFFILIATE_PROGRAMS
    tool_meta = AFFILIATE_PROGRAMS.get(tool_key, {})
    tool_name = tool_meta.get("name") or tool_key.replace("_", " ").title()
    category = tool_meta.get("category", "")
    alt = None
    alt_key = _WAITLIST_ALT_BY_CATEGORY.get(category)
    if alt_key and alt_key != tool_key:
        alt_meta = AFFILIATE_PROGRAMS.get(alt_key, {})
        if alt_meta.get("is_active") is True:
            alt = {
                "key": alt_key,
                "name": alt_meta.get("name", alt_key),
                "description": alt_meta.get("description", ""),
            }
    ctx = base_ctx(request)
    ctx.update({
        "tool_key": tool_key,
        "tool_name": tool_name,
        "alt_tool": alt,
    })
    return templates.TemplateResponse("waitlist.html", ctx)


@app.post("/waitlist/{tool_key}/subscribe")
async def waitlist_subscribe(tool_key: str, request: Request):
    from fastapi.responses import JSONResponse
    try:
        payload = await request.json()
        email_addr = (payload.get("email") or "").strip().lower()
        if "@" not in email_addr or "." not in email_addr:
            return JSONResponse({"ok": False, "error": "Invalid email"}, status_code=400)
        add_subscriber(email_addr, name="", source=f"waitlist_{tool_key}")
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)[:120]}, status_code=500)


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

def _admin_authed(request: Request) -> bool:
    """Check if admin is authenticated via cookie or query param (legacy fallback)."""
    cookie_token = request.cookies.get("admin_session")
    if cookie_token and cookie_token == hashlib.sha256(config.ADMIN_PASSWORD.encode()).hexdigest():
        return True
    # Legacy fallback: query param (will be removed in future)
    pwd = request.query_params.get("pwd", "")
    return pwd == config.ADMIN_PASSWORD


@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    if not _admin_authed(request):
        # Dark-themed login form using POST (password in body, not URL)
        html = """<!DOCTYPE html><html><head>
        <meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
        <link rel="stylesheet" href="/static/css/design-system.css">
        <title>Admin Login</title></head>
        <body style='font-family:var(--font-family);display:flex;align-items:center;justify-content:center;height:100vh;background:var(--color-bg-base);'>
        <form method='post' action='/admin/login' style='text-align:center;background:var(--color-bg-card);padding:40px;border-radius:14px;border:1px solid var(--color-border);box-shadow:var(--shadow-lg);'>
          <h2 style='margin:0 0 20px;color:var(--color-text-primary);font-weight:800;'>🔐 Admin Login</h2>
          <input name='pwd' type='password' placeholder='Password' autocomplete='current-password'
            style='padding:12px 18px;border-radius:8px;border:1px solid var(--color-border);font-size:15px;width:240px;margin-bottom:12px;display:block;background:var(--color-bg-elevated);color:var(--color-text-primary);outline:none;'>
          <button type='submit' style='background:var(--color-primary);color:white;border:none;padding:12px 28px;border-radius:8px;font-size:15px;font-weight:600;cursor:pointer;width:100%;'>Login</button>
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
    response = templates.TemplateResponse("dashboard.html", ctx)
    # Refresh session cookie on each dashboard visit
    session_hash = hashlib.sha256(config.ADMIN_PASSWORD.encode()).hexdigest()
    response.set_cookie("admin_session", session_hash, httponly=True, samesite="lax", max_age=86400)
    return response


@app.get("/admin/experiments/{experiment_id}", response_class=HTMLResponse)
async def admin_experiment_report(request: Request, experiment_id: str):
    """Per-variant stats with Wilson 95% CIs for one experiment."""
    if not _admin_authed(request):
        raise HTTPException(401)
    try:
        from ab_testing import summarize
    except ImportError:
        raise HTTPException(500, "A/B testing module unavailable")

    s = summarize(experiment_id)
    rows = []
    for v in s["variants"]:
        c_rate, c_lo, c_hi = v["click_rate"]
        s_rate, s_lo, s_hi = v["signup_rate"]
        rows.append(f"""
        <tr>
          <td><strong>{v['variant']}</strong></td>
          <td>{v['assignments']:,}</td>
          <td>{v['views']:,}</td>
          <td>{v['clicks']:,}</td>
          <td>{v['signups']:,}</td>
          <td>{c_rate*100:.2f}% <span style='color:#64748b;'>({c_lo*100:.1f}–{c_hi*100:.1f})</span></td>
          <td>{s_rate*100:.2f}% <span style='color:#64748b;'>({s_lo*100:.1f}–{s_hi*100:.1f})</span></td>
        </tr>""")

    html = f"""<!DOCTYPE html><html><head>
      <meta charset="UTF-8"><title>Experiment: {experiment_id}</title>
      <link rel="stylesheet" href="/static/css/design-system.css">
      <style>
        body {{ font-family: var(--font-family); background: var(--color-bg-base); color: var(--color-text); padding: 40px; }}
        h1 {{ font-size: 28px; margin-bottom: 8px; }}
        .sub {{ color: var(--color-text-muted); margin-bottom: 24px; }}
        table {{ width: 100%; max-width: 1100px; border-collapse: collapse; background: var(--color-bg-card); border: 1px solid var(--color-border); border-radius: 12px; overflow: hidden; }}
        th, td {{ padding: 12px 16px; text-align: left; border-bottom: 1px solid var(--color-border); font-size: 14px; }}
        th {{ background: rgba(255,255,255,0.04); font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--color-text-muted); }}
        tr:last-child td {{ border-bottom: none; }}
        a {{ color: #10b981; }}
      </style>
    </head><body>
      <a href="/admin">← back to admin</a>
      <h1>Experiment: <code>{experiment_id}</code></h1>
      <p class="sub">Variants with 95% Wilson confidence intervals. Rates computed as events / views.</p>
      <table>
        <thead><tr>
          <th>Variant</th><th>Assignments</th><th>Views</th><th>Clicks</th><th>Signups</th>
          <th>Click rate (95% CI)</th><th>Signup rate (95% CI)</th>
        </tr></thead>
        <tbody>{''.join(rows) if rows else '<tr><td colspan=7 style="text-align:center;padding:32px;color:var(--color-text-muted);">No data yet for this experiment.</td></tr>'}</tbody>
      </table>
      <p style="margin-top:16px;font-size:12px;color:var(--color-text-muted);">Non-overlapping CIs = statistically meaningful difference.</p>
    </body></html>"""
    return HTMLResponse(html)


@app.post("/admin/login")
async def admin_login(pwd: str = Form(...)):
    if pwd != config.ADMIN_PASSWORD:
        html = """<!DOCTYPE html><html><head><meta charset="UTF-8"><link rel="stylesheet" href="/static/css/design-system.css"></head>
        <body style='font-family:var(--font-family);display:flex;align-items:center;justify-content:center;height:100vh;background:var(--color-bg-base);'>
        <div style='text-align:center;background:var(--color-bg-card);padding:40px;border-radius:14px;border:1px solid var(--color-border);'>
          <p style='color:var(--color-error);font-weight:600;margin:0 0 16px;'>Invalid password</p>
          <a href='/admin' style='color:var(--color-primary-light);'>Try again</a>
        </div></body></html>"""
        return HTMLResponse(html, status_code=401)
    response = RedirectResponse(url="/admin", status_code=303)
    session_hash = hashlib.sha256(config.ADMIN_PASSWORD.encode()).hexdigest()
    response.set_cookie("admin_session", session_hash, httponly=True, samesite="lax", max_age=86400)
    return response


@app.post("/admin/generate-content")
async def admin_generate_content(request: Request):
    if not _admin_authed(request):
        raise HTTPException(401)
    try:
        from automation.content_generator import run_content_generation
        result = run_content_generation(count=3)
        return JSONResponse({"message": f"Generated {result['generated']} articles", **result})
    except Exception as e:
        return JSONResponse({"message": f"Error: {str(e)}"}, status_code=500)


@app.post("/admin/send-welcomes")
async def admin_send_welcomes(request: Request):
    if not _admin_authed(request):
        raise HTTPException(401)
    try:
        from automation.email_sender import send_welcome_to_pending
        sent = send_welcome_to_pending()
        return JSONResponse({"message": f"Sent {sent} welcome emails", "sent": sent})
    except Exception as e:
        return JSONResponse({"message": f"Error: {str(e)}"}, status_code=500)


@app.post("/admin/send-newsletter")
async def admin_send_newsletter(request: Request):
    if not _admin_authed(request):
        raise HTTPException(401)
    try:
        from automation.email_sender import send_weekly_newsletter
        sent = send_weekly_newsletter()
        return JSONResponse({"message": f"Newsletter sent to {sent} subscribers", "sent": sent})
    except Exception as e:
        return JSONResponse({"message": f"Error: {str(e)}"}, status_code=500)


@app.post("/admin/post-tweet")
async def admin_post_tweet(request: Request):
    if not _admin_authed(request):
        raise HTTPException(401)
    try:
        from automation.social_poster import run_social_posting
        run_social_posting()
        return JSONResponse({"message": "Tweet posted successfully"})
    except Exception as e:
        return JSONResponse({"message": f"Error: {str(e)}"}, status_code=500)


@app.post("/admin/save-affiliate-ids")
async def admin_save_affiliate_ids(request: Request):
    if not _admin_authed(request):
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
    if not _admin_authed(request):
        raise HTTPException(401)
    add_to_queue(topic, keywords, tool_focus or None, priority=9)
    return JSONResponse({"message": f"Topic queued: {topic}"})


@app.get("/admin/service-summary")
async def admin_service_summary(request: Request):
    if not _admin_authed(request):
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
    if not _admin_authed(request):
        raise HTTPException(401)
    try:
        from automation.youtube_engine import export_all_scripts, VIDEO_TOPICS
        count = export_all_scripts()
        return JSONResponse({"message": f"Exported {count} YouTube video scripts to data/youtube_scripts/", "count": count})
    except Exception as e:
        return JSONResponse({"message": f"Error: {str(e)}"}, status_code=500)


@app.get("/admin/reddit-guide")
async def admin_reddit_guide(request: Request):
    if not _admin_authed(request):
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
        # Interactive tools + lead magnets
        f"<url><loc>{config.SITE_URL}/ai-stack-calculator</loc><lastmod>{today}</lastmod><changefreq>weekly</changefreq><priority>0.95</priority></url>",
        f"<url><loc>{config.SITE_URL}/stack-audit</loc><lastmod>{today}</lastmod><changefreq>monthly</changefreq><priority>0.85</priority></url>",
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
