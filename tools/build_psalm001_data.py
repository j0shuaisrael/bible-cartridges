#!/usr/bin/env python3
"""Build tools/psalm001_data.json — the single source of truth for Psalm 1.

Verses are the pointed Hebrew exactly as supplied (Mechon Mamre).
The lexicon is keyed by UNIQUE space-separated token (49 tokens for Psalm 1):
each entry carries the Hebrew token, an SBL-style transliteration, and a short
plain gloss in every packed language (English + Spanish to start).
Translations are baked here, at build time — the decoder never fetches
anything and pays nothing.

The generator VERIFIES: every token in every verse exists in the table,
and joining the tokens with single spaces reproduces each verse exactly.
"""
import json

VERSES = [
    "אַשְׁרֵי הָאִישׁ אֲשֶׁר לֹא הָלַךְ בַּעֲצַת רְשָׁעִים וּבְדֶרֶךְ חַטָּאִים לֹא עָמָד וּבְמוֹשַׁב לֵצִים לֹא יָשָׁב",
    "כִּי אִם בְּתוֹרַת יְהוָה חֶפְצוֹ וּבְתוֹרָתוֹ יֶהְגֶּה יוֹמָם וָלָיְלָה",
    "וְהָיָה כְּעֵץ שָׁתוּל עַל־פַּלְגֵי־מָיִם אֲשֶׁר פִּרְיוֹ יִתֵּן בְּעִתּוֹ וְעָלֵהוּ לֹא־יִבּוֹל וְכֹל אֲשֶׁר־יַעֲשֶׂה יַצְלִיחַ",
    "לֹא־כֵן הָרְשָׁעִים כִּי אִם־כַּמֹּץ אֲשֶׁר־תִּדְּפֶנּוּ רוּחַ",
    "עַל־כֵּן לֹא־יָקֻמוּ רְשָׁעִים בַּמִּשְׁפָּט וְחַטָּאִים בַּעֲדַת צַדִּיקִים",
    "כִּי־יוֹדֵעַ יְהוָה דֶּרֶךְ צַדִּיקִים וְדֶרֶךְ רְשָׁעִים תֹּאבֵד",
]

# (hebrew, transliteration, english gloss, spanish gloss)
GLOSSES = [
    ("אַשְׁרֵי", "ashrei", "happy is", "dichoso es"),
    ("הָאִישׁ", "ha-ish", "the man", "el hombre"),
    ("אֲשֶׁר", "asher", "who", "que"),
    ("לֹא", "lo", "not", "no"),
    ("הָלַךְ", "halakh", "walked", "anduvo"),
    ("בַּעֲצַת", "ba-atsat", "in the counsel of", "en el consejo de"),
    ("רְשָׁעִים", "resha'im", "the wicked", "los malvados"),
    ("וּבְדֶרֶךְ", "u-ve-derekh", "and in the way of", "y en el camino de"),
    ("חַטָּאִים", "chatta'im", "sinners", "pecadores"),
    ("עָמָד", "amad", "stood", "estuvo en pie"),
    ("וּבְמוֹשַׁב", "u-ve-moshav", "and in the seat of", "y en el asiento de"),
    ("לֵצִים", "letsim", "scoffers", "burladores"),
    ("יָשָׁב", "yashav", "sat", "se sentó"),
    ("כִּי", "ki", "for", "porque"),
    ("אִם", "im", "but", "sino"),
    ("בְּתוֹרַת", "be-torat", "in the teaching of", "en la ley de"),
    ("יְהוָה", "YHWH", "the LORD", "el SEÑOR"),
    ("חֶפְצוֹ", "cheftzo", "his delight", "su deleite"),
    ("וּבְתוֹרָתוֹ", "u-ve-torato", "and in his teaching", "y en su ley"),
    ("יֶהְגֶּה", "yehgeh", "he meditates", "medita"),
    ("יוֹמָם", "yomam", "by day", "de día"),
    ("וָלָיְלָה", "va-laylah", "and by night", "y de noche"),
    ("וְהָיָה", "ve-hayah", "and he will be", "y será"),
    ("כְּעֵץ", "ke-etz", "like a tree", "como un árbol"),
    ("שָׁתוּל", "shatul", "planted", "plantado"),
    ("עַל־פַּלְגֵי־מָיִם", "al-palgei-mayim", "by streams of water", "junto a corrientes de agua"),
    ("פִּרְיוֹ", "piryo", "its fruit", "su fruto"),
    ("יִתֵּן", "yitten", "it gives", "da"),
    ("בְּעִתּוֹ", "be-itto", "in its season", "a su tiempo"),
    ("וְעָלֵהוּ", "ve-alehu", "and its leaf", "y su hoja"),
    ("לֹא־יִבּוֹל", "lo-yibbol", "does not wither", "no se marchita"),
    ("וְכֹל", "ve-khol", "and all", "y todo"),
    ("אֲשֶׁר־יַעֲשֶׂה", "asher-ya'aseh", "that he does", "que él hace"),
    ("יַצְלִיחַ", "yatzliach", "he prospers", "prospera"),
    ("לֹא־כֵן", "lo-khen", "not so", "no así"),
    ("הָרְשָׁעִים", "ha-resha'im", "the wicked", "los malvados"),
    ("אִם־כַּמֹּץ", "im-kammotz", "but like chaff", "sino como el tamo"),
    ("אֲשֶׁר־תִּדְּפֶנּוּ", "asher-tiddeffennu", "that the wind drives away", "que el viento se lleva"),
    ("רוּחַ", "ruach", "wind", "viento"),
    ("עַל־כֵּן", "al-ken", "therefore", "por tanto"),
    ("לֹא־יָקֻמוּ", "lo-yakumu", "they will not stand", "no se levantarán"),
    ("בַּמִּשְׁפָּט", "ba-mishpat", "in the judgment", "en el juicio"),
    ("וְחַטָּאִים", "ve-chatta'im", "and sinners", "y los pecadores"),
    ("בַּעֲדַת", "ba-adat", "in the assembly of", "en la congregación de"),
    ("צַדִּיקִים", "tzaddikim", "the righteous", "los justos"),
    ("כִּי־יוֹדֵעַ", "ki-yodea", "for he knows", "porque conoce"),
    ("דֶּרֶךְ", "derekh", "the way of", "el camino de"),
    ("וְדֶרֶךְ", "ve-derekh", "and the way of", "y el camino de"),
    ("תֹּאבֵד", "toved", "will perish", "perecerá"),
]

TABLE = {h: (t, en, es) for h, t, en, es in GLOSSES}
assert len(TABLE) == len(GLOSSES), "duplicate Hebrew token in gloss table"

# Build the lexicon in first-appearance order; verses become index arrays.
lexicon = []
index = {}
verse_tokens = []
for v in VERSES:
    toks = v.split(" ")
    for tok in toks:
        if tok not in TABLE:
            raise SystemExit(f"TOKEN MISSING FROM GLOSS TABLE: {tok!r}")
        if tok not in index:
            t, en, es = TABLE[tok]
            index[tok] = len(lexicon)
            lexicon.append({"h": tok, "t": t, "g": {"en": en, "es": es}})
    verse_tokens.append([index[tok] for tok in toks])

# Verify: joining the tokens reproduces each verse byte-for-byte.
for v, idxs in zip(VERSES, verse_tokens):
    rebuilt = " ".join(lexicon[i]["h"] for i in idxs)
    assert rebuilt == v, f"verse rebuild mismatch: {rebuilt!r} != {v!r}"

data = {
    "chapter": 1,
    "title": "Psalm 1",
    "languages": ["en", "es"],
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
print(f"canonical text bytes: {len(data['text'].encode('utf-8'))}")
