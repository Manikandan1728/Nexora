import { useEffect } from "react";
import { NavLink } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  LayoutDashboard, Search, Database, Settings, Brain, X,
  MessageSquare, Users, Activity,
} from "lucide-react";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/",               label: "Dashboard",      Icon: LayoutDashboard, end: true  },
  { to: "/search",         label: "Search",         Icon: Search,          end: false },
  { to: "/collections",    label: "Collections",    Icon: Database,        end: false },
  { to: "/telegram",       label: "Telegram",       Icon: MessageSquare,   end: true  },
  { to: "/telegram/chats", label: "Chats",          Icon: Users,           end: false },
  { to: "/telegram/status",label: "Indexing Status",Icon: Activity,        end: false },
  { to: "/settings",       label: "Settings",       Icon: Settings,        end: false },
];

interface Props {
  open: boolean;
  onClose: () => void;
}

export function MobileNav({ open, onClose }: Props) {
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            key="backdrop"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="fixed inset-0 z-40 bg-black/60 md:hidden"
            onClick={onClose} aria-hidden="true"
          />
          <motion.nav
            key="drawer"
            role="dialog" aria-label="Mobile navigation" aria-modal="true"
            initial={{ x: "-100%" }} animate={{ x: 0 }} exit={{ x: "-100%" }}
            transition={{ type: "spring", stiffness: 380, damping: 35 }}
            className="fixed inset-y-0 left-0 z-50 w-64 bg-surface border-r border-border flex flex-col md:hidden"
          >
            <div className="flex items-center justify-between px-5 h-14 border-b border-border">
              <div className="flex items-center gap-2.5">
                <Brain className="h-5 w-5 text-accent" aria-hidden="true" />
                <span className="text-base font-semibold text-foreground">Nexora</span>
              </div>
              <button type="button" onClick={onClose}
                className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-surface-hover"
                aria-label="Close navigation">
                <X className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
            <ul className="flex flex-col gap-0.5 p-2 flex-1" role="list">
              {NAV.map(({ to, label, Icon, end }) => (
                <li key={to}>
                  <NavLink to={to} end={end} onClick={onClose}
                    className={({ isActive }) => cn(
                      "flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium transition-colors",
                      "hover:bg-surface-hover hover:text-foreground",
                      isActive ? "bg-accent/10 text-accent" : "text-muted-foreground"
                    )}>
                    <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                    {label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </motion.nav>
        </>
      )}
    </AnimatePresence>
  );
}
