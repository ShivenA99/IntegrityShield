import React from "react";
import { NavLink } from "react-router-dom";

const links = [
  { to: '/dashboard', label: 'Active Run', icon: '🚀' },
  { to: '/runs', label: 'Previous Runs', icon: '🗂️' },
  { to: '/settings', label: 'Settings', icon: '⚙️' },
];

const Sidebar: React.FC = () => (
  <aside className="app-sidebar">
    <nav>
      {links.map((link) => (
        <NavLink key={link.to} to={link.to} className={({ isActive }) => (isActive ? 'active' : undefined)}>
          <span aria-hidden='true' style={{ marginRight: '0.5rem' }}>{link.icon}</span>
          {link.label}
        </NavLink>
      ))}
    </nav>
  </aside>
);

export default Sidebar;
