/**
 * FishingForm.test.tsx — Integration tests for the search form.
 *
 * We mock the `recommend` function from lib/api so tests never hit the network.
 * Everything else (React state, DOM events, rendering) is real.
 *
 * userEvent is preferred over fireEvent because it simulates actual browser
 * behaviour (focus, keyboard, pointer events) instead of dispatching raw DOM
 * events — this catches more real-world bugs.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import FishingForm from "../FishingForm";
import { ApiError, type RecommendResponse } from "@/lib/api";

// ─── Mock the API module ───────────────────────────────────────────────────────
// jest.mock() is hoisted to the top of the file before any transforms run,
// so @/ path aliases are not reliably resolved at that point. We use a
// relative path here instead (3 levels up: __tests__ → components → app → lib).
// Regular `import` statements below can still use @/ — only jest.mock() and
// jest.requireActual() need relative paths.

jest.mock("../../../lib/api", () => ({
  ...jest.requireActual("../../../lib/api"),
  recommend: jest.fn(),
}));

// Re-import after mocking so we have a typed handle on the mock.
import { recommend } from "@/lib/api";
const mockRecommend = recommend as jest.MockedFunction<typeof recommend>;

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const MOCK_RESULT: RecommendResponse = {
  input_postcode: "TR1 1AA",
  nearest_harbour: "Falmouth Harbour",
  recommendation_window: "Saturday 06:00 – 10:00",
  confidence_score: 0.82,
  explanation: "Good conditions for Bass.",
  used_fallback: false,
  retrieved_notes: ["Spring tide Saturday."],
};

// ─── Setup ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  mockRecommend.mockReset();
});

// ─── Helpers ──────────────────────────────────────────────────────────────────

/** Fills the postcode field and submits the form. */
async function submitForm(postcode = "TR1 1AA") {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText(/postcode/i), postcode);
  await user.click(screen.getByRole("button", { name: /find fishing spots/i }));
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe("FishingForm", () => {
  describe("rendering", () => {
    it("renders the postcode input", () => {
      render(<FishingForm />);
      expect(screen.getByLabelText(/postcode/i)).toBeInTheDocument();
    });

    it("renders the species input", () => {
      render(<FishingForm />);
      expect(screen.getByLabelText(/target species/i)).toBeInTheDocument();
    });

    it("renders the preference dropdown with three options", () => {
      render(<FishingForm />);
      const select = screen.getByLabelText(/i'd prefer/i);
      expect(select).toBeInTheDocument();
      // Check all three options exist
      expect(screen.getByRole("option", { name: /closest harbour/i })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: /best chance/i })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: /calmer/i })).toBeInTheDocument();
    });

    it("uppercases the postcode as the user types", async () => {
      render(<FishingForm />);
      const user = userEvent.setup();
      await user.type(screen.getByLabelText(/postcode/i), "tr1 1aa");
      expect(screen.getByLabelText(/postcode/i)).toHaveValue("TR1 1AA");
    });
  });

  describe("form submission", () => {
    it("calls recommend() with the entered values", async () => {
      mockRecommend.mockResolvedValue(MOCK_RESULT);
      render(<FishingForm />);
      const user = userEvent.setup();

      await user.type(screen.getByLabelText(/postcode/i), "TR1 1AA");
      await user.type(screen.getByLabelText(/target species/i), "Bass");
      await user.click(screen.getByRole("button", { name: /find fishing spots/i }));

      await waitFor(() =>
        expect(mockRecommend).toHaveBeenCalledWith(
          expect.objectContaining({
            postcode: "TR1 1AA",
            species: "Bass",
          }),
          expect.any(AbortSignal)
        )
      );
    });

    it("omits species from the payload when the species field is empty", async () => {
      mockRecommend.mockResolvedValue(MOCK_RESULT);
      render(<FishingForm />);

      await submitForm();

      await waitFor(() => {
        const [payload] = mockRecommend.mock.calls[0];
        expect(payload.species).toBeUndefined();
      });
    });

    it("disables the submit button while the request is in flight", async () => {
      // Never resolves — keeps the request pending so we can inspect mid-flight state.
      mockRecommend.mockReturnValue(new Promise(() => {}));
      render(<FishingForm />);

      await submitForm();

      expect(screen.getByRole("button", { name: /scanning/i })).toBeDisabled();
    });

    it("re-enables the submit button after the request completes", async () => {
      mockRecommend.mockResolvedValue(MOCK_RESULT);
      render(<FishingForm />);

      await submitForm();

      await waitFor(() =>
        expect(screen.getByRole("button", { name: /find fishing spots/i })).not.toBeDisabled()
      );
    });
  });

  describe("success state", () => {
    it("renders ResultsPanel with the harbour name after a successful response", async () => {
      mockRecommend.mockResolvedValue(MOCK_RESULT);
      render(<FishingForm />);

      await submitForm();

      await waitFor(() => expect(screen.getByText("Falmouth Harbour")).toBeInTheDocument());
    });
  });

  describe("error state", () => {
    it("shows a friendly message on a 422 validation error", async () => {
      mockRecommend.mockRejectedValue(new ApiError(422, "Validation error"));
      render(<FishingForm />);

      await submitForm();

      await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/invalid postcode/i));
    });

    it("shows a server error message on a 500", async () => {
      mockRecommend.mockRejectedValue(new ApiError(500, "Internal error"));
      render(<FishingForm />);

      await submitForm();

      await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/server error/i));
    });

    it("shows a connection error message on a network failure", async () => {
      mockRecommend.mockRejectedValue(new Error("Failed to fetch"));
      render(<FishingForm />);

      await submitForm();

      await waitFor(() =>
        expect(screen.getByRole("alert")).toHaveTextContent(/could not reach the server/i)
      );
    });

    it("does not show an error when the request is aborted", async () => {
      const abortError = new DOMException("Aborted", "AbortError");
      mockRecommend.mockRejectedValue(abortError);
      render(<FishingForm />);

      await submitForm();

      // Brief wait to let async state settle — no alert should appear.
      await new Promise((r) => setTimeout(r, 50));
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });
  });
});
