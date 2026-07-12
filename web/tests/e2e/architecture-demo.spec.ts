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
  await source.evaluate((element) => {
    const root = document.documentElement;
    const previousBehavior = root.style.scrollBehavior;
    root.style.scrollBehavior = "auto";
    element.scrollIntoView({ block: "center", inline: "center", behavior: "auto" });
    root.style.scrollBehavior = previousBehavior;
  });
  await expect.poll(async () => (await source.boundingBox())?.y ?? 0).toBeGreaterThan(130);
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
  await expect(demo).toHaveAttribute("data-health-status", "ready", { timeout: 75_000 });
  await expect(page.getByTestId("architecture-run-verification")).toBeEnabled();
}

async function expectNoHorizontalPageOverflow(page: Page) {
  const metrics = await page.evaluate(() => ({
    scrollWidth: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
    viewportWidth: window.innerWidth,
  }));
  expect(metrics.scrollWidth).toBeLessThanOrEqual(metrics.viewportWidth);
}

test.describe("interactive architecture demo", () => {
  test.describe.configure({ timeout: 90_000 });

  test("serves the frontend security policy headers", async ({ page }) => {
    const response = await page.goto("/");
    expect(response).not.toBeNull();
    const headers = response?.headers() || {};
    expect(headers["content-security-policy"]).toContain("object-src 'none'");
    expect(headers["content-security-policy"]).toContain("frame-ancestors 'none'");
    expect(headers["x-content-type-options"]).toBe("nosniff");
    expect(headers["x-frame-options"]).toBe("DENY");
    expect(headers["referrer-policy"]).toBe("strict-origin-when-cross-origin");
  });

  test("is the default four-room route with the exact five-stage assurance flow", async ({ page }) => {
    await page.goto("/");
    const demo = page.getByTestId("architecture-demo");
    await expect(demo).toBeVisible();
    await expect(demo).toHaveAttribute("data-verification-status", "idle");
    await expect(page.getByTestId("architecture-scenario")).toContainText("샘플 선택");
    await expect(page.getByTestId("architecture-scenario")).toContainText("정확한 값 확인");
    await expect(page.getByTestId("architecture-scenario")).toContainText("DXF 재측정");
    await expect(page.getByRole("button", { name: /wall.*후속.*객체 추가는 후속 범위/i })).toBeDisabled();
    await expect(page.getByRole("button", { name: /column.*후속.*객체 추가는 후속 범위/i })).toBeDisabled();
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
    await expect(page.locator('a[href="/plate"]')).toHaveCount(1);
    await expect(page.getByRole("link", { name: "Piping", exact: true })).toHaveAttribute("href", "/piping");
    await expect(page.getByText(/not a certification/i)).toBeVisible();
  });

  test("keeps Architecture navigation and content inside a 375 px viewport", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto("/");

    await page.keyboard.press("Tab");
    await expect(page.getByRole("link", { name: "Skip to engineering workspace" })).toBeFocused();
    await expect(page.getByRole("heading", { level: 1, name: "Architecture accuracy workspace", includeHidden: true })).toHaveCount(1);
    const navigation = page.getByRole("navigation", { name: "Engineering workspaces" });
    await expect(navigation).toBeVisible();
    const activeLink = navigation.getByRole("link", { name: "Architecture", exact: true });
    await expect(activeLink).toHaveAttribute("aria-current", "page");
    await expect(activeLink).toHaveCSS("background-color", "rgb(27, 27, 30)");
    await expect(navigation.getByRole("link", { name: "Piping", exact: true })).toBeVisible();
    await expect(navigation.getByRole("link", { name: "Case Study", exact: true })).toBeVisible();
    await expectNoHorizontalPageOverflow(page);
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
    await page.getByTestId("architecture-inspector-center-x").press("Enter");
    await expect(page.getByTestId("architecture-inspector-center-x")).toHaveValue("8001");
    await page.getByTestId("architecture-undo").click();

    await page.getByRole("button", { name: "wall-service", exact: true }).click();
    await dragBy(page, page.getByTestId("architecture-draggable-wall"), 120, 0);
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
    for (let index = 0; index < 55; index += 1) {
      await xInput.fill(String(4000 + index));
      await xInput.press("Enter");
    }
    await expect(page.getByTestId("architecture-demo")).toHaveAttribute("data-history-depth", "50");
  });

  test("buffers exact numeric input, validates it inline, and commits one undo step", async ({ page }) => {
    await page.goto("/");
    await waitForArchitectureReady(page);
    await page.getByTestId("architecture-preset-studio").click();

    const demo = page.getByTestId("architecture-demo");
    const input = page.getByTestId("architecture-inspector-center-x");
    const initialDepth = Number(await demo.getAttribute("data-history-depth"));

    await input.fill("");
    await expect(demo).toHaveAttribute("data-history-depth", String(initialDepth));
    await expect(page.getByTestId("architecture-run-verification")).toBeDisabled();
    await input.press("Tab");
    await expect(input).toHaveAttribute("aria-invalid", "true");
    await expect(page.getByText("유한한 숫자 값을 입력하세요.")).toBeVisible();
    await expect(page.getByTestId("architecture-snap-select")).toBeDisabled();

    await input.click();
    await input.press("Escape");
    await expect(input).toHaveValue("4000");
    await expect(input).toHaveAttribute("aria-invalid", "false");
    await expect(page.getByTestId("architecture-run-verification")).toBeEnabled();

    await input.fill("");
    await input.press("Tab");
    await page.getByTestId("architecture-preset-studio").click();
    await expect(page.getByTestId("architecture-inspector-center-x")).toHaveValue("4000");
    await expect(page.getByTestId("architecture-snap-select")).toBeEnabled();
    await expect(page.getByTestId("architecture-run-verification")).toBeEnabled();
    const resetDepth = Number(await demo.getAttribute("data-history-depth"));

    const resetInput = page.getByTestId("architecture-inspector-center-x");
    await resetInput.fill("4321");
    await expect(demo).toHaveAttribute("data-history-depth", String(resetDepth));
    await resetInput.press("Enter");
    await expect(resetInput).toHaveValue("4321");
    await expect(demo).toHaveAttribute("data-history-depth", String(resetDepth + 1));

    await resetInput.fill("4322");
    await resetInput.press("Control+z");
    await expect(demo).toHaveAttribute("data-history-depth", String(resetDepth + 1));
    await resetInput.press("Escape");
  });

  test("polls through a cold start and recovers without reloading", async ({ page }) => {
    let readinessCalls = 0;
    await page.route("**/api/v1/ready", async (route) => {
      readinessCalls += 1;
      await route.fulfill({
        status: readinessCalls < 3 ? 503 : 200,
        contentType: "application/json",
        body: readinessCalls < 3
          ? '{"status":"not_ready","version":"0.2.1"}'
          : '{"status":"ready","version":"0.2.1"}',
      });
    });
    await page.goto("/");
    await expect(page.getByTestId("architecture-health")).toContainText("검증 엔진 준비 중");
    await waitForArchitectureReady(page);
    expect(readinessCalls).toBeGreaterThanOrEqual(3);
    await expect(page.getByTestId("architecture-health")).toContainText("검증 엔진 준비 완료");
  });

  test("restores the exact architecture draft from IndexedDB after reload", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("architecture-preset-studio").click();
    await page.getByTestId("architecture-inspector-center-x").fill("4321");
    await page.getByTestId("architecture-inspector-center-x").press("Enter");
    await page.waitForTimeout(450);
    const metadata = await page.evaluate(async () => {
      const database = await new Promise<IDBDatabase>((resolve, reject) => {
        const request = indexedDB.open("datumguard", 2);
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
      });
      const value = await new Promise<Record<string, unknown>>((resolve, reject) => {
        const request = database.transaction("drafts", "readonly").objectStore("drafts").get("architecture-contract-draft-v1");
        request.onsuccess = () => resolve(request.result as Record<string, unknown>);
        request.onerror = () => reject(request.error);
      });
      database.close();
      return { schemaVersion: value.schemaVersion, updatedAt: value.updatedAt, expiresAt: value.expiresAt };
    });
    expect(metadata.schemaVersion).toBe(2);
    expect(Number(metadata.expiresAt)).toBeGreaterThan(Number(metadata.updatedAt));
    await page.reload();
    await expect(page.getByTestId("architecture-inspector-center-x")).toHaveValue("4321");
    await expect(page.getByTestId("architecture-restore-studio")).toBeVisible();
    await page.getByTestId("architecture-restore-studio").click();
    await expect(page.getByTestId("architecture-inspector-center-x")).toHaveValue("4000");
    await page.getByTestId("architecture-undo").click();
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
    await expect(page.getByTestId("architecture-result-heading")).toBeFocused();
    await expect(page.getByTestId("architecture-verified-badge")).toContainText(/verified \/ pass/i);
    for (const label of ["Contract locked", "DXF written", "DXF reopened", "Remeasured", "Approved"]) {
      await expect(page.getByTestId("verification-timeline")).toContainText(label);
    }
    await expect(page.getByTestId("architecture-contract-hash")).toContainText(/^sha256:[0-9a-f]{64}$/i);
    await expect(page.getByTestId("architecture-artifact-hash")).toContainText(/^sha256:[0-9a-f]{64}$/i);
    await expect(page.getByTestId("verification-summary")).toContainText(/96(?:\.0)?\s*m²/i);
    await expect(page.getByTestId("verification-summary")).toContainText(/4/);
    await expect(page.getByTestId("architecture-download")).toBeEnabled();

    const pendingInput = page.getByTestId("architecture-inspector-center-x");
    await pendingInput.fill("4001");
    await expect(page.getByTestId("architecture-demo")).toHaveAttribute("data-verification-status", "idle");
    await expect(page.getByTestId("architecture-download")).toBeDisabled();
    await pendingInput.press("Escape");
    await expect(page.getByTestId("architecture-download")).toBeDisabled();
  });

  test("locks contract-changing controls while independent verification is running", async ({ page }) => {
    await page.goto("/");
    await waitForArchitectureReady(page);
    await page.getByTestId("architecture-preset-studio").click();
    await page.route("**/api/v1/architecture/designs/run", async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 1_000));
      await route.continue();
    });

    await page.getByTestId("architecture-run-verification").click();
    await expect(page.getByTestId("architecture-demo")).toHaveAttribute("data-verification-status", "running");
    await expect(page.getByTestId("architecture-scenario-valid")).toBeDisabled();
    await expect(page.getByTestId("architecture-scenario-failure")).toBeDisabled();
    await expect(page.getByTestId("architecture-preset-studio")).toBeDisabled();
    await expect(page.getByTestId("architecture-inspector-center-x")).toBeDisabled();
    await expect(page.getByTestId("architecture-snap-select")).toBeDisabled();
    await expect(page.getByTestId("architecture-demo")).toHaveAttribute("data-verification-status", "passed", { timeout: 20_000 });
  });

  test("separates a verification request error from design violations", async ({ page }) => {
    await page.goto("/");
    await waitForArchitectureReady(page);
    await page.route("**/api/v1/architecture/designs/run", async (route) => {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "temporary verification outage" }),
      });
    });

    await page.getByTestId("architecture-run-verification").click();
    await expect(page.getByTestId("architecture-demo")).toHaveAttribute("data-verification-status", "error");
    await expect(page.getByTestId("architecture-result-heading")).toHaveText("검증 요청 실패");
    await expect(page.getByTestId("architecture-verified-badge")).toContainText("REQUEST ERROR");
    await expect(page.locator(".arch-result-announcement")).not.toContainText("0개 위반");
    await expect(page.getByTestId("architecture-summary-dimensions")).toHaveText("—");
    await expect(page.getByTestId("architecture-summary-violations")).toHaveText("—");
    await expect(page.getByTestId("architecture-summary-walls")).toHaveText("—");
    await expect(page.getByTestId("architecture-summary-rooms")).toHaveText("—");
    await expect(page.getByTestId("architecture-download")).toBeDisabled();
  });

  test("blocks the exact 300 mm open-loop preset", async ({ page }) => {
    await page.goto("/");
    await waitForArchitectureReady(page);
    await page.getByTestId("architecture-preset-invalid").click();
    await expect(page.getByTestId("architecture-inspector-end-x")).toHaveValue("300");
    await page.getByTestId("architecture-run-verification").click();
    await expect(page.getByTestId("architecture-demo")).toHaveAttribute("data-verification-status", "failed", { timeout: 15_000 });
    await expect(page.getByTestId("architecture-result-heading")).toBeFocused();
    await expect(page.getByText("DG_ARCH_EXTERIOR_OPEN")).toBeVisible();
    await expect(page.getByTestId("architecture-download")).toBeDisabled();
    await page.getByRole("button", { name: "wall-north 객체 선택" }).first().click();
    await expect(page.getByTestId("architecture-inspector-end-x")).toBeFocused();
    await expect(page.getByTestId("architecture-inspector-end-x")).toHaveValue("300");
    await page.getByTestId("architecture-repair-open-loop").click();
    await expect(page.getByTestId("architecture-demo")).toHaveAttribute("data-verification-status", "passed", { timeout: 15_000 });
    await expect(page.getByTestId("architecture-inspector-end-x")).toHaveValue("0");
    await expect(page.getByTestId("architecture-download")).toBeEnabled();
  });

  test("keeps exact input, verification, and download usable below 900 px", async ({ page }) => {
    await page.setViewportSize({ width: 820, height: 900 });
    await page.goto("/");
    await waitForArchitectureReady(page);
    await page.getByTestId("architecture-preset-studio").click();
    await expect(page.getByTestId("architecture-canvas")).toHaveCSS("pointer-events", "none");
    await expect(page.getByTestId("architecture-mobile-action")).toBeVisible();
    await page.getByTestId("architecture-mobile-object-select").selectOption("wall-north");
    await expect(page.getByTestId("architecture-inspector-end-x")).toBeVisible();
    await page.getByTestId("architecture-mobile-object-select").selectOption("column-a");
    const centerX = page.getByTestId("architecture-inspector-center-x");
    await centerX.fill("4001");
    await centerX.press("Enter");
    await expect(centerX).toHaveValue("4001");
    await centerX.fill("4000");
    await centerX.press("Enter");
    await page.getByTestId("architecture-run-verification").click();
    await expect(page.getByTestId("architecture-demo")).toHaveAttribute("data-verification-status", "passed", { timeout: 15_000 });
    await expect(page.getByTestId("architecture-download")).toBeEnabled();
    await expect(page.getByTestId("architecture-mobile-action")).toContainText("검증 번들 다운로드");
    await expectNoHorizontalPageOverflow(page);
  });
});

test("keeps the detailed plate designer deep-linkable", async ({ page }) => {
  await page.goto("/plate");
  await expect(page.getByTestId("plate-designer")).toBeVisible();
  await expect(page.getByRole("img", { name: /실시간 형상 미리보기/i })).toBeVisible();
  await expect(page.getByRole("button", { name: /DXF 생성 및 독립 검증/i })).toBeEnabled();
  await expect(page.getByRole("link", { name: /architecture/i })).toHaveAttribute("href", "/");
  await expect(page.getByRole("link", { name: "Piping", exact: true })).toHaveAttribute("href", "/piping");
});

test("keeps Plate navigation usable at phone and tablet widths", async ({ page }) => {
  for (const viewport of [
    { width: 375, height: 812 },
    { width: 768, height: 1024 },
  ]) {
    await page.setViewportSize(viewport);
    await page.goto("/plate");

    const navigation = page.getByRole("navigation", { name: "주요 링크" });
    await expect(navigation).toBeVisible();
    const activeLink = navigation.getByRole("link", { name: "Plate", exact: true });
    await expect(activeLink).toHaveAttribute("aria-current", "page");
    await expect(activeLink).toHaveCSS("background-color", "rgb(27, 27, 30)");
    await expect(navigation.getByRole("link", { name: "Architecture", exact: true })).toBeVisible();
    await expect(navigation.getByRole("link", { name: "Case Study", exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "GitHub source", exact: true })).toBeVisible();
    await expectNoHorizontalPageOverflow(page);
  }
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
