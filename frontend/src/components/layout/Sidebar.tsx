import React from "react";
import { NavLink } from "react-router-dom";

import { History, LayoutDashboard, PanelLeftClose, PanelLeftOpen, Settings } from "lucide-react";

const links = [
  { to: "/dashboard", label: "Active Run", shortLabel: "Run", icon: LayoutDashboard },
  { to: "/runs", label: "Previous Runs", shortLabel: "History", icon: History },
  { to: "/settings", label: "Settings", shortLabel: "Prefs", icon: Settings },
];

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
}

const Sidebar: React.FC<SidebarProps> = ({ collapsed, onToggle }) => (
  <aside className={["app-sidebar", collapsed ? "app-sidebar--collapsed" : ""].join(" ").trim()}>
    <div className="app-sidebar__inner">
      <div className="app-sidebar__top">
        <span className="app-sidebar__brand">{collapsed ? "AC" : "AntiCheatAI"}</span>
        <button
          type="button"
          className="app-sidebar__toggle"
          onClick={onToggle}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
        </button>
      </div>

      <nav>
        {links.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            className={({ isActive }) => ["app-sidebar__link", isActive ? "active" : ""].join(" ").trim()}
            title={link.label}
          >
            <link.icon className="app-sidebar__icon" size={18} aria-hidden="true" />
            <span className="app-sidebar__label">
              {collapsed ? link.shortLabel : link.label}
            </span>
          </NavLink>
        ))}
      </nav>
    </div>
  </aside>
);

export default Sidebar;
