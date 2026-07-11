import { mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const webDirectory = resolve(scriptDirectory, "..");
const outputPath = resolve(webDirectory, "../docs/assets/demo/piping-verified.png");
const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:3000";

async function dragCenterToCenter(page, source, target) {
  const sourceBox = await source.boundingBox();
  const targetBox = await target.boundingBox();
  if (!sourceBox || !targetBox) {
    throw new Error("Piping drag/snap controls are not visible.");
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
    viewport: { width: 1440, height: 1024 },
    deviceScaleFactor: 1,
    locale: "ko-KR",
    timezoneId: "Asia/Seoul",
    colorScheme: "light",
  });
  const page = await context.newPage();
  await page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" });
  await page.goto(`${baseURL}/piping`, { waitUntil: "networkidle" });
  await page.getByTestId("piping-preset-utility").click();
  await dragCenterToCenter(
    page,
    page.getByTestId("piping-draggable-valve"),
    page.getByTestId("piping-snap-target"),
  );

  const responsePromise = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/piping/designs/run") &&
      response.request().method() === "POST",
  );
  await page.getByTestId("piping-run-verification").click();
  const response = await responsePromise;
  if (!response.ok()) {
    throw new Error(`Piping verification failed with HTTP ${response.status()}.`);
  }

  const demo = page.locator(
    '[data-testid="piping-demo"][data-verification-status="passed"]',
  );
  await demo.waitFor({ state: "visible" });
  await page.getByTestId("piping-summary").waitFor({ state: "visible" });
  await page.evaluate(() => document.fonts.ready);
  await page.addStyleTag({
    content:
      "*, *::before, *::after { animation: none !important; caret-color: transparent !important; transition: none !important; }",
  });
  await demo.screenshot({
    path: outputPath,
    animations: "disabled",
    caret: "hide",
  });
  process.stdout.write(`${outputPath}\n`);
  await context.close();
} finally {
  await browser.close();
}
