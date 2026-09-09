import { useEffect, useMemo, useRef, useState } from "react";
import { marked } from "marked";
import DOMPurify from "dompurify";
import { meta, SUGGESTIONS } from "./tools.js";

marked.setOptions({ breaks: true, gfm: true });

function Markdown({ text }) {
  const html = useMemo(
    () => DOMPurify.sanitize(marked.parse(text || "")),
    [text]
  );
  return <div className="md" dangerouslySetInnerHTML={{ __html: html }} />;
}

function Logo() {
  return (
    <svg className="logo" viewBox="0 0 32 32" aria-hidden="true">
      <defs>
        <linearGradient id="lg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#6366f1" />
          <stop offset="1" stopColor="#a855f7" />
        </linearGradient>
      </defs>
      <rect x="1" y="1" width="30" height="30" rx="9" fill="url(#lg)" />
      <circle cx="16" cy="16" r="4.4" fill="#fff" />
      <g fill="#fff">
        <circle cx="16" cy="5.4" r="2.1" />
        <circle cx="16" cy="26.6" r="2.1" />
        <circle cx="5.4" cy="16" r="2.1" />
        <circle cx="26.6" cy="16" r="2.1" />
      </g>
      <g stroke="#fff" strokeWidth="1.6" opacity="0.9">
        <line x1="16" y1="11.6" x2="16" y2="7.5" />
        <line x1="16" y1="20.4" x2="16" y2="24.5" />
        <line x1="11.6" y1="16" x2="7.5" y2="16" />
        <line x1="20.4" y1="16" x2="24.5" y2="16" />
      </g>
    </svg>
  );
}

function ToolStep({ step }) {
  const [open, setOpen] = useState(false);
  const m = meta(step.tool);
  const failed = step.result && step.result.error;
  const args = Object.entries(step.args || {});
  return (
    <div className={`step ${failed ? "failed" : ""}`}>
      <button className="step-head" onClick={() => setOpen((v) => !v)}>
        <span className="step-icon" style={{ background: m.accent + "22" }}>
          {m.icon}
        </span>
        <span className="step-name">{step.tool}</span>
        <span className="step-args">
          {args.map(([k, v]) => (
            <span className="pill" key={k}>
              <b>{k}</b> {String(v)}
            </span>
          ))}
        </span>
        <span className={`chev ${open ? "up" : ""}`}>›</span>
      </button>
      {open && (
        <pre className="step-body">{JSON.stringify(step.result, null, 2)}</pre>
      )}
    </div>
  );
}

function GmailIcon() {
  return (
    <svg viewBox="0 0 48 48" width="15" height="15" aria-hidden="true">
      <path fill="#4285F4" d="M6 12v24a2 2 0 002 2h6V21l10 7.4L34 21v17h6a2 2 0 002-2V12L24 25.4z" />
      <path fill="#34A853" d="M6 12v24a2 2 0 002 2h6V21z" />
      <path fill="#FBBC04" d="M34 21v17h6a2 2 0 002-2V12z" />
      <path fill="#EA4335" d="M6 12l18 13.4L42 12a3 3 0 00-3-3H9a3 3 0 00-3 3z" />
    </svg>
  );
}

function EmailButton({ question, answer, enabled }) {
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState(() => {
    try {
      return localStorage.getItem("oa_email") || "";
    } catch {
      return "";
    }
  });
  const [status, setStatus] = useState(null); // null | "sending" | "sent" | error text

  if (!enabled) return null;

  if (status === "sent") {
    return (
      <div className="email-row done">
        <GmailIcon /> Emailed to {email}
      </div>
    );
  }

  async function submit(e) {
    e.preventDefault();
    const to = email.trim();
    if (!to) return;
    setStatus("sending");
    try {
      const res = await fetch("/api/email", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ to, question, answer }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || `Failed (${res.status})`);
      try {
        localStorage.setItem("oa_email", to);
      } catch {}
      setStatus("sent");
    } catch (err) {
      setStatus(err.message);
    }
  }

  return (
    <div className="email-row">
      {!open ? (
        <button
          className="email-btn"
          onClick={() => {
            setOpen(true);
            setStatus(null);
          }}
        >
          <GmailIcon /> Email this
        </button>
      ) : (
        <form className="email-form" onSubmit={submit}>
          <input
            type="email"
            required
            autoFocus
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <button
            type="submit"
            className="email-send"
            disabled={status === "sending" || !email.trim()}
          >
            {status === "sending" ? "Sending…" : "Send"}
          </button>
          <button
            type="button"
            className="email-cancel"
            onClick={() => {
              setOpen(false);
              setStatus(null);
            }}
          >
            Cancel
          </button>
          {status && status !== "sending" && (
            <span className="email-err">{status}</span>
          )}
        </form>
      )}
    </div>
  );
}

function Message({ m, question, emailEnabled }) {
  if (m.role === "user") {
    return (
      <div className="row user">
        <div className="bubble user">{m.content}</div>
      </div>
    );
  }
  return (
    <div className="row agent">
      <div className="avatar">
        <Logo />
      </div>
      <div className="agent-col">
        {m.steps?.length > 0 && (
          <div className="steps">
            {m.steps.map((s, i) => (
              <ToolStep step={s} key={i} />
            ))}
          </div>
        )}
        <div className="bubble agent">
          <Markdown text={m.content} />
        </div>
        {m.content && (
          <EmailButton
            question={question}
            answer={m.content}
            enabled={emailEnabled}
          />
        )}
      </div>
    </div>
  );
}

export default function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [tools, setTools] = useState([]);
  const [health, setHealth] = useState(null);
  const [error, setError] = useState("");
  const [navOpen, setNavOpen] = useState(false);
  const scroller = useRef(null);
  const ta = useRef(null);

  useEffect(() => {
    fetch("/api/tools")
      .then((r) => r.json())
      .then((d) => setTools(d.tools || []))
      .catch(() => {});
    const ping = () =>
      fetch("/api/health")
        .then((r) => r.json())
        .then(setHealth)
        .catch(() => setHealth({ status: "down" }));
    ping();
    const id = setInterval(ping, 20000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [messages, busy]);

  function autosize() {
    const el = ta.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 180) + "px";
  }

  async function send(text) {
    const content = (text ?? input).trim();
    if (!content || busy) return;
    setError("");
    setInput("");
    requestAnimationFrame(autosize);

    const history = messages.map((m) => ({ role: m.role, content: m.content }));
    const next = [...messages, { role: "user", content }];
    setMessages(next);
    setBusy(true);

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: content, history }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
      setMessages([
        ...next,
        { role: "assistant", content: data.reply, steps: data.steps || [] },
      ]);
    } catch (e) {
      setError(e.message);
      setMessages(next);
    } finally {
      setBusy(false);
    }
  }

  function onKey(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  const online = health?.status === "ok";
  const model = health?.model || "gemini";

  return (
    <div className="app">
      <aside className={`sidebar ${navOpen ? "open" : ""}`}>
        <div className="brand">
          <Logo />
          <div>
            <div className="brand-name">One Agent</div>
            <div className="brand-sub">many tools</div>
          </div>
        </div>

        <p className="blurb">
          One Gemini agent that reads your question and calls the right tool —
          or several — to answer it.
        </p>

        <div className="side-label">
          Tools <span className="count">{tools.length}</span>
        </div>
        <ul className="toollist">
          {tools.map((t) => {
            const m = meta(t.name);
            return (
              <li key={t.name}>
                <span className="ti" style={{ background: m.accent + "22" }}>
                  {m.icon}
                </span>
                <span className="tinfo">
                  <code>{t.name}</code>
                  <span>{t.description}</span>
                </span>
              </li>
            );
          })}
          {tools.length === 0 && (
            <li className="muted">Waiting for the backend on :8000…</li>
          )}
        </ul>

        <div className={`status ${online ? "ok" : "bad"}`}>
          <span className="dot" />
          {online ? (
            <>
              Connected · <code>{model}</code>
            </>
          ) : (
            "Backend offline"
          )}
        </div>
      </aside>

      <div
        className={`scrim ${navOpen ? "show" : ""}`}
        onClick={() => setNavOpen(false)}
      />

      <main className="chat">
        <header className="topbar">
          <button className="hamburger" onClick={() => setNavOpen((v) => !v)}>
            ☰
          </button>
          <div className="topbar-title">
            <Logo />
            <span>One Agent · Many Tools</span>
          </div>
          <div className="topbar-right">
            {messages.length > 0 && (
              <button className="ghost" onClick={() => setMessages([])}>
                Clear
              </button>
            )}
            <span className={`ping ${online ? "ok" : "bad"}`} title={model}>
              <span className="dot" />
              {online ? model : "offline"}
            </span>
          </div>
        </header>

        <div className="messages" ref={scroller}>
          <div className="messages-inner">
            {messages.length === 0 ? (
              <div className="hero">
                <div className="hero-mark">
                  <Logo />
                </div>
                <h1>What can I look up for you?</h1>
                <p>
                  Weather, live stock &amp; crypto prices, currency &amp; unit
                  conversion, math, Wikipedia, web search, world clocks, word
                  definitions and the news — all through one agent.
                </p>
                <div className="cards">
                  {SUGGESTIONS.map((s) => (
                    <button
                      key={s.text}
                      className="card"
                      onClick={() => send(s.text)}
                    >
                      <span className="card-ic">{s.icon}</span>
                      <span>{s.text}</span>
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((m, i) => (
                <Message
                  m={m}
                  key={i}
                  question={messages[i - 1]?.content || ""}
                  emailEnabled={health?.email_enabled}
                />
              ))
            )}

            {busy && (
              <div className="row agent">
                <div className="avatar">
                  <Logo />
                </div>
                <div className="bubble agent thinking">
                  <span />
                  <span />
                  <span />
                </div>
              </div>
            )}
          </div>
        </div>

        {error && (
          <div className="error">
            <b>Error:</b> {error}
          </div>
        )}

        <div className="composer-wrap">
          <form
            className="composer"
            onSubmit={(e) => {
              e.preventDefault();
              send();
            }}
          >
            <textarea
              ref={ta}
              value={input}
              rows={1}
              onChange={(e) => {
                setInput(e.target.value);
                autosize();
              }}
              onKeyDown={onKey}
              placeholder="Ask anything — e.g. “weather in Karachi and the price of BTC in PKR”"
              disabled={busy}
            />
            <button
              type="submit"
              className="send"
              disabled={busy || !input.trim()}
              aria-label="Send"
            >
              <svg viewBox="0 0 24 24" width="18" height="18">
                <path
                  fill="currentColor"
                  d="M3.4 20.4l17.45-7.48a1 1 0 000-1.84L3.4 3.6a1 1 0 00-1.39 1.17L4 11l12 1-12 1-1.98 6.23a1 1 0 001.38 1.17z"
                />
              </svg>
            </button>
          </form>
          <div className="composer-hint">
            Enter to send · Shift+Enter for a new line
          </div>
        </div>
      </main>
    </div>
  );
}
