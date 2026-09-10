import { useRef, useState } from 'react'

export default function UploadPanel({ disabled, onSubmit }) {
  const [file, setFile] = useState(null)
  const [useLlm, setUseLlm] = useState(false)
  const [dragOver, setDragOver] = useState(false)
  const [hint, setHint] = useState(null)
  const inputRef = useRef(null)

  const pick = (f) => {
    if (!f) return
    if (!f.name.toLowerCase().endsWith('.zip')) {
      setHint('That is not a .zip file.')
      return
    }
    setHint(null)
    setFile(f)
  }

  return (
    <div
      className={`upload${dragOver ? ' upload-dragover' : ''}`}
      onDragOver={(e) => {
        e.preventDefault()
        setDragOver(true)
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault()
        setDragOver(false)
        pick(e.dataTransfer.files[0])
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".zip,application/zip,application/x-zip-compressed"
        hidden
        onChange={(e) => pick(e.target.files[0])}
      />

      <div className="upload-row">
        <button
          type="button"
          className="btn"
          onClick={() => inputRef.current?.click()}
          disabled={disabled}
        >
          Choose .zip
        </button>
        <span className="upload-filename">
          {file ? file.name : 'or drop a project archive here'}
        </span>
      </div>

      <label className="upload-toggle">
        <input
          type="checkbox"
          checked={useLlm}
          disabled={disabled}
          onChange={(e) => setUseLlm(e.target.checked)}
        />
        AI remediation (Gemini) — makes one API call, costs a few cents
      </label>

      <button
        type="button"
        className="btn btn-primary"
        disabled={disabled || !file}
        onClick={() => onSubmit(file, useLlm)}
      >
        {disabled ? 'Scanning…' : 'Audit'}
      </button>

      {hint && <p className="upload-hint">{hint}</p>}
    </div>
  )
}
