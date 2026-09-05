// node lib/password.test.mjs — hashing and password rules. A security path.
import assert from "node:assert/strict";
import { checkPassword, hashPassword, verifyPassword } from "./password.ts";

const stored = await hashPassword("correct horse battery");
assert.match(stored, /^scrypt\$16384\$8\$1\$[0-9a-f]{32}\$[0-9a-f]{128}$/, "self-describing format");
assert.equal(await verifyPassword("correct horse battery", stored), true);
assert.equal(await verifyPassword("Correct horse battery", stored), false, "case matters");
assert.equal(await verifyPassword("", stored), false);
assert.equal(await verifyPassword("correct horse batter", stored), false);

// same password, different salt, so hashes never collide
const again = await hashPassword("correct horse battery");
assert.notEqual(again, stored, "salted");
assert.equal(await verifyPassword("correct horse battery", again), true);

// a malformed or foreign hash must fail closed, not throw
for (const bad of ["", "plaintext", "bcrypt$x$y", "scrypt$16384$8$1$$", "scrypt$a$b$c$dd$ee"])
  assert.equal(await verifyPassword("anything", bad), false, `must reject ${JSON.stringify(bad)}`);

// rules
assert.equal(checkPassword("longenough1"), null);
assert.match(checkPassword("short"), /at least 8/);
assert.match(checkPassword("        "), /only spaces/);
assert.match(checkPassword("change-me"), /real password/);
assert.match(checkPassword("changeme"), /real password/);
assert.match(checkPassword("a@company.com", "a@company.com"), /your email/);

console.log("password ok");
