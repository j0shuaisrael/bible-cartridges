#!/usr/bin/env python3
"""Master word list for the Psalter: every unique pointed-Hebrew surface
token (same tokenisation as Psalm 1's lexicon key "h": split the cleaned
verse on single spaces), in first-appearance order across Psalms 1..150,
plus per-psalm word lists and stats.

    python3 tools/build_word_list.py

Reads tools/text/psalmNNN_text.json (the harvest output), writes
tools/psalm_all_words.json:
  {"total_unique": N, "words": [...first-appearance order...],
   "per_psalm": {"001": {"verses": V, "occurrences": O, "unique": U,
                          "words": [...]}, ...},
   "stats": {...}}
"""
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEXT_DIR = ROOT / "tools" / "text"


def main():
    all_words = []
    seen = set()
    per_psalm = {}
    for n in range(1, 151):
        data = json.loads((TEXT_DIR / f"psalm{n:03d}_text.json").read_text(encoding="utf-8"))
        words = []
        for v in data["verses_hebrew"]:
            for tok in v.split(" "):
                if not tok:
                    raise SystemExit(f"psalm {n}: empty token in verse {v!r}")
                words.append(tok)
                if tok not in seen:
                    seen.add(tok)
                    all_words.append(tok)
        uniq = []
        useen = set()
        for tok in words:
            if tok not in useen:
                useen.add(tok)
                uniq.append(tok)
        per_psalm[f"{n:03d}"] = {
            "verses": len(data["verses_hebrew"]),
            "occurrences": len(words),
            "unique": len(uniq),
            "words": uniq,
        }
    uniq_counts = [p["unique"] for p in per_psalm.values()]
    occ_counts = [p["occurrences"] for p in per_psalm.values()]
    verse_counts = [p["verses"] for p in per_psalm.values()]
    stats = {
        "psalms": 150,
        "total_unique_words": len(all_words),
        "total_occurrences": sum(occ_counts),
        "total_verses": sum(verse_counts),
        "unique_per_psalm": {
            "min": min(uniq_counts), "max": max(uniq_counts),
            "median": statistics.median(uniq_counts),
            "min_psalms": [f"{i+1:03d}" for i, c in enumerate(uniq_counts) if c == min(uniq_counts)],
            "max_psalms": [f"{i+1:03d}" for i, c in enumerate(uniq_counts) if c == max(uniq_counts)],
        },
        "occurrences_per_psalm": {
            "min": min(occ_counts), "max": max(occ_counts),
            "median": statistics.median(occ_counts),
        },
        "verses_per_psalm": {
            "min": min(verse_counts), "max": max(verse_counts),
            "median": statistics.median(verse_counts),
            "longest_psalms": sorted(
                ((f"{i+1:03d}", c) for i, c in enumerate(verse_counts)),
                key=lambda kv: -kv[1])[:10],
        },
    }
    out = {"total_unique": len(all_words), "words": all_words,
           "per_psalm": per_psalm, "stats": stats}
    out_path = ROOT / "tools" / "psalm_all_words.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {out_path}")
    print(f"total unique words: {len(all_words)} | occurrences: {sum(occ_counts)} | verses: {sum(verse_counts)}")
    print(f"unique/psalm: min {stats['unique_per_psalm']['min']} "
          f"(psalms {', '.join(stats['unique_per_psalm']['min_psalms'])}), "
          f"max {stats['unique_per_psalm']['max']} "
          f"(psalms {', '.join(stats['unique_per_psalm']['max_psalms'])}), "
          f"median {stats['unique_per_psalm']['median']}")
    print(f"verses/psalm: min {stats['verses_per_psalm']['min']}, "
          f"max {stats['verses_per_psalm']['max']}, "
          f"median {stats['verses_per_psalm']['median']}")
    print(f"longest psalms (verses): {stats['verses_per_psalm']['longest_psalms']}")


if __name__ == "__main__":
    main()
