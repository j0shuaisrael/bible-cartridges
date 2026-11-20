# Bible Cartridges — prototype (Psalm 1)

A chapter of Psalms steganographed into a PNG ("Bible cartridge"), presented
as a floating scroll in a first-person 3D scene. One isolated webapp per
chapter. This prototype is **Psalm 1 only**.

## Layout

```
index.html                  plain white "Index of /" directory listing (the hub)
decode.html                 universal decoder: drop any cartridge PNG, read the
                            chapter — nothing to install, works from file:// too
assets/
  cloud-palace.glb          the platform (sky strip surgically removed, see below)
  skybox.glb                the surrounding sky (single sphere)
psalms/001/
  index.html                the Psalm 1 viewer (three.js) — THE TEMPLATE, see below
  chapter.js                chapter metadata: number, titles, filenames
  decode.js                 in-browser PSLM cartridge decoder
  encode.html               the Psalm 1 encoder (template for all 150 psalms):
                            drop your image, get the cartridge — no downgrade
  cartridge.png             the cartridge: cover + Psalm 1 text + audio, steganographed
  cover.png                 cover art (PLACEHOLDER — replace with real art)
  audio.webm                the chapter reading, Opus in WebM (58 s)
  t2601.mp3                 the original Mechon Mamre MP3 (source for audio.webm)
tools/
  build_psalm001_data.py    builds psalm001_data.json (verses + lexicon) from the
                            hand-written gloss table; verifies every token
  psalm001_data.json        chapter data: 6 verses as lexicon indices + the
                            per-unique-word lexicon (Hebrew, transliteration,
                            baked gloss per language)
  encode.py                 builds a cartridge PNG from cover + data + audio
  decode.py                 verifies + extracts a cartridge PNG (Python)
```

## The platform GLB

`assets/cloud-palace.glb` is the Cloud Palace with its built-in sky strip
removed **properly, in the file** — not hidden at runtime. The strip was
mesh `GeometryNode_15` (84×84×42 units, 182 vertices, emissive material);
removing its node + mesh + now-unused material + orphaned accessors /
bufferViews / texture with gltf-transform shrank the file from 1,207,616 to
795,224 bytes and the bounding box from 84×84×42 to 28×28×18. The remaining
4 meshes are the real palace. `assets/skybox.glb` is the anime skybox
unchanged; the viewer measures its loaded size at runtime and scales it to
a ~60-unit radius (the file's own node matrix already makes it ~1000 units,
so a blind 60x would have made it invisible).

## The cartridge format (PSLM v2)

All lossless and exactly reversible. The decoder verifies a SHA-256 over the
text pack and over the audio, and returns the exact original bytes — or
reports damage.

* **Visible strip** — the top 16 rows of the cover hold the text pack as raw
  RGB bytes (3 bytes/pixel): magic `PSLM`, version byte, a JSON header
  (chapter, packed languages, lengths, SHA-256s, strip height), then the
  zlib-compressed text pack. Bytes past the payload inside the strip are
  deterministic filler and are ignored by the decoder.
* **Invisible LSB layer** — the Opus audio is hidden in the lowest bit of
  each colour channel of every pixel below the strip (1 bit × RGB). A channel
  changes by at most 1/255: invisible to the eye. Psalm 1's 192,766-byte
  audio uses 49.8% of a 1024×1024 cover's LSB capacity.

The text pack is the chapter data JSON: verses as indices into a lexicon,
plus one entry per **unique** Hebrew word (49 for Psalm 1) — Hebrew token,
SBL-style transliteration, and a gloss in each packed language.

## Translations are baked in — no API, no cost, offline forever

The parentheticals on the scroll are `(transliteration, meaning in the
user's device language)`. The meanings are **baked into the cartridge once,
at build time** — one gloss per language per unique word, stored in the text
pack, and the cartridge header lists which languages are packed (Psalm 1:
English + Spanish). The decoder reads `navigator.language`, picks the best
matching packed language (`es-MX` → `es`), and falls back to English when
the device language isn't packed. Hebrew + transliteration always work
regardless of language. Decoding never fetches anything and never costs
anything. Adding a language later means adding one gloss per word at build
time — the format needs no redesign.

## The template: one page per psalm (all 150)

`psalms/001/index.html` is the reusable template for every psalm. It holds
**nothing chapter-specific**: the chapter number, the titles shown on the
page and the scroll, and the cartridge/audio filenames all come from
`chapter.js` in the same folder; the text, transliteration, glosses and
audio all come from the cartridge itself, decoded in the browser. The 3D
world (palace, skybox, scroll, controls) is shared logic.

To make another psalm's page (e.g. Psalm 23):

1. Copy the whole `psalms/001/` folder to `psalms/023/`.
2. Replace `chapter.js` (number, title, Hebrew title).
3. Replace `cartridge.png` (built with `tools/encode.py` from that
   chapter's data + audio + cover), `audio.webm`, `cover.png`, `t2601.mp3`.
4. Add one line to the hub `index.html`.
5. Change nothing in `index.html` or `decode.js`.

Long chapters need a bigger cover: the LSB audio layer holds ~393 KB in a
1024×1024 cover, ~1.5 MB in 2048×2048. Psalm 119 (~10 min of audio,
~1.8 MB at 24 kbps) will not fit a 1024×1024 cover — use a larger cover
image for it (or 2 LSBs, or a lower Opus bitrate). The encoder fails loudly
at build time if a payload doesn't fit; it never silently truncates.

## Encoder + decoder pages — the "pregnant twin" maker (2026-11-20)

* **`psalms/001/encode.html`** — the per-psalm encoder (template for all
  150). Drop a PNG or JPEG; it builds this psalm's cartridge as a download.
  The psalm number comes from the page's own folder; the chapter data is
  fetched from `tools/psalmNNN_data.json` and the audio from `audio.webm`
  in the same folder — the same files the viewer uses. Both are also
  embedded in the page as fallbacks, used only when fetch is blocked
  (opening the page directly from `file://`). On GitHub Pages the live
  files are always preferred. To clone for another psalm: copy the folder,
  replace the data + audio, and regenerate the two embedded blobs from
  those files.
* **`decode.html`** (repo root) — the universal decoder. Anyone can drag
  any cartridge PNG onto it (or pick a file) and read the chapter: verified
  intercalated Hebrew + transliteration + gloss in the device language
  (English fallback, manual language picker), plus the audio player. On
  any SHA-256 mismatch it reports DAMAGE and shows nothing unverified. It
  accepts cartridges made by either the Python encoder or the web encoder.
  Its decoder is a standalone copy of `psalms/001/decode.js`, inlined so
  the page works from `file://` (a module import would be blocked there).

### The no-downgrade rule — how it is kept

* Output dimensions are exactly the input's. The art is never resized;
  the code strip is extra rows added on top.
* PNG input: the pixel data is re-encoded losslessly (filter-0 scanlines,
  zlib) and **every metadata chunk is copied verbatim** into the output
  (`tEXt`, `iTXt`, `zTXt`, `eXIf`, `iCCP`, and any others) — the file is
  never rebuilt from pixels alone. RGBA input stays RGBA; RGB stays RGB.
* JPEG input: decoded once to PNG — pixels identical to the decoded JPEG,
  never re-encoded as JPEG. EXIF → `eXIf`, XMP → `iTXt`
  "XML:com.adobe.xmp", IPTC → `zTXt` "Raw profile type iptc"
  (ImageMagick convention, hex-encoded), ICC profile → `iCCP`.
* The numbers are shown before encoding (pack bytes, audio bytes, strip
  rows, LSB capacity, % used). If the audio does not fit, the page refuses
  loudly with those numbers and disables encoding — it never silently
  truncates. An in-page self-check re-reads the built strip and verifies
  both SHA-256s before offering the download.
* Known limits: 16-bit PNG input is stored as 8-bit (the browser canvas
  holds 8-bit pixels) — the page warns when it happens. The strip filler
  bytes use a small deterministic PRNG (mulberry32) instead of Python's
  Mersenne Twister; filler is ignored by every decoder, so cartridges
  still verify — but a byte-for-byte diff against a Python-encoded
  cartridge of the same cover will differ in the filler (and in the
  compressed pack bytes, since the browser's deflate level is not
  controllable). The decoded content is identical.
* Engine quirk, measured 2026-11-20: WebKit's `CompressionStream`
  ('deflate') is non-conformant — it returns a **zlib-wrapped** stream
  instead of raw deflate. The encoder uses `'deflate-raw'` (with a
  strip-the-wrapper fallback), and the decoder's inflate retries stripped
  on failure, so both pages work in WebKit and in spec-conformant engines.

### Verification (2026-11-20, headless WebKit + Python)

* Real 2048×2048 test images (Pillow): PNG with 3× `tEXt` + `eXIf`;
  JPEG with EXIF + XMP + IPTC + ICC. Both encoded through the page.
* `tools/decode.py` round-trips all browser-encoded cartridges: both
  SHA-256s verified; decoded text pack is exactly `psalm001_data.json`;
  decoded audio SHA-256 `5474dd97…` matches `audio.webm`. The `file://`
  cartridge is byte-identical to the HTTP one (SHA-256 `64f93372…`).
* Metadata: PNG output chunks byte-identical to input (all 4, in order);
  JPEG output carries `eXIf` (EXIF bytes identical), `iTXt` (XMP bytes
  identical), `zTXt` (IPTC bytes identical), `iCCP` (profile bytes
  identical). Dimensions 2048×2048 in, 2048×2048 out.
* Pixels: below the strip, max channel change is 1/255 (the LSB audio);
  strip rows hold the code. JPEG cartridge vs Pillow's JPEG decode: max
  delta 1 (decoder rounding).
* Decoder page renders the browser cartridge (6 verses, EN + ES glosses,
  audio readyState 4, duration 58.417 s) and the Python cartridge alike;
  a plain PNG reports DAMAGE ("bad magic"); a one-pixel flip in the pack
  reports DAMAGE ("pack length mismatch"); a flip in the header reports
  DAMAGE ("audio SHA-256 mismatch"). Nothing unverified is ever shown.
* Oversize: a 64×64 image refuses loudly — 192,766 bytes of audio vs
  1,152 bytes of LSB capacity (16,733.2%), encode button disabled.
* Zero console errors on both pages, over HTTP and from `file://`.

### Follow-ups (not in this round)

* **Webpage-as-input** — rendering a page to pixels needs a page
  renderer; the encoder takes image files only for now.
* Cover the other 149 psalms (each: data JSON + audio + cover +
  cartridge + one `psalms/NNN/` viewer/encoder pair).

## Building a cartridge

```sh
# 1. Audio: MP3 -> Opus in WebM (plays on iPhone Safari; plain .opus/Ogg does not)
ffmpeg -i t2601.mp3 -c:a libopus -b:a 24k audio.webm

# 2. Chapter data (regenerate after editing the gloss table in
#    tools/build_psalm001_data.py)
python3 tools/build_psalm001_data.py

# 3. Cartridge: cover + text pack + audio
python3 tools/encode.py --cover psalms/001/cover.png \
    --audio psalms/001/audio.webm \
    --data tools/psalm001_data.json \
    --out psalms/001/cartridge.png

# 4. Verify (round-trip: exact bytes or DAMAGE)
python3 tools/decode.py psalms/001/cartridge.png \
    --out-text /tmp/text.json --out-audio /tmp/audio.webm
```

The encoder accepts `--audio` as optional: a cartridge without audio still
builds and decodes, with `audio_len: 0` in the header.

## Running the viewer

The viewer is an ES module and fetches its files, so serve the folder over
HTTP — opening the file directly will not work:

```sh
python3 -m http.server 8000        # from the project root
# open http://localhost:8000/  ->  white index  ->  psalms/001/
```

Controls: virtual joystick (bottom-left) or WASD to move; drag anywhere else
to look around; drag the scroll itself — or two-finger scroll / mouse wheel
over it — to read on when the text exceeds the sheet; tap/click the scroll
to play or pause the reading. `?lang=es` forces Spanish glosses;
`?scroll=0.5` starts halfway down the text.

The viewer decodes `cartridge.png` in the browser (see `decode.js`) and
renders the scroll from the decoded pack. If the cartridge is damaged it
says so on the scroll instead of failing silently. If `audio.webm` is
missing it shows a note and the scroll still reads fine.

## Refinement round — 2026-11-19 (Pol's first look at the live site)

* **Scroll is one continuous object** — the tan sheet and the tan rolls now
  share the same height (3.5), and the sheet's edge sits inside the roll
  (roll radius 0.5, centre ±3.8, sheet plane z = −0.30), so no seam or
  see-through gap shows from any angle.
* **Trackpad scroll reads the chapter** — a wheel / two-finger scroll over
  the scroll advances the text, in addition to drag-to-scroll. Scoped to
  the scroll by raycast; a wheel anywhere else does nothing.
* **Skybox visible** — the anime sky now shows. Root cause: the sky sphere
  winds inward (signed volume < 0) and its GLB material uses
  `KHR_materials_pbrSpecularGlossiness`, unsupported in three r160, so the
  old BackSide standard material rendered nothing and the dark-navy scene
  background showed through. The sky is now an unlit `MeshBasicMaterial`
  using the decoded texture, double-sided, un-tone-mapped.
* **Sleek glossy pillar arches** — the palace structure meshes (everything
  but the mosaic floor) are polished metal: metalness 1.0, roughness 0.05,
  near-white silver, lit by a RoomEnvironment PMREM map assigned
  per-material, so the pillars show clear bright reflections. The floor
  keeps its own material. Side effect: the central step/dais tip below the
  scroll is now bright metallic white and more noticeable (it never
  touches the text).
* Verified in headless WebKit (Playwright): zero console errors; wheel and
  drag tests pass with measured text offsets; screenshots inspected
  (default, outward, sky-up, pillar close-up, scroll side/back/joint).

## Refinement round 2 — 2026-11-19 (the very top of the skybox)

* **Zenith black disc — fixed.** Looking straight up showed a black disc
  (~5–7° radius, serrated edge, tiny blue speck at its centre) at the top
  of the sky. Root cause, measured: the skybox GLB file itself is cut
  short — its header declares 2,697,556 bytes but the file has 2,660,849
  (36,707 bytes missing off the end) — so its embedded JPEG has no EOI
  marker and its scan data ends ~70 rows early. The sphere's zenith pole
  samples exactly those bottom rows (v near 1.0), which decode as a flat
  fill (black in the browser), hence the disc. Sketchfab displays the
  same asset fine because its pipeline fills the missing rows
  differently. The fix is viewer-side, in `psalms/001/index.html`, and
  the GLB is untouched: the viewer parses the GLB container directly
  (`parseGlbContainer`, clamping chunk lengths to the bytes present),
  decodes the sky image straight out of the BIN chunk, and rebuilds the
  sky material by hand on a pure-white base. Two things that did NOT
  work, measured: `createImageBitmap` decodes this truncated JPEG as an
  all-black bitmap (mean luminance 0.000, no error thrown), so the decode
  goes through an `<img>` element over a blob: URL instead (verified
  working here: mean luminance 0.668, only the missing rows black); and
  the stock-like emissive material also showed the disc (brown, from the
  hemisphere ground light on the backfaces), so the material swap alone
  was never the fix. The pole band is healed (`healSkyPoleBand`, adapted
  from the rainbow globe's `healPoleTexture`): the bottom 8% of rows is
  compared against a 65–80% reference band, and the contiguous uniform
  run at the bottom edge is filled by extending the first good row
  downward with a light seam blur — the log reads
  `[sky] pole check: healed 72 rows …`. If the hand-built texture fails
  for any reason, the viewer falls back to GLTFLoader's own texture with
  the same bottom-row repair (`repairSkyTexture`).
* Verified in headless WebKit (Playwright): straight-up, max-drag-up,
  and yaw-90 straight-up views all show blue sky with clouds at the
  zenith (0 near-black pixels in the old disc zone); default and outward
  views unchanged; zero console errors.

## Still missing

* **Real cover art** — `psalms/001/cover.png` is a clearly marked
  placeholder. Replace that one file and re-run the encoder; nothing else
  changes.
* **GLB credit lines** — the viewer source carries the comment with both
  real lines, supplied by Pol 2026-11-19: `"FREE - SkyBox Anime Sky" by
  Paul` and `"Cloud palace column Hall" by xinige`. Credits live only in
  that comment, never in the 3D scene.
* More chapters — each is the same shape: data JSON + audio + cover +
  cartridge + one `psalms/NNN/` viewer. The index page lists them.
