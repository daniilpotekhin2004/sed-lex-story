import React, { useEffect } from "react";
import { Router } from "./router";
import { sendTelemetry } from "./api/telemetry";
import { clearBufferedEvents, toApiPayloads } from "./utils/tracker";

const App: React.FC = () => {
  useEffect(() => {
    const payloads = toApiPayloads();
    if (payloads.length === 0) return;
    sendTelemetry(payloads).finally(() => clearBufferedEvents());
  }, []);

  return <Router />;
};

export default App;
