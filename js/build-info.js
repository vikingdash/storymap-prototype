// The frontend half of the frontend/backend wire-contract version check (governing spec
// §9/§6's "stale frontend assets" gap — worst detectability rating in the whole FMEA
// table, since an already-open browser tab keeps running stale JS modules regardless of
// server-side cache headers). Detection only, per the approved Phase 2 scope — no UI is
// wired to this yet; that's deferred to whichever later phase implements the actual
// reload prompt. Bump this only when a genuinely breaking change is made to what any
// endpoint returns, in lockstep with backend/app.py's API_CONTRACT_VERSION.
export const API_CONTRACT_VERSION = 1;
