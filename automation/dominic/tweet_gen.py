"""
Tweet generator for Dominic.
Uses Claude to generate high-quality tweets for AI Tools Empire.
"""
import sys
import re
import json
import random
from pathlib import Path
from typing import List, Dict, Optional

_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT))

from automation.dominic.config import get_config
from automation.dominic.db import is_duplicate
from automation.dominic.logger import log_action, log_error

# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

TWEET_TEMPLATES = [
    "I tested {tool} for 30 days. Here's what nobody tells you:\n\n{insight}\n\nFull review: {url}",
    "Stop wasting hours on {task}.\n\n{tool} does it in minutes. Here's how:\n\n{url}",
    "Hot take: {opinion}\n\nHere's the data to back it up:\n\n{url}",
    "The AI tool stack I'd use if I was starting from zero today:\n\n{list}\n\nMore at {url}",
    "{number} AI tools that 10x'd my {outcome}:\n\n{list}\n\n{url}",
    "Everyone's using ChatGPT. Almost nobody's using {tool}.\n\nBig mistake. Here's why:\n\n{url}",
    "Free AI tool alert: {tool} just launched a free tier.\n\n{feature}\n\nGrab it: {url}",
    "I asked {tool} to {task}. The result was actually impressive.\n\n{result_teaser}\n\n{url}",
    "The {year} AI tools landscape has changed dramatically.\n\nHere's what's actually worth your money:\n\n{url}",
    "If you use {platform} for work, you need to know about {tool}.\n\n{benefit}\n\n{url}",
    "Unpopular opinion: Most AI writing tools are the same.\n\nExcept {tool}. Here's what makes it different:\n\n{url}",
    "{tool} vs {tool2}: I spent a week with both.\n\nWinner: {winner}. But it depends on what you need.\n\nBreakdown: {url}",
    "How I cut my content creation time by 70%:\n\n1. {step1}\n2. {step2}\n3. {step3}\n\n{url}",
    "The AI tool every {profession} should be using in {year}:\n\n{tool}\n\nHere's why: {url}",
    "Tested: Can {tool} replace a human {role}?\n\nResults were surprising.\n\n{url}",
    "I made ${amount} using this AI tool stack:\n\n{list}\n\nSetup guide: {url}",
    "Quick tip: {tip}\n\nWorks every time with {tool}. Try it today.",
    "What's the best AI tool for {use_case}?\n\nI compared 7 of them so you don't have to:\n\n{url}",
    "The AI tools that actually save me money (vs the ones that waste it):\n\n{url}",
    "If you're still writing {content_type} manually, you're leaving time on the table.\n\n{tool} changes that: {url}",
    "{tool} just got a major update.\n\nNew features:\n{features}\n\nIs it worth upgrading? {url}",
    "AI content creation in {year}: Here's what's working, what's not, and what's next:\n\n{url}",
    "Real talk: {tool} isn't perfect. Here's what it's actually good for:\n\n{url}",
    "My favorite way to use {tool} for {use_case}:\n\n{method}\n\nFull tutorial: {url}",
    "Built an entire {deliverable} using only AI tools.\n\nHere's the exact stack I used:\n\n{url}",
    "Everyone's building AI tools. Here are the ones actually worth paying for:\n\n{url}",
    "From zero to {outcome} with AI tools.\n\nHere's the 30-day breakdown:\n\n{url}",
    "{number} things I wish I knew before paying for AI tools:\n\n{list}\n\n{url}",
    "The most underrated AI tool I've used this year: {tool}\n\nHere's what it does: {url}",
    "Stop paying for {expensive_tool}. {tool} does the same thing for free:\n\n{url}",
]

HOOK_TEMPLATES = [
    "I tested {n} AI tools so you don't have to. Here are the only ones worth your time:",
    "Nobody talks about this AI tool. But it's the most useful one I've found:",
    "Hot take: You don't need a $500/month AI tool stack. Here's the $50 version that does the same:",
    "Honest review after 90 days with {tool}: Here's what the sales page won't tell you:",
    "I asked {tool} to do something impossible. It actually worked.",
    "The AI tools market is full of hype. Here's what actually delivers results in {year}:",
    "Most AI tools promise everything. This one delivers. And it's free:",
    "I just found an AI tool that replaced 3 tools I was paying for. Here's what it does:",
    "Stop paying for {category} software. This free AI alternative is better:",
    "The {profession}'s AI tool guide — everything you actually need, nothing you don't:",
    "Controversial take: {tool} is overpriced. Here are 3 alternatives that cost less and work better:",
    "Before you buy any AI tool, read this. It'll save you hundreds of dollars:",
    "I automated my entire {workflow} with AI tools. Here's the exact system I use:",
    "The AI tools that actually work for {use_case} (after testing 20+ options):",
    "Real numbers: I made ${amount} using only AI tools this month. Here's how:",
]

CTA_TEMPLATES = [
    "Get the full breakdown at {url} — bookmark it, you'll come back to this.",
    "All reviews and comparisons at {url}. No fluff, just what actually works.",
    "Start your free trial: {affiliate_url} — I use this one daily.",
    "Full comparison at {url} → {affiliate_url} for the best deal right now.",
    "See all {count}+ AI tool reviews at {url}",
    "The complete guide is at {url} — grab it before you spend on anything.",
    "Try it free at {affiliate_url} — seriously no catch, just a free plan.",
    "More picks at {url} — I update it every week.",
    "Full list and honest scores at {url}",
    "Honest breakdown at {url} — includes pricing, pros, cons, and alternatives.",
    "Before you sign up for anything, check {url} first. I do the legwork so you don't have to.",
    "Free 14-day trial at {affiliate_url} — cancel anytime, worth trying once.",
    "Compare all options side-by-side at {url}",
    "My top-rated pick is at {url} — includes exclusive deal if available.",
    "Full tutorial and link at {url}",
]


# ---------------------------------------------------------------------------
# Claude call
# ---------------------------------------------------------------------------

def _call_claude(prompt: str, max_tokens: int = 600) -> str:
    try:
        import anthropic
        cfg = get_config()
        client = anthropic.Anthropic(api_key=cfg.anthropic_api_key)
        response = client.messages.create(
            model=cfg.claude_model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text if response.content else ""
    except Exception as e:
        log_error("tweet_gen", str(e), "_call_claude")
        return ""


# ---------------------------------------------------------------------------
# Tweet generation
# ---------------------------------------------------------------------------

def generate_tweet(idea_dict: Dict, tweet_type: str = "single") -> str:
    """
    Generate a single tweet from an idea dict.
    Returns tweet text (under 280 chars).
    """
    headline = idea_dict.get("headline") or ""
    body = idea_dict.get("body") or ""
    content_type = idea_dict.get("content_type") or "educational"
    url = idea_dict.get("url") or get_config().site_url

    prompt = f"""You are a social media expert for AI Tools Empire (aitoolsempire.co).
Write ONE engaging tweet about this topic.

Topic: {headline}
Context: {body[:300]}
Content type: {content_type}
Site URL: {url}

Rules:
- Under 270 characters total
- Start with a strong hook (curiosity, value, or bold claim)
- Be specific and concrete — not generic
- Include the URL if the tweet is informational
- Max 2 hashtags, only if they add real value (e.g. #AI #AItools)
- Never use emoji spam — 1 emoji max at the start if it helps
- Sound like a sharp, knowledgeable person — not a bot
- Do NOT say "I'm excited to share" or any corporate filler

Return ONLY the tweet text. No quotes, no explanation."""

    tweet = _call_claude(prompt, max_tokens=200)
    tweet = tweet.strip().strip('"').strip("'")

    # Validate length
    if len(tweet) > 280:
        tweet = tweet[:277] + "..."

    log_action("generate_tweet", "tweet_gen", "ok", headline[:50])
    return tweet


def generate_thread(idea_dict: Dict, max_tweets: int = 5) -> List[str]:
    """
    Generate a tweet thread (list of tweets).
    """
    headline = idea_dict.get("headline") or ""
    body = idea_dict.get("body") or ""
    url = idea_dict.get("url") or get_config().site_url

    prompt = f"""You are a social media expert for AI Tools Empire (aitoolsempire.co).
Create a tweet thread of {max_tweets} tweets about this topic.

Topic: {headline}
Context: {body[:500]}
Site URL: {url}

Format your response as a numbered list:
1. [Hook tweet — bold claim or question, under 270 chars]
2. [Value tweet — key insight #1, under 270 chars]
3. [Value tweet — key insight #2, under 270 chars]
4. [Value tweet — key insight #3, under 270 chars]
5. [CTA tweet — drive to URL, under 270 chars]

Rules:
- Each tweet standalone under 270 characters
- Thread should tell a complete story
- Be specific and concrete
- Max 1 hashtag per tweet
- Sound like a knowledgeable human, not a bot
- Final tweet drives to {url}

Return only the numbered list. No explanation."""

    raw = _call_claude(prompt, max_tokens=800)
    tweets = []

    for line in raw.strip().split("\n"):
        line = line.strip()
        # Remove numbering like "1." "1)" etc.
        line = re.sub(r"^\d+[\.\)]\s*", "", line).strip()
        if len(line) > 20:
            if len(line) > 280:
                line = line[:277] + "..."
            tweets.append(line)

    if not tweets:
        # Fallback: generate single tweet
        tweets = [generate_tweet(idea_dict)]

    log_action("generate_thread", "tweet_gen", "ok", f"{len(tweets)} tweets for {headline[:40]}")
    return tweets[:max_tweets]


def generate_hook_tweet(topic: str) -> str:
    """Generate a high-engagement hook tweet for a topic."""
    hook = random.choice(HOOK_TEMPLATES)
    cfg = get_config()

    prompt = f"""Write an engaging hook tweet for this AI tools topic: "{topic}"

Site: {cfg.site_url}

Rules:
- Under 270 characters
- Creates curiosity or promises clear value
- Specific, not vague
- Sounds like a real person
- Max 1 hashtag
- End with the site URL or a CTA

Return only the tweet text."""

    tweet = _call_claude(prompt, max_tokens=150)
    tweet = tweet.strip().strip('"').strip("'")
    if not tweet:
        # Use template fallback
        tweet = hook.replace("{n}", "12").replace("{tool}", "this AI tool").replace(
            "{year}", "2025").replace("{profession}", "creator").replace(
            "{category}", "content creation").replace("{workflow}", "content workflow").replace(
            "{use_case}", "content creation").replace("{amount}", "2,000")
        tweet = tweet[:270]

    return tweet if len(tweet) <= 280 else tweet[:277] + "..."


def generate_cta_tweet(topic: str, affiliate_link: str = None) -> str:
    """Generate a CTA-focused tweet."""
    cfg = get_config()
    url = affiliate_link or cfg.site_url

    prompt = f"""Write a CTA tweet for AI Tools Empire about: "{topic}"

URL to promote: {url}
Site: {cfg.site_url}

Rules:
- Under 270 characters
- Clear, specific value proposition
- Natural call-to-action (not pushy)
- If it's an affiliate link, be transparent ("I earn commission")
- Max 1 hashtag
- Sounds human and helpful

Return only the tweet text."""

    tweet = _call_claude(prompt, max_tokens=150)
    tweet = tweet.strip().strip('"').strip("'")
    return tweet[:280] if tweet else f"Get the full breakdown on AI tools that actually work: {cfg.site_url}"


def generate_engagement_tweet(topic: str) -> str:
    """Generate a question or poll-style engagement tweet."""
    prompt = f"""Write an engagement tweet (question or poll) about this AI tools topic: "{topic}"

Rules:
- Under 270 characters
- Ask a specific, interesting question your audience will want to answer
- Or set up a poll format: "Which do you prefer: A or B? Reply below"
- Should be something an AI tools audience genuinely cares about
- Sounds natural, not formulaic
- No hashtags needed

Return only the tweet text."""

    tweet = _call_claude(prompt, max_tokens=150)
    tweet = tweet.strip().strip('"').strip("'")
    return tweet[:280] if tweet else f"Quick question: What's the #1 AI tool you couldn't live without right now? Drop it below 👇"


def pick_best_tweet(candidates: List[str]) -> str:
    """
    Score candidates and return the best tweet.
    Uses heuristics + Claude scoring.
    """
    if not candidates:
        return ""
    if len(candidates) == 1:
        return candidates[0]

    # Quick heuristic scores
    def heuristic_score(tweet: str) -> float:
        score = 0.5
        if len(tweet) < 280:
            score += 0.1
        if len(tweet) > 50:
            score += 0.1
        if "?" in tweet:
            score += 0.05  # Questions engage
        if "http" in tweet:
            score += 0.05  # Has link
        if tweet.count("#") <= 2:
            score += 0.05  # Not hashtag spam
        if any(w in tweet.lower() for w in ["free", "best", "vs", "how to", "tested", "results"]):
            score += 0.10
        return score

    scored = [(heuristic_score(t), t) for t in candidates if t]
    scored.sort(reverse=True)
    return scored[0][1]


def validate_tweet(text: str) -> Dict:
    """
    Validate a tweet for quality and compliance.
    Returns dict with {valid, issues, score}.
    """
    issues = []
    score = 1.0

    if not text:
        return {"valid": False, "issues": ["Empty tweet"], "score": 0.0}

    if len(text) > 280:
        issues.append(f"Too long: {len(text)} chars (max 280)")
        score -= 0.5

    if text.count("#") > 2:
        issues.append("Too many hashtags (max 2)")
        score -= 0.2

    if is_duplicate(text[:100]):
        issues.append("Too similar to existing content")
        score -= 0.4

    # Quality checks
    filler_phrases = [
        "i'm excited to share", "i am excited", "thrilled to announce",
        "please check out", "don't forget to", "make sure to"
    ]
    for phrase in filler_phrases:
        if phrase in text.lower():
            issues.append(f"Contains filler phrase: '{phrase}'")
            score -= 0.2

    if len(text) < 30:
        issues.append("Too short (< 30 chars)")
        score -= 0.3

    valid = score > 0.5 and len(text) <= 280
    return {"valid": valid, "issues": issues, "score": round(max(0.0, score), 2)}


def batch_generate_tweets(ideas: List[Dict], n_per_idea: int = 2) -> List[Dict]:
    """
    Generate multiple tweets from a list of ideas.
    Returns list of dicts: {idea, tweet, validation}
    """
    results = []
    for idea in ideas:
        for _ in range(n_per_idea):
            try:
                tweet = generate_tweet(idea)
                validation = validate_tweet(tweet)
                results.append({
                    "idea": idea,
                    "tweet": tweet,
                    "validation": validation,
                    "content_type": idea.get("content_type"),
                    "platform": "twitter",
                })
            except Exception as e:
                log_error("tweet_gen", str(e), f"batch idea={idea.get('headline','?')[:40]}")

    log_action("batch_generate", "tweet_gen", "ok", f"generated {len(results)} tweets")
    return results
