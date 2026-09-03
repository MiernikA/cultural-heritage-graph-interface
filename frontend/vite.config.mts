import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@/app": new URL("./src/app", import.meta.url).pathname,
      "@/pages": new URL("./src/pages", import.meta.url).pathname,
      "@/entities": new URL("./src/entities", import.meta.url).pathname,
      "@/shared": new URL("./src/shared", import.meta.url).pathname,
    },
  },
});
