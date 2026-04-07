// ResultsPanel.tsx — Displays the recommendation returned by the backend.
// This is a plain presentational component: it receives data and renders it.
// No state or browser APIs needed, so no "use client" directive required.

import type { FishingResult } from "@/lib/api";

// ─── Props ────────────────────────────────────────────────────────────────────
interface Props {
  result: FishingResult;
}

// ─── Component ────────────────────────────────────────────────────────────────
export default function ResultsPanel({ result }: Props) {
  return (
    // Outer wrapper with animated fade-in
    <div className="results-panel">
      {/* Section header */}
      <div className="results-header">
        <span className="results-tag">RECOMMENDATION</span>
        {/* Amber badge when fallback mode is active */}
        {result.fallback_used && <span className="fallback-badge">Fallback mode</span>}
      </div>

      {/* ── Grid of result cards ─────────────────────────────────────────── */}
      <div className="results-grid">
        {/* Nearest harbour */}
        <ResultCard index="A" label="Nearest Harbour" value={result.nearest_harbour ?? "—"} />

        {/* Recommended time window */}
        <ResultCard
          index="B"
          label="Recommended Window"
          value={result.recommendation_window ?? "—"}
        />

        {/* AI confidence score — formatted as a percentage */}
        <ResultCard
          index="C"
          label="Confidence Score"
          value={
            result.confidence_score !== undefined
              ? `${Math.round(result.confidence_score * 100)}%`
              : "—"
          }
          accent={getConfidenceAccent(result.confidence_score)}
        />

        {/* Whether the result came from fallback logic instead of live AI */}
        <ResultCard
          index="D"
          label="Fallback Mode"
          value={result.fallback_used ? "Yes — limited data" : "No"}
        />
      </div>

      {/* ── Explanation — full-width narrative from the AI ────────────────── */}
      {result.explanation && (
        <div className="explanation-box">
          <span className="explanation-label">AI EXPLANATION</span>
          <p className="explanation-text">{result.explanation}</p>
        </div>
      )}
    </div>
  );
}

// ─── Sub-component: a single result card ──────────────────────────────────────
function ResultCard({
  index,
  label,
  value,
  accent,
}: {
  index: string;
  label: string;
  value: string;
  accent?: string;
}) {
  return (
    <div className="result-card">
      {/* Small letter index in the corner — mimics chart notation */}
      <span className="card-index">{index}</span>
      <p className="card-label">{label}</p>
      <p className="card-value" style={accent ? { color: accent } : undefined}>
        {value}
      </p>
    </div>
  );
}

// ─── Helper: colour-code the confidence score ──────────────────────────────
function getConfidenceAccent(score?: number): string | undefined {
  if (score === undefined) return undefined;
  if (score >= 0.75) return "var(--accent)"; // high — teal
  if (score >= 0.4) return "var(--amber)"; // medium — amber
  return "#ef4444"; // low — red
}
