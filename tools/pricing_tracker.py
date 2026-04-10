"""
Pricing Tracker for AI Tools Empire
====================================
Reads data/pricing.json and provides:
  - Staleness report (tools not verified in 90+ days)
  - Markdown pricing report
  - Manual plan price updates saved back to pricing.json

Usage:
  python tools/pricing_tracker.py --report
  python tools/pricing_tracker.py --update TOOL_KEY --plan "Plan Name" --price 29.99

# MANUAL UPDATE: When a tool's price changes, visit the pricing_page_url in pricing.json
# for that tool, verify the current price, then run:
#   python tools/pricing_tracker.py --update <tool_key> --plan "<Plan Name>" --price <new_price>
# Finally, bump last_verified to today's date with --verify (or do it manually in the JSON).
"""

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
PRICING_FILE = ROOT / "data" / "pricing.json"

STALE_DAYS = 90  # Flag as STALE if last_verified is older than this many days


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_pricing() -> dict:
    """Load pricing data from JSON file."""
    if not PRICING_FILE.exists():
        print(f"ERROR: pricing file not found at {PRICING_FILE}", file=sys.stderr)
        sys.exit(1)
    with PRICING_FILE.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def save_pricing(data: dict) -> None:
    """Write pricing data back to JSON file."""
    with PRICING_FILE.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print(f"Saved: {PRICING_FILE}")


def days_since(date_str: str) -> int:
    """Return how many days have elapsed since date_str (YYYY-MM-DD)."""
    verified = datetime.strptime(date_str, "%Y-%m-%d").date()
    return (date.today() - verified).days


def is_stale(tool_data: dict) -> bool:
    last = tool_data.get("last_verified", "2000-01-01")
    return days_since(last) >= STALE_DAYS


def find_plan(tool_data: dict, plan_name: str) -> Optional[int]:
    """Return index of plan with matching name (case-insensitive), or None."""
    for i, plan in enumerate(tool_data.get("plans", [])):
        if plan["name"].lower() == plan_name.lower():
            return i
    return None


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def generate_report(pricing: dict) -> str:
    today = date.today().isoformat()
    lines = [
        "# AI Tools Pricing Report",
        f"Generated: {today}  |  Stale threshold: {STALE_DAYS} days",
        "",
    ]

    stale_tools = []
    current_tools = []
    for key, tool in pricing.items():
        if is_stale(tool):
            stale_tools.append((key, tool))
        else:
            current_tools.append((key, tool))

    # --- Staleness alert section ---
    if stale_tools:
        lines.append("## Stale Pricing (needs manual verification)")
        lines.append("")
        lines.append("| Tool | Last Verified | Days Since | Pricing Page |")
        lines.append("|------|--------------|-----------|--------------|")
        for key, tool in sorted(stale_tools, key=lambda x: x[1]["last_verified"]):
            age = days_since(tool["last_verified"])
            url = tool.get("pricing_page_url", "N/A")
            lines.append(
                f"| **{tool['name']}** `[STALE]` | {tool['last_verified']} | {age}d | {url} |"
            )
        lines.append("")
        lines.append(
            "> **Action required:** Visit each pricing page URL above and run "
            "`python tools/pricing_tracker.py --update TOOL_KEY --plan \"Plan Name\" --price X` "
            "to record any changes."
        )
        lines.append("")
    else:
        lines.append("## Staleness Status")
        lines.append("")
        lines.append(f"All {len(pricing)} tools verified within the last {STALE_DAYS} days.")
        lines.append("")

    # --- Full pricing table ---
    lines.append("## Current Stored Prices")
    lines.append("")

    for key, tool in sorted(pricing.items(), key=lambda x: x[1]["name"]):
        stale_marker = " `[STALE]`" if is_stale(tool) else ""
        lines.append(f"### {tool['name']}{stale_marker}")
        lines.append("")
        lines.append(f"- **Last verified:** {tool['last_verified']}")
        lines.append(f"- **Pricing page:** {tool.get('pricing_page_url', 'N/A')}")
        lines.append(f"- **Affiliate URL:** {tool.get('affiliate_url', 'N/A')}")

        notes = tool.get("notes", "")
        if notes:
            lines.append(f"- **Notes:** {notes}")

        lines.append("")
        lines.append("| Plan | Price (USD) | Billing | Key Limits |")
        lines.append("|------|------------|---------|-----------|")

        for plan in tool.get("plans", []):
            price = plan.get("price_usd", 0)
            price_str = "Custom / Contact Sales" if price == 0 and plan.get("billing") == "custom" else f"${price:.2f}"
            lines.append(
                f"| {plan['name']} | {price_str} | {plan.get('billing', '')} | {plan.get('key_limits', '')} |"
            )

        lines.append("")

    # --- Footer ---
    lines.append("---")
    lines.append("")
    lines.append("## How to Update a Price")
    lines.append("")
    lines.append("```")
    lines.append("# MANUAL UPDATE: check pricing page URL and update here")
    lines.append("# 1. Visit the tool's pricing_page_url listed above")
    lines.append("# 2. Find the plan whose price has changed")
    lines.append("# 3. Run the update command:")
    lines.append("#    python tools/pricing_tracker.py --update <tool_key> --plan \"<Plan Name>\" --price <new_price>")
    lines.append("# 4. Verify the update was saved in data/pricing.json")
    lines.append("```")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI actions
# ---------------------------------------------------------------------------

def cmd_report(args) -> None:
    pricing = load_pricing()
    report = generate_report(pricing)
    print(report)


def cmd_update(args) -> None:
    """
    MANUAL UPDATE: check pricing page URL and update here.
    This command updates a single plan's price in pricing.json.
    No web scraping — the new price must be provided by the operator
    after manually checking the tool's pricing page.
    """
    tool_key: str = args.update
    plan_name: str = args.plan
    new_price: float = args.price

    pricing = load_pricing()

    # Validate tool key
    if tool_key not in pricing:
        available = ", ".join(sorted(pricing.keys()))
        print(f"ERROR: Tool key '{tool_key}' not found.", file=sys.stderr)
        print(f"Available keys: {available}", file=sys.stderr)
        sys.exit(1)

    tool_data = pricing[tool_key]

    # Find matching plan
    plan_idx = find_plan(tool_data, plan_name)
    if plan_idx is None:
        available_plans = [p["name"] for p in tool_data.get("plans", [])]
        print(f"ERROR: Plan '{plan_name}' not found for '{tool_key}'.", file=sys.stderr)
        print(f"Available plans: {', '.join(available_plans)}", file=sys.stderr)
        print("", file=sys.stderr)
        print("To add a new plan, edit data/pricing.json directly.", file=sys.stderr)
        sys.exit(1)

    old_price = tool_data["plans"][plan_idx]["price_usd"]
    tool_data["plans"][plan_idx]["price_usd"] = new_price

    # Bump last_verified to today
    today = date.today().isoformat()
    tool_data["last_verified"] = today
    pricing[tool_key] = tool_data

    save_pricing(pricing)

    print(f"Updated  : {tool_data['name']} / {plan_name}")
    print(f"Price    : ${old_price} -> ${new_price}")
    print(f"Verified : {today}")
    print("")
    print(
        "Reminder: If other plans on this tool also changed, run --update again "
        "for each affected plan."
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pricing_tracker.py",
        description="AI Tools Empire — pricing tracker (manual updates, no scraping)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tools/pricing_tracker.py --report
  python tools/pricing_tracker.py --update grammarly --plan "Premium" --price 12.00
  python tools/pricing_tracker.py --update jasper --plan "Pro" --price 69.00
        """,
    )

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--report",
        action="store_true",
        help="Print a markdown pricing report (stdout). Flags stale entries.",
    )
    mode.add_argument(
        "--update",
        metavar="TOOL_KEY",
        help="Tool key to update (e.g. grammarly, jasper). Requires --plan and --price.",
    )

    parser.add_argument(
        "--plan",
        metavar="NAME",
        help='Plan name to update (e.g. "Pro", "Premium"). Required with --update.',
    )
    parser.add_argument(
        "--price",
        type=float,
        metavar="USD",
        help="New monthly price in USD (e.g. 29.00). Required with --update.",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.update:
        # Validate required companion flags
        missing = []
        if args.plan is None:
            missing.append("--plan")
        if args.price is None:
            missing.append("--price")
        if missing:
            parser.error(f"--update requires: {', '.join(missing)}")
        cmd_update(args)
    else:
        cmd_report(args)


if __name__ == "__main__":
    main()
