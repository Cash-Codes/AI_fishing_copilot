/**
 * jest.config.ts — Jest configuration for the Next.js frontend.
 *
 * `next/jest` wraps Jest with Next.js-specific transforms:
 * - Compiles TypeScript and JSX via the SWC compiler (fast).
 * - Mocks CSS imports, images, and next/font automatically.
 * - Loads .env files into process.env.
 *
 * Why moduleNameMapper is defined here instead of relying on next/jest:
 *
 * next/jest auto-generates a moduleNameMapper entry for `@/*` from tsconfig
 * paths, but it uses array form (["<rootDir>/$1"]). jest.mock() calls are
 * hoisted before module resolution and don't handle array-form mappers
 * correctly in some environments. Defining the string form here overrides
 * next/jest's generated entry so both regular imports and jest.mock() resolve
 * the alias consistently.
 *
 * Note: jest.mock() calls in tests should always use relative paths
 * (e.g. "../../lib/api") rather than @/ aliases. jest.mock() is hoisted
 * to the top of the file before any transforms run, making alias resolution
 * unreliable regardless of config. Regular imports can use @/ freely.
 */
import type { Config } from "jest";
import nextJest from "next/jest.js";

const createJestConfig = nextJest({ dir: "./" });

const config: Config = {
  testEnvironment: "jsdom",
  setupFilesAfterEnv: ["<rootDir>/jest.setup.ts"],
  moduleNameMapper: {
    // String form overrides next/jest's array form for this key.
    // Must be defined here so the override is applied synchronously.
    "^@/(.*)$": "<rootDir>/$1",
  },
  testPathIgnorePatterns: ["<rootDir>/node_modules/", "<rootDir>/.next/"],
  collectCoverageFrom: ["app/**/*.{ts,tsx}", "lib/**/*.{ts,tsx}", "!**/*.d.ts"],
};

export default createJestConfig(config);
