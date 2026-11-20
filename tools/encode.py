#!/usr/bin/env python3
"""Encode a Bible cartridge PNG (format PSLM v3).

    python3 encode.py --cover psalms/001/cover.png --audio psalms/001/audio.webm \\
        --data tools/psalm001_data.json --palace assets/cloud-palace.glb \\
        --skybox assets/skybox.glb --out psalms/001/cartridge.png

Layout of the cartridge PNG (all lossless, exactly reversible):
  * Visible strip: the top `strip_h` rows of the cover hold the text pack as
    raw RGB bytes (3 bytes per pixel). The strip is at least 16 rows tall so
    it reads as a visible band of code; bytes past the end of the payload
    inside the strip are deterministic filler (seeded from the pack hash) and
    are ignored by the decoder.
  * Invisible LSB layer: ONE bitstream below the strip, at `lsb_depth` bits
    per colour channel (1 or 2, chosen as the minimum that fits), row-major,
    MSB-first within each byte. Sections in order: the chapter audio (raw
    Opus/WebM), then each model in header order (stored bytes; zlib-
    compressed only where that actually shrinks them — the palace geometry
    compresses to ~37%, the skybox's embedded JPEG does not, so it is
    stored raw). Changing a channel by at most 1/255 (depth 1) or 3/255
    (depth 2) is invisible to the eye.

Visible blob layout:
    [0:4]   magic "PSLM"
    [4]     version (3)
    [5:9]   uint32 big-endian header JSON length N
    [9:9+N] header JSON (see below)
    [9+N:]  zlib-compressed text pack (the data JSON: verses as lexicon
            indices + the per-unique-word lexicon with transliteration and
            a baked gloss per packed language + the canonical Hebrew text)

Header JSON:
    {"format": "PSLM", "version": 3, "chapter": 1,
     "languages": ["en", "es", ...], "fallback": "en",
     "pack_len": <uncompressed pack bytes>, "pack_comp_len": <compressed>,
     "pack_sha256": <hex of the uncompressed pack>,
     "audio_len": <bytes>, "audio_sha256": <hex or null>,
     "audio_format": "opus-webm",
     "strip_h": <rows>, "cover_w": <px>, "cover_h": <px>,
     "lsb_depth": 1 or 2,
     "models": [{"name": "palace", "len": <GLB bytes>, "sha256": <hex>,
                "stored_len": <bytes in the LSB stream>,
                "compressed": true/false},
               {"name": "skybox", ...}]}

THE MODELS LIVE IN THE IMAGE. The cartridge carries the full palace and
skybox GLBs; the decoder extracts them and builds the world from them.
Nothing is ever fetched from the site — not by the decoder, not by any
viewer page. A cartridge with no models is incomplete: the decoder must
report it, never quietly complete it from assets/ or anywhere else.

CAPACITY (measured for Psalm 1: audio 192,766 + palace stored 291,028 +
skybox stored 2,622,191 = 3,105,985 bytes in the LSB stream):
    cover      depth 1          depth 2
    1024x1024    387,072 B        774,144 B   (cannot hold the models)
    2048x2048  1,560,576 B      3,121,152 B   (fits at depth 2, 99.5% used —
                                               only ~15 KB spare; tight)
    3072x3072  3,520,512 B      7,041,024 B   (fits at depth 1, 88% used)
    4096x4096  6,266,880 B     12,533,760 B   (fits at depth 1, 50% used)
The encoder chooses the minimum depth that fits and REFUSES LOUDLY with
the numbers when no depth fits the cover — it never silently drops the
models, never truncates, and never falls back to fetching them.

COMPRESSION (measured 2026-11-19, zlib level 9, lossless — the decoded
bytes are byte-identical to the originals, so quality is unchanged):
    palace  795,224 -> 291,028 (36.6% — worth compressing)
    skybox 2,697,556 -> 2,622,191 (97.2% — its 2.58 MB is an already-
            compressed embedded JPEG; zlib barely helps, but it is
            smaller, so it is stored compressed)
Draco/meshopt (measured, NOT adopted): Draco gets the palace to 155,876
and the skybox to 2,589,880 (total payload 3,105,985 -> 2,927,956, a 5.7%
saving) — but Draco is LOSSY (quantised geometry; decoded bytes differ),
and the Draco decoder is a ~763 KB JS+WASM pair that would have to be
bundled into the decoder, so the decoder would grow by ~1 MB to save
~178 KB in the cartridge. Not worth it. Anything lossy needs an explicit
opt-in from the person encoding; nothing lossy is applied by default.

FULL QUALITY IS THE DEFAULT: the cartridge holds the complete,
unmodified models, audio and text. Lossless zlib is the only compression
applied by default. No Draco/meshopt, no JPEG re-encode, no lower Opus
bitrate — ever, unless the person encoding explicitly opts in.

SMALL IMAGES (remote models — explicit opt-in only): if the cover cannot
hold the models even at 2 LSBs, the encoder first refuses loudly with
the numbers. The person encoding then has two explicit choices, neither
automatic:
  * --remote-models: the header records the models as remote (their
    stable GitHub Pages URLs) instead of their bytes. The decoder fetches
    them ONLY when the header says remote, verifies length + SHA-256
    against the header, and ALWAYS warns the cartridge is not fully
    offline (its world needs the network).
  * --text-audio-only: encode text + audio only (models: []). The
    resulting cartridge is INCOMPLETE for the world — the decoder reports
    it and never fetches models to fill the gap.
Order of attempts: fit everything in the image first (with lossless
compression); offer the toggle only when the models do not fit.

Translations are BAKED IN at build time (one gloss per language per unique
word, stored once per chapter). Decoding is fully offline and free forever:
the decoder reads navigator.language, picks the best matching packed
language, and falls back to English. Adding a language later means adding
one gloss per word at build time — the format needs no redesign.
"""
import argparse
import hashlib
import json
import math
import random
import struct
import sys
import zlib

from PIL import Image

MAGIC = b"PSLM"
VERSION = 3
MIN_STRIP_H = 16  # the code band stays visible as a design element

# Stable GitHub Pages URLs for the models. Used ONLY when a cartridge is
# encoded with --remote-models (explicit opt-in, default off) because the
# cover is too small to hold the models. The decoder fetches from these
# URLs only when the header records a model as remote.
REMOTE_URLS = {
    "palace": "https://j0shuaisrael.github.io/bible-cartridges/assets/cloud-palace.glb",
    "skybox": "https://j0shuaisrael.github.io/bible-cartridges/assets/skybox.glb",
}


def build_pack(data_path):
    with open(data_path, encoding="utf-8") as f:
        data = json.load(f)
    pack = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return pack, zlib.compress(pack, 9)


def build_model(name, path):
    """Read a GLB; store it zlib-compressed only if that actually shrinks it."""
    raw = open(path, "rb").read()
    comp = zlib.compress(raw, 9)
    if len(comp) < len(raw):
        return {"name": name, "len": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                "stored_len": len(comp), "compressed": True, "_stored": comp}
    return {"name": name, "len": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
            "stored_len": len(raw), "compressed": False, "_stored": raw}


def build_model_remote(name, path):
    """Record a model as remote (explicit opt-in only): no bytes are packed;
    the header carries the URL + the SHA-256 of the full-quality GLB so the
    decoder can verify whatever it fetches."""
    raw = open(path, "rb").read()
    return {"name": name, "len": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
            "remote": True, "url": REMOTE_URLS[name], "_stored": b""}


def header_model_entry(m):
    if m.get("remote"):
        return {k: m[k] for k in ("name", "len", "sha256", "remote", "url")}
    return {k: m[k] for k in ("name", "len", "sha256", "stored_len", "compressed")}


def build_header(pack, comp, audio, models, strip_h, w, h, depth, data):
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
        "lsb_depth": depth,
        "models": [header_model_entry(m) for m in models],
    }


def visible_blob(header, comp):
    hj = json.dumps(header, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return MAGIC + bytes([VERSION]) + struct.pack(">I", len(hj)) + hj + comp


def lsb_capacity(w, h, strip_h, depth):
    return (h - strip_h) * w * 3 * depth // 8


def min_square_side(payload, depth):
    """Smallest square cover side whose LSB layer (minus a 16-row strip)
    holds `payload` bytes at the given depth."""
    s = 16
    while lsb_capacity(s, s, MIN_STRIP_H, depth) < payload:
        s += 1
    return s


def encode(cover_path, data_path, out_path, audio_path, palace_path, skybox_path,
           depth_arg, remote_models=False, text_audio_only=False):
    cover = Image.open(cover_path).convert("RGB")
    w, h = cover.size
    pack, comp = build_pack(data_path)
    audio = open(audio_path, "rb").read() if audio_path else b""
    with open(data_path, encoding="utf-8") as f:
        data = json.load(f)
    embedded = [build_model("palace", palace_path), build_model("skybox", skybox_path)]

    def strip_and_depth(models):
        """Fixed-point strip height + minimum LSB depth that fits for this
        models list. Returns (strip_h, depth, payload); depth is None when
        no depth fits."""
        stream = audio + b"".join(m["_stored"] for m in models)
        payload = len(stream)
        # strip_h depends on the header, which contains strip_h: iterate to
        # a fixed point (header length only changes if the digit count
        # changes). lsb_depth is 1 or 2 either way — one digit — so the
        # header length is identical for both depths and the depth choice
        # can follow the strip.
        strip_h = MIN_STRIP_H
        for _ in range(5):
            header = build_header(pack, comp, audio, models, strip_h, w, h, 1, data)
            blob = visible_blob(header, comp)
            need = (len(blob) + w * 3 - 1) // (w * 3)
            new_h = max(MIN_STRIP_H, need)
            if new_h == strip_h:
                break
            strip_h = new_h
        else:
            raise SystemExit("strip height did not converge")
        if strip_h >= h:
            raise SystemExit(
                f"cover is too small: the text strip alone needs {strip_h} rows of {h} — "
                f"use a larger cover image"
            )
        if depth_arg == "auto":
            depths = [1, 2]
        else:
            depths = [int(depth_arg)]
        for d in depths:
            if payload <= lsb_capacity(w, h, strip_h, d):
                return strip_h, d, payload
        return strip_h, None, payload

    # ORDER OF ATTEMPTS: fit everything in the image first (with lossless
    # compression). Only when the models do not fit do the explicit opt-ins
    # come into play — never automatically, never silently.
    strip_h, depth, payload = strip_and_depth(embedded)
    mode = "embedded"
    models = embedded
    if depth is None:
        cap1 = lsb_capacity(w, h, strip_h, 1)
        cap2 = lsb_capacity(w, h, strip_h, 2)
        if remote_models:
            models = [build_model_remote("palace", palace_path),
                      build_model_remote("skybox", skybox_path)]
            strip_h, depth, payload = strip_and_depth(models)
            if depth is None:
                raise SystemExit(
                    f"PAYLOAD DOES NOT FIT even without the models: audio {len(audio):,} bytes "
                    f"exceeds the LSB capacity of this cover ({w}x{h}, strip {strip_h} rows): "
                    f"{cap1:,} bytes at 1 LSB, {cap2:,} bytes at 2 LSBs. "
                    f"Use a larger cover image."
                )
            mode = "remote"
        elif text_audio_only:
            models = []
            strip_h, depth, payload = strip_and_depth(models)
            if depth is None:
                raise SystemExit(
                    f"PAYLOAD DOES NOT FIT even without the models: audio {len(audio):,} bytes "
                    f"exceeds the LSB capacity of this cover ({w}x{h}, strip {strip_h} rows): "
                    f"{cap1:,} bytes at 1 LSB, {cap2:,} bytes at 2 LSBs. "
                    f"Use a larger cover image."
                )
            mode = "text-audio-only"
        else:
            raise SystemExit(
                f"PAYLOAD DOES NOT FIT: {payload:,} bytes (audio {len(audio):,} + "
                f"palace stored {embedded[0]['stored_len']:,} + skybox stored {embedded[1]['stored_len']:,}) "
                f"exceeds the LSB capacity of this cover ({w}x{h}, strip {strip_h} rows): "
                f"{cap1:,} bytes at 1 LSB, {cap2:,} bytes at 2 LSBs. "
                f"Use a cover at least {min_square_side(payload, 2)}x{min_square_side(payload, 2)} "
                f"px for 2 LSBs, or {min_square_side(payload, 1)}x{min_square_side(payload, 1)} px for 1 LSB. "
                f"The models are never dropped silently. Two explicit choices: "
                f"re-run with --remote-models (the cartridge is encoded with text + audio in the image, "
                f"but its world will need the network), or --text-audio-only (the cartridge will be "
                f"incomplete for the world). A bigger cover image is the fully-offline option."
            )
    header = build_header(pack, comp, audio, models, strip_h, w, h, depth, data)
    blob = visible_blob(header, comp)
    capacity = lsb_capacity(w, h, strip_h, depth)
    stream = audio + b"".join(m["_stored"] for m in models)

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

    # 2. LSB stream: audio then models, `depth` bits per channel, rows below
    # the strip, MSB first within each byte. Each channel takes the next
    # `depth` stream bits, first bit into the highest of them.
    mask = (1 << depth) - 1
    bitpos = 0
    total_bits = len(stream) * 8
    for y in range(strip_h, h):
        for x in range(w):
            if bitpos >= total_bits:
                break
            r, g, b = px[x, y]
            channels = []
            for ch in (r, g, b):
                if bitpos >= total_bits:
                    channels.append(ch)
                    continue
                chunk = 0
                for _ in range(depth):
                    if bitpos < total_bits:
                        byte = stream[bitpos // 8]
                        chunk = (chunk << 1) | ((byte >> (7 - bitpos % 8)) & 1)
                        bitpos += 1
                    else:
                        chunk <<= 1
                channels.append((ch & ~mask) | chunk)
            px[x, y] = tuple(channels)
        if bitpos >= total_bits:
            break

    cover.save(out_path, format="PNG")
    print(f"wrote {out_path} ({w}x{h}, strip {strip_h} rows, PSLM v{VERSION}, {depth} LSB)")
    print(f"  text pack: {len(pack)} bytes -> {len(comp)} compressed "
          f"(sha256 {hashlib.sha256(pack).hexdigest()[:12]}...)")
    print(f"  audio: {len(audio)} bytes Opus/WebM "
          f"(sha256 {(hashlib.sha256(audio).hexdigest()[:12] if audio else '-') }...)")
    if mode == "embedded":
        for m in models:
            print(f"  model {m['name']}: {m['len']:,} bytes -> {m['stored_len']:,} stored "
                  f"({'zlib' if m['compressed'] else 'raw'}, "
                  f"sha256 {m['sha256'][:12]}...)")
        if remote_models:
            print("  note: --remote-models was given, but the models fit in the image, "
                  "so they were packed in — remote was not needed.")
    elif mode == "remote":
        print("  WARNING: this cartridge is NOT fully offline. The cover was too small "
              "to hold the models, so they are recorded as remote (explicit opt-in):")
        for m in models:
            print(f"  model {m['name']}: REMOTE {m['url']} "
                  f"({m['len']:,} bytes, sha256 {m['sha256'][:12]}... — verified on fetch)")
        print("  The decoder will fetch these URLs when the world opens, and will warn "
              "that the cartridge needs the network. A bigger cover image is the "
              "fully-offline option.")
    else:  # text-audio-only
        print("  WARNING: this cartridge is INCOMPLETE for the world — it carries text "
              "+ audio only, no models. The decoder will report it incomplete and will "
              "never fetch models to fill the gap. Re-encode with a bigger cover image "
              "(or --remote-models) for the full world.")
    print(f"  languages packed: {data['languages']} (fallback {data.get('fallback', 'en')})")
    print(f"  LSB capacity at {depth} bit(s): {capacity:,} bytes; payload {payload:,} "
          f"({100.0 * payload / capacity:.1f}%)")


def main():
    ap = argparse.ArgumentParser(description="Encode a Bible cartridge PNG (PSLM v3).")
    ap.add_argument("--cover", required=True, help="cover art PNG (RGB)")
    ap.add_argument("--data", required=True, help="chapter data JSON (verses + lexicon)")
    ap.add_argument("--audio", help="Opus-in-WebM audio file (optional)")
    ap.add_argument("--palace", required=True, help="palace GLB (packed into the image)")
    ap.add_argument("--skybox", required=True, help="skybox GLB, complete file (packed into the image)")
    ap.add_argument("--out", required=True, help="output cartridge PNG")
    ap.add_argument("--lsb-depth", default="auto", choices=["auto", "1", "2"],
                    help="LSB bits per channel: auto = minimum depth that fits (default)")
    ap.add_argument("--remote-models", action="store_true",
                    help="EXPLICIT OPT-IN, used only when the cover is too small to hold "
                         "the models: record the models as remote GitHub Pages URLs in "
                         "the header instead of packing them. The decoder fetches them "
                         "only when the header says remote, verifies their SHA-256, and "
                         "always warns the cartridge is not fully offline. Ignored when "
                         "the models fit in the image (they are packed in instead).")
    ap.add_argument("--text-audio-only", action="store_true",
                    help="EXPLICIT OPT-IN, used only when the cover is too small to hold "
                         "the models: encode text + audio only, no models. The resulting "
                         "cartridge is INCOMPLETE for the world; the decoder reports it "
                         "and never fetches models to fill the gap.")
    args = ap.parse_args()
    encode(args.cover, args.data, args.out, args.audio, args.palace, args.skybox,
           args.lsb_depth, remote_models=args.remote_models,
           text_audio_only=args.text_audio_only)


if __name__ == "__main__":
    main()
