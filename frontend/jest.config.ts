/**
 * jest.config.ts — Jest configuration for the Next.js frontend.
 *
 * `next/jest` wraps Jest with Next.js-specific transforms:
 * - Compiles TypeScript and JSX via the SWC compiler (fast).
 * - Mocks CSS imports, images, and next/font automatically.
 * - Loads .env files into process.env.
 *
 * moduleNameMapper note:
 * next/jest auto-generates a @/* entry from tsconfig paths in array form
 * (["<rootDir>/$1"]). Array form works for regular imports but the $1
 * capture group is not substituted when jest.mock() resolves the path in
 * some environments (CI, coverage mode). We override with exact-match
 * entries — no capture groups, no $1, nothing to break.
 */
import type { Config } from "jest";
import nextJest from "next/jest.js";

const createJestConfig = nextJest({ dir: "./" });

const config: Config = {
  testEnvironment: "jsdom",
  setupFilesAfterEnv: ["<rootDir>/jest.setup.ts"],
  moduleNameMapper: {
    // Exact match for every @/ path used in tests and source files.
    // Exact matches have no capture groups so there is no $1 substitution —
    // the most common source of jest.mock() resolution failures in CI.
    "^@/lib/api$": "<rootDir>/lib/api",
  },
  testPathIgnorePatterns: ["<rootDir>/node_modules/", "<rootDir>/.next/"],
  collectCoverageFrom: ["app/**/*.{ts,tsx}", "lib/**/*.{ts,tsx}", "!**/*.d.ts"],
};

export default createJestConfig(config);
