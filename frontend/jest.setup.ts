/**
 * jest.setup.ts — Runs once before each test file.
 *
 * Importing @testing-library/jest-dom extends Jest's built-in `expect`
 * with DOM-aware matchers:
 *   expect(el).toBeInTheDocument()
 *   expect(input).toHaveValue("TR1 1AA")
 *   expect(btn).toBeDisabled()
 * …and many more. See https://github.com/testing-library/jest-dom
 */
import "@testing-library/jest-dom";
