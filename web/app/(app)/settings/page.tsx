import Link from "next/link";
import SettingsForm from "@/components/settings-form";
import TeamPanel from "@/components/team-panel";
import { requireAdmin } from "@/lib/auth";
import { getSettings, listUsers } from "@/lib/db";
import { Clock, Gauge, MapPin, Tag, Users } from "lucide-react";
import { ago, CRON_HOURS } from "@/lib/leads";

export const dynamic = "force-dynamic";

export default async function SettingsPage({
  searchParams,
}: {
  searchParams: Promise<{ tab?: string }>;
}) {
  const [me, { tab }] = await Promise.all([requireAdmin(), searchParams]);
  const onTeam = tab === "team";
  const [s, users] = await Promise.all([getSettings(), onTeam ? listUsers() : []]);

  return (
    <div className="flex max-w-3xl flex-col gap-5">
      <section>
        <h1 className="text-2xl font-semibold">Settings</h1>
        <p className="text-sm text-muted">
          Stored in the database and merged over crawler/config.yaml. No commit, no redeploy.
        </p>
      </section>

      <nav className="flex gap-2">
        {[
          { key: "crawler", label: "Crawler", icon: <Gauge size={14} strokeWidth={2} /> },
          { key: "team", label: "Team", icon: <Users size={14} strokeWidth={2} /> },
        ].map((t) => {
          const on = (t.key === "team") === onTeam;
          return (
            <Link
              key={t.key}
              href={`/settings?tab=${t.key}`}
              className={`flex h-9 items-center gap-1.5 rounded-pill px-4 text-sm font-medium transition ${
                on ? "bg-ink text-white" : "bg-sunken text-muted hover:text-ink"
              }`}
            >
              {t.icon}
              {t.label}
            </Link>
          );
        })}
      </nav>

      {onTeam ? <TeamPanel users={users} me={me.email} /> : <SettingsForm initial={s} />}

      {!onTeam && (
      <ul className="flex flex-col gap-3 rounded-card bg-sunken px-5 py-4 text-sm text-muted">
        <li className="flex items-start gap-2.5">
          <MapPin size={15} strokeWidth={2} className="mt-0.5 shrink-0" />
          New city = new market. Existing leads stay in theirs; switch with the chip up top.
        </li>
        <li className="flex items-start gap-2.5">
          <Gauge size={15} strokeWidth={2} className="mt-0.5 shrink-0" />
          New thresholds re-bucket every existing lead, since a bucket is just a view of its score.
        </li>
        <li className="flex items-start gap-2.5">
          <Tag size={15} strokeWidth={2} className="mt-0.5 shrink-0" />
          Removing a category stops future searches; leads you already paid for stay.
        </li>
      </ul>
      )}

      {!onTeam && (
      <p className="flex items-center gap-2 text-sm text-muted">
        <Clock size={14} strokeWidth={1.75} />
        {s.updated_by ? `${s.updated_by} · ${ago(s.updated_at!)}` : "config.yaml defaults"} · crawls
        every {CRON_HOURS}h
      </p>
      )}
    </div>
  );
}
