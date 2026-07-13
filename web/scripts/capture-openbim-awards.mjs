import { mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const webDirectory = resolve(scriptDirectory, "..");
const fixtureDirectory = resolve(webDirectory, "../fixtures/openbim");
const outputDirectory = resolve(webDirectory, "../docs/awards-2026/assets");
const inputOutputPath = resolve(outputDirectory, "openbim-demo-input.png");
const resultOutputPath = resolve(outputDirectory, "openbim-demo-result.png");
const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:3000";

const baselineIfc = resolve(fixtureDirectory, "representative/v0_clean.ifc");
const faultyIfc = resolve(fixtureDirectory, "representative/v1_faulty.ifc");
const requirementsIds = resolve(fixtureDirectory, "virtual_fab_v1.ids");

await mkdir(outputDirectory, { recursive: true });

const browser = await chromium.launch();
try {
  const context = await browser.newContext({
    viewport: { width: 1600, height: 1200 },
    deviceScaleFactor: 2,
    locale: "ko-KR",
    timezoneId: "Asia/Seoul",
    colorScheme: "light",
  });
  const page = await context.newPage();
  await page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" });
  await page.goto(`${baseURL}/openbim`, { waitUntil: "networkidle" });

  await page.getByTestId("baseline-input").setInputFiles(baselineIfc);
  await page.getByTestId("candidate-input").setInputFiles(faultyIfc);
  await page.getByTestId("requirements-input").setInputFiles(requirementsIds);
  await page.getByLabel(/research validation only/).check();

  await page.evaluate(() => document.fonts.ready);
  await page.addStyleTag({
    content:
      "*, *::before, *::after { animation: none !important; caret-color: transparent !important; transition: none !important; }",
  });
  await page.locator(".ob-run-grid").screenshot({
    path: inputOutputPath,
    animations: "disabled",
    caret: "hide",
  });

  const responsePromise = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/openbim/evidence/run") &&
      response.request().method() === "POST",
    { timeout: 150_000 },
  );
  await page.getByTestId("openbim-run").click();
  const response = await responsePromise;
  if (!response.ok()) {
    throw new Error(`OpenBIM evidence run failed with HTTP ${response.status()}.`);
  }
  await page
    .locator('[data-testid="openbim-workspace"][data-status="failed_verification"]')
    .waitFor({ state: "visible", timeout: 150_000 });
  await page.getByTestId("openbim-results").waitFor({ state: "visible" });

  await page.addStyleTag({
    content: [
      ".ob-results { padding-top: 42px !important; padding-bottom: 42px !important; }",
      ".ob-result-heading { margin-bottom: 28px !important; }",
      ".ob-result-grid { max-height: 560px !important; overflow: hidden !important; }",
      ".ob-issues, .ob-exports, .ob-result-error { display: none !important; }",
    ].join("\n"),
  });
  await page.getByTestId("openbim-results").screenshot({
    path: resultOutputPath,
    animations: "disabled",
    caret: "hide",
  });

  process.stdout.write(`${inputOutputPath}\n${resultOutputPath}\n`);
  await context.close();
} finally {
  await browser.close();
}
