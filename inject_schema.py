"""
inject_schema.py
Populates the `faq_data` column in the articles table.
FAQ pairs are extracted from H2/H3 headings + their following paragraph.
The template renders these as JSON-LD in <head> — content is never touched.

Run: python3 inject_schema.py
Re-running is safe (idempotent — skips articles already populated).
"""

import sqlite3
import json
from bs4 import BeautifulSoup

DB = "/Users/kennethbonnet/ai-tools-empire/data.db"
MIN_PAIRS = 2
MAX_PAIRS = 6


def extract_faq_pairs(content: str) -> list:
    soup = BeautifulSoup(content, "html.parser")
    pairs = []
    for h in soup.find_all(["h2", "h3"]):
        question = h.get_text(strip=True)
        if len(question) < 15 or len(question) > 120:
            continue
        # Find the first real paragraph sibling
        node = h.find_next_sibling()
        while node and node.name not in ("p", "ul", "ol"):
            node = node.find_next_sibling()
        if not node:
            continue
        answer = node.get_text(" ", strip=True)
        if len(answer) < 40:
            continue
        q = question if question.endswith("?") else question + "?"
        pairs.append({"q": q, "a": answer[:350]})
        if len(pairs) >= MAX_PAIRS:
            break
    return pairs


def main():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT id, title, content FROM articles WHERE content IS NOT NULL AND (faq_data IS NULL OR faq_data = '')")
    rows = c.fetchall()

    added = 0
    skipped = 0
    for art_id, title, content in rows:
        pairs = extract_faq_pairs(content)
        if len(pairs) < MIN_PAIRS:
            skipped += 1
            continue
        c.execute("UPDATE articles SET faq_data=? WHERE id=?", (json.dumps(pairs), art_id))
        print(f"  ✓ [{art_id}] {title[:60]}  ({len(pairs)} pairs)")
        added += 1

    conn.commit()
    conn.close()
    print(f"\nDone: {added} articles populated, {skipped} skipped (too few headings).")


if __name__ == "__main__":
    main()
