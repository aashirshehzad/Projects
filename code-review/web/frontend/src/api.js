export async function postAudit(file, useLlm) {
  const form = new FormData()
  form.append('file', file)
  form.append('llm', useLlm ? 'true' : 'false')

  const res = await fetch('/api/audit', { method: 'POST', body: form })
  if (!res.ok) {
    let detail = `Request failed (${res.status})`
    try {
      const body = await res.json()
      if (body && body.detail) detail = body.detail
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail)
  }
  return res.json()
}
