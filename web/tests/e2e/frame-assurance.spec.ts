import path from "node:path";

import { expect, test } from "@playwright/test";

const rhinoFixture = path.resolve(
  process.cwd(),
  "..",
  "fixtures",
  "examples",
  "frame_rhino_exchange.json",
);

test.beforeEach(async ({ page }) => {
  await page.goto("/frame");
  await expect(page.getByTestId("frame-assurance-lab")).toBeVisible();
});

test("imports a Rhino exchange without guessing units or datum", async ({ page }) => {
  const adapterCard = page.getByTestId("frame-rhino-adapter");
  await adapterCard.locator('input[type="file"]').setInputFiles(rhinoFixture);

  await expect(adapterCard).toHaveAttribute("data-state", "passed", { timeout: 15_000 });
  await expect(adapterCard).toContainText("NORMALIZED");
  await expect(adapterCard).toContainText("mm", { ignoreCase: true });
});

test("writes, reopens, verifies, and downloads the exact frame DXF", async ({ page }) => {
  const assuranceCard = page.getByTestId("frame-dxf-assurance");
  await assuranceCard.getByRole("button", { name: "Run DXF assurance" }).click();

  await expect(assuranceCard).toHaveAttribute("data-state", "passed", { timeout: 20_000 });
  await expect(assuranceCard).toContainText("0.001 MM VERIFIED");
  const downloadPromise = page.waitForEvent("download");
  await assuranceCard.getByRole("button", { name: "Download screened DXF" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("frameguard-screening-model.dxf");
});

test("clears stale CAD evidence and blocks download after the contract changes", async ({ page }) => {
  const assuranceCard = page.getByTestId("frame-dxf-assurance");
  const downloadButton = assuranceCard.getByRole("button", { name: "Download screened DXF" });
  await assuranceCard.getByRole("button", { name: "Run DXF assurance" }).click();
  await expect(assuranceCard).toHaveAttribute("data-state", "passed", { timeout: 20_000 });
  await expect(downloadButton).toBeEnabled();

  await page.getByTestId("frame-preset-failure").click();

  const resetAssuranceCard = page.getByTestId("frame-dxf-assurance");
  const resetDownloadButton = resetAssuranceCard.getByRole("button", { name: "Download screened DXF" });
  await expect(resetAssuranceCard).toHaveAttribute("data-state", "idle");
  await expect(resetAssuranceCard).toContainText("not run");
  await expect(resetDownloadButton).toBeDisabled();

  await resetAssuranceCard.getByRole("button", { name: "Run DXF assurance" }).click();
  await expect(resetAssuranceCard).toHaveAttribute("data-state", "review", { timeout: 20_000 });
  await expect(resetDownloadButton).toBeDisabled();
});

test("shows immutable OpenSees evidence and keeps the GNN advisory", async ({ page }) => {
  const parity = page.getByTestId("frame-opensees-parity");
  await expect(parity).toHaveAttribute("data-state", "passed", { timeout: 15_000 });
  await expect(parity).toContainText("6");
  await expect(parity).toContainText("3.8.0.0");

  const surrogate = page.getByTestId("frame-gnn-surrogate");
  await expect(surrogate).toContainText("COMPLETED", { timeout: 15_000 });
  await surrogate.getByRole("button", { name: "Run advisory GNN" }).click();
  await expect(surrogate).toHaveAttribute("data-state", "review", { timeout: 15_000 });
  await expect(surrogate).toContainText("REVIEW_REQUIRED");
  await expect(surrogate).toContainText("DG_FRAME_SURROGATE_HIGH_UNCERTAINTY");
  await expect(surrogate).toContainText("authoritative=false");
});
