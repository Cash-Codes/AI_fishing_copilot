/**
 * lib/__tests__/api.test.ts — Unit tests for the HTTP client.
 *
 * We test at the fetch() boundary, not the network. jest.fn() replaces the
 * global `fetch` so tests are deterministic and work offline.
 *
 * Each test follows the Arrange / Act / Assert structure:
 *   Arrange: set up state and mocks
 *   Act:     call the function under test
 *   Assert:  verify the outcome
 */

import { ApiError, recommend, type RecommendRequest } from "../api";

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const REQUEST: RecommendRequest = {
  postcode: "TR1 1AA",
  species: "Bass",
  preference: "best-chance",
};

const MOCK_RESPONSE = {
  input_postcode: "TR1 1AA",
  nearest_harbour: "Falmouth Harbour",
  recommendation_window: "Saturday 06:00 – 10:00",
  confidence_score: 0.82,
  explanation: "Good conditions.",
  used_fallback: false,
  retrieved_notes: ["Spring tide Saturday."],
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

/**
 * Builds a minimal Response-like object for fetch mocking.
 * We only implement what our code actually calls (ok, status, text, json).
 */
function mockFetchResponse(body: unknown, status = 200): Response {
  const json = JSON.stringify(body);
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? "OK" : "Error",
    text: () => Promise.resolve(typeof body === "string" ? body : json),
    json: () => Promise.resolve(body),
  } as unknown as Response;
}

// ─── Setup ────────────────────────────────────────────────────────────────────

// Replace the global fetch before each test; restore it after.
// This prevents one test's mock from leaking into the next.
let fetchMock: jest.Mock;

beforeEach(() => {
  fetchMock = jest.fn();
  global.fetch = fetchMock;
});

afterEach(() => {
  jest.restoreAllMocks();
});

// ─── Tests ────────────────────────────────────────────────────────────────────

describe("recommend()", () => {
  it("POSTs to /recommend with the correct URL and body", async () => {
    fetchMock.mockResolvedValue(mockFetchResponse(MOCK_RESPONSE));

    await recommend(REQUEST);

    // Verify the exact URL and method — a typo here would silently break prod.
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/recommend",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(REQUEST),
      })
    );
  });

  it("returns the parsed JSON body on a 200 response", async () => {
    fetchMock.mockResolvedValue(mockFetchResponse(MOCK_RESPONSE));

    const result = await recommend(REQUEST);

    expect(result).toEqual(MOCK_RESPONSE);
  });

  it("omits species from the request when not provided", async () => {
    fetchMock.mockResolvedValue(mockFetchResponse(MOCK_RESPONSE));

    const requestWithoutSpecies: RecommendRequest = {
      postcode: "EX1 1AA",
      preference: "closest",
    };
    await recommend(requestWithoutSpecies);

    const sentBody = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    // species should not appear in the payload at all (undefined is omitted by JSON.stringify)
    expect(sentBody).not.toHaveProperty("species");
  });

  it("throws ApiError with the response status on a 422", async () => {
    fetchMock.mockResolvedValue(mockFetchResponse("Postcode too short", 422));

    await expect(recommend(REQUEST)).rejects.toThrow(ApiError);
    await expect(recommend(REQUEST)).rejects.toMatchObject({ status: 422 });
  });

  it("throws ApiError with the response status on a 500", async () => {
    fetchMock.mockResolvedValue(mockFetchResponse("Internal server error", 500));

    await expect(recommend(REQUEST)).rejects.toThrow(ApiError);
    await expect(recommend(REQUEST)).rejects.toMatchObject({ status: 500 });
  });

  it("includes the error body text in the ApiError message", async () => {
    fetchMock.mockResolvedValue(mockFetchResponse("Postcode not found", 404));

    try {
      await recommend(REQUEST);
      fail("Expected recommend() to throw");
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      expect((err as ApiError).message).toContain("Postcode not found");
    }
  });

  it("forwards the AbortSignal to fetch", async () => {
    fetchMock.mockResolvedValue(mockFetchResponse(MOCK_RESPONSE));
    const controller = new AbortController();

    await recommend(REQUEST, controller.signal);

    expect(fetchMock).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ signal: controller.signal })
    );
  });

  it("propagates an AbortError when the signal fires", async () => {
    // Simulate fetch throwing an AbortError (what browsers do when aborted).
    const abortError = new DOMException("Aborted", "AbortError");
    fetchMock.mockRejectedValue(abortError);

    const controller = new AbortController();
    controller.abort();

    await expect(recommend(REQUEST, controller.signal)).rejects.toThrow("Aborted");
  });
});
