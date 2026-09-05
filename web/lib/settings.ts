export type Settings = {
  city: string;
  categories: string[];
  thresholds: { hot: number; warm: number; qualified: number };
};

/** Used when the settings table is empty; mirrors crawler/config.yaml. */
export const DEFAULTS: Settings = {
  city: "Kathmandu, Nepal",
  categories: ["restaurant", "cafe", "hotel", "clinic", "salon"],
  thresholds: { hot: 90, warm: 70, qualified: 50 },
};

export const MAX_CITY = 120;
export const MAX_CATEGORIES = 30;
export const MAX_CATEGORY = 40;

type Raw = {
  city: string;
  categories: string[];
  hot: string;
  warm: string;
  qualified: string;
};

/** Trust boundary: these values steer what the crawler spends API quota on and
 *  how every lead is bucketed, so nothing gets through unchecked. */
export function parseSettings(raw: Raw): { ok: true; value: Settings } | { ok: false; error: string } {
  const city = raw.city.trim();
  if (!city) return { ok: false, error: "City is required." };
  if (city.length > MAX_CITY) return { ok: false, error: `City must be under ${MAX_CITY} characters.` };

  const categories = [
    ...new Set(raw.categories.map((c) => c.trim().toLowerCase()).filter(Boolean)),
  ];
  if (categories.length === 0) return { ok: false, error: "Add at least one category." };
  if (categories.length > MAX_CATEGORIES)
    return { ok: false, error: `At most ${MAX_CATEGORIES} categories. Each one is a separate Places search.` };
  if (categories.some((c) => c.length > MAX_CATEGORY))
    return { ok: false, error: `Each category must be under ${MAX_CATEGORY} characters.` };

  const nums: Record<string, number> = {};
  for (const k of ["hot", "warm", "qualified"] as const) {
    const text = String(raw[k] ?? "").trim();
    // Number("") is 0, so a blank field must not silently become a 0 threshold.
    if (!text) return { ok: false, error: `${k.toUpperCase()} is required.` };
    const n = Number(text);
    if (!Number.isInteger(n) || n < 0 || n > 100)
      return { ok: false, error: `${k.toUpperCase()} must be a whole number from 0 to 100.` };
    nums[k] = n;
  }
  if (!(nums.hot >= nums.warm && nums.warm >= nums.qualified))
    return { ok: false, error: "Thresholds must descend: HOT ≥ WARM ≥ QUALIFIED." };

  return {
    ok: true,
    value: { city, categories, thresholds: { hot: nums.hot, warm: nums.warm, qualified: nums.qualified } },
  };
}
