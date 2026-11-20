#!/usr/bin/env python3
"""Decode a Bible cartridge PNG (format PSLM v2 and v3) and verify it.

    python3 decode.py cartridge.png [--out-text text.json] [--out-audio audio.webm]
        [--out-model-palace palace.glb] [--out-model-skybox skybox.glb]

Verifies the magic + version, decompresses the text pack, checks its SHA-256
against the header, extracts the LSB stream below the strip (audio, then
the v3 model sections) and checks every SHA-256. On any mismatch it reports
DAMAGE and exits non-zero; it never returns bytes it cannot prove are the
exact originals.

A v2 cartridge has no models: it verifies fine for text + audio, but it is
INCOMPLETE for the world — the 3D world cannot be built from it, and the
decoder never fetches models from the site to fill the gap. Re-encode as
v3 to make a complete cartridge.
"""
import argparse
import hashlib
import json
import struct
import sys
import zlib

from PIL import Image

MAGIC = b"PSLM"


def read_strip_bytes(px, w, nbytes):
    """Read the first nbytes of the visible strip, row-major, RGB order."""
    out = bytearray()
    rows = (nbytes + w * 3 - 1) // (w * 3)
    for y in range(rows):
        for x in range(w):
            if len(out) >= nbytes:
                # Pixels come in RGB triples: slice, or the caller gets up
                # to 2 stray bytes past the end (this once broke the header
                # parse with a UTF-8 error at the first compressed byte).
                return bytes(out[:nbytes])
            r, g, b = px[x, y]
            out.extend((r, g, b))
    return bytes(out[:nbytes])


def read_lsb_stream(px, w, h, strip_h, nbytes, depth):
    """Read nbytes from the LSB layer below the strip, MSB-first bits,
    `depth` bits per channel."""
    out = bytearray(nbytes)
    bitpos = 0
    total_bits = nbytes * 8
    mask = (1 << depth) - 1
    for y in range(strip_h, h):
        for x in range(w):
            if bitpos >= total_bits:
                return bytes(out)
            r, g, b = px[x, y]
            for ch in (r, g, b):
                if bitpos >= total_bits:
                    return bytes(out)
                chunk = ch & mask
                for b in range(depth - 1, -1, -1):
                    if bitpos >= total_bits:
                        return bytes(out)
                    if (chunk >> b) & 1:
                        out[bitpos // 8] |= 1 << (7 - bitpos % 8)
                    bitpos += 1
    if bitpos < total_bits:
        raise ValueError("cartridge truncated: LSB layer ended before the payload did")
    return bytes(out)


def decode(path):
    img = Image.open(path).convert("RGB")
    w, h = img.size
    px = img.load()

    head = read_strip_bytes(px, w, 9)
    if head[:4] != MAGIC:
        raise ValueError("not a PSLM cartridge (bad magic)")
    version = head[4]
    if version not in (2, 3):
        raise ValueError(f"unsupported PSLM version {version} (this decoder reads v2 and v3)")
    (hlen,) = struct.unpack(">I", head[5:9])
    header = json.loads(read_strip_bytes(px, w, 9 + hlen)[9:])
    if header.get("format") != "PSLM" or header.get("version") != version:
        raise ValueError("header/version mismatch")

    strip_h = header["strip_h"]
    blob_len = 9 + hlen + header["pack_comp_len"]
    blob = read_strip_bytes(px, w, blob_len)
    comp = blob[9 + hlen:]
    pack = zlib.decompress(comp)
    if len(pack) != header["pack_len"]:
        raise ValueError("pack length mismatch — cartridge damaged")
    if hashlib.sha256(pack).hexdigest() != header["pack_sha256"]:
        raise ValueError("pack SHA-256 mismatch — text damaged")

    depth = header.get("lsb_depth", 1)
    models = header.get("models", []) if version == 3 else []
    # Remote models occupy NO bytes in the LSB stream; they are recorded
    # (URL + SHA-256) and fetched only when the world opens, never here.
    embedded = [m for m in models if not m.get("remote")]
    total_lsb = header["audio_len"] + sum(m["stored_len"] for m in embedded)
    stream = read_lsb_stream(px, w, h, strip_h, total_lsb, depth) if total_lsb else b""
    off = 0
    audio = b""
    if header["audio_len"]:
        audio = stream[off:off + header["audio_len"]]; off += header["audio_len"]
        if hashlib.sha256(audio).hexdigest() != header["audio_sha256"]:
            raise ValueError("audio SHA-256 mismatch — audio damaged")

    decoded_models = {}
    remote_models = {}
    for m in models:
        if m.get("remote"):
            remote_models[m["name"]] = m
            continue
        stored = stream[off:off + m["stored_len"]]; off += m["stored_len"]
        raw = zlib.decompress(stored) if m["compressed"] else stored
        if len(raw) != m["len"]:
            raise ValueError(f"model {m['name']} length mismatch: {len(raw)} != {m['len']}")
        if hashlib.sha256(raw).hexdigest() != m["sha256"]:
            raise ValueError(f"model {m['name']} SHA-256 mismatch — model damaged")
        decoded_models[m["name"]] = raw

    return header, json.loads(pack.decode("utf-8")), audio, decoded_models, remote_models


def main():
    ap = argparse.ArgumentParser(description="Decode and verify a PSLM v2/v3 cartridge.")
    ap.add_argument("cartridge", help="cartridge PNG")
    ap.add_argument("--out-text", help="write the decoded text pack JSON here")
    ap.add_argument("--out-audio", help="write the decoded audio here")
    ap.add_argument("--out-model-palace", help="write the decoded palace GLB here")
    ap.add_argument("--out-model-skybox", help="write the decoded skybox GLB here")
    args = ap.parse_args()

    try:
        header, pack, audio, models, remote_models = decode(args.cartridge)
    except (ValueError, zlib.error, json.JSONDecodeError) as e:
        print(f"DAMAGED: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"OK: PSLM v{header['version']} chapter {header['chapter']} "
          f"({header['cover_w']}x{header['cover_h']}, strip {header['strip_h']} rows, "
          f"{header.get('lsb_depth', 1)} LSB)")
    print(f"  languages packed: {header['languages']} (fallback {header['fallback']})")
    print(f"  text pack: {header['pack_len']} bytes, sha256 verified")
    print(f"    verses: {len(pack['verses'])}, unique words: {len(pack['lexicon'])}")
    print(f"  audio: {header['audio_len']} bytes {header['audio_format'] or ''}, "
          f"{'sha256 verified' if header['audio_len'] else 'none packed'}")
    if header["version"] == 3:
        if not header["models"]:
            print("  models: NONE packed (text + audio only) — INCOMPLETE for the world: "
                  "this cartridge cannot render the 3D world, and the decoder "
                  "never fetches models from the site. Re-encode as v3 with models.")
        for m in header["models"]:
            if m.get("remote"):
                print(f"  model {m['name']}: REMOTE {m['url']} "
                      f"({m['len']:,} bytes, sha256 {m['sha256'][:12]}... — not fetched here; "
                      f"verified when the world opens)")
            else:
                raw = models[m["name"]]
                print(f"  model {m['name']}: {m['len']:,} bytes "
                      f"({'zlib, stored ' + str(m['stored_len']) if m['compressed'] else 'raw'}), "
                      f"sha256 verified")
        if remote_models:
            print("  WARNING: this cartridge is NOT fully offline — its world is fetched "
                  "from the URLs above and needs the network. Text and audio are inside "
                  "the image and work offline.")
    else:
        print("  models: NONE packed (PSLM v2) — INCOMPLETE for the world: "
              "this cartridge cannot render the 3D world, and the decoder "
              "never fetches models from the site. Re-encode as v3.")
    if args.out_text:
        with open(args.out_text, "w", encoding="utf-8") as f:
            json.dump(pack, f, ensure_ascii=False, indent=1)
        print(f"  wrote text pack -> {args.out_text}")
    if args.out_audio and audio:
        with open(args.out_audio, "wb") as f:
            f.write(audio)
        print(f"  wrote audio -> {args.out_audio}")
    for name, dest in (("palace", args.out_model_palace), ("skybox", args.out_model_skybox)):
        if dest and name in models:
            with open(dest, "wb") as f:
                f.write(models[name])
            print(f"  wrote model {name} -> {dest}")


if __name__ == "__main__":
    main()
