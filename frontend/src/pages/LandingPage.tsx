import React from "react";
import { Link } from "react-router-dom";
import { Button } from "@instructure/ui-buttons";

import PublicShell from "@layout/PublicShell";

const STEPS = [
  { title: "Ingest", body: "Upload PDFs and answer keys to recover latex, metadata, and structures." },
  { title: "Baseline", body: "Generate vulnerability baselines using your configured providers." },
  { title: "Manipulate", body: "Apply detection or prevention strategies across every question set." },
  { title: "Package", body: "Deliver shielded PDFs plus detection/evaluation packets for LMS handoff." },
];

const LandingPage: React.FC = () => (
  <PublicShell>
    <div className="canvas-card home-hero">
      <div>
        <h2>About</h2>
      </div>
    </div>

    <section className="canvas-card" style={{ marginTop: "1.5rem" }}>
      <h2>How it works</h2>
      <ol className="stepper">
        {STEPS.map((step, index) => (
          <li key={step.title}>
            <div className="step-index">{index + 1}</div>
            <div className="step-body">
              <h3>{step.title}</h3>
              <p>{step.body}</p>
              <details>
                <summary>Learn more</summary>
                <p>IntegrityShield keeps a trace of every action so you can audit manipulations and re-run stages.</p>
              </details>
            </div>
          </li>
        ))}
      </ol>
    </section>
  </PublicShell>
);

export default LandingPage;
