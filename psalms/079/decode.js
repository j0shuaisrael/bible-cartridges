// decode.js — PSLM cartridge decoder (v2 and v3), shared by the viewer
// (psalms/NNN/index.html) and the standalone decoder page (decode.html).
// If this file changes, mirror the change into decode.html's inlined copy.
//
// Format (PSLM v3; v2 cartridges still read — models come back null):
//   PNG pixels, row-major. Top strip rows hold the text pack (zlib) as a
//   visible RGB strip: 3 bytes per pixel, header first.
//   Strip blob: 4 bytes magic "PSLM", 1 byte version, 4 bytes BE header_len,
//   header JSON (UTF-8), then the zlib-compressed text pack (pack_comp_len).
//   Header fields: format, version, chapter, languages[], fallback,
//   pack_len, pack_comp_len, pack_sha256, audio_len, audio_sha256,
//   audio_format, strip_h, cover_w, cover_h, lsb_depth (1|2, v3 only),
//   models[] (v3 only): [{name, len, sha256, stored_len, compressed}].
//   Below the strip, ONE LSB bitstream at lsb_depth bits per channel,
//   MSB-first within each byte, sections in order: audio (audio_len bytes,
//   raw Opus/WebM), then each model in header order (stored_len bytes;
//   zlib-compressed iff compressed is true, else raw GLB bytes).
//   Every payload (text pack, audio, each model) is SHA-256-verified; any
//   mismatch throws, and the caller reports DAMAGE. The decoder never
//   fetches language data or models: everything comes out of the image.
//
// Transliteration: the lexicon stores ONE Latin transliteration per word
// (the verified pronunciation). The tables below render that same
// pronunciation in the reader's own alphabet, chosen by gloss language.
// Transliteration is RULES, not data: a small table per script, computed
// at render time. Latin itself is the identity (en/es/pt/fr/de/id and
// zh-pinyin). Nothing is fetched at decode time.

const MAGIC = [0x50, 0x53, 0x4c, 0x4d]; // "PSLM"
const VERSIONS = [2, 3];

function hexSha256(bytes) {
  // SHA-256 via the browser's built-in crypto (async).
  return crypto.subtle.digest('SHA-256', bytes).then((buf) =>
    [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join(''));
}

// Inflate a zlib stream. Tries 'deflate' first (WebKit accepts zlib streams
// there); falls back to stripping the 2-byte zlib header + 4-byte Adler
// trailer and inflating the raw deflate body (spec engines).
async function inflateZlib(bytes) {
  try {
    const ds = new DecompressionStream('deflate');
    const out = await new Response(new Blob([bytes]).stream().pipeThrough(ds)).arrayBuffer();
    return new Uint8Array(out);
  } catch (e) {
    const ds = new DecompressionStream('deflate-raw');
    const out = await new Response(new Blob([bytes.slice(2, -4)]).stream().pipeThrough(ds)).arrayBuffer();
    return new Uint8Array(out);
  }
}

function stripBytes(data, w, n) {
  // First n bytes of the visible strip, row-major, RGB order (skip alpha).
  const out = new Uint8Array(n);
  const rows = Math.ceil(n / (w * 3));
  let p = 0;
  for (let y = 0; y < rows; y++) {
    for (let x = 0; x < w; x++) {
      if (p >= n) return out;
      const i = (y * w + x) * 4;
      out[p++] = data[i];
      if (p >= n) return out;
      out[p++] = data[i + 1];
      if (p >= n) return out;
      out[p++] = data[i + 2];
    }
  }
  return out;
}

// Read `n` bytes from the LSB bitstream below the strip, at `depth` bits
// per channel (1 or 2), MSB-first within each byte, row-major, RGB order.
function lsbBytes(data, w, h, stripH, n, depth) {
  const out = new Uint8Array(n);
  let bit = 0;
  const total = n * 8;
  const mask = (1 << depth) - 1;
  for (let y = stripH; y < h; y++) {
    for (let x = 0; x < w; x++) {
      if (bit >= total) return out;
      const i = (y * w + x) * 4;
      for (let c = 0; c < 3; c++) {
        if (bit >= total) return out;
        const chunk = data[i + c] & mask;
        for (let b = depth - 1; b >= 0; b--) {
          if (bit >= total) return out;
          if ((chunk >> b) & 1) out[Math.floor(bit / 8)] |= 1 << (7 - (bit % 8));
          bit++;
        }
      }
    }
  }
  if (bit < total) throw new Error('cartridge truncated: LSB layer ended before the payload did');
  return out;
}

export async function decodeCartridge(url) {
  const img = new Image();
  img.src = url;
  await img.decode();
  const canvas = document.createElement('canvas');
  canvas.width = img.naturalWidth;
  canvas.height = img.naturalHeight;
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  ctx.drawImage(img, 0, 0);
  const { data } = ctx.getImageData(0, 0, canvas.width, canvas.height);
  const w = canvas.width, h = canvas.height;

  const head = stripBytes(data, w, 9);
  if (!MAGIC.every((b, i) => b === head[i])) {
    throw new Error('not a PSLM cartridge (bad magic)');
  }
  const version = head[4];
  if (!VERSIONS.includes(version)) {
    throw new Error(`unsupported PSLM version ${version} (this decoder reads v2 and v3)`);
  }
  const hlen = new DataView(head.buffer, head.byteOffset + 5, 4).getUint32(0, false);
  const headerRaw = stripBytes(data, w, 9 + hlen).subarray(9);
  const header = JSON.parse(new TextDecoder().decode(headerRaw));
  if (header.format !== 'PSLM' || header.version !== version) {
    throw new Error('header/version mismatch');
  }

  const stripH = header.strip_h;
  const blobLen = 9 + hlen + header.pack_comp_len;
  const blob = stripBytes(data, w, blobLen);
  const comp = blob.subarray(9 + hlen);
  const packBytes = await inflateZlib(comp);
  if (packBytes.length !== header.pack_len) {
    throw new Error('pack length mismatch — cartridge damaged');
  }
  if ((await hexSha256(packBytes)) !== header.pack_sha256) {
    throw new Error('pack SHA-256 mismatch — text damaged');
  }
  const pack = JSON.parse(new TextDecoder().decode(packBytes));

  // LSB stream: audio first, then the v3 model sections, in header order.
  const depth = header.lsb_depth || 1;
  const models = version === 3 && Array.isArray(header.models) ? header.models : [];
  const totalLsb = header.audio_len + models.reduce((s, m) => s + m.stored_len, 0);
  const stream = totalLsb ? lsbBytes(data, w, h, stripH, totalLsb, depth) : new Uint8Array(0);
  let off = 0;
  let audio = null;
  if (header.audio_len) {
    audio = stream.slice(off, off + header.audio_len); off += header.audio_len;
    if ((await hexSha256(audio)) !== header.audio_sha256) {
      throw new Error('audio SHA-256 mismatch — audio damaged');
    }
  }
  const decodedModels = {};
  for (const m of models) {
    const stored = stream.slice(off, off + m.stored_len); off += m.stored_len;
    const bytes = m.compressed ? await inflateZlib(stored) : stored;
    if (bytes.length !== m.len) {
      throw new Error(`model ${m.name} length mismatch: ${bytes.length} != ${m.len}`);
    }
    if ((await hexSha256(bytes)) !== m.sha256) {
      throw new Error(`model ${m.name} SHA-256 mismatch — model damaged`);
    }
    decodedModels[m.name] = bytes;
  }
  return { header, pack, audio, models: version === 3 ? decodedModels : null };
}

// Best packed language for a device language tag ("es-MX" -> "es",
// "en-US" -> "en", anything unpacked -> header fallback, usually "en").
// Hebrew + transliteration always work regardless of language.
export function pickLanguage(header, deviceLanguage) {
  const langs = header.languages || [];
  const tag = (deviceLanguage || '').toLowerCase();
  if (langs.includes(tag)) return tag;
  const primary = tag.split('-')[0];
  if (langs.includes(primary)) return primary;
  return header.fallback || 'en';
}

// ---- transliteration: Latin (SBL) -> the reader's own alphabet ---------
// The lexicon's `t` field is the verified Latin pronunciation. These
// tables render that same pronunciation in Cyrillic, Arabic, Devanagari,
// Hangul or kana, chosen by gloss language. Latin is the identity for
// en/es/pt/fr/de/id, and pinyin for zh. YHWH is special-cased per script
// (each language's standard rendering of the divine name).

const DIGRAPHS = ['sh', 'kh', 'ch', 'tz', 'ts']; // 'ts' = the צ affricate, spelled both 'ts' and 'tz' in the data

function scanLatin(s) {
  // Split a Latin transliteration into phonemes (digraphs first).
  const out = [];
  for (let i = 0; i < s.length;) {
    const two = s.slice(i, i + 2).toLowerCase();
    if (DIGRAPHS.includes(two)) { out.push(two); i += 2; }
    else { out.push(s[i].toLowerCase()); i += 1; }
  }
  return out;
}

// Pronounced glottal letters of a Hebrew token, in order: ayin anywhere,
// alef except as the token's first consonant (word-initial alef is silent
// in these transliterations). Used to tell ء (alef) from ع (ayin) in
// Arabic; other scripts use one mark for both.
function glottalKinds(hebrew) {
  const kinds = [];
  const letters = [...(hebrew || '')].filter((ch) => ch >= '\u05D0' && ch <= '\u05EA');
  letters.forEach((ch, i) => {
    if (ch === '\u05E2') kinds.push('ayin');
    else if (ch === '\u05D0' && i !== 0) kinds.push('alef');
  });
  return kinds;
}

// --- Cyrillic (alphabetic: letters just concatenate) ---
const CYR = { a: '\u0430', e: '\u0435', i: '\u0438', o: '\u043E', u: '\u0443', y: '\u0439', b: '\u0431', v: '\u0432', g: '\u0433', d: '\u0434', h: '\u0445', z: '\u0437', t: '\u0442', k: '\u043A', l: '\u043B', m: '\u043C', n: '\u043D', s: '\u0441', p: '\u043F', f: '\u0444', r: '\u0440', sh: '\u0448', kh: '\u0445', ch: '\u0445', tz: '\u0446', ts: '\u0446', "'": '\u044A', '-': '-' };
function renderCyrillic(phonemes) {
  return phonemes.map((p, i) => {
    if (p === 'e' && i === 0) return '\u044D'; // word-initial e -> э
    return CYR[p] ?? p;
  }).join('');
}

// --- Arabic (alphabetic; short vowels as matres, no tashkeel) ---
const AR = { a: '\u0627', e: '\u064A', i: '\u064A', o: '\u0648', u: '\u0648', y: '\u064A', b: '\u0628', v: '\u06A4', g: '\u062C', d: '\u062F', h: '\u0647', z: '\u0632', t: '\u062A', k: '\u0643', l: '\u0644', m: '\u0645', n: '\u0646', s: '\u0633', p: '\u0628', f: '\u0641', r: '\u0631', sh: '\u0634', kh: '\u062E', ch: '\u062E', tz: '\u062A\u0633', ts: '\u062A\u0633', '-': '-' };
function renderArabic(phonemes, kinds) {
  let k = 0;
  return phonemes.map((p) => {
    if (p === "'") {
      const kind = kinds[k++] || 'alef';
      return kind === 'ayin' ? '\u0639' : '\u0621';
    }
    return AR[p] ?? p;
  }).join('');
}

// --- Devanagari (abugida: consonant + vowel matra; bare consonant takes
// a halant) ---
const DEVA_CONS = { b: '\u092C', v: '\u0935', g: '\u0917', d: '\u0926', h: '\u0939', z: '\u091C\u093C', t: '\u0924', k: '\u0915', l: '\u0932', m: '\u092E', n: '\u0928', s: '\u0938', p: '\u092A', f: '\u092B\u093C', r: '\u0930', y: '\u092F', sh: '\u0936', kh: '\u0916\u093C', ch: '\u0916\u093C', tz: '\u0924\u094D\u0938', ts: '\u0924\u094D\u0938' };
const DEVA_VOW = { a: ['\u0905', '\u093E'], i: ['\u0907', '\u093F'], u: ['\u0909', '\u0941'], e: ['\u090F', '\u0947'], o: ['\u0913', '\u094B'] };
const HALANT = '\u094D';
function renderDevanagari(phonemes) {
  let out = '', pending = null;
  const flush = () => { if (pending) { out += pending + HALANT; pending = null; } };
  for (const p of phonemes) {
    if (DEVA_VOW[p]) {
      if (pending) { out += pending + DEVA_VOW[p][1]; pending = null; }
      else out += DEVA_VOW[p][0];
    } else if (p === "'") { flush(); out += '\u093D'; }
    else if (p === '-') { flush(); out += '-'; }
    else if (DEVA_CONS[p]) { flush(); pending = DEVA_CONS[p]; }
    else { flush(); out += p; }
  }
  flush();
  return out;
}

// --- Hangul (syllabic: onset + vowel + optional coda, one code point) ---
// Onset indices (Choseong): ㄱ0 ㄲ1 ㄴ2 ㄷ3 ㄸ4 ㄹ5 ㅁ6 ㅂ7 ㅃ8 ㅅ9 ㅆ10 ㅇ11
//   ㅈ12 ㅉ13 ㅊ14 ㅋ15 ㅌ16 ㅍ17 ㅎ18. Vowel indices (Jungseong, verified
//   against known syllables): ㅏ0 ㅐ1 ㅑ2 ㅒ3 ㅓ4 ㅔ5 ㅖ6 ㅖ7 ㅗ8 ㅘ9 ㅙ10
//   ㅚ11 ㅛ12 ㅜ13 ㅝ14 ㅞ15 ㅟ16 ㅠ17 ㅡ18 ㅢ19 ㅣ20. Coda indices
//   (Jongseong): none0 ㄱ1 ㄲ2 ㄳ3 ㄴ4 ㄵ5 ㄶ6 ㄷ7 ㄹ8 ㄺ9 ㄻ10 ㄼ11 ㄽ12 ㄾ13
//   ㅀ15 ㅁ16 ㅂ17 ㅄ18 ㅅ19 ㅆ20 ㅇ21 ㅈ22 ㅊ23 ㅋ24 ㅌ25 ㅍ26 ㅎ27.
const HANG_ONSET = { b: 7, v: 7, g: 0, d: 3, h: 18, z: 12, t: 16, k: 15, l: 5, m: 6, n: 2, s: 9, p: 17, f: 17, r: 5, sh: 9, kh: 15, ch: 15, tz: 12, ts: 12 };
const HANG_CODA = { b: 17, v: 17, g: 1, d: 7, h: 27, z: 22, t: 25, k: 24, l: 8, m: 16, n: 4, s: 19, p: 26, f: 26, r: 8, sh: 19, kh: 24, ch: 24, tz: 22, ts: 22 };
const HANG_VOW = { a: 0, e: 5, i: 20, o: 8, u: 13 };
const HANG_YVOW = { a: 2, e: 7, o: 12, u: 17, i: 20 };
function renderHangul(phonemes) {
  const syls = []; // {onset, vowel, coda} or '-' markers
  let pendingOnset = null; // onset index waiting for a vowel
  let pendingY = false; // a y-glide is coming before that vowel
  const isVowel = (p) => p in HANG_VOW;
  for (let i = 0; i < phonemes.length; i++) {
    const p = phonemes[i];
    if (p === "'") { pendingOnset = null; pendingY = false; continue; } // no Korean glottal mark
    if (p === '-') { pendingOnset = null; pendingY = false; syls.push('-'); continue; }
    if (p === 'y') {
      const next = phonemes[i + 1];
      if (next && isVowel(next)) {
        if (pendingOnset === null) pendingOnset = 11; // bare glide -> ㅇ onset
        pendingY = true;
        continue;
      }
      // Lone y (not before a vowel): flush any pending onset as a ㅡ
      // syllable, then render y itself as 이.
      if (pendingOnset !== null) syls.push({ onset: pendingOnset, vowel: 18, coda: 0 });
      syls.push({ onset: 11, vowel: 20, coda: 0 });
      pendingOnset = null; pendingY = false;
      continue;
    }
    if (isVowel(p)) {
      const v = pendingY ? HANG_YVOW[p] : HANG_VOW[p];
      syls.push({ onset: pendingOnset ?? 11, vowel: v, coda: 0 });
      pendingOnset = null; pendingY = false;
      continue;
    }
    // Consonant phoneme.
    const next = phonemes[i + 1];
    if (next && (isVowel(next) || (next === 'y' && phonemes[i + 2] && isVowel(phonemes[i + 2])))) {
      pendingOnset = HANG_ONSET[p] ?? 11; // pairs with the coming vowel
      pendingY = false;
      continue;
    }
    // Coda position: attach to the last syllable if it has no coda yet,
    // otherwise start a new syllable with the epenthetic vowel ㅡ.
    const last = syls[syls.length - 1];
    if (last && typeof last === 'object' && last.coda === 0) {
      last.coda = HANG_CODA[p] ?? 0;
    } else {
      syls.push({ onset: HANG_ONSET[p] ?? 11, vowel: 18, coda: 0 });
    }
    pendingOnset = null; pendingY = false;
  }
  return syls.map((s) => s === '-' ? '-' : String.fromCodePoint(0xAC00 + (s.onset * 21 + s.vowel) * 28 + s.coda)).join('');
}

// --- Kana (moraic katakana; foreign words) ---
const KANA_ROW = {
  k: ['\u30AB', '\u30AD', '\u30AF', '\u30B1', '\u30B3'], s: ['\u30B5', '\u30B7', '\u30B9', '\u30BB', '\u30BD'],
  t: ['\u30BF', '\u30C1', '\u30C4', '\u30C6', '\u30C8'], n: ['\u30CA', '\u30CB', '\u30CC', '\u30CD', '\u30CE'],
  h: ['\u30CF', '\u30D2', '\u30D5', '\u30D8', '\u30DB'], m: ['\u30DE', '\u30DF', '\u30E0', '\u30E1', '\u30E2'],
  y: ['\u30E4', '\u30A4', '\u30E6', '\u30A4\u30A8', '\u30E8'], r: ['\u30E9', '\u30EA', '\u30EB', '\u30EC', '\u30ED'],
  g: ['\u30AC', '\u30AE', '\u30B0', '\u30B2', '\u30B4'], z: ['\u30B6', '\u30B8', '\u30BA', '\u30BC', '\u30BE'],
  d: ['\u30C0', '\u30C2', '\u30C5', '\u30C7', '\u30C9'], b: ['\u30D0', '\u30D3', '\u30D6', '\u30D9', '\u30DC'],
  p: ['\u30D1', '\u30D4', '\u30D7', '\u30DA', '\u30DD'], v: ['\u30F4\u30A1', '\u30F4\u30A3', '\u30F4', '\u30F4\u30A7', '\u30F4\u30A9'],
  f: ['\u30D5\u30A1', '\u30D5\u30A3', '\u30D5', '\u30D5\u30A7', '\u30D5\u30A9'],
  sh: ['\u30B7\u30E3', '\u30B7', '\u30B7\u30E5', '\u30B7\u30A7', '\u30B7\u30E7'],
  kh: ['\u30CF', '\u30D2', '\u30D5', '\u30D8', '\u30DB'], ch: ['\u30CF', '\u30D2', '\u30D5', '\u30D8', '\u30DB'],
  tz: ['\u30C4\u30A1', '\u30C4\u30A3', '\u30C4', '\u30C4\u30A7', '\u30C4\u30A9'],
  ts: ['\u30C4\u30A1', '\u30C4\u30A3', '\u30C4', '\u30C4\u30A7', '\u30C4\u30A9'],
  l: ['\u30E9', '\u30EA', '\u30EB', '\u30EC', '\u30ED'],
};
const KANA_VOWEL = { a: '\u30A2', i: '\u30A4', u: '\u30A6', e: '\u30A8', o: '\u30AA' };
const KANA_FINAL = { k: '\u30AF', g: '\u30B0', s: '\u30B9', z: '\u30BA', t: '\u30C8', d: '\u30C9', n: '\u30F3', h: '\u30D5', b: '\u30D6', p: '\u30D7', m: '\u30E0', r: '\u30EB', l: '\u30EB', v: '\u30F4', f: '\u30D5', sh: '\u30B7\u30E5', kh: '\u30D5', ch: '\u30D5', tz: '\u30C4', ts: '\u30C4', y: '\u30A4' };
const VOWEL_IDX = { a: 0, i: 1, u: 2, e: 3, o: 4 };
function renderKana(phonemes) {
  let out = '';
  for (let i = 0; i < phonemes.length; i++) {
    const p = phonemes[i];
    if (p === "'") continue;
    if (p === '-') { out += '\u30FB'; continue; }
    if (p in KANA_VOWEL) { out += KANA_VOWEL[p]; continue; }
    const next = phonemes[i + 1];
    if (next && next in VOWEL_IDX && KANA_ROW[p]) { out += KANA_ROW[p][VOWEL_IDX[next]]; i++; continue; }
    if (next === p) { out += '\u30C3'; continue; } // geminate -> っ
    if (p === 'n') { out += '\u30F3'; continue; }
    out += KANA_FINAL[p] ?? p;
  }
  return out;
}

const YHWH_RENDER = {
  cyrillic: '\u042F\u0445\u0432\u0435', arabic: '\u064A\u0647\u0648\u0647',
  devanagari: '\u092F\u0939\u094B\u0935\u093E', hangul: '\uC5EC\uD638\uC640', kana: '\u30E4\u30CF\u30A6\u30A7',
};

function scriptForLang(lang) {
  return { ru: 'cyrillic', ar: 'arabic', hi: 'devanagari', ko: 'hangul', ja: 'kana' }[lang] || 'latin';
}

export function transliterate(latin, hebrew, script) {
  if (!latin) return '';
  if (script === 'latin') return latin;
  if (latin.toUpperCase() === 'YHWH') return YHWH_RENDER[script] || latin;
  const phonemes = scanLatin(latin);
  switch (script) {
    case 'cyrillic': return renderCyrillic(phonemes);
    case 'arabic': return renderArabic(phonemes, glottalKinds(hebrew));
    case 'devanagari': return renderDevanagari(phonemes);
    case 'hangul': return renderHangul(phonemes);
    case 'kana': return renderKana(phonemes);
    default: return latin;
  }
}

// Verses as display tokens: "HEBREW (transliteration, gloss-in-lang)".
// Glosses are the baked-in ones from the cartridge — no fetch, no cost.
// A word with no gloss in the reader's language falls back to the pack's
// fallback language (English); the transliteration is rendered in the
// reader's own alphabet (rules, not data).
export function intercalate(pack, lang) {
  const glossLang = pack.languages.includes(lang) ? lang : pack.fallback;
  const script = scriptForLang(glossLang);
  return pack.verses.map((verse) =>
    verse.map((idx) => {
      const e = pack.lexicon[idx];
      const gloss = e.g[glossLang] || e.g[pack.fallback] || '';
      return `${e.h} (${transliterate(e.t, e.h, script)}, ${gloss})`;
    }));
}
