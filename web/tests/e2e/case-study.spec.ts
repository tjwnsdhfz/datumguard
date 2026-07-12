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
    await expect(page.getByText("376", { exact: true })).toBeVisible();
    await expect(page.getByText("35", { exact: true })).toBeVisible();
    await expect(page.getByText("376 pytest + 35 Playwright", { exact: true })).toBeVisible();
    await expect(page.getByText("OpenSees 6/6 + PyG 90 cases", { exact: true })).toBeVisible();
    await expect(page.getByText("30 cases · 330 TP · 0 FP · 0 FN", { exact: true })).toBeVisible();
    await expect(page.getByText(/research_validation_only: true/)).toBeVisible();
    const openBimLink = page
      .getByRole("table", { name: "Implemented engineering workspaces" })
      .getByRole("link", { name: "OpenBIM Evidence" });
    await expect(openBimLink).toHaveAttribute("href", "/openbim");
    await expect(page.getByText(/DG_ARCH_EXTERIOR_OPEN/)).toBeVisible();
    await expect(page.getByText(/계획 중인 100 golden \+ 50 language benchmark/)).toBeVisible();
    const frameActions = page.getByRole("link", { name: "RUN VERIFIED FRAME" });
    await expect(frameActions).toHaveCount(2);
    await expect(frameActions.first()).toHaveAttribute("href", "/frame");
    const architectureActions = page.getByRole("link", { name: "OPEN ARCHITECTURE" });
    await expect(architectureActions).toHaveCount(2);
    await expect(architectureActions.first()).toHaveAttribute("href", "/");
    await expect(page.getByRole("link", { name: "Skip to case study content" })).toHaveAttribute(
      "href",
      "#case-study-content",
    );
    await expect(page.getByRole("link", { name: /Open the v0\.3\.0 release evidence/i })).toHaveAttribute(
      "href",
      /\/releases\/tag\/v0\.3\.0$/,
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
      await expect(screenshots.nth(index)).toHaveAttribute("loading", "lazy");
      await expect(screenshots.nth(index)).toHaveAttribute("sizes", /100vw/);
      await screenshots.nth(index).scrollIntoViewIfNeeded();
      await expect
        .poll(() => screenshots.nth(index).evaluate((image: HTMLImageElement) => image.naturalWidth))
        .toBeGreaterThan(0);
    }

    const workspaceTable = page.getByRole("table", { name: "Implemented engineering workspaces" });
    await expect(workspaceTable.getByRole("link", { name: /Architecture/, exact: false })).toHaveAttribute("href", "/");
  });

  test("keeps the case study accessible and contained across phone, tablet, and desktop", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/case-study");

    const skipLink = page.getByRole("link", { name: "Skip to case study content" });
    await page.keyboard.press("Tab");
    await expect(skipLink).toBeFocused();

    const navigation = page.getByRole("navigation", { name: "Case study navigation" });
    await expect(navigation).toBeVisible();
    await expect(navigation.getByRole("link", { name: "Method" })).toBeVisible();
    await expect(navigation.getByRole("link", { name: "Evidence" })).toBeVisible();
    await expect(navigation.getByRole("link", { name: "Open Frame" })).toBeVisible();
    const openFrameBox = await navigation.getByRole("link", { name: "Open Frame" }).boundingBox();
    expect(openFrameBox?.height).toBeGreaterThanOrEqual(44);

    const privacyBox = await page.getByRole("link", { name: "PRIVACY / LOCAL DATA" }).boundingBox();
    expect(privacyBox?.height).toBeGreaterThanOrEqual(44);
    const reducedTransitionSeconds = await page
      .getByRole("link", { name: "RUN VERIFIED FRAME" })
      .first()
      .evaluate((element) => Number.parseFloat(getComputedStyle(element).transitionDuration));
    expect(reducedTransitionSeconds).toBeLessThanOrEqual(0.000001);

    const artifactCell = page.locator('[data-label="Artifact"]').first();
    await artifactCell.scrollIntoViewIfNeeded();
    expect(await artifactCell.evaluate((element) => getComputedStyle(element, "::before").content)).toContain("Artifact");

    for (const viewport of [
      { width: 375, height: 812 },
      { width: 768, height: 1024 },
      { width: 1440, height: 960 },
    ]) {
      await page.setViewportSize(viewport);
      const metrics = await page.evaluate(() => ({
        scrollWidth: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
        viewportWidth: window.innerWidth,
      }));
      expect(metrics.scrollWidth).toBeLessThanOrEqual(metrics.viewportWidth);
    }
  });
});
