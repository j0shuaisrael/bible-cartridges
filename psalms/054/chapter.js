// Chapter data for THIS page. The viewer (index.html in this folder) is a
// shared template for all 150 Psalms: to make another psalm's page, copy
// this whole folder, replace this file, cartridge.png and
// cover.png — the viewer logic itself stays untouched. Nothing
// Psalm-54-specific lives in index.html; everything chapter-specific lives
// here (page metadata) or inside the cartridge (text, glosses, audio).
export const CHAPTER = {
  number: 54,
  // Shown in the browser tab, the corner label, and as the scroll's heading.
  title: 'Psalm 54',
  // Hebrew heading on the scroll (Tehillim = Psalms, נד = 54).
  hebrewTitle: 'תְּהִלִּים נד',
  // Files in this folder. The cartridge holds the chapter text + glosses +
  // audio; the <audio> element plays the audio bytes decoded from the
  // cartridge — there is no separate audio file.
  cartridge: 'cartridge.png',
};
