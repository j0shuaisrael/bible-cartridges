#!/usr/bin/env python3
"""Rule-based SBL-style transliteration of pointed Hebrew tokens.

Pol's Psalm 1 table (tools/build_psalm001_data.py TRANSLIT) is hand-made
and ASCII-friendly: ח -> "ch", כ/ך without dagesh -> "kh", ש -> "sh",
שׂ -> "s", צ -> "ts", ק -> "q", ט/ת -> "t", א/ע silent, ה -> "h" always,
יהוה -> "YHWH". This module reproduces those conventions by rule, so the
generalized builder (tools/build_psalm_data.py) can compute the "t" field
for any psalm without a stored per-word table.

Rules (verified against Psalm 1's 49 tokens; see __main__):
  * begedkephat: ב/כ/פ with dagesh -> b/k/p; without -> v/kh/f.
  * dagesh forte doubles the consonant, but only when the letter carries a
    full vowel or a vocal sheva, is not part-initial, and directly follows
    a pronounced vowel (a dagesh after a silent sheva, or at a part start,
    is lene and does not double: "ba-mishpat" keeps single p after שְׁ).
  * sheva is vocal ("e") when part-initial, after a long vowel, after a
    vocal sheva/hatef, or when the letter itself carries a dagesh after a
    short vowel; otherwise silent. Sheva under י/ו after a vowel is silent.
  * ו/י carrying holam/shureq, or following a vowel with no point of their
    own, are vowel letters (o/u, or the diphthong ei/ai/i); ו/י with any
    other vowel point are consonantal (v/y + vowel).
  * maqaf (U+05BE) joins parts with "-" in the transliteration.

Known misses against Psalm 1's hand table (measured 45/49 exact; the
table itself is inconsistent here — a per-word override in the gloss
cache, "translit_overrides", wins over the rule):
  * "בַּעֲצַת" / "לֵצִים" -> rule gives "ba-atzat" / "letzim"; Pol wrote
    "ba-atsat" / "letsim" (צ is "tz" in his other four tokens).
  * "בַּמִּשְׁפָּט" -> rule gives "ba-mmishpat", Pol wrote "ba-mishpat"
    (the article-assimilation mem is left single by hand). [Fixed in
    practice: the prefix loop resets the doubling context, so the rule
    now gives "ba-mishpat".]
  * "אֲשֶׁר־יַעֲשֶׂה" -> rule gives "asher-yaaseh", Pol wrote "asher-ya'aseh"
    (an apostrophe for the medial ayin after ya-).
  * "אֲשֶׁר־תִּדְּפֶנּוּ" -> rule gives "asher-tiddefennu", Pol wrote
    "asher-tiddeffennu" (the פ is doubled by hand although it has no dagesh).
Run `python3 tools/transliterate.py` for the Psalm 1 score.
"""
import json
import sys
from pathlib import Path

MAQAF = "\u05be"
DAGESH = "\u05bc"
SHEVA = "\u05b0"
SHIN_DOT = "\u05c1"
SIN_DOT = "\u05c2"
METEG = "\u05bd"
RAFE = "\u05bf"
SOF_PASUQ = "\u05c3"

# vowel point -> (latin vowel, is_long)
VOWELS = {
    "\u05b7": ("a", False),  # patah
    "\u05b8": ("a", True),   # qamats
    "\u05b6": ("e", False),  # segol
    "\u05b5": ("e", True),   # tsere
    "\u05b4": ("i", False),  # hiriq
    "\u05b9": ("o", True),   # holam
    "\u05bb": ("u", False),  # qubuts
    "\u05b2": ("a", False),  # hatef patah
    "\u05b1": ("e", False),  # hatef segol
    "\u05b3": ("o", False),  # hatef qamats
}
LONG_VOWELS = {"\u05b8", "\u05b5", "\u05b9"}  # qamats, tsere, holam

CONSONANTS = set("אבגדהוזחטיכלמנסעפצקרשתךםןףץ")

# base sound without dagesh (spirant form for begedkephat)
BASE = {
    "א": "", "ב": "v", "ג": "g", "ד": "d", "ה": "h", "ו": "w", "ז": "z",
    "ח": "ch", "ט": "t", "י": "y", "כ": "kh", "ל": "l", "מ": "m", "נ": "n",
    "ס": "s", "ע": "", "פ": "f", "צ": "tz", "ק": "k", "ר": "r", "ש": "sh",
    "ת": "t", "ך": "kh", "ם": "m", "ן": "n", "ף": "f", "ץ": "tz",
}
# hard form with dagesh (begedkephat only)
HARD = {"ב": "b", "כ": "k", "פ": "p"}


def _letters(part: str):
    """Split a maqaf-part into (consonant, marks) pairs."""
    out = []
    for ch in part:
        if ch in CONSONANTS:
            out.append([ch, set()])
        elif out:
            out[-1][1].add(ch)
    return [(c, m) for c, m in out]


def _vowel_of(marks):
    """Return (latin, is_long, kind) for the vowel point in marks."""
    if SHEVA in marks:
        return ("e", False, "sheva")
    for p, (lat, long_) in VOWELS.items():
        if p in marks:
            return (lat, long_, "full")
    return (None, False, "none")


def _is_vocal_sheva(letters, i):
    """Sheva na' (vocal) vs sheva nach (silent), by standard rules."""
    if i == 0:
        return True
    c, marks = letters[i]
    if c in ("י", "ו"):
        return False  # closes the previous syllable: laylah, not layelah
    prev_c, prev_marks = letters[i - 1]
    if prev_c == "ו" and DAGESH in prev_marks and _vowel_of(prev_marks)[2] == "none":
        return True  # shureq (וּ) is a long vowel: u-ve-derekh
    prev_vowel, prev_long, prev_kind = _vowel_of(prev_marks)
    if prev_kind in ("sheva", "full") and prev_vowel is not None:
        # after a hatef / vocal sheva, or after a long vowel -> vocal
        if prev_kind == "sheva":
            return True
        if prev_long:
            return True
    if DAGESH in marks and prev_kind == "full" and not prev_long:
        return True  # tiddeffennu: dalet with dagesh after short hiriq
    return False


def _sound_of(c, marks):
    if c == "ו" and _vowel_of(marks)[2] in ("full", "sheva"):
        return "v"  # vav with a vowel point is consonantal v, not w
    if c == "ש":
        return "s" if SIN_DOT in marks else "sh"
    if DAGESH in marks and c in HARD:
        return HARD[c]
    return BASE[c]


def _is_prefix(letters, i=0):
    """Is letters[i] a proclitic prefix (vav / bet / kaf / lamed / he)?

    Pol hyphenates proclitics: u-ve-derekh, be-torat, ha-ish, ke-etz.
    Word-initial vav is always proclitic; bet/lamed take a hyphen with a
    sheva or short vowel when a real stem follows; kaf only with a sheva
    (כַּמֹּץ is not hyphenated: im-kammotz); he only before a sheva or a
    hiriq (ha-ish, ha-resha'im — but halakh, where הָ is the verb stem).
    Mem is left alone: מִזְמוֹר is a noun, not a prefix.
    """
    if i >= len(letters):
        return False
    c, marks = letters[i]
    if c == "ו":
        return True  # word-initial vav is always proclitic (ve-, u-, va-)
    _, _, kind = _vowel_of(marks)
    if kind == "none":
        return False
    rest = len(letters) - i - 1
    if rest < 2:
        return False
    if c in ("ב", "ל"):
        # proclitic with a sheva or a SHORT vowel only: לֵצִים (tsere) and
        # בָּרוּךְ (qamats) are stems, not prefixes
        return kind == "sheva" or bool(
            marks & {"\u05b7", "\u05b6", "\u05b4"})  # patah, segol, hiriq
    if c == "כ":
        return kind == "sheva"
    if c == "ה":
        if i + 1 >= len(letters):
            return False
        _, _, nkind = _vowel_of(letters[i + 1][1])
        nmarks = letters[i + 1][1]
        return nkind == "sheva" or "\u05b4" in nmarks  # sheva or hiriq
    return False


def _transliterate_part(part: str) -> str:
    if part == "יְהוָה":
        return "YHWH"
    letters = _letters(part)
    if not letters:
        return ""
    out = []
    i = 0
    # Proclitic prefixes, hyphenated, repeatable (u-ve-derekh).
    while _is_prefix(letters, i):
        c, marks = letters[i]
        if c == "ו" and DAGESH in marks and _vowel_of(marks)[2] == "none":
            out.append("u")  # shureq prefix: u-ve-derekh
        else:
            out.append(_sound_of(c, marks))
            vowel, _, kind = _vowel_of(marks)
            if kind == "full":
                out.append(vowel)
            elif kind == "sheva":
                out.append("e")
        out.append("-")
        i += 1
    prev_had_vowel = False  # previous letter sounded a vowel (for doubling)
    n = len(letters)
    for j in range(i, n):
        c, marks = letters[j]
        vowel, is_long, kind = _vowel_of(marks)
        dagesh = DAGESH in marks
        is_first = j == 0

        # The consonant's vowel may sit on the NEXT letter (vav carrying
        # holam/shureq: תּוֹ, בּוֹ, נּוּ) — that still counts as a vowel
        # for dagesh doubling.
        next_is_vav_vowel = (
            j + 1 < n
            and letters[j + 1][0] == "ו"
            and (_vowel_of(letters[j + 1][1])[2] == "full"
                 or DAGESH in letters[j + 1][1])
        )
        eff_kind = "full" if (kind == "full" or next_is_vav_vowel) else kind

        # --- mater / diphthong letters (vav / yod with no point of their own)
        if c in ("ו", "י") and kind == "none":
            if c == "ו" and dagesh:
                out.append("u")  # shureq: word-initial וּ, e.g. u-ve-derekh
                prev_had_vowel = True
                continue
            prev_vowel, _, prev_kind = (
                _vowel_of(letters[j - 1][1]) if j else (None, False, "none")
            )
            if prev_kind == "full" and prev_vowel is not None:
                if c == "י":
                    # yod after a vowel: silent after hiriq (ha-ish, not
                    # ha-iish), otherwise the second half of a diphthong
                    # (ashrei, palgei, mayim).
                    out.append("" if prev_vowel == "i" else "i")
                # vav as mater after a vowel adds nothing
                prev_had_vowel = True
                continue
            out.append("w" if c == "ו" else "y")
            prev_had_vowel = False
            continue

        # --- vav as a vowel carrier (holam / shureq on the vav itself)
        if c == "ו" and kind == "full" and vowel in ("o", "u") and (
            "\u05b9" in marks or dagesh
        ):
            out.append(vowel)
            prev_had_vowel = True
            continue

        # --- consonant sound
        sound = _sound_of(c, marks)

        # alef/ayin with hiriq before a word-final ים (the plural ending)
        # takes an apostrophe: resha'im, chatta'im — but not ha-ish.
        if c in ("א", "ע") and kind == "full" and vowel == "i" and j + 3 == n \
                and letters[j + 1][0] == "י" and letters[j + 2][0] == "ם":
            out.append("'")

        # doubling: dagesh forte only
        double = False
        if dagesh and not is_first and prev_had_vowel and eff_kind in ("full", "sheva"):
            if eff_kind == "full":
                double = True
            elif _is_vocal_sheva(letters, j):
                double = True
        if double and sound:
            sound = sound + sound if len(sound) == 1 else sound[0] + sound

        # furtive patah: a patah under a word-final guttural is pronounced
        # BEFORE the consonant: ruach, yatzliach — not rucha, yatzlicha.
        furtive = (
            kind == "full" and vowel == "a" and "\u05b7" in marks
            and j == n - 1 and c in ("ח", "ה", "ע")
        )
        if furtive:
            out.append("a")
            out.append(sound)
            prev_had_vowel = True
            continue
        out.append(sound)

        # --- vowel sound
        if kind == "full":
            out.append(vowel)
            prev_had_vowel = True
        elif kind == "sheva":
            if _is_vocal_sheva(letters, j):
                out.append("e")
                prev_had_vowel = True
            else:
                prev_had_vowel = False
        else:
            # no vowel point: final consonant, or mater handled above
            prev_had_vowel = False
    return "".join(out)


def transliterate(token: str) -> str:
    """Transliterate one pointed-Hebrew token (may contain maqaf)."""
    token = token.replace(SOF_PASUQ, "").replace(METEG, "").replace(RAFE, "")
    parts = token.split(MAQAF)
    return "-".join(_transliterate_part(p) for p in parts if p != "")


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    data = json.loads((root / "tools" / "psalm001_data.json").read_text(encoding="utf-8"))
    ok, bad = 0, []
    for e in data["lexicon"]:
        got = transliterate(e["h"])
        if got == e["t"]:
            ok += 1
        else:
            bad.append((e["h"], e["t"], got))
    print(f"Psalm 1 transliteration: {ok}/{len(data['lexicon'])} exact")
    for h, want, got in bad:
        print(f"  {h}: want {want!r}, rule gives {got!r}")
