#!/usr/bin/env python3
"""Shared Mechon Mamre parsing for the Bible cartridges project.

URL pattern (established empirically 2026-11-19, from the site's own
``padme()`` in /js/mtr.js, and probed chapter by chapter):
  Psalms 1-99:    text https://www.mechon-mamre.org/p/pt/pt26NN.htm
                  audio https://www.mechon-mamre.org/mp3/t26NN.mp3
                  where NN is the zero-padded chapter (01..99)
  Psalms 100-109: pt26a0..pt26a9 / t26a0..t26a9
  Psalms 110-119: pt26b0..pt26b9 / t26b0..t26b9
  Psalms 120-129: pt26c0..pt26c9 / t26c0..t26c9
  Psalms 130-139: pt26d0..pt26d9 / t26d0..t26d9
  Psalms 140-149: pt26e0..pt26e9 / t26e0..t26e9
  Psalm  150:     pt26f0 / t26f0
The naive guesses are WRONG: pt27xx is the Book of Job (pt2710 is Job 10,
pt2719 is Job 19), and pt26100 / pt2700 / t2700 / t2750 are all 404.
Probe evidence (all with a browser User-Agent):
  pt2610 -> "Psalms 10", pt2650 -> "Psalms 50", pt2699 -> "Psalms 99",
  pt26a0 -> "Psalms 100", pt26b9 -> "Psalms 119", pt26f0 -> "Psalms 150",
  t2610/t2650/t26a0/t26b9/t26f0 -> HTTP 200 valid MP3 (ffprobe durations
  160 s / 161 s / 36 s / 1136 s / 36 s).

Page structure: one <TABLE> row per verse; the Hebrew cell is
``<TD class=h>`` (verse letter in <B>, Hebrew text with <BR> line breaks,
``--`` clause breaks, ASCII ``-`` inside words); the English cell is the
following ``<TD>`` (verse number in <B>, JPS English, ``{N}``/``{P}``
section markers). A trailing ``<A NAME="N+1">`` follows the table.

Cleaning (``clean_hebrew``) follows the Psalm 1 pipeline
(tools/build_psalm001_data.py) exactly: ``--`` -> space, ``{N}``/``{P}``
removed, ``, ; : .`` removed, ASCII ``-`` inside a word normalised to the
Hebrew maqaf U+05BE, whitespace collapsed. The cleaned verses for Psalm 1
reproduce tools/psalm001_data.json byte-for-byte (checked by
tools/harvest.py --check-psalm1).

Verse splitting is by ANCHOR, not by table row: in Psalms 70, 80, 84 and
108 the superscription (v. 1) and verse 2 share one table row, lettered
א-ב with a mid-cell <A NAME="2">, so a row-based parse merges two verses
and undercounts by one (caught by the anchor check on the first full
harvest, 2026-11-19).
"""
import html as html_mod
import re

BASE_TEXT = "https://www.mechon-mamre.org/p/pt"
BASE_AUDIO = "https://www.mechon-mamre.org/mp3"

MAQAF = "\u05be"


def suffix(n: int) -> str:
    """Mechon Mamre chapter suffix for Psalm n (1..150), e.g. 1->'01', 100->'a0'."""
    if not 1 <= n <= 150:
        raise ValueError(f"psalm out of range: {n}")
    if n < 100:
        return f"{n:02d}"
    if n < 110:
        return f"a{n % 10}"
    if n < 120:
        return f"b{n % 10}"
    if n < 130:
        return f"c{n % 10}"
    if n < 140:
        return f"d{n % 10}"
    if n < 150:
        return f"e{n % 10}"
    return "f0"


def text_code(n: int) -> str:
    return "pt26" + suffix(n)


def audio_code(n: int) -> str:
    return "t26" + suffix(n)


def text_url(n: int) -> str:
    return f"{BASE_TEXT}/{text_code(n)}.htm"


def audio_url(n: int) -> str:
    return f"{BASE_AUDIO}/{audio_code(n)}.mp3"


ROW_RE = re.compile(
    r"<TR><TD class=h[^>]*>(.*?)</TD><TD>(.*?)</TD></TR>", re.DOTALL | re.IGNORECASE
)
ANCHOR_RE = re.compile(r'<A NAME="(\d+)">', re.IGNORECASE)
TITLE_RE = re.compile(r"<TITLE>Psalms (\d+) /", re.IGNORECASE)
# A verse letter is one Hebrew letter, or a range like א-ב (Psalms 70, 80,
# 84, 108 put the superscription and verse 2 in one row, lettered א-ב).
LETTER_RE = re.compile(r"^[א-ת]+(?:-[א-ת]+)?\s+")
TABLE_RE = re.compile(r"<TABLE.*?</TABLE>", re.DOTALL | re.IGNORECASE)
ENG_VERSE_RE = re.compile(r"<B>(\d+)</B>(.*?)(?=<B>\d+</B>|</TD>)",
                          re.DOTALL | re.IGNORECASE)


def _strip_cell(cell: str) -> str:
    cell = re.sub(r"<BR\s*/?>", " ", cell, flags=re.IGNORECASE)
    cell = re.sub(r"<[^>]+>", "", cell)
    cell = html_mod.unescape(cell)
    cell = cell.replace("\xa0", " ")
    return " ".join(cell.split())


def parse_page(html_text: str, n: int) -> dict:
    """Parse one Mechon Mamre Psalms page. Returns verses + checks.

    Verses are split on their <A NAME="k"> anchors (Hebrew) and <B>k</B>
    markers (English), NOT on table rows: in Psalms 70, 80, 84 and 108 the
    superscription (v. 1) and verse 2 share a single table row, lettered
    א-ב, with a mid-cell anchor — a row-based parse merges them into one
    verse and undercounts by one. Anchors inside the table must be exactly
    1..N; the trailing <A NAME="N+1"> sits outside the table.
    """
    m = TITLE_RE.search(html_text)
    if not m or int(m.group(1)) != n:
        raise ValueError(f"page title does not say Psalms {n}: {m.group(0) if m else None!r}")
    table = TABLE_RE.search(html_text)
    if not table:
        raise ValueError(f"no verse table found on Psalms {n} page")
    table_html = table.group(0)

    # Hebrew: one verse per <A NAME="k"> anchor inside the table.
    heb_parts = re.split(r'<A NAME="(\d+)">', table_html)
    # re.split with a group: [pre, num, text, num, text, ...]
    hebrew_raw = []
    heb_nums = []
    for num, text in zip(heb_parts[1::2], heb_parts[2::2]):
        seg = text.split("</TD>", 1)[0]
        seg = _strip_cell(seg)
        seg = LETTER_RE.sub("", seg, count=1)
        if not seg:
            continue
        heb_nums.append(int(num))
        hebrew_raw.append(seg)
    if heb_nums != list(range(1, len(hebrew_raw) + 1)):
        raise ValueError(f"Psalms {n}: Hebrew anchors not 1..N: {heb_nums}")

    # English: one verse per <B>k</B> marker inside the table.
    english = []
    eng_nums = []
    for num, text in ENG_VERSE_RE.findall(table_html):
        eng = _strip_cell(text)
        if not eng:
            continue
        eng_nums.append(int(num))
        english.append(eng)
    if eng_nums != list(range(1, len(english) + 1)):
        raise ValueError(f"Psalms {n}: English markers not 1..N: {eng_nums}")
    if len(english) != len(hebrew_raw):
        raise ValueError(
            f"Psalms {n}: Hebrew verses ({len(hebrew_raw)}) != English verses ({len(english)})")

    anchors = [int(a) for a in ANCHOR_RE.findall(html_text)]
    return {
        "chapter": n,
        "title": f"Psalm {n}",
        "source_text": text_url(n),
        "source_audio": audio_url(n),
        "verses_hebrew_raw": hebrew_raw,
        "verses_hebrew": [clean_hebrew(v) for v in hebrew_raw],
        "verses_english": english,
        "verse_count": len(hebrew_raw),
        "anchors": anchors,
        "anchor_check": anchors == list(range(1, len(hebrew_raw) + 2)),
    }


def clean_hebrew(raw: str) -> str:
    """Psalm 1 pipeline cleaning: punctuation/--/{N}/{P} out, '-' -> maqaf."""
    s = raw.replace("--", " ")
    s = s.replace("{N}", "").replace("{P}", "")
    for ch in [",", ";", ":", "."]:
        s = s.replace(ch, "")
    s = s.replace("-", MAQAF)
    return " ".join(s.split())
