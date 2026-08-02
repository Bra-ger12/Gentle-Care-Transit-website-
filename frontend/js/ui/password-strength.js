const LEVELS = ["weak", "fair", "strong"];

function scorePassword(value) {
  if (!value) return 0;
  let score = 0;
  if (value.length >= 8) score += 1;
  if (/\d/.test(value)) score += 1;
  if (/[a-z]/.test(value) && /[A-Z]/.test(value)) score += 1;
  if (/[^A-Za-z0-9]/.test(value)) score += 1;
  return Math.min(score, 3);
}

export function initPasswordStrength(input, wrapEl, labelEl) {
  const segments = [...wrapEl.querySelectorAll(".password-strength__segment")];
  input.addEventListener("input", () => {
    const value = input.value;
    wrapEl.hidden = value.length === 0;
    const score = scorePassword(value);
    const level = LEVELS[Math.max(score - 1, 0)];
    segments.forEach((seg, i) => seg.classList.toggle("is-filled", i < score));
    wrapEl.className = `password-strength password-strength--${level}`;
    labelEl.textContent = value.length === 0 ? "" : level[0].toUpperCase() + level.slice(1);
  });
}
