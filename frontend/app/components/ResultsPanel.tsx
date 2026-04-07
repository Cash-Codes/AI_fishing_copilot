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
  const confidencePercent = Math.round(result.confidence_score * 100);
  const confidenceColor = confidenceAccentColor(result.confidence_score);
  const hasConditions =
    result.wind_description || result.sea_state || result.tide_phase || result.spring_or_neap;

  return (
    <div className="results-panel" data-testid="results-panel">
      {/* ── Header row ──────────────────────────────────────────────────── */}
      <div className="results-header">
        <span className="results-tag">RECOMMENDATION</span>
        {result.used_fallback && <span className="fallback-badge">Template mode</span>}
      </div>

      {/* ── Fallback notice ───────────────────────────────────────────── */}
      {result.used_fallback && (
        <div className="fallback-notice" role="note">
          <span className="fallback-icon">◈</span>
          <span className="fallback-text">
            {result.out_of_range ? (
              "Location outside coverage area — this service covers UK coastal sea fishing."
            ) : (
              <>
                AI explanation unavailable — showing a template recommendation. Set{" "}
                <code>GOOGLE_CLOUD_PROJECT</code> and <code>ENABLE_VERTEX_AI=true</code> to enable
                full AI output.
              </>
            )}
          </span>
        </div>
      )}

      {/* ── Stat cards — 2-column grid ────────────────────────────────── */}
      <div className="results-grid">
        <ResultCard index="A" label="Nearest Harbour" value={result.nearest_harbour} />
        <ResultCard index="B" label="Best Window" value={result.recommendation_window} />
      </div>

      {/* ── Confidence gauge ──────────────────────────────────────────── */}
      <div className="confidence-section">
        <div className="confidence-header">
          <span className="confidence-label">Confidence score</span>
          <span className="confidence-value" style={{ color: confidenceColor }}>
            {confidencePercent}%
          </span>
        </div>
        <div
          className="gauge-track"
          role="meter"
          aria-valuenow={confidencePercent}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <div
            className="gauge-fill"
            style={{
              width: `${confidencePercent}%`,
              background: confidenceGradient(result.confidence_score),
            }}
          />
        </div>
      </div>

      {/* ── Conditions strip ──────────────────────────────────────────── */}
      {hasConditions && (
        <div className="conditions-strip" aria-label="Current conditions">
          {result.wind_description && result.wind_direction && (
            <div className="condition-chip">
              <span className="chip-label">Wind</span>
              <span className="chip-value">
                {result.wind_description}
                {result.wind_speed_knots !== undefined
                  ? ` · ${Math.round(result.wind_speed_knots)} kn`
                  : ""}
                {result.wind_direction ? ` ${result.wind_direction}` : ""}
              </span>
            </div>
          )}
          {result.sea_state && (
            <div className="condition-chip">
              <span className="chip-label">Sea state</span>
              <span className="chip-value">{result.sea_state}</span>
            </div>
          )}
          {result.tide_phase && (
            <div className="condition-chip">
              <span className="chip-label">Tide</span>
              <span className="chip-value chip-value--accent">{result.tide_phase}</span>
            </div>
          )}
          {result.spring_or_neap && (
            <div className="condition-chip">
              <span className="chip-label">Type</span>
              <span className="chip-value">{result.spring_or_neap}</span>
            </div>
          )}
        </div>
      )}

      {/* ── AI explanation ────────────────────────────────────────────── */}
      <div className="explanation-box">
        <span className="explanation-label">
          {result.used_fallback ? "Template recommendation" : "AI recommendation"}
        </span>
        <p className="explanation-text">{result.explanation}</p>
      </div>

      {/* ── Retrieved notes ───────────────────────────────────────────── */}
      {result.retrieved_notes.length > 0 && (
        <div className="notes-section">
          <span className="notes-header">
            Knowledge base · {result.retrieved_notes.length} relevant notes
          </span>
          {result.retrieved_notes.map((note, i) => (
            <div key={i} className="note-card">
              <span className="note-index">#{i + 1}</span>
              <p className="note-text">{note}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function ResultCard({ index, label, value }: { index: string; label: string; value: string }) {
  return (
    <div className="result-card">
      <span className="card-index">{index}</span>
      <p className="card-label">{label}</p>
      <p className="card-value">{value}</p>
    </div>
  );
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

/** Text colour for the confidence number — traffic-light heuristic. */
function confidenceAccentColor(score: number): string {
  if (score >= 0.75) return "var(--accent)";
  if (score >= 0.4) return "var(--amber)";
  return "#ef4444";
}

/**
 * Gauge fill gradient.
 * Low scores fill with red; high scores fill with teal.
 * A continuous gradient avoids a jarring colour jump at thresholds.
 */
function confidenceGradient(score: number): string {
  if (score >= 0.75) return "linear-gradient(90deg, rgba(45,212,191,0.6) 0%, var(--accent) 100%)";
  if (score >= 0.4) return "linear-gradient(90deg, rgba(239,68,68,0.5) 0%, var(--amber) 100%)";
  return "linear-gradient(90deg, rgba(239,68,68,0.4) 0%, #ef4444 100%)";
}
