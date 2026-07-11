import { expect, test, type Locator, type Page } from "@playwright/test";

async function dragCenterToCenter(page: Page, sourceTestId: string, targetTestId: string) {
  const source = page.getByTestId(sourceTestId);
  const target = page.getByTestId(targetTestId);
  const sourceBox = await source.boundingBox();
  const targetBox = await target.boundingBox();
  expect(sourceBox, `${sourceTestId} must be rendered`).not.toBeNull();
  expect(targetBox, `${targetTestId} must be rendered`).not.toBeNull();
  if (!sourceBox || !targetBox) return;
  await page.mouse.move(sourceBox.x + sourceBox.width / 2, sourceBox.y + sourceBox.height / 2);
  await page.mouse.down();
  await page.mouse.move(targetBox.x + targetBox.width / 2, targetBox.y + targetBox.height / 2, { steps: 12 });
  await page.mouse.up();
}

async function dragBy(
  page: Page,
  source: Locator,
  deltaX: number,
  deltaY: number,
  options: { xFraction?: number; yFraction?: number; shift?: boolean } = {},
) {
  const box = await source.boundingBox();
  expect(box, "drag source must be rendered").not.toBeNull();
  if (!box) return;
  const x = box.x + box.width * (options.xFraction ?? 0.5);
  const y = box.y + box.height * (options.yFraction ?? 0.5);
  if (options.shift) await page.keyboard.down("Shift");
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x + deltaX, y + deltaY, { steps: 10 });
  await page.mouse.up();
  if (options.shift) await page.keyboard.up("Shift");
}

async function waitForArchitectureReady(page: Page) {
  const demo = page.getByTestId("architecture-demo");
  await expect(demo).toHaveAttribute("data-health-status", "ready", { timeout: 45_000 });
  await expect(page.getByTestId("architecture-run-verification")).toBeEnabled();
}

test.describe("interactive architecture demo", () => {
  test("is the default four-room route with the exact five-stage assurance flow", async ({ page }) => {
    await page.goto("/");
    const demo = page.getByTestId("architecture-demo");
    await expect(demo).toBeVisible();
    await expect(demo).toHaveAttribute("data-verification-status", "idle");
    await page.getByTestId("architecture-preset-studio").click();
    await expect(page.getByTestId("architecture-canvas")).toHaveAttribute("data-preset-id", "architecture-studio");
    await expect(page.getByRole("button", { name: /entry \/ reception/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /service \/ utility/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /open studio/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /meeting \/ review/i })).toBeVisible();

    const exactStages = [
      ["contract", "Contract locked"],
      ["writer", "DXF written"],
      ["reopen", "DXF reopened"],
      ["remeasure", "Remeasured"],
      ["gate", "Approved"],
    ] as const;
    for (const [id, label] of exactStages) {
      await expect(page.getByTestId(`architecture-stage-${id}`)).toContainText(label);
    }
    await expect(page.getByRole("link", { name: /플레이트 데모 열기/i })).toHaveAttribute("href", "/plate");
    await expect(page.getByRole("link", { name: /plant piping/i })).toHaveAttribute("href", "/piping");
    await expect(page.getByText(/not a certification/i)).toBeVisible();
  });

  test("supports snapped constrained drag, 1 mm inspector edits, view controls, and capped history", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("architecture-preset-studio").click();

    await dragCenterToCenter(page, "architecture-draggable-column", "architecture-snap-target-center");
    await expect(page.getByTestId("architecture-draggable-column")).toHaveAttribute("data-snap-state", "snapped");
    await expect(page.getByTestId("architecture-inspector-center-x")).toHaveValue("8000");
    await page.getByTestId("architecture-undo").click();
    await expect(page.getByTestId("architecture-inspector-center-x")).toHaveValue("4000");
    await page.getByTestId("architecture-redo").click();
    await expect(page.getByTestId("architecture-inspector-center-x")).toHaveValue("8000");

    await page.getByTestId("architecture-inspector-center-x").fill("8001");
    await expect(page.getByTestId("architecture-inspector-center-x")).toHaveValue("8001");
    await page.getByTestId("architecture-undo").click();

    await page.getByRole("button", { name: "wall-service", exact: true }).click();
    await dragBy(page, page.getByTestId("architecture-draggable-wall"), 42, 0);
    await expect(page.getByTestId("architecture-draggable-wall")).toHaveAttribute("data-snap-state", "snapped");
    const wallStart = Number(await page.getByTestId("architecture-inspector-start-x").inputValue());
    expect(wallStart).not.toBe(0);
    expect(wallStart % 100).toBe(0);
    await page.getByTestId("architecture-undo").click();

    await page.getByRole("button", { name: "wall-service", exact: true }).click();
    await dragBy(page, page.getByTestId("architecture-wall-start-handle"), 25, 30, { shift: true });
    expect(Number(await page.getByTestId("architecture-inspector-start-x").inputValue()) % 10).toBe(0);
    await expect(page.getByTestId("architecture-inspector-start-y")).toHaveValue("4000");

    await page.getByTestId("architecture-preset-studio").click();
    await dragBy(page, page.getByTestId("architecture-draggable-opening"), 40, 0);
    const openingOffset = Number(await page.getByTestId("architecture-inspector-offset").inputValue());
    expect(openingOffset).not.toBe(1200);
    expect(openingOffset % 100).toBe(0);

    await page.getByTestId("architecture-preset-studio").click();
    await dragBy(page, page.getByTestId("architecture-draggable-grid"), 32, 0, { yFraction: 0.25 });
    expect(Number(await page.getByTestId("architecture-inspector-x-offset").inputValue()) % 100).toBe(0);

    const canvas = page.getByTestId("architecture-canvas");
    const fitted = await canvas.getAttribute("viewBox");
    await page.getByTestId("architecture-zoom-in").click();
    await expect(canvas).not.toHaveAttribute("viewBox", fitted || "");
    await page.getByTestId("architecture-fit").click();
    await expect(canvas).toHaveAttribute("viewBox", fitted || "");

    await page.getByTestId("architecture-preset-studio").click();
    const xInput = page.getByTestId("architecture-inspector-center-x");
    for (let index = 0; index < 55; index += 1) await xInput.fill(String(4000 + index));
    await expect(page.getByTestId("architecture-demo")).toHaveAttribute("data-history-depth", "50");
  });

  test("polls through a cold start and recovers without reloading", async ({ page }) => {
    let healthCalls = 0;
    await page.route("**/api/v1/health", async (route) => {
      healthCalls += 1;
      await route.fulfill({ status: healthCalls < 3 ? 503 : 200, contentType: "application/json", body: healthCalls < 3 ? '{"status":"starting"}' : '{"status":"ok"}' });
    });
    await page.goto("/");
    await expect(page.getByTestId("architecture-health")).toContainText("검증 엔진 준비 중");
    await waitForArchitectureReady(page);
    expect(healthCalls).toBeGreaterThanOrEqual(3);
    await expect(page.getByTestId("architecture-health")).toContainText("검증 엔진 준비 완료");
  });

  test("restores the exact architecture draft from IndexedDB after reload", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("architecture-preset-studio").click();
    await page.getByTestId("architecture-inspector-center-x").fill("4321");
    await page.waitForTimeout(450);
    await page.reload();
    await expect(page.getByTestId("architecture-inspector-center-x")).toHaveValue("4321");
  });

  test("verifies the real four-room contract and exposes the exact five-stage evidence", async ({ page }) => {
    await page.goto("/");
    await waitForArchitectureReady(page);
    await page.getByTestId("architecture-preset-studio").click();
    const responsePromise = page.waitForResponse((response) => response.url().endsWith("/api/v1/architecture/designs/run") && response.request().method() === "POST");
    await page.getByTestId("architecture-run-verification").click();
    const response = await responsePromise;
    expect(response.ok()).toBeTruthy();
    const requestBody = response.request().postDataJSON() as { walls: unknown[]; room_seeds: unknown[] };
    expect(requestBody.walls).toHaveLength(7);
    expect(requestBody.room_seeds).toHaveLength(4);
    await expect(page.getByTestId("architecture-demo")).toHaveAttribute("data-verification-status", "passed", { timeout: 15_000 });
    await expect(page.getByTestId("architecture-verified-badge")).toContainText(/verified \/ pass/i);
    for (const label of ["Contract locked", "DXF written", "DXF reopened", "Remeasured", "Approved"]) {
      await expect(page.getByTestId("verification-timeline")).toContainText(label);
    }
    await expect(page.getByTestId("architecture-contract-hash")).toContainText(/^sha256:[0-9a-f]{64}$/i);
    await expect(page.getByTestId("architecture-artifact-hash")).toContainText(/^sha256:[0-9a-f]{64}$/i);
    await expect(page.getByTestId("verification-summary")).toContainText(/96(?:\.0)?\s*m²/i);
    await expect(page.getByTestId("verification-summary")).toContainText(/4/);
    await expect(page.getByTestId("architecture-download")).toBeEnabled();
  });

  test("blocks the exact 300 mm open-loop preset", async ({ page }) => {
    await page.goto("/");
    await waitForArchitectureReady(page);
    await page.getByTestId("architecture-preset-invalid").click();
    await expect(page.getByTestId("architecture-inspector-end-x")).toHaveValue("300");
    await page.getByTestId("architecture-run-verification").click();
    await expect(page.getByTestId("architecture-demo")).toHaveAttribute("data-verification-status", "failed", { timeout: 15_000 });
    await expect(page.getByText("DG_ARCH_EXTERIOR_OPEN")).toBeVisible();
    await expect(page.getByTestId("architecture-download")).toBeDisabled();
  });

  test("keeps exact input, verification, and download usable below 900 px", async ({ page }) => {
    await page.setViewportSize({ width: 820, height: 900 });
    await page.goto("/");
    await waitForArchitectureReady(page);
    await page.getByTestId("architecture-preset-studio").click();
    await expect(page.getByTestId("architecture-canvas")).toHaveCSS("pointer-events", "none");
    const centerX = page.getByTestId("architecture-inspector-center-x");
    await centerX.fill("4001");
    await expect(centerX).toHaveValue("4001");
    await centerX.fill("4000");
    await page.getByTestId("architecture-run-verification").click();
    await expect(page.getByTestId("architecture-demo")).toHaveAttribute("data-verification-status", "passed", { timeout: 15_000 });
    await expect(page.getByTestId("architecture-download")).toBeEnabled();
  });
});

test("keeps the detailed plate designer deep-linkable", async ({ page }) => {
  await page.goto("/plate");
  await expect(page.getByTestId("plate-designer")).toBeVisible();
  await expect(page.getByRole("img", { name: /실시간 형상 미리보기/i })).toBeVisible();
  await expect(page.getByRole("button", { name: /DXF 생성 및 독립 검증/i })).toBeEnabled();
  await expect(page.getByRole("link", { name: /architecture/i })).toHaveAttribute("href", "/");
  await expect(page.getByRole("link", { name: /plant piping/i })).toHaveAttribute("href", "/piping");
});

test("verifies the mechanical and ship plate preset with the real API", async ({ page }) => {
  await page.goto("/plate");
  await page.getByTestId("plate-preset-ship").click();
  await expect(page.getByLabel("프로젝트 이름")).toHaveValue("Ship stiffener bracket plate");
  const responsePromise = page.waitForResponse((response) => response.url().includes("/api/v1/designs/run") && response.request().method() === "POST");
  await page.getByRole("button", { name: /DXF 생성 및 독립 검증/i }).click();
  const response = await responsePromise;
  expect(response.ok()).toBeTruthy();
  await expect(page.getByText("모든 필수 검사를 통과했습니다")).toBeVisible();
  await expect(page.getByRole("button", { name: /검증 ZIP 받기/i })).toBeEnabled();
});
