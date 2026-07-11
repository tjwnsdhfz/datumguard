import { defineConfig, devices } from "@playwright/test";

const port = Number(process.env.PLAYWRIGHT_PORT ?? "3000");
const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? `http://127.0.0.1:${port}`;
const apiURL = process.env.PLAYWRIGHT_API_URL ?? "http://127.0.0.1:8000";
const parsedApiURL = new URL(apiURL);
const apiHost = parsedApiURL.hostname;
const apiPort = Number(parsedApiURL.port || (parsedApiURL.protocol === "https:" ? "443" : "80"));
const isCI = Boolean(process.env.CI);
const apiPython =
  process.env.DATUMGUARD_PYTHON ??
  (process.platform === "win32" ? ".venv\\Scripts\\python.exe" : "python");

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  forbidOnly: isCI,
  retries: isCI ? 2 : 0,
  workers: isCI ? 1 : undefined,
  timeout: 30_000,
  expect: {
    timeout: 5_000,
  },
  outputDir: "test-results",
  reporter: isCI
    ? [
        ["line"],
        ["html", { outputFolder: "playwright-report", open: "never" }],
      ]
    : [["list"], ["html", { outputFolder: "playwright-report", open: "never" }]],
  use: {
    baseURL,
    locale: "ko-KR",
    timezoneId: "Asia/Seoul",
    colorScheme: "light",
    serviceWorkers: "block",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 1024 },
      },
    },
  ],
  webServer: [
    {
      command: `"${apiPython}" -m uvicorn datumguard.api:app --host ${apiHost} --port ${apiPort}`,
      cwd: "..",
      url: `${apiURL}/api/v1/health`,
      reuseExistingServer: !isCI,
      timeout: 120_000,
      env: {
        DATUMGUARD_CORS_ORIGINS:
          process.env.DATUMGUARD_CORS_ORIGINS ?? baseURL,
      },
    },
    {
      command: isCI
        ? `npm run start -- --hostname 127.0.0.1 --port ${port}`
        : `npm run dev -- --hostname 127.0.0.1 --port ${port}`,
      url: baseURL,
      reuseExistingServer: !isCI,
      timeout: 120_000,
      env: {
        NEXT_PUBLIC_DATUMGUARD_API_URL:
          process.env.NEXT_PUBLIC_DATUMGUARD_API_URL ?? apiURL,
        NEXT_PUBLIC_GITHUB_URL:
          process.env.NEXT_PUBLIC_GITHUB_URL ?? "https://github.com",
      },
    },
  ],
});
