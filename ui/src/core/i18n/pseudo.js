// AI-CONTEXT: Pseudo-locale generator (design-prd §12.5). Produces `xx-XL` by
// inflating every EN string ~+40% so layouts are tested for overflow at the
// worst realistic translation length, on the 360dp baseline, in CI. Never
// shipped. Preserves ICU `{placeholders}` untouched so message structure is
// exercised, not mangled.
const PAD_GLYPHS = "åéîõü"; // åéîõü — visibly non-ASCII, width-representative

// AI-CONTEXT: the padding is computed from the VISIBLE text, so a string is inflated
// by 40% of everything except its placeholders — and `pseudo-locale.test.js` measures
// the result against 40% of the WHOLE string. The two disagree by 0.4 × (placeholder
// length), which the ⟦⟧ and the joining space cover only up to about seven characters.
//
// So the test enforces an unwritten rule: PLACEHOLDER NAMES STAY SHORT. Every one in
// the catalogue is ≤5 characters ({n}, {place}, {zone}, {name}, {brand}); an
// eight-character `{facility}` failed the guard on the day it was added. Recorded here
// because the failure names the string, not the reason, and the fix is to rename the
// placeholder rather than to pad harder — a longer name buys no layout coverage, since
// what actually renders there is a facility name, not the token.
export function pseudoInflate(value, factor = 1.4) {
  const parts = value.split(/(\{[^}]+\})/g);
  const visible = parts
    .filter((_, i) => i % 2 === 0)
    .join("");
  const targetExtra = Math.ceil(visible.length * (factor - 1));
  let pad = "";
  for (let i = 0; i < targetExtra; i++) {
    pad += PAD_GLYPHS[i % PAD_GLYPHS.length];
  }
  const rebuilt = parts.join("");
  return `⟦${rebuilt}${pad ? " " + pad : ""}⟧`;
}

export function buildPseudoCatalog(enMessages, factor = 1.4) {
  const out = {};
  for (const [key, value] of Object.entries(enMessages)) {
    out[key] = pseudoInflate(value, factor);
  }
  return out;
}
