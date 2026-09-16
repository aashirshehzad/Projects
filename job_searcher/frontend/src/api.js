const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

async function request(path, options = {}) {
  const res = await fetch(`${API_URL}${path}`, {
    credentials: "include",
    headers: options.body instanceof FormData ? {} : { "Content-Type": "application/json" },
    ...options,
  });

  let data = null;
  try {
    data = await res.json();
  } catch {
    // no JSON body
  }

  if (!res.ok) {
    const message = data?.detail || `Request failed (${res.status})`;
    const error = new Error(message);
    error.status = res.status;
    error.data = data;
    throw error;
  }

  return data;
}

export const api = {
  uploadProfileFile: (file) => {
    const form = new FormData();
    form.append("file", file);
    return request("/api/profile", { method: "POST", body: form });
  },
  uploadProfileText: (text) => {
    const form = new FormData();
    form.append("text", text);
    return request("/api/profile", { method: "POST", body: form });
  },
  getProfile: () => request("/api/profile"),

  analyzeJob: (jobText) =>
    request("/api/jobs/analyze", { method: "POST", body: JSON.stringify({ job_text: jobText }) }),
  skipJob: () => request("/api/jobs/skip", { method: "POST" }),
  draftEmail: (force = false) =>
    request("/api/jobs/draft", { method: "POST", body: JSON.stringify({ force }) }),
  getHistory: () => request("/api/jobs/history"),

  gmailStatus: () => request("/api/gmail/status"),
  gmailDisconnect: () => request("/api/gmail/disconnect", { method: "POST" }),
  gmailSaveDraft: () => request("/api/gmail/save-draft", { method: "POST" }),
  gmailAuthorizeUrl: () => `${API_URL}/api/gmail/authorize`,
};
