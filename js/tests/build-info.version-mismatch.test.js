import { test } from "node:test";
import assert from "node:assert/strict";
import { setupJSDOM } from "./helpers/dom-setup.js";

setupJSDOM();
const { checkApiContractVersion } = await import("../live-analysis-service.js");
const { API_CONTRACT_VERSION } = await import("../build-info.js");

test("stale build-version mismatch can be detected: matching backend version reports matches:true", async () => {
  globalThis.fetch = async () => ({ ok: true, json: async () => ({ status: "ok", apiContractVersion: API_CONTRACT_VERSION }) });
  const result = await checkApiContractVersion();
  assert.equal(result.matches, true);
  assert.equal(result.backendVersion, API_CONTRACT_VERSION);
  assert.equal(result.frontendVersion, API_CONTRACT_VERSION);
});

test("stale build-version mismatch can be detected: different backend version reports matches:false", async () => {
  globalThis.fetch = async () => ({ ok: true, json: async () => ({ status: "ok", apiContractVersion: API_CONTRACT_VERSION + 1 }) });
  const result = await checkApiContractVersion();
  assert.equal(result.matches, false);
  assert.equal(result.backendVersion, API_CONTRACT_VERSION + 1);
});

test("an unreachable backend returns null, never a false mismatch", async () => {
  globalThis.fetch = async () => { throw new Error("network error"); };
  const result = await checkApiContractVersion();
  assert.equal(result, null);
});
