// FishingForm.tsx — The search form users fill in.
// "use client" is required because we use React state (useState) and
// event handlers — these only work in the browser, not on the server.
"use client";

import { useState, FormEvent } from "react";
import { getFishingRecommendation, type FishingRequest, type FishingResult } from "@/lib/api";
import ResultsPanel from "./ResultsPanel";

// ─── Component ────────────────────────────────────────────────────────────────
export default function FishingForm() {
  // Local state for each form field
  const [postcode, setPostcode] = useState("");
  const [species, setSpecies] = useState("");
  const [preference, setPreference] = useState<FishingRequest["preference"]>("best-chance");

  // State for the API response (null = not yet fetched)
  const [result, setResult] = useState<FishingResult | null>(null);

  // Loading and error states to give the user feedback
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // handleSubmit runs when the user clicks "Find Fishing Spots"
  async function handleSubmit(e: FormEvent) {
    // Prevent the browser from reloading the page (default form behaviour)
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      // Call our placeholder API helper (see lib/api.ts)
      const data = await getFishingRecommendation({ postcode, species, preference });
      setResult(data);
    } catch (err: unknown) {
      // Show a friendly error message if the request fails
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      // Always turn off the loading spinner
      setLoading(false);
    }
  }

  return (
    <div className="w-full">
      {/* ── Form ──────────────────────────────────────────────────────────── */}
      <form onSubmit={handleSubmit} className="space-y-5">
        {/* Postcode */}
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
            onChange={(e) => setPostcode(e.target.value.toUpperCase())}
            className="field-input"
          />
        </div>

        {/* Species (optional) */}
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

        {/* Preference dropdown */}
        <div className="field-group">
          <label htmlFor="preference" className="field-label">
            <span className="label-tag">03</span> I&apos;d prefer…
          </label>
          <select
            id="preference"
            value={preference}
            onChange={(e) => setPreference(e.target.value as FishingRequest["preference"])}
            className="field-input"
          >
            {/* Each option represents a different optimisation strategy */}
            <option value="closest">Closest harbour to me</option>
            <option value="best-chance">Best chance of a catch</option>
            <option value="calmer-conditions">Calmer sea conditions</option>
          </select>
        </div>

        {/* Submit button */}
        <button type="submit" disabled={loading} className="submit-btn">
          {/* Show a spinner while waiting for the API response */}
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
        <div className="mt-6 error-box">
          <span className="error-icon">⚠</span> {error}
        </div>
      )}

      {/* ── Results panel — only shown once we have a result ──────────────── */}
      {result && <ResultsPanel result={result} />}
    </div>
  );
}

// Small inline spinner — a simple rotating border trick using Tailwind
function Spinner() {
  return (
    <span
      className="inline-block w-4 h-4 border-2 rounded-full animate-spin"
      style={{
        borderColor: "var(--accent)",
        borderTopColor: "transparent",
      }}
      aria-hidden="true"
    />
  );
}
