"use client";
/**
 * FishingForm.tsx — Controlled form that drives the recommendation flow.
 *
 * "use client" is required because we use React state and event handlers,
 * which only run in the browser (not during server-side rendering).
 *
 * Key patterns used here:
 * - Controlled inputs: React owns every field value via useState, which makes
 *   the form easy to test and reset.
 * - AbortController: cancels any in-flight request when the user submits
 *   again or when the component unmounts. Without this the app can show stale
 *   results from a previous (slower) request that resolves after a newer one.
 * - Error discrimination: ApiError vs generic Error lets us show different
 *   messages for "the server rejected your input" vs "network is down".
 */

import { useEffect, useRef, useState } from "react";

import { ApiError, recommend, type RecommendRequest, type RecommendResponse } from "@/lib/api";
import ResultsPanel from "./ResultsPanel";

export default function FishingForm() {
  // ── Form field state ───────────────────────────────────────────────────────
  const [location, setLocation] = useState("");
  const [species, setSpecies] = useState("");
  const [preference, setPreference] = useState<RecommendRequest["preference"]>("best-chance");

  // ── Request state ──────────────────────────────────────────────────────────
  const [result, setResult] = useState<RecommendResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /**
   * Holds the AbortController for the current in-flight request.
   * useRef (not useState) because changing it must not trigger a re-render.
   */
  const abortRef = useRef<AbortController | null>(null);

  /**
   * Ref for the results column — used to scroll into view on mobile when
   * results arrive (on desktop the split layout means no scroll is needed).
   */
  const resultsRef = useRef<HTMLDivElement>(null);

  // Cancel any in-flight request when the component unmounts (e.g. page change).
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  // Scroll results into view on mobile once they arrive.
  useEffect(() => {
    if (result && resultsRef.current && window.innerWidth < 768) {
      // Small delay so the animation has started before scroll begins.
      const id = setTimeout(() => {
        resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 80);
      return () => clearTimeout(id);
    }
  }, [result]);

  // Separated from the DOM onSubmit so this function has no dependency on
  // SyntheticEvent — it's pure business logic and trivial to call in tests.
  async function handleSubmit() {
    // Cancel the previous request if the user re-submits before it resolves.
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const data = await recommend(
        {
          location,
          // Only include species in the payload when the user typed something —
          // the backend treats undefined as "no species preference".
          species: species.trim() || undefined,
          preference,
        },
        controller.signal
      );
      setResult(data);
    } catch (err: unknown) {
      // Ignore AbortError — it's intentional (user re-submitted or navigated away).
      if (err instanceof DOMException && err.name === "AbortError") return;

      if (err instanceof ApiError && err.status === 422) {
        // 422 means the backend rejected our input — show a friendlier message.
        setError("Invalid location or input. Please check and try again.");
      } else if (err instanceof ApiError) {
        setError(`Server error (${err.status}). Please try again in a moment.`);
      } else {
        // Network failure, DNS error, etc.
        setError("Could not reach the server. Check your connection and try again.");
      }
    } finally {
      setLoading(false);
    }
  }

  const hasOutput = loading || !!result;

  return (
    <div className={`form-results-wrapper${hasOutput ? " has-output" : ""}`}>
      {/* ── LEFT COLUMN: Form ─────────────────────────────────────────────── */}
      <div className="form-section">
        {/* preventDefault handled inline; handleSubmit stays event-free */}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void handleSubmit();
          }}
          className="form-stack"
        >
          {/* ── Location ────────────────────────────────────────────────── */}
          <div className="field-group">
            <label htmlFor="location" className="field-label">
              Location
            </label>
            <input
              id="location"
              type="text"
              required
              placeholder="Postcode or city — e.g. TR1 1AA, Falmouth, New York"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              className="field-input"
            />
          </div>

          {/* ── Species (optional) ──────────────────────────────────────── */}
          <div className="field-group">
            <label htmlFor="species" className="field-label">
              Target species
              <span className="optional-badge">optional</span>
            </label>
            <input
              id="species"
              type="text"
              placeholder="e.g. Bass, Mackerel, Pollock"
              value={species}
              onChange={(e) => setSpecies(e.target.value)}
              className="field-input"
            />
          </div>

          {/* ── Preference ──────────────────────────────────────────────── */}
          <div className="field-group">
            <label htmlFor="preference" className="field-label">
              I&apos;d prefer…
            </label>
            <select
              id="preference"
              value={preference}
              onChange={(e) => setPreference(e.target.value as RecommendRequest["preference"])}
              className="field-input"
            >
              <option value="closest">Closest harbour to me</option>
              <option value="best-chance">Best chance of a catch</option>
              <option value="calmer-conditions">Calmer sea conditions</option>
            </select>
          </div>

          {/* ── Submit ──────────────────────────────────────────────────── */}
          <button
            type="submit"
            disabled={loading}
            className={`submit-btn${loading ? " submit-btn--loading" : ""}`}
          >
            {loading ? (
              <span className="flex items-center gap-2">
                <Spinner />
                Scanning conditions…
              </span>
            ) : (
              "Find Fishing Spots →"
            )}
          </button>
        </form>

        {/* ── Error message ─────────────────────────────────────────────── */}
        {error && (
          <div role="alert" className="mt-6 error-box">
            <span className="error-icon">⚠</span> {error}
          </div>
        )}
      </div>

      {/* ── RIGHT COLUMN: Results / Loading / Empty state ─────────────────── */}
      <div className="results-section" ref={resultsRef}>
        {/* Loading skeleton */}
        {loading && <LoadingSkeleton />}

        {/* Results */}
        {!loading && result && <ResultsPanel result={result} />}

        {/* Desktop empty state — hidden on mobile, shown when no output yet */}
        {!hasOutput && <EmptyState />}
      </div>
    </div>
  );
}

/** Placeholder shown in the right column on desktop before any search. */
function EmptyState() {
  return (
    <div className="empty-state" aria-hidden="true">
      <div className="empty-state-sonar">
        <span className="sonar-ring sonar-ring--1" />
        <span className="sonar-ring sonar-ring--2" />
        <span className="sonar-ring sonar-ring--3" />
        <span className="sonar-dot" />
      </div>
      <p className="empty-state-label">Cast your line</p>
      <p className="empty-state-hint">Enter a location to get your fishing report</p>
    </div>
  );
}

/** Skeleton placeholder shown in the results area while a request is in flight. */
function LoadingSkeleton() {
  return (
    <div className="loading-state" aria-busy="true" aria-label="Loading recommendation">
      <span className="loading-label">Scanning conditions</span>
      <div className="skeleton-grid">
        <div className="skeleton-card skeleton-bar" />
        <div className="skeleton-card skeleton-bar" />
      </div>
      <div className="skeleton-wide skeleton-bar" />
      <div className="skeleton-narrow skeleton-bar" />
      <div className="skeleton-block skeleton-bar" />
    </div>
  );
}

/** Animated border-spin indicator. CSS-only — no JS timer needed. */
function Spinner() {
  return (
    <span
      role="status"
      aria-label="Loading"
      className="inline-block w-4 h-4 border-2 rounded-full animate-spin"
      style={{ borderColor: "var(--accent)", borderTopColor: "transparent" }}
    />
  );
}
