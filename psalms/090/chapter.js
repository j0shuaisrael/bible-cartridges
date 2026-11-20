// Chapter data for THIS page. The viewer (index.html in this folder) is a
// shared template for all 150 Psalms: to make another psalm's page, copy
// this whole folder, replace this file, cartridge.png, audio.webm and
// cover.png — the viewer logic itself stays untouched. Nothing
// Psalm-90-specific lives in index.html; everything chapter-specific lives
// here (page metadata) or inside the cartridge (text, glosses, audio).
export const CHAPTER = {
  number: 90,
  // Shown in the browser tab, the corner label, and as the scroll's heading.
  title: 'Psalm 90',
  // Hebrew heading on the scroll (Tehillim = Psalms, צ = 90).
  hebrewTitle: 'תְּהִלִּים צ',
  // Files in this folder. The cartridge holds the chapter text + glosses +
  // audio; the audio file is the same Opus WebM packed into the cartridge,
  // kept as a file so the <audio> element can play it.
  cartridge: 'cartridge.png',
  audio: 'audio.webm',
};
