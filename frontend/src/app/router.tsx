import { lazy, Suspense } from "react";
import { createBrowserRouter, Navigate, Outlet } from "react-router-dom";
import { AppLayout } from "@/components/layout/AppLayout";
import { LoadingSkeleton } from "@/components/common/LoadingSkeleton";
import { ErrorBoundary } from "./error-boundary";
import { OnboardingLayout } from "@/components/layout/OnboardingLayout";

// ─── Onboarding ────────────────────────────────────────────────────────────
const LandingPage                = lazy(() => import("@/features/landing/LandingPage"));
const TelegramConnectionPage     = lazy(() => import("@/features/telegram/TelegramConnectionPage"));
const TelegramChatSelectionPage  = lazy(() => import("@/features/telegram/TelegramChatSelectionPage"));
const TelegramIndexingStatusPage = lazy(() => import("@/features/telegram/TelegramIndexingStatusPage"));

// ─── Main app ──────────────────────────────────────────────────────────────
const WorkspacePage        = lazy(() => import("@/features/workspace/WorkspacePage"));
const SearchPage           = lazy(() => import("@/features/search/SearchPage"));
const CollectionsPage      = lazy(() => import("@/features/collections/CollectionsPage"));
const NotFoundPage         = lazy(() => import("@/features/not-found/NotFoundPage"));

// ─── Knowledge Explorer (Phase 4C) ─────────────────────────────────────────
const ExploreSearchPage       = lazy(() => import("@/features/explorer/ExploreSearchPage"));
const ConversationsPage       = lazy(() => import("@/features/conversations/ConversationsPage"));
const ConversationDetailPage  = lazy(() => import("@/features/conversations/ConversationDetailPage"));
const TimelinePage            = lazy(() => import("@/features/timeline/TimelinePage"));
const MediaExplorerPage       = lazy(() => import("@/features/media/MediaExplorerPage"));
const DocumentExplorerPage    = lazy(() => import("@/features/documents/DocumentExplorerPage"));
const PeoplePage              = lazy(() => import("@/features/people/PeoplePage"));

// ─── Settings (Phase 4D) ───────────────────────────────────────────────────
const SettingsLayout          = lazy(() => import("@/features/settings/SettingsLayout"));
const GeneralSettings         = lazy(() => import("@/features/settings/GeneralSettings"));
const TelegramSettings        = lazy(() => import("@/features/settings/TelegramSettings"));
const SyncSettings            = lazy(() => import("@/features/settings/SyncSettings"));
const AISettings              = lazy(() => import("@/features/settings/AISettings"));
const AppearanceSettings      = lazy(() => import("@/features/settings/AppearanceSettings"));
const NotificationSettings    = lazy(() => import("@/features/settings/NotificationSettings"));
const PrivacySettings         = lazy(() => import("@/features/settings/PrivacySettings"));
const AboutSettings           = lazy(() => import("@/features/settings/AboutSettings"));

function SuspenseLayout() {
  return (
    <ErrorBoundary label="Page error">
      <Suspense fallback={<LoadingSkeleton variant="page" />}>
        <Outlet />
      </Suspense>
    </ErrorBoundary>
  );
}

export const router = createBrowserRouter([
  {
    element: <SuspenseLayout />,
    children: [
      // ─── Onboarding (no sidebar) ────────────────────────────────────────
      {
        element: <OnboardingLayout />,
        children: [
          { index: true,                element: <LandingPage /> },
          { path: "telegram",           element: <TelegramConnectionPage /> },
          { path: "telegram/chats",     element: <TelegramChatSelectionPage /> },
          { path: "telegram/status",    element: <TelegramIndexingStatusPage /> },
        ],
      },
      // ─── Main app (with sidebar) ────────────────────────────────────────
      {
        element: <AppLayout />,
        children: [
          // AI Workspace
          { path: "workspace",                    element: <WorkspacePage /> },
          { path: "search",                       element: <SearchPage /> },
          // Knowledge Explorer
          { path: "explore",                      element: <ExploreSearchPage /> },
          { path: "conversations",                element: <ConversationsPage /> },
          { path: "conversations/:chatId",        element: <ConversationDetailPage /> },
          { path: "timeline",                     element: <TimelinePage /> },
          { path: "media",                        element: <MediaExplorerPage /> },
          { path: "documents",                    element: <DocumentExplorerPage /> },
          { path: "people",                       element: <PeoplePage /> },
          // Collections
          { path: "collections",                  element: <CollectionsPage /> },
          // Settings (nested)
          {
            path: "settings",
            element: <SettingsLayout />,
            children: [
              { index: true,              element: <Navigate to="/settings/general" replace /> },
              { path: "general",          element: <GeneralSettings /> },
              { path: "telegram",         element: <TelegramSettings /> },
              { path: "sync",             element: <SyncSettings /> },
              { path: "ai",               element: <AISettings /> },
              { path: "appearance",       element: <AppearanceSettings /> },
              { path: "notifications",    element: <NotificationSettings /> },
              { path: "privacy",          element: <PrivacySettings /> },
              { path: "about",            element: <AboutSettings /> },
            ],
          },
        ],
      },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);
