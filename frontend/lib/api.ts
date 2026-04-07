/**
 * lib/api.ts — Typed HTTP client for the AI Fishing Copilot backend.
 *
 * Design decisions:
 * - All fetch() calls live here. Components never call fetch directly.
 *   That means tests only need to mock this one module, not every component.
 * - `ApiError` carries the HTTP status so callers can distinguish a
 *   validation error (422) from a server fault (500) and respond differently.
 * - Every public function accepts an optional `AbortSignal` so callers
 *   (e.g. a form component) can cancel an in-flight request on unmount or
 *   when the user submits again before the first request resolves.
 */

// ─── Types ────────────────────────────────────────────────────────────────────

/** Body sent to POST /recommend. */
export interface RecommendRequest {
  /** UK postcode ("TR1 1AA") or any place name ("Falmouth", "New York"). */
  location: string;
  /** Optional — omit for a general (non-species-specific) recommendation. */
  species?: string;
  preference: "closest" | "best-chance" | "calmer-conditions";
}

/**
 * Body returned by POST /recommend.
 * Field names match the backend Pydantic model exactly so we don't need
 * a manual mapping layer.
 */
export interface RecommendResponse {
  input_location: string;
  nearest_harbour: string;
  recommendation_window: string;
  /** 0.0 (uncertain) → 1.0 (highly confident). */
  confidence_score: number;
  explanation: string;
  /** True when live data was unavailable and static rules were used instead. */
  used_fallback: boolean;
  /** True when the location is outside the service's coverage area. */
  out_of_range?: boolean;
  /** Relevant notes retrieved from the FAISS knowledge base. */
  retrieved_notes: string[];
  /** Retrieval strategy used: 'hybrid-rrf', 'faiss', or 'bm25'. */
  retrieval_method?: string;
  // ── Conditions (all optional — absent when backend uses mock data) ──────────
  wind_speed_knots?: number;
  wind_direction?: string;
  wind_description?: string;
  wave_height_m?: number;
  sea_state?: string;
  tide_phase?: string;
  spring_or_neap?: string;
  conditions_summary?: string;
}

// ─── Error handling ───────────────────────────────────────────────────────────

/**
 * Thrown for any non-2xx response.
 *
 * Carrying `.status` lets callers write:
 *
 *   catch (err) {
 *     if (err instanceof ApiError && err.status === 422) { ... }
 *   }
 *
 * rather than parsing a string to recover the status code.
 */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string
  ) {
    super(message);
    // Ensure `instanceof ApiError` works correctly after TypeScript compilation.
    Object.setPrototypeOf(this, ApiError.prototype);
    this.name = "ApiError";
  }
}

// ─── Config ───────────────────────────────────────────────────────────────────

/**
 * Only env vars prefixed with NEXT_PUBLIC_ are sent to the browser bundle.
 * The fallback keeps local development working without a .env file.
 */
const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

// ─── Helpers ──────────────────────────────────────────────────────────────────

/**
 * Centralise the response-error path so every endpoint gets the same
 * behaviour: try to extract a detail message from the body, fall back to
 * the HTTP status text if the body isn't readable.
 */
async function throwForStatus(res: Response): Promise<never> {
  const detail = await res.text().catch(() => res.statusText);
  throw new ApiError(res.status, `Request failed (${res.status}): ${detail}`);
}

// ─── Endpoints ────────────────────────────────────────────────────────────────

/**
 * POST /recommend
 *
 * @param request  — validated on the backend; Pydantic returns 422 on bad input
 * @param signal   — optional AbortSignal; pass `AbortController.signal` to
 *                   cancel the request (e.g. when a component unmounts)
 * @throws {ApiError}  for non-2xx HTTP responses
 * @throws {DOMException} with name "AbortError" if the signal fires
 */
export async function recommend(
  request: RecommendRequest,
  signal?: AbortSignal
): Promise<RecommendResponse> {
  const res = await fetch(`${API_BASE}/recommend`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    signal,
  });

  if (!res.ok) {
    await throwForStatus(res);
  }

  // `as` cast is safe: the backend schema guarantees this shape and we validate
  // via Pydantic on the server. A full runtime validator (e.g. Zod) could be
  // added here if the backend contract ever becomes untrustworthy.
  return res.json() as Promise<RecommendResponse>;
}
