import { redirect } from "next/navigation";
import Link from "next/link";
import { auth } from "@/lib/auth";
import { SignOutButton } from "@/components/SignOutButton";
import styles from "./dashboard.module.css";

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await auth();

  if (!session?.user) {
    redirect("/login");
  }
  if (!session.user.onboarded) {
    redirect("/onboarding");
  }

  return (
    <div className={styles.shell}>
      <aside className={styles.sidebar}>
        <Link href="/" className={styles.brand}>
          EasyPezee
        </Link>
        <nav className={styles.nav}>
          <Link href="/dashboard">Overview</Link>
          <Link href="/dashboard/cvs">CVs</Link>
          <Link href="/dashboard/jobs">Applications</Link>
        </nav>
        <div className={styles.userBox}>
          <span className={styles.userName}>
            {session.user.name ?? session.user.email}
          </span>
          <SignOutButton />
        </div>
      </aside>
      <main className={styles.content}>{children}</main>
    </div>
  );
}
