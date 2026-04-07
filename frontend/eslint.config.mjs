// eslint.config.mjs — ESLint flat config (ESLint v9+ / Next.js 16+).
// next lint was removed in Next.js 16; run "npx eslint ." directly instead.

import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
import prettier from "eslint-config-prettier/flat"; // disables ESLint rules that clash with Prettier

const eslintConfig = defineConfig([
  // Next.js recommended rules (core web vitals + TypeScript)
  ...nextVitals,
  ...nextTs,

  // Prettier last — turns off any ESLint formatting rules Prettier owns
  prettier,

  // Custom rule overrides
  {
    rules: {
      // Warn on console.log so dev logging is visible during review
      "no-console": ["warn", { allow: ["warn", "error"] }],
    },
  },

  // Ignore generated / dependency folders
  globalIgnores([".next/**", "out/**", "build/**", "next-env.d.ts"]),
]);

export default eslintConfig;
