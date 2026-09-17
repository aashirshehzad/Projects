import NextAuth from "next-auth";
import Google from "next-auth/providers/google";
import Credentials from "next-auth/providers/credentials";
import bcrypt from "bcryptjs";
import {
  createUser,
  findUserByEmail,
  findUserByGoogleId,
  findUserById,
} from "@/lib/db";
import { logActivity } from "@/lib/db";
import { sendDiscordAlert } from "@/lib/discord";

export const { handlers, signIn, signOut, auth } = NextAuth({
  session: { strategy: "jwt" },
  pages: {
    signIn: "/login",
  },
  providers: [
    Google({
      clientId: process.env.GOOGLE_CLIENT_ID,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET,
    }),
    Credentials({
      name: "credentials",
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        const email = credentials?.email as string | undefined;
        const password = credentials?.password as string | undefined;
        if (!email || !password) return null;

        const user = findUserByEmail(email.toLowerCase());
        if (!user || !user.password_hash) return null;

        const valid = await bcrypt.compare(password, user.password_hash);
        if (!valid) return null;

        return {
          id: user.id,
          email: user.email,
          name: user.name ?? undefined,
          image: user.avatar_url ?? undefined,
        };
      },
    }),
  ],
  callbacks: {
    async signIn({ user, account }) {
      if (account?.provider === "google") {
        const googleId = account.providerAccountId;
        const email = (user.email ?? "").toLowerCase();
        if (!email) return false;

        let existing = findUserByGoogleId(googleId) ?? findUserByEmail(email);

        if (!existing) {
          existing = createUser({
            email,
            name: user.name,
            googleId,
            avatarUrl: user.image,
          });
          logActivity({
            userId: existing.id,
            event: "user_registered",
            metadata: { method: "google" },
          });
          await sendDiscordAlert("user_registered", {
            email: existing.email,
            method: "google",
          });
        }

        user.id = existing.id;
      }
      return true;
    },
    async jwt({ token, user }) {
      if (user?.id) {
        token.userId = user.id;
      }
      if (token.userId) {
        const dbUser = findUserById(token.userId as string);
        if (dbUser) {
          token.onboarded = dbUser.onboarded === 1;
        }
      }
      return token;
    },
    async session({ session, token }) {
      if (session.user && token.userId) {
        session.user.id = token.userId as string;
        session.user.onboarded = Boolean(token.onboarded);
      }
      return session;
    },
  },
});
