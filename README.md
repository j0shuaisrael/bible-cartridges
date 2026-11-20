# Bible Cartridges — prototype (Psalm 1)

A chapter of Psalms steganographed into a PNG ("Bible cartridge"), presented
as a floating scroll in a first-person 3D scene. One isolated webapp per
chapter. This prototype is **Psalm 1 only**.

## Layout

```
index.html                  plain white "Index of /" directory listing (the hub)
assets/
  cloud-palace.glb          the platform (sky strip surgically removed, see below)
  skybox.glb                the surrounding sky (single sphere)
psalms/001/
  index.html                the Psalm 1 viewer (three.js) — THE TEMPLATE, see below
  chapter.js                chapter metadata: number, titles, filenames
  decode.js                 in-browser PSLM cartridge decoder
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

Planned later (not built yet): a separate encoder page per psalm — the
cartridge's "pregnant twin" maker — hooked to that psalm's chapter + audio,
which accepts an image and produces the cartridge. That page is a sibling
of the viewer, not part of it.

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
