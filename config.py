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

    # Site
    SITE_NAME = os.getenv("SITE_NAME", "AI Tools Empire")
    SITE_URL = os.getenv("SITE_URL", "http://localhost:8000")
    SITE_TAGLINE = os.getenv("SITE_TAGLINE", "The #1 Resource for AI Tool Reviews, Comparisons & Deals")

    # Admin
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")

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
    }

config = Config()
