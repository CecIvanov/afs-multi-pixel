import { test } from "node:test";
import assert from "node:assert/strict";
import { clientIp, receiveRelay } from "./relay-intake.shared.mjs";

const relayRequest = (body, headers = {}) =>
  new Request("https://app.example.com/api/events", {
    method: "POST",
    headers: { "content-type": "text/plain", ...headers },
    body,
  });

test("a Relay is handed to the backend with its Origin, IP and user agent", async () => {
  const forwarded = [];
  const response = await receiveRelay(
    relayRequest('{"v":1}', {
      origin: "https://dontmiss.bg",
      "x-forwarded-for": "203.0.113.7",
      "user-agent": "Mozilla/5.0",
    }),
    { forward: async (relay) => forwarded.push(relay) },
  );

  assert.equal(response.status, 204);
  assert.deepEqual(forwarded, [
    { body: '{"v":1}', origin: "https://dontmiss.bg", ip: "203.0.113.7", user_agent: "Mozilla/5.0" },
  ]);
});

test("an oversized body is refused before reaching the backend", async () => {
  let called = false;
  const response = await receiveRelay(relayRequest("x".repeat(40 * 1024)), {
    forward: async () => {
      called = true;
    },
  });

  assert.equal(response.status, 413);
  assert.equal(called, false);
});

test("a backend failure still answers 204: the storefront can't act on it", async () => {
  const errors = [];
  const response = await receiveRelay(relayRequest("{}"), {
    forward: async () => {
      throw new Error("backend down");
    },
    logError: (name) => errors.push(name),
  });

  assert.equal(response.status, 204);
  assert.deepEqual(errors, ["relay_forward_failed"]);
});

test("clientIp reads X-Forwarded-For, then X-Real-IP", () => {
  assert.equal(clientIp(new Headers({ "x-forwarded-for": " 1.2.3.4 " })), "1.2.3.4");
  assert.equal(clientIp(new Headers({ "x-real-ip": "9.9.9.9" })), "9.9.9.9");
  assert.equal(clientIp(new Headers()), null);
});

test("clientIp ignores a client-forged first hop and takes the hop our proxy added", () => {
  assert.equal(clientIp(new Headers({ "x-forwarded-for": "6.6.6.6, 203.0.113.7" })), "203.0.113.7");
});
