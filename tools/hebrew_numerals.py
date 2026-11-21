#!/usr/bin/env python3
"""Hebrew numerals for chapter titles (Psalm 1 uses bare 'א', no punctuation).

Same letter tables as Mechon Mamre's own hebNumber() in /js/mtr.js.
15 -> טו and 16 -> טז (never יה / יו, which would spell the divine name).
"""
UNITS = ["", "א", "ב", "ג", "ד", "ה", "ו", "ז", "ח", "ט"]
TENS = ["", "י", "כ", "ל", "מ", "נ", "ס", "ע", "פ", "צ"]
HUNDREDS = ["", "ק", "ר", "ש", "ת"]


def heb_number(n: int) -> str:
    if not 1 <= n <= 150:
        raise ValueError(f"psalm out of range: {n}")
    if n == 15:
        return "טו"
    if n == 16:
        return "טז"
    h, rem = divmod(n, 100)
    t, u = divmod(rem, 10)
    return HUNDREDS[h] + TENS[t] + UNITS[u]


def hebrew_title(n: int) -> str:
    return f"תְּהִלִּים {heb_number(n)}"


if __name__ == "__main__":
    for n in [1, 2, 10, 15, 16, 19, 42, 100, 119, 150]:
        print(n, hebrew_title(n))
