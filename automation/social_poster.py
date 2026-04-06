"""
Social media automation — posts 4x/day to Twitter/X.
Drives traffic to the site; includes affiliate links naturally.
"""
import tweepy
import logging
import random
from datetime import datetime
from config import config
from database.db import get_articles
from affiliate.links import AFFILIATE_PROGRAMS

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# ── Tweet templates ────────────────────────────────────────────────────────────
TWEET_TEMPLATES = [
    # Review hook
    "🤖 {tool_name} Review ({year}): Is It Worth ${price}/month?\n\nSpoiler: For most content creators, yes.\n\nHere's why 👇\n\n{article_url}\n\n{affiliate_url}",

    # Stat-led
    "📊 We tested {count}+ AI tools so you don't have to.\n\nOur top pick in {category}: {tool_name}\n\n✅ {feature1}\n✅ {feature2}\n✅ Free trial available\n\nFull breakdown: {article_url}",

    # Comparison
    "⚔️ {tool1} vs {tool2}: Which is better in {year}?\n\nWinner: {tool1} (by a slim margin)\n\nHere's the full comparison:\n{article_url}\n\nTry {tool1} free: {affiliate_url}",

    # Deal alert
    "💰 DEAL ALERT: {tool_name} free trial is live right now.\n\n{description}\n\n→ {affiliate_url}\n\n(Affiliate link — I earn a commission if you sign up. No extra cost to you!)",

    # Tips
    "⚡ AI tip of the day:\n\nIf you're spending more than 2 hours writing content, you're doing it wrong.\n\n{tool_name} cuts my writing time by 70%.\n\nFree trial: {affiliate_url}",

    # Question hook
    "What's the best AI tool for {use_case} in {year}?\n\nWe ranked all of them:\n{article_url}\n\n#AItools #ContentCreation #Productivity",

    # Listicle hook
    "🧵 {count} AI tools that actually save you money:\n\n1. {tool1} — {desc1}\n2. {tool2} — {desc2}\n3. {tool3} — {desc3}\n\nFull reviews: {site_url}/articles",
]

HASHTAG_SETS = [
    "#AItools #ContentCreation #Productivity #Marketing",
    "#ArtificialIntelligence #AIwriting #SEO #Blogging",
    "#AItools #Automation #WorkSmart #Tech",
    "#DigitalMarketing #ContentMarketing #AI #SaaS",
]

def get_twitter_client():
    """Initialize Twitter/X API v2 client."""
    if not all([config.TWITTER_API_KEY, config.TWITTER_API_SECRET,
                config.TWITTER_ACCESS_TOKEN, config.TWITTER_ACCESS_SECRET]):
        log.warning("Twitter credentials not configured")
        return None
    try:
        client = tweepy.Client(
            consumer_key=config.TWITTER_API_KEY,
            consumer_secret=config.TWITTER_API_SECRET,
            access_token=config.TWITTER_ACCESS_TOKEN,
            access_token_secret=config.TWITTER_ACCESS_SECRET,
        )
        return client
    except Exception as e:
        log.error(f"Twitter client error: {e}")
        return None

def build_tweet(article: dict = None) -> str:
    """Build a tweet from an article or pick a general promotional one."""
    tools = list(AFFILIATE_PROGRAMS.values())
    featured = random.choice(tools)
    other = random.choice([t for t in tools if t["name"] != featured["name"]])

    year = datetime.now().year
    hashtags = random.choice(HASHTAG_SETS)

    if article:
        article_url = f"{config.SITE_URL}/articles/{article['slug']}"

        tweet = (
            f"📖 New: {article['title']}\n\n"
            f"{article.get('meta_description', '')[:120]}...\n\n"
            f"Read it: {article_url}\n\n"
            f"{hashtags}"
        )
        return tweet[:280]

    # General promotional tweets
    templates_simple = [
        f"🔥 {featured['name']} is the best AI tool for {featured['category']} right now.\n\n{featured['description']}\n\nFree trial: {featured['signup_url']}\n\n{hashtags}",
        f"⚡ Stop wasting time on manual work.\n\n{featured['name']} automates your {featured['category']} workflow.\n\n→ {featured['signup_url']}\n\n{hashtags}",
        f"💡 AI tool spotlight: {featured['name']}\n\n{featured['description']}\n\nRating: {'⭐' * int(featured['rating'])}\n\nTry it free: {featured['signup_url']}\n\n{hashtags}",
        f"📊 {featured['name']} vs {other['name']} — which is better?\n\nRead our full comparison:\n{config.SITE_URL}/articles\n\n{hashtags}",
        f"💡 Looking to save time on content creation?\n\n{featured['name']} handles the heavy lifting so you can focus on growth.\n\nSee our top picks:\n{config.SITE_URL}/tools\n\n{hashtags}",
    ]
    return random.choice(templates_simple)[:280]

def post_tweet(content: str) -> bool:
    """Post a single tweet."""
    client = get_twitter_client()
    if not client:
        log.info(f"[MOCK TWEET] Would post: {content[:100]}...")
        return True

    try:
        response = client.create_tweet(text=content)
        log.info(f"Tweet posted: {content[:60]}...")
        return True
    except tweepy.TweepyException as e:
        if "402" in str(e) or "Payment Required" in str(e) or "credits" in str(e).lower():
            log.info(f"[MOCK TWEET — add X credits to go live] {content[:80]}...")
            return True  # Mock so queue advances; buy credits at console.x.com
        log.error(f"Tweet failed: {e}")
        return False

def run_social_posting() -> bool:
    """
    Called by scheduler 2x/day — posts from social_queue first,
    falls back to generating from recent articles.
    """
    from database.db import get_conn
    conn = get_conn()
    row = conn.execute("""
        SELECT id, content FROM social_queue
        WHERE platform='twitter' AND posted=0
          AND (scheduled_for IS NULL OR scheduled_for <= datetime('now'))
        ORDER BY scheduled_for ASC LIMIT 1
    """).fetchone()
    conn.close()

    if row:
        ok = post_tweet(row["content"])
        if ok:
            c = get_conn()
            c.execute("UPDATE social_queue SET posted=1, posted_at=CURRENT_TIMESTAMP WHERE id=?", (row["id"],))
            c.commit()
            c.close()
        return ok

    # Fallback: auto-generate from articles
    articles = get_articles(limit=20)
    article = random.choice(articles) if articles else None
    return post_tweet(build_tweet(article=article))


def run_promo_tweet() -> bool:
    """Second daily tweet slot."""
    return run_social_posting()
