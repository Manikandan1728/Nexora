import { NavLink } from "react-router-dom";
import {
  MessageSquare,
  Search,
  Database,
  Settings,
  Brain,
  Users,
  Activity,
  Image,
  FileText,
  Compass,
} from "lucide-react";
import { cn } from "@/lib/utils";

const NAV_SECTIONS = [
  {
    label: "AI",
    items: [
      { to: "/workspace",  label: "AI Chat",       Icon: MessageSquare, end: true  },
      { to: "/search",     label: "RAG Search",    Icon: Search,        end: false },
    ],
  },
  {
    label: "Knowledge Explorer",
    items: [
      { to: "/explore",        label: "Search",       Icon: Compass,    end: false },
      { to: "/conversations",  label: "Chats",        Icon: Users,      end: false },
      { to: "/timeline",       label: "Timeline",     Icon: Activity,   end: false },
      { to: "/media",          label: "Media",        Icon: Image,      end: false },
      { to: "/documents",      label: "Documents",    Icon: FileText,   end: false },
      { to: "/people",         label: "People",       Icon: Users,      end: false },
    ],
  },
  {
    label: "System",
    items: [
      { to: "/collections", label: "Collections", Icon: Database,      end: false },
      { to: "/telegram",    label: "Telegram",    Icon: Brain,         end: false },
      { to: "/settings",    label: "Settings",    Icon: Settings,      end: false },
    ],
  },
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
        <span className="text-base font-semibold tracking-tight text-foreground">Nexora</span>
      </div>

      {/* Nav sections */}
      <ul className="flex flex-col gap-0 p-2 flex-1 overflow-y-auto" role="list">
        {NAV_SECTIONS.map((section) => (
          <li key={section.label} className="mb-3">
            <p className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/60">
              {section.label}
            </p>
            <ul role="list" className="space-y-0.5">
              {section.items.map(({ to, label, Icon, end }) => (
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
          </li>
        ))}
      </ul>

      {/* Footer */}
      <div className="px-5 py-3 border-t border-border">
        <p className="text-xs text-muted-foreground">Nexora v8.0.0</p>
      </div>
    </nav>
  );
}
