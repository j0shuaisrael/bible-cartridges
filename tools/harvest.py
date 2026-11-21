#!/usr/bin/env python3
"""Harvest all 150 Psalms from Mechon Mamre (text + audio).

    python3 tools/harvest.py --all            # texts + audios for 1..150
    python3 tools/harvest.py --texts          # texts only
    python3 tools/harvest.py --audios         # audios only
    python3 tools/harvest.py --psalms 2,119   # subset (comma list / ranges)
    python3 tools/harvest.py --check-psalm1   # re-parse Psalm 1, compare to
                                              # tools/psalm001_data.json

Texts -> tools/text/psalmNNN_text.json (cleaned + raw Hebrew verses, JPS
English, source URLs). Audios -> tools/mp3/t<code>.mp3 (e.g. t2601.mp3,
t26b9.mp3). Manifest -> tools/harvest_manifest.json (HTTP status, bytes,
SHA-256, ffprobe duration/bitrate per audio).

Polite: 0.35 s between requests, 3 retries, 30 s timeout, browser UA.
Exits non-zero if any requested psalm fails; re-running is safe (skips
files already present and valid unless --force).
"""
import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse_mechon import (  # noqa: E402
    audio_code,
    audio_url,
    parse_page,
    text_code,
    text_url,
)

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
TEXT_DIR = TOOLS / "text"
MP3_DIR = TOOLS / "mp3"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"


def fetch(url, dest: Path, retries=3):
    import urllib.request

    last_err = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                if r.status != 200:
                    raise RuntimeError(f"HTTP {r.status}")
                data = r.read()
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            return {"status": 200, "bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest()}
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(1.0 * attempt)
    raise RuntimeError(f"fetch failed for {url}: {last_err}")


def ffprobe(path: Path):
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration,bit_rate,size", "-show_entries",
             "stream=codec_name,sample_rate,channels",
             "-of", "json", str(path)],
            capture_output=True, text=True, timeout=60)
        j = json.loads(out.stdout)
        fmt, streams = j.get("format", {}), j.get("streams", [])
        return {"duration": float(fmt.get("duration", 0)),
                "bit_rate": int(fmt.get("bit_rate", 0)),
                "codec": streams[0].get("codec_name") if streams else None,
                "sample_rate": streams[0].get("sample_rate") if streams else None,
                "channels": streams[0].get("channels") if streams else None}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def parse_range(spec: str):
    out = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            out.extend(range(int(a), int(b) + 1))
        elif part:
            out.append(int(part))
    return sorted(set(out))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--texts", action="store_true")
    ap.add_argument("--audios", action="store_true")
    ap.add_argument("--psalms", default="1-150")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--check-psalm1", action="store_true")
    args = ap.parse_args()

    if args.check_psalm1:
        html_text = (TEXT_DIR / "psalm001_text.json")
        ref = json.loads((TOOLS / "psalm001_data.json").read_text(encoding="utf-8"))
        got = json.loads(html_text.read_text(encoding="utf-8"))
        ok = got["verses_hebrew"] == ref["text"].split("\n")
        print(f"Psalm 1 harvested text == psalm001_data.json: {ok}")
        return 0 if ok else 1

    do_texts = args.all or args.texts or (not args.audios)
    do_audios = args.all or args.audios
    psalms = parse_range(args.psalms)
    manifest_path = TOOLS / "harvest_manifest.json"
    manifest = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    failures = []
    for n in psalms:
        entry = manifest.get(str(n), {})
        if do_texts:
            dest = TEXT_DIR / f"psalm{n:03d}_text.json"
            if dest.exists() and not args.force:
                print(f"[{n}] text: already present, skipped")
            else:
                try:
                    info = fetch(text_url(n), TEXT_DIR / f".tmp_{text_code(n)}.html")
                    html_text = (TEXT_DIR / f".tmp_{text_code(n)}.html").read_text(encoding="utf-8")
                    parsed = parse_page(html_text, n)
                    parsed["fetched_at"] = datetime.now(timezone.utc).isoformat()
                    parsed["source_bytes"] = info["bytes"]
                    dest.write_text(json.dumps(parsed, ensure_ascii=False, indent=1),
                                    encoding="utf-8")
                    (TEXT_DIR / f".tmp_{text_code(n)}.html").unlink(missing_ok=True)
                    entry["text"] = {**info, "verses": parsed["verse_count"],
                                     "anchor_check": parsed["anchor_check"],
                                     "file": f"tools/text/psalm{n:03d}_text.json"}
                    print(f"[{n}] text: {info['bytes']} B, {parsed['verse_count']} verses, "
                          f"anchors ok={parsed['anchor_check']}")
                    if not parsed["anchor_check"]:
                        failures.append(f"psalm {n}: anchor check failed")
                except Exception as e:  # noqa: BLE001
                    failures.append(f"psalm {n} text: {e}")
                    print(f"[{n}] text FAILED: {e}")
                time.sleep(0.35)
        if do_audios:
            dest = MP3_DIR / f"{audio_code(n)}.mp3"
            if dest.exists() and not args.force:
                print(f"[{n}] audio: already present, skipped")
            else:
                try:
                    info = fetch(audio_url(n), dest)
                    probe = ffprobe(dest)
                    entry["audio"] = {**info, **probe,
                                      "file": f"tools/mp3/{audio_code(n)}.mp3"}
                    ok = probe.get("codec") == "mp3" and probe.get("duration", 0) > 0
                    print(f"[{n}] audio: {info['bytes']} B, "
                          f"{probe.get('duration')} s, {probe.get('bit_rate')} bps, "
                          f"codec={probe.get('codec')}, valid={ok}")
                    if not ok:
                        failures.append(f"psalm {n}: audio probe invalid {probe}")
                except Exception as e:  # noqa: BLE001
                    failures.append(f"psalm {n} audio: {e}")
                    print(f"[{n}] audio FAILED: {e}")
                time.sleep(0.35)
        manifest[str(n)] = entry

    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                             encoding="utf-8")
    print(f"\nmanifest: {manifest_path}")
    if failures:
        print(f"FAILURES ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("all requested harvests succeeded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
