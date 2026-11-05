import { expect, test } from "@playwright/test";

import { TANK_IDS } from "./tanks";

test.describe("tanks overview", () => {
  test("lists the simulated tanks with their latest readings and goes live", async ({ page }) => {
    await page.goto("/");

    const tanks = page.getByRole("list", { name: "Tanks" });
    for (const id of TANK_IDS) {
      const card = tanks.getByRole("listitem").filter({ has: page.getByRole("link", { name: id }) });
      await expect(card).toBeVisible();
      await expect(card.getByText("Temperature")).toBeVisible();
      await expect(card.getByText("Pressure")).toBeVisible();
      await expect(card.getByText("Alcohol")).toBeVisible();
      await expect(card.getByText(/°C/)).toBeVisible();
      await expect(card.getByText(/\bbar\b/)).toBeVisible();
      await expect(card.getByText(/% ABV/)).toBeVisible();
    }

    await expect(page.getByRole("status", { name: "Connection: Live" })).toBeVisible({ timeout: 20_000 });
  });

  test("updates a card without reloading the page", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("status", { name: "Connection: Live" })).toBeVisible({ timeout: 20_000 });

    const card = page
      .getByRole("list", { name: "Tanks" })
      .getByRole("listitem")
      .filter({ has: page.getByRole("link", { name: "tank-1" }) });
    const updated = card.locator("time").first();
    await expect(updated).toBeVisible();
    const before = await updated.getAttribute("datetime");
    expect(before).not.toBeNull();

    // A new reading must arrive over the WebSocket; the page is never reloaded.
    await expect
      .poll(async () => card.locator("time").first().getAttribute("datetime"), { timeout: 30_000 })
      .not.toBe(before);
  });
});

test.describe("tank detail", () => {
  test("renders the header, range selector and three charts", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("link", { name: "tank-1" }).click();

    await expect(page).toHaveURL(/\/tanks\/tank-1$/);
    await expect(page.getByRole("heading", { name: "tank-1" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Back to tanks" })).toBeVisible();
    await expect(page.getByRole("radiogroup", { name: "Time range" })).toBeVisible();

    for (const title of ["Temperature (°C)", "Pressure (bar)", "Alcohol (% ABV)"]) {
      const chart = page.getByRole("img", { name: `${title} over time` });
      await expect(chart).toBeVisible();
      await expect(chart.locator("canvas")).toBeVisible();
    }
  });

  test("keeps the selected range in the URL", async ({ page }) => {
    await page.goto("/tanks/tank-1");
    await page.getByRole("radiogroup", { name: "Time range" }).getByText("Last hour").click();

    await expect(page).toHaveURL(/\/tanks\/tank-1\?range=1h$/);
    await expect(page.getByRole("radio", { name: "Last hour" })).toBeChecked();
  });

  test("shows a not-found state with a way back for an unknown tank", async ({ page }) => {
    await page.goto("/tanks/nope");

    await expect(page.getByRole("heading", { name: "Tank not found" })).toBeVisible();
    await page.getByRole("link", { name: "Back to tanks" }).click();
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole("list", { name: "Tanks" })).toBeVisible();
  });
});

test.describe("responsive layout", () => {
  test("arranges the tank grid for the viewport", async ({ page }, testInfo) => {
    await page.goto("/");
    const cards = page.getByRole("list", { name: "Tanks" }).getByRole("listitem");
    // At least the expected tanks: the shared stack may hold extra ones; the layout check needs two.
    await expect.poll(() => cards.count()).toBeGreaterThanOrEqual(TANK_IDS.length);

    const first = await cards.nth(0).boundingBox();
    const second = await cards.nth(1).boundingBox();
    expect(first).not.toBeNull();
    expect(second).not.toBeNull();
    if (!first || !second) return;

    if (testInfo.project.name === "mobile") {
      // Single column: the second card sits below the first.
      expect(second.y).toBeGreaterThanOrEqual(first.y + first.height);
    } else {
      // At least two cards share a row.
      expect(Math.abs(second.y - first.y)).toBeLessThan(1);
      expect(second.x).toBeGreaterThan(first.x);
    }
  });
});
