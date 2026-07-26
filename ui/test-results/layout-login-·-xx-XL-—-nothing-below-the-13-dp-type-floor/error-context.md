# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: layout.spec.js >> login · xx-XL — nothing below the 13 dp type floor
- Location: layout/layout.spec.js:167:7

# Error details

```
Error: §6.2 says nothing smaller than 13 dp exists: div.canvas__gl mapboxgl-map @12px | div.mapboxgl-ctrl-bottom-right @12px | div.mapboxgl-ctrl mapboxgl-ctrl-attrib mapboxgl-compact @12px

expect(received).toEqual(expected) // deep equality

- Expected  - 1
+ Received  + 5

- Array []
+ Array [
+   "div.canvas__gl mapboxgl-map @12px",
+   "div.mapboxgl-ctrl-bottom-right @12px",
+   "div.mapboxgl-ctrl mapboxgl-ctrl-attrib mapboxgl-compact @12px",
+ ]
```

# Page snapshot

```yaml
- generic [ref=e3]:
  - banner [ref=e4]:
    - generic [ref=e5]: idle
    - button "Voice" [disabled] [ref=e6] [cursor=pointer]
  - main [ref=e10]:
    - generic [ref=e11]:
      - tablist "Map presets" [ref=e12]:
        - tab "Drive" [selected] [ref=e13] [cursor=pointer]
        - tab "Tonight" [ref=e14] [cursor=pointer]
        - tab "Work" [ref=e15] [cursor=pointer]
        - tab "Fuel" [ref=e16] [cursor=pointer]
        - tab "Food" [ref=e17] [cursor=pointer]
      - button "2 opening nearby" [ref=e18] [cursor=pointer]
      - generic [ref=e19]:
        - application "Map" [ref=e20]:
          - generic [ref=e21]:
            - region "Map" [ref=e22]
            - generic:
              - generic:
                - button "Find my location" [ref=e24] [cursor=pointer]
                - button "Toggle attribution" [ref=e27] [cursor=pointer]
              - link "Mapbox homepage" [ref=e30] [cursor=pointer]:
                - /url: https://www.mapbox.com/
          - generic [ref=e31]: Map · tiles pending
          - 'button "Loves Travel Stop #212" [ref=e32] [cursor=pointer]'
          - 'button "Pilot #77" [ref=e39] [cursor=pointer]'
          - button "Rest Area — I-35 NB" [ref=e46] [cursor=pointer]
          - button "TA Travel Center" [ref=e50] [cursor=pointer]
          - generic: © OpenStreetMap contributors (ODbL)
        - button "Report status" [ref=e55] [cursor=pointer]
      - button "Voice" [ref=e59] [cursor=pointer]
  - navigation "Primary" [ref=e63]:
    - link "Map" [ref=e64] [cursor=pointer]:
      - /url: /map
    - link "Load" [ref=e68] [cursor=pointer]:
      - /url: /load
    - link "Money" [ref=e75] [cursor=pointer]:
      - /url: /money
    - link "Docs" [ref=e79] [cursor=pointer]:
      - /url: /docs
    - link "More" [ref=e84] [cursor=pointer]:
      - /url: /more
```

# Test source

```ts
  88  |           }),
  89  |         );
  90  |       } catch {
  91  |         /* storage unavailable */
  92  |       }
  93  |     },
  94  |     [theme, pseudo],
  95  |   );
  96  | }
  97  | 
  98  | async function settle(page) {
  99  |   await page.waitForLoadState("networkidle").catch(() => {});
  100 |   // the map canvas initialises asynchronously and has no layout contribution here
  101 |   await page.waitForTimeout(250);
  102 | }
  103 | 
  104 | // AI-CONTEXT: the theme dimension was REMOVED on evidence, not on a hunch.
  105 | //
  106 | // It was also broken: `theme.js` keeps the mode in a ref and never persists it, so
  107 | // the `longhaul.theme` key this harness had been setting for two sessions was read
  108 | // by nothing, and only one of four assertions ever stamped `data-theme` itself. The
  109 | // dimension had been running the same theme twice.
  110 | //
  111 | // Then, measured properly across all six surfaces under a correctly applied dark and
  112 | // light: geometry was IDENTICAL on five, and the single difference was a font size
  113 | // inside Mapbox's own attribution furniture, which is exempt anyway. That matches
  114 | // §23's light-theme entry exactly — "Only the 12 color tokens change;
  115 | // type/space/radius/motion/touch are theme-invariant" — so none of these assertions
  116 | // CAN vary by theme, by constitutional decision rather than by luck. Contrast, the
  117 | // genuinely theme-sensitive property, is computed from tokens in contrast.test.js.
  118 | //
  119 | // The budget went to surfaces instead, which is the dimension that finds bugs.
  120 | for (const [name, path] of SURFACES) {
  121 |   {
  122 |     const theme = "dark";
  123 |     // `pa` joins the matrix because §6.2's "metrics-compatible line-height tokens
  124 |     // verified" is a LAYOUT claim, and this harness is the only thing that can
  125 |     // answer it. Gurmukhi carries matras above AND below the baseline, so a line
  126 |     // height tuned for Latin is exactly the kind of thing that clips silently — and
  127 |     // "verified" was asserted in the constitution without anyone rendering it.
  128 |     for (const pseudo of [false, "xx-XL", "pa"]) {
  129 |       const label = `${name}${pseudo ? ` · ${pseudo}` : ""}`;
  130 | 
  131 |       test(`${label} — no horizontal overflow at 360 dp`, async ({ page }) => {
  132 |         await prepare(page, { theme, pseudo });
  133 |         await page.setViewportSize({ width: 360, height: 800 });
  134 |         await page.goto(`${BASE}${path}`);
  135 |         await settle(page);
  136 |         await page.evaluate((t) => document.documentElement.setAttribute("data-theme", t), theme);
  137 | 
  138 |         const overflow = await page.evaluate(() => {
  139 |           const doc = document.documentElement;
  140 |           const offenders = [];
  141 |           for (const el of document.querySelectorAll("body *")) {
  142 |             const r = el.getBoundingClientRect();
  143 |             if (r.width === 0 || r.height === 0) continue;
  144 |             // 1 px of tolerance: sub-pixel rounding is not a layout defect
  145 |             if (r.right > doc.clientWidth + 1 || r.left < -1) {
  146 |               const style = getComputedStyle(el);
  147 |               // an element that scrolls its own overflow is doing so ON PURPOSE
  148 |               // (the preset chip row, the portal rail) — that is a pattern the
  149 |               // constitution approves, not a break
  150 |               const scrolls = ["auto", "scroll"].includes(style.overflowX);
  151 |               const parentScrolls = el.parentElement
  152 |                 ? ["auto", "scroll"].includes(getComputedStyle(el.parentElement).overflowX)
  153 |                 : false;
  154 |               if (!scrolls && !parentScrolls) {
  155 |                 offenders.push(`${el.tagName.toLowerCase()}.${el.className} @${Math.round(r.right)}`);
  156 |               }
  157 |             }
  158 |           }
  159 |           return { docScroll: doc.scrollWidth, clientWidth: doc.clientWidth, offenders };
  160 |         });
  161 | 
  162 |         expect(overflow.offenders, `elements past 360 dp: ${overflow.offenders.join(" | ")}`)
  163 |           .toEqual([]);
  164 |         expect(overflow.docScroll).toBeLessThanOrEqual(overflow.clientWidth + 1);
  165 |       });
  166 | 
  167 |       test(`${label} — nothing below the 13 dp type floor`, async ({ page }) => {
  168 |         await prepare(page, { theme, pseudo });
  169 |         await page.setViewportSize({ width: 360, height: 800 });
  170 |         await page.goto(`${BASE}${path}`);
  171 |         await settle(page);
  172 | 
  173 |         const small = await page.evaluate((floor) => {
  174 |           const found = [];
  175 |           for (const el of document.querySelectorAll("body *")) {
  176 |             if (!el.textContent || !el.textContent.trim()) continue;
  177 |             const r = el.getBoundingClientRect();
  178 |             if (r.width === 0 || r.height === 0) continue;
  179 |             const size = parseFloat(getComputedStyle(el).fontSize);
  180 |             if (size && size < floor) {
  181 |               found.push(`${el.tagName.toLowerCase()}.${el.className} @${size}px`);
  182 |             }
  183 |           }
  184 |           return found;
  185 |         }, CAPTION_FLOOR_PX);
  186 | 
  187 |         expect(small, `§6.2 says nothing smaller than 13 dp exists: ${small.join(" | ")}`)
> 188 |           .toEqual([]);
      |            ^ Error: §6.2 says nothing smaller than 13 dp exists: div.canvas__gl mapboxgl-map @12px | div.mapboxgl-ctrl-bottom-right @12px | div.mapboxgl-ctrl mapboxgl-ctrl-attrib mapboxgl-compact @12px
  189 |       });
  190 | 
  191 |       test(`${label} — text is not clipped by its line box`, async ({ page }) => {
  192 |         await prepare(page, { theme, pseudo });
  193 |         await page.setViewportSize({ width: 360, height: 800 });
  194 |         await page.goto(`${BASE}${path}`);
  195 |         await settle(page);
  196 |         await page.evaluate(() => document.fonts && document.fonts.ready);
  197 | 
  198 |         const clipped = await page.evaluate(() => {
  199 |           const found = [];
  200 |           for (const el of document.querySelectorAll("body *")) {
  201 |             if (!el.childElementCount && el.textContent && el.textContent.trim()) {
  202 |               const style = getComputedStyle(el);
  203 |               if (style.overflow === "visible") continue; // nothing to clip against
  204 |               if (el.scrollHeight > el.clientHeight + 1) {
  205 |                 found.push(`${el.tagName.toLowerCase()}.${el.className} ${el.scrollHeight}>${el.clientHeight}`);
  206 |               }
  207 |             }
  208 |           }
  209 |           return found;
  210 |         });
  211 | 
  212 |         expect(clipped, `clipped text: ${clipped.join(" | ")}`).toEqual([]);
  213 |       });
  214 | 
  215 |       // AI-CONTEXT: the fifth assertion, and the one with the best odds of paying for
  216 |       // its runtime. A <button> with no handler is the FIFTH instance of one bug
  217 |       // class in this project: the "suggest a cook" control with no destination,
  218 |       // `categories` collected and never read, `portions` carried through three API
  219 |       // layers to nowhere, `followers_notified` returned and rendered nowhere, and
  220 |       // the Docs capture chip. The near side of a seam gets built, the far side does
  221 |       // not, and nothing in §22.3 catches it because every one of those passes review
  222 |       // — the code looks finished from whichever side you are reading.
  223 |       //
  224 |       // A control that reports nothing when pressed is worse than an absent one: it
  225 |       // spends the driver's trust. §23 already settled the principle for the module
  226 |       // registry — a capability whose destination does not exist is LABELLED, never
  227 |       // linked — and this is that rule, enforced.
  228 |       //
  229 |       // `disabled` is an acceptable answer. Saying "not yet" is honest; saying
  230 |       // nothing is not.
  231 |       test(`${label} — every control does something, or says it cannot`, async ({ page }) => {
  232 |         await prepare(page, { theme, pseudo });
  233 |         await page.setViewportSize({ width: 360, height: 800 });
  234 |         await page.goto(`${BASE}${path}`);
  235 |         await settle(page);
  236 | 
  237 |         const inert = await page.evaluate(() => {
  238 |           const found = [];
  239 |           for (const el of document.querySelectorAll("button")) {
  240 |             const r = el.getBoundingClientRect();
  241 |             if (!r.width || !r.height) continue;
  242 |             if (el.disabled || el.getAttribute("aria-disabled") === "true") continue;
  243 |             // a <button type=submit> inside a form acts through the form
  244 |             if (el.type === "submit" && el.closest("form")) continue;
  245 |             // Vue compiles @click to a listener; getEventListeners is devtools-only,
  246 |             // so the reliable signal is the framework's own bookkeeping on the node
  247 |             const vue = el.__vnode || el.__vueParentComponent;
  248 |             const props = vue && vue.props;
  249 |             const hasVueHandler = !!(
  250 |               props &&
  251 |               Object.keys(props).some((k) => /^on[A-Z]/.test(k) && typeof props[k] === "function")
  252 |             );
  253 |             const hasDomHandler = typeof el.onclick === "function";
  254 |             // Mapbox attaches its own listeners imperatively, so neither Vue's
  255 |             // bookkeeping nor `onclick` can see them. Same exemption the glove-spec
  256 |             // check already carries, and for the same reason: not our furniture.
  257 |             if (el.closest(".mapboxgl-ctrl") || /mapboxgl/.test(el.className)) continue;
  258 |             if (!hasVueHandler && !hasDomHandler && !el.closest("a[href]")) {
  259 |               found.push(`${el.className || el.tagName.toLowerCase()}: "${(el.textContent || "").trim().slice(0, 32)}"`);
  260 |             }
  261 |           }
  262 |           return found;
  263 |         });
  264 | 
  265 |         expect(inert, `controls that do nothing when pressed: ${inert.join(" | ")}`).toEqual([]);
  266 |       });
  267 | 
  268 |       test(`${label} — interactive targets meet the glove spec`, async ({ page }) => {
  269 |         await prepare(page, { theme, pseudo });
  270 |         await page.setViewportSize({ width: 360, height: 800 });
  271 |         await page.goto(`${BASE}${path}`);
  272 |         await settle(page);
  273 | 
  274 |         const tooSmall = await page.evaluate(
  275 |           ([selector, min, exempt]) => {
  276 |             const found = [];
  277 |             for (const el of document.querySelectorAll(selector)) {
  278 |               const r = el.getBoundingClientRect();
  279 |               if (r.width === 0 || r.height === 0) continue; // not rendered
  280 |               if (getComputedStyle(el).visibility === "hidden") continue;
  281 |               if (new RegExp(exempt).test(el.className) || el.closest(".mapboxgl-ctrl")) continue;
  282 |               if (r.height < min - 0.5 || r.width < min - 0.5) {
  283 |                 found.push(
  284 |                   `${el.tagName.toLowerCase()}.${el.className} ${Math.round(r.width)}×${Math.round(r.height)}`,
  285 |                 );
  286 |               }
  287 |             }
  288 |             return found;
```