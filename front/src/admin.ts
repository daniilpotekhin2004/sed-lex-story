import React from "react";
import { Navigate, Outlet, RouteObject, useLocation, useRoutes } from "react-router-dom";
import { useAuth } from "../auth/useAuth";
import { getAccessTokenSnapshot } from "../auth/sessionStore";
import { GeneratePage } from "../pages/GeneratePage";
import { SettingsPage } from "../pages/SettingsPage";
import { LoginPage } from "../pages/LoginPage";
import ProjectsPage from "../pages/ProjectsPage";
import ProjectDetailPage from "../pages/ProjectDetailPage";
import GraphEditorPage from "../pages/GraphEditorPage";
import WorldLibraryPage from "../pages/WorldLibraryPage";
import WizardPage from "../pages/WizardPage";
import PlayerPage from "../pages/PlayerPage";
import PlayerLandingPage from "../pages/PlayerLandingPage";
import OpsConsolePage from "../pages/OpsConsolePage";
import AdminConsolePage from "../pages/AdminConsolePage";
import MyStatsPage from "../pages/MyStatsPage";
import DraftRunnerPage from "../pages/DraftRunnerPage";
import ProjectVoiceoverPage from "../pages/ProjectVoiceoverPage";
import { AppLayout } from "../components/layout/AppLayout";
import { RoleGuard } from "../components/auth/RoleGuard";

const Protected: React.FC = () => {
  const { token } = useAuth();
  const location = useLocation();
  if (!token && !getAccessTokenSnapshot()) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }
  return (
    <AppLayout>
      <Outlet />
    </AppLayout>
  );
};

const PublicOnlyLogin: React.FC = () => {
  const { token, user } = useAuth();
  const snapshotToken = getAccessTokenSnapshot();

  if (token || snapshotToken) {
    const isPlayer =
      user?.role?.toLowerCase() === "player" ||
      (user?.roles ?? []).some((role) => role.toLowerCase() === "player");
    return <Navigate to={isPlayer ? "/player" : "/"} replace />;
  }

  return <LoginPage />;
};

export const Router: React.FC = () => {
  const routes: RouteObject[] = [
    {
      path: "/login",
      element: <PublicOnlyLogin />,
    },
    {
      element: <Protected />,
      children: [
        {
          path: "/",
          element: (
            <RoleGuard allowedRoles={["admin", "author"]}>
              <GeneratePage />
            </RoleGuard>
          ),
        },
        {
          path: "/history",
          element: <Navigate to="/" replace />,
        },
        {
          path: "/voice-generator",
          element: <Navigate to="/" replace />,
        },
        { path: "/settings", element: <SettingsPage /> },
        { path: "/my-stats", element: <MyStatsPage /> },
        {
          path: "/projects",
          element: (
            <RoleGuard allowedRoles={["admin", "author"]}>
              <ProjectsPage />
            </RoleGuard>
          ),
        },
        {
          path: "/projects/:projectId",
          element: (
            <RoleGuard allowedRoles={["admin", "author"]}>
              <ProjectDetailPage />
            </RoleGuard>
          ),
        },
        {
          path: "/projects/:projectId/graphs/:graphId",
          element: (
            <RoleGuard allowedRoles={["admin", "author"]}>
              <GraphEditorPage />
            </RoleGuard>
          ),
        },
        {
          path: "/projects/:projectId/graphs/:graphId/draft-runner",
          element: (
            <RoleGuard allowedRoles={["admin", "author"]}>
              <DraftRunnerPage />
            </RoleGuard>
          ),
        },
        {
          path: "/projects/:projectId/wizard",
          element: (
            <RoleGuard allowedRoles={["admin", "author"]}>
              <WizardPage />
            </RoleGuard>
          ),
        },
        {
          path: "/projects/:projectId/world",
          element: (
            <RoleGuard allowedRoles={["admin", "author"]}>
              <WorldLibraryPage />
            </RoleGuard>
          ),
        },
        {
          path: "/projects/:projectId/voiceover",
          element: (
            <RoleGuard allowedRoles={["admin", "author"]}>
              <ProjectVoiceoverPage />
            </RoleGuard>
          ),
        },
        {
          path: "/studio",
          element: (
            <RoleGuard allowedRoles={["admin", "author"]}>
              <WorldLibraryPage />
            </RoleGuard>
          ),
        },
        {
          path: "/admin",
          element: (
            <RoleGuard allowedRoles={["admin"]}>
              <AdminConsolePage />
            </RoleGuard>
          ),
        },
        {
          path: "/ops",
          element: (
            <RoleGuard allowedRoles={["admin"]}>
              <OpsConsolePage />
            </RoleGuard>
          ),
        },
        { path: "/player", element: <PlayerLandingPage /> },
        { path: "/player/:projectId", element: <PlayerPage /> },
      ],
    },
  ];

  return useRoutes(routes);
};
