import { sql } from "@/lib/db";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";

export const dynamic = "force-dynamic";

export async function GET() {
  const leads = await sql`
    select id, name, phone, email, service, what_they_want, evidence_quote,
           why_contact, source, source_url, intent_score, bucket, status
    from leads order by intent_score desc`;
  return Response.json(leads);
}

export async function PATCH(req: Request) {
  const session = await getServerSession(authOptions);
  const rep = session?.user?.email;
  if (!rep) return Response.json({ error: "unauthorized" }, { status: 401 });
  const { id, status } = await req.json();
  if (!id || !status) return Response.json({ error: "id+status required" }, { status: 400 });
  await sql`update leads set status = ${status} where id = ${id}`;
  await sql`insert into outcomes (lead_id, rep_email, status)
            values (${id}, ${rep}, ${status})`;
  return Response.json({ ok: true });
}
