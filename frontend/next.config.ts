import path from "path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  turbopack: {
    /**
     * Explicitly pin Turbopack's root to the `frontend/` directory.
     *
     * Without this, Turbopack walks up the directory tree looking for
     * a lockfile. Because the repo root also has a package-lock.json
     * (created for husky + concurrently), Turbopack picks that one as
     * the workspace root and resolves modules from there — where
     * `tailwindcss` is not installed.
     *
     * `__dirname` is the directory that contains this file (i.e. `frontend/`),
     * which is where our node_modules live.
     */
    root: path.resolve(__dirname),
  },
};

export default nextConfig;
