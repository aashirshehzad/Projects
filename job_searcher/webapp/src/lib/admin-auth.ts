import { SignJWT, jwtVerify } from "jose";
import bcrypt from "bcryptjs";
import { cookies } from "next/headers";
import { ADMIN_COOKIE_NAME } from "@/lib/admin-constants";

export { ADMIN_COOKIE_NAME };
const ADMIN_USERNAME = "easypezee";

// bcrypt hash of the admin password, generated once at module load.
// The plaintext password never sits in a variable beyond this call.
const ADMIN_PASSWORD_HASH = bcrypt.hashSync("fgvbsd53", 10);

function getSecretKey() {
  const secret = process.env.NEXTAUTH_SECRET;
  if (!secret) {
    throw new Error("NEXTAUTH_SECRET must be set to secure the admin panel");
  }
  return new TextEncoder().encode(secret);
}

export async function verifyAdminCredentials(
  username: string,
  password: string
): Promise<boolean> {
  if (username !== ADMIN_USERNAME) return false;
  return bcrypt.compare(password, ADMIN_PASSWORD_HASH);
}

export async function createAdminSessionToken(): Promise<string> {
  return new SignJWT({ role: "admin" })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime("8h")
    .sign(getSecretKey());
}

export async function isAdminSession(): Promise<boolean> {
  const cookieStore = await cookies();
  const token = cookieStore.get(ADMIN_COOKIE_NAME)?.value;
  if (!token) return false;
  try {
    const { payload } = await jwtVerify(token, getSecretKey());
    return payload.role === "admin";
  } catch {
    return false;
  }
}
