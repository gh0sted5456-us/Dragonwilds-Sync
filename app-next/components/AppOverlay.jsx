"use client";

import { createContext, useContext, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

const OverlayDepth = createContext(0);
const layers = [];
let background = [];
let sequence = 0;
const topLayer = () => layers[layers.length - 1]?.node;
const focusable = (node) => [...node.querySelectorAll('button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])')]
  .filter((element) => element.tabIndex >= 0 && element.getClientRects().length && !element.closest("[inert]"));

function reconcileLayers() {
  layers.sort((a, b) => a.depth - b.depth || a.order - b.order);
  for (const { node } of layers) {
    node.inert = node !== topLayer();
    if (node.inert) node.setAttribute("aria-hidden", "true");
    else node.removeAttribute("aria-hidden");
  }
}

// Portals escape app-content's container-query containing block and stacking
// context. Every editor/dialog uses the same viewport and native-titlebar inset.
export default function AppOverlay({ children, label = "Dialog", labelledBy, onClose, onEscape, className = "", dismissible = true }) {
  const depth = useContext(OverlayDepth) + 1;
  const [mounted, setMounted] = useState(false);
  const root = useRef(null);
  const downOnBackdrop = useRef(false);
  const handlers = useRef(null);
  handlers.current = { onClose, onEscape, dismissible };

  useEffect(() => { setMounted(true); }, []);
  useEffect(() => {
    if (!mounted || !root.current) return undefined;
    const node = root.current;
    const previousFocus = document.activeElement;
    if (!layers.length) {
      const frame = document.querySelector(".app-frame");
      const nodes = frame ? [frame, document.querySelector(".skip-link")] : [...document.body.children].filter((child) => !child.matches(".app-overlay, script, style, nextjs-portal"));
      background = nodes.filter(Boolean).map((element) => ({ element, inert: element.inert }));
      background.forEach(({ element }) => { element.inert = true; });
    }
    const layer = { node, depth, order: ++sequence };
    layers.push(layer);
    reconcileLayers();
    if (topLayer() === node) node.focus({ preventScroll: true });

    const keydown = (event) => {
      if (topLayer() !== node || event.defaultPrevented) return;
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        const current = handlers.current;
        if (current.dismissible) (current.onEscape || current.onClose)?.();
      } else if (event.key === "Tab") {
        const items = focusable(node);
        const first = items[0], last = items[items.length - 1];
        if (!first) { event.preventDefault(); node.focus({ preventScroll: true }); }
        else if (event.shiftKey && (document.activeElement === first || document.activeElement === node)) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && (document.activeElement === last || document.activeElement === node)) { event.preventDefault(); first.focus(); }
      }
    };
    const keepFocus = (event) => {
      if (topLayer() === node && !node.contains(event.target)) node.focus({ preventScroll: true });
    };
    window.addEventListener("keydown", keydown);
    document.addEventListener("focusin", keepFocus);
    return () => {
      window.removeEventListener("keydown", keydown);
      document.removeEventListener("focusin", keepFocus);
      const wasTop = topLayer() === node;
      layers.splice(layers.indexOf(layer), 1);
      reconcileLayers();
      if (!layers.length) {
        background.forEach(({ element, inert }) => { element.inert = inert; });
        background = [];
      }
      if (wasTop) queueMicrotask(() => {
        if (previousFocus?.isConnected && !previousFocus.closest("[inert]") && (!topLayer() || topLayer().contains(previousFocus))) previousFocus.focus({ preventScroll: true });
        else topLayer()?.focus({ preventScroll: true });
      });
    };
  }, [mounted, depth]);

  if (!mounted) return null;
  return createPortal(<OverlayDepth.Provider value={depth}>
    <div ref={root} className={`app-overlay ${className}`} style={{ zIndex: 1000 + depth * 10 }} role="dialog" aria-modal="true" aria-label={labelledBy ? undefined : label} aria-labelledby={labelledBy} tabIndex={-1}
      onMouseDown={(event) => { downOnBackdrop.current = event.target === event.currentTarget; }}
      onClick={(event) => {
        if (event.target === event.currentTarget && downOnBackdrop.current && topLayer() === root.current && dismissible) onClose?.();
        downOnBackdrop.current = false;
      }}>
      {children}
    </div>
  </OverlayDepth.Provider>, document.body);
}
