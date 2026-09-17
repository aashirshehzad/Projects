import Link from "next/link";
import styles from "./Navbar.module.css";

export function Navbar() {
  return (
    <header className={styles.wrapper}>
      <nav className={styles.pill}>
        <Link href="/" className={styles.brand}>
          EasyPezee
        </Link>
        <div className={styles.links}>
          <Link href="/#features">Features</Link>
          <Link href="/#how-it-works">How it works</Link>
        </div>
        <div className={styles.actions}>
          <Link href="/login" className={styles.login}>
            Log in
          </Link>
          <Link href="/register" className="btn btn-dark">
            Get started
          </Link>
        </div>
      </nav>
    </header>
  );
}
