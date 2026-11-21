#!/usr/bin/env python3
"""Independent PSLM v3 decoder, written ONLY from the AI-spec textbox in
decode.html (SPEC_TEXT). Deliberately does NOT import tools/decode.py and
shares no code with psalms/001/decode.js. Proves a cartridge can be opened
with nothing but the image + the public spec: no key, no password, no
decoder binary, no network.
Usage: python3 independent-pslm-decode.py <cartridge.png> [data.json]
"""
import sys, json, struct, zlib, hashlib
from PIL import Image

def sha(b): return hashlib.sha256(b).hexdigest()

def main(path, data_path=None):
    img = Image.open(path).convert("RGBA")
    w, h = img.size
    px = img.load()
    # --- STRIP: 3 bytes per pixel (R,G,B), row-major, top rows ---
    strip = bytearray()
    # read enough rows: header is at the very start, so read row by row
    # until we have the header + pack; cap at 64 rows (strip_h is small)
    for y in range(64):
        for x in range(w):
            r, g, b, a = px[x, y]
            strip += bytes((r, g, b))
    assert bytes(strip[0:4]) == b"PSLM", "magic mismatch: %r" % bytes(strip[0:4])
    version = strip[4]
    assert version in (2, 3), version
    hlen = struct.unpack(">I", bytes(strip[5:9]))[0]
    header = json.loads(bytes(strip[9:9 + hlen]).decode("utf-8"))
    assert header["format"] == "PSLM" and header["version"] == version
    strip_h = header["strip_h"]
    # text pack: zlib stream immediately after the header in the strip
    pack_comp = bytes(strip[9 + hlen: 9 + hlen + header["pack_comp_len"]])
    pack = zlib.decompress(pack_comp)
    assert len(pack) == header["pack_len"], (len(pack), header["pack_len"])
    assert sha(pack) == header["pack_sha256"], "pack SHA mismatch"
    text = json.loads(pack.decode("utf-8"))
    print(f"chapter {header['chapter']}  version {version}  strip_h {strip_h}  "
          f"languages {header['languages']}  depth {header.get('lsb_depth', 1)}")
    print(f"text pack OK: {len(pack)} bytes, {len(text['verses'])} verses, "
          f"{len(text['lexicon'])} lexicon entries, sha256 {sha(pack)[:12]}...")
    if data_path:
        want = json.load(open(data_path))
        # compare the semantic content (key order/spacing may differ)
        assert text == want, "text pack != source data file"
        print("text pack == source data file (parsed JSON identical)")
    # --- LSB BITSTREAM from row strip_h, depth bits per channel, MSB-first ---
    depth = header.get("lsb_depth", 1)
    bits = []
    total_bytes = header["audio_len"] + sum(
        m["stored_len"] for m in header.get("models", []) if not m.get("remote"))
    need_bits = total_bytes * 8
    got = 0
    out = bytearray()
    cur = 0
    nbits = 0
    done = False
    for y in range(strip_h, h):
        if done: break
        for x in range(w):
            r, g, b, a = px[x, y]
            for v in (r, g, b):
                for k in range(depth - 1, -1, -1):
                    cur = (cur << 1) | ((v >> k) & 1)
                    nbits += 1
                    got += 1
                    if nbits == 8:
                        out.append(cur); cur = 0; nbits = 0
                        if len(out) == total_bytes:
                            done = True; break
                if done: break
            if done: break
    assert len(out) == total_bytes, f"truncated: got {len(out)} of {total_bytes}"
    audio = bytes(out[:header["audio_len"]])
    assert sha(audio) == header["audio_sha256"], "audio SHA mismatch"
    print(f"audio OK: {len(audio)} bytes, sha256 {sha(audio)[:12]}...")
    off = header["audio_len"]
    for m in header.get("models", []):
        if m.get("remote"):
            print(f"model {m['name']}: REMOTE ({m['url']}) — not in image")
            continue
        stored = bytes(out[off:off + m["stored_len"]]); off += m["stored_len"]
        raw = zlib.decompress(stored) if m.get("compressed") else stored
        assert len(raw) == m["len"], (m["name"], len(raw), m["len"])
        assert sha(raw) == m["sha256"], f"{m['name']} SHA mismatch"
        print(f"model {m['name']} OK: {len(raw)} bytes, sha256 {sha(raw)[:12]}...")
    print("ALL CHECKS PASSED — decoded with the spec alone, no key, no decoder code.")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
