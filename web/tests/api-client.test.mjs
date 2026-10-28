import assert from "node:assert/strict";
import test from "node:test";
import { apiErrorMessage, apiGet, apiPostJson, waitForBackendReadiness } from "../lib/api-client.ts";

test("deadline covers a response body that stalls after HTTP headers", async () => {
  const previous = globalThis.fetch;
  globalThis.fetch = async (_url, { signal }) => ({
    text: () => new Promise((_resolve, reject) => signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true })),
  });
  try { await assert.rejects(apiGet("/test", { timeoutMs: 20 }), { kind: "timeout" }); }
  finally { globalThis.fetch = previous; }
});
test("caller cancellation stays active while receiving the body", async () => {
  const previous = globalThis.fetch;
  const controller = new AbortController();
  globalThis.fetch = async (_url, { signal }) => ({
    text: () => new Promise((_resolve, reject) => {
      signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true });
      controller.abort();
    }),
  });
  try { await assert.rejects(apiGet("/test", { signal: controller.signal }), { kind: "aborted" }); }
  finally { globalThis.fetch = previous; }
});
test("successful response and structured failure remain readable; POST is never retried", async () => {
  const previous = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async () => { calls++; return new Response(JSON.stringify({ error: { message: "busy", code: "BUSY" } }), { status: 503, headers: { "retry-after": "2" } }); };
  try {
    await assert.rejects(apiPostJson("/test", {}), { kind: "http", code: "BUSY", retryAfterMs: 2000 });
    assert.equal(calls, 1);
    globalThis.fetch = async () => Response.json({ ok: true });
    assert.deepEqual(await apiGet("/test"), { ok: true });
  } finally { globalThis.fetch = previous; }
});

test("disabled hosted capability gives a local-run instruction instead of a retry countdown", async () => {
  const previous = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async () => {
    calls++;
    return new Response(JSON.stringify({ error: { code: "DG_CAPABILITY_DISABLED", message: "disabled" } }), {
      status: 503,
      headers: { "retry-after": "60" },
    });
  };
  try {
    await assert.rejects(apiPostJson("/api/v1/solid/designs/run", {}), error => {
      const message = apiErrorMessage(error, "failed");
      assert.match(message, /비활성화/);
      assert.match(message, /로컬 실행/);
      assert.doesNotMatch(message, /다시 시도|준비되지|60초/);
      return true;
    });
    assert.equal(calls, 1);
  } finally { globalThis.fetch = previous; }
});

test("readiness stops polling an explicitly disabled capability", async () => {
  const previousFetch = globalThis.fetch;
  const previousWindow = globalThis.window;
  globalThis.window = globalThis;
  const progress = [];
  let calls = 0;
  globalThis.fetch = async () => {
    calls++;
    return new Response(JSON.stringify({ error: { code: "DG_CAPABILITY_DISABLED", message: "disabled" } }), { status: 503 });
  };
  try {
    await assert.rejects(waitForBackendReadiness({ domainId: "solid_part", deadlineMs: 50, onProgress: update => progress.push(update) }), { code: "DG_CAPABILITY_DISABLED" });
    assert.equal(calls, 1);
    assert.deepEqual(progress.map(update => update.phase), ["checking"]);
  } finally {
    globalThis.fetch = previousFetch;
    if (previousWindow === undefined) delete globalThis.window;
    else globalThis.window = previousWindow;
  }
});
