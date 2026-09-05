"use client";
import { signOut } from "next-auth/react";
export default function SignOut() {
  return (
    <a href="#" onClick={(e) => { e.preventDefault(); signOut({ callbackUrl: "/login" }); }}
       style={{ color: "#60a5fa" }}>sign out</a>
  );
}
