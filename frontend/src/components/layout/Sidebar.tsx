import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  Upload,
  Search,
  Database,
  Settings,
  Brain,
} from "lucide-react";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/", label: "Dashboard", Icon: LayoutDashboard, end: true },
  { to: "/upload", label: "Upload", Icon: Upload, end: false },
  { to: "/search", label: "Search", Icon: Search, end: false },
  { to: "/collections", label: "Collections", Icon: Database, end: false },
  { to: "/settings", label: "Settings", Icon: Settings, end: false },
];

export function Sidebar() {
  return (
    <nav
      aria-label="Main navigation"
      className="flex flex-col h-full bg-surface border-r border-border"
    >
      {/* Logo */}
      <div className="flex items-center gap-2.5 px-5 h-14 border-b border-border shrink-0">
        <Brain className="h-5 w-5 text-accent" aria-hidden="true" />
        <span className="text-base font-semibold tracking-tight text-foreground">
          Nexora
        </span>
      </div>

      {/* Nav items */}
      <ul className="flex flex-col gap-0.5 p-2 flex-1" role="list">
        {NAV.map(({ to, label, Icon, end }) => (
          <li key={to}>
            <NavLink
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors",
                  "hover:bg-surface-hover hover:text-foreground",
                  isActive
                    ? "bg-accent/10 text-accent"
                    : "text-muted-foreground"
                )
              }
            >
              <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
              {label}
            </NavLink>
          </li>
        ))}
      </ul>

      {/* Footer version */}
      <div className="px-5 py-3 border-t border-border">
        <p className="text-xs text-muted-foreground">Nexora v1.0.0</p>
      </div>
    </nav>
  );
}
