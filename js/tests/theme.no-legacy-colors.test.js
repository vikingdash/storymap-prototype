// Guards the Arctic Blue & Haze migration: (1) the :root token block matches the approved
// Style 6 hex values name-for-name, so nobody silently edits an approved color; (2) no raw
// hex/rgba literal exists anywhere outside :root, so a future PR can't paste a new
// hardcoded color instead of using a token; (3) the specific orphaned dark-theme and
// beige/amber legacy values this migration removed can never quietly reappear.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const CSS_PATH = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "css", "styles.css");
const css = readFileSync(CSS_PATH, "utf8");

// name -> approved value. --color-text-muted is intentionally darker than the value first
// proposed (#7A8795): that hex only cleared 3.67:1 against white, below the 4.5:1 AA floor
// its metadata/timestamp/count usage requires. Darkening was pre-authorized for this token
// specifically if it failed in context; every other value here is used exactly as approved.
const APPROVED_TOKENS = {
  "--color-page": "#F7FAFC",
  "--color-surface": "#FFFFFF",
  "--color-surface-secondary": "#EEF4FA",
  "--color-surface-tertiary": "#E7EEF6",
  "--color-text-primary": "#1D2A3A",
  "--color-text-secondary": "#536273",
  "--color-text-muted": "#5B6B7A",
  "--color-border": "#D8E1EA",
  "--color-border-strong": "#C4D0DC",
  "--color-primary": "#3E73C8",
  "--color-primary-hover": "#315FA7",
  "--color-primary-soft": "#E4EDF9",
  "--color-evidence": "#537DB7",
  "--color-evidence-soft": "#EAF1F8",
  "--color-success": "#4C7A68",
  "--color-review": "#9A742F",
  "--color-risk": "#A75A62",
};

function extractRootBlock(source) {
  const start = source.indexOf(":root");
  const braceOpen = source.indexOf("{", start);
  const braceClose = source.indexOf("\n}", braceOpen);
  return source.slice(braceOpen + 1, braceClose);
}

const rootBlock = extractRootBlock(css);
const bodyAfterRoot = css.slice(css.indexOf("\n}", css.indexOf(":root")) + 2);

test("every approved Style 6 token is present in :root with its exact approved value", () => {
  for (const [name, value] of Object.entries(APPROVED_TOKENS)) {
    const match = rootBlock.match(new RegExp(`${name}:\\s*([^;]+);`));
    assert.ok(match, `${name} must be defined in :root`);
    assert.equal(match[1].trim().toUpperCase(), value.toUpperCase(), `${name} must equal the approved value`);
  }
});

test("no raw hex or rgba color literal exists outside :root", () => {
  const hexMatches = bodyAfterRoot.match(/#[0-9a-fA-F]{3,6}\b/g) || [];
  const rgbaMatches = bodyAfterRoot.match(/rgba\(/g) || [];
  assert.deepEqual(hexMatches, [], "every color outside :root must be var(--color-*) or color-mix() off a token, never a literal hex");
  assert.deepEqual(rgbaMatches, [], "every translucent color outside :root must use color-mix() off a token, never a literal rgba()");
});

test("legacy Verdigris/Ink-era and orphaned dark-theme literals never reappear", () => {
  const RETIRED_LITERALS = [
    "#f8f6f1", "#f1ede4", "#ede7d9", "#1b2430", "#5b6472", "#e8e2d6",
    "#a9782f", "#3f7d5c", "#b1443a", "#2d6ca6", "#9c7a1e", "#6b5b95", "#2f8a85", "#5b5fc7",
    "#101b27", "#233348", "#263548", "#3c526b", "#1a1206", "#4b637d", "#7a8795",
  ];
  const lowerCss = css.toLowerCase();
  for (const literal of RETIRED_LITERALS) {
    assert.ok(!lowerCss.includes(literal.toLowerCase()), `retired legacy value ${literal} must not appear anywhere in styles.css`);
  }
});

test("legacy custom-property names (Verdigris/Ink era) are fully retired", () => {
  const RETIRED_NAMES = [
    "--bg", "--panel", "--panel2", "--panel3", "--text", "--muted", "--line",
    "--orange", "--green", "--red", "--blue", "--yellow", "--purple", "--teal",
    "--attention", "--focus-ring", "--shadow-sm", "--shadow-md", "--radius-sm", "--radius-md", "--serif",
  ];
  for (const name of RETIRED_NAMES) {
    // Word-boundary-ish check: the retired name must not appear as its own token anywhere,
    // including as a prefix collision with an approved name sharing the same stem.
    const pattern = new RegExp(`(^|[^a-zA-Z0-9-])${name}([^a-zA-Z0-9-]|$)`);
    assert.ok(!pattern.test(css), `retired token ${name} must not be declared or referenced anywhere`);
  }
});
