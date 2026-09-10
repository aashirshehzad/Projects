const ORDER = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']

export default function SummaryBar({
  data,
  pdfBusy,
  onDownloadJson,
  onDownloadSarif,
  onDownloadPdf,
}) {
  const total = data.violations.length
  return (
    <div className="summary">
      <div className="summary-counts">
        <span className="summary-total">
          {total} violation{total === 1 ? '' : 's'}
        </span>
        <span className="summary-sub">
          {data.files_scanned} file{data.files_scanned === 1 ? '' : 's'} scanned
        </span>
        {ORDER.map((s) =>
          data.counts[s] ? (
            <span key={s} className={`badge sev-${s.toLowerCase()}`}>
              {s} {data.counts[s]}
            </span>
          ) : null,
        )}
      </div>
      <div className="summary-actions">
        <button
          type="button"
          className="btn btn-small btn-primary"
          onClick={onDownloadPdf}
          disabled={pdfBusy}
        >
          {pdfBusy ? 'Building PDF…' : 'Download PDF'}
        </button>
        <button type="button" className="btn btn-small" onClick={onDownloadJson}>
          JSON
        </button>
        <button type="button" className="btn btn-small" onClick={onDownloadSarif}>
          SARIF
        </button>
      </div>
    </div>
  )
}
