import { Outlet } from "react-router-dom";
import { ThemeToggle } from "@/components/theme/ThemeToggle";
import { Shield } from "lucide-react";

export function OnboardingLayout() {
  return (
    <div className="min-h-screen bg-background flex flex-col relative overflow-hidden">
      {/* Dynamic background gradients */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-[40%] -right-[10%] w-[70%] h-[70%] rounded-full bg-accent/20 blur-[120px]" />
        <div className="absolute top-[60%] -left-[10%] w-[60%] h-[60%] rounded-full bg-accent/10 blur-[100px]" />
      </div>

      <header className="absolute top-0 w-full p-6 flex justify-between items-center z-10">
        <div className="flex items-center gap-2">
          <Shield className="w-6 h-6 text-accent" />
          <span className="font-bold text-lg tracking-tight">Nexora</span>
        </div>
        <ThemeToggle />
      </header>
      
      <main className="flex-1 flex flex-col items-center justify-center p-6 z-10">
        <Outlet />
      </main>
    </div>
  );
}
