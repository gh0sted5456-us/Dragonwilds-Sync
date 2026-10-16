const palettes = Object.freeze({
  dark: { color: "#11151d", symbolColor: "#f1f3fb" },
  gilded: { color: "#11151d", symbolColor: "#f1f3fb" },
  amethyst: { color: "#171521", symbolColor: "#f5f0ff" },
  ember: { color: "#211916", symbolColor: "#fff4e8" },
  frost: { color: "#121d26", symbolColor: "#f1f8fb" },
});

function windowPalette(theme) {
  const selected = typeof theme === "string" && Object.hasOwn(palettes, theme) ? palettes[theme] : palettes.dark;
  return { ...selected, height: 46 };
}

module.exports = { windowPalette };
