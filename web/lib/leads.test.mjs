// node lib/leads.test.mjs: the board's counting and filtering rules.
import assert from "node:assert/strict";
import { ago, cleanName, filterLeads, heroCounts, pageWindow, paginate, runHealth, winRate } from "./leads.ts";

const now = Date.parse("2026-01-10T12:00:00Z");
const lead = (o) => ({
  id: o.id, name: o.name ?? "Cafe", phone: "+977 1", email: null, service: o.service ?? "website",
  what_they_want: "Needs a real website", evidence_quote: o.ev ?? "Cafe, 4.8 (315 reviews)",
  why_contact: "No website", source: "google_maps_gap", source_url: "u",
  intent_score: 100, bucket: o.bucket ?? "HOT", status: o.status ?? "new",
  assigned_to: null, found_at: o.found_at ?? "2026-01-10T09:00:00Z", ...o,
});

const rows = [
  lead({ id: "1", bucket: "HOT" }),
  lead({ id: "2", bucket: "WARM", status: "contacted" }),
  lead({ id: "3", bucket: "HOT", phone: null }),
  lead({ id: "4", bucket: "QUALIFIED", found_at: "2026-01-01T00:00:00Z" }),
  lead({ id: "5", bucket: "WARM", name: "Momo Hut", service: "chatbot", status: "won",
        ev: "Restaurant, 4.2 (12 reviews)" }),
];

const h = heroCounts(rows, now);
assert.equal(h.ready, 1, "only lead 1: 2 is contacted, 3 has no phone, 4 is QUALIFIED, 5 is won");
assert.equal(h.newToday, 4, "one lead is 9 days old");
assert.deepEqual(h.byBucket, { HOT: 2, WARM: 2, QUALIFIED: 1 });

const all = { bucket: "all", status: "all", service: "all", q: "" };
assert.equal(filterLeads(rows, all).length, 5);
assert.equal(filterLeads(rows, { ...all, bucket: "HOT" }).length, 2);
assert.equal(filterLeads(rows, { ...all, status: "won" }).length, 1);
assert.equal(filterLeads(rows, { ...all, service: "chatbot" }).length, 1);
// search spans name, need, evidence and phone, and stacks with the other filters
assert.equal(filterLeads(rows, { ...all, q: "momo" }).length, 1);
assert.equal(filterLeads(rows, { ...all, q: "MOMO" }).length, 1, "case-insensitive");
assert.equal(filterLeads(rows, { ...all, q: "315 reviews" }).length, 4);
assert.equal(filterLeads(rows, { ...all, q: "momo", bucket: "HOT" }).length, 0);
assert.equal(filterLeads(rows, { ...all, q: "   " }).length, 5, "blank search is not a filter");

console.log("leads ok");

// SEO-stuffed Places names get trimmed to the business
assert.equal(cleanName("Carpe Diem Bakery | Top Restaurant in Kathmandu"), "Carpe Diem Bakery");
assert.equal(cleanName("Cycle Coffee Co"), "Cycle Coffee Co");
assert.equal(cleanName(null), "Unknown");
console.log("cleanName ok");

// activity rail timestamps
const T = Date.parse("2026-01-10T12:00:00Z");
const back = (s) => new Date(T - s * 1000).toISOString();
assert.equal(ago(back(30), T), "just now");
assert.equal(ago(back(300), T), "5m ago");
assert.equal(ago(back(4 * 3600), T), "4h ago");
assert.equal(ago(back(3 * 86400), T), "3d ago");
assert.doesNotMatch(ago(back(30 * 86400), T), /ago/, "older than a week falls back to a date");
console.log("ago ok");

// small samples must never print a rate; this is the page's honesty guarantee
assert.deepEqual(winRate(0, 0), { decided: 0, enough: false, needed: 5, pct: 0 });
assert.equal(winRate(1, 0).enough, false, "1 win is not a 100% win rate");
assert.equal(winRate(1, 0).needed, 4);
assert.equal(winRate(0, 1).enough, false, "1 loss is not a 0% win rate");
assert.deepEqual(winRate(3, 2), { decided: 5, enough: true, needed: 0, pct: 60 });
assert.equal(winRate(1, 2).pct, 33, "rounds to whole percent");
assert.equal(winRate(10, 0).pct, 100);
console.log("winRate ok");

// crawler freshness: 6h cron, stale after 1.5 cycles
const N = Date.parse("2026-01-10T12:00:00Z");
const hoursAgo = (h) => new Date(N - h * 3600_000).toISOString();
assert.deepEqual(runHealth(null, N), { everRan: false, stale: true, hours: null });
assert.equal(runHealth(hoursAgo(2), N).stale, false);
assert.equal(runHealth(hoursAgo(6), N).stale, false, "exactly one cycle is still healthy");
assert.equal(runHealth(hoursAgo(10), N).stale, true, "past 9h the cron has missed one");
assert.equal(Math.round(runHealth(hoursAgo(10), N).hours), 10);
console.log("runHealth ok");

// pagination: the slice, and the clamp that stops a stale page blanking the list
const nums = Array.from({ length: 83 }, (_, i) => i + 1);
let p = paginate(nums, 1, 24);
assert.deepEqual([p.pages, p.current, p.from, p.to, p.slice.length], [4, 1, 1, 24, 24]);
p = paginate(nums, 4, 24);
assert.deepEqual([p.current, p.from, p.to, p.slice.length], [4, 73, 83, 11], "last page is short");
assert.equal(paginate(nums, 99, 24).current, 4, "page past the end clamps to the last");
assert.equal(paginate(nums, 0, 24).current, 1, "page below 1 clamps up");
assert.equal(paginate(nums, -5, 24).current, 1);
p = paginate([], 1, 24);
assert.deepEqual([p.pages, p.from, p.to, p.slice.length], [1, 0, 0, 0], "empty list still has one page");
p = paginate(Array.from({ length: 48 }, (_, i) => i), 2, 24);
assert.deepEqual([p.pages, p.from, p.to], [2, 25, 48], "exact multiple leaves no empty page");

// page window: every page while they fit, then first/last plus a window
assert.deepEqual(pageWindow(1, 4), [1, 2, 3, 4]);
assert.deepEqual(pageWindow(1, 7), [1, 2, 3, 4, 5, 6, 7]);
assert.deepEqual(pageWindow(1, 20), [1, 2, null, 20]);
assert.deepEqual(pageWindow(10, 20), [1, null, 9, 10, 11, null, 20]);
assert.deepEqual(pageWindow(20, 20), [1, null, 19, 20]);
assert.deepEqual(pageWindow(3, 20), [1, 2, 3, 4, null, 20], "no gap marker right next to page 1");
console.log("paginate ok");
