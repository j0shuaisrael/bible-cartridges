# Audio-format investigation: Opus-in-WebM fails on Pol's iPhone

Date: 2026-11-20. Status: INVESTIGATION + DESIGN ONLY. No code changed, no
cartridge rebuilt, nothing pushed. Yashar decides before anything is (re)built.

Live report: Psalm 1's audio plays on Safari on Mac, FAILS on Pol's iPhone.
The viewer (`psalms/001/index.html`) plays a sidecar `audio.webm`
(Opus-in-WebM, single source, no fallback) through a plain `<audio>` element.
The standalone decoder (`decode.html`) plays the same Opus bytes from the
cartridge through a `blob:` URL. Both paths are Opus-only today.

## 1. The gap is confirmed — and it is worse than one bug

### Bug 238546 — "WebM Opus support still inconsistent in Safari 15.4"

Fetched 2026-11-20 from https://bugs.webkit.org/show_bug.cgi?id=238546.
The fetched page shows comments only; no resolution/status field was visible
in the fetch, and **nobody from Apple has ever updated the issue** (the
reporter's own meta-point in the last comment).

What exactly fails, per the bug:

- Safari 15.4, macOS 12.3: WebM Opus works with `canPlayType()`, `<audio>`,
  and `decodeAudioData`.
- Safari 15.4, iPadOS 15.4: `canPlayType()` returns "" (not detected),
  `<audio>` does not play — but the same bytes DO decode via
  `decodeAudioData`. The three surfaces disagree with each other.
- Reproduced by the reporter on iOS 15.5, iOS 16.1, and iOS 17: "There is no
  support for WebM Opus on iOS devices, although Web Audio is supported,
  exactly as per the original issue."
- A WebKit engineer (Jean-Yves Avenard) stated: "At this stage, webm is only
  supported on macOS and iPadOS. Not iOS." (Later comments show this was
  wrong/incomplete even for iPadOS — the reporter tested iPadOS and found it
  unsupported there too — but it is the only Apple-side statement on the bug.)

The Safari 17.4 fix claim:

- Apple release notes (Safari 17.4, 5 Mar 2024): "Added support for VP8/VP9
  and WebM on iOS and iPadOS." WebKit blog (WebKit Features in Safari 17.4):
  "WebM is fully supported everywhere" from 17.4; Vorbis added on iOS too.
- The reporter, testing 17.4: "As of Safari 17.4, at long long last, it seems
  WebM Opus is now finally supported consistently across iOS and macOS
  devices." Note the word **"seems"** — a single reporter's observation, not
  an Apple confirmation, and the bug was never closed or updated by Apple.
- Safari 17 release notes are narrower and macOS-only: "Added support for
  stereo-only Opus in MPEG-4 and WebM containers on macOS Sonoma."

So the 17.4 fix claim is: **plausible for direct-URL `<audio>` playback,
reported by one user, never confirmed by Apple, never closed on the bug.**
It does NOT hold as a guarantee, for three reasons:

1. Pol's iPhone fails TODAY. His iOS version is unknown (not guessed here);
   the failure is consistent with iOS < 17.4, and nothing rules out a newer
   version hitting the same inconsistency.
2. The sibling bug below still reproduces on 17.4.
3. MDN's audio-codec guide still says Safari supports Opus in `<audio>`
   "only when packaged in a CAF file, and only on macOS High Sierra (10.13)
   or iOS 11" — stale, predates WebM support, and therefore unreliable as a
   source on this point. Caniuse (as reported by multiple secondary sources)
   lists full WebM support from Safari 16 on macOS and Safari 17.4 on iOS,
   partial/unsupported before that.

### Bug 245428 — "Safari 16 cannot play WebM Opus from blob URL"

Fetched 2026-11-20 from https://bugs.webkit.org/show_bug.cgi?id=245428.
This one matters independently, because `decode.html` plays cartridge audio
from a `blob:` URL, not a file URL.

- Safari 16 macOS: the same WebM Opus file plays from a normal URL but
  produces NO audio (plus a console error) from a `blob:` URL
  (`URL.createObjectURL`). MP4/AAC from a blob URL works fine in the same
  build — only WebM Opus via blob is broken.
- Reproduced in Safari 17, and: "This still reproduces in Safari 17.4 which
  is meant to now have full support for WebM, but this issue still blocks us
  using WebM in Safari." (Ashley Gullen, same reporter.)
- Two further bugs (270772, 272502) were marked duplicates of it.
- No fix version is established anywhere in the fetched thread.

Consequence for this project: **even if Pol updates to iOS 17.4+, the
standalone decoder page (`decode.html`, blob URL) may still fail on Opus
while the viewer (file URL) works.** The two audio paths have different
failure modes and must both be fixed; fixing only the viewer's file URL
would leave the decoder page broken on the same phone.

### Known vs unknown

- KNOWN: Opus-in-WebM `<audio>` failed on iOS/iPadOS from 15.4 through 17.0
  (reporter-verified, three surfaces disagreeing); Apple added WebM on iOS
  in 17.4 per its own release notes; the blob-URL variant still reproduced
  on 17.4; AAC in MP4 plays everywhere on Apple devices (uncontested in
  every source checked).
- UNKNOWN: Pol's iOS version (the one fact that would say which failure mode
  he hit); whether 17.4+ direct-URL playback is reliable across devices
  (one reporter's "seems"); whether 245428 is fixed in any later version
  (no evidence found either way; iOS 18/26 behaviour unverified); whether
  `canPlayType('audio/webm; codecs=opus')` returns a truthful answer on
  17.4+ (it returned "" pre-17.4 while `decodeAudioData` worked — the probe
  has lied before, in the direction of false negative; the blob bug is a
  false positive: probe says playable, blob playback fails).

Design rule that follows: **never trust a version number or a probe alone.**
The decoder must probe AND fall back on playback error (see §4).

Side note: `README.md:307` says the Opus WebM "plays on iPhone Safari;
plain .opus/Ogg does not". That claim is now disproven by Pol's live report
and must be corrected when the format changes.

## 2. Measured sizes — AAC vs Opus (ffmpeg 8.1.2, /usr/bin/ffmpeg)

Encoder available: **native `aac` only. No `libfdk_aac`.**
(`ffmpeg -encoders` lists `aac` / `opus` / `libopus`; no fdk.) Quality per
bit is therefore the native encoder's, which at low bitrates is noticeably
below fdk_aac — one more reason not to go below 32 kbps for the AAC track
(see recommendation).

Sources: `tools/mp3/t2601.mp3` (Psalm 1: mono, 22,050 Hz, 32 kbps MP3,
58.136 s) and `tools/mp3/t26b9.mp3` (Psalm 119: stereo, 44,100 Hz,
128 kbps MP3, 1,136.117 s — the longest psalm, ~19 min).

Commands (the pipeline's own Opus command, `tools/build_psalm.py:145`,
plus AAC equivalents):

    ffmpeg -i tools/mp3/t2601.mp3 -c:a libopus -b:a 24k out.webm
    ffmpeg -i tools/mp3/t2601.mp3 -c:a aac -b:a 24k -movflags +faststart out.m4a
    (same at 32k / 48k, and for t26b9)

### Psalm 1 (58 s, mono)

| track | bytes |
|---|---|
| Opus 24k (fresh encode; shipped `audio.webm` is also 192,766 B) | **192,766** |
| AAC 24k (M4A) | 182,281 |
| AAC 32k (M4A) | 243,819 |
| AAC 48k (M4A) | 359,911 |

Fresh Opus re-encode is exactly the same SIZE as the shipped file
(192,766 B) but a different SHA-256 (different ffmpeg build than the one
that made the shipped file) — size-reproducible, not byte-reproducible.

Note: AAC 24k is SMALLER than Opus 24k here (mono 22 kHz source; the
container overhead dominates at this size). Do not generalise that to
stereo/long chapters — see Psalm 119.

### Psalm 119 (1,136 s, stereo)

| track | bytes |
|---|---|
| Opus 24k (fresh encode) | **3,929,703** |
| AAC 24k (M4A) | 3,525,911 |
| AAC 32k (M4A) | 4,835,384 |
| AAC 48k (M4A) | 7,074,986 |

Correction to the task brief: Psalm 119's Opus is **3,929,703 bytes
(~3.93 MB), not "~3.4 MB"**. The ~3.4 MB figure was an estimate from
Psalm 1's byte rate; the measured file is ~0.5 MB larger. All capacity
figures below use the measured 3,929,703.

## 3. Capacity impact

Models stored (unchanged): palace 291,028 + skybox 2,622,191 = **2,913,219**.
Capacities (strip_h = 16, as in `tools/encode.py`): 3072² d1 = 3,520,512;
4096² d1 = 6,266,880; 4096² d2 = 12,533,760; 2048² d2 = 3,121,152.
Payload = audio track(s) + 2,913,219 models.

### Psalm 1 (current payload 3,105,985 = 49.6% of 4096² d1)

| configuration | payload | 3072² d1 | 4096² d1 |
|---|---|---|---|
| Opus-only (today) | 3,105,985 | 88.2% | 49.6% |
| Dual, AAC 24k | 3,288,266 | 93.4% | 52.5% |
| Dual, AAC 32k | 3,349,804 | 95.2% | 53.5% |
| Dual, AAC 48k | 3,465,896 | 98.4% | 55.3% |
| AAC-only 24k | 3,095,500 | 87.9% | 49.4% |

Psalm 1 fits dual audio at every AAC bitrate, even in a 3072² cover at
depth 1. (At AAC 48k in 3072² d1 only 54,616 bytes spare — tight, but the
4096² cover is the shipped one anyway.)

### Psalm 119 (models 2,913,219; text strip will be taller than 16 rows —
see caveat below)

| configuration | payload | 4096² d1 | 4096² d2 |
|---|---|---|---|
| Opus-only (today) | 6,842,922 | 109.2% ✗ | 54.6% ✓ |
| Dual, AAC 24k | 10,368,833 | — | 82.7% ✓ (2,164,927 spare) |
| Dual, AAC 32k | 11,678,306 | — | 93.2% ✓ (855,454 spare) |
| Dual, AAC 48k | 13,917,908 | — | 111.0% ✗ (1,384,148 OVER) |
| AAC-only 24k | 6,439,130 | 102.7% ✗ | 51.4% ✓ |
| AAC-only 32k | 7,748,603 | — | 61.8% ✓ |
| AAC-only 48k | 9,988,205 | — | 79.7% ✓ |

### Verdict

- **No psalm becomes unfittable under the recommendation (dual, AAC 32k).**
  Psalm 119, the longest chapter, fits dual audio at 32k in a 4096² cover
  at depth 2 with 855,454 bytes spare. Every shorter psalm fits with more
  room (Psalm 1 fits even in 3072² d1).
- **AAC 48k dual is the one combination that breaks: Psalm 119 exceeds
  the maximum planned capacity (4096², depth 2) by 1,384,148 bytes.**
  48k is therefore ruled out for dual audio, whatever its quality appeal.
- Caveat: the table uses strip_h = 16. Psalm 119's text pack (176 verses)
  is far larger than Psalm 1's, so its real strip will be taller; each
  extra strip row at 4096² d2 costs 3,072 bytes of LSB capacity. Even 100
  extra rows cost only 307,200 bytes — absorbed by the 855,454 spare at
  32k dual, and irrelevant to the 48k verdict (already over by 1.38 MB).
  The encoder's loud-refusal numbers (already built in) remain the guard.
- Further dials, NOT adopted now (listed only so they exist): downmixing
  Psalm 119's stereo source to mono would roughly halve its audio tracks;
  dropping AAC to 24k buys 1.31 MB on Psalm 119. Neither is needed at 32k.

## 4. Proposed format change — exact design

### Version: v4, not v3.1

This is a breaking wire change, so it gets a major bump:

- The LSB bitstream gains a second audio section before the models; a v3
  decoder reading a v4 cartridge would slice the stream at the wrong
  offsets (it reads `audio_len` bytes as the single audio, then models from
  the wrong place) and fail SHA checks. A minor bump would imply v3 readers
  can still read it. They cannot — and must not pretend to.
- The header drops the single-audio fields for an audio-track list (below).
- The version byte at offset [4] already gates this cleanly: v3 decoders
  reject any version outside {2, 3} with "unsupported PSLM version", so a
  v4 cartridge fails LOUDLY on old decoders (DAMAGE/unsupported), never
  silently wrong. v2/v3 read support stays in all decoders.

### Header (v4) — exact fields

Replace the three single-audio fields:

```json
"audio_len": 192766,
"audio_sha256": "<hex>",
"audio_format": "opus-webm",
```

with one list (Opus first — it stays the preferred track where it plays):

```json
"audio": [
  {"format": "opus-webm", "mime": "audio/webm; codecs=opus",
   "len": 192766, "sha256": "<hex>"},
  {"format": "aac-mp4", "mime": "audio/mp4; codecs=mp4a.40.2",
   "len": 243819, "sha256": "<hex>"}
]
```

- `format` values: `"opus-webm"` (existing string, kept) and `"aac-mp4"`
  (new). `mime` is the exact string passed to `canPlayType` — stored in
  the header so the probe string is data, not hardcoded in the decoder.
- `len`/`sha256` per track; every track is SHA-256-verified like every
  other payload today. A track failing verification is DAMAGE, same as now
  (a corrupt AAC track must not silently fall back to Opus-less silence —
  it must report DAMAGE; the Opus/AAC choice is a playback decision, not
  an integrity decision).
- No legacy `audio_len`/`audio_sha256`/`audio_format` kept in v4 headers:
  v3 decoders reject v4 by version byte anyway, so the old fields would buy
  nothing and would be a second source of truth. v2/v3 cartridges keep
  their old fields and keep decoding exactly as today.
- `models`, `pack_*`, `strip_h`, `cover_w/h`, `lsb_depth` unchanged.

### LSB bitstream section order (v4)

Unchanged pattern, one more section:

1. audio track 1 (Opus, `audio[0].len` bytes)
2. audio track 2 (AAC, `audio[1].len` bytes)
3. each model in header order (stored bytes, as today)

Total LSB payload = sum of audio lens + sum of model `stored_len`s.
The visible strip (magic/version/header/pack) is unchanged in structure.

### Encoder changes

`tools/encode.py`:
- `VERSION = 4`; `build_header()` emits the `"audio"` list; `build_model*`
  untouched.
- New input: the AAC file. Preferred interface: `--audio-aac audio.m4a`
  alongside existing `--audio audio.webm` (both optional individually; at
  least one required — a cartridge with neither is today's no-audio case).
  The encoder reads both files, hashes both, packs Opus then AAC then
  models, and prints both sizes + both SHA prefixes the way it prints the
  single audio line today.
- Refusal messages must list BOTH audio sizes (e.g. "audio 192,766 Opus +
  243,819 AAC + palace stored …"), and `min_square_side` unchanged.
- `--remote-models` / `--text-audio-only` logic unchanged: "audio" in
  those paths means both tracks together; the models are what those
  opt-ins drop, never an audio track.
- The "FULL QUALITY IS THE DEFAULT" rule extends: no lower Opus bitrate,
  no lower AAC bitrate than the chosen 32k, unless explicitly opted in.

`tools/build_psalm.py` (pipeline — the place the AAC file gets MADE):
- Add an AAC step next to the existing Opus step (line ~145):
  `ffmpeg -y -v error -i <mp3> -c:a aac -b:a 32k <psalm-dir>/audio.m4a`,
  probe it the same way (duration/codec/sample-rate/channels/size), and
  pass both files to `encode.py`. The psalm folder then carries
  `audio.webm` + `audio.m4a` side by side (the viewer plays the sidecars;
  see below).
- `tools/build_psalm.py`'s verify step (decode round-trip) must decode and
  SHA-check BOTH audio tracks, not just Opus.

`psalms/encode.html` (browser encoder — one universal encoder page):
- It cannot SYNTHESISE AAC: it has no AAC encoder (WebCodecs `AudioEncoder`
  supports AAC only in Safari 26+; MediaRecorder is a recorder, not a
  transcoder). It must FETCH a pre-made `audio.m4a` exactly the way it
  already fetches `audio.webm` (line ~2025: `fetch(`${nnn}/audio.webm`)`).
- So: fetch `${nnn}/audio.m4a` alongside; `planEncode`/`buildCartridge`
  take both byte arrays and build the v4 header + stream; the "Audio:" rows
  in the plan UI list both tracks; the embedded fallback
  (`EMBEDDED_AUDIO_B64`, Psalm 1 only, file:// use) needs an AAC twin
  (`EMBEDDED_AUDIO_AAC_B64`) or the browser encoder cannot make a dual
  Psalm 1 cartridge from file:// — flag as a build detail for whoever
  implements it (the AAC bytes are 243,819 B base64 ≈ 325 KB added to the
  page; acceptable, same pattern as the existing embedded Opus).
- Its self-check decoder (line ~1800) must verify both track SHAs.

`tools/decode.py` (Python verifier):
- Accept version 4 (and keep 2/3). Read the `"audio"` list; verify each
  track's SHA-256; return both.
- CLI: `--out-audio` keeps writing the Opus track by default; add
  `--out-audio-track {opus,aac}` (default `opus`) to extract the AAC one.
  Print both tracks ("audio: Opus 192,766 B sha256 verified; AAC 243,819 B
  sha256 verified").

### Decoder changes

`psalms/001/decode.js` (+ the inlined copy in `decode.html` — the two must
stay mirrored, per the file's own header comment):
- `VERSIONS = [2, 3, 4]`.
- Parse v4: `audioTracks = header.audio` (list of {format, mime, len,
  sha256}); read each section in order from the LSB stream; SHA-verify
  each. Parse v2/v3: synthesise a one-element list from the legacy fields
  (`audio_format` → format, `audio_len`, `audio_sha256`, mime derived:
  `opus-webm` → `audio/webm; codecs=opus`).
- Return shape: `{header, pack, audio, audioTracks, models}` where
  `audioTracks` is `[{format, mime, bytes}]` for every track and `audio`
  stays the Opus bytes when present (else the first track) — preserving
  every existing caller. New callers use `audioTracks`.
- New helper, `pickAudioTrack(audioEl, audioTracks)`: probe with
  `canPlayType(track.mime)` for each track in header order; first track
  whose probe returns `"probably"` or `"maybe"` wins; if all probes return
  `""`, fall back to the LAST track (AAC — the universal one) rather than
  the first, and let the error handler below have the final say. Rationale:
  the probe has lied in both directions on iOS (false negative pre-17.4,
  false positive on blob URLs per bug 245428), so the probe picks the
  FIRST ATTEMPT, never the final answer.
- Error-driven fallback (mandatory, in both pages): attach the `error`
  listener BEFORE setting `src`. If the chosen track errors, swap to the
  next track in the list (Opus → AAC) and try once; if that errors too,
  report "audio unavailable". This is what saves the decode.html blob-URL
  case, where the probe can say "probably" for Opus and playback still
  fails.

`psalms/001/index.html` (viewer) and the viewer half of `decode.html`:
- The viewer today plays the SIDECAR file, not the cartridge audio:
  `document.getElementById('chap-audio').src = CHAPTER.audio`
  (`chapter.js`: `audio: 'audio.webm'`). Two sub-changes:
  1. `chapter.js`: add `audioAac: 'audio.m4a'` next to `audio: 'audio.webm'`
     (the file is made by the pipeline and shipped in the psalm folder).
  2. `index.html`: at load, run the same `pickAudioTrack` probe against
     the two sidecar URLs and set `audio.src` to the winner; keep the
     existing `error` listener, extended to swap to the other sidecar on
     error (same one-swap rule). `toggleAudio()` logic is otherwise
     unchanged.
- `decode.html` (standalone decoder): same selection, but over the DECODED
  bytes: `URL.createObjectURL(new Blob([track.bytes],
  {type: track.mime.split(';')[0]}))` — Opus → `audio/webm`, AAC →
  `audio/mp4`. Its existing `<audio id="player">` (line ~1374, also
  blob-URL Opus) gets the same treatment. Revoke the old object URL on
  swap (the page already revokes on teardown, line ~1241).

### canPlayType probe at load + status line — YES

Recommend yes, for both pages, with reasons:

- It determines which track to attempt BEFORE the user taps, so the first
  tap plays instead of failing once and then recovering.
- It lets the status line state the choice up front, which is the only way
  Pol (or anyone debugging on a phone) can see what happened without
  opening a console. Proposed wording, appended to the existing
  `refreshStatus()` bits:
  - Opus chosen: `audio Opus`
  - AAC chosen: `audio AAC` (on the viewer; on the decoder page, when the
    probe fell through to AAC, `audio AAC (Opus unsupported here)`)
  - Neither plays after both attempts: `audio unavailable` + hint text
    `Audio won't play on this device — the scroll still reads fine.`
    (mirrors the existing "Audio file not available — the scroll still
    reads fine." wording; never a silent dead tap).
- Cost is one probe call per track at load; no playback, no download
  (blob URLs are already in memory; sidecar files are only probed by MIME,
  not fetched — `canPlayType` does not fetch).
- The probe is NOT trusted as the final answer: the error-driven fallback
  above is what makes the design sound despite the probe's history of
  lying (see §1). Probe-first + error-fallback is the combination; either
  alone is insufficient on iOS.

### Zero site dependence — confirmed, holds

Both tracks live inside the cartridge (v4 LSB stream), exactly like the
GLBs: no fetch, no per-decode cost, works from file://. The viewer's
sidecar files (`audio.webm` / `audio.m4a`) are same-origin files shipped
with the page — the same pattern as today, not a new dependency. The
decoder page's audio comes only from the cartridge bytes. Nothing in this
design phones home, fetches a model/audio from the site, or needs the
network for audio.

## 5. Alternatives, with numbers

### (a) Dual Opus + AAC (recommended)

- Psalm 1: +182,281 B (AAC 24k) to +243,819 B (AAC 32k) — payload
  3,288,266–3,349,804; 4096² d1, 52–54%.
- Psalm 119: +3,525,911 B (24k) to +4,835,384 B (32k) — payload
  10,368,833–11,678,306; 4096² d2, 83–93%.
- Keeps Opus as the primary everywhere it works (smaller, open codec,
  better quality per bit) and AAC as the universal Apple fallback. Format
  cost is one new header shape + one new LSB section. Every psalm still
  fits (see §3).

### (b) AAC-only

- Simpler format (single track; could arguably stay v3 with
  `audio_format` changed — but the JS mime/probe/selection changes are
  needed either way, so the saving is small).
- Psalm 1 at AAC 32k: payload 3,157,038 (vs 3,105,985 today, +51,053).
  Psalm 119 at AAC 32k: payload 7,748,603 (vs 6,842,922 Opus-only,
  +905,681) — fits 4096² d2 at 61.8%.
- Costs: every cartridge gets bigger on non-Apple devices too (Psalm 119
  +906 KB for no benefit there); Opus — the better codec at these
  bitrates, and the open one — is abandoned for the sake of the fallback;
  and the "full quality" default is weakened for the majority of listeners
  to serve the Apple edge case. The size saving over dual is real but
  small (Psalm 119: 7.75 MB vs 11.68 MB) and buys nothing the dual format
  doesn't already fit.

### (c) Opus-only (status quo)

- Zero size cost, zero work. Also zero audio on Pol's iPhone — the live
  failure that started this investigation — and on any iOS < 17.4, plus
  the blob-URL failure mode on the decoder page even on 17.4+. Rejected.

### Recommendation: (a) dual audio, AAC at 32 kbps, PSLM v4

- 32 kbps is the highest AAC rate under which the LONGEST psalm still
  fits dual audio in the largest planned cover (Psalm 119: 93.2% of
  4096² d2). 48k is ruled out by capacity (§3); 24k fits with more
  headroom but the native (non-fdk) AAC encoder at 24k stereo is thin
  for a spoken reading, and 24k is documented as the fallback dial if a
  future chapter ever strains capacity.
- Opus stays 24k and stays first/preferred: nothing about the primary
  track changes for listeners whose browsers already play it.
- **`<source>` children vs JS selection: JS selection via `canPlayType`,
  explicitly.** Native `<source>` fallback is silent (no status-line
  reporting, no way to say which track played) and its error behaviour
  is unreliable — a failed `<source>` does not deterministically advance
  to the next one on decode failure, which is exactly the failure mode
  bug 245428 describes. JS selection is explicit, reportable in the
  status line, and pairs with the one-swap error fallback that the blob
  case requires.

## 6. Sequencing note (not a code change)

The viewer and the decoder page have DIFFERENT audio sources today, so
the fix lands in two steps with different costs:

1. **Viewer (cheap, immediate, no re-encode):** ship `audio.m4a` next to
   `audio.webm` in `psalms/001/` and add the probe + error-fallback
   selection in `index.html`/`chapter.js`. This fixes Pol's iPhone on the
   page he actually uses, without touching any cartridge.
2. **Cartridge (durable, needs re-encode):** v4 dual-audio cartridges via
   the `encode.py` / `build_psalm.py` / `encode.html` changes in §4, so
   the standalone decoder page (`decode.html`, blob URL) also plays on
   iOS. That page cannot be fixed by a sidecar file — its audio comes
   only from the cartridge.

Step 1 without step 2 leaves the decoder page broken on iOS; step 2
without step 1 leaves the viewer playing the sidecar anyway (it does not
read cartridge audio today). Both are needed; step 1 can ship first.

Also to correct alongside: `README.md:307` ("plays on iPhone Safari") and
any other place that asserts Opus plays on iPhone (grep for it at
implementation time).

## 7. Still unknown / needs a human or a device

- **Pol's iOS version.** The single most informative fact: it decides
  whether he hit the pre-17.4 gap, the 17.4 blob bug, or something else.
  The dual-audio fix covers all three, so it is not a blocker — but it
  should still be asked, because it tells us whether 17.4+ direct-URL
  playback can be trusted at all.
- Whether bug 245428 (blob-URL Opus) is fixed in iOS 18/26. No evidence
  found either way. The error-fallback design assumes NOT fixed.
- Whether `canPlayType('audio/webm; codecs=opus')` returns `"probably"` on
  Pol's phone (false positive) or `""` (honest negative). Only a live
  probe on the device answers this; the design does not depend on it.
- Real-device verification of the fix: the AAC track must be played on
  Pol's actual iPhone (viewer + decoder page) before the change is
  called done. No headless probe here can substitute for that.
- The exact Psalm 119 text-pack/strip height (affects the 855,454-byte
  spare at 32k dual by at most a few hundred KB — see §3 caveat).
- `fdk_aac` is unavailable in this ffmpeg build; if a better AAC encoder
  were wanted later, it would need a different ffmpeg build — out of scope
  for this fix.

## 8. Change list (for Yashar's decision — nothing done yet)

| file | change |
|---|---|
| `tools/encode.py` | VERSION 4; `--audio-aac`; `"audio"` list header; Opus+AAC+models LSB order; dual sizes in refusal/printing |
| `tools/build_psalm.py` | AAC 32k step (`audio.m4a`); pass both files to encoder; verify both tracks on round-trip |
| `tools/decode.py` | Accept v4; verify both track SHAs; `--out-audio-track {opus,aac}` |
| `psalms/001/decode.js` | VERSIONS + 4; `audioTracks`; `pickAudioTrack()` probe helper |
| `decode.html` | Mirror decode.js; blob-URL selection Opus→AAC + error fallback; status wording |
| `psalms/001/index.html` | Sidecar selection (Opus→AAC) + error fallback; status wording |
| `psalms/001/chapter.js` | Add `audioAac: 'audio.m4a'` |
| `psalms/encode.html` | Fetch `audio.m4a`; v4 header/stream; `EMBEDDED_AUDIO_AAC_B64` for file:// Psalm 1; dual self-check |
| `README.md` (+ PIPELINE.md if it repeats it) | Correct "plays on iPhone Safari" |
| Rebuild | Psalm 1 cartridge to v4 (dual audio); Psalm 119 when built |

## Appendix — measurements log

- ffmpeg 8.1.2, `/usr/bin/ffmpeg`, Ubuntu build; encoders present: native
  `aac`, `opus`, `libopus`; `libfdk_aac` absent.
- Test files written to `/tmp/audio-meas/` (not in the repo):
  `t2601_aac_{24k,32k,48k}.m4a`, `t2601_opus24.webm`,
  `t26b9_aac_{24k,32k,48k}.m4a`, `t26b9_opus24.webm`.
- `ffprobe` on sources: t2601 = mono 22,050 Hz, 58.136 s; t26b9 = stereo
  44,100 Hz, 1,136.117 s.
- Sources consulted 2026-11-20: bugs.webkit.org 238546, 245428; Apple
  Safari 17.4 release notes ("Added support for VP8/VP9 and WebM on iOS
  and iPadOS"); WebKit blog "WebKit Features in Safari 17.4" ("WebM is
  fully supported everywhere"); Safari 17 release notes (stereo-only Opus
  in WebM/MP4 on macOS Sonoma only); MDN Web audio codec guide; caniuse
  via secondary sources.

## Addendum — 2026-11-20 ~20:35 PST: Pol's phone is NOT a codec failure

New symptom evidence from Pol's iPhone changes the picture for HIS
device: the hint reads "Playing the reading — tap scroll to pause".
That means the file LOADED (canplay fired, audioReady true) and
play() succeeded — the codec decodes fine on his phone. The sound is
being muted between the player and his ears, most likely the iPhone's
silent switch, which silences web audio even while the page says it
is playing.

Consequences:
- The v4 dual-audio work above is now a COMPATIBILITY ENHANCEMENT
  for older iOS / other devices, NOT a fix for Pol's phone and NOT a
  blocker. Nothing is rebuilt on its basis until Yashar says so.
- The HOLD on encoding final cartridges stays ONLY until Pol confirms
  the silent switch was the cause. If he confirms, the Opus-only
  cartridges stand as built.
- Bugs 238546/245428 remain real for other devices (older iOS, blob-URL
  decoder page) — the investigation's findings and measurements stand;
  only the urgency and the target device change.

## Confirmation — 2026-11-20 ~20:37 PST: silent mode, hold lifted

Pol confirmed: it was the iPhone silent mode. He turned it off and the
audio plays on his iPhone 16 Pro. Opus WebM DOES decode and play on a
real iPhone — no codec failure. HOLD LIFTED: final cartridges resume
with Opus audio as designed. The v4 dual-audio design above stays as a
compatibility enhancement for older iOS / other devices; no cartridge
is rebuilt on its basis unless Yashar says so.
