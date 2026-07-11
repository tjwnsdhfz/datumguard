import { mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const webDirectory = resolve(scriptDirectory, "..");
const outputPath = resolve(
  webDirectory,
  "../docs/assets/demo/architecture-verified.png",
);
const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:3000";

async function dragCenterToCenter(page, source, target) {
  const sourceBox = await source.boundingBox();
  const targetBox = await target.boundingBox();
  if (!sourceBox || !targetBox) {
    throw new Error("Architecture drag/snap controls are not visible.");
  }

  await page.mouse.move(
    sourceBox.x + sourceBox.width / 2,
    sourceBox.y + sourceBox.height / 2,
  );
  await page.mouse.down();
  await page.mouse.move(
    targetBox.x + targetBox.width / 2,
    targetBox.y + targetBox.height / 2,
    { steps: 12 },
  );
  await page.mouse.up();
}

await mkdir(dirname(outputPath), { recursive: true });

const browser = await chromium.launch();
try {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 960 },
    deviceScaleFactor: 1,
    locale: "ko-KR",
    timezoneId: "Asia/Seoul",
    colorScheme: "light",
  });
  const page = await context.newPage();
  await page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" });

  await page.goto(baseURL, { waitUntil: "networkidle" });
  await page.locator('[data-testid="architecture-demo"][data-health-status="ready"]').waitFor({
    state: "visible",
    timeout: 45_000,
  });
  await page.getByTestId("architecture-preset-studio").click();
  await dragCenterToCenter(
    page,
    page.getByTestId("architecture-draggable-column"),
    page.getByTestId("architecture-snap-target-center"),
  );

  const responsePromise = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/architecture/designs/run") &&
      response.request().method() === "POST",
  );
  await page.getByTestId("architecture-run-verification").click();
  const response = await responsePromise;
  if (!response.ok()) {
    throw new Error(`Architecture verification failed with HTTP ${response.status()}.`);
  }

  const demo = page.locator(
    '[data-testid="architecture-demo"][data-verification-status="passed"]',
  );
  await demo.waitFor({ state: "visible" });
  await page.getByTestId("verification-summary").waitFor({ state: "visible" });
  await page.getByTestId("architecture-download").waitFor({ state: "visible" });
  await page.evaluate(() => document.fonts.ready);
  await page.evaluate(() => {
    document.documentElement.dataset.architectureCapture = "true";
    window.scrollTo(0, 0);
  });
  await page.addStyleTag({
    content:
      "*, *::before, *::after { animation: none !important; caret-color: transparent !important; transition: none !important; }",
  });

  await page.screenshot({
    path: outputPath,
    animations: "disabled",
    caret: "hide",
    fullPage: false,
  });
  process.stdout.write(`${outputPath}\n`);
  await context.close();
} finally {
  await browser.close();
}
