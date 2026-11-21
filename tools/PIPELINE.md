# Bible Cartridges — Psalms 2–150 Pipeline

How Psalms 2–150 get built from Mechon Mamre sources into PSLM v4
cartridges. Psalm 1 is the reference build (`psalms/001/`,
`tools/psalm001_data.json`); everything here reproduces its pipeline,
parameterized by psalm number.

## 0. Sources (verified)

- Text: Mechon Mamre, pointed Hebrew + JPS English, one page per psalm.
- Audio: Mechon Mamre MP3 readings, one file per psalm.
- Models (shared by all 150 cartridges): `assets/cloud-palace.glb`,
  `assets/skybox.glb` — packed whole into every cartridge by
  `tools/encode.py`; never fetched at decode time.

## 1. URL pattern (established empirically, 2026-11-19)

From the site's own `padme()` in `/js/mtr.js`, confirmed chapter by chapter
with `curl` (browser User-Agent; HTTP 200 + the expected psalm's title and
Hebrew text / valid MP3):

| Psalms | Text | Audio |
|---|---|---|
| 1–99 | `https://www.mechon-mamre.org/p/pt/pt26NN.htm` | `https://www.mechon-mamre.org/mp3/t26NN.mp3` |
| 100–109 | `pt26a0` … `pt26a9` | `t26a0` … `t26a9` |
| 110–119 | `pt26b0` … `pt26b9` | `t26b0` … `t26b9` |
| 120–129 | `pt26c0` … `pt26c9` | `t26c0` … `t26c9` |
| 130–139 | `pt26d0` … `pt26d9` | `t26d0` … `t26d9` |
| 140–149 | `pt26e0` … `pt26e9` | `t26e0` … `t26e9` |
| 150 | `pt26f0` | `t26f0` |

where `NN` is the zero-padded chapter (01–99). The naive guesses are
wrong: `pt27xx` is the Book of Job (`pt2710` is Job 10, `pt2719` is
Job 19), and `pt26100` / `pt2700` / `t2700` / `t2750` are all 404.
Probe evidence: `pt2610` → "Psalms 10", `pt2650` → "Psalms 50",
`pt2699` → "Psalms 99", `pt26a0` → "Psalms 100", `pt26b9` →
"Psalms 119", `pt26f0` → "Psalms 150"; audio `t2610`/`t2650`/`t26a0`/
`t26b9`/`t26f0` all HTTP 200, valid MP3 (ffprobe 160 s / 161 s / 36 s /
1136 s / 36 s). See `tools/parse_mechon.py` (`suffix()`, `text_url()`,
`audio_url()`).

## 2. Harvest

```
python3 tools/harvest.py --all        # texts + audios, Psalms 1–150
python3 tools/harvest.py --texts      # texts only
python3 tools/harvest.py --audios     # audios only
python3 tools/harvest.py --psalms 2,119 --force   # subset / re-fetch
```

- Texts → `tools/text/psalmNNN_text.json`: cleaned Hebrew verses
  (`verses_hebrew`), raw Hebrew as printed (`verses_hebrew_raw`), JPS
  English (`verses_english`), source URLs, verse count, anchor check.
- Audios → `tools/mp3/t<code>.mp3` (e.g. `t2601.mp3`, `t26b9.mp3`),
  each ffprobe-verified (MP3, duration, bitrate).
- Manifest → `tools/harvest_manifest.json` (HTTP status, bytes, SHA-256,
  ffprobe data per psalm). Re-running is safe (skips present files
  unless `--force`); exits non-zero on any failure.

Harvest result (2026-11-19/20): **150/150 texts, 150/150 audios**.
Audio notes: most readings are 32 kbps mono 22.05 kHz; 24 of the longer
psalms are 64 kbps. Totals: **18,627.7 s of audio = 5.17 h**,
98,166,019 bytes (93.6 MiB) of MP3. Psalm 119 is the outlier: 1136.1 s
(~19 min), 18,178,297 bytes; shortest is Psalm 117 at 16.4 s. Total
verses across the Psalter: 2,527.

### Parsing rules (`tools/parse_mechon.py`)

- One verse per `<A NAME="k">` anchor (Hebrew) and `<B>k</B>` marker
  (English) — **not** one verse per table row. In Psalms 70, 80, 84
  and 108 the superscription (v. 1) and verse 2 share a single table
  row, lettered א-ב with a mid-cell anchor; a row-based parse merges
  them and undercounts by one. This was caught by the anchor check on
  the first full harvest and the parser was fixed (re-harvest changed
  only those four files: 70: 5→6 verses, 80: 19→20, 84: 12→13,
  108: 13→14).
- Cleaning follows the Psalm 1 pipeline exactly: `--` → space,
  `{N}`/`{P}` removed, `, ; : .` removed, ASCII `-` inside a word →
  Hebrew maqaf U+05BE, whitespace collapsed. The cleaned Psalm 1
  verses reproduce `tools/psalm001_data.json` byte-for-byte.
- Checks per page: title says `Psalms N`; Hebrew anchors are exactly
  1..N; English markers are exactly 1..N; Hebrew and English verse
  counts agree; the whole page's anchors are 1..N+1 (the trailing
  anchor sits outside the table).

## 3. Master word list

```
python3 tools/build_word_list.py
```

Reads all 150 harvested texts, tokenizes the cleaned Hebrew verses on
single spaces (same tokenisation as Psalm 1's lexicon key `"h"`), and
writes `tools/psalm_all_words.json`: the full unique list in
first-appearance order across Psalms 1–150, per-psalm word lists, and
stats. Totals (2026-11-20): **9,121 unique words; 17,250 occurrences;
2,527 verses**. Unique words per psalm: min 12 (Psalm 117), max 627
(Psalm 119), median 82. Verses per psalm: min 2 (Psalm 117), max 176
(Psalm 119), median 13. Longest psalms by verses: 119 (176), 78 (72),
89 (53), 18 (51), 106 (48), 105 (45), 107 (43), 37 (40), 69 (37),
68 (36).

## 4. Gloss cache (the single gloss source)

`tools/gloss-cache.json`:

```json
{"version": 1,
 "languages": ["en","es","pt","fr","de","ru","ar","zh","hi","id","ja","ko"],
 "glosses": {"<hebrew token>": {"en": "...", "es": "...", "...": "..."}},
 "translit_overrides": {"<hebrew token>": "hand-checked transliteration"}}
```

Batch workers fill `glosses` (one entry per unique word in
`tools/psalm_all_words.json`); the builder reads only this file. A
missing file or a missing token means **empty glosses, never invented** —
the decoder falls back to English per word. The file currently in the
repo is an **empty stub** (all glosses blank); never encode a final
cartridge from it.

## 5. Per-psalm data build

```
python3 tools/build_psalm_data.py --psalm N [--cache tools/gloss-cache.json] [--strict]
```

- Inputs: `tools/text/psalmNNN_text.json` + the gloss cache.
- Outputs: `tools/psalmNNN_data.json` (same schema as Psalm 1:
  chapter/title/languages/fallback/verses-as-lexicon-index-arrays/
  lexicon `{h, t, g}`/text) and `tools/psalmNNN_meanings.csv`
  (columns `hebrew,en,es,pt,fr,de,ru,ar,zh,hi,id,ja,ko`).
- Transliteration (`"t"`) is **rule-computed** by
  `tools/transliterate.py` (SBL-style, ASCII-friendly, following Pol's
  Psalm 1 table: ח→ch, כ→kh, ש→sh, שׂ→s, צ→tz, ק→k, א/ע silent,
  ה→h always, יהוה→YHWH, proclitics hyphenated: u-ve-derekh,
  be-torat, ha-ish). Measured **45/49 exact** against Psalm 1's hand
  table (`python3 tools/transliterate.py`); the 4 misses are documented
  hand-table inconsistencies (צ as "ts" in `ba-atsat`/`letsim` vs "tz"
  elsewhere; an apostrophe for the medial ayin in `asher-ya'aseh`;
  a doubled פ with no dagesh in `asher-tiddeffennu`). A per-word
  `translit_overrides` entry in the cache wins over the rule.
- The builder **asserts every verse rebuilds byte-for-byte** from the
  lexicon (joining tokens with single spaces reproduces each verse).
- Safety: it refuses to overwrite an existing data file with
  higher gloss coverage (a stub cache must never clobber a real build);
  `--force` overrides. `--strict` fails the build when any word lacks
  a gloss — use for final builds, never for smoke tests.
- Psalm 1 cross-check: building Psalm 1 from a cache derived from
  `tools/psalm001_meanings.csv` reproduces its glosses exactly (see
  §7 smoke-test notes).

## 6. Audio, cover, viewer, encode, verify

All wired by the driver (next section); the individual tools:

- **Audio**: `ffmpeg -i tools/mp3/t<code>.mp3 -c:a libopus -b:a 24k
  psalms/NNN/audio.webm` (same as Psalm 1: Opus, 48 kHz, mono,
  ~26 kbps overall). The source MP3 is also kept at
  `psalms/NNN/t<code>.mp3`, mirroring `psalms/001/t2601.mp3`.
- **Cover**: `python3 tools/make_cover.py --psalm N --size 3072|4096
  --out psalms/NNN/cover.png` — deterministic procedural stand-in
  (golden-angle hue per psalm, gradient + arcs + rays + vignette),
  marked as a stand-in twice: a visible `PSALM N · STAND-IN COVER`
  label on the image and a `Stand-in` PNG text chunk. Pol's real
  cover art is still owed; swapping it in means replacing
  `psalms/NNN/cover.png` and nothing else.
- **Viewer**: copy `psalms/001/index.html` + `psalms/001/decode.js`
  (shared logic, nothing chapter-specific) and generate `chapter.js`
  (number / `Psalm N` / Hebrew title `תְּהִלִּים <numeral>` —
  `tools/hebrew_numerals.py`, 15→טו, 16→טז, 119→קיט, 150→קנ).
- **Encode**: `python3 tools/encode.py --cover psalms/NNN/cover.png
  --data tools/psalmNNN_data.json --audio psalms/NNN/audio.webm
  --palace assets/cloud-palace.glb --skybox assets/skybox.glb
  --out psalms/NNN/cartridge.png` (PSLM v4, full models + scene embedded).
- **Verify**: `python3 tools/decode.py psalms/NNN/cartridge.png
  --out-text … --out-audio … --out-model-palace … --out-model-skybox …`
  — every SHA-256 checked; extracted text/audio/models compared
  byte-for-byte with the sources.

### Cover-size rule

Minimum that fits, depth 1 preferred. The driver computes the exact
payload (header blob + Opus audio + scene + zlib-stored models, same
arithmetic as `encode.py`) and picks **3072×3072 when the payload fits
its depth-1 LSB layer (3,538,944 B), else 4096×4096**; the encoder then
picks the minimum depth (1, else 2) that fits and refuses loudly if
nothing fits. Psalm 119's ~19-minute reading (~3.9 MB Opus) plus the
~2.9 MB stored models exceeds depth-1 capacity even at 4096
(6,291,456 B), so its cartridge is expected to be **4096 depth 2**.

## 7. Driver

```
python3 tools/build_psalm.py --psalm N [--steps data,audio,cover,viewer,encode,verify] [--cache ...] [--cover-size auto|3072|4096] [--force]
tools/build_psalm.sh --psalm N        # thin wrapper
```

`--steps all` is the default. For a smoke test without final glosses
or a cartridge, use `--steps data,audio,cover,viewer` and redirect the
data output instead of writing the final path (see §8).

## 8. Smoke test (Psalm 2, 2026-11-20)

Run without final glosses and without encoding a cartridge:

```
python3 tools/build_psalm_data.py --psalm 2 \
    --out-data /tmp/smoke/psalm002_data.json --out-csv /tmp/smoke/psalm002_meanings.csv
python3 tools/build_psalm.py --psalm 2 --steps audio,cover,viewer --cover-size 3072
```

Results (all passed):

- **Data (to /tmp, not the final path)**: `build_psalm_data.py --psalm 2
  --out-data /tmp/smoke/psalm002_data.json` — 12 verses, 76 occurrences,
  75 unique words; verse-rebuild check passed on all 12 verses; gloss
  coverage 0.0% as expected with the stub cache (all 75 rows blank in
  the CSV). No `tools/psalm002_data.json` was written.
- **Audio**: `psalms/002/audio.webm` — Opus, 48 kHz, mono, 89.66 s,
  26,280 bps, 294,543 B (MP3 source 89.232 s); `psalms/002/t2602.mp3`
  kept alongside (356,928 B, byte-identical to the harvest).
- **Cover**: `psalms/002/cover.png` — 3072×3072 RGB, 193,553 B, with
  the visible `PSALM 2 · STAND-IN COVER` label and the `Stand-in` PNG
  text chunk; distinct from Psalm 1's cover.
- **Viewer**: `index.html` and `decode.js` byte-identical to
  `psalms/001/`; `chapter.js` generated (number 2, `Psalm 2`,
  `תְּהִלִּים ב`), parses clean under `node --check`. Served over
  local HTTP: `psalms/002/`, `index.html`, `chapter.js`, `decode.js`,
  `audio.webm`, `cover.png` all returned HTTP 200.
- **Not done (by design)**: no `psalms/002/cartridge.png` encoded and
  no final data file — those wait for the filled gloss cache.

Also verified in this job (not via the driver):

- Psalm 1 cross-check: re-parsing the Mechon Mamre Psalm 1 page
  reproduces `tools/psalm001_data.json` byte-for-byte (6 verses,
  49 tokens); `tools/harvest.py --check-psalm1` passes.
- Psalm 2 draft verdict: `tools/psalm002_data_draft.json` **matches**
  the generalized parser exactly — all 12 cleaned verses
  byte-identical, 75 unique tokens, same first-appearance order. The
  draft is staging data only (verses + audio verified, glosses not
  yet added); the batch worker builds the real
  `tools/psalm002_data.json` from the gloss cache. Do not commit the
  draft as-is.
- Psalm 2 staging audio: `tools/psalm002_audio.mp3` is **byte-identical**
  (SHA-256 `1fa1a45c…`) to a fresh download of
  `https://www.mechon-mamre.org/mp3/t2602.mp3`; valid MP3, 89.232 s,
  32 kbps, 356,928 bytes. Adopted: the harvest copy lives at
  `tools/mp3/t2602.mp3`.

## 9. What is still owed (for the batch workers)

1. The real 12-language gloss cache (`tools/gloss-cache.json`) — one
   gloss per language per unique word in `tools/psalm_all_words.json`;
   blanks stay blank, never invented.
2. Per-psalm builds: `tools/build_psalm.py --psalm N` (all steps) for
   N = 2–150, with `--strict` once the cache is filled.
3. Real cover art from Pol (≥3072²), replacing the stand-in covers.
4. Psalm 119's cartridge will be 4096 depth 2 (see §6); confirm the
   encoder accepts it and the decoder verifies it.
5. Nothing in this job was pushed (`git status` clean apart from the
   new files listed in §10); `psalms/001/index.html` untouched.
6. Coordination (parallel worker, appeared during this job): the
   universal encoder `psalms/encode.html` reads
   `tools/built-psalms.json` to know which psalms are selectable; a
   psalm counts as built when `tools/psalmNNN_data.json` AND
   `psalms/NNN/audio.webm` both exist. The driver re-runs
   `tools/build_built_psalms.py` after a successful verify so the
   manifest stays current. The smoke test wrote no final
   `tools/psalm002_data.json`, so Psalm 2 correctly stays "not built
   yet" in that manifest. README.md, index.html and
   `psalms/001/encode.html` were also modified during this job by that
   parallel live-site work — not by this pipeline job; do not revert
   them here.

## 10. File list (this job)

- `tools/parse_mechon.py` — URL pattern + page parser + cleaning.
- `tools/harvest.py` — text + audio harvester, manifest writer.
- `tools/text/psalmNNN_text.json` (×150) — harvested texts.
- `tools/mp3/t<code>.mp3` (×150) — harvested MP3s.
- `tools/harvest_manifest.json` — per-psalm fetch + ffprobe record.
- `tools/build_word_list.py`, `tools/psalm_all_words.json` — master word list.
- `tools/transliterate.py` — rule-based transliteration (45/49 on Psalm 1).
- `tools/hebrew_numerals.py` — Hebrew numerals for chapter titles.
- `tools/build_psalm_data.py` — generalized data + meanings-CSV builder.
- `tools/gloss-cache.json` — empty stub cache (to be filled).
- `tools/make_cover.py` — deterministic stand-in cover generator.
- `tools/build_psalm.py`, `tools/build_psalm.sh` — end-to-end driver.
- `tools/PIPELINE.md` — this file.
- `psalms/002/` (smoke test only) — `audio.webm`, `t2602.mp3`,
  `cover.png` (3072 stand-in), `index.html`, `decode.js`, `chapter.js`.
  No `cartridge.png`, no final `tools/psalm002_data.json` — those wait
  for the gloss cache.
