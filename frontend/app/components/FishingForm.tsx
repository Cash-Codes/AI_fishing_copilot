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
  const [postcode, setPostcode] = useState("");
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

  // Cancel any in-flight request when the component unmounts (e.g. page change).
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

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
          postcode,
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
        setError("Invalid postcode or input. Please check and try again.");
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

  return (
    <div className="w-full">
      {/* preventDefault handled inline; handleSubmit stays event-free */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void handleSubmit();
        }}
        className="space-y-5"
      >
        {/* ── Postcode ──────────────────────────────────────────────────── */}
        <div className="field-group">
          <label htmlFor="postcode" className="field-label">
            <span className="label-tag">01</span> Postcode
          </label>
          <input
            id="postcode"
            type="text"
            required
            placeholder="e.g. TR1 1AA"
            value={postcode}
            // toUpperCase keeps the value consistent with UK postcode format.
            onChange={(e) => setPostcode(e.target.value.toUpperCase())}
            className="field-input"
          />
        </div>

        {/* ── Species (optional) ────────────────────────────────────────── */}
        <div className="field-group">
          <label htmlFor="species" className="field-label">
            <span className="label-tag">02</span> Target species
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

        {/* ── Preference ────────────────────────────────────────────────── */}
        <div className="field-group">
          <label htmlFor="preference" className="field-label">
            <span className="label-tag">03</span> I&apos;d prefer…
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

        {/* ── Submit ────────────────────────────────────────────────────── */}
        <button type="submit" disabled={loading} className="submit-btn">
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

      {/* ── Error message ─────────────────────────────────────────────────── */}
      {error && (
        <div role="alert" className="mt-6 error-box">
          <span className="error-icon">⚠</span> {error}
        </div>
      )}

      {/* ── Results ───────────────────────────────────────────────────────── */}
      {result && <ResultsPanel result={result} />}
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
