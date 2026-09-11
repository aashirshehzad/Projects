// JSX-specific trigger for JS-002.
export function Comment({ html }) {
  return <div dangerouslySetInnerHTML={{ __html: html }} />;   // JS-002
}
