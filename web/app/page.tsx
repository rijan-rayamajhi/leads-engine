import { sql, Lead } from "@/lib/db";
import LeadsBoard from "./leads-board";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import SignOut from "./sign-out";

export const dynamic = "force-dynamic";

export default async function Page() {
  const session = await getServerSession(authOptions);
  const leads = (await sql`
    select id, name, phone, email, service, what_they_want, evidence_quote,
           why_contact, source, source_url, intent_score, bucket, status
    from leads
    order by case bucket when 'HOT' then 0 when 'WARM' then 1
                         when 'QUALIFIED' then 2 else 3 end,
             intent_score desc
  `) as Lead[];
  return (
    <>
      <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
        <h1>Lead Engine</h1>
        <span style={{ marginLeft: "auto", fontSize: 12, color: "#9aa0a6" }}>
          {session?.user?.email} · <SignOut />
        </span>
      </div>
      <p className="sub">{leads.length} qualified leads · sorted hottest first</p>
      <LeadsBoard initial={leads} />
    </>
  );
}
