#!/usr/bin/env python3
"""Decode a Bible cartridge PNG (format PSLM v2) and verify it.

    python3 decode.py cartridge.png [--out-text text.json] [--out-audio audio.webm]

Verifies the magic + version, decompresses the text pack, checks its SHA-256
against the header, extracts the LSB audio below the strip and checks its
SHA-256 too. On any mismatch it reports DAMAGE and exits non-zero; it never
returns bytes it cannot prove are the exact originals.
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


def read_lsb_audio(px, w, h, strip_h, nbytes):
    """Read nbytes from the LSB layer below the strip, MSB-first bits."""
    out = bytearray(nbytes)
    bitpos = 0
    total_bits = nbytes * 8
    for y in range(strip_h, h):
        for x in range(w):
            if bitpos >= total_bits:
                return bytes(out)
            r, g, b = px[x, y]
            for ch in (r, g, b):
                if bitpos >= total_bits:
                    return bytes(out)
                if ch & 1:
                    out[bitpos // 8] |= 1 << (7 - bitpos % 8)
                bitpos += 1
    if bitpos < total_bits:
        raise ValueError("cartridge truncated: LSB layer ended before audio did")
    return bytes(out)


def decode(path):
    img = Image.open(path).convert("RGB")
    w, h = img.size
    px = img.load()

    head = read_strip_bytes(px, w, 9)
    if head[:4] != MAGIC:
        raise ValueError("not a PSLM cartridge (bad magic)")
    version = head[4]
    if version != 2:
        raise ValueError(f"unsupported PSLM version {version} (this decoder reads v2)")
    (hlen,) = struct.unpack(">I", head[5:9])
    header = json.loads(read_strip_bytes(px, w, 9 + hlen)[9:])

    strip_h = header["strip_h"]
    blob_len = 9 + hlen + header["pack_comp_len"]
    blob = read_strip_bytes(px, w, blob_len)
    comp = blob[9 + hlen:]
    pack = zlib.decompress(comp)
    if len(pack) != header["pack_len"]:
        raise ValueError("pack length mismatch — cartridge damaged")
    if hashlib.sha256(pack).hexdigest() != header["pack_sha256"]:
        raise ValueError("pack SHA-256 mismatch — text damaged")

    audio = b""
    if header["audio_len"]:
        audio = read_lsb_audio(px, w, h, strip_h, header["audio_len"])
        if hashlib.sha256(audio).hexdigest() != header["audio_sha256"]:
            raise ValueError("audio SHA-256 mismatch — audio damaged")

    return header, json.loads(pack.decode("utf-8")), audio


def main():
    ap = argparse.ArgumentParser(description="Decode and verify a PSLM v2 cartridge.")
    ap.add_argument("cartridge", help="cartridge PNG")
    ap.add_argument("--out-text", help="write the decoded text pack JSON here")
    ap.add_argument("--out-audio", help="write the decoded audio here")
    args = ap.parse_args()

    try:
        header, pack, audio = decode(args.cartridge)
    except (ValueError, zlib.error, json.JSONDecodeError) as e:
        print(f"DAMAGED: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"OK: PSLM v{header['version']} chapter {header['chapter']} "
          f"({header['cover_w']}x{header['cover_h']}, strip {header['strip_h']} rows)")
    print(f"  languages packed: {header['languages']} (fallback {header['fallback']})")
    print(f"  text pack: {header['pack_len']} bytes, sha256 verified")
    print(f"    verses: {len(pack['verses'])}, unique words: {len(pack['lexicon'])}")
    print(f"  audio: {header['audio_len']} bytes {header['audio_format'] or ''}, "
          f"{'sha256 verified' if header['audio_len'] else 'none packed'}")
    if args.out_text:
        with open(args.out_text, "w", encoding="utf-8") as f:
            json.dump(pack, f, ensure_ascii=False, indent=1)
        print(f"  wrote text pack -> {args.out_text}")
    if args.out_audio and audio:
        with open(args.out_audio, "wb") as f:
            f.write(audio)
        print(f"  wrote audio -> {args.out_audio}")


if __name__ == "__main__":
    main()
