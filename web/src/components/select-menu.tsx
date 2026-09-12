"use client";

import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown } from "lucide-react";

export function SelectMenu({ label, value, options, onChange, compact = false, compactDefault, disabled = false }: { label: string; value: string; options: Array<[string, string]>; onChange: (value: string) => void; compact?: boolean; compactDefault?: string; disabled?: boolean }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const selected = options.find(([key]) => key === value)?.[1] ?? options[0]?.[1];
  const focusOption = (offset: number) => {
    const items = Array.from(list.current?.querySelectorAll<HTMLButtonElement>('[role="option"]') ?? []);
    if (!items.length) return;
    const current = Math.max(0, items.indexOf(document.activeElement as HTMLButtonElement));
    items[(current + offset + items.length) % items.length]?.focus();
  };
  const openAndFocus = () => { setOpen(true); requestAnimationFrame(() => (list.current?.querySelector<HTMLButtonElement>('[aria-selected="true"]') ?? list.current?.querySelector<HTMLButtonElement>('[role="option"]'))?.focus()); };
  useEffect(() => {
    const close = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false); };
    document.addEventListener("pointerdown", close); return () => document.removeEventListener("pointerdown", close);
  }, []);
  return <div className={`select-menu ${compact ? "compact" : ""} ${open ? "open" : ""}`} ref={root}>
    <span className="select-label">{label}</span>
    <button ref={trigger} type="button" className="select-trigger" aria-label={label} disabled={disabled} aria-haspopup="listbox" aria-expanded={open} onClick={() => open ? setOpen(false) : openAndFocus()} onKeyDown={(event) => { if (["ArrowDown", "ArrowUp"].includes(event.key)) { event.preventDefault(); openAndFocus(); } }}>
      <span>{compact && value === options[0]?.[0] ? compactDefault ?? selected : selected}</span><ChevronDown aria-hidden="true" />
    </button>
    {open && <div ref={list} className="select-options" role="listbox" aria-label={label} tabIndex={-1} onKeyDown={(event) => { if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); setOpen(false); trigger.current?.focus(); } else if (event.key === "Tab") { setOpen(false); } else if (event.key === "ArrowDown") { event.preventDefault(); focusOption(1); } else if (event.key === "ArrowUp") { event.preventDefault(); focusOption(-1); } }}>
      {options.map(([key, text]) => <button type="button" role="option" aria-selected={key === value} key={key} onClick={() => { onChange(key); setOpen(false); trigger.current?.focus(); }}>
        <span>{text}</span>{key === value && <Check aria-hidden="true" />}
      </button>)}
    </div>}
  </div>;
}
