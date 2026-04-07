/**
 * ResultsPanel.test.tsx — Tests for the recommendation display component.
 *
 * Because ResultsPanel is purely presentational (props in → DOM out),
 * every test follows the same pattern: render with a fixture, query the DOM,
 * make assertions. No mocking needed.
 */

import { render, screen, within } from "@testing-library/react";

import ResultsPanel from "../ResultsPanel";
import type { RecommendResponse } from "@/lib/api";

// ─── Fixtures ─────────────────────────────────────────────────────────────────

/** A fully-populated result for the happy-path tests. */
const BASE_RESULT: RecommendResponse = {
  input_postcode: "TR1 1AA",
  nearest_harbour: "Falmouth Harbour",
  recommendation_window: "Saturday 06:00 – 10:00",
  confidence_score: 0.82,
  explanation: "Tidal flow peaks Saturday morning.",
  used_fallback: false,
  retrieved_notes: ["Spring tide Saturday.", "SW wind 12 knots."],
};

// ─── Tests ────────────────────────────────────────────────────────────────────

describe("ResultsPanel", () => {
  describe("result cards", () => {
    it("renders the nearest harbour", () => {
      render(<ResultsPanel result={BASE_RESULT} />);
      expect(screen.getByText("Falmouth Harbour")).toBeInTheDocument();
    });

    it("renders the recommendation window", () => {
      render(<ResultsPanel result={BASE_RESULT} />);
      expect(screen.getByText("Saturday 06:00 – 10:00")).toBeInTheDocument();
    });

    it("formats confidence_score as a rounded percentage", () => {
      render(<ResultsPanel result={BASE_RESULT} />);
      // 0.82 → "82%"
      expect(screen.getByText("82%")).toBeInTheDocument();
    });

    it("shows 'No' for fallback mode when used_fallback is false", () => {
      render(<ResultsPanel result={BASE_RESULT} />);
      expect(screen.getByText("No")).toBeInTheDocument();
    });

    it("shows 'Yes — limited data' and the fallback badge when used_fallback is true", () => {
      render(<ResultsPanel result={{ ...BASE_RESULT, used_fallback: true }} />);
      expect(screen.getByText("Yes — limited data")).toBeInTheDocument();
      expect(screen.getByText("Fallback mode")).toBeInTheDocument();
    });

    it("does not render the fallback badge when used_fallback is false", () => {
      render(<ResultsPanel result={BASE_RESULT} />);
      expect(screen.queryByText("Fallback mode")).not.toBeInTheDocument();
    });
  });

  describe("confidence accent colour", () => {
    it("uses the teal accent colour for a high score (≥75%)", () => {
      render(<ResultsPanel result={{ ...BASE_RESULT, confidence_score: 0.9 }} />);
      const value = screen.getByText("90%");
      // Inline style is set directly on the element.
      expect(value).toHaveStyle({ color: "var(--accent)" });
    });

    it("uses the amber colour for a medium score (40–74%)", () => {
      render(<ResultsPanel result={{ ...BASE_RESULT, confidence_score: 0.6 }} />);
      expect(screen.getByText("60%")).toHaveStyle({ color: "var(--amber)" });
    });

    it("uses red for a low score (<40%)", () => {
      render(<ResultsPanel result={{ ...BASE_RESULT, confidence_score: 0.2 }} />);
      expect(screen.getByText("20%")).toHaveStyle({ color: "#ef4444" });
    });
  });

  describe("AI explanation", () => {
    it("renders the explanation text", () => {
      render(<ResultsPanel result={BASE_RESULT} />);
      expect(screen.getByText("Tidal flow peaks Saturday morning.")).toBeInTheDocument();
    });
  });

  describe("retrieved notes", () => {
    it("renders each note as a list item", () => {
      render(<ResultsPanel result={BASE_RESULT} />);
      expect(screen.getByText("Spring tide Saturday.")).toBeInTheDocument();
      expect(screen.getByText("SW wind 12 knots.")).toBeInTheDocument();
    });

    it("renders the correct number of notes", () => {
      render(<ResultsPanel result={BASE_RESULT} />);
      // Find the notes list by its label text, then count the list items within it.
      const section = screen.getByText("RETRIEVED NOTES").closest("div")!;
      const items = within(section).getAllByRole("listitem");
      expect(items).toHaveLength(2);
    });

    it("hides the notes section when retrieved_notes is empty", () => {
      render(<ResultsPanel result={{ ...BASE_RESULT, retrieved_notes: [] }} />);
      expect(screen.queryByText("RETRIEVED NOTES")).not.toBeInTheDocument();
    });
  });
});
