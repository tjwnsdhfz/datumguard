import { expect, test, type Page, type Route } from "@playwright/test";

const CONTRACT_HASH = `sha256:${"a".repeat(64)}`;
const ARTIFACT_HASH = `sha256:${"b".repeat(64)}`;

async function readyEngine(page: Page) {
  await page.route("**/api/v1/ready", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "ready", version: "frame-e2e" }),
    });
  });
}

function frameResponse(status: "passed" | "failed_verification") {
  const passed = status === "passed";
  return {
    status,
    contract_hash: CONTRACT_HASH,
    artifact_hash: ARTIFACT_HASH,
    preview_svg:
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 60"><path d="M10 50V10M60 50V10M110 50V10M10 30H110" fill="none" stroke="#10201a"/></svg>',
    measurements: [
      {
        measurement_id: "frame-max-displacement",
        dimension_id: "max_displacement_mm",
        target: 20,
        actual: passed ? 7.42 : 31.86,
        deviation: passed ? -12.58 : 11.86,
        passed,
      },
    ],
    violations: passed
      ? []
      : [
          {
            code: "DG_FRAME_DISPLACEMENT_EXCEEDED",
            message: "Maximum translation exceeds the configured screening limit.",
            entity_ids: ["N14", "C08"],
            repairable: false,
          },
        ],
    evidence: [{ evidence_id: "solver-run", source: "datumguard_numpy_2d_frame_v1" }],
    summary: {
      max_displacement_mm: passed ? 7.42 : 31.86,
      governing_member_id: passed ? "BR04" : "C08",
      max_utilization: passed ? 0.684 : 1.284,
      node_count: 15,
      member_count: passed ? 26 : 25,
      solver: "datumguard_numpy_2d_frame_v1",
    },
    timeline: [
      { stage: "contract_validation", status: "passed" },
      { stage: "graph_assembly", status: "completed" },
      { stage: "solver_analysis", status: "completed" },
      { stage: "response_verification", status: passed ? "passed" : "failed" },
      { stage: "screening_decision", status: passed ? "approved" : "blocked" },
    ],
    repair_proposals: passed
      ? []
      : [
          {
            id: "restore-brace",
            member_id: "BR04",
            description: "Restore the missing brace and rerun the structural solver.",
          },
        ],
    error: null,
  };
}

async function fulfillFrameRun(route: Route, status: "passed" | "failed_verification") {
  const request = route.request();
  expect(request.method()).toBe("POST");
  expect(new URL(request.url()).searchParams.get("auto_repair")).toBe("false");
  const contract = request.postDataJSON() as {
    design_kind: string;
    nodes: Array<{ point: number[] }>;
    supports: unknown[];
    limits: { max_displacement_mm: number };
  };
  expect(contract.design_kind).toBe("structural_frame");
  expect(contract.nodes).toHaveLength(15);
  expect(contract.nodes[0].point).toEqual([0, 0]);
  expect(contract.supports).toHaveLength(5);
  expect(contract.limits.max_displacement_mm).toBe(0.65);

  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(frameResponse(status)),
  });
}

test.describe("FrameGuard structural screening workspace", () => {
  test.beforeEach(async ({ page }) => {
    await readyEngine(page);
  });

  test("renders the deep-linkable utility rack route", async ({ page }) => {
    await page.goto("/frame");

    await expect(page.getByTestId("frame-workspace")).toBeVisible();
    await expect(page.getByRole("heading", { level: 1, name: "FrameGuard" })).toBeVisible();
    await expect(page.getByText("Structural Frame Screening", { exact: true })).toBeVisible();
    await expect(page.getByTestId("frame-canvas")).toBeVisible();
    await expect(page.getByTestId("frame-preset-verified")).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByTestId("frame-engine-state")).toContainText("SOLVER READY");
  });

  test("switches to the missing-brace failure contract", async ({ page }) => {
    await page.goto("/frame");
    await page.getByTestId("frame-preset-failure").click();

    await expect(page.getByTestId("frame-workspace")).toHaveAttribute("data-preset", "missing-brace");
    await expect(page.getByTestId("frame-preset-failure")).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByLabel("Missing brace BR04")).toBeVisible();
    await expect(page.getByText("25", { exact: true }).first()).toBeVisible();
  });

  test("posts the exact contract and displays solver PASS evidence", async ({ page }) => {
    await page.route("**/api/v1/frame/designs/run?auto_repair=false", (route) =>
      fulfillFrameRun(route, "passed"),
    );
    await page.goto("/frame");
    await page.getByTestId("frame-run-analysis").click();

    await expect(page.getByTestId("frame-workspace")).toHaveAttribute("data-run-status", "passed");
    await expect(page.getByTestId("frame-verdict")).toContainText("SCREENED PASS");
    await expect(page.getByTestId("frame-metrics")).toContainText("7.42");
    await expect(page.getByTestId("frame-metrics")).toContainText("0.684");
    await expect(page.getByTestId("frame-metrics")).toContainText("BR04");
    await expect(page.getByTestId("frame-timeline")).toContainText("Solver executed");
  });

  test("shows violations and keeps repair proposals advisory on FAIL", async ({ page }) => {
    await page.route("**/api/v1/frame/designs/run?auto_repair=false", (route) =>
      fulfillFrameRun(route, "failed_verification"),
    );
    await page.goto("/frame");
    await page.getByTestId("frame-preset-failure").click();
    await page.getByTestId("frame-run-analysis").click();

    await expect(page.getByTestId("frame-workspace")).toHaveAttribute("data-run-status", "failed");
    await expect(page.getByTestId("frame-verdict")).toContainText("REVIEW REQUIRED");
    await expect(page.getByTestId("frame-metrics")).toContainText("31.86");
    await expect(page.getByTestId("frame-violations")).toContainText("DG_FRAME_DISPLACEMENT_EXCEEDED");
    await expect(page.getByTestId("frame-repairs")).toContainText("Restore the missing brace");
  });
});
