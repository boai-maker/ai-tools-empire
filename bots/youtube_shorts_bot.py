"""
YouTube Shorts Bot — compatibility shim
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The real engine now lives in `bots/video_engine.py`. This file exists
only so that the existing scheduler entries (`job_youtube_shorts` in
`bots/run_bots.py`) and any other code importing `run_youtube_shorts_bot`
keep working without modification.

To produce a Short directly:
    from bots.video_engine import run_video_engine
    result = run_video_engine("short")
"""
from bots.video_engine import run_video_engine


def run_youtube_shorts_bot(tool_key: str = None):
    """Backwards-compatible entry point. Routes to the unified video engine."""
    # tool_key is ignored — the engine picks the highest-money topic itself
    result = run_video_engine(format_type="rotate")
    return result.to_dict() if hasattr(result, "to_dict") else result


if __name__ == "__main__":
    print(run_youtube_shorts_bot())
