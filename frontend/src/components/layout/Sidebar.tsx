import React from "react";
import { NavLink } from "react-router-dom";

const Sidebar: React.FC = () => (
  <aside className="app-sidebar">
    <nav>
      <NavLink to="/dashboard">Dashboard</NavLink>
      <NavLink to="/runs">Active Run</NavLink>
      <NavLink to="/settings">Settings</NavLink>
      <NavLink to="/developer">Developer Console</NavLink>
    </nav>
  </aside>
);

export default Sidebar;
