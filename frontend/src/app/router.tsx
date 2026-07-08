import { lazy, Suspense } from "react";
import { createBrowserRouter, Outlet } from "react-router-dom";
import { AppLayout } from "@/components/layout/AppLayout";
import { LoadingSkeleton } from "@/components/common/LoadingSkeleton";
import { ErrorBoundary } from "./error-boundary";

const DashboardPage = lazy(
  () => import("@/features/dashboard/DashboardPage")
);
const UploadPage = lazy(() => import("@/features/upload/UploadPage"));
const SearchPage = lazy(() => import("@/features/search/SearchPage"));
const CollectionsPage = lazy(
  () => import("@/features/collections/CollectionsPage")
);
const SettingsPage = lazy(() => import("@/features/settings/SettingsPage"));
const NotFoundPage = lazy(() => import("@/features/not-found/NotFoundPage"));

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
    element: <AppLayout />,
    children: [
      {
        element: <SuspenseLayout />,
        children: [
          { index: true, element: <DashboardPage /> },
          { path: "upload", element: <UploadPage /> },
          { path: "search", element: <SearchPage /> },
          { path: "collections", element: <CollectionsPage /> },
          { path: "settings", element: <SettingsPage /> },
          { path: "*", element: <NotFoundPage /> },
        ],
      },
    ],
  },
]);
