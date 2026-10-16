"use client";

import Link from "next/link";
import { Icon } from "@/components/ui";

export function PageHeader({ eyebrow, title, description, icon, image, actions, backHref, backLabel, children }) {
  return <>
    {backHref && <Link href={backHref} className="page-back"><Icon name="back" size={16} /> {backLabel || "Back"}</Link>}
    <header className="page-header">
      <div className="page-header-main">
        {image ? <img className="page-header-image" src={image} alt="" /> : icon ? <span className="page-header-icon"><Icon name={icon} size={23} /></span> : null}
        <div className="page-header-copy">
          {eyebrow && <div className="eyebrow">{eyebrow}</div>}
          <h1 className="heading">{title}</h1>
          {description && <p className="subtle">{description}</p>}
          {children}
        </div>
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </header>
  </>;
}

export function SegmentedMenu({ items, value, onChange, ariaLabel = "Page section" }) {
  const selectedIndex = Math.max(0, items.findIndex((item) => item.id === value));
  const move = (event, index) => {
    const steps = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };
    let next;
    if (event.key === "Home") next = 0;
    else if (event.key === "End") next = items.length - 1;
    else if (event.key in steps) next = (index + steps[event.key] + items.length) % items.length;
    else return;
    if (!items[next]) return;
    event.preventDefault();
    const buttons = event.currentTarget.parentElement.querySelectorAll('[role="tab"]');
    onChange(items[next].id);
    buttons[next]?.focus();
  };
  return <nav className="segmented-menu" role="tablist" aria-label={ariaLabel} style={{ "--segment-count": Math.max(1, items.length) }}>
    {items.map((item, index) => <button key={item.id} type="button" role="tab" tabIndex={index === selectedIndex ? 0 : -1} aria-selected={value === item.id} className={value === item.id ? "active" : ""} onKeyDown={(event) => move(event, index)} onClick={() => onChange(item.id)}>
      {item.icon && <Icon name={item.icon} size={17} />}
      <span><strong>{item.label}</strong>{item.detail && <small>{item.detail}</small>}</span>
    </button>)}
  </nav>;
}
