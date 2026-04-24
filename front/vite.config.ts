
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { apiScanPlugin } from "./vite-plugins/api-scan-plugin";

export default defineConfig({
  plugins: [
    react(),
    apiScanPlugin({ scanOnStart: true, scanOnChange: false })
  ],
  server: {
    host: true,
    port: 5174,
    proxy: {
      "/api": {
        target: "http://localhost:8888",
        changeOrigin: true,
      },
    },
  },
});
