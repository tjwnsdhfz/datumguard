import { expect, test } from "@playwright/test";

test.describe("public product case study", () => {
  test("presents the assurance method, evidence, limits, and live reproduction path", async ({
    page,
  }) => {
    const response = await page.goto("/case-study");

    expect(response?.status()).toBe(200);
    await expect(page.getByTestId("case-study")).toBeVisible();
    await expect(
      page.getByRole("heading", { level: 1, name: /cad command success is not accuracy evidence/i }),
    ).toBeVisible();
    await expect(page.getByText("256", { exact: true })).toBeVisible();
    await expect(page.getByText("24", { exact: true })).toBeVisible();
    await expect(page.getByText("256 pytest + 24 Playwright", { exact: true })).toBeVisible();
    await expect(page.getByText(/DG_ARCH_EXTERIOR_OPEN/)).toBeVisible();
    await expect(page.getByText(/계획 중인 100 golden \+ 50 language benchmark/)).toBeVisible();
    await expect(page.getByRole("link", { name: "OPEN LIVE ARCHITECTURE" })).toHaveAttribute(
      "href",
      "/",
    );
    await expect(page.locator('link[rel="canonical"]')).toHaveAttribute(
      "href",
      "https://datumguard-tjwnsdhfz.vercel.app/case-study",
    );
    await expect(page.locator('meta[property="og:image"]')).toHaveAttribute(
      "content",
      /\/opengraph-image/,
    );
    await expect(page.locator('meta[name="twitter:image"]')).toHaveAttribute(
      "content",
      /\/opengraph-image/,
    );

    const screenshots = page.getByTestId("case-study").locator("img");
    await expect(screenshots).toHaveCount(3);
    for (let index = 0; index < 3; index += 1) {
      await screenshots.nth(index).scrollIntoViewIfNeeded();
      await expect
        .poll(() => screenshots.nth(index).evaluate((image: HTMLImageElement) => image.naturalWidth))
        .toBeGreaterThan(0);
    }
  });

  test("keeps the case study navigation and evidence within a 390 px viewport", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/case-study");

    const navigation = page.getByRole("navigation", { name: "Case study navigation" });
    await expect(navigation).toBeVisible();
    await expect(navigation.getByRole("link", { name: "Method" })).toBeVisible();
    await expect(navigation.getByRole("link", { name: "Evidence" })).toBeVisible();
    await expect(navigation.getByRole("link", { name: "Open CAD" })).toBeVisible();

    const metrics = await page.evaluate(() => ({
      scrollWidth: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
      viewportWidth: window.innerWidth,
    }));
    expect(metrics.scrollWidth).toBeLessThanOrEqual(metrics.viewportWidth);
  });
});
