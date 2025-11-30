import React from "react";
import { Link } from "react-router-dom";
import { Button } from "@instructure/ui-buttons";
import PublicShell from "@layout/PublicShell";

const VideoPage: React.FC = () => (
  <PublicShell>
    <div className="video-page">
      <section className="video-hero">
        <h2 className="video-hero__title">See IntegrityShield in Action</h2>
      </section>

      <div className="video-container">
        <div className="video-placeholder">
          <svg className="video-placeholder__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10"></circle>
            <polygon points="10 8 16 12 10 16 10 8"></polygon>
          </svg>
          <p className="video-placeholder__text">
            A comprehensive walkthrough video will be available here soon.
          </p>
        </div>

        <div className="video-actions">
          <p className="video-actions__text">
            In the meantime, explore the interactive demo or sign in to access the full dashboard.
          </p>
          <div className="video-actions__buttons">
            <Button color="primary" as={Link} to="/try" size="large">
              Try the demo
            </Button>
            <Button color="secondary" as={Link} to="/login" size="large">
              Sign in to Dashboard
            </Button>
          </div>
        </div>
      </div>
    </div>
  </PublicShell>
);

export default VideoPage;
