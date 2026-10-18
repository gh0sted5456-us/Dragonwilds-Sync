const DEFAULT_APPEARANCE = Object.freeze({ version: 1, background: "woodland.webp", backgroundOpacity: 0.32, surfaceOpacity: 0.88, fit: "cover" });
function validBackgroundName(value) {
  return typeof value === "string" && value.length <= 160 && value !== "none" && !value.startsWith(".") && !/[\\/:\x00-\x1f]/.test(value) && /\.(?:png|jpe?g|webp)$/i.test(value);
}
function normalizeAppearance(input = {}, previous = DEFAULT_APPEARANCE) {
  if (!input || typeof input !== "object" || Array.isArray(input)) input = {};
  const number = (name, min, max) => typeof input[name] === "number" && Number.isFinite(input[name]) ? Math.min(max, Math.max(min, input[name])) : previous[name];
  return { version: 1,
    background: input.background === "none" || validBackgroundName(input.background) ? input.background : previous.background,
    backgroundOpacity: number("backgroundOpacity", 0, 0.6), surfaceOpacity: number("surfaceOpacity", 0.72, 1),
    fit: ["cover", "contain"].includes(input.fit) ? input.fit : previous.fit };
}
module.exports = { DEFAULT_APPEARANCE, normalizeAppearance, validBackgroundName };
