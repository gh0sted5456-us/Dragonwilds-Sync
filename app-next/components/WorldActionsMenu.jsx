"use client";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Icon } from "@/components/ui";

export default function WorldActionsMenu({ menu, onClose, items, label = "World actions" }) {
  const ref = useRef(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  const [position, setPosition] = useState({ left: 8, top: 54 });
  useLayoutEffect(() => {
    if (!menu || !ref.current) return;
    const node = ref.current;
    const previousFocus = document.activeElement;
    const box = node.getBoundingClientRect();
    const titlebar = parseFloat(getComputedStyle(document.body).getPropertyValue("--app-titlebar-height")) || 0;
    setPosition({ left: Math.max(8, Math.min(menu.x, window.innerWidth - box.width - 8)), top: Math.max(titlebar + 8, Math.min(menu.y, window.innerHeight - box.height - 8)) });
    node.querySelector('button:not(:disabled)')?.focus({ preventScroll: true });
    return () => {
      if (previousFocus?.isConnected && (node.contains(document.activeElement) || document.activeElement === document.body)) previousFocus.focus({ preventScroll: true });
    };
  }, [menu]);
  useEffect(() => {
    if (!menu) return;
    const node = ref.current;
    const outside = (event) => { if (!node?.contains(event.target)) closeRef.current(); };
    const close = () => closeRef.current();
    const keys = (event) => {
      if (["Escape", "Tab"].includes(event.key)) { if (event.key === "Escape") event.preventDefault(); close(); return; }
      if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const buttons = [...node.querySelectorAll('button:not(:disabled)')];
      if (!buttons.length) return;
      const current = buttons.indexOf(document.activeElement);
      const index = event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1 : (current + (event.key === "ArrowDown" ? 1 : -1) + buttons.length) % buttons.length;
      buttons[index].focus();
    };
    window.addEventListener("pointerdown", outside, true);
    window.addEventListener("scroll", outside, true);
    window.addEventListener("blur", close);
    window.addEventListener("resize", close);
    window.addEventListener("keydown", keys);
    return () => {
      window.removeEventListener("pointerdown", outside, true);
      window.removeEventListener("scroll", outside, true);
      window.removeEventListener("blur", close);
      window.removeEventListener("resize", close);
      window.removeEventListener("keydown", keys);
    };
  }, [menu]);
  if (!menu) return null;
  return createPortal(<div ref={ref} className="panel world-context-menu" role="menu" aria-label={label} style={position}>
    {items.map((item) => <button key={item.label} className="btn btn-ghost" role="menuitem" disabled={item.disabled} title={item.title} style={{ width: "100%", justifyContent: "flex-start" }} onClick={() => { onClose(); item.onClick(); }}><Icon name={item.icon || "download"} size={16} /> {item.label}</button>)}
  </div>, document.body);
}
