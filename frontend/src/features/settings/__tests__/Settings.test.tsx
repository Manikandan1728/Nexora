import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, beforeEach } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import GeneralSettings from "../GeneralSettings";
import PrivacySettings from "../PrivacySettings";
import NotificationSettings from "../NotificationSettings";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
});

function TestWrapper({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("Settings Module", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  describe("GeneralSettings", () => {
    it("renders Startup and Date & Time sections", () => {
      render(
        <TestWrapper>
          <GeneralSettings />
        </TestWrapper>
      );
      expect(screen.getByText("Startup")).toBeInTheDocument();
      expect(screen.getByText("Date & Time")).toBeInTheDocument();
    });

    it("changes default landing page preference", () => {
      render(
        <TestWrapper>
          <GeneralSettings />
        </TestWrapper>
      );
      const select = screen.getByLabelText(/Default Landing Page/i) as HTMLSelectElement;
      expect(select.value).toBe("/workspace"); // default
      fireEvent.change(select, { target: { value: "/explore" } });
      expect(select.value).toBe("/explore");
    });
  });

  describe("NotificationSettings", () => {
    it("renders notification toggles", () => {
      render(
        <TestWrapper>
          <NotificationSettings />
        </TestWrapper>
      );
      expect(screen.getByText("Synchronization")).toBeInTheDocument();
      expect(screen.getByText("AI Errors")).toBeInTheDocument();
    });

    it("toggles sync complete notification", () => {
      render(
        <TestWrapper>
          <NotificationSettings />
        </TestWrapper>
      );
      const toggle = screen.getByRole("switch", { name: /Notify on sync complete/i });
      expect(toggle).toBeChecked(); // defaults to true
      fireEvent.click(toggle);
      expect(toggle).not.toBeChecked();
    });
  });

  describe("PrivacySettings", () => {
    it("renders encryption status and local storage info", () => {
      render(
        <TestWrapper>
          <PrivacySettings />
        </TestWrapper>
      );
      expect(screen.getByText("Encryption")).toBeInTheDocument();
      expect(screen.getByText("Local Storage")).toBeInTheDocument();
      expect(screen.getByText("Clear Data")).toBeInTheDocument();
    });

    it("requires confirmation for clear history", () => {
      render(
        <TestWrapper>
          <PrivacySettings />
        </TestWrapper>
      );
      const clearBtn = screen.getByRole("button", { name: /Clear History/i });
      fireEvent.click(clearBtn);
      
      const confirmBtn = screen.getByRole("button", { name: /Confirm/i });
      expect(confirmBtn).toBeInTheDocument();
      expect(screen.getByText("Are you sure?")).toBeInTheDocument();
    });
  });
});
