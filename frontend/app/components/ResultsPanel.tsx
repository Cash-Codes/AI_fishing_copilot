/**
 * ResultsPanel.tsx — Presentational component that renders a RecommendResponse.
 *
 * Deliberately has no state and no side-effects — it's a pure function of its
 * props. That makes it trivial to test: render it with a fixture, assert output.
 *
 * No "use client" needed — nothing here requires browser APIs or interactivity.
 */

import type { RecommendResponse } from "@/lib/api";

interface Props {
  result: RecommendResponse;
}

export default function ResultsPanel({ result }: Props) {
  return (
    <div className="results-panel">
      {/* ── Header row ──────────────────────────────────────────────────── */}
      <div className="results-header">
        <span className="results-tag">RECOMMENDATION</span>
        {result.used_fallback && <span className="fallback-badge">Fallback mode</span>}
      </div>

      {/* ── Stat cards — 2-column grid ────────────────────────────────── */}
      <div className="results-grid">
        <ResultCard index="A" label="Nearest Harbour" value={result.nearest_harbour} />

        <ResultCard index="B" label="Recommended Window" value={result.recommendation_window} />

        {/* Confidence formatted as a percentage with colour coding */}
        <ResultCard
          index="C"
          label="Confidence Score"
          value={`${Math.round(result.confidence_score * 100)}%`}
          accent={confidenceAccent(result.confidence_score)}
        />

        <ResultCard
          index="D"
          label="Fallback Mode"
          value={result.used_fallback ? "Yes — limited data" : "No"}
        />
      </div>

      {/* ── AI explanation ────────────────────────────────────────────── */}
      <div className="explanation-box">
        <span className="explanation-label">AI EXPLANATION</span>
        <p className="explanation-text">{result.explanation}</p>
      </div>

      {/* ── Retrieved notes ───────────────────────────────────────────── */}
      {/*
       * These are the raw knowledge-base excerpts that informed the AI answer.
       * Showing them gives the user transparency into why the recommendation
       * was made — useful while the system is still in early development.
       */}
      {result.retrieved_notes.length > 0 && (
        <div className="notes-box">
          <span className="notes-label">RETRIEVED NOTES</span>
          <ul className="notes-list">
            {result.retrieved_notes.map((note, i) => (
              <li key={i} className="notes-item">
                {note}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// ─── Sub-components ───────────────────────────────────────────────────────────

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
      <span className="card-index">{index}</span>
      <p className="card-label">{label}</p>
      <p className="card-value" style={accent ? { color: accent } : undefined}>
        {value}
      </p>
    </div>
  );
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

/**
 * Maps a 0–1 confidence score to a CSS colour.
 * Green (≥75%), amber (≥40%), red (<40%) — a traffic-light heuristic.
 */
function confidenceAccent(score: number): string {
  if (score >= 0.75) return "var(--accent)";
  if (score >= 0.4) return "var(--amber)";
  return "#ef4444";
}
