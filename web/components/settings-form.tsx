"use client";
import { useActionState, useState } from "react";
import { Gauge, MapPin, Plus, X } from "lucide-react";
import { saveSettings } from "@/app/actions";
import { MAX_CATEGORIES, type Settings } from "@/lib/settings";
import { BTN, FIELD } from "./ui";

const BUCKET: Record<string, string> = { hot: "bg-hot", warm: "bg-warm", qualified: "bg-cool" };

export default function SettingsForm({ initial }: { initial: Settings }) {
  const [state, action, pending] = useActionState(saveSettings, null);
  const [cats, setCats] = useState(initial.categories);
  const [draft, setDraft] = useState("");

  function add() {
    const c = draft.trim().toLowerCase();
    if (c && !cats.includes(c) && cats.length < MAX_CATEGORIES) setCats([...cats, c]);
    setDraft("");
  }

  return (
    <form action={action} className="flex flex-col gap-4">
      <section className="flex flex-col gap-4 rounded-card bg-surface p-5 shadow-card">
        <h2 className="flex items-center gap-2 font-semibold">
          <MapPin size={16} strokeWidth={2} />
          Where to hunt
        </h2>

        <label className="flex flex-col gap-1.5">
          <span className="text-xs text-muted">City</span>
          <input name="city" defaultValue={initial.city} required className={`${FIELD} h-11 w-full max-w-sm`} />
        </label>

        <div className="flex flex-col gap-2">
          <span className="text-xs text-muted">
            Categories ({cats.length}/{MAX_CATEGORIES}), one Places search each
          </span>
          <input type="hidden" name="categories" value={cats.join("\n")} />
          <div className="flex flex-wrap items-center gap-2">
            {cats.map((c) => (
              <span
                key={c}
                className="flex h-9 items-center gap-1 rounded-pill bg-sunken pl-3.5 pr-1.5 text-sm"
              >
                {c}
                <button
                  type="button"
                  onClick={() => setCats(cats.filter((x) => x !== c))}
                  aria-label={`Remove ${c}`}
                  className="grid size-6 place-items-center rounded-full text-muted transition hover:bg-lost hover:text-ink"
                >
                  <X size={12} strokeWidth={2.5} />
                </button>
              </span>
            ))}
            <span className="flex items-center gap-1">
              <input
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === ",") {
                    e.preventDefault(); // Enter adds a category, it does not submit
                    add();
                  }
                }}
                placeholder="add category…"
                aria-label="Add a category"
                className={`${FIELD} h-9 w-36 px-3.5`}
              />
              <button
                type="button"
                onClick={add}
                aria-label="Add category"
                className="grid size-9 place-items-center rounded-full bg-sunken text-muted transition hover:text-ink"
              >
                <Plus size={15} strokeWidth={2} />
              </button>
            </span>
          </div>
        </div>
      </section>

      <section className="flex flex-col gap-4 rounded-card bg-surface p-5 shadow-card">
        <h2 className="flex items-center gap-2 font-semibold">
          <Gauge size={16} strokeWidth={2} />
          How to score
        </h2>
        <div className="flex flex-wrap gap-3">
          {(["hot", "warm", "qualified"] as const).map((k) => (
            <label key={k} className="flex flex-col gap-1.5">
              <span className="flex items-center gap-1.5 text-xs text-muted">
                <span className={`size-2.5 rounded-full ${BUCKET[k]}`} />
                {k.toUpperCase()}
              </span>
              <input
                name={k}
                type="number"
                min={0}
                max={100}
                step={1}
                required
                defaultValue={initial.thresholds[k]}
                className={`${FIELD} h-11 w-28 tabular-nums`}
              />
            </label>
          ))}
        </div>
      </section>

      <div className="flex flex-wrap items-center gap-3">
        <button
          disabled={pending}
          className={BTN}
        >
          {pending ? "Saving…" : "Save for the next crawl"}
        </button>
        {state && (
          <p
            role="status"
            className={`rounded-pill px-4 py-2 text-sm text-ink ${state.ok ? "bg-won" : "bg-lost"}`}
          >
            {state.message}
          </p>
        )}
      </div>
    </form>
  );
}
