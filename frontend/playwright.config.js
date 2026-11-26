import process from "node:process";
import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests", timeout: 45000, workers: 1, retries: 0,
  use: { baseURL: "http://localhost:5174", headless: true, channel: process.env.PLAYWRIGHT_CHANNEL || "msedge", viewport: { width: 1280, height: 900 }, screenshot: "only-on-failure", trace: "retain-on-failure" },
});
