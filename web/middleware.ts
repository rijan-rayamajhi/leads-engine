import { withAuth } from "next-auth/middleware";

export default withAuth({ pages: { signIn: "/login" } });

// Protect everything except the login page, auth endpoints, and static assets.
export const config = {
  matcher: ["/((?!login|api/auth|_next/static|_next/image|favicon.ico).*)"],
};
