"use client";
import { signIn } from "next-auth/react";
import { useState } from "react";

export default function Login() {
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr("");
    const r = await signIn("credentials", { email, password: pw, redirect: false });
    setBusy(false);
    if (r?.error) setErr("Wrong email or password.");
    else window.location.href = "/";
  }

  return (
    <div style={{ maxWidth: 320, margin: "12vh auto" }}>
      <h1>Lead Engine</h1>
      <p className="sub">Sign in to view your leads.</p>
      <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <input className="in" type="email" placeholder="email" value={email}
          onChange={(e) => setEmail(e.target.value)} required />
        <input className="in" type="password" placeholder="password" value={pw}
          onChange={(e) => setPw(e.target.value)} required />
        <button disabled={busy} type="submit"
          style={{ background: "#16a34a", color: "#fff", border: 0, borderRadius: 8,
                   padding: "10px", fontWeight: 600, cursor: "pointer" }}>
          {busy ? "…" : "Sign in"}
        </button>
        {err && <p style={{ color: "#f87171", fontSize: 13 }}>{err}</p>}
      </form>
      <style>{`.in{background:#1a1d23;color:#e6e8eb;border:1px solid #2a2f37;border-radius:8px;padding:10px;font-size:14px}`}</style>
    </div>
  );
}
