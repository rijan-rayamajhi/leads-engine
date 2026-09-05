// node lib/settings.test.mjs: settings steer crawler spend and lead bucketing.
import assert from "node:assert/strict";
import { parseSettings } from "./settings.ts";

const good = { city: "Pokhara, Nepal", categories: ["Cafe", "hotel"], hot: "90", warm: "70", qualified: "50" };
const ok = parseSettings(good);
assert.ok(ok.ok);
assert.deepEqual(ok.value.categories, ["cafe", "hotel"], "lowercased");
assert.deepEqual(ok.value.thresholds, { hot: 90, warm: 70, qualified: 50 });

// tidying
assert.deepEqual(
  parseSettings({ ...good, categories: [" Cafe ", "CAFE", "", "  ", "gym"] }).value.categories,
  ["cafe", "gym"],
  "trimmed, lowercased, deduped, blanks dropped",
);
assert.equal(parseSettings({ ...good, city: "  Pokhara  " }).value.city, "Pokhara");

const bad = (o, why, match) => {
  const r = parseSettings({ ...good, ...o });
  assert.equal(r.ok, false, why);
  if (match) assert.match(r.error, match, `${why}: rejected, but for the wrong reason: ${r.error}`);
};
bad({ city: "   " }, "blank city");
bad({ city: "x".repeat(121) }, "overlong city");
bad({ categories: [] }, "no categories");
bad({ categories: ["  ", ""] }, "only blanks");
bad({ categories: Array.from({ length: 31 }, (_, i) => `c${i}`) }, "too many categories");
bad({ categories: ["x".repeat(41)] }, "overlong category");
bad({ hot: "101" }, "over 100", /0 to 100/);
bad({ hot: "-1" }, "negative");
bad({ hot: "abc" }, "not a number");
bad({ hot: "90.5" }, "not an integer");
bad({ hot: "" }, "blank is rejected, not read as 0", /required/);
bad({ hot: "", warm: "0", qualified: "0" }, "blank still rejected when 0 would satisfy the ordering", /required/);
bad({ hot: "60", warm: "70" }, "HOT below WARM", /descend/);
bad({ warm: "40", qualified: "50" }, "WARM below QUALIFIED");
// equal thresholds are legal; one bucket simply goes unused
assert.equal(parseSettings({ ...good, hot: "70", warm: "70", qualified: "70" }).ok, true);

console.log("settings ok");
