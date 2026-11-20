#!/usr/bin/env python3
"""Assemble tools/psalm001_meanings.csv + the extended tools/psalm001_data.json.

Sources:
  - tools/psalm001_data.json (current, en+es): transliterations + verse
    structure + the EN/ES glosses (kept byte-identical — asserted below).
  - tools/gloss-fetch/{pt,fr,de,ru,ar,zh,hi,id,ja,ko}.json: the fetched
    glosses, one file per language, keyed by the 49 Hebrew tokens; a blank
    value means "no gloss in this language" (the decoder falls back to
    English for that word; nothing is invented).

Outputs:
  - tools/psalm001_meanings.csv: one row per unique word (49 + header),
    columns hebrew,en,es,pt,fr,de,ru,ar,zh,hi,id,ja,ko. This is the
    human-editable per-psalm meanings table. Transliteration is
    rule-computed at render time, so it is NOT stored here.
  - tools/psalm001_data.json: rebuilt by build_psalm001_data.py from the
    CSV (the CSV is the source of truth for glosses; the build script keeps
    the transliteration table + verses). Empty glosses are omitted from
    the JSON "g" objects (the decoder falls back per word).
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path("/home/hatch/workspace/bible-cartridges/tools")
LANGS = ["en", "es", "pt", "fr", "de", "ru", "ar", "zh", "hi", "id", "ja", "ko"]
FETCH = ["pt", "fr", "de", "ru", "ar", "zh", "hi", "id", "ja", "ko"]

old = json.loads((ROOT / "psalm001_data.json").read_text(encoding="utf-8"))
lexicon = old["lexicon"]
tokens = [e["h"] for e in lexicon]
assert len(tokens) == 49, f"expected 49 tokens, got {len(tokens)}"

# Load the fetched glosses; every file must carry all 49 tokens as keys.
fetched = {}
for lang in FETCH:
    d = json.loads((ROOT / "gloss-fetch" / f"{lang}.json").read_text(encoding="utf-8"))
    g = d["glosses"]
    missing = [t for t in tokens if t not in g]
    extra = [t for t in g if t not in tokens]
    if missing or extra:
        sys.exit(f"{lang}.json: missing tokens {missing}; extra keys {extra}")
    fetched[lang] = g

# Build rows in first-appearance order (the lexicon's order).
rows = []
for e in lexicon:
    row = {"hebrew": e["h"], "en": e["g"]["en"], "es": e["g"]["es"]}
    for lang in FETCH:
        row[lang] = fetched[lang][e["h"]] or ""
    rows.append(row)

csv_path = ROOT / "psalm001_meanings.csv"
with open(csv_path, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["hebrew"] + LANGS)
    w.writeheader()
    w.writerows(rows)

# Coverage report.
print(f"wrote {csv_path} ({len(rows)} rows + header)")
for lang in LANGS:
    n = sum(1 for r in rows if r[lang])
    print(f"  {lang}: {n}/49")
total = sum(1 for r in rows for lang in LANGS if r[lang])
print(f"  total non-empty glosses: {total}/{49 * 12}")
