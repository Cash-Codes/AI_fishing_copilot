/**
 * ResultsPanel.test.tsx — Tests for the recommendation display component.
 *
 * Because ResultsPanel is purely presentational (props in → DOM out),
 * every test follows the same pattern: render with a fixture, query the DOM,
 * make assertions. No mocking needed.
 */

import { render, screen } from "@testing-library/react";

import ResultsPanel from "../ResultsPanel";
import type { RecommendResponse } from "@/lib/api";

// ─── Fixtures ─────────────────────────────────────────────────────────────────

/** A fully-populated result for the happy-path tests. */
const BASE_RESULT: RecommendResponse = {
  input_location: "TR1 1AA",
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

    it("shows the fallback badge when used_fallback is true", () => {
      render(<ResultsPanel result={{ ...BASE_RESULT, used_fallback: true }} />);
      expect(screen.getByText("Template mode")).toBeInTheDocument();
    });

    it("shows a fallback notice when used_fallback is true", () => {
      render(<ResultsPanel result={{ ...BASE_RESULT, used_fallback: true }} />);
      expect(screen.getByRole("note")).toBeInTheDocument();
    });

    it("does not render the fallback badge when used_fallback is false", () => {
      render(<ResultsPanel result={BASE_RESULT} />);
      expect(screen.queryByText("Template mode")).not.toBeInTheDocument();
    });

    it("does not render the fallback notice when used_fallback is false", () => {
      render(<ResultsPanel result={BASE_RESULT} />);
      expect(screen.queryByRole("note")).not.toBeInTheDocument();
    });
  });

  describe("confidence gauge", () => {
    it("uses the teal accent colour for a high score (≥75%)", () => {
      render(<ResultsPanel result={{ ...BASE_RESULT, confidence_score: 0.9 }} />);
      const value = screen.getByText("90%");
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

    it("renders a meter element for the gauge", () => {
      render(<ResultsPanel result={BASE_RESULT} />);
      const meter = screen.getByRole("meter");
      expect(meter).toHaveAttribute("aria-valuenow", "82");
    });
  });

  describe("AI explanation", () => {
    it("renders the explanation text", () => {
      render(<ResultsPanel result={BASE_RESULT} />);
      expect(screen.getByText("Tidal flow peaks Saturday morning.")).toBeInTheDocument();
    });

    it("labels the explanation as AI when used_fallback is false", () => {
      render(<ResultsPanel result={BASE_RESULT} />);
      expect(screen.getByText("AI recommendation")).toBeInTheDocument();
    });

    it("labels the explanation as template when used_fallback is true", () => {
      render(<ResultsPanel result={{ ...BASE_RESULT, used_fallback: true }} />);
      expect(screen.getByText("Template recommendation")).toBeInTheDocument();
    });
  });

  describe("retrieved notes", () => {
    it("renders each note", () => {
      render(<ResultsPanel result={BASE_RESULT} />);
      expect(screen.getByText("Spring tide Saturday.")).toBeInTheDocument();
      expect(screen.getByText("SW wind 12 knots.")).toBeInTheDocument();
    });

    it("renders the correct number of notes", () => {
      render(<ResultsPanel result={BASE_RESULT} />);
      // Count the note index markers — one per note card (#1, #2, …)
      expect(screen.getByText("#1")).toBeInTheDocument();
      expect(screen.getByText("#2")).toBeInTheDocument();
    });

    it("shows the note count in the section header", () => {
      render(<ResultsPanel result={BASE_RESULT} />);
      expect(screen.getByText(/2 relevant notes/)).toBeInTheDocument();
    });

    it("hides the notes section when retrieved_notes is empty", () => {
      render(<ResultsPanel result={{ ...BASE_RESULT, retrieved_notes: [] }} />);
      expect(screen.queryByText(/Knowledge base/)).not.toBeInTheDocument();
    });
  });

  describe("conditions strip", () => {
    it("renders wind conditions when present", () => {
      render(
        <ResultsPanel
          result={{
            ...BASE_RESULT,
            wind_description: "Moderate breeze",
            wind_speed_knots: 14,
            wind_direction: "SW",
          }}
        />
      );
      expect(screen.getByLabelText("Current conditions")).toBeInTheDocument();
    });

    it("does not render the conditions strip when no conditions are present", () => {
      render(<ResultsPanel result={BASE_RESULT} />);
      expect(screen.queryByLabelText("Current conditions")).not.toBeInTheDocument();
    });
  });
});
