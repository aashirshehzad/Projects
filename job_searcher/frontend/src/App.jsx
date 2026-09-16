import { useEffect, useState } from "react";
import { api, gmailComposeUrl, mailtoUrl } from "./api";
import "./App.css";

const PLACEHOLDER_EMAIL = "recruiter-email-not-found@example.com";

const STEPS = ["Profile", "Job", "Match", "Draft"];

export default function App() {
  const [step, setStep] = useState(0);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const [hasProfile, setHasProfile] = useState(false);
  const [profileText, setProfileText] = useState("");

  const [jobText, setJobText] = useState("");
  const [job, setJob] = useState(null);
  const [match, setMatch] = useState(null);
  const [duplicate, setDuplicate] = useState(null);

  const [draft, setDraft] = useState(null);
  const [opened, setOpened] = useState(false);

  useEffect(() => {
    api.getProfile().then((r) => setHasProfile(r.has_profile)).catch(() => {});
  }, []);

  async function handleFileUpload(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setError("");
    setLoading(true);
    try {
      await api.uploadProfileFile(file);
      setHasProfile(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleTextUpload() {
    if (!profileText.trim()) return;
    setError("");
    setLoading(true);
    try {
      await api.uploadProfileText(profileText);
      setHasProfile(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleAnalyze() {
    if (!jobText.trim()) return;
    setError("");
    setLoading(true);
    try {
      const res = await api.analyzeJob(jobText);
      setJob(res.job);
      setMatch(res.match);
      setDuplicate(res.duplicate);
      setDraft(null);
      setOpened(false);
      setStep(2);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleGenerateDraft(force = false) {
    setError("");
    setLoading(true);
    try {
      const res = await api.draftEmail(force);
      setDraft(res.draft);
      setStep(3);
    } catch (err) {
      if (err.status === 409) {
        // role mismatch - the confirm banner in the Match step handles this
        setError(err.message);
      } else {
        setError(err.message);
      }
    } finally {
      setLoading(false);
    }
  }

  async function handleSkip() {
    setError("");
    setLoading(true);
    try {
      await api.skipJob();
      setStep(1);
      setJob(null);
      setMatch(null);
      setJobText("");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function handleOpenCompose(kind) {
    const url =
      kind === "gmail"
        ? gmailComposeUrl({ to: draft.recipient_email, subject: draft.subject_line, body: draft.body })
        : mailtoUrl({ to: draft.recipient_email, subject: draft.subject_line, body: draft.body });
    window.open(url, "_blank", "noopener,noreferrer");
    setOpened(true);
    api.markOpened().catch(() => {});
  }

  return (
    <div className="app">
      <header>
        <h1>JobAgent</h1>
        <p className="subtitle">Match your resume to a job posting and draft a cold outreach email.</p>
      </header>

      <nav className="steps">
        {STEPS.map((label, i) => (
          <span key={label} className={`step ${i === step ? "active" : ""} ${i < step ? "done" : ""}`}>
            {i + 1}. {label}
          </span>
        ))}
      </nav>

      {error && <div className="error-banner">{error}</div>}

      {step === 0 && (
        <section className="card">
          <h2>1. Upload your resume</h2>
          {hasProfile && <p className="ok-banner">A resume is already loaded for this session.</p>}
          <div className="row">
            <input type="file" accept=".pdf,.txt,.md" onChange={handleFileUpload} disabled={loading} />
          </div>
          <p className="or">or paste resume text</p>
          <textarea
            rows={8}
            placeholder="Paste your resume text here..."
            value={profileText}
            onChange={(e) => setProfileText(e.target.value)}
          />
          <div className="row">
            <button onClick={handleTextUpload} disabled={loading || !profileText.trim()}>
              Save pasted text
            </button>
            <button className="primary" onClick={() => setStep(1)} disabled={!hasProfile}>
              Next: Add Job →
            </button>
          </div>
        </section>
      )}

      {step === 1 && (
        <section className="card">
          <h2>2. Paste the job description</h2>
          <textarea
            rows={12}
            placeholder="Paste the LinkedIn job description here..."
            value={jobText}
            onChange={(e) => setJobText(e.target.value)}
          />
          <div className="row">
            <button onClick={() => setStep(0)}>← Back</button>
            <button className="primary" onClick={handleAnalyze} disabled={loading || !jobText.trim()}>
              {loading ? "Analyzing..." : "Analyze Match"}
            </button>
          </div>
        </section>
      )}

      {step === 2 && job && match && (
        <section className="card">
          <h2>3. Match result</h2>
          <h3>
            {job.job_title} @ {job.company_name}
          </h3>
          <p>
            Recruiter: {job.recruiter_name || "N/A"} &lt;{job.recruiter_email || "N/A"}&gt;
          </p>
          <p>Tech stack: {job.tech_stack.join(", ") || "N/A"}</p>

          {duplicate && (
            <p className="warn-banner">
              You already processed a job at this company with this title on{" "}
              {new Date(duplicate.created_at).toLocaleString()} (status: {duplicate.draft_status}).
            </p>
          )}

          <div className={`score ${match.is_aligned ? "aligned" : "mismatch"}`}>
            Match score: {match.match_score}% — {match.is_aligned ? "Aligned" : "Mismatch"}
          </div>
          <p>{match.verdict_summary}</p>

          <div className="two-col">
            <div>
              <h4>Strengths</h4>
              <ul>
                {match.matching_strengths.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            </div>
            <div>
              <h4>Gaps</h4>
              <ul>
                {match.missing_or_gap_skills.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            </div>
          </div>

          {!match.is_aligned && (
            <div className="warn-banner">
              Role mismatch detected ({match.match_score}%). Do you still want to generate an application?
              <div className="row">
                <button onClick={handleSkip} disabled={loading}>
                  No, skip this job
                </button>
                <button className="primary" onClick={() => handleGenerateDraft(true)} disabled={loading}>
                  Yes, generate anyway
                </button>
              </div>
            </div>
          )}

          {match.is_aligned && (
            <div className="row">
              <button onClick={() => setStep(1)}>← Back</button>
              <button className="primary" onClick={() => handleGenerateDraft(false)} disabled={loading}>
                {loading ? "Drafting..." : "Generate Email Draft →"}
              </button>
            </div>
          )}
        </section>
      )}

      {step === 3 && draft && (
        <section className="card">
          <h2>4. Generated email draft</h2>
          <p>
            <strong>To:</strong> {draft.recipient_email}
          </p>
          <p>
            <strong>Subject:</strong> {draft.subject_line}
          </p>
          <textarea rows={12} value={draft.body} readOnly />

          {draft.recipient_email === PLACEHOLDER_EMAIL && (
            <p className="warn-banner">
              No recruiter email was found in the job posting — fill in the real "To" address yourself
              before sending.
            </p>
          )}

          {opened && <p className="ok-banner">Opened in your email client. Review and hit send there.</p>}

          <div className="row">
            <button onClick={() => setStep(2)}>← Back</button>
            <button className="primary" onClick={() => handleOpenCompose("gmail")}>
              Open in Gmail
            </button>
            <button onClick={() => handleOpenCompose("mailto")}>Open in email client</button>
          </div>
          <p className="hint">
            This opens a pre-filled compose window in your own email account — nothing is sent
            automatically. Review it, then hit send yourself.
          </p>
        </section>
      )}

      <footer>
        <p>Your resume is only stored for this browser session. Emails are never sent automatically.</p>
      </footer>
    </div>
  );
}
