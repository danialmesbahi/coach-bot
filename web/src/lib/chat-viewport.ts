// The conversation stays full-screen; only the composer clears the keyboard.
export function chatViewport(layoutHeight: number, visibleHeight: number, offsetTop: number) {
  // visualViewport remains shrunken briefly after focusout on iOS. Its geometry,
  // rather than focus state, is the source of truth for a smooth return.
  const keyboardInset = Math.max(0, Math.round(layoutHeight - visibleHeight - offsetTop));
  return {
    keyboardInset: keyboardInset > 100 ? keyboardInset : 0,
    keyboard: keyboardInset > 100,
  };
}
