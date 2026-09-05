import { ChevronDown } from "lucide-react";

/** Native <select> with the OS arrow replaced by our own chevron.
 *  The wrapper carries the colour, so the chevron inherits it and a coloured
 *  pill (status, market) needs no extra wiring. Sizes match the other controls:
 *  xs on a dense card row, sm in a filter bar, md in a form. */
const H = { xs: "h-8", sm: "h-9", md: "h-11" };

export function Select({
  className = "",
  size = "sm",
  ...rest
}: Omit<React.ComponentProps<"select">, "size"> & { size?: keyof typeof H }) {
  return (
    <span
      className={`relative inline-flex items-center rounded-pill transition focus-within:ring-2 focus-within:ring-ink ${className}`}
    >
      <select
        {...rest}
        className={`${H[size]} cursor-pointer appearance-none rounded-pill bg-transparent pl-3.5 pr-8 text-sm font-medium text-inherit focus-visible:outline-none`}
      />
      <ChevronDown
        size={14}
        strokeWidth={2.25}
        aria-hidden
        className="pointer-events-none absolute right-3 opacity-60"
      />
    </span>
  );
}

/** Shared control styling. Height and width stay with the caller: putting them
 *  here collides with per-use overrides, since equal-specificity Tailwind
 *  classes resolve by stylesheet order, not by the order in the string. */
export const FIELD =
  "rounded-pill bg-sunken px-4 text-sm outline-none ring-1 ring-line transition focus:ring-2 focus:ring-ink placeholder:text-muted";

export const BTN =
  "h-11 rounded-pill bg-ink px-6 text-sm font-medium text-white transition hover:opacity-90 disabled:opacity-50";

/** Filter-bar pill: same 36px height as Select so a row of them lines up. */
export const CHIP =
  "inline-flex h-9 items-center rounded-pill px-3.5 text-sm font-medium transition";
