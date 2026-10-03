/** Horizontally centres the selected item inside a scrollable row without ever scrolling the page. */
export function centerInRow(row: HTMLElement | null, selector: string) {
  const item = row?.querySelector<HTMLElement>(selector);
  if (!row || !item || row.scrollWidth <= row.clientWidth) return;
  const r = row.getBoundingClientRect();
  const i = item.getBoundingClientRect();
  row.scrollBy({ left: i.left + i.width / 2 - (r.left + r.width / 2), behavior: "smooth" });
}
