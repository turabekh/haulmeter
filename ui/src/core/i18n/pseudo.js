// AI-CONTEXT: Pseudo-locale generator (design-prd §12.5). Produces `xx-XL` by
// inflating every EN string ~+40% so layouts are tested for overflow at the
// worst realistic translation length, on the 360dp baseline, in CI. Never
// shipped. Preserves ICU `{placeholders}` untouched so message structure is
// exercised, not mangled.
const PAD_GLYPHS = "åéîõü"; // åéîõü — visibly non-ASCII, width-representative

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
