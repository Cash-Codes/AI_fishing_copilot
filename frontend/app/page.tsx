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
        {/* Main title */}
        <h1 className="page-title">
          Fishing
          <span className="title-accent"> Copilot</span>
        </h1>

        {/* Short description */}
        <p className="page-subtitle">
          Enter your postcode to find the best nearby harbour, optimal tidal window and a
          personalised catch forecast.
        </p>
      </header>

      {/* ── Main card — contains the form ────────────────────────────────── */}
      <div className="main-card">
        {/* The form is a Client Component so it can manage state */}
        <FishingForm />
      </div>

      {/* ── Footer ──────────────────────────────────────────────────────── */}
      <footer className="page-footer">AI Fishing Copilot &mdash; UK coastal waters</footer>
    </main>
  );
}
