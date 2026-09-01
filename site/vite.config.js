import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "/documentation-contract-referee/",
  plugins: [react()],
});
