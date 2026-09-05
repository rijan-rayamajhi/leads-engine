"use client";
import { useMemo, useState } from "react";
import type { Lead } from "@/lib/db";

const STATUSES = ["new", "contacted", "replied", "meeting", "proposal", "won", "lost"];

export default function LeadsBoard({ initial }: { initial: Lead[] }) {
  const [leads, setLeads] = useState(initial);
  const [q, setQ] = useState("");
  const [bucket, setBucket] = useState("all");
  const [service, setService] = useState("all");

  const services = useMemo(
    () => Array.from(new Set(initial.map((l) => l.service))).sort(),
    [initial]
  );

  const shown = leads.filter((l) => {
    if (bucket !== "all" && l.bucket !== bucket) return false;
    if (service !== "all" && l.service !== service) return false;
    if (q && !(`${l.name} ${l.what_they_want} ${l.why_contact}`
      .toLowerCase().includes(q.toLowerCase()))) return false;
    return true;
  });

  const counts = { HOT: 0, WARM: 0, QUALIFIED: 0 } as Record<string, number>;
  leads.forEach((l) => { if (l.bucket in counts) counts[l.bucket]++; });

  async function setStatus(id: string, status: string) {
    setLeads((ls) => ls.map((l) => (l.id === id ? { ...l, status } : l)));
    await fetch("/api/leads", {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ id, status }),
    }).catch(() => {});
  }

  return (
    <>
      <div className="counts">
        <span className="pill">🔥 HOT {counts.HOT}</span>
        <span className="pill">● WARM {counts.WARM}</span>
        <span className="pill">○ QUALIFIED {counts.QUALIFIED}</span>
      </div>
      <div className="bar">
        <input placeholder="Search name / need…" value={q}
          onChange={(e) => setQ(e.target.value)} />
        <select value={bucket} onChange={(e) => setBucket(e.target.value)}>
          <option value="all">All buckets</option>
          <option>HOT</option><option>WARM</option><option>QUALIFIED</option>
        </select>
        <select value={service} onChange={(e) => setService(e.target.value)}>
          <option value="all">All services</option>
          {services.map((s) => <option key={s}>{s}</option>)}
        </select>
      </div>

      {shown.map((l) => (
        <div key={l.id} className={`card ${l.bucket}`}>
          <div className="row1">
            <span className="name">{l.name}</span>
            <span className={`badge ${l.bucket}`}>{l.bucket}</span>
            <span className="svc">{l.service}</span>
            <span className="score">score {l.intent_score}</span>
          </div>
          <div className="want">{l.what_they_want}</div>
          <div className="why">{l.why_contact}</div>
          <div className="ev">{l.evidence_quote}</div>
          <div className="actions">
            {l.phone && <a className="call" href={`tel:${l.phone}`}>📞 {l.phone}</a>}
            <a className="link" href={l.source_url} target="_blank" rel="noreferrer">source ↗</a>
            <select className={`status ${l.status !== "new" ? "done" : ""}`}
              value={l.status} onChange={(e) => setStatus(l.id, e.target.value)}>
              {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
        </div>
      ))}
      {shown.length === 0 && <p className="sub">No leads match these filters.</p>}
    </>
  );
}
