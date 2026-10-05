// The AFAQ mark: a horizon line (آفاق, "horizons") with the arc of the sun above it, in gold.
// The line takes the text colour, so the mark works on paper and in dark mode.
export function Mark({ size = 34 }: { size?: number }) {
  return (
    <svg className="mark-logo" width={size} height={size} viewBox="0 0 64 64" fill="none" aria-hidden="true">
      <path d="M14 42a18 18 0 0 1 36 0" stroke="var(--gold)" strokeWidth="5" strokeLinecap="round" />
      <path d="M6 42h52" stroke="currentColor" strokeWidth="5" strokeLinecap="round" />
    </svg>
  );
}

/** Mark and wordmark; `large` adds the Latin name under it, for the home page. */
export default function Logo({ large = false }: { large?: boolean }) {
  return (
    <span className={`logo${large ? " logo-large" : ""}`}>
      <Mark size={large ? 76 : 34} />
      <span className="logo-words">
        <span className="logo-ar">آفاق</span>
        {large && <span className="logo-en" dir="ltr">AFAQ</span>}
      </span>
    </span>
  );
}
