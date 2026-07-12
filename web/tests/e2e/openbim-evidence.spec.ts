import { expect, test, type Page } from "@playwright/test";
import path from "node:path";

const fixtures = path.resolve(process.cwd(), "../fixtures/openbim");
const baselineIfc = path.join(fixtures, "representative/v0_clean.ifc");
const faultyIfc = path.join(fixtures, "representative/v1_faulty.ifc");
const requirementsIds = path.join(fixtures, "virtual_fab_v1.ids");

async function expectNoHorizontalPageOverflow(page: Page) {
  const metrics = await page.evaluate(() => ({
    scrollWidth: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
    viewportWidth: window.innerWidth,
  }));
  expect(metrics.scrollWidth).toBeLessThanOrEqual(metrics.viewportWidth);
}

async function attachVirtualFile(page: Page, testId: string, name: string, size: number) {
  await page.getByTestId(testId).evaluate(
    (node, file) => {
      const transfer = new DataTransfer();
      transfer.items.add(new File([new Uint8Array(file.size)], file.name));
      const input = node as HTMLInputElement;
      input.files = transfer.files;
      input.dispatchEvent(new Event("change", { bubbles: true }));
    },
    { name, size },
  );
}

test.describe("OpenBIM Evidence Guard", () => {
  test("exposes a clear research boundary and remains usable at 375 px", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto("/openbim");

    await expect(page.getByRole("heading", { level: 1, name: /모델을 보는 대신/ })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Engineering workspaces" }).getByRole("link", { name: "OpenBIM" })).toHaveAttribute("aria-current", "page");
    await expect(page.getByText("Research validation only", { exact: false }).first()).toBeVisible();
    await expect(page.getByText(/AI 추론이나 자동 수정 없이/)).toBeVisible();
    await expect(page.getByText(/3D viewer 없이/)).toBeVisible();
    await expect(page.getByTestId("openbim-run")).toBeDisabled();
    await expectNoHorizontalPageOverflow(page);
  });

  test("validates all three files, consent, and the 41 MiB aggregate budget before upload", async ({ page }) => {
    test.setTimeout(60_000);
    await page.goto("/openbim");

    await attachVirtualFile(page, "baseline-input", "baseline.ifc", 20 * 1024 * 1024);
    await attachVirtualFile(page, "candidate-input", "candidate.ifc", 20 * 1024 * 1024);
    await attachVirtualFile(page, "requirements-input", "requirements.ids", 1024 * 1024 + 1);

    await expect(page.getByText(/세 파일의 합계가 41\.0 MB 제한을 초과/)).toBeVisible();
    await expect(page.getByText(/파일이 1\.0 MB 제한을 초과/)).toBeVisible();
    await page.getByRole("checkbox").check();
    await expect(page.getByTestId("openbim-run")).toBeDisabled();
  });

  test("runs the real faulty IFC case and exposes traceable reports", async ({ page }) => {
    test.setTimeout(150_000);
    await page.goto("/openbim");

    await page.getByTestId("baseline-input").setInputFiles(baselineIfc);
    await page.getByTestId("candidate-input").setInputFiles(faultyIfc);
    await page.getByTestId("requirements-input").setInputFiles(requirementsIds);
    await expect(page.getByTestId("baseline-filename")).toContainText("v0_clean.ifc");
    await expect(page.getByTestId("candidate-filename")).toContainText("v1_faulty.ifc");
    await expect(page.getByTestId("requirements-filename")).toContainText("virtual_fab_v1.ids");
    await page.getByRole("checkbox").check();
    await expect(page.getByTestId("openbim-run")).toBeEnabled();

    const responsePromise = page.waitForResponse((response) =>
      response.url().endsWith("/api/v1/openbim/evidence/run") && response.request().method() === "POST",
    );
    await page.getByTestId("openbim-run").click();
    await expect(page.getByTestId("openbim-run")).toContainText("증거 생성 중");
    const response = await responsePromise;
    const responseBody = await response.text();
    expect(response.ok(), responseBody).toBeTruthy();
    const payload = JSON.parse(responseBody) as {
      status: string;
      baseline_hash: string;
      candidate_hash: string;
      ids_hash: string;
      profile_hash: string;
      rule_results: unknown[];
      issues: unknown[];
      reports: Array<{ kind: string }>;
      research_validation_only: boolean;
      approval_eligible: boolean;
    };

    expect(payload.status).toBe("failed_verification");
    expect(payload.research_validation_only).toBe(true);
    expect(payload.approval_eligible).toBe(false);
    expect(payload.rule_results.length).toBeGreaterThan(0);
    expect(payload.issues.length).toBeGreaterThan(0);
    expect(payload.reports.map((report) => report.kind)).toEqual(expect.arrayContaining(["evidence_json", "html", "bcfzip", "manifest"]));
    for (const hash of [payload.baseline_hash, payload.candidate_hash, payload.ids_hash, payload.profile_hash]) {
      expect(hash).toMatch(/^sha256:[0-9a-f]{64}$/);
    }

    await expect(page.getByTestId("openbim-workspace")).toHaveAttribute("data-status", payload.status);
    await expect(page.getByTestId("openbim-results")).toBeVisible();
    await expect(page.getByTestId("openbim-status")).toContainText("검증 실패");
    await expect(page.getByText("IDS-01", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("REV-03", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("GEO-01", { exact: true }).first()).toBeVisible();
    await expect(page.getByText(/각 이슈는 이 네 입력 해시/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Evidence JSON 다운로드" })).toBeEnabled();
    await expect(page.getByRole("button", { name: "검토 보고서 다운로드" })).toBeEnabled();
    await expect(page.getByRole("button", { name: "BCF 이슈 다운로드" })).toBeEnabled();
  });
});
