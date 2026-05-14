export function Field({ label, children }) {
  return (
    <label className="image-tool-field">
      <span>{label}</span>
      {children}
    </label>
  )
}
