import { NavLink, Outlet, useNavigate, useLocation } from "react-router-dom";
import {
  Settings,
  User,
  RefreshCw,
  Brain,
  Palette,
  ShieldCheck,
  Bell,
  Info,
} from "lucide-react";
import { cn } from "@/lib/utils";

const SETTINGS_NAV = [
  { to: "/settings/general",       label: "General",          Icon: Settings    },
  { to: "/settings/telegram",      label: "Telegram",         Icon: User        },
  { to: "/settings/sync",          label: "Synchronization",  Icon: RefreshCw   },
  { to: "/settings/ai",            label: "AI & Models",      Icon: Brain       },
  { to: "/settings/appearance",    label: "Appearance",       Icon: Palette     },
  { to: "/settings/notifications", label: "Notifications",    Icon: Bell        },
  { to: "/settings/privacy",       label: "Privacy & Security", Icon: ShieldCheck },
  { to: "/settings/about",         label: "About",            Icon: Info        },
];

export default function SettingsLayout() {
  const navigate = useNavigate();
  const location = useLocation();

  // If at exactly /settings, redirect to general
  if (location.pathname === "/settings" || location.pathname === "/settings/") {
    navigate("/settings/general", { replace: true });
    return null;
  }

  return (
    <div className="flex h-full gap-6 animate-fade-in">
      {/* Sidebar nav — desktop */}
      <aside
        className="hidden md:flex flex-col w-52 shrink-0 rounded-xl border border-border bg-surface shadow-card overflow-hidden h-fit sticky top-0"
        aria-label="Settings navigation"
      >
        <div className="px-4 py-3 border-b border-border">
          <h1 className="text-sm font-semibold text-foreground">Settings</h1>
        </div>
        <nav>
          <ul className="p-1.5 space-y-0.5" role="list">
            {SETTINGS_NAV.map(({ to, label, Icon }) => (
              <li key={to}>
                <NavLink
                  to={to}
                  className={({ isActive }) =>
                    cn(
                      "flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors w-full",
                      isActive
                        ? "bg-accent/10 text-accent"
                        : "text-muted-foreground hover:text-foreground hover:bg-surface-hover"
                    )
                  }
                >
                  <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                  {label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </aside>

      {/* Mobile nav — horizontal scroll tabs */}
      <div className="md:hidden w-full mb-4">
        <div className="flex gap-1 overflow-x-auto pb-1 no-scrollbar" role="tablist">
          {SETTINGS_NAV.map(({ to, label, Icon }) => (
            <NavLink
              key={to}
              to={to}
              role="tab"
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium whitespace-nowrap shrink-0 transition-colors",
                  isActive
                    ? "bg-accent/10 text-accent"
                    : "text-muted-foreground hover:text-foreground bg-surface border border-border"
                )
              }
            >
              <Icon className="h-3.5 w-3.5" aria-hidden="true" />
              {label}
            </NavLink>
          ))}
        </div>
      </div>

      {/* Content area */}
      <main className="flex-1 min-w-0 space-y-5">
        <Outlet />
      </main>
    </div>
  );
}
