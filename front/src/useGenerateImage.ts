import React from "react";
import { useLocation } from "react-router-dom";
import { Header } from "./Header";
import { GenerationProgressOverlay } from "../GenerationProgressOverlay";

type Props = {
  children: React.ReactNode;
};

export const AppLayout: React.FC<Props> = ({ children }) => {
  const location = useLocation();
  const isWorkspaceRoute = /^\/projects\/[^/]+\/graphs\/[^/]+(\/.*)?$/.test(location.pathname);
  const pageClassName = isWorkspaceRoute ? "page page--workspace" : "page";

  return (
    <div className={pageClassName}>
      <Header />
      <main>{children}</main>
      <GenerationProgressOverlay />
    </div>
  );
};
