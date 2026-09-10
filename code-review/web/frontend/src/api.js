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

export async function fetchReportPdf(payload) {
  const res = await fetch('/api/report.pdf', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw new Error(`Could not build PDF (${res.status})`)
  return res.blob()
}
