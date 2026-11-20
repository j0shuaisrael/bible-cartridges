#!/usr/bin/env python3
"""Inject the bundled three.js into decode.html's import map.

decode.html must work from file:// with the network unavailable, so it
cannot load three.js from a CDN — and ES-module imports of separate files
are blocked by CORS on file:// in Chrome. The fix: the three.js library
and its addons are inlined into decode.html itself as base64 data: URLs
in the import map. The page then makes zero external requests of any kind.

Sources (committed, MIT-licensed, three.js r160):
  tools/vendor/three.module.min.js
  tools/vendor/GLTFLoader.js
  tools/vendor/RoomEnvironment.js
  tools/vendor/BufferGeometryUtils.js

GLTFLoader's one relative import ('../utils/BufferGeometryUtils.js') is
rewritten to the bare specifier 'three/addons/utils/BufferGeometryUtils.js'
so it resolves through the import map (a relative import off a data: URL
has nothing to resolve against).

Usage: python3 tools/inline_three.py   (rewrites decode.html in place;
it is idempotent — re-run it after changing the vendor files, or after
editing decode.html's import-map placeholder).

decode.html must contain the marker line:
    <!-- IMPORTMAP:INJECTED-BY-TOOLS/INLINE_THREE.PY -->
inside a <script type="importmap"> block; this script replaces that
marker line with the "imports" JSON. If the import map is already
injected, the script replaces the whole block (so re-running is safe).
"""
import base64
import json
import re
import sys
from pathlib import Path

ROOT = Path("/home/hatch/workspace/bible-cartridges")
VENDOR = ROOT / "tools" / "vendor"
DECODE_HTML = ROOT / "decode.html"

FILES = {
    "three": "three.module.min.js",
    "three/addons/loaders/GLTFLoader.js": "GLTFLoader.js",
    "three/addons/environments/RoomEnvironment.js": "RoomEnvironment.js",
    "three/addons/utils/BufferGeometryUtils.js": "BufferGeometryUtils.js",
}


def data_url(text):
    b64 = base64.b64encode(text.encode("utf-8")).decode("ascii")
    return "data:text/javascript;base64," + b64


def main():
    imports = {}
    for spec, fname in FILES.items():
        text = (VENDOR / fname).read_text(encoding="utf-8")
        if fname == "GLTFLoader.js":
            # Rewrite the one relative import so it resolves via the map.
            text = text.replace(
                "from '../utils/BufferGeometryUtils.js'",
                "from 'three/addons/utils/BufferGeometryUtils.js'",
            )
            assert "three/addons/utils/BufferGeometryUtils.js" in text
            assert "../utils/BufferGeometryUtils.js" not in text
        imports[spec] = data_url(text)
        print(f"  {spec}: {len(text):,} chars -> data: URL {len(imports[spec]):,} chars")

    importmap = (
        '<script type="importmap">\n'
        + json.dumps({"imports": imports}, indent=1)
        + "\n</script>"
    )
    html = DECODE_HTML.read_text(encoding="utf-8")
    marker = "<!-- IMPORTMAP:INJECTED-BY-TOOLS/INLINE_THREE.PY -->"
    # Replace either the placeholder marker (first run) or a previously
    # injected import-map block (re-run).
    if marker in html:
        html = html.replace(marker, importmap)
    else:
        new_html, n = re.subn(
            r'<script type="importmap">.*?</script>',
            lambda _: importmap,
            html,
            count=1,
            flags=re.S,
        )
        if n != 1:
            sys.exit("decode.html has neither the import-map marker nor an import-map block to replace")
        html = new_html
    DECODE_HTML.write_text(html, encoding="utf-8")
    print(f"wrote {DECODE_HTML} ({len(html):,} bytes)")


if __name__ == "__main__":
    main()
