"""
Affiliate link registry - all programs, commissions, and tracking links.
Register for these programs to get your affiliate IDs:
"""
from config import config

AFFILIATE_PROGRAMS = {
    "jasper": {
        "name": "Jasper AI",
        "description": "AI writing assistant for marketers and content teams",
        "commission": "30% recurring monthly",
        "commission_pct": 30,
        "cookie_days": 60,
        "avg_sale": 49,
        "category": "writing",
        "logo": "jasper.png",
        "badge": "Most Popular",
        "rating": 4.8,
        "reviews": 12400,
        "signup_url": f"https://www.jasper.ai/?fpr={config.AFFILIATE_IDS['jasper']}",
        "review_keywords": ["jasper ai review", "jasper ai vs copy ai", "best ai writing tool"],
        "monthly_est_commission": 200,  # conservative estimate
    },
    "copyai": {
        "name": "Copy.ai",
        "description": "AI-powered copywriting for blogs, ads, and social media",
        "commission": "45% recurring",
        "commission_pct": 45,
        "cookie_days": 60,
        "avg_sale": 36,
        "category": "writing",
        "logo": "copyai.png",
        "badge": "Best Value",
        "rating": 4.7,
        "reviews": 8900,
        "signup_url": f"https://www.copy.ai/?via={config.AFFILIATE_IDS['copyai']}",
        "review_keywords": ["copy ai review", "copy.ai pricing", "copy ai vs jasper"],
        "monthly_est_commission": 180,
    },
    "writesonic": {
        "name": "Writesonic",
        "description": "AI writing + SEO content platform with Chatsonic",
        "commission": "30% recurring",
        "commission_pct": 30,
        "cookie_days": 30,
        "avg_sale": 19,
        "category": "writing",
        "logo": "writesonic.png",
        "badge": "Best for SEO",
        "rating": 4.6,
        "reviews": 7200,
        "signup_url": f"https://writesonic.com/?via={config.AFFILIATE_IDS['writesonic']}",
        "review_keywords": ["writesonic review", "writesonic vs jasper", "writesonic pricing"],
        "monthly_est_commission": 120,
    },
    "surfer": {
        "name": "Surfer SEO",
        "description": "AI-powered SEO content optimization tool",
        "commission": "25% recurring",
        "commission_pct": 25,
        "cookie_days": 60,
        "avg_sale": 89,
        "category": "seo",
        "logo": "surfer.png",
        "badge": "Best SEO Tool",
        "rating": 4.8,
        "reviews": 5300,
        "signup_url": f"https://surferseo.com/?via={config.AFFILIATE_IDS['surfer']}",
        "review_keywords": ["surfer seo review", "surfer seo pricing", "best seo ai tools"],
        "monthly_est_commission": 220,
    },
    "semrush": {
        "name": "Semrush",
        "description": "All-in-one SEO, content, and competitor research platform",
        "commission": "$200 per sale",
        "commission_pct": None,
        "commission_flat": 200,
        "cookie_days": 120,
        "avg_sale": 129,
        "category": "seo",
        "logo": "semrush.png",
        "badge": "Highest Payout",
        "rating": 4.9,
        "reviews": 22000,
        "signup_url": f"https://www.semrush.com/partner/?affcode={config.AFFILIATE_IDS['semrush']}",
        "review_keywords": ["semrush review", "semrush vs ahrefs", "semrush pricing 2026"],
        "monthly_est_commission": 400,
    },
    "pictory": {
        "name": "Pictory AI",
        "description": "Turn scripts and articles into engaging videos with AI",
        "commission": "50% first month, 20% recurring",
        "commission_pct": 20,
        "cookie_days": 30,
        "avg_sale": 39,
        "category": "video",
        "logo": "pictory.png",
        "badge": "Best AI Video",
        "rating": 4.6,
        "reviews": 4100,
        "signup_url": f"https://pictory.ai/?ref={config.AFFILIATE_IDS['pictory']}",
        "review_keywords": ["pictory ai review", "pictory ai pricing", "best ai video tools"],
        "monthly_est_commission": 150,
    },
    "invideo": {
        "name": "InVideo AI",
        "description": "Create professional videos from text prompts in minutes",
        "commission": "50% of first payment",
        "commission_pct": 50,
        "cookie_days": 60,
        "avg_sale": 25,
        "category": "video",
        "logo": "invideo.png",
        "badge": "Easiest to Use",
        "rating": 4.5,
        "reviews": 6800,
        "signup_url": f"https://invideo.io/?ref={config.AFFILIATE_IDS['invideo']}",
        "review_keywords": ["invideo ai review", "invideo pricing", "invideo vs pictory"],
        "monthly_est_commission": 100,
    },
    "murf": {
        "name": "Murf AI",
        "description": "Realistic AI voiceovers for videos, podcasts, and e-learning",
        "commission": "30% recurring",
        "commission_pct": 30,
        "cookie_days": 30,
        "avg_sale": 29,
        "category": "audio",
        "logo": "murf.png",
        "badge": "Best Voiceover AI",
        "rating": 4.7,
        "reviews": 3200,
        "signup_url": f"https://murf.ai/?ref={config.AFFILIATE_IDS['murf']}",
        "review_keywords": ["murf ai review", "murf ai pricing", "best ai voiceover tools"],
        "monthly_est_commission": 90,
    },
    "elevenlabs": {
        "name": "ElevenLabs",
        "description": "Ultra-realistic AI voice cloning and text-to-speech",
        "commission": "22% recurring",
        "commission_pct": 22,
        "cookie_days": 30,
        "avg_sale": 22,
        "category": "audio",
        "logo": "elevenlabs.png",
        "badge": "Most Realistic Voice",
        "rating": 4.9,
        "reviews": 9800,
        "signup_url": f"https://elevenlabs.io/?from={config.AFFILIATE_IDS['elevenlabs']}",
        "review_keywords": ["elevenlabs review", "elevenlabs pricing", "elevenlabs vs murf"],
        "monthly_est_commission": 110,
    },
    "descript": {
        "name": "Descript",
        "description": "AI video and podcast editing — edit media like a Word doc",
        "commission": "15% recurring",
        "commission_pct": 15,
        "cookie_days": 30,
        "avg_sale": 24,
        "category": "video",
        "logo": "descript.png",
        "badge": "Best for Creators",
        "rating": 4.7,
        "reviews": 5600,
        "signup_url": f"https://www.descript.com/affiliates?ref={config.AFFILIATE_IDS['descript']}",
        "review_keywords": ["descript review", "descript pricing", "descript vs premiere"],
        "monthly_est_commission": 80,
    },
    "fireflies": {
        "name": "Fireflies AI",
        "description": "AI meeting notetaker that records, transcribes, and summarizes calls",
        "commission": "30% recurring",
        "commission_pct": 30,
        "cookie_days": 30,
        "avg_sale": 18,
        "category": "productivity",
        "logo": "fireflies.png",
        "badge": "Best Meeting AI",
        "rating": 4.6,
        "reviews": 4400,
        "signup_url": f"https://fireflies.ai/?ref={config.AFFILIATE_IDS['fireflies']}",
        "review_keywords": ["fireflies ai review", "fireflies ai pricing", "best meeting ai tools"],
        "monthly_est_commission": 95,
    },
}

CATEGORIES = {
    "writing": {"label": "AI Writing Tools", "icon": "✍️", "description": "AI-powered writing assistants"},
    "seo": {"label": "AI SEO Tools", "icon": "🔍", "description": "SEO and content optimization"},
    "video": {"label": "AI Video Tools", "icon": "🎬", "description": "Create and edit videos with AI"},
    "audio": {"label": "AI Voice Tools", "icon": "🎙️", "description": "Voice cloning and text-to-speech"},
    "productivity": {"label": "AI Productivity", "icon": "⚡", "description": "Work smarter with AI"},
}

def get_tools_by_category(category: str = None):
    if category:
        return {k: v for k, v in AFFILIATE_PROGRAMS.items() if v["category"] == category}
    return AFFILIATE_PROGRAMS

def get_affiliate_link(tool_key: str) -> str:
    tool = AFFILIATE_PROGRAMS.get(tool_key)
    if not tool:
        return "#"
    return tool["signup_url"]

def get_monthly_revenue_estimate() -> dict:
    total = 0
    breakdown = {}
    for key, tool in AFFILIATE_PROGRAMS.items():
        est = tool.get("monthly_est_commission", 0)
        breakdown[tool["name"]] = est
        total += est
    return {"total_monthly": total, "total_weekly": total / 4.33, "breakdown": breakdown}
