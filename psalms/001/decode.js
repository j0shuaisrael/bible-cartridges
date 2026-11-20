// decode.js — in-browser decoder for PSLM v2 Bible cartridges.
//
// Reads the cartridge PNG through a canvas (pixel values are exact), pulls
// the text pack out of the visible strip, verifies its SHA-256, pulls the
// audio out of the LSB layer below the strip, verifies that too, and hands
// back the exact original bytes — or throws, never returning damaged data.
//
// Translations are BAKED INTO the cartridge at build time (one gloss per
// packed language per unique word). Nothing is fetched at decode time and
// nothing costs anything: pickLanguage() just matches navigator.language
// against the header's packed-language list, falling back to English.

const MAGIC = [0x50, 0x53, 0x4c, 0x4d]; // "PSLM"
const VERSION = 2;

function hexSha256(bytes) {
  // SHA-256 via the browser's built-in crypto (async).
  return crypto.subtle.digest('SHA-256', bytes).then((buf) =>
    [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join(''));
}

// Minimal inflate for zlib streams: browsers have DecompressionStream('deflate').
async function inflateZlib(bytes) {
  const ds = new DecompressionStream('deflate');
  const out = await new Response(new Blob([bytes]).stream().pipeThrough(ds)).arrayBuffer();
  return new Uint8Array(out);
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

function lsbAudio(data, w, h, stripH, n) {
  const out = new Uint8Array(n);
  let bit = 0;
  const total = n * 8;
  for (let y = stripH; y < h; y++) {
    for (let x = 0; x < w; x++) {
      if (bit >= total) return out;
      const i = (y * w + x) * 4;
      for (let c = 0; c < 3; c++) {
        if (bit >= total) return out;
        if (data[i + c] & 1) out[Math.floor(bit / 8)] |= 1 << (7 - (bit % 8));
        bit++;
      }
    }
  }
  if (bit < total) throw new Error('cartridge truncated: LSB layer ended before the audio did');
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
  if (head[4] !== VERSION) {
    throw new Error(`unsupported PSLM version ${head[4]} (this decoder reads v${VERSION})`);
  }
  const hlen = new DataView(head.buffer, head.byteOffset + 5, 4).getUint32(0, false);
  const headerRaw = stripBytes(data, w, 9 + hlen).subarray(9);
  const header = JSON.parse(new TextDecoder().decode(headerRaw));

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

  let audio = null;
  if (header.audio_len) {
    audio = lsbAudio(data, w, h, stripH, header.audio_len);
    if ((await hexSha256(audio)) !== header.audio_sha256) {
      throw new Error('audio SHA-256 mismatch — audio damaged');
    }
  }
  return { header, pack, audio };
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

// Verses as display tokens: "HEBREW (transliteration, gloss-in-lang)".
// Glosses are the baked-in ones from the cartridge — no fetch, no cost.
export function intercalate(pack, lang) {
  const glossLang = pack.languages.includes(lang) ? lang : pack.fallback;
  return pack.verses.map((verse) =>
    verse.map((idx) => {
      const e = pack.lexicon[idx];
      return `${e.h} (${e.t}, ${e.g[glossLang]})`;
    }));
}
