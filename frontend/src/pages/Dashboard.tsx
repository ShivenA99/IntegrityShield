import React from "react";

import PipelineContainer from "@components/pipeline/PipelineContainer";
import DeveloperPanel from "@components/developer/DeveloperPanel";

const Dashboard: React.FC = () => (
  <div className="page dashboard">
    <PipelineContainer />
    <DeveloperPanel />
  </div>
);

export default Dashboard;
