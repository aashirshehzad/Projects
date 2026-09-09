import { useEffect, useRef, useState } from "react";

const SUGGESTIONS = [
  "What's the weather in Lahore right now?",
  "Price of TSLA and how it changed today",
  "Convert 120 USD to PKR",
  "sqrt(2) * 45 + 17^2",
  "Give me a 2-line summary of the Eiffel Tower",
  "What time is it in Tokyo?",
  "Define 'serendipity'",
  "Latest news about electric vehicles",
];

export default function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [tools, setTools] = useState([]);
  const [error, setError] = useState("");
  const scroller = useRef(null);

  useEffect(() => {
    fetch("/api/tools")
      .then((r) => r.json())
      .then((d) => setTools(d.tools || []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    scroller.current?.scrollTo(0, scroller.current.scrollHeight);
  }, [messages, busy]);

  async function send(text) {
    const content = (text ?? input).trim();
    if (!content || busy) return;
    setError("");
    setInput("");

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
      if (!res.ok) throw new Error(data.detail || "Request failed");
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

  return (
    <div className="app">
      <aside className="sidebar">
        <h1>
          One Agent<br />
          <span>· many tools</span>
        </h1>
        <p className="blurb">
          A single Gemini-powered agent that decides which tool to call for each
          question.
        </p>
        <h2>Tools it can use</h2>
        <ul className="toollist">
          {tools.map((t) => (
            <li key={t.name}>
              <code>{t.name}</code>
              <span>{t.description}</span>
            </li>
          ))}
          {tools.length === 0 && <li className="muted">Start the backend to load tools…</li>}
        </ul>
      </aside>

      <main className="chat">
        <div className="messages" ref={scroller}>
          {messages.length === 0 && (
            <div className="empty">
              <p>Ask me something. Try:</p>
              <div className="chips">
                {SUGGESTIONS.map((s) => (
                  <button key={s} onClick={() => send(s)}>
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m, i) => (
            <div key={i} className={`msg ${m.role}`}>
              <div className="role">{m.role === "user" ? "You" : "Agent"}</div>
              {m.steps?.length > 0 && (
                <div className="steps">
                  {m.steps.map((s, j) => (
                    <details key={j}>
                      <summary>
                        🔧 {s.tool}
                        <span className="args">({fmtArgs(s.args)})</span>
                      </summary>
                      <pre>{JSON.stringify(s.result, null, 2)}</pre>
                    </details>
                  ))}
                </div>
              )}
              <div className="bubble">{m.content}</div>
            </div>
          ))}

          {busy && (
            <div className="msg assistant">
              <div className="role">Agent</div>
              <div className="bubble typing">thinking…</div>
            </div>
          )}
        </div>

        {error && <div className="error">{error}</div>}

        <form
          className="composer"
          onSubmit={(e) => {
            e.preventDefault();
            send();
          }}
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about weather, stocks, math, time, news…"
            disabled={busy}
          />
          <button type="submit" disabled={busy || !input.trim()}>
            Send
          </button>
        </form>
      </main>
    </div>
  );
}

function fmtArgs(args) {
  return Object.entries(args || {})
    .map(([k, v]) => `${k}: ${v}`)
    .join(", ");
}
