import { el } from "./dom.js";

/**
 * Canvas signature capture for the drop-off record.
 *
 * Built on pointer events rather than separate mouse/touch handlers: the same
 * code then serves a driver signing with a finger on a phone, a stylus on a
 * tablet, and a mouse on the dispatch desktop, which is exactly the spread of
 * devices this gets used on.
 *
 * The canvas is sized to its own displayed box at device pixel ratio, so a line
 * drawn on a high-DPI phone isn't a blurry approximation of where the finger was.
 */

const STROKE_COLOUR = "#0E1B26";
const STROKE_WIDTH = 2.2;

export function signaturePad({ label = "Signature", hint } = {}) {
  const canvas = el("canvas", { class: "sigpad__canvas", "aria-label": label });
  const clearBtn = el("button", { type: "button", class: "btn btn--ghost btn--small", text: "Clear" });
  const status = el("p", { class: "sigpad__status", text: "Not signed yet.", "aria-live": "polite" });

  let context = null;
  let drawing = false;
  let hasInk = false;

  /** Match the backing store to the box the browser actually painted. */
  function resize() {
    const ratio = window.devicePixelRatio || 1;
    const box = canvas.getBoundingClientRect();
    if (!box.width) return;

    // Re-sizing clears the canvas, so keep what's drawn and put it back.
    const previous = hasInk ? canvas.toDataURL("image/png") : null;

    canvas.width = Math.round(box.width * ratio);
    canvas.height = Math.round(box.height * ratio);
    context = canvas.getContext("2d");
    context.scale(ratio, ratio);
    context.lineWidth = STROKE_WIDTH;
    context.lineCap = "round";
    context.lineJoin = "round";
    context.strokeStyle = STROKE_COLOUR;

    if (previous) {
      const image = new Image();
      image.onload = () => context.drawImage(image, 0, 0, box.width, box.height);
      image.src = previous;
    }
  }

  function positionOf(event) {
    const box = canvas.getBoundingClientRect();
    return { x: event.clientX - box.left, y: event.clientY - box.top };
  }

  function start(event) {
    if (!context) resize();
    drawing = true;
    canvas.setPointerCapture(event.pointerId);
    const { x, y } = positionOf(event);
    context.beginPath();
    context.moveTo(x, y);
    // A tap with no drag is still a mark; draw a dot so it registers.
    context.lineTo(x + 0.01, y);
    context.stroke();
    markSigned();
    event.preventDefault();
  }

  function move(event) {
    if (!drawing) return;
    const { x, y } = positionOf(event);
    context.lineTo(x, y);
    context.stroke();
    event.preventDefault();
  }

  function end(event) {
    if (!drawing) return;
    drawing = false;
    if (canvas.hasPointerCapture(event.pointerId)) {
      canvas.releasePointerCapture(event.pointerId);
    }
  }

  function markSigned() {
    if (hasInk) return;
    hasInk = true;
    status.textContent = "Signed.";
    wrapper.classList.add("sigpad--signed");
  }

  function clear() {
    if (context) context.clearRect(0, 0, canvas.width, canvas.height);
    hasInk = false;
    status.textContent = "Not signed yet.";
    wrapper.classList.remove("sigpad--signed");
  }

  canvas.addEventListener("pointerdown", start);
  canvas.addEventListener("pointermove", move);
  canvas.addEventListener("pointerup", end);
  canvas.addEventListener("pointercancel", end);
  canvas.addEventListener("pointerleave", end);
  clearBtn.addEventListener("click", clear);
  window.addEventListener("resize", resize);

  const wrapper = el("div", { class: "sigpad" }, [
    el("div", { class: "sigpad__head" }, [
      el("span", { class: "sigpad__label", text: label }),
      clearBtn,
    ]),
    canvas,
    el("div", { class: "sigpad__foot" }, [
      status,
      hint ? el("p", { class: "sigpad__hint", text: hint }) : null,
    ]),
  ]);

  // The canvas has no size until it's in the document; size it on the next frame.
  requestAnimationFrame(resize);

  return {
    element: wrapper,
    isSigned: () => hasInk,
    /** PNG data URL the completion endpoint accepts, or null if unsigned. */
    toDataURL: () => (hasInk ? canvas.toDataURL("image/png") : null),
    clear,
  };
}
