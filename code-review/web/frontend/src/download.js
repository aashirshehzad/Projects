export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export function downloadJson(obj, filename) {
  downloadBlob(
    new Blob([JSON.stringify(obj, null, 2)], { type: 'application/json' }),
    filename,
  )
}
