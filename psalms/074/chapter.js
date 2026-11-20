// Chapter data for THIS page. The viewer (index.html in this folder) is a
// shared template for all 150 Psalms: to make another psalm's page, copy
// this whole folder, replace this file, cartridge.png and
// cover.png — the viewer logic itself stays untouched. Nothing
// Psalm-74-specific lives in index.html; everything chapter-specific lives
// here (page metadata) or inside the cartridge (text, glosses, audio).
export const CHAPTER = {
  number: 74,
  // Shown in the browser tab, the corner label, and as the scroll's heading.
  title: 'Psalm 74',
  // Hebrew heading on the scroll (Tehillim = Psalms, עד = 74).
  hebrewTitle: 'תְּהִלִּים עד',
  // Files in this folder. The cartridge holds the chapter text + glosses +
  // audio; the <audio> element plays the audio bytes decoded from the
  // cartridge — there is no separate audio file.
  cartridge: 'cartridge.png',
};
