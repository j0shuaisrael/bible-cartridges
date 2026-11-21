#!/usr/bin/env python3
"""One-psalm end-to-end driver: data -> audio -> cover -> viewer -> encode -> verify.

    python3 tools/build_psalm.py --psalm 2 --steps data,audio,cover,viewer
    python3 tools/build_psalm.py --psalm 2            # all steps incl. encode+verify
    python3 tools/build_psalm.py --psalm 119 --cover-size 4096

Steps (each is a separate tool; this driver only wires them together):
  data    tools/build_psalm_data.py (gloss cache -> data JSON + meanings CSV)
  audio   ffmpeg MP3 -> Opus-in-WebM 24 kbps (psalms/NNN/audio.webm) and the
          source MP3 kept at psalms/NNN/t<code>.mp3 (same layout as Psalm 1)
  cover   tools/make_cover.py (deterministic procedural STAND-IN cover)
  viewer  copy psalms/001/index.html + decode.js; generate chapter.js
          (number / title / Hebrew title) for this psalm
  encode  tools/encode.py (PSLM v4 cartridge with the full palace + skybox + scene)
  verify  tools/decode.py round-trip: every SHA-256 checked, extracted
          audio/text/models compared byte-for-byte with the sources

Cover size choice (minimum that fits, depth 1 preferred): the driver
computes the exact payload (Opus audio + zlib-stored models + text pack,
same arithmetic as tools/encode.py) and picks 3072x3072 when the payload
fits its depth-1 LSB layer, else 4096x4096. The encoder itself then picks
the minimum depth (1, else 2) that fits the chosen cover and refuses
loudly if nothing fits — e.g. Psalm 119's ~19-minute reading is too big
for depth 1 even at 4096, so its cartridge is expected to be depth 2.

Never run with a stub/empty gloss cache and expect a final cartridge:
the data step refuses to overwrite a higher-coverage data.json, and a
smoke test should use --steps data,audio,cover,viewer with the data
output redirected (build_psalm_data.py --out-data /tmp/...) instead.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hebrew_numerals import hebrew_title  # noqa: E402
from parse_mechon import audio_code  # noqa: E402
import encode as encode_mod  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"


def run(cmd, **kw):
    print(f"$ {' '.join(str(c) for c in cmd)}")
    r = subprocess.run(cmd, **kw)
    if r.returncode != 0:
        raise SystemExit(f"step failed (exit {r.returncode}): {cmd[0]}")
    return r


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def choose_cover_size(n, data_path, audio_path):
    """Minimum square cover (3072 or 4096) whose depth-1 LSB layer holds
    the whole v4 payload: header blob + audio + scene + models. No strip
    is subtracted in v4 — the capacity is the whole image."""
    pack, comp = encode_mod.build_pack(str(data_path))
    audio = Path(audio_path).read_bytes()
    models = [encode_mod.build_model("palace", str(ROOT / "assets" / "cloud-palace.glb")),
              encode_mod.build_model("skybox", str(ROOT / "assets" / "skybox.glb"))]
    data = json.loads(Path(data_path).read_text(encoding="utf-8"))
    header = encode_mod.build_header(pack, comp, audio, models, 3072, 3072, 1, data)
    blob = encode_mod.prefix_blob(header, comp)
    payload = (len(blob) + len(audio) + len(encode_mod.SCENE_BYTES)
               + sum(m["stored_len"] for m in models))
    for side in (3072, 4096):
        cap1 = encode_mod.lsb_capacity(side, side, 1)
        print(f"  cover sizing: payload={payload} B (blob {len(blob)} + audio {len(audio)} + "
              f"scene {len(encode_mod.SCENE_BYTES)} + models {sum(m['stored_len'] for m in models)}), "
              f"{side}x{side} d1 capacity={cap1} B")
        if payload <= cap1:
            return side
    return 4096


CHAPTER_JS = """// Chapter data for THIS page. The viewer (index.html in this folder) is a
// shared template for all 150 Psalms: to make another psalm's page, copy
// this whole folder, replace this file, cartridge.png, audio.webm and
// cover.png — the viewer logic itself stays untouched. Nothing
// Psalm-{n}-specific lives in index.html; everything chapter-specific lives
// here (page metadata) or inside the cartridge (text, glosses, audio).
export const CHAPTER = {{
  number: {n},
  // Shown in the browser tab, the corner label, and as the scroll's heading.
  title: 'Psalm {n}',
  // Hebrew heading on the scroll (Tehillim = Psalms, {heb} = {n}).
  hebrewTitle: '{hebrew_title}',
  // Files in this folder. The cartridge holds the chapter text + glosses +
  // audio; the audio file is the same Opus WebM packed into the cartridge,
  // kept as a file so the <audio> element can play it.
  cartridge: 'cartridge.png',
  audio: 'audio.webm',
}};
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--psalm", type=int, required=True)
    ap.add_argument("--steps", default="all",
                    help="comma list: data,audio,cover,viewer,encode,verify (default all)")
    ap.add_argument("--cache", default=str(TOOLS / "gloss-cache.json"))
    ap.add_argument("--cover-size", default="auto", choices=["auto", "3072", "4096"])
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    n = args.psalm
    if not 1 <= n <= 150:
        raise SystemExit(f"psalm out of range: {n}")
    steps = ["data", "audio", "cover", "viewer", "encode", "verify"] \
        if args.steps == "all" else [s.strip() for s in args.steps.split(",")]
    pdir = ROOT / "psalms" / f"{n:03d}"
    pdir.mkdir(parents=True, exist_ok=True)
    data_path = TOOLS / f"psalm{n:03d}_data.json"
    audio_path = pdir / "audio.webm"
    cover_path = pdir / "cover.png"

    if "data" in steps:
        cmd = [sys.executable, str(TOOLS / "build_psalm_data.py"),
               "--psalm", str(n), "--cache", args.cache]
        if args.force:
            cmd.append("--force")
        run(cmd)

    if "audio" in steps:
        src_mp3 = TOOLS / "mp3" / f"{audio_code(n)}.mp3"
        if not src_mp3.exists():
            raise SystemExit(f"harvested MP3 missing: {src_mp3} — run tools/harvest.py first")
        shutil.copy2(src_mp3, pdir / f"{audio_code(n)}.mp3")
        run(["ffmpeg", "-y", "-v", "error", "-i", str(src_mp3),
             "-c:a", "libopus", "-b:a", "24k", str(audio_path)])
        probe = json.loads(subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration,bit_rate",
             "-show_entries", "stream=codec_name,sample_rate,channels",
             "-of", "json", str(audio_path)],
            capture_output=True, text=True).stdout)
        print(f"  audio.webm: {probe['format']['duration']} s, "
              f"codec={probe['streams'][0]['codec_name']}, "
              f"{probe['streams'][0]['sample_rate']} Hz, "
              f"{probe['streams'][0]['channels']} ch, {audio_path.stat().st_size} B")

    if "cover" in steps:
        if args.cover_size == "auto":
            if not data_path.exists() or not audio_path.exists():
                raise SystemExit("cover-size auto needs the data + audio steps first")
            side = choose_cover_size(n, data_path, audio_path)
        else:
            side = int(args.cover_size)
        run([sys.executable, str(TOOLS / "make_cover.py"),
             "--psalm", str(n), "--size", str(side), "--out", str(cover_path)])

    if "viewer" in steps:
        for name in ("index.html", "decode.js"):
            shutil.copy2(ROOT / "psalms" / "001" / name, pdir / name)
        (pdir / "chapter.js").write_text(
            CHAPTER_JS.format(n=n, heb=hebrew_title(n).split()[-1],
                              hebrew_title=hebrew_title(n)), encoding="utf-8")
        print(f"  viewer: {pdir}/index.html + decode.js + chapter.js "
              f"(Psalm {n}, {hebrew_title(n)})")

    if "encode" in steps:
        for p in (cover_path, data_path, audio_path):
            if not p.exists():
                raise SystemExit(f"encode needs {p} — run the earlier steps first")
        run([sys.executable, str(TOOLS / "encode.py"),
             "--cover", str(cover_path), "--data", str(data_path),
             "--audio", str(audio_path),
             "--palace", str(ROOT / "assets" / "cloud-palace.glb"),
             "--skybox", str(ROOT / "assets" / "skybox.glb"),
             "--out", str(pdir / "cartridge.png")])

    if "verify" in steps:
        cart = pdir / "cartridge.png"
        if not cart.exists():
            raise SystemExit(f"verify needs {cart} — run the encode step first")
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            run([sys.executable, str(TOOLS / "decode.py"), str(cart),
                 "--out-text", str(td / "text.json"),
                 "--out-audio", str(td / "audio.webm"),
                 "--out-model-palace", str(td / "palace.glb"),
                 "--out-model-skybox", str(td / "skybox.glb")])
            decoded_text = json.loads((td / "text.json").read_text(encoding="utf-8"))
            orig_text = json.loads(data_path.read_text(encoding="utf-8"))
            assert decoded_text == orig_text, "decoded text pack != data JSON"
            assert sha256(td / "audio.webm") == sha256(audio_path), "decoded audio != audio.webm"
            assert sha256(td / "palace.glb") == sha256(ROOT / "assets" / "cloud-palace.glb"), \
                "decoded palace != assets/cloud-palace.glb"
            assert sha256(td / "skybox.glb") == sha256(ROOT / "assets" / "skybox.glb"), \
                "decoded skybox != assets/skybox.glb"
            print("  verify: text pack, audio, palace, skybox all byte-identical to sources")
            # Keep the universal encoder's manifest current: a psalm counts
            # as built when its data file and its audio both exist
            # (tools/build_built_psalms.py, created by a parallel worker).
            manifest_script = TOOLS / "build_built_psalms.py"
            if manifest_script.exists():
                run([sys.executable, str(manifest_script)])
    print(f"Psalm {n}: steps done: {', '.join(steps)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
