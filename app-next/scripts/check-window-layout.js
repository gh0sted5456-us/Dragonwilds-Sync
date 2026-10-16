const assert = require("assert");
const fs = require("fs");
const path = require("path");
const postcss = require("postcss");
const read = (file) => fs.readFileSync(path.join(__dirname, "..", file), "utf8");
const css = postcss.parse(read("app/globals.css"));
function declaration(selector, property) {
  let result;
  css.walkRules(selector, (rule) => rule.walkDecls(property, (decl) => { result = decl.value; }));
  return result;
}

const overlay = read("components/AppOverlay.jsx");
assert(overlay.includes("createPortal(") && overlay.includes(", document.body)"), "dialogs must escape the workspace's containing block");
assert(overlay.includes('role="dialog"') && overlay.includes('aria-modal="true"'));
assert(overlay.includes('event.key === "Tab"') && overlay.includes('event.key === "Escape"'));
assert(overlay.includes("previousFocus.focus") && overlay.includes("element.inert = inert"), "focus and background interactivity must be restored");
assert(overlay.includes("topLayer() !== node") && overlay.includes("node !== topLayer()"), "only the top nested dialog may handle input");
assert(overlay.includes("downOnBackdrop.current"), "dragging a selection onto the backdrop must not dismiss an editor");
assert.equal(declaration(".app-overlay", "position"), "fixed");
assert.equal(declaration(".app-overlay", "grid-template-rows"), "minmax(0, 1fr)");
assert.equal(declaration(".app-overlay", "inset"), "var(--app-titlebar-height, 0px) 0 0");
assert.equal(declaration("body:has(.desktop-titlebar)", "--app-titlebar-height"), "46px");
assert.equal(declaration(".app-overlay > .panel", "max-height"), "100%");
assert.equal(declaration(".app-overlay .ini-editor-window", "overflow"), "hidden");
assert.equal(declaration(".ini-editor-body", "min-height"), "0");
assert.equal(declaration(".ini-editor-footer", "flex-shrink"), "0");
assert.equal(declaration(".app-overlay .code-editor-window", "display"), "flex", "optional warning must not shift the Monaco/footer grid rows");
assert.equal(declaration(".app-overlay .code-editor-window", "min-height"), "0");
assert.equal(declaration(".code-editor-surface", "flex"), "1");
assert.equal(declaration(".world-context-menu", "position"), "fixed");

for (const file of ["components/IniEditor.jsx", "components/ModCodeEditor.jsx", "components/CustomizeModal.jsx", "components/CreateWorldModal.jsx", "app/worlds/[id]/page.jsx", "app/remote-access/page.jsx", "app/profiles/[id]/player/page.jsx"]) {
  const source = read(file);
  assert(source.includes('from "@/components/AppOverlay"') && source.includes("<AppOverlay"), `${file} must use the shared window layer`);
  assert(!source.includes('position: "fixed"'), `${file} must not reintroduce an inline fixed dialog`);
  assert(!/maxHeight: "\d+vh"/.test(source), `${file} must size within the titlebar-safe layer, not the entire viewport`);
}
const ini = read("components/IniEditor.jsx");
assert(ini.includes('aria-label="DedicatedServer.ini contents"') && ini.includes('className="ini-editor-footer"'));
assert(ini.includes('data-history-open={historyOpen}') && ini.includes("e.stopPropagation(); closeFind()"));
assert(!ini.includes("minHeight: 360"), "history previews must fit short windows");
const mod = read("components/ModCodeEditor.jsx");
assert(mod.includes('label="Unsaved mod changes"') && mod.includes("plain text fallback"));
assert(mod.includes("readOnly: saving || (running && !file.hotload)"));
assert(read("components/PlayerWorldLibrary.jsx").includes("</div>, document.body)"), "the viewport-positioned World menu must also escape the content container");
assert(read("electron/main.js").includes("resizable: true") && read("electron/main.js").includes("thickFrame: true"));
console.log("Window layout: portaled dialogs, native titlebar inset, bounded editors, nested focus/Escape, unsaved guards and responsive history: OK");
