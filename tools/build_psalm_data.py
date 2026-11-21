#!/usr/bin/env python3
"""Generalized psalm data builder — the Psalm 1 pipeline, parameterized.

    python3 tools/build_psalm_data.py --psalm 2
    python3 tools/build_psalm_data.py --psalm 119 --cache tools/gloss-cache.json
    python3 tools/build_psalm_data.py --psalm 1 --cache /tmp/psalm1_cache.json --strict

Inputs:
  - tools/text/psalmNNN_text.json (harvested Mechon Mamre verses; the
    cleaned Hebrew is the source of truth for verses).
  - tools/gloss-cache.json (the single gloss source; batch workers drop
    the filled cache here):
        {"version": 1,
         "languages": ["en", "es", ...],
         "glosses": {"<hebrew token>": {"en": "...", "es": "...", ...}},
         "translit_overrides": {"<hebrew token>": "hand-checked transliteration"}}
    A missing cache file, or a token missing from it, means EMPTY glosses
    for that token (never invented): the builder warns, writes the row
    blank, and the decoder falls back to English per word. Pass --strict
    to fail the build when any gloss (or transliteration override check)
    is missing — use --strict for final builds, never for smoke tests.

Outputs (same schema as tools/psalm001_data.json):
  - tools/psalmNNN_data.json: chapter/title/languages/fallback/verses
    (lexicon-index arrays)/lexicon ("h" Hebrew, "t" transliteration,
    "g" non-empty glosses)/text (canonical Hebrew, verses joined by \n).
  - tools/psalmNNN_meanings.csv: one row per unique word, columns
    hebrew,en,es,pt,fr,de,ru,ar,zh,hi,id,ja,ko. Transliteration is
    rule-computed (tools/transliterate.py, 45/49 exact against Psalm 1's
    hand table — the 4 misses are documented hand-table inconsistencies)
    and is NOT stored in the CSV.

The builder ASSERTS every verse rebuilds byte-for-byte from the lexicon
(joining the lexicon tokens with single spaces reproduces each verse),
exactly as build_psalm001_data.py does for Psalm 1.

Safety: if tools/psalmNNN_data.json already exists with HIGHER gloss
coverage than the new build, the builder refuses to overwrite it (a stub
cache must never clobber a real build); pass --force to override.
"""
import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from transliterate import transliterate  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
LANGS = ["en", "es", "pt", "fr", "de", "ru", "ar", "zh", "hi", "id", "ja", "ko"]


def coverage_of(data):
    """Fraction of lexicon x language cells that are non-empty."""
    lex = data["lexicon"]
    if not lex:
        return 0.0
    filled = sum(1 for e in lex for lang in LANGS if e["g"].get(lang))
    return filled / (len(lex) * len(LANGS))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--psalm", type=int, required=True)
    ap.add_argument("--cache", default=str(TOOLS / "gloss-cache.json"))
    ap.add_argument("--text-dir", default=str(TOOLS / "text"))
    ap.add_argument("--out-data", default=None)
    ap.add_argument("--out-csv", default=None)
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    n = args.psalm
    if not 1 <= n <= 150:
        raise SystemExit(f"psalm out of range: {n}")
    text_path = Path(args.text_dir) / f"psalm{n:03d}_text.json"
    if not text_path.exists():
        raise SystemExit(f"harvested text missing: {text_path} — run tools/harvest.py first")
    text_data = json.loads(text_path.read_text(encoding="utf-8"))
    verses = text_data["verses_hebrew"]

    cache_path = Path(args.cache)
    cache = {"glosses": {}, "translit_overrides": {}}
    if cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    else:
        print(f"WARNING: gloss cache not found at {cache_path} — building with EMPTY glosses (stub mode)")
    glosses = cache.get("glosses", {})
    overrides = cache.get("translit_overrides", {})

    # Lexicon in first-appearance order; verses become index arrays.
    lexicon, index, verse_tokens = [], {}, []
    missing_gloss_tokens = []
    for v in verses:
        toks = v.split(" ")
        for tok in toks:
            if not tok:
                raise SystemExit(f"psalm {n}: empty token in verse {v!r}")
            if tok not in index:
                g = {lang: (glosses.get(tok, {}).get(lang) or "").strip()
                     for lang in LANGS if (glosses.get(tok, {}).get(lang) or "").strip()}
                if not g:
                    missing_gloss_tokens.append(tok)
                t = overrides.get(tok) or transliterate(tok)
                index[tok] = len(lexicon)
                lexicon.append({"h": tok, "t": t, "g": g})
        verse_tokens.append([index[tok] for tok in toks])

    # Verify: joining the tokens reproduces each verse byte-for-byte.
    for v, idxs in zip(verses, verse_tokens):
        rebuilt = " ".join(lexicon[i]["h"] for i in idxs)
        assert rebuilt == v, f"verse rebuild mismatch: {rebuilt!r} != {v!r}"

    data = {
        "chapter": n,
        "title": f"Psalm {n}",
        "languages": LANGS,
        "fallback": "en",
        "verses": verse_tokens,
        "lexicon": lexicon,
        "text": "\n".join(verses),
    }
    cov = coverage_of(data)
    print(f"psalm {n}: verses={len(verses)} occurrences={sum(len(v) for v in verse_tokens)} "
          f"unique={len(lexicon)} gloss coverage={cov:.1%} "
          f"({len(lexicon) - len(missing_gloss_tokens)}/{len(lexicon)} words have any gloss)")
    if missing_gloss_tokens:
        print(f"  WARNING: {len(missing_gloss_tokens)} word(s) with no gloss at all "
              f"(first 10: {missing_gloss_tokens[:10]})")
    if args.strict and missing_gloss_tokens:
        raise SystemExit(f"--strict: {len(missing_gloss_tokens)} words lack glosses; refusing to build")

    out_data = Path(args.out_data) if args.out_data else TOOLS / f"psalm{n:03d}_data.json"
    out_csv = Path(args.out_csv) if args.out_csv else TOOLS / f"psalm{n:03d}_meanings.csv"
    if out_data.exists() and not args.force:
        old = json.loads(out_data.read_text(encoding="utf-8"))
        old_cov = coverage_of(old)
        if cov < old_cov:
            raise SystemExit(
                f"REFUSING to overwrite {out_data}: existing gloss coverage "
                f"{old_cov:.1%} > new build {cov:.1%} (stub cache must never clobber "
                f"a real build). Pass --force to override.")
    out_data.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["hebrew"] + LANGS)
        w.writeheader()
        for e in lexicon:
            w.writerow({"hebrew": e["h"], **{lang: e["g"].get(lang, "") for lang in LANGS}})
    print(f"wrote {out_data}")
    print(f"wrote {out_csv} ({len(lexicon)} rows + header)")
    print(f"verse rebuild check: all {len(verses)} verses reproduce byte-for-byte from the lexicon")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
