"""
Shared Anthropic Claude client for all bots.
"""
import logging
import anthropic
from config import config

logger = logging.getLogger(__name__)

_client = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


def ask_claude(
    prompt: str,
    system: str = None,
    max_tokens: int = 1500,
    model: str = "claude-3-5-haiku-20241022"
) -> str:
    """
    Call Claude with the given prompt. Returns text response.
    Returns empty string on any error.
    """
    try:
        client = _get_client()
        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system

        message = client.messages.create(**kwargs)
        return message.content[0].text if message.content else ""
    except anthropic.APIConnectionError as e:
        logger.error(f"Claude API connection error: {e}")
        return ""
    except anthropic.RateLimitError as e:
        logger.error(f"Claude rate limit error: {e}")
        return ""
    except anthropic.APIStatusError as e:
        logger.error(f"Claude API status error {e.status_code}: {e.message}")
        return ""
    except Exception as e:
        logger.error(f"Claude unexpected error: {e}")
        return ""


def generate_content(topic: str, content_type: str, extra_context: str = "") -> str:
    """
    Generate content for AI Tools Empire using Claude.
    content_type can be: article, social_post, email, newsletter, script, etc.
    """
    system = (
        "You are an expert content creator for AI Tools Empire (aitoolsempire.co), "
        "a leading resource for AI tool reviews, comparisons, and deals. "
        "Your writing is authoritative, helpful, and conversion-focused. "
        "You understand SEO, affiliate marketing, and the AI tools space deeply. "
        "Always write in an engaging, informative tone that builds trust with readers "
        "who are business owners, marketers, and professionals looking to use AI tools."
    )

    context_section = f"\n\nAdditional context: {extra_context}" if extra_context else ""

    prompt = (
        f"Create {content_type} content for AI Tools Empire about: {topic}"
        f"{context_section}\n\n"
        f"Site: https://aitoolsempire.co\n"
        f"Audience: Business owners, marketers, freelancers, and professionals exploring AI tools.\n"
        f"Goal: Educate readers and drive conversions to affiliate tool signups."
    )

    return ask_claude(prompt, system=system, max_tokens=2000)
