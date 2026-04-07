/**
 * jest.config.ts — Jest configuration for the Next.js frontend.
 *
 * `next/jest` wraps Jest with Next.js-specific transforms:
 * - Compiles TypeScript and JSX via the SWC compiler (fast).
 * - Mocks CSS imports, images, and next/font automatically.
 * - Loads .env files into process.env.
 */
import type { Config } from "jest";
import nextJest from "next/jest.js";

// Tell next/jest where the Next.js app lives so it can read next.config.ts.
const createJestConfig = nextJest({ dir: "./" });

const config: Config = {
  testEnvironment: "jsdom", // simulate a browser DOM for component tests

  // Run this file before each test suite — sets up jest-dom matchers like
  // toBeInTheDocument(), toHaveValue(), etc.
  setupFilesAfterEnv: ["<rootDir>/jest.setup.ts"],

  // Make @/ imports (tsconfig path alias) work in tests.
  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/$1",
  },

  // Only test files we own — ignore node_modules and the Next.js build output.
  testPathIgnorePatterns: ["<rootDir>/node_modules/", "<rootDir>/.next/"],

  // Collect coverage from our source files, excluding config and generated files.
  collectCoverageFrom: ["app/**/*.{ts,tsx}", "lib/**/*.{ts,tsx}", "!**/*.d.ts"],
};

// createJestConfig wraps our config so next/jest can apply its async setup.
export default createJestConfig(config);
