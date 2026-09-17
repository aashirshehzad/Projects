"use client";

import { useState, useRef } from "react";
import { useRouter } from "next/navigation";
import styles from "./onboarding.module.css";

export function OnboardingFlow() {
  const router = useRouter();
  const [step, setStep] = useState<1 | 2>(1);
  const [linkedinUrl, setLinkedinUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function handleStepOneSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const pattern = /^https?:\/\/(www\.)?linkedin\.com\/.+/i;
    if (!pattern.test(linkedinUrl.trim())) {
      setError("Please enter a valid LinkedIn profile URL.");
      return;
    }
    setStep(2);
  }

  function handleFileSelect(selected: File | null) {
    setError(null);
    if (!selected) return;
    if (selected.type !== "application/pdf") {
      setError("Only PDF files are supported.");
      return;
    }
    if (selected.size > 5 * 1024 * 1024) {
      setError("File exceeds the 5MB limit.");
      return;
    }
    setFile(selected);
  }

  async function handleFinish() {
    if (!file) {
      setError("Please upload a CV to continue.");
      return;
    }
    setLoading(true);
    setError(null);

    const formData = new FormData();
    formData.append("file", file);

    const uploadRes = await fetch("/api/cvs/upload", {
      method: "POST",
      body: formData,
    });
    if (!uploadRes.ok) {
      const data = await uploadRes.json().catch(() => ({}));
      setError(data.error ?? "Failed to upload CV.");
      setLoading(false);
      return;
    }

    const profileRes = await fetch("/api/user/profile", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ linkedinUrl }),
    });
    if (!profileRes.ok) {
      const data = await profileRes.json().catch(() => ({}));
      setError(data.error ?? "Failed to save profile.");
      setLoading(false);
      return;
    }

    router.push("/dashboard");
    router.refresh();
  }

  return (
    <div className={styles.wrapper}>
      <div className={`card ${styles.card}`}>
        <div className={styles.progress}>
          <div className={`${styles.bar} ${step >= 1 ? styles.barActive : ""}`} />
          <div className={`${styles.bar} ${step >= 2 ? styles.barActive : ""}`} />
        </div>

        {step === 1 && (
          <form onSubmit={handleStepOneSubmit}>
            <h1 className={styles.title}>Your LinkedIn profile</h1>
            <p className={styles.subtitle}>
              We&apos;ll use this to help personalize your applications.
            </p>
            {error && <div className={styles.error}>{error}</div>}
            <input
              type="url"
              placeholder="https://www.linkedin.com/in/yourname"
              value={linkedinUrl}
              onChange={(e) => setLinkedinUrl(e.target.value)}
              required
            />
            <button type="submit" className="btn btn-dark" style={{ marginTop: 20, width: "100%" }}>
              Continue
            </button>
          </form>
        )}

        {step === 2 && (
          <div>
            <h1 className={styles.title}>Upload your CV</h1>
            <p className={styles.subtitle}>PDF only, up to 5MB.</p>
            {error && <div className={styles.error}>{error}</div>}
            <div
              className={`${styles.dropzone} ${dragOver ? styles.dropzoneActive : ""}`}
              onClick={() => fileInputRef.current?.click()}
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragOver(false);
                handleFileSelect(e.dataTransfer.files?.[0] ?? null);
              }}
            >
              {file ? (
                <span>{file.name}</span>
              ) : (
                <span>Drag & drop your CV here, or click to browse</span>
              )}
              <input
                ref={fileInputRef}
                type="file"
                accept="application/pdf"
                hidden
                onChange={(e) => handleFileSelect(e.target.files?.[0] ?? null)}
              />
            </div>
            <button
              type="button"
              disabled={loading}
              onClick={handleFinish}
              className="btn btn-dark"
              style={{ marginTop: 20, width: "100%" }}
            >
              {loading ? "Finishing up..." : "Finish setup"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
