import { type ReactNode } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "sonner";
import { queryClient } from "./query-client";
import { ThemeProvider } from "@/hooks/useTheme";

interface Props {
  children: ReactNode;
}

export function Providers({ children }: Props) {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        {children}
        <Toaster
          position="bottom-right"
          toastOptions={{
            classNames: {
              toast:
                "bg-surface border border-border text-foreground text-sm shadow-card",
              success: "border-success/30",
              error: "border-danger/30",
            },
          }}
        />
      </ThemeProvider>
    </QueryClientProvider>
  );
}
