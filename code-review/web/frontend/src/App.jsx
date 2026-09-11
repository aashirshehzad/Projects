import { useCallback, useMemo, useState } from 'react'
import UploadPanel from './components/UploadPanel.jsx'
import SummaryBar from './components/SummaryBar.jsx'
import FindingCard from './components/FindingCard.jsx'
import { postAudit, fetchReportPdf } from './api.js'
import { downloadJson, downloadBlob } from './download.js'

export default function App() {
  const [status, setStatus] = useState('idle') // idle | loading | done | error
  const [error, setError] = useState(null)
  const [data, setData] = useState(null)
  const [projectLabel, setProjectLabel] = useState('Uploaded project')
  const [pdfBusy, setPdfBusy] = useState(false)

  const runAudit = useCallback(async (file, useLlm) => {
    setStatus('loading')
    setError(null)
    setData(null)
    setProjectLabel(file?.name || 'Uploaded project')
    try {
      const result = await postAudit(file, useLlm)
      setData(result)
      setStatus('done')
    } catch (e) {
      setError(e.message)
      setStatus('error')
    }
  }, [])

  const downloadPdf = useCallback(async () => {
    if (!data) return
    setPdfBusy(true)
    try {
      const blob = await fetchReportPdf({ ...data, project_label: projectLabel })
      downloadBlob(blob, 'audit-report.pdf')
    } catch (e) {
      setError(e.message)
    } finally {
      setPdfBusy(false)
    }
  }, [data, projectLabel])

  const remediationByKey = useMemo(() => {
    const map = {}
    for (const r of data?.report?.remediations ?? []) {
      map[`${r.rule_id}|${r.file_path}|${r.line_number}`] = r
    }
    return map
  }, [data])

  return (
    <div className="app">
      <header className="app-header">
        <h1>Hybrid Code Auditor</h1>
        <p>
          Upload a <code>.zip</code> of a Python project — <code>.py</code> and{" "}
          <code>.ipynb</code> files. It is parsed locally with
          <code> ast</code> — never executed — then checked against rules SEC-001…SEC-010.
          Optionally, Gemini triages each finding and drafts a patch.
        </p>
      </header>

      <UploadPanel disabled={status === 'loading'} onSubmit={runAudit} />

      {status === 'loading' && <div className="notice">Scanning…</div>}
      {status === 'error' && <div className="notice notice-error">{error}</div>}

      {status === 'done' && data && (
        <section className="results">
          <SummaryBar
            data={data}
            pdfBusy={pdfBusy}
            onDownloadJson={() => downloadJson(data.report ?? data, 'audit-report.json')}
            onDownloadSarif={() => downloadJson(data.sarif, 'audit-results.sarif')}
            onDownloadPdf={downloadPdf}
          />

          {data.llm_error && (
            <div className="notice notice-warn">
              AI remediation failed: {data.llm_error} — showing static findings only.
            </div>
          )}

          {data.violations.length === 0 ? (
            <div className="notice notice-ok">No violations found.</div>
          ) : (
            data.violations.map((v, i) => (
              <FindingCard
                key={`${v.file_path}:${v.line_number}:${v.rule_id}:${i}`}
                violation={v}
                remediation={
                  remediationByKey[`${v.rule_id}|${v.file_path}|${v.line_number}`]
                }
              />
            ))
          )}
        </section>
      )}

      <footer className="app-footer">
        Local only · Stage 3 provider is read from <code>.env</code>
      </footer>
    </div>
  )
}
