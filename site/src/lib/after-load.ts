/** Runs `fn` once the page has loaded and the browser is idle. */
export function afterLoad(fn: () => void) {
  let cancelled = false;
  const run = () => {
    const idle = (window as Window & { requestIdleCallback?: (cb: () => void, o?: { timeout: number }) => number }).requestIdleCallback;
    if (idle) idle(() => { if (!cancelled) fn(); }, { timeout: 1200 });
    else setTimeout(() => { if (!cancelled) fn(); }, 200);
  };
  if (document.readyState === "complete") run();
  else window.addEventListener("load", run, { once: true });
  return () => { cancelled = true; window.removeEventListener("load", run); };
}
