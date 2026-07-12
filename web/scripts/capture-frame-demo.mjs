import { mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const webDirectory = resolve(scriptDirectory, "..");
const outputPath = resolve(webDirectory, "../docs/assets/demo/frame-verified.png");
const assuranceOutputPath = resolve(
  webDirectory,
  "../docs/assets/demo/frame-assurance-pipeline.png",
);
const rhinoFixture = resolve(
  webDirectory,
  "../fixtures/examples/frame_rhino_exchange.json",
);
const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:3000";

await mkdir(dirname(outputPath), { recursive: true });

const browser = await chromium.launch();
try {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1024 },
    deviceScaleFactor: 1,
    locale: "ko-KR",
    timezoneId: "Asia/Seoul",
    colorScheme: "light",
  });
  const page = await context.newPage();
  await page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" });
  await page.goto(`${baseURL}/frame`, { waitUntil: "networkidle" });
  await page.getByTestId("frame-preset-verified").click();

  const responsePromise = page.waitForResponse(
    (response) =>
      response.url().includes("/api/v1/frame/designs/run") &&
      response.request().method() === "POST",
    { timeout: 120_000 },
  );
  await page.getByTestId("frame-run-analysis").click();
  const response = await responsePromise;
  if (!response.ok()) {
    throw new Error(`Frame analysis failed with HTTP ${response.status()}.`);
  }

  const workspace = page.locator(
    '[data-testid="frame-workspace"][data-run-status="passed"]',
  );
  await workspace.waitFor({ state: "visible", timeout: 120_000 });
  await page.getByTestId("frame-metrics").waitFor({ state: "visible" });

  const rhinoModule = page.getByTestId("frame-rhino-adapter");
  await rhinoModule.locator('input[type="file"]').setInputFiles(rhinoFixture);
  await rhinoModule.waitFor({ state: "visible" });
  await page.waitForFunction(
    () => document.querySelector('[data-testid="frame-rhino-adapter"]')?.getAttribute("data-state") === "passed",
  );

  await page.getByTestId("frame-dxf-assurance").getByRole("button", { name: "Run DXF assurance" }).click();
  await page.waitForFunction(
    () => document.querySelector('[data-testid="frame-dxf-assurance"]')?.getAttribute("data-state") === "passed",
  );
  await page.getByTestId("frame-gnn-surrogate").getByRole("button", { name: "Run advisory GNN" }).click();
  await page.waitForFunction(
    () => document.querySelector('[data-testid="frame-gnn-surrogate"]')?.getAttribute("data-state") === "review",
  );

  await page.evaluate(() => document.fonts.ready);
  await page.addStyleTag({
    content:
      "*, *::before, *::after { animation: none !important; caret-color: transparent !important; transition: none !important; }",
  });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: outputPath,
    fullPage: true,
    animations: "disabled",
    caret: "hide",
  });
  await page.evaluate(() => {
    const stickyHeader = document.querySelector(
      'main[data-testid="frame-workspace"] > header',
    );
    if (stickyHeader instanceof HTMLElement) {
      stickyHeader.style.position = "absolute";
      stickyHeader.style.visibility = "hidden";
    }
  });
  await page.getByTestId("frame-assurance-lab").screenshot({
    path: assuranceOutputPath,
    animations: "disabled",
    caret: "hide",
  });
  process.stdout.write(`${outputPath}\n${assuranceOutputPath}\n`);
  await context.close();
} finally {
  await browser.close();
}
