import { chromium } from "@playwright/test";
import { pathToFileURL } from "node:url";
import path from "node:path";

const repositoryRoot = path.resolve(import.meta.dirname, "..", "..");
const sourcePath = path.join(
  repositoryRoot,
  "docs",
  "assets",
  "social",
  "datumguard-social-preview.svg",
);
const outputPath = path.join(
  repositoryRoot,
  "docs",
  "assets",
  "social",
  "datumguard-social-preview.png",
);

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({
    viewport: { width: 1280, height: 640 },
    deviceScaleFactor: 1,
  });
  await page.goto(pathToFileURL(sourcePath).href, { waitUntil: "load" });
  await page.screenshot({
    path: outputPath,
    animations: "disabled",
    caret: "hide",
    fullPage: false,
  });
  console.log(`Rendered ${outputPath}`);
} finally {
  await browser.close();
}
