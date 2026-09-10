export default function FindingCard({ violation: v, remediation: r }) {
  return (
    <article className="finding">
      <div className="finding-head">
        <span className={`badge sev-${v.severity.toLowerCase()}`}>{v.severity}</span>
        <span className="finding-rule">
          {v.rule_id} · {v.title}
        </span>
        {v.tainted && <span className="badge badge-taint">user input</span>}
        <span className="finding-loc">
          {v.file_path}:{v.line_number}
        </span>
      </div>

      <p className="finding-msg">{v.message}</p>

      {v.snippet && (
        <pre className="code">
          <code>{v.snippet}</code>
        </pre>
      )}

      {r && (
        <div className="remediation">
          <span className={`verdict ${r.is_exploitable ? 'verdict-bad' : 'verdict-ok'}`}>
            {r.is_exploitable ? 'Exploitable' : 'Likely false positive'}
          </span>
          {r.root_cause && <p className="remediation-cause">{r.root_cause}</p>}

          {r.is_exploitable && r.patched_code && (
            <>
              <h4>Suggested patch</h4>
              <pre className="code code-patch">
                <code>{r.patched_code}</code>
              </pre>
            </>
          )}

          {r.is_exploitable && r.unit_test && (
            <details className="remediation-test">
              <summary>Regression test</summary>
              <pre className="code">
                <code>{r.unit_test}</code>
              </pre>
            </details>
          )}
        </div>
      )}
    </article>
  )
}
