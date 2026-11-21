#!/usr/bin/env python3
"""Encode a Bible cartridge PNG (format PSLM v4).

    python3 encode.py --cover psalms/001/cover.png --audio psalms/001/audio.webm \\
        --data tools/psalm001_data.json --palace assets/cloud-palace.glb \\
        --skybox assets/skybox.glb --out psalms/001/cartridge.png

Layout of the cartridge PNG (all lossless, exactly reversible):
  * ONE LSB bitstream, starting at pixel (0, 0), row-major, at `lsb_depth`
    bits per colour channel (1 or 2, chosen as the minimum that fits),
    MSB-first within each byte. Sections in order, back to back, with no
    separators: the header blob (magic + version + header length + header
    JSON), then the parts the header lists, in the order it lists them.
    Each part's stored bytes are zlib-compressed only where that actually
    shrinks them — the text pack and the palace geometry compress well,
    the skybox's embedded JPEG does not, so it is stored raw. Changing a
    channel by at most 1/255 (depth 1) or 3/255 (depth 2) is invisible
    to the eye.
  * There is NO visible strip. The cartridge differs from its cover ONLY
    in the least-significant bits of its pixels (at most 1/255 per channel
    at depth 1, 3/255 at depth 2), and no row of the cover is lost — the
    top rows of the photo survive in the cartridge. (PSLM v3 wrote the
    header + text pack as a visible band of code over the top rows; v4
    restores the original spec: everything lives in the LSBs.)

Header blob layout (the first section of the bitstream):
    [0:4]   magic "PSLM"
    [4]     version (4)
    [5:9]   uint32 big-endian header JSON length N
    [9:9+N] header JSON (see below)
    [9+N:]  the parts, in the order the header lists them.

Header JSON — a generic, self-describing parts list. The extractor
needs only version, lsb_depth and parts; everything else is metadata
it ignores. Roles (which part is the text, the audio, a model) are just
names the RENDERER uses afterwards — extraction and verification stay
role-blind:
    {"format": "PSLM", "version": 4,
     "lsb_depth": 1 or 2,
     "parts": [{"name": "text", "len": <stored bytes>,
                "sha256": <hex of the stored bytes>, "encoding": "zlib"},
               {"name": "audio", "len": <bytes>, "sha256": <hex>,
                "encoding": "raw"},
               {"name": "world", "len": <bytes>, "sha256": <hex>,
                "encoding": "raw"},
               {"name": "palace", "len": <stored bytes>, "sha256": <hex>,
                "encoding": "zlib"},
               {"name": "skybox", "len": <stored bytes>, "sha256": <hex>,
                "encoding": "zlib"}],
     "strip_h": 0, "cover_w": <px>, "cover_h": <px>,
     "chapter": 1, "languages": ["en", "es", ...], "fallback": "en",
     "audio_format": "opus-webm"}
Each part: name (an opaque label — the renderer looks parts up by
name), len (how many bytes it occupies in the bitstream), sha256 (of
the STORED bytes, exactly as they sit in the bitstream), encoding
("zlib" — a zlib-wrapped DEFLATE stream, decompress after verifying —
or "raw" — the bytes as-is). A part may instead be remote:
{"name": "palace", "len": <GLB bytes>, "sha256": <hex of the GLB>,
 "encoding": "raw", "remote": true, "url": "https://..."} — it occupies
no bytes in the bitstream; the renderer fetches it only when the header
says remote and verifies len + sha256 exactly as for an embedded part.
`strip_h` is kept (always 0 in v4) so the header shape is stable across
versions: it is the row where the LSB bitstream starts — row 0 in v4.
A v3 header has strip_h >= 16; the decoder tells the versions apart by
the version byte, not by this field.
The metadata (chapter, languages, fallback, cover_w, cover_h,
audio_format) is for the renderer: the chapter number, the gloss
languages packed, the fallback language, the cover dimensions, and the
audio container format. The extractor ignores all of it.

THE MODELS LIVE IN THE IMAGE. The cartridge carries the full palace and
skybox GLBs; the decoder extracts them and builds the world from them.
Nothing is ever fetched from the site — not by the decoder, not by any
viewer page. A cartridge with no models is incomplete: the decoder must
report it, never quietly complete it from assets/ or anywhere else.

THE SCENE RECIPE LIVES IN THE IMAGE TOO. The parts list carries a
"world" part: the scene recipe as JSON, exactly the bytes of
tools/scene.json (built by tools/build_scene.py), stored raw — raw keeps
the part byte-identical across encoders. It gets a SHA-256 in the header
like every other part. The decoder builds the world from the cartridge's
own scene part, using only a 3D engine — it needs no WORLD section in
the spec to know the scene. The scene part is a STANDARD glTF 2.0 scene
document (key "gltf": nodes, meshes, PBR materials, perspective camera,
KHR_lights_punctual sun, palace referenced by the PSLM_part extension)
plus plain-data sections for what glTF core does not name (sky
background/environment, dynamic scroll-text layout, animation formula,
controls, audio, renderer settings). No engine names, no function names,
nothing that only makes sense with one decoder's source. The spec's
WORLD section defines the schema of that JSON, not its values: the
cartridge is the single source of truth for the scene. Gaps, all named
in the spec: the hemisphere light is not in glTF, so the ambient
contribution is image-based lighting from the sky environment (the old
neutral studio-room environment is gone — the world is now fully
contained in the cartridge); the sky background is not in glTF core, so
the panorama from the skybox part is used directly as the equirect
background/environment (the skybox GLB's sphere mesh is not rendered —
its radius exceeds the camera far plane); the scroll-text texture is
dynamic, referenced by the plain name "scroll-text" with its layout data
in the scene part; controls are plain interaction data, not glTF.

THE PNG TEACHES ITSELF. The encoder also writes a plain-text PNG
metadata chunk (tEXt, keyword "PSLM") into the cartridge file, carrying
the whole bootstrap in one paragraph: the bit order, the depth fallback,
the stream layout, the JSON header, the hashes, and glTF for the scene.
It touches no pixels and is readable by any tool that opens the file,
even a hex dump. It is a bootstrap aid ONLY — nothing depends on it.
The LSB bitstream is fully self-teaching on its own: it opens with
readable ASCII (magic PSLM, then the JSON header), so anyone who reads
the LSB plane — the standard first place to look for hidden data in an
image — sees readable instructions, not noise. Strip every ancillary
chunk from a cartridge and it still decodes fully; that is the proof.
The chunk text is BOOTSTRAP_TEXT below; the full spec documents it.

CAPACITY — the whole image is the bitstream (w*h*3*depth/8 bytes):
    cover      depth 1          depth 2
    1024x1024    393,216 B        786,432 B   (cannot hold the models)
    2048x2048  1,572,864 B      3,145,728 B
    3072x3072  3,538,944 B      7,077,888 B   (fits Psalm 1 at depth 1)
    4096x4096  6,291,456 B     12,582,912 B
Psalm 1's v4 payload is 3,139,412 bytes (header blob 3,815 + audio
192,766 + world scene 29,612 + palace stored 291,028 + skybox stored
2,622,191) — 49.9% of a 4096 cover at depth 1, 88.6% of a 3072 cover
at depth 1.
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
and the skybox to 2,589,880 (a 5.7% saving) — but Draco is LOSSY
(quantised geometry; decoded bytes differ), and the Draco decoder is a
~763 KB JS+WASM pair that would have to be bundled into the decoder, so
the decoder would grow by ~1 MB to save ~178 KB in the cartridge. Not
worth it. Anything lossy needs an explicit opt-in from the person
encoding; nothing lossy is applied by default.

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

BACKWARDS COMPATIBILITY: v4 changes the layout, not the contract. The
decoder (tools/decode.py, psalms/NNN/decode.js, decode.html) reads v4 and
v3 (and v2) cartridges: it tries the v3 visible-strip header first, then
the v4 LSB header, and validates the header fully (version, header-length
bounds, JSON, format/version match, every SHA-256) before trusting
either. A v3 cartridge keeps working until it is rebuilt as v4.

PIXEL WRITING: the LSB layer is written with numpy when it is available
(vectorised — seconds per cartridge instead of minutes); without numpy
the same layout is written by the pure-Python loop below it. The two
paths produce byte-identical pixels (checked on Psalms 1 and 119).
"""
import argparse
import hashlib
import json
import os
import struct
import sys
import zlib

from PIL import Image

try:
    import numpy as _np
except ImportError:  # pragma: no cover - numpy is installed here; the
    _np = None       # fallback keeps the tools working without it.

MAGIC = b"PSLM"
VERSION = 4
# A header longer than this is not a PSLM header (real ones are ~500 B);
# the bound stops a corrupt length field from causing a huge read.
MAX_HEADER_LEN = 1_000_000

# Stable GitHub Pages URLs for the models. Used ONLY when a cartridge is
# encoded with --remote-models (explicit opt-in, default off) because the
# cover is too small to hold the models. The decoder fetches from these
# URLs only when the header records a model as remote.
REMOTE_URLS = {
    "palace": "https://j0shuaisrael.github.io/bible-cartridges/assets/cloud-palace.glb",
    "skybox": "https://j0shuaisrael.github.io/bible-cartridges/assets/skybox.glb",
}

# The canonical scene recipe (tools/scene.json): the exact bytes packed
# as the "world" part of every v4 cartridge, stored raw. Loaded once;
# validated as JSON here so a broken scene file fails the build loudly
# instead of producing cartridges whose world part will not parse.
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "scene.json"), "rb") as _f:
    SCENE_BYTES = _f.read()
json.loads(SCENE_BYTES.decode("utf-8"))  # raises if the scene file is not valid JSON

# The self-teaching bootstrap, written into every v4 cartridge as a
# plain-text PNG tEXt chunk (keyword "PSLM"). One paragraph, the whole
# bootstrap: bit order, depth fallback, stream layout, JSON header,
# hashes, glTF for the scene. A bootstrap aid ONLY — nothing depends on
# it; the LSB bitstream is self-teaching on its own (it opens with
# readable ASCII: PSLM, then the JSON header). The browser encoder
# (psalms/encode.html) writes this exact text in its tEXt chunk.
BOOTSTRAP_TEXT = (
    "PSLM cartridge. Read the least-significant bit of each R, G, B "
    "channel, row by row from the top-left, most-significant bit first "
    "(8 bits = 1 byte). If the first 4 bytes are not PSLM, try the "
    "lowest 2 bits per channel instead. The stream starts: PSLM, 1 "
    "version byte, 4-byte big-endian header length, then that many "
    "bytes of JSON. The JSON lists every part with its length and "
    "SHA-256. Read each part, check its hash. The scene is standard "
    "glTF 2.0."
)


def _png_chunk(chunk_type, data):
    crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
    return (struct.pack(">I", len(data)) + chunk_type + data +
            struct.pack(">I", crc))


def insert_bootstrap_chunk(png_bytes):
    """Insert the tEXt "PSLM" bootstrap chunk right after IHDR.
    Returns new PNG bytes. The chunk touches no pixels."""
    if png_bytes[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG file")
    pos = 8
    length = struct.unpack(">I", png_bytes[pos:pos + 4])[0]
    ctype = png_bytes[pos + 4:pos + 8]
    if ctype != b"IHDR":
        raise ValueError("PNG has no IHDR first")
    after_ihdr = pos + 12 + length
    text = b"PSLM\x00" + BOOTSTRAP_TEXT.encode("latin-1")
    return (png_bytes[:after_ihdr] +
            _png_chunk(b"tEXt", text) + png_bytes[after_ihdr:])


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


def part_entry(name, stored, encoding, remote=None):
    """One entry of the generic parts list. `stored` is the exact bytes
    that go into the bitstream; the SHA-256 is of those stored bytes.
    The extractor verifies each part against this entry and knows nothing
    about what the part IS — the name is only a label the renderer looks
    up afterwards. For a remote part, `remote` carries the length +
    SHA-256 of the bytes to be fetched, and the part occupies no bytes
    in the bitstream."""
    if remote is not None:
        return {"name": name, "len": remote["len"], "sha256": remote["sha256"],
                "encoding": "raw", "remote": True, "url": remote["url"]}
    return {"name": name, "len": len(stored),
            "sha256": hashlib.sha256(stored).hexdigest(), "encoding": encoding}


def build_header(pack, comp, audio, models, w, h, depth, data):
    """The v4 header: version + lsb_depth + a generic parts list, plus
    renderer metadata the extractor ignores. `models` are the build
    records from build_model / build_model_remote. The parts list IS the
    bitstream order after the header blob: text, audio, world (the scene
    recipe, tools/scene.json, stored raw), then models."""
    parts = [part_entry("text", comp, "zlib")]
    if audio:
        parts.append(part_entry("audio", audio, "raw"))
    parts.append(part_entry("world", SCENE_BYTES, "raw"))
    for m in models:
        if m.get("remote"):
            parts.append(part_entry(m["name"], b"", "raw",
                                    remote={"len": m["len"], "sha256": m["sha256"],
                                            "url": m["url"]}))
        else:
            parts.append(part_entry(m["name"], m["_stored"],
                                    "zlib" if m["compressed"] else "raw"))
    return {
        "format": "PSLM",
        "version": VERSION,
        "lsb_depth": depth,
        "parts": parts,
        "strip_h": 0,  # v4: no strip; the LSB bitstream starts at row 0.
        "cover_w": w,
        "cover_h": h,
        "chapter": data["chapter"],
        "languages": data["languages"],
        "fallback": data.get("fallback", "en"),
        "audio_format": "opus-webm" if audio else None,
    }


def prefix_blob(header, comp):
    """The header blob: the first section of the LSB bitstream."""
    hj = json.dumps(header, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return MAGIC + bytes([VERSION]) + struct.pack(">I", len(hj)) + hj + comp


def lsb_capacity(w, h, depth):
    """Whole-image LSB capacity in bytes (v4: no strip is subtracted)."""
    return w * h * 3 * depth // 8


def min_square_side(payload, depth):
    """Smallest square cover side whose LSB layer holds `payload` bytes
    at the given depth."""
    s = 1
    while lsb_capacity(s, s, depth) < payload:
        s += 1
    return s


def _lsb_write_numpy(img_bytes, stream, depth):
    """Write `stream` into the LSBs of the flat RGB byte string, starting
    at channel 0 (pixel (0, 0), R). Returns the new RGB bytes. The bit
    layout is identical to the pure-Python loop below: each channel takes
    the next `depth` stream bits, first bit into the highest of them."""
    arr = _np.frombuffer(img_bytes, dtype=_np.uint8).copy()
    bits = _np.unpackbits(_np.frombuffer(stream, dtype=_np.uint8))
    if depth == 1:
        n = len(bits)
        arr[:n] = (arr[:n] & 0xFE) | bits
    else:
        n = len(bits) // 2
        chunk = bits[0::2] * 2 + bits[1::2]
        arr[:n] = (arr[:n] & 0xFC) | chunk
    return arr.tobytes()


def _lsb_write_python(img, stream, depth):
    """Pure-Python fallback for the same write (no numpy). Slow on large
    covers; kept so the tool works anywhere."""
    px = img.load()
    w, h = img.size
    mask = (1 << depth) - 1
    bitpos = 0
    total_bits = len(stream) * 8
    for y in range(h):
        for x in range(w):
            if bitpos >= total_bits:
                return
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
            return


def encode(cover_path, data_path, out_path, audio_path, palace_path, skybox_path,
           depth_arg, remote_models=False, text_audio_only=False):
    cover = Image.open(cover_path).convert("RGB")
    w, h = cover.size
    pack, comp = build_pack(data_path)
    audio = open(audio_path, "rb").read() if audio_path else b""
    with open(data_path, encoding="utf-8") as f:
        data = json.load(f)
    embedded = [build_model("palace", palace_path), build_model("skybox", skybox_path)]

    def depth_for(models):
        """Minimum LSB depth whose whole-image capacity holds this models
        list (header blob + audio + stored models). Returns
        (depth, payload, blob); depth is None when no depth fits. The
        header length does not depend on the depth (one digit either
        way) or on strip_h (always 0 in v4), so no fixed-point
        iteration is needed."""
        header = build_header(pack, comp, audio, models, w, h, 1, data)
        blob = prefix_blob(header, comp)
        # The whole bitstream: the header blob (which already carries the
        # text part, parts[0]) + every other part in the header's list,
        # in listed order. The parts list is the single source of truth.
        payload = len(blob) + sum(p["len"] for p in header["parts"]
                                  if p["name"] != "text" and "remote" not in p)
        if depth_arg == "auto":
            depths = [1, 2]
        else:
            depths = [int(depth_arg)]
        for d in depths:
            if payload <= lsb_capacity(w, h, d):
                return d, payload, blob
        return None, payload, blob

    # ORDER OF ATTEMPTS: fit everything in the image first (with lossless
    # compression). Only when the models do not fit do the explicit opt-ins
    # come into play — never automatically, never silently.
    depth, payload, blob = depth_for(embedded)
    mode = "embedded"
    models = embedded
    if depth is None:
        cap1 = lsb_capacity(w, h, 1)
        cap2 = lsb_capacity(w, h, 2)
        if remote_models:
            models = [build_model_remote("palace", palace_path),
                      build_model_remote("skybox", skybox_path)]
            depth, payload, blob = depth_for(models)
            if depth is None:
                raise SystemExit(
                    f"PAYLOAD DOES NOT FIT even without the models: audio {len(audio):,} bytes "
                    f"exceeds the LSB capacity of this cover ({w}x{h}): "
                    f"{cap1:,} bytes at 1 LSB, {cap2:,} bytes at 2 LSBs. "
                    f"Use a larger cover image."
                )
            mode = "remote"
        elif text_audio_only:
            models = []
            depth, payload, blob = depth_for(models)
            if depth is None:
                raise SystemExit(
                    f"PAYLOAD DOES NOT FIT even without the models: audio {len(audio):,} bytes "
                    f"exceeds the LSB capacity of this cover ({w}x{h}): "
                    f"{cap1:,} bytes at 1 LSB, {cap2:,} bytes at 2 LSBs. "
                    f"Use a larger cover image."
                )
            mode = "text-audio-only"
        else:
            raise SystemExit(
                f"PAYLOAD DOES NOT FIT: {payload:,} bytes (header blob "
                f"{len(blob):,} + audio {len(audio):,} + world scene "
                f"{len(SCENE_BYTES):,} + "
                f"palace stored {embedded[0]['stored_len']:,} + skybox stored {embedded[1]['stored_len']:,}) "
                f"exceeds the LSB capacity of this cover ({w}x{h}): "
                f"{cap1:,} bytes at 1 LSB, {cap2:,} bytes at 2 LSBs. "
                f"Use a cover at least {min_square_side(payload, 2)}x{min_square_side(payload, 2)} "
                f"px for 2 LSBs, or {min_square_side(payload, 1)}x{min_square_side(payload, 1)} px for 1 LSB. "
                f"The models are never dropped silently. Two explicit choices: "
                f"re-run with --remote-models (the cartridge is encoded with text + audio in the image, "
                f"but its world will need the network), or --text-audio-only (the cartridge will be "
                f"incomplete for the world). A bigger cover image is the fully-offline option."
            )
    header = build_header(pack, comp, audio, models, w, h, depth, data)
    blob = prefix_blob(header, comp)
    capacity = lsb_capacity(w, h, depth)
    # The bitstream follows the header's parts list, in listed order: the
    # header blob (which carries the text part), then audio, the world
    # part (the scene recipe), then the models. Remote parts occupy no
    # bytes here.
    stream = blob + audio + SCENE_BYTES + b"".join(m["_stored"] for m in models)
    assert len(stream) == payload, "bitstream length does not match the parts list"

    # ONE LSB bitstream from pixel (0, 0): header blob, audio, models.
    # No strip — no pixel is replaced, only least-significant bits change.
    if _np is not None:
        out_bytes = _lsb_write_numpy(cover.tobytes(), stream, depth)
        cover = Image.frombytes("RGB", (w, h), out_bytes)
    else:
        _lsb_write_python(cover, stream, depth)

    cover.save(out_path, format="PNG")
    # The PNG teaches itself: add the plain-text bootstrap chunk (tEXt
    # "PSLM"). It touches no pixels and nothing depends on it.
    with open(out_path, "rb") as f:
        png_bytes = f.read()
    with open(out_path, "wb") as f:
        f.write(insert_bootstrap_chunk(png_bytes))
    print(f"wrote {out_path} ({w}x{h}, PSLM v{VERSION}, {depth} LSB, no strip)")
    print(f"  text pack: {len(pack)} bytes -> {len(comp)} compressed "
          f"(sha256 {hashlib.sha256(pack).hexdigest()[:12]}...)")
    print(f"  audio: {len(audio)} bytes Opus/WebM "
          f"(sha256 {(hashlib.sha256(audio).hexdigest()[:12] if audio else '-') }...)")
    for p in header["parts"]:
        if p["name"] in ("text", "audio") or p.get("remote"):
            continue  # text/audio printed above; remote parts are reported by the mode branches below
        print(f"  part {p['name']}: {p['len']:,} bytes stored ({p['encoding']}), "
              f"sha256 {p['sha256'][:12]}...")
    if mode == "embedded":
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
    ap = argparse.ArgumentParser(description="Encode a Bible cartridge PNG (PSLM v4).")
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
