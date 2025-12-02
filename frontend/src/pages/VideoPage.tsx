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
        <div className="video-embed">
          <iframe
            width="100%"
            height="600"
            src="https://www.youtube.com/embed/77W_fWW2Agg"
            title="IntegrityShield Demo Video"
            frameBorder="0"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowFullScreen
            style={{
              maxWidth: '1200px',
              margin: '0 auto',
              display: 'block',
              borderRadius: '8px',
              boxShadow: '0 4px 20px rgba(0, 0, 0, 0.15)'
            }}
          />
        </div>

        <div className="video-actions">
          <p className="video-actions__text">
            Watch the demo above, then explore the interactive version or sign in to access the full dashboard.
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
