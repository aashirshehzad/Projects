import Link from "next/link";
import styles from "./HeroSection.module.css";

export function HeroSection() {
  return (
    <section className={styles.hero}>
      <div className={`container ${styles.inner}`}>
        <span className={styles.eyebrow}>AI job application assistant</span>
        <h1 className={styles.headline}>
          Land your next role
          <br />
          <em>without the busywork</em>
        </h1>
        <p className={styles.subhead}>
          EasyPezee keeps your CVs organized, drafts outreach emails with AI,
          and tracks every application so you can focus on interviews, not
          spreadsheets.
        </p>
        <div className={styles.ctas}>
          <Link href="/register" className="btn btn-primary">
            Start for free
          </Link>
          <Link href="/login" className="btn btn-outline">
            I already have an account
          </Link>
        </div>
      </div>
    </section>
  );
}
