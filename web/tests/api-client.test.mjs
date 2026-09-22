import assert from "node:assert/strict";
import test from "node:test";
import { apiGet, apiPostJson } from "../lib/api-client.ts";

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
