import React from "react";

import DeveloperPanel from "@components/developer/DeveloperPanel";
import DeveloperToggle from "@components/layout/DeveloperToggle";

const DeveloperConsole: React.FC = () => (
  <div className="page developer-console">
    <DeveloperToggle />
    <DeveloperPanel />
  </div>
);

export default DeveloperConsole;
