#!/usr/bin/env python3
"""Build tools/psalm001_data.json — the single source of truth for Psalm 1.

Verses are the pointed Hebrew exactly as supplied (Mechon Mamre).
The lexicon is keyed by UNIQUE space-separated token (49 tokens for Psalm 1):
each entry carries the Hebrew token, an SBL-style transliteration, and a short
plain gloss in every packed language that has one.

SOURCES:
  - tools/psalm001_meanings.csv — the per-psalm meanings table (the source
    of truth for glosses; one row per word, one column per language).
    A blank cell means "no gloss in this language" — the decoder falls
    back to English for that word. Nothing is invented here.
  - TRANSLIT below — the SBL-style transliteration per token. It is NOT in
    the CSV: transliteration is rule-computed at render time (the decoder
    renders the Latin pronunciation into the reader's alphabet), so the
    CSV stores meanings only.

The generator VERIFIES: every token in every verse exists in the table,
joining the tokens with single spaces reproduces each verse exactly, and
the English + Spanish glosses are byte-identical to the hand-written
originals (they were written first and must never drift).
"""
import csv
import json

VERSES = [
    "אַשְׁרֵי הָאִישׁ אֲשֶׁר לֹא הָלַךְ בַּעֲצַת רְשָׁעִים וּבְדֶרֶךְ חַטָּאִים לֹא עָמָד וּבְמוֹשַׁב לֵצִים לֹא יָשָׁב",
    "כִּי אִם בְּתוֹרַת יְהוָה חֶפְצוֹ וּבְתוֹרָתוֹ יֶהְגֶּה יוֹמָם וָלָיְלָה",
    "וְהָיָה כְּעֵץ שָׁתוּל עַל־פַּלְגֵי־מָיִם אֲשֶׁר פִּרְיוֹ יִתֵּן בְּעִתּוֹ וְעָלֵהוּ לֹא־יִבּוֹל וְכֹל אֲשֶׁר־יַעֲשֶׂה יַצְלִיחַ",
    "לֹא־כֵן הָרְשָׁעִים כִּי אִם־כַּמֹּץ אֲשֶׁר־תִּדְּפֶנּוּ רוּחַ",
    "עַל־כֵּן לֹא־יָקֻמוּ רְשָׁעִים בַּמִּשְׁפָּט וְחַטָּאִים בַּעֲדַת צַדִּיקִים",
    "כִּי־יוֹדֵעַ יְהוָה דֶּרֶךְ צַדִּיקִים וְדֶרֶךְ רְשָׁעִים תֹּאבֵד",
]

# Hebrew token -> SBL-style transliteration (verified pronunciation).
TRANSLIT = {
    "אַשְׁרֵי": "ashrei", "הָאִישׁ": "ha-ish", "אֲשֶׁר": "asher",
    "לֹא": "lo", "הָלַךְ": "halakh", "בַּעֲצַת": "ba-atsat",
    "רְשָׁעִים": "resha'im", "וּבְדֶרֶךְ": "u-ve-derekh",
    "חַטָּאִים": "chatta'im", "עָמָד": "amad", "וּבְמוֹשַׁב": "u-ve-moshav",
    "לֵצִים": "letsim", "יָשָׁב": "yashav", "כִּי": "ki", "אִם": "im",
    "בְּתוֹרַת": "be-torat", "יְהוָה": "YHWH", "חֶפְצוֹ": "cheftzo",
    "וּבְתוֹרָתוֹ": "u-ve-torato", "יֶהְגֶּה": "yehgeh", "יוֹמָם": "yomam",
    "וָלָיְלָה": "va-laylah", "וְהָיָה": "ve-hayah", "כְּעֵץ": "ke-etz",
    "שָׁתוּל": "shatul", "עַל־פַּלְגֵי־מָיִם": "al-palgei-mayim",
    "פִּרְיוֹ": "piryo", "יִתֵּן": "yitten", "בְּעִתּוֹ": "be-itto",
    "וְעָלֵהוּ": "ve-alehu", "לֹא־יִבּוֹל": "lo-yibbol", "וְכֹל": "ve-khol",
    "אֲשֶׁר־יַעֲשֶׂה": "asher-ya'aseh", "יַצְלִיחַ": "yatzliach",
    "לֹא־כֵן": "lo-khen", "הָרְשָׁעִים": "ha-resha'im",
    "אִם־כַּמֹּץ": "im-kammotz", "אֲשֶׁר־תִּדְּפֶנּוּ": "asher-tiddeffennu",
    "רוּחַ": "ruach", "עַל־כֵּן": "al-ken", "לֹא־יָקֻמוּ": "lo-yakumu",
    "בַּמִּשְׁפָּט": "ba-mishpat", "וְחַטָּאִים": "ve-chatta'im",
    "בַּעֲדַת": "ba-adat", "צַדִּיקִים": "tzaddikim",
    "כִּי־יוֹדֵעַ": "ki-yodea", "דֶּרֶךְ": "derekh", "וְדֶרֶךְ": "ve-derekh",
    "תֹּאבֵד": "toved",
}

LANGS = ["en", "es", "pt", "fr", "de", "ru", "ar", "zh", "hi", "id", "ja", "ko"]

# The hand-written English + Spanish originals — the build must reproduce
# them byte-for-byte (they were written first and must never drift).
ORIGINAL_EN_ES = {
    "אַשְׁרֵי": ("happy is", "dichoso es"),
    "הָאִישׁ": ("the man", "el hombre"),
    "אֲשֶׁר": ("who", "que"),
    "לֹא": ("not", "no"),
    "הָלַךְ": ("walked", "anduvo"),
    "בַּעֲצַת": ("in the counsel of", "en el consejo de"),
    "רְשָׁעִים": ("the wicked", "los malvados"),
    "וּבְדֶרֶךְ": ("and in the way of", "y en el camino de"),
    "חַטָּאִים": ("sinners", "pecadores"),
    "עָמָד": ("stood", "estuvo en pie"),
    "וּבְמוֹשַׁב": ("and in the seat of", "y en el asiento de"),
    "לֵצִים": ("scoffers", "burladores"),
    "יָשָׁב": ("sat", "se sentó"),
    "כִּי": ("for", "porque"),
    "אִם": ("but", "sino"),
    "בְּתוֹרַת": ("in the teaching of", "en la ley de"),
    "יְהוָה": ("the LORD", "el SEÑOR"),
    "חֶפְצוֹ": ("his delight", "su deleite"),
    "וּבְתוֹרָתוֹ": ("and in his teaching", "y en su ley"),
    "יֶהְגֶּה": ("he meditates", "medita"),
    "יוֹמָם": ("by day", "de día"),
    "וָלָיְלָה": ("and by night", "y de noche"),
    "וְהָיָה": ("and he will be", "y será"),
    "כְּעֵץ": ("like a tree", "como un árbol"),
    "שָׁתוּל": ("planted", "plantado"),
    "עַל־פַּלְגֵי־מָיִם": ("by streams of water", "junto a corrientes de agua"),
    "פִּרְיוֹ": ("its fruit", "su fruto"),
    "יִתֵּן": ("it gives", "da"),
    "בְּעִתּוֹ": ("in its season", "a su tiempo"),
    "וְעָלֵהוּ": ("and its leaf", "y su hoja"),
    "לֹא־יִבּוֹל": ("does not wither", "no se marchita"),
    "וְכֹל": ("and all", "y todo"),
    "אֲשֶׁר־יַעֲשֶׂה": ("that he does", "que él hace"),
    "יַצְלִיחַ": ("he prospers", "prospera"),
    "לֹא־כֵן": ("not so", "no así"),
    "הָרְשָׁעִים": ("the wicked", "los malvados"),
    "אִם־כַּמֹּץ": ("but like chaff", "sino como el tamo"),
    "אֲשֶׁר־תִּדְּפֶנּוּ": ("that the wind drives away", "que el viento se lleva"),
    "רוּחַ": ("wind", "viento"),
    "עַל־כֵּן": ("therefore", "por tanto"),
    "לֹא־יָקֻמוּ": ("they will not stand", "no se levantarán"),
    "בַּמִּשְׁפָּט": ("in the judgment", "en el juicio"),
    "וְחַטָּאִים": ("and sinners", "y los pecadores"),
    "בַּעֲדַת": ("in the assembly of", "en la congregación de"),
    "צַדִּיקִים": ("the righteous", "los justos"),
    "כִּי־יוֹדֵעַ": ("for he knows", "porque conoce"),
    "דֶּרֶךְ": ("the way of", "el camino de"),
    "וְדֶרֶךְ": ("and the way of", "y el camino de"),
    "תֹּאבֵד": ("will perish", "perecerá"),
}

# Read the meanings CSV (the source of truth for glosses).
TABLE = {}
with open("/home/hatch/workspace/bible-cartridges/tools/psalm001_meanings.csv", encoding="utf-8", newline="") as f:
    for row in csv.DictReader(f):
        h = row["hebrew"]
        if h in TABLE:
            raise SystemExit(f"duplicate Hebrew token in CSV: {h!r}")
        TABLE[h] = {lang: (row[lang] or "").strip() for lang in LANGS}

assert set(TABLE) == set(TRANSLIT), (
    f"CSV tokens != transliteration table: "
    f"missing {set(TRANSLIT) - set(TABLE)}, extra {set(TABLE) - set(TRANSLIT)}"
)
for h, (en, es) in ORIGINAL_EN_ES.items():
    if TABLE[h]["en"] != en or TABLE[h]["es"] != es:
        raise SystemExit(f"EN/ES gloss drifted for {h!r}: "
                         f"{TABLE[h]['en']!r}/{TABLE[h]['es']!r} != {en!r}/{es!r}")

# Build the lexicon in first-appearance order; verses become index arrays.
lexicon = []
index = {}
verse_tokens = []
for v in VERSES:
    toks = v.split(" ")
    for tok in toks:
        if tok not in TABLE:
            raise SystemExit(f"TOKEN MISSING FROM MEANINGS CSV: {tok!r}")
        if tok not in index:
            g = {lang: TABLE[tok][lang] for lang in LANGS if TABLE[tok][lang]}
            index[tok] = len(lexicon)
            lexicon.append({"h": tok, "t": TRANSLIT[tok], "g": g})
    verse_tokens.append([index[tok] for tok in toks])

# Verify: joining the tokens reproduces each verse byte-for-byte.
for v, idxs in zip(VERSES, verse_tokens):
    rebuilt = " ".join(lexicon[i]["h"] for i in idxs)
    assert rebuilt == v, f"verse rebuild mismatch: {rebuilt!r} != {v!r}"

data = {
    "chapter": 1,
    "title": "Psalm 1",
    "languages": LANGS,
    "fallback": "en",
    "verses": verse_tokens,
    "lexicon": lexicon,
    "text": "\n".join(VERSES),  # canonical Hebrew text, verses separated by \n
}

out_path = "/home/hatch/workspace/bible-cartridges/tools/psalm001_data.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=1)
print(f"wrote {out_path}")
print(f"verses: {len(VERSES)} | occurrences: {sum(len(v) for v in verse_tokens)} | unique tokens: {len(lexicon)}")
print(f"languages: {len(LANGS)} | canonical text bytes: {len(data['text'].encode('utf-8'))}")
print(f"EN/ES glosses verified byte-identical to the hand-written originals")
