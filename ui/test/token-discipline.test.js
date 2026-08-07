// AI-CONTEXT: design-prd §6 — tokens are the ONLY source of visual truth, and
// tokens.scss says so in its own first lines: "no component may hardcode a hex, px,
// duration, radius, or shadow."
//
// It was not true. `MapCanvas.vue` carried seven colour literals and `BottomSheet.vue`
// an eighth (audit U-01), and nothing could detect them — the contrast suite reads
// tokens.scss, so a colour that never became a token was invisible to the check that
// exists to catch exactly this. §23 entry 45 closed light theme on the argument that
// "contrast is verified from tokens in CI across both themes"; these were the exception
// that argument did not cover, and they were on the map — the surface a driver reads at
// a glance, in glare, at speed.
//
// This test is the detector that was missing. It is deliberately a WHOLE-TREE sweep
// rather than a list of the files that were wrong: a list would have to be remembered,
// and the audit's recurring finding is that a fix lands where it was found and not
// where the pattern lives.
import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join, relative } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const SRC = join(here, "../src");

// tokens.scss is where colour literals BELONG. Nothing else is exempt.
const EXEMPT = new Set(["core/tokens.scss"]);
const SCANNED = /\.(vue|scss|css|js)$/;

// a hex colour, or an rgb()/rgba() whose first argument is a number. `rgba(var(--x), .5)`
// is composition from a token and is not a literal.
const LITERAL = /#[0-9a-fA-F]{3,8}\b|\brgba?\(\s*[0-9]/;

function walk(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) out.push(...walk(full));
    else if (SCANNED.test(name)) out.push(full);
  }
  return out;
}

// Two things look like colours and are not. A comment talks ABOUT a colour — an
// AI-CONTEXT note explaining why a token holds a value is documentation. And a quoted
// string can contain a `#`: "Loves Travel Stop #212" is a truck stop, not a hex. A CSS
// colour is never inside quotes, so both are stripped before judging. Line structure is
// preserved so the reported line numbers stay true.
function blank(match) {
  return match.replace(/[^\n]/g, " ");
}
function stripNonCode(source) {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, blank)
    .replace(/(^|[^:])\/\/.*$/gm, (m, p) => p + blank(m.slice(p.length)))
    .replace(/"(?:[^"\\\n]|\\.)*"/g, blank)
    .replace(/'(?:[^'\\\n]|\\.)*'/g, blank)
    .replace(/`(?:[^`\\]|\\.)*`/g, blank);
}

describe("no component hardcodes a colour (design-prd §6)", () => {
  const files = walk(SRC).filter((f) => !EXEMPT.has(relative(SRC, f).split("\\").join("/")));

  it("finds files to check — a sweep over nothing would pass forever", () => {
    expect(files.length).toBeGreaterThan(20);
  });

  it("ui/src contains no colour literal outside tokens.scss", () => {
    const offenders = [];
    for (const file of files) {
      const rel = relative(SRC, file).split("\\").join("/");
      stripNonCode(readFileSync(file, "utf8"))
        .split("\n")
        .forEach((line, i) => {
          if (LITERAL.test(line)) offenders.push(`${rel}:${i + 1}  ${line.trim()}`);
        });
    }
    expect(offenders, `hardcoded colours:\n${offenders.join("\n")}`).toEqual([]);
  });
});
