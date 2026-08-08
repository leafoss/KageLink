"use strict";

// Preserve the v0.2.3/v0.2.4 mobile behavior: Android/iOS IME composition
// is mirrored while the user is typing instead of appearing only at commit.
// The transport remains text-only; no typed content is logged by the Host.
let liveCompositionMirror = "";

function liveImeTap(key) {
  if (!canControl()) return;
  send({ type: "key", key, down: true });
  send({ type: "key", key, down: false });
}

function reconcileLiveComposition(nextValue) {
  if (!canControl()) return;
  const previous = Array.from(liveCompositionMirror);
  const next = Array.from(String(nextValue || ""));
  let common = 0;
  while (common < previous.length && common < next.length && previous[common] === next[common]) common += 1;
  for (let index = previous.length; index > common; index -= 1) liveImeTap("backspace");
  const suffix = next.slice(common).join("");
  if (suffix) send({ type: "text", text: suffix });
  liveCompositionMirror = next.join("");
}

els.ime.addEventListener("compositionstart", () => {
  liveCompositionMirror = "";
}, true);

els.ime.addEventListener("compositionupdate", (event) => {
  reconcileLiveComposition(event.data || "");
}, true);

els.ime.addEventListener("compositionend", (event) => {
  // Capture phase prevents the older commit-only listener in client.js from
  // sending the final text a second time.
  event.stopImmediatePropagation();
  reconcileLiveComposition(event.data || "");
  composing = false;
  liveCompositionMirror = "";
  els.ime.value = "";
}, true);
