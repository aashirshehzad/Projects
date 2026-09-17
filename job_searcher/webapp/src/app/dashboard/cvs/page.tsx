"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { CVCard, type CvItem } from "@/components/CVCard";
import styles from "./cvs.module.css";

export default function CvManagerPage() {
  const [cvs, setCvs] = useState<CvItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadCvs = useCallback(async () => {
    const res = await fetch("/api/cvs/list");
    const data = await res.json();
    setCvs(data.cvs ?? []);
    setLoading(false);
  }, []);

  useEffect(() => {
    fetch("/api/cvs/list")
      .then((res) => res.json())
      .then((data) => {
        setCvs(data.cvs ?? []);
        setLoading(false);
      });
  }, []);

  async function uploadFile(file: File) {
    setError(null);
    if (file.type !== "application/pdf") {
      setError("Only PDF files are supported.");
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      setError("File exceeds the 5MB limit.");
      return;
    }
    setUploading(true);
    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch("/api/cvs/upload", { method: "POST", body: formData });
    setUploading(false);
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      setError(data.error ?? "Upload failed.");
      return;
    }
    await loadCvs();
  }

  async function handleActivate(id: string) {
    await fetch(`/api/cvs/${id}/activate`, { method: "POST" });
    await loadCvs();
  }

  async function handleDelete(id: string) {
    await fetch(`/api/cvs/${id}`, { method: "DELETE" });
    await loadCvs();
  }

  return (
    <div>
      <h1 className={styles.title}>Your CVs</h1>
      <p className={styles.subtitle}>
        Upload multiple CVs and choose which one is active for new applications.
      </p>

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
          const file = e.dataTransfer.files?.[0];
          if (file) uploadFile(file);
        }}
      >
        {uploading ? (
          <span>Uploading...</span>
        ) : (
          <span>Drag & drop a PDF here, or click to browse</span>
        )}
        <input
          ref={fileInputRef}
          type="file"
          accept="application/pdf"
          hidden
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) uploadFile(file);
            e.target.value = "";
          }}
        />
      </div>

      {loading ? (
        <p className={styles.subtitle}>Loading...</p>
      ) : cvs.length === 0 ? (
        <p className={styles.subtitle}>No CVs uploaded yet.</p>
      ) : (
        <div className={styles.grid}>
          {cvs.map((cv) => (
            <CVCard
              key={cv.id}
              cv={cv}
              onActivate={handleActivate}
              onDelete={handleDelete}
            />
          ))}
        </div>
      )}
    </div>
  );
}
