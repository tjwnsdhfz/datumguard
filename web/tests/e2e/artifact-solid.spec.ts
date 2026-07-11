import { expect, test } from "@playwright/test";

function lineDxf(endX: number): Buffer {
  const rows = [
    "0", "SECTION", "2", "HEADER",
    "9", "$ACADVER", "1", "AC1027",
    "9", "$INSUNITS", "70", "4",
    "0", "ENDSEC",
    "0", "SECTION", "2", "TABLES", "0", "ENDSEC",
    "0", "SECTION", "2", "BLOCKS", "0", "ENDSEC",
    "0", "SECTION", "2", "ENTITIES",
    "0", "LINE", "5", "10", "100", "AcDbEntity", "8", "AUDIT",
    "100", "AcDbLine", "10", "0", "20", "0", "30", "0",
    "11", String(endX), "21", "0", "31", "0",
    "0", "ENDSEC", "0", "EOF", "",
  ];
  return Buffer.from(rows.join("\n"), "ascii");
}

test.describe("real CAD artifact and solid workspaces", () => {
  test("audits an uploaded millimetre DXF without mutating the original", async ({ page }) => {
    await page.goto("/intake");
    await expect(page.getByTestId("artifact-lab")).toBeVisible();
    await page.locator("#artifact-file").setInputFiles({
      name: "equipment-layout.dxf",
      mimeType: "application/dxf",
      buffer: lineDxf(1200),
    });
    await page.getByRole("checkbox", { name: /비기밀 CAD/i }).check();

    const responsePromise = page.waitForResponse(
      (response) => response.url().endsWith("/api/v1/artifacts/audit") && response.request().method() === "POST",
    );
    await page.getByTestId("artifact-audit-button").click();
    expect((await responsePromise).ok()).toBeTruthy();

    const results = page.getByTestId("artifact-audit-results");
    await expect(results).toBeVisible();
    await expect(results).toContainText("equipment-layout.dxf");
    await expect(results).toContainText(/sha256:[0-9a-f]{64}/i);
    await expect(results).toContainText("ORIGINAL PRESERVED");
    await expect(results.getByRole("img")).toBeVisible();
  });

  test("compares two DXF revisions by serialized geometry", async ({ page }) => {
    test.slow();
    await page.goto("/intake");
    await page.getByRole("tab", { name: /revision compare/i }).click();
    await page.locator("#baseline-file").setInputFiles({
      name: "baseline.dxf", mimeType: "application/dxf", buffer: lineDxf(1200),
    });
    await page.locator("#candidate-file").setInputFiles({
      name: "candidate.dxf", mimeType: "application/dxf", buffer: lineDxf(1300),
    });
    await page.getByRole("checkbox", { name: /비기밀 CAD/i }).check();

    const responsePromise = page.waitForResponse(
      (response) => response.url().endsWith("/api/v1/artifacts/compare") && response.request().method() === "POST",
    );
    await page.getByTestId("artifact-compare-button").click();
    expect((await responsePromise).ok()).toBeTruthy();

    const results = page.getByTestId("artifact-compare-results");
    await expect(results).toBeVisible();
    await expect(results).toContainText("CHANGED");
    await expect(results).toContainText("Added geometry");
    await expect(results).toContainText("Removed geometry");
  });

  test("generates and independently reimports a real OpenCascade STEP solid", async ({ page }) => {
    test.slow();
    await page.goto("/solid");
    await expect(page.getByTestId("solid-workspace")).toHaveAttribute("data-run-status", "idle");

    const responsePromise = page.waitForResponse(
      (response) => response.url().endsWith("/api/v1/solid/designs/run") && response.request().method() === "POST",
    );
    await page.getByTestId("solid-run-button").click();
    const response = await responsePromise;
    expect(response.ok()).toBeTruthy();

    await expect(page.getByTestId("solid-workspace")).toHaveAttribute("data-run-status", "passed", { timeout: 30_000 });
    await expect(page.getByTestId("cad-mesh-preview")).toBeVisible();
    await expect(page.getByTestId("solid-results")).toContainText("Serialized STEP remeasurement passed");
    await expect(page.getByTestId("solid-results")).toContainText(/sha256:[0-9a-f]{64}/i);
    await expect(page.getByTestId("solid-download-step")).toBeEnabled();
    await expect(page.getByTestId("solid-download-bundle")).toBeEnabled();
  });

  test("supports keyboard tabs and never automatically retries a heavy upload", async ({ page }) => {
    let requests = 0;
    await page.route("**/api/v1/artifacts/audit", async (route) => {
      requests += 1;
      await route.fulfill({
        status: 503,
        headers: {
          "access-control-expose-headers": "Retry-After",
          "content-type": "application/json",
          "retry-after": "2",
        },
        body: JSON.stringify({ error: { code: "DG_BUSY", message: "worker busy" } }),
      });
    });
    await page.goto("/intake");

    const auditTab = page.getByRole("tab", { name: /single file audit/i });
    await auditTab.focus();
    await page.keyboard.press("ArrowRight");
    await expect(page.getByRole("tab", { name: /revision compare/i })).toHaveAttribute("aria-selected", "true");
    await page.keyboard.press("Home");
    await expect(auditTab).toHaveAttribute("aria-selected", "true");

    await page.locator("#artifact-file").setInputFiles({
      name: "busy.dxf", mimeType: "application/dxf", buffer: lineDxf(1200),
    });
    await page.getByRole("checkbox", { name: /비기밀 CAD/i }).check();
    await page.getByTestId("artifact-audit-button").click();
    await expect(page.locator(".lab-error")).toContainText(/약 2초 후.*수동으로 다시 시도/);
    await page.waitForTimeout(2_300);
    expect(requests).toBe(1);
  });

  test("publishes the upload and browser-draft privacy controls", async ({ page }) => {
    await page.goto("/privacy");
    await expect(page.getByRole("heading", { name: /비기밀 CAD만/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Oregon에서 일시 처리" })).toBeVisible();
    await expect(page.getByRole("button", { name: /로컬 draft 삭제/i })).toBeVisible();
  });
});
