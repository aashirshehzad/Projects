import { Navbar } from "@/components/Navbar";
import { HeroSection } from "@/components/HeroSection";
import { FeatureCard } from "@/components/FeatureCard";
import styles from "./landing.module.css";

const FEATURES = [
  {
    title: "One home for every CV",
    description:
      "Upload, organize, and pick your active CV in seconds — no more digging through email attachments.",
  },
  {
    title: "AI-drafted outreach",
    description:
      "EasyPezee drafts tailored application emails using your CV and the job details, so you write less and send more.",
  },
  {
    title: "Applications, tracked",
    description:
      "See every application you've sent, its status, and what's next — all from one clean dashboard.",
  },
];

const STEPS = [
  {
    step: "01",
    title: "Sign up in seconds",
    description: "Create an account with Google or email — no setup fuss.",
  },
  {
    step: "02",
    title: "Add your profile",
    description:
      "Paste your LinkedIn URL and upload your CV during a quick onboarding flow.",
  },
  {
    step: "03",
    title: "Apply with confidence",
    description:
      "Track applications and let EasyPezee help you draft the outreach.",
  },
];

export default function Home() {
  return (
    <>
      <Navbar />
      <HeroSection />

      <section id="features" className={styles.section}>
        <div className="container">
          <h2 className={styles.sectionTitle}>
            Everything you need, <em>nothing you don&apos;t</em>
          </h2>
          <div className={styles.grid}>
            {FEATURES.map((feature) => (
              <FeatureCard key={feature.title} {...feature} />
            ))}
          </div>
        </div>
      </section>

      <section id="how-it-works" className={styles.section}>
        <div className="container">
          <h2 className={styles.sectionTitle}>How it works</h2>
          <div className={styles.steps}>
            {STEPS.map((item) => (
              <div key={item.step} className={styles.step}>
                <span className={styles.stepNumber}>{item.step}</span>
                <h3 className={styles.stepTitle}>{item.title}</h3>
                <p className={styles.stepDescription}>{item.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <footer className={styles.footer}>
        <div className={`container ${styles.footerInner}`}>
          <span className={styles.brand}>EasyPezee</span>
          <span>© {new Date().getFullYear()} EasyPezee. All rights reserved.</span>
        </div>
      </footer>
    </>
  );
}
