// page.tsx — The homepage (route: "/").
// This is a Server Component by default — it renders on the server and sends
// HTML to the browser. The interactive form is split into a Client Component.

import FishingForm from "./components/FishingForm";

export default function HomePage() {
  return (
    // Full-height centred layout
    <main className="page-wrapper">
      {/* ── Header ──────────────────────────────────────────────────────── */}
      <header className="page-header">
        {/* Decorative coordinates — evokes a navigation instrument */}
        <p className="coord-line" aria-hidden="true">
          50°09′N 5°04′W &nbsp;·&nbsp; COASTAL ADVISORY SYSTEM
        </p>

        {/* Main title */}
        <h1 className="page-title">
          AI&nbsp;Fishing
          <br />
          <span className="title-accent">Copilot</span>
        </h1>

        {/* Short description */}
        <p className="page-subtitle">
          Enter your postcode and we&apos;ll find the nearest harbour, optimal tidal window, and
          AI-powered recommendation.
        </p>
      </header>

      {/* ── Main card — contains the form ────────────────────────────────── */}
      <div className="main-card">
        {/* The form is a Client Component so it can manage state */}
        <FishingForm />
      </div>

      {/* ── Footer ──────────────────────────────────────────────────────── */}
      <footer className="page-footer">AI Fishing Copilot &mdash; prototype build</footer>
    </main>
  );
}
