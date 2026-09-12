import assert from "node:assert/strict";
import { passwordPolicyError } from "../src/lib/password-policy.ts";

assert.equal(passwordPolicyError("Strong!1", "en"), "");
assert.match(passwordPolicyError("short", "en"), /8/);
assert.match(passwordPolicyError("lowercase!1", "en"), /uppercase/);
assert.match(passwordPolicyError("NO-NUMBER!", "en"), /number/);
assert.match(passwordPolicyError("NoSymbol1", "en"), /symbol/);
console.log("password policy regression checks passed");
