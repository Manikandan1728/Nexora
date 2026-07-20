import { Menu } from "lucide-react";
import { useLocation } from "react-router-dom";
import { StatusIndicator } from "@/components/common/StatusIndicator";
import { ThemeToggle } from "@/components/theme/ThemeToggle";

const PAGE_TITLES: Record<string, string> = {
  "/": "Dashboard",
  "/search": "Search",
  "/collections": "Collections",
  "/settings": "Settings",
};

interface Props {
  onMenuClick: () => void;
}

export function Topbar({ onMenuClick }: Props) {
  const { pathname } = useLocation();
  const title = PAGE_TITLES[pathname] ?? "Nexora";

  return (
    <header className="flex items-center justify-between h-14 px-4 md:px-6 border-b border-border bg-surface shrink-0 gap-3">
      {/* Mobile menu button */}
      <button
        type="button"
        className="md:hidden p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-surface-hover transition-colors"
        onClick={onMenuClick}
        aria-label="Open navigation menu"
      >
        <Menu className="h-5 w-5" aria-hidden="true" />
      </button>

      <h1 className="text-sm font-semibold text-foreground md:text-base">
        {title}
      </h1>

      <div className="flex items-center gap-3 ml-auto">
        <StatusIndicator />
        <ThemeToggle />
      </div>
    </header>
  );
}
