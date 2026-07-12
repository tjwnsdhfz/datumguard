import { expect, test, type Page } from "@playwright/test";

const PRODUCTION_ORIGIN = "https://datumguard-tjwnsdhfz.vercel.app";
const RELEASE_VERSION = "0.3.0";

async function expectNoHorizontalPageOverflow(page: Page, context: string) {
  const metrics = await page.evaluate(() => ({
    bodyScrollWidth: document.body.scrollWidth,
    documentScrollWidth: document.documentElement.scrollWidth,
    viewportWidth: window.innerWidth,
  }));

  expect(
    Math.max(metrics.bodyScrollWidth, metrics.documentScrollWidth),
    `${context} should not overflow horizontally`,
  ).toBeLessThanOrEqual(metrics.viewportWidth);
}

test.describe("public launch readiness", () => {
  test("publishes route-specific FrameGuard social metadata", async ({ page }) => {
    const response = await page.goto("/frame");

    expect(response?.status()).toBe(200);
    await expect(page).toHaveTitle(
      "FrameGuard | Structural Frame Screening | DatumGuard",
    );
    await expect(page.locator('link[rel="canonical"]')).toHaveAttribute(
      "href",
      `${PRODUCTION_ORIGIN}/frame`,
    );
    await expect(page.locator('meta[property="og:url"]')).toHaveAttribute(
      "content",
      `${PRODUCTION_ORIGIN}/frame`,
    );
    await expect(page.locator('meta[property="og:title"]')).toHaveAttribute(
      "content",
      "FrameGuard | Structural Frame Screening",
    );
    await expect(page.locator('meta[name="twitter:title"]')).toHaveAttribute(
      "content",
      "FrameGuard | Structural Frame Screening",
    );
    await expect(page.locator('meta[property="og:image"]')).toHaveAttribute(
      "content",
      `${PRODUCTION_ORIGIN}/opengraph-image`,
    );
    await expect(page.locator('meta[name="twitter:image"]')).toHaveAttribute(
      "content",
      `${PRODUCTION_ORIGIN}/opengraph-image`,
    );
  });

  test("publishes factual root structured data without ratings or reviews", async ({
    page,
  }) => {
    const response = await page.goto("/");

    expect(response?.status()).toBe(200);
    const structuredData = await page
      .locator('script#datumguard-structured-data[type="application/ld+json"]')
      .textContent();
    expect(structuredData).not.toBeNull();

    const payload = JSON.parse(structuredData ?? "{}") as {
      "@context"?: string;
      "@graph"?: Array<Record<string, unknown>>;
    };
    expect(payload["@context"]).toBe("https://schema.org");
    expect(payload["@graph"]).toBeDefined();

    const graph = payload["@graph"] ?? [];
    expect(graph.map((entry) => entry["@type"])).toEqual([
      "WebSite",
      "WebApplication",
      "SoftwareSourceCode",
      "Person",
    ]);
    const application = graph.find((entry) => entry["@type"] === "WebApplication");
    expect(application).toMatchObject({
      softwareVersion: RELEASE_VERSION,
      isAccessibleForFree: true,
      license: "https://spdx.org/licenses/MIT.html",
    });
    expect(application).not.toHaveProperty("codeRepository");
    const sourceCode = graph.find((entry) => entry["@type"] === "SoftwareSourceCode");
    expect(sourceCode).toMatchObject({
      codeRepository: "https://github.com/tjwnsdhfz/datumguard",
    });
    expect(graph.filter((entry) => "codeRepository" in entry)).toHaveLength(1);

    const serializedGraph = JSON.stringify(graph).toLowerCase();
    expect(serializedGraph).not.toContain("aggregaterating");
    expect(serializedGraph).not.toContain('"review"');
    expect(serializedGraph).not.toContain('"reviews"');
    expect(serializedGraph).not.toContain('"rating"');
  });

  test("advertises only production URLs in robots and sitemap", async ({ request }) => {
    const robotsResponse = await request.get("/robots.txt");
    expect(robotsResponse.status()).toBe(200);
    const robots = await robotsResponse.text();
    expect(robots).toContain("User-Agent: *");
    expect(robots).toContain("Allow: /");
    expect(robots).toContain(`Host: ${PRODUCTION_ORIGIN}`);
    expect(robots).toContain(`Sitemap: ${PRODUCTION_ORIGIN}/sitemap.xml`);
    expect(robots).not.toContain("127.0.0.1");
    expect(robots).not.toContain("localhost");

    const sitemapResponse = await request.get("/sitemap.xml");
    expect(sitemapResponse.status()).toBe(200);
    const sitemap = await sitemapResponse.text();
    const expectedPaths = [
      "/case-study",
      "/",
      "/piping",
      "/frame",
      "/plate",
      "/openbim",
      "/intake",
      "/solid",
      "/privacy",
    ];
    const locations = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map(
      (match) => match[1],
    );

    expect(locations).toEqual(expectedPaths.map((path) => `${PRODUCTION_ORIGIN}${path}`));
    expect(sitemap).toContain("2026-07-13T00:00:00.000Z");
    expect(sitemap).not.toContain("127.0.0.1");
    expect(sitemap).not.toContain("localhost");
  });

  test("returns a real noindex 404 with deterministic recovery routes", async ({ page }) => {
    const response = await page.goto("/this-route-must-not-exist");

    expect(response?.status()).toBe(404);
    await expect(
      page.getByRole("heading", { level: 1, name: "THE DRAWING PATH DOES NOT EXIST." }),
    ).toBeVisible();
    await expect(page.locator('meta[name="robots"][content*="noindex"]')).not.toHaveCount(0);

    const recovery = page.getByRole("navigation", { name: "Recovery routes" });
    await expect(recovery.getByRole("link", { name: /CASE STUDY/ })).toHaveAttribute(
      "href",
      "/case-study",
    );
    await expect(recovery.getByRole("link", { name: /FRAMEGUARD/ })).toHaveAttribute(
      "href",
      "/frame",
    );
    await expect(recovery.getByRole("link", { name: /CAD WORKSPACE/ })).toHaveAttribute(
      "href",
      "/",
    );
  });

  test("discloses pageview analytics and its privacy boundaries", async ({ page }) => {
    const response = await page.goto("/privacy");

    expect(response?.status()).toBe(200);
    await expect(
      page.getByRole("heading", { level: 2, name: "페이지뷰 기준선만 측정" }),
    ).toBeVisible();
    await expect(page.getByText(/custom event를 보내지 않으며/)).toBeVisible();
    await expect(page.getByText(/분석용 cookie를 설정하지 않습니다/)).toBeVisible();
    await expect(
      page.getByText(/설계 payload, 파일명, contract 또는 artifact hash, 좌표, 치수/),
    ).toBeVisible();
    await expect(page.getByText(/별도 앱 내 설정이 없습니다/)).toBeVisible();
    await expect(
      page.getByText(/브라우저 draft의 30일 만료와 분석 보고 기간은 서로 다른 정책/),
    ).toBeVisible();
  });

  test("keeps launch surfaces contained at phone, tablet, and desktop widths", async ({
    page,
  }) => {
    test.setTimeout(60_000);
    await page.route("**/api/v1/ready", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ status: "ready", version: "launch-readiness-e2e" }),
      });
    });

    const routes = ["/", "/frame", "/privacy", "/this-route-must-not-exist"];
    const viewports = [
      { width: 375, height: 812 },
      { width: 768, height: 1024 },
      { width: 1440, height: 960 },
    ];

    for (const viewport of viewports) {
      await page.setViewportSize(viewport);
      for (const route of routes) {
        const response = await page.goto(route);
        expect(response?.status()).toBe(route.includes("must-not-exist") ? 404 : 200);
        await expect(page.locator("main").first()).toBeVisible();
        await expectNoHorizontalPageOverflow(
          page,
          `${route} at ${viewport.width}x${viewport.height}`,
        );
      }
    }
  });
});
