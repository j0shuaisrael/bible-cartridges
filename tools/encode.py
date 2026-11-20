#!/usr/bin/env python3
"""Encode a Bible cartridge PNG (format PSLM v2).

    python3 encode.py --cover psalms/001/cover.png --audio psalms/001/audio.webm \
        --data tools/psalm001_data.json --out psalms/001/cartridge.png

Layout of the cartridge PNG (all lossless, exactly reversible):
  * Visible strip: the top `strip_h` rows of the cover hold the text pack as
    raw RGB bytes (3 bytes per pixel). The strip is at least 16 rows tall so
    it reads as a visible band of code; bytes past the end of the payload
    inside the strip are deterministic filler (seeded from the pack hash) and
    are ignored by the decoder.
  * Invisible LSB layer: the chapter audio is hidden in the lowest bit of
    each colour channel of every pixel BELOW the strip (1 bit x RGB, row
    major). Changing a channel by at most 1/255 is invisible to the eye.

Visible blob layout:
    [0:4]   magic "PSLM"
    [4]     version (2)
    [5:9]   uint32 big-endian header JSON length N
    [9:9+N] header JSON (see below)
    [9+N:]  zlib-compressed text pack (the data JSON: verses as lexicon
            indices + the per-unique-word lexicon with transliteration and
            a baked gloss per packed language + the canonical Hebrew text)

Header JSON:
    {"format": "PSLM", "version": 2, "chapter": 1,
     "languages": ["en", "es"], "fallback": "en",
     "pack_len": <uncompressed pack bytes>, "pack_comp_len": <compressed>,
     "pack_sha256": <hex of the uncompressed pack>,
     "audio_len": <bytes>, "audio_sha256": <hex or null>,
     "audio_format": "opus-webm",
     "strip_h": <rows>, "cover_w": <px>, "cover_h": <px>}

Translations are BAKED IN at build time (one gloss per language per unique
word, stored once per chapter). Decoding is fully offline and free forever:
the decoder reads navigator.language, picks the best matching packed
language, and falls back to English. Adding a language later means adding
one gloss per word at build time — the format needs no redesign.
"""
import argparse
import hashlib
import json
import random
import struct
import sys
import zlib

from PIL import Image

MAGIC = b"PSLM"
VERSION = 2
MIN_STRIP_H = 16  # the code band stays visible as a design element


def build_pack(data_path):
    with open(data_path, encoding="utf-8") as f:
        data = json.load(f)
    pack = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return pack, zlib.compress(pack, 9)


def build_header(pack, comp, audio, strip_h, w, h, data):
    return {
        "format": "PSLM",
        "version": VERSION,
        "chapter": data["chapter"],
        "languages": data["languages"],
        "fallback": data.get("fallback", "en"),
        "pack_len": len(pack),
        "pack_comp_len": len(comp),
        "pack_sha256": hashlib.sha256(pack).hexdigest(),
        "audio_len": len(audio),
        "audio_sha256": hashlib.sha256(audio).hexdigest() if audio else None,
        "audio_format": "opus-webm" if audio else None,
        "strip_h": strip_h,
        "cover_w": w,
        "cover_h": h,
    }


def visible_blob(header, comp):
    hj = json.dumps(header, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return MAGIC + bytes([VERSION]) + struct.pack(">I", len(hj)) + hj + comp


def encode(cover_path, data_path, out_path, audio_path=None):
    cover = Image.open(cover_path).convert("RGB")
    w, h = cover.size
    pack, comp = build_pack(data_path)
    audio = open(audio_path, "rb").read() if audio_path else b""
    with open(data_path, encoding="utf-8") as f:
        data = json.load(f)

    # strip_h depends on the header, which contains strip_h: iterate to a
    # fixed point (header length only changes if the digit count changes).
    strip_h = MIN_STRIP_H
    for _ in range(5):
        header = build_header(pack, comp, audio, strip_h, w, h, data)
        blob = visible_blob(header, comp)
        need = (len(blob) + w * 3 - 1) // (w * 3)
        new_h = max(MIN_STRIP_H, need)
        if new_h == strip_h:
            break
        strip_h = new_h
    else:
        raise SystemExit("strip height did not converge")

    # Audio capacity in the LSB layer below the strip.
    lsb_capacity_bytes = (h - strip_h) * w * 3 // 8
    if len(audio) > lsb_capacity_bytes:
        raise SystemExit(
            f"audio too large for LSB layer: {len(audio)} bytes > "
            f"{lsb_capacity_bytes} available (cover {w}x{h}, strip {strip_h})"
        )

    px = cover.load()

    # 1. Visible strip: blob bytes as RGB pixels, row-major.
    seed = int.from_bytes(hashlib.sha256(pack).digest()[:4], "big")
    rng = random.Random(seed)
    total_strip_bytes = strip_h * w * 3
    strip_bytes = bytearray(blob)
    strip_bytes.extend(rng.randrange(256) for _ in range(total_strip_bytes - len(blob)))
    pos = 0
    for y in range(strip_h):
        for x in range(w):
            r, g, b = px[x, y]
            px[x, y] = (strip_bytes[pos], strip_bytes[pos + 1], strip_bytes[pos + 2])
            pos += 3

    # 2. LSB audio: 1 bit per channel, rows below the strip, MSB first.
    bitpos = 0
    total_bits = len(audio) * 8
    for y in range(strip_h, h):
        for x in range(w):
            if bitpos >= total_bits:
                break
            r, g, b = px[x, y]
            channels = []
            for ch in (r, g, b):
                if bitpos < total_bits:
                    byte = audio[bitpos // 8]
                    bit = (byte >> (7 - bitpos % 8)) & 1
                    channels.append((ch & 0xFE) | bit)
                    bitpos += 1
                else:
                    channels.append(ch)
            px[x, y] = tuple(channels)
        if bitpos >= total_bits:
            break

    cover.save(out_path, format="PNG")
    print(f"wrote {out_path} ({w}x{h}, strip {strip_h} rows)")
    print(f"  text pack: {len(pack)} bytes -> {len(comp)} compressed "
          f"(sha256 {hashlib.sha256(pack).hexdigest()[:12]}...)")
    print(f"  audio: {len(audio)} bytes Opus/WebM "
          f"(sha256 {(hashlib.sha256(audio).hexdigest()[:12] if audio else '-') }...)")
    print(f"  languages packed: {data['languages']} (fallback {data.get('fallback', 'en')})")
    print(f"  LSB capacity: {lsb_capacity_bytes} bytes; used {len(audio)} "
          f"({100.0 * len(audio) / max(lsb_capacity_bytes, 1):.1f}%)")


def main():
    ap = argparse.ArgumentParser(description="Encode a Bible cartridge PNG (PSLM v2).")
    ap.add_argument("--cover", required=True, help="cover art PNG (RGB)")
    ap.add_argument("--data", required=True, help="chapter data JSON (verses + lexicon)")
    ap.add_argument("--audio", help="Opus-in-WebM audio file (optional)")
    ap.add_argument("--out", required=True, help="output cartridge PNG")
    args = ap.parse_args()
    encode(args.cover, args.data, args.out, args.audio)


if __name__ == "__main__":
    main()
