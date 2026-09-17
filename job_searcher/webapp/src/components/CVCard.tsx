"use client";

import styles from "./CVCard.module.css";

export type CvItem = {
  id: string;
  filename: string;
  uploaded_at: string;
  is_active: number;
};

export function CVCard({
  cv,
  onActivate,
  onDelete,
}: {
  cv: CvItem;
  onActivate: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  return (
    <div className={`card ${styles.card}`}>
      {cv.is_active === 1 && <span className={styles.badge}>Active</span>}
      <h3 className={styles.filename}>{cv.filename}</h3>
      <p className={styles.date}>
        Uploaded {new Date(cv.uploaded_at).toLocaleDateString()}
      </p>
      <div className={styles.actions}>
        {cv.is_active !== 1 && (
          <button
            type="button"
            className="btn btn-outline"
            style={{ fontSize: 13, padding: "8px 14px" }}
            onClick={() => onActivate(cv.id)}
          >
            Set as active
          </button>
        )}
        <button
          type="button"
          className="btn"
          style={{
            fontSize: 13,
            padding: "8px 14px",
            background: "rgba(220,38,38,0.08)",
            color: "#b91c1c",
          }}
          onClick={() => onDelete(cv.id)}
        >
          Delete
        </button>
      </div>
    </div>
  );
}
