import { mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const webDirectory = resolve(scriptDirectory, "..");
const outputPath = resolve(webDirectory, "../docs/assets/demo/solid-step-verified.png");
const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:3000";

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
  await page.goto(`${baseURL}/solid`, { waitUntil: "networkidle" });
  await page.getByTestId("solid-run-button").click();
  await page.locator('[data-testid="solid-workspace"][data-run-status="passed"]').waitFor({
    state: "visible",
    timeout: 45_000,
  });
  await page.getByTestId("cad-mesh-preview").waitFor({ state: "visible" });
  await page.evaluate(() => document.fonts.ready);
  await page.evaluate(() => window.scrollTo(0, 410));
  await page.addStyleTag({
    content: "*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important}",
  });
  await page.screenshot({ path: outputPath, animations: "disabled", caret: "hide", fullPage: false });
  process.stdout.write(`${outputPath}\n`);
  await context.close();
} finally {
  await browser.close();
}
