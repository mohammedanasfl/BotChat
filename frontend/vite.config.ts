/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// `vite` (dev) serves index.html, which loads the widget source as a module.
// `vite build` produces ONE self-contained file, dist/widget.js (IIFE: React + CSS inlined),
// so any website can embed it with a plain <script> tag.
export default defineConfig({
  plugins: [react()],
  define: { "process.env.NODE_ENV": JSON.stringify("production") },
  build: {
    lib: {
      entry: "src/widget.tsx",
      name: "AbinayaChat",
      formats: ["iife"],
      fileName: () => "widget.js",
    },
    target: "es2020",
    cssCodeSplit: false,
  },
  test: {
    environment: "jsdom",
    include: ["tests/**/*.test.ts?(x)"],
  },
});
