import type { NextAuthOptions } from "next-auth";
import Credentials from "next-auth/providers/credentials";

// Reps allowlist as JSON in env: REPS={"alice@you.com":"pw1","bob@you.com":"pw2"}
// ponytail: plaintext passwords in env — fine for a small internal team over HTTPS;
// upgrade to bcrypt hashes if the team grows or the threat model hardens.
function reps(): Record<string, string> {
  try { return JSON.parse(process.env.REPS || "{}"); } catch { return {}; }
}

export const authOptions: NextAuthOptions = {
  providers: [
    Credentials({
      name: "Email",
      credentials: { email: {}, password: {} },
      authorize(creds) {
        const r = reps();
        const email = creds?.email?.trim().toLowerCase() ?? "";
        if (email && r[email] && r[email] === creds?.password) {
          return { id: email, email };
        }
        return null;
      },
    }),
  ],
  session: { strategy: "jwt" },
  pages: { signIn: "/login" },
};
