"use client";

import { useState } from "react";
import { signIn } from "next-auth/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import styles from "@/styles/auth.module.css";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    const result = await signIn("credentials", {
      email,
      password,
      redirect: false,
    });

    setLoading(false);

    if (result?.error) {
      setError("Invalid email or password.");
      return;
    }

    router.push("/dashboard");
    router.refresh();
  }

  return (
    <div className={styles.wrapper}>
      <div className={`card ${styles.card}`}>
        <Link href="/" className={styles.brand}>
          EasyPezee
        </Link>
        <h1 className={styles.title}>Welcome back</h1>
        <p className={styles.subtitle}>Log in to continue your job search.</p>

        <button
          type="button"
          className={`btn ${styles.google}`}
          onClick={() => signIn("google", { callbackUrl: "/dashboard" })}
        >
          Continue with Google
        </button>

        <div className={styles.divider}>or continue with email</div>

        {error && <div className={styles.error}>{error}</div>}

        <form className={styles.form} onSubmit={handleSubmit}>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="email">
              Email
            </label>
            <input
              id="email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="password">
              Password
            </label>
            <input
              id="password"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className={`btn btn-dark ${styles.submit}`}
          >
            {loading ? "Signing in..." : "Sign in"}
          </button>
        </form>

        <p className={styles.footerLink}>
          Don&apos;t have an account? <Link href="/register">Sign up</Link>
        </p>
      </div>
    </div>
  );
}
