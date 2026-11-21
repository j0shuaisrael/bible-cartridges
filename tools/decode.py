#!/usr/bin/env python3
"""Decode a Bible cartridge PNG (format PSLM v2, v3 and v4) and verify it.

    python3 decode.py cartridge.png [--out-text text.json] [--out-audio audio.webm]
        [--out-model-palace palace.glb] [--out-model-skybox skybox.glb]

Verifies the magic + version, decompresses the text pack, checks its SHA-256
against the header, extracts the audio and the model sections and checks
every SHA-256. On any mismatch it reports DAMAGE and exits non-zero; it
never returns bytes it cannot prove are the exact originals.

LAYOUTS (tried in this order; the header is fully validated — version,
header-length bounds, JSON parse, format/version match, every SHA-256 —
before either layout is trusted):
  * v3 (and v2): a visible strip at the top of the image holds the header
    blob (magic + version + header length + header JSON + zlib text pack)
    as raw RGB pixels; the audio and models live in ONE LSB bitstream
    below the strip, at lsb_depth bits per channel.
  * v4: the ENTIRE payload — header blob, audio, models — lives in ONE
    LSB bitstream starting at pixel (0, 0), at lsb_depth bits per channel.
    There is no strip: a v4 cartridge differs from its cover only in the
    least-significant bits, and no row of the cover is lost. The depth is
    not in the open: the decoder reads the first 9 bytes at depth 1, and
    if they do not spell PSLM, at depth 2; the version byte then says 4.

A v2 cartridge has no models: it verifies fine for text + audio, but it is
INCOMPLETE for the world — the 3D world cannot be built from it, and the
decoder never fetches models from the site to fill the gap. Re-encode as
v4 to make a complete cartridge.

LSB READING: the bitstream is read with numpy when it is available
(vectorised — seconds per cartridge instead of a minute); without numpy
the same layout is read by the pure-Python loop below it. The two paths
return byte-identical results (checked on Psalms 1 and 119).
"""
import argparse
import hashlib
import json
import struct
import sys
import zlib

from PIL import Image

try:
    import numpy as _np
except ImportError:  # pragma: no cover - numpy is installed here; the
    _np = None       # fallback keeps the tools working without it.

MAGIC = b"PSLM"
# A header longer than this is not a PSLM header (real ones are ~500 B);
# the bound stops a corrupt length field from causing a huge read.
MAX_HEADER_LEN = 1_000_000


class NotThisFormat(Exception):
    """The layout's magic did not match — try the other layout."""


def read_strip_bytes(px, w, nbytes):
    """Read the first nbytes of the visible strip (v2/v3), row-major, RGB order."""
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


def _read_lsb_numpy(raw, w, h, start_row, nbytes, depth):
    """Read nbytes from the LSB layer of the flat RGB bytes `raw`, starting
    at row `start_row`, MSB-first bits, `depth` bits per channel."""
    ch = _np.frombuffer(raw, dtype=_np.uint8)
    start = start_row * w * 3
    if depth == 1:
        need = nbytes * 8
        if start + need > ch.size:
            raise ValueError("cartridge truncated: LSB layer ended before the payload did")
        return _np.packbits(ch[start:start + need] & 1).tobytes()
    need = nbytes * 4
    if start + need > ch.size:
        raise ValueError("cartridge truncated: LSB layer ended before the payload did")
    chunk = ch[start:start + need] & 3
    bits = _np.empty(nbytes * 8, dtype=_np.uint8)
    bits[0::2] = (chunk >> 1) & 1
    bits[1::2] = chunk & 1
    return _np.packbits(bits).tobytes()


def _read_lsb_python(px, w, h, start_row, nbytes, depth):
    """Pure-Python fallback for the same read (no numpy)."""
    out = bytearray(nbytes)
    bitpos = 0
    total_bits = nbytes * 8
    mask = (1 << depth) - 1
    for y in range(start_row, h):
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


def read_lsb_stream(raw, px, w, h, start_row, nbytes, depth):
    """Read nbytes from the LSB layer starting at row `start_row`."""
    if nbytes == 0:
        return b""
    if _np is not None:
        return _read_lsb_numpy(raw, w, h, start_row, nbytes, depth)
    return _read_lsb_python(px, w, h, start_row, nbytes, depth)


def _parse_header(head):
    """Validate the 9-byte intro (magic + version + BE header length) and
    return (version, header-length). Raises NotThisFormat when the magic
    does not match, ValueError when the magic matched but the intro is bad."""
    if head[:4] != MAGIC:
        raise NotThisFormat("no PSLM magic in this layout")
    version = head[4]
    (hlen,) = struct.unpack(">I", head[5:9])
    if hlen == 0 or hlen > MAX_HEADER_LEN:
        raise ValueError(f"header length {hlen} out of bounds — cartridge damaged")
    return version, hlen


def _finish(header, comp, stream):
    """Verify the text pack, audio and models from the already-read bytes.
    Returns (header, pack, audio, models, remote_models)."""
    pack = zlib.decompress(comp)
    if len(pack) != header["pack_len"]:
        raise ValueError("pack length mismatch — cartridge damaged")
    if hashlib.sha256(pack).hexdigest() != header["pack_sha256"]:
        raise ValueError("pack SHA-256 mismatch — text damaged")
    pack_json = json.loads(pack.decode("utf-8"))

    off = 0
    audio = b""
    if header["audio_len"]:
        audio = stream[off:off + header["audio_len"]]; off += header["audio_len"]
        if len(audio) != header["audio_len"]:
            raise ValueError("cartridge truncated: audio runs past the bitstream")
        if hashlib.sha256(audio).hexdigest() != header["audio_sha256"]:
            raise ValueError("audio SHA-256 mismatch — audio damaged")

    models = header.get("models", [])
    decoded_models = {}
    remote_models = {}
    for m in models:
        if m.get("remote"):
            remote_models[m["name"]] = m
            continue
        stored = stream[off:off + m["stored_len"]]; off += m["stored_len"]
        if len(stored) != m["stored_len"]:
            raise ValueError(f"cartridge truncated: model {m['name']} runs past the bitstream")
        raw = zlib.decompress(stored) if m["compressed"] else stored
        if len(raw) != m["len"]:
            raise ValueError(f"model {m['name']} length mismatch: {len(raw)} != {m['len']}")
        if hashlib.sha256(raw).hexdigest() != m["sha256"]:
            raise ValueError(f"model {m['name']} SHA-256 mismatch — model damaged")
        decoded_models[m["name"]] = raw
    if off != len(stream):
        raise ValueError("bitstream length mismatch — cartridge damaged")
    return header, pack_json, audio, decoded_models, remote_models


def _decode_v3(px, raw, w, h):
    """v2/v3 layout: header blob in the visible strip, audio + models in
    the LSB layer below the strip."""
    head = read_strip_bytes(px, w, 9)
    version, hlen = _parse_header(head)
    if version not in (2, 3):
        raise ValueError(f"unsupported PSLM version {version} (this layout reads v2 and v3)")
    header = json.loads(read_strip_bytes(px, w, 9 + hlen)[9:])
    if header.get("format") != "PSLM" or header.get("version") != version:
        raise ValueError("header/version mismatch")

    strip_h = header["strip_h"]
    blob_len = 9 + hlen + header["pack_comp_len"]
    blob = read_strip_bytes(px, w, blob_len)
    comp = blob[9 + hlen:]

    depth = header.get("lsb_depth", 1)
    models = header.get("models", []) if version == 3 else []
    # Remote models occupy NO bytes in the LSB stream; they are recorded
    # (URL + SHA-256) and fetched only when the world opens, never here.
    embedded = [m for m in models if not m.get("remote")]
    total_lsb = header["audio_len"] + sum(m["stored_len"] for m in embedded)
    stream = read_lsb_stream(raw, px, w, h, strip_h, total_lsb, depth)
    return _finish(header, comp, stream)


def _extract_parts(header, data):
    """Role-blind extraction: split the bytes after the header JSON into
    the parts the header lists, in listed order, and verify each part's
    SHA-256 against its stored bytes. Knows nothing about what any part
    IS — only its name, length, hash and encoding. Remote parts occupy
    no bytes here; they are recorded for the caller."""
    parts = {}
    remote_parts = {}
    off = 0
    for p in header["parts"]:
        if p.get("remote"):
            remote_parts[p["name"]] = p
            continue
        chunk = data[off:off + p["len"]]
        if len(chunk) != p["len"]:
            raise ValueError(f"cartridge truncated: part {p['name']!r} runs past the bitstream")
        if hashlib.sha256(chunk).hexdigest() != p["sha256"]:
            raise ValueError(f"part {p['name']!r} SHA-256 mismatch — part damaged")
        parts[p["name"]] = chunk
        off += p["len"]
    if off != len(data):
        raise ValueError("bitstream length mismatch — cartridge damaged")
    return parts, remote_parts


def _resolve_parts(header, parts):
    """Renderer-side role resolution, AFTER extraction: look the parts up
    by name and turn them into the chapter's text, audio, scene and
    models. The text part is zlib-compressed JSON; the audio part is
    played as-is; the world part is the scene recipe JSON (see
    tools/scene.json — the decoder builds the world from it, using only
    a 3D engine); any other part is a model, decompressed per its
    encoding marker. (The zlib stream's own Adler-32 verifies each
    decompression; the stored bytes were already SHA-256-verified by
    _extract_parts.)"""
    if "text" not in parts:
        raise ValueError("v4 cartridge has no part named 'text' — cartridge damaged")
    pack = json.loads(zlib.decompress(parts["text"]).decode("utf-8"))
    audio = parts.get("audio", b"")
    world = None
    if "world" in parts:
        try:
            world = json.loads(parts["world"].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise ValueError(f"world part is not valid JSON — cartridge damaged ({e})")
    models = {}
    for p in header["parts"]:
        name = p["name"]
        if name in ("text", "audio", "world") or name not in parts:
            continue
        chunk = parts[name]
        raw = zlib.decompress(chunk) if p.get("encoding") == "zlib" else chunk
        models[name] = raw
    return pack, audio, models, world


def _decode_v4(px, raw, w, h):
    """v4 layout: the whole bitstream (header blob, then the parts the
    header lists, in listed order) in the LSB layer from pixel (0, 0).
    The depth is found by trying 1, then 2."""
    for depth in (1, 2):
        head = read_lsb_stream(raw, px, w, h, 0, 9, depth)
        if head[:4] != MAGIC:
            continue
        # The magic matched at this depth: this IS the layout — any
        # failure from here on is damage, not the wrong layout.
        version, hlen = _parse_header(head)
        if version != 4:
            raise ValueError(f"unsupported PSLM version {version} (this layout reads v4)")
        header = json.loads(read_lsb_stream(raw, px, w, h, 0, 9 + hlen, depth)[9:])
        if header.get("format") != "PSLM" or header.get("version") != 4:
            raise ValueError("header/version mismatch")
        if not isinstance(header.get("parts"), list) or not header["parts"]:
            raise ValueError("v4 header has no parts list — cartridge damaged")
        # The whole bitstream: header blob + the parts, in listed order.
        total = 9 + hlen + sum(p["len"] for p in header["parts"] if "remote" not in p)
        buf = read_lsb_stream(raw, px, w, h, 0, total, depth)
        parts, remote_parts = _extract_parts(header, buf[9 + hlen:])
        pack, audio, models, world = _resolve_parts(header, parts)
        return header, pack, audio, models, remote_parts, world
    raise NotThisFormat("no PSLM magic in the LSB layer at depth 1 or 2")


def decode(path):
    img = Image.open(path).convert("RGB")
    w, h = img.size
    raw = img.tobytes()
    px = img.load()

    # v3 first (the 150 live cartridges are v3 until rebuilt), then v4.
    # A layout whose magic matched but whose validation failed is reported
    # as damage; a layout whose magic never matched is simply not this
    # cartridge's layout.
    v3_err = None
    try:
        header, pack, audio, models, remote_models = _decode_v3(px, raw, w, h)
        return header, pack, audio, models, remote_models, None  # v3 has no world part
    except NotThisFormat:
        pass
    except Exception as e:
        v3_err = e
    try:
        return _decode_v4(px, raw, w, h)
    except NotThisFormat:
        pass
    except Exception as e:
        raise e  # v4 magic matched: damaged v4, not a wrong guess
    if v3_err is not None:
        raise v3_err
    raise ValueError("not a PSLM cartridge (bad magic)")


def main():
    ap = argparse.ArgumentParser(description="Decode and verify a PSLM v2/v3/v4 cartridge.")
    ap.add_argument("cartridge", help="cartridge PNG")
    ap.add_argument("--out-text", help="write the decoded text pack JSON here")
    ap.add_argument("--out-audio", help="write the decoded audio here")
    ap.add_argument("--out-world", help="write the decoded world (scene recipe) JSON here")
    ap.add_argument("--out-model-palace", help="write the decoded palace GLB here")
    ap.add_argument("--out-model-skybox", help="write the decoded skybox GLB here")
    args = ap.parse_args()

    try:
        header, pack, audio, models, remote_models, world = decode(args.cartridge)
    except (ValueError, zlib.error, json.JSONDecodeError, IndexError, struct.error) as e:
        print(f"DAMAGED: {e}", file=sys.stderr)
        sys.exit(1)

    version = header["version"]
    layout = "no strip" if version == 4 else f"strip {header['strip_h']} rows"
    print(f"OK: PSLM v{version} chapter {header['chapter']} "
          f"({header['cover_w']}x{header['cover_h']}, {layout}, "
          f"{header.get('lsb_depth', 1)} LSB)")
    print(f"  languages packed: {header['languages']} (fallback {header['fallback']})")
    print(f"  text pack: {len(json.dumps(pack, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))} bytes, sha256 verified")
    print(f"    verses: {len(pack['verses'])}, unique words: {len(pack['lexicon'])}")
    print(f"  audio: {len(audio)} bytes {header.get('audio_format') or ''}, "
          f"{'sha256 verified' if audio else 'none packed'}")
    if version == 4:
        # The generic parts list: each part verified by stored SHA-256.
        for p in header["parts"]:
            if p.get("remote"):
                print(f"  part {p['name']}: REMOTE {p['url']} "
                      f"({p['len']:,} bytes, sha256 {p['sha256'][:12]}... — not fetched here; "
                      f"verified when the world opens)")
            else:
                print(f"  part {p['name']}: {p['len']:,} bytes stored ({p['encoding']}), "
                      f"sha256 verified")
        model_parts = [p for p in header["parts"] if p["name"] not in ("text", "audio", "world")]
        if world is not None:
            print(f"  world part: scene recipe v{world.get('version')} present, sha256 verified "
                  f"— the decoder builds the 3D world from this part alone")
        else:
            print("  world part: NONE (cartridge predates the scene part) — the decoder "
                  "falls back to its built-in recipe for this cartridge")
        if not model_parts:
            print("  models: NONE packed (text + audio only) — INCOMPLETE for the world: "
                  "this cartridge cannot render the 3D world, and the decoder "
                  "never fetches models from the site. Re-encode as v4 with models.")
        if remote_models:
            print("  WARNING: this cartridge is NOT fully offline — its world is fetched "
                  "from the URLs above and needs the network. Text and audio are inside "
                  "the image and work offline.")
    elif version == 3:
        if not header["models"]:
            print("  models: NONE packed (text + audio only) — INCOMPLETE for the world: "
                  "this cartridge cannot render the 3D world, and the decoder "
                  "never fetches models from the site. Re-encode as v4 with models.")
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
              "never fetches models from the site. Re-encode as v4.")
    if args.out_text:
        with open(args.out_text, "w", encoding="utf-8") as f:
            json.dump(pack, f, ensure_ascii=False, indent=1)
        print(f"  wrote text pack -> {args.out_text}")
    if args.out_audio and audio:
        with open(args.out_audio, "wb") as f:
            f.write(audio)
        print(f"  wrote audio -> {args.out_audio}")
    if args.out_world and world is not None:
        with open(args.out_world, "w", encoding="utf-8") as f:
            json.dump(world, f, ensure_ascii=False, indent=1, sort_keys=True)
        print(f"  wrote world (scene recipe) -> {args.out_world}")
    for name, dest in (("palace", args.out_model_palace), ("skybox", args.out_model_skybox)):
        if dest and name in models:
            with open(dest, "wb") as f:
                f.write(models[name])
            print(f"  wrote model {name} -> {dest}")


if __name__ == "__main__":
    main()
