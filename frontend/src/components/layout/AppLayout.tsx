import { useState } from "react";
import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
import { MobileNav } from "./MobileNav";

export function AppLayout() {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="flex min-h-screen bg-background">
      {/* Desktop sidebar */}
      <aside className="hidden md:flex md:flex-col md:w-56 lg:w-60 shrink-0">
        <Sidebar />
      </aside>

      {/* Mobile nav overlay */}
      <MobileNav
        open={mobileOpen}
        onClose={() => setMobileOpen(false)}
      />

      {/* Main content */}
      <div className="flex flex-col flex-1 min-w-0">
        <Topbar onMenuClick={() => setMobileOpen(true)} />
        <main
          id="main-content"
          className="flex-1 p-4 md:p-6 lg:p-8 overflow-y-auto"
        >
          <Outlet />
        </main>
      </div>
    </div>
  );
}
