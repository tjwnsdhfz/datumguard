import { expect, test, type Page } from "@playwright/test";

async function dragCenterToCenter(page: Page, sourceTestId: string, targetTestId: string) {
  const source = page.getByTestId(sourceTestId);
  const target = page.getByTestId(targetTestId);
  const sourceBox = await source.boundingBox();
  const targetBox = await target.boundingBox();

  expect(sourceBox, `${sourceTestId} must be rendered`).not.toBeNull();
  expect(targetBox, `${targetTestId} must be rendered`).not.toBeNull();
  if (!sourceBox || !targetBox) return;

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

test.describe("plant and semiconductor utility piping workspace", () => {
  test("is deep-linkable and exposes the three engineering domains", async ({ page }) => {
    await page.goto("/piping");

    await expect(page.getByTestId("piping-demo")).toBeVisible();
    await expect(page.getByTestId("piping-canvas")).toBeVisible();
    await expect(page.getByTestId("piping-preset-utility")).toBeVisible();
    await expect(page.getByTestId("piping-preset-clearance-fail")).toBeVisible();
    await expect(page.locator('a[href="/"]')).toHaveCount(1);
    await expect(page.locator('a[href="/plate"]')).toHaveCount(1);
  });

  test("snaps an inline valve and verifies the serialized DXF with the real API", async ({
    page,
  }) => {
    await page.goto("/piping");
    await page.getByTestId("piping-preset-utility").click();

    await dragCenterToCenter(page, "piping-draggable-valve", "piping-snap-target");
    await expect(page.getByTestId("piping-draggable-valve")).toHaveAttribute(
      "data-snap-state",
      "snapped",
    );

    const responsePromise = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/v1/piping/designs/run") &&
        response.request().method() === "POST",
    );
    await page.getByTestId("piping-run-verification").click();
    const response = await responsePromise;

    expect(response.ok()).toBeTruthy();
    await expect(page.getByTestId("piping-demo")).toHaveAttribute(
      "data-verification-status",
      "passed",
    );
    await expect(page.getByTestId("piping-verified-badge")).toContainText(/verified/i);
    await expect(page.getByTestId("piping-contract-hash")).toContainText(
      /^sha256:[0-9a-f]{64}$/i,
    );
    await expect(page.getByTestId("piping-artifact-hash")).toContainText(
      /^sha256:[0-9a-f]{64}$/i,
    );
    await expect(page.getByTestId("piping-timeline")).toContainText(/DXF/i);
    await expect(page.getByTestId("piping-summary")).toContainText(/support|clearance/i);
    await expect(page.getByTestId("piping-download")).toBeEnabled();
  });

  test("blocks the official bundle when equipment clearance fails", async ({ page }) => {
    await page.goto("/piping");
    await page.getByTestId("piping-preset-clearance-fail").click();

    const responsePromise = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/v1/piping/designs/run") &&
        response.request().method() === "POST",
    );
    await page.getByTestId("piping-run-verification").click();
    const response = await responsePromise;

    expect(response.ok()).toBeTruthy();
    await expect(page.getByTestId("piping-demo")).toHaveAttribute(
      "data-verification-status",
      "failed",
    );
    await expect(page.getByTestId("piping-demo")).toContainText(
      "DG_PIPE_CLEARANCE_VIOLATION",
    );
    await expect(page.getByTestId("piping-download")).toBeDisabled();
  });
});
