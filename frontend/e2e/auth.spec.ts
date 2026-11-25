import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

import { createBatch } from "./batches-api";
import { ADMIN_EMAIL, ADMIN_NAME, ADMIN_PASSWORD } from "./session";

const SIGNED_OUT = { cookies: [], origins: [] };

async function signIn(page: Page, email: string, password: string): Promise<void> {
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
}

test.describe("signed out", () => {
  // Opt out of the admin session the global setup saved.
  test.use({ storageState: SIGNED_OUT });

  test("sends a visitor to the login page and back to the page they asked for", async ({ page }) => {
    await page.goto("/batches");
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();

    await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);

    await expect(page).toHaveURL(/\/batches$/);
    await expect(page.getByRole("heading", { level: 2, name: "Batches" })).toBeVisible();
  });

  test("rejects a wrong password with one generic message", async ({ page }) => {
    await page.goto("/login");
    await signIn(page, ADMIN_EMAIL, "not-the-password");

    await expect(page.getByRole("alert")).toHaveText("Incorrect email or password.");
    await expect(page).toHaveURL(/\/login$/);
  });

  test("signs in to the dashboard, shows who is signed in and signs out", async ({ page }) => {
    await page.goto("/login");
    await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);

    await expect(page.getByRole("heading", { level: 2, name: "Tanks" })).toBeVisible();
    const account = page.getByRole("group", { name: "Account" });
    await expect(account).toContainText(ADMIN_NAME);
    await expect(account).toContainText("admin");
    // Live data flows over the WebSocket with the same session.
    await expect(page.getByRole("status", { name: "Connection: Live" })).toBeVisible({ timeout: 20_000 });

    await account.getByRole("button", { name: "Sign out" }).click();
    await expect(page).toHaveURL(/\/login$/);

    // The session is gone for good: protected pages bounce back to the login page.
    await page.goto("/");
    await expect(page).toHaveURL(/\/login$/);
  });
});

test.describe("roles", () => {
  test("an admin creates a viewer, who must change the temporary password and then cannot write", async ({
    page,
    browser,
    baseURL,
    request,
  }, testInfo) => {
    test.skip(testInfo.project.name === "mobile", "shared user and batch state: desktop only");
    const stamp = Date.now();
    const email = `viewer-${stamp}@example.com`;
    const name = `Viewer ${stamp}`;
    const temporary = "temporary-pass-1";
    const chosen = "a-better-password-1";
    const batch = await createBatch(request, `Viewer check ${stamp}`, {
      temperature_min: 15,
      temperature_max: 25,
      pressure_max: 10,
    });

    // The admin (signed in by the global setup) creates the user from the Users page.
    await page.goto("/");
    await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Users" }).click();
    await expect(page.getByRole("heading", { level: 2, name: "Users" })).toBeVisible();
    await page.getByRole("button", { name: "New user" }).click();
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Display name").fill(name);
    await page.getByLabel("Temporary password").fill(temporary);
    await page.getByRole("button", { name: "Create user" }).click();
    const row = page.getByRole("listitem", { name });
    await expect(row).toBeVisible();
    await expect(row).toContainText("Must change password");

    // The viewer, in a browser of their own, is held on the change-password page.
    const context = await browser.newContext({ baseURL, storageState: SIGNED_OUT });
    const viewer = await context.newPage();
    try {
      await viewer.goto("/");
      await signIn(viewer, email, temporary);
      await expect(viewer).toHaveURL(/\/account\/password$/);
      await expect(viewer.getByText(/temporary password/i).first()).toBeVisible();
      await expect(viewer.getByRole("navigation", { name: "Main" })).toHaveCount(0);
      await viewer.goto("/batches");
      await expect(viewer).toHaveURL(/\/account\/password$/);

      await viewer.getByLabel("Current password").fill(temporary);
      await viewer.getByLabel("New password", { exact: true }).fill(chosen);
      await viewer.getByLabel("Confirm new password").fill(chosen);
      await viewer.getByRole("button", { name: "Change password" }).click();
      await expect(viewer.getByRole("heading", { level: 2, name: "Tanks" })).toBeVisible();

      // Read-only: the data is there, the write actions are not.
      const nav = viewer.getByRole("navigation", { name: "Main" });
      await expect(nav.getByRole("link", { name: "Users" })).toHaveCount(0);
      await nav.getByRole("link", { name: "Batches" }).click();
      await expect(viewer.getByRole("heading", { level: 2, name: "Batches" })).toBeVisible();
      await expect(viewer.getByRole("link", { name: "New batch" })).toHaveCount(0);

      await viewer.goto(`/batches/${batch.id}`);
      await expect(viewer.getByRole("heading", { level: 2, name: `Viewer check ${stamp}` })).toBeVisible();
      await expect(viewer.getByRole("button", { name: "Start batch" })).toHaveCount(0);
      await expect(viewer.getByRole("button", { name: "Save changes" })).toHaveCount(0);
      await expect(viewer.getByLabel("Beer name")).toBeDisabled();

      await viewer.goto("/batches/new");
      await expect(viewer.getByRole("heading", { name: "Not allowed" })).toBeVisible();
      await viewer.goto("/users");
      await expect(viewer.getByRole("heading", { name: "Not allowed" })).toBeVisible();
    } finally {
      await context.close();
    }
  });
});
