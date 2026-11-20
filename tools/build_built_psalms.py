#!/usr/bin/env python3
"""Regenerate tools/built-psalms.json: the psalms actually built on disk.

A psalm counts as built when BOTH its chapter data and its cartridge exist:
    tools/psalmNNN_data.json AND psalms/NNN/cartridge.png

The universal encoder (psalms/encode.html) reads this one file to know
which picker entries to enable — one request, no probing, and no console
noise. (Probing for each data file would work too, but the browser logs
one console error per psalm that is not built yet — 149 lines on every
page load — so the manifest is the primary mechanism. If the manifest is
missing, the encoder falls back to probing.)

Re-run after building a psalm (or after deleting one):

    python3 tools/build_built_psalms.py
"""
import json
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    built = []
    for n in range(1, 151):
        nnn = f"{n:03d}"
        data = os.path.join(REPO, "tools", f"psalm{nnn}_data.json")
        cartridge = os.path.join(REPO, "psalms", nnn, "cartridge.png")
        if os.path.exists(data) and os.path.exists(cartridge):
            built.append(n)
    out = {"built": built}
    with open(os.path.join(REPO, "tools", "built-psalms.json"), "w", encoding="utf-8") as f:
        json.dump(out, f)
        f.write("\n")
    print(f"built psalms: {built}")


if __name__ == "__main__":
    main()
