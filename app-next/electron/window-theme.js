const palettes = Object.freeze({
  dark: { color: "#050505", symbolColor: "#c7a45b" },
  gilded: { color: "#080705", symbolColor: "#d2b577" },
  amethyst: { color: "#171521", symbolColor: "#f5f0ff" },
  ember: { color: "#211916", symbolColor: "#fff4e8" },
  frost: { color: "#121d26", symbolColor: "#f1f8fb" },
});

function windowPalette(theme) {
  const selected = typeof theme === "string" && Object.hasOwn(palettes, theme) ? palettes[theme] : palettes.dark;
  return { ...selected, height: 46 };
}

module.exports = { windowPalette };
