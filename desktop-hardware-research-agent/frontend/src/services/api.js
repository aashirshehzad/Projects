const API_BASE = import.meta.env.VITE_API_BASE || "/api";

export async function fetchThreads() {
  const res = await fetch(`${API_BASE}/chat/threads`);
  if (!res.ok) throw new Error("Failed to fetch threads");
  return res.json();
}

export async function fetchHistory(threadId) {
  const res = await fetch(`${API_BASE}/chat/history/${threadId}`);
  if (!res.ok) throw new Error("Failed to fetch thread history");
  return res.json();
}

export async function deleteThread(threadId) {
  const res = await fetch(`${API_BASE}/chat/threads/${threadId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("Failed to delete thread");
  return res.json();
}

export async function streamChat({ threadId, query, budget, useCase, resolution, onStatus, onToken, onDone, onError }) {
  try {
    const response = await fetch(`${API_BASE}/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        thread_id: threadId,
        query,
        budget: String(budget),
        use_case: useCase,
        resolution,
      }),
    });

    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const rawData = line.slice(6).trim();
          if (!rawData) continue;
          try {
            const data = JSON.parse(rawData);
            if (data.type === "status" && onStatus) onStatus(data);
            if (data.type === "token" && onToken) {
              let text = data.content;
              if (typeof text !== "string") {
                if (Array.isArray(text)) {
                  text = text.map((item) => (typeof item === "string" ? item : item?.text || "")).join("");
                } else if (text && typeof text === "object") {
                  text = text.text || "";
                } else {
                  text = String(text ?? "");
                }
              }
              onToken(text);
            }
            if (data.type === "done" && onDone) onDone();
          } catch (err) {
            console.error("Error parsing SSE JSON:", err, rawData);
          }
        }
      }
    }
  } catch (err) {
    if (onError) onError(err);
  }
}
