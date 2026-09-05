import { cookies } from "next/headers";

export const ALL = "all";
export const MARKET_COOKIE = "market";

/** Which market the rep is looking at. A cookie, not a URL param, because it is a
 *  global lens over every page, and links shouldn't have to carry it. */
export async function currentMarket(): Promise<string> {
  return (await cookies()).get(MARKET_COOKIE)?.value || ALL;
}
