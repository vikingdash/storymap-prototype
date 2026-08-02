// Minimal jsdom bootstrap shared by every Phase 2 frontend test. Call setupJSDOM() once,
// synchronously, at the top of a test file -- BEFORE dynamically importing any component
// module -- since every component relies on the bare global document/window (matching how
// it runs in a real browser), not an injected parameter. live-analysis-service.js also
// reads window.location.hostname at module-import time, which is exactly why the dynamic
// import must come after this call, never before it.
import { JSDOM } from "jsdom";

// Node 21+ ships its own built-in global `navigator` as a getter with no setter, so a
// plain `globalThis.navigator = ...` throws ("Cannot set property navigator ... which has
// only a getter"). defineProperty overrides it outright, same as every other global here.
function defineGlobal(name, value) {
  Object.defineProperty(globalThis, name, { value, configurable: true, writable: true });
}

export function setupJSDOM() {
  const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost:4173/" });
  globalThis.window = dom.window;
  globalThis.document = dom.window.document;
  defineGlobal("navigator", dom.window.navigator);
  globalThis.HTMLElement = dom.window.HTMLElement;
  globalThis.Node = dom.window.Node;
  globalThis.localStorage = dom.window.localStorage;
  // jsdom doesn't implement confirm()/alert() itself -- only Recommendation.js's "Add
  // sources" flow ever calls confirm(), which none of the Phase 2 fixtures exercise, but
  // leaving it undefined would throw the moment any code path touched it.
  globalThis.confirm = () => true;
  // jsdom also doesn't implement Element.scrollIntoView at all (a well-known gap, not a
  // real-browser difference) -- StrategicFoundation.js's review-strip jump-links call it.
  // A no-op default here; individual tests that need to assert on the call still override
  // it per-element, which shadows this prototype default normally.
  if (!dom.window.HTMLElement.prototype.scrollIntoView) {
    dom.window.HTMLElement.prototype.scrollIntoView = function scrollIntoView() {};
  }
  return dom;
}

// Each individual test gets its own detached-then-attached <div>, so tests within the
// same file never see each other's leftover DOM.
export function freshContainer() {
  const el = document.createElement("div");
  document.body.appendChild(el);
  return el;
}
