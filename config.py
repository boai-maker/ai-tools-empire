import os
from pathlib import Path
from dotenv import load_dotenv

# Always load .env from the project root, regardless of cwd
load_dotenv(Path(__file__).parent / ".env", override=True)

class Config:
    # Core
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
    FROM_EMAIL = os.getenv("FROM_EMAIL", "newsletter@aitoolsempire.co")
    FROM_NAME = os.getenv("FROM_NAME", "AI Tools Empire")

    # Twitter
    TWITTER_API_KEY = os.getenv("TWITTER_API_KEY", "")
    TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET", "")
    TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN", "")
    TWITTER_ACCESS_SECRET = os.getenv("TWITTER_ACCESS_SECRET", "")

    # Reddit
    REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "")
    REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
    REDDIT_USERNAME = os.getenv("REDDIT_USERNAME", "")
    REDDIT_PASSWORD = os.getenv("REDDIT_PASSWORD", "")
    REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "AIToolsEmpire/1.0")

    # YouTube
    YOUTUBE_CLIENT_ID = os.getenv("YOUTUBE_CLIENT_ID", "")
    YOUTUBE_CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET", "")
    YOUTUBE_REFRESH_TOKEN = os.getenv("YOUTUBE_REFRESH_TOKEN", "")

    # Site
    SITE_NAME = os.getenv("SITE_NAME", "AI Tools Empire")
    SITE_URL = os.getenv("SITE_URL", "http://localhost:8000")
    SITE_TAGLINE = os.getenv("SITE_TAGLINE", "The #1 Resource for AI Tool Reviews, Comparisons & Deals")

    # Admin
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")

    # SMTP (Gmail fallback — use when RESEND_API_KEY is not set)
    SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER = os.getenv("SMTP_USER", "")        # your Gmail address
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "") # Gmail App Password (not your login password)

    # SEO
    GOOGLE_SITE_VERIFICATION = os.getenv("GOOGLE_SITE_VERIFICATION", "")

    # Content generation schedule
    ARTICLES_PER_DAY = 3
    NEWSLETTER_DAY = "monday"  # Day to send weekly newsletter
    SOCIAL_POSTS_PER_DAY = 4

    # Affiliate IDs
    AFFILIATE_IDS = {
        "jasper": os.getenv("JASPER_AFFILIATE_ID", "YOURJASPERID"),
        "copyai": os.getenv("COPYAI_AFFILIATE_ID", "YOURCOPYAIID"),
        "writesonic": os.getenv("WRITESONIC_AFFILIATE_ID", "YOURWRITESONICID"),
        "surfer": os.getenv("SURFER_AFFILIATE_ID", "YOURSURFERID"),
        "semrush": os.getenv("SEMRUSH_AFFILIATE_ID", "YOURSEMRUSHID"),
        "pictory": os.getenv("PICTORY_AFFILIATE_ID", "YOURPICTORYID"),
        "invideo": os.getenv("INVIDEO_AFFILIATE_ID", "YOURINVIDEOID"),
        "murf": os.getenv("MURF_AFFILIATE_ID", "YOURMURFID"),
        "elevenlabs": os.getenv("ELEVENLABS_AFFILIATE_ID", "YOURELEVENLABSID"),
        "descript": os.getenv("DESCRIPT_AFFILIATE_ID", "YOURDESCRIPTID"),
        "fireflies": os.getenv("FIREFLIES_AFFILIATE_ID", "YOURFIREFLIESID"),
        "speechify": os.getenv("SPEECHIFY_AFFILIATE_ID", "YOURSPEECHIFYID"),
        "getresponse": os.getenv("GETRESPONSE_AFFILIATE_ID", "YOURGETRESPONSEID"),
        "hubspot": os.getenv("HUBSPOT_AFFILIATE_ID", "YOURHUBSPOTID"),
        "quillbot": os.getenv("QUILLBOT_AFFILIATE_ID", ""),
        "kit": os.getenv("KIT_AFFILIATE_ID", ""),
        "webflow": os.getenv("WEBFLOW_AFFILIATE_ID", ""),
        "grammarly": os.getenv("GRAMMARLY_AFFILIATE_ID", ""),
        "canva": os.getenv("CANVA_AFFILIATE_ID", ""),
        "synthesia": os.getenv("SYNTHESIA_AFFILIATE_ID", ""),
        "runway": os.getenv("RUNWAY_AFFILIATE_ID", ""),
        # New programs (v2 — April 2026)
        "notion": os.getenv("NOTION_AFFILIATE_ID", ""),
        "scalenut": os.getenv("SCALENUT_AFFILIATE_ID", ""),
        "anyword": os.getenv("ANYWORD_AFFILIATE_ID", ""),
        "seranking": os.getenv("SERANKING_AFFILIATE_ID", ""),
        "make": os.getenv("MAKE_AFFILIATE_ID", ""),
        "fliki": os.getenv("FLIKI_AFFILIATE_ID", ""),
        "rytr": os.getenv("RYTR_AFFILIATE_ID", ""),
        "koala": os.getenv("KOALA_AFFILIATE_ID", ""),
        "frase": os.getenv("FRASE_AFFILIATE_ID", ""),
        "hostinger": os.getenv("HOSTINGER_AFFILIATE_ID", ""),
        "heygen": os.getenv("HEYGEN_AFFILIATE_ID", ""),
        "colossyan": os.getenv("COLOSSYAN_AFFILIATE_ID", ""),
        "playht": os.getenv("PLAYHT_AFFILIATE_ID", ""),
        "lovo": os.getenv("LOVO_AFFILIATE_ID", ""),
        "mangools": os.getenv("MANGOOLS_AFFILIATE_ID", ""),
        "fotor": os.getenv("FOTOR_AFFILIATE_ID", ""),
        "hypotenuse": os.getenv("HYPOTENUSE_AFFILIATE_ID", ""),
        "clickup": os.getenv("CLICKUP_AFFILIATE_ID", ""),
        "zapier": os.getenv("ZAPIER_AFFILIATE_ID", ""),
        "wix": os.getenv("WIX_AFFILIATE_ID", ""),
    }

config = Config()
