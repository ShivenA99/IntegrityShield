import React from "react";
import PublicShell from "@layout/PublicShell";

const LandingPage: React.FC = () => {
  return (
    <PublicShell>
      <div className="landing-page">
        {/* Hero Section */}
        <section className="landing-hero">
          <h2 className="landing-hero__title">
            Protecting Educational Assessments from LLM-Based Cheating
          </h2>
        </section>

        {/* About Section */}
        <section className="landing-section">
          <h3 className="landing-section__title">About</h3>
          <p className="landing-section__text">
            In the competitive landscape of online education, accurate and comprehensive assessment protection is crucial for both educators and students. While educational platforms strive to provide detailed information, assessment integrity often lacks completeness or accuracy. Student behavior can bridge this gap, but navigating a plethora of unstructured feedback can be challenging.
          </p>
          <p className="landing-section__text">
            To address this issue, we introduce <strong>IntegrityShield: LLM Vulnerability Assessment & Protection Engine</strong>. This innovative tool leverages the power of Large Language Models (LLMs) to automatically analyze and synthesize assessment security within a single, user-friendly interface.
          </p>
          <p className="landing-section__text">
            By integrating these diverse data sources, IntegrityShield empowers both educators and students with a more comprehensive understanding of assessments, leading to improved decision-making and increased security confidence.
          </p>
        </section>

        {/* How it Works Section */}
        <section className="landing-section">
          <h3 className="landing-section__title">How does it work?</h3>
          <p className="landing-section__text">
            We introduce IntegrityShield, a tool designed to improve the clarity and informativeness of assessments by leveraging insights derived from testing vulnerabilities. IntegrityShield employs a hybrid approach, combining the analytical capabilities of Large Language Models (LLMs) with a rule-based methodology to effectively synthesize information from both assessment content and vulnerability testing. IntegrityShield leverages the idea of structured outputs through LLMs. The core functionality of IntegrityShield can be broken down into these key stages:
          </p>

          <div className="landing-steps">
            <div className="landing-step">
              <div className="landing-step__number">1</div>
              <div className="landing-step__content">
                <h4 className="landing-step__title">Ingest</h4>
                <p className="landing-step__text">
                  Upload PDFs and answer keys to recover latex, metadata, and structures. IntegrityShield extracts question structures, LaTeX formatting, and metadata from your assessment PDFs.
                </p>
              </div>
            </div>

            <div className="landing-step">
              <div className="landing-step__number">2</div>
              <div className="landing-step__content">
                <h4 className="landing-step__title">Baseline</h4>
                <p className="landing-step__text">
                  Generate vulnerability baselines using your configured providers. The system tests your original assessment against multiple LLM providers to establish baseline vulnerability scores.
                </p>
              </div>
            </div>

            <div className="landing-step">
              <div className="landing-step__number">3</div>
              <div className="landing-step__content">
                <h4 className="landing-step__title">Manipulate</h4>
                <p className="landing-step__text">
                  Apply detection or prevention strategies across every question set. Choose from various protection strategies: add honeypot questions, rephrase vulnerable items, or inject detection mechanisms.
                </p>
              </div>
            </div>

            <div className="landing-step">
              <div className="landing-step__number">4</div>
              <div className="landing-step__content">
                <h4 className="landing-step__title">Package</h4>
                <p className="landing-step__text">
                  Deliver shielded PDFs plus detection/evaluation packets for LMS handoff. Generate protected assessment PDFs ready for your LMS, along with comprehensive detection reports and evaluation metrics.
                </p>
              </div>
            </div>
          </div>
        </section>
      </div>
    </PublicShell>
  );
};

export default LandingPage;
