import { readFile } from "node:fs/promises";

import { expect, test } from "@playwright/test";
import type { Download, Page } from "@playwright/test";

import {
  BATCH_TANK,
  createBatch,
  getAlert,
  listBatchAlerts,
  patchBatch,
  releaseTank,
  startBatch,
  unresolvedAlertCount,
} from "./batches-api";
import { adminApiContext } from "./session";

// One active batch per tank and shared tank state: these specs run one after another, and only in the
// desktop project (the mobile one ignores this file, see playwright.config.ts): it would race for the tank.
test.describe.configure({ mode: "serial" });

// Alert thresholds in the e2e stack are short (see README): an alert opens ~15 s after a deviation.
const ALERT_TIMEOUT = 60_000;

// The simulator holds an ale tank near 19 C, so this range can never be met.
const UNATTAINABLE = { temperature_min: 30, temperature_max: 35, pressure_max: 10 };
const ATTAINABLE = { temperature_min: 15, temperature_max: 25, pressure_max: 10 };

const uniqueName = (prefix: string) => `${prefix} ${Date.now()}`;

const tankCard = (page: Page, tankId: string) =>
  page
    .getByRole("list", { name: "Tanks" })
    .getByRole("listitem")
    .filter({ has: page.getByRole("link", { name: tankId, exact: true }) });

const alertsNavLink = (page: Page) => page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: /^Alerts/ });

/** The number in the header pill; 0 when there is none. Capped at "99+" by the UI, far above e2e counts. */
async function navCount(page: Page): Promise<number> {
  const text = (await alertsNavLink(page).textContent()) ?? "";
  return Number(/(\d+)\s*unresolved/.exec(text)?.[1] ?? 0);
}

test.beforeAll(async ({ playwright }) => {
  const request = await adminApiContext(playwright);
  await releaseTank(request);
  await request.dispose();
});

test.afterAll(async ({ playwright }) => {
  const request = await adminApiContext(playwright);
  await releaseTank(request);
  await request.dispose();
});

test("creates a batch from the template, starts it and shows it on the tank", async ({ page, request }) => {
  await releaseTank(request);
  const beer = uniqueName("E2E Ale");
  try {
    await page.goto("/batches");
    await page.getByRole("link", { name: "New batch" }).click();
    await expect(page.getByRole("heading", { name: "New batch" })).toBeVisible();

    await page.getByLabel("Tank").selectOption(BATCH_TANK);
    await page.getByLabel("Template").selectOption("ale");
    // The template pre-fills the editable target ranges.
    await expect(page.getByLabel("Minimum temperature (°C)")).toHaveValue("18");
    await expect(page.getByLabel("Maximum temperature (°C)")).toHaveValue("21");
    await page.getByLabel("Beer name").fill(beer);
    await page.getByLabel("Style").fill("Pale Ale");
    await page.getByRole("button", { name: "Create batch" }).click();

    // Saved: lands on the detail page as a planned batch.
    await expect(page.getByRole("heading", { name: beer })).toBeVisible();
    await expect(page.getByText("Planned", { exact: true })).toBeVisible();

    await page.getByRole("link", { name: "Back to batches" }).click();
    const row = page.getByRole("row").filter({ has: page.getByRole("link", { name: beer }) });
    await expect(row).toContainText("Planned");

    await row.getByRole("link", { name: beer }).click();
    await page.getByRole("button", { name: "Start batch" }).click();
    await expect(page.getByText("Active", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Finish batch" })).toBeVisible();

    // Overview: the active batch is on the tank's card.
    await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Tanks" }).click();
    await expect(tankCard(page, BATCH_TANK).getByRole("link", { name: beer })).toBeVisible();

    // Detail: the batch panel and the target band configured on the chart (drawn on a canvas, so the
    // chart exposes its configured band as `data-target-band`).
    await page.getByRole("link", { name: BATCH_TANK, exact: true }).click();
    const panel = page.getByRole("region", { name: "Active batch" });
    await expect(panel.getByRole("link", { name: beer })).toBeVisible();
    await expect(panel.getByText("18–21 °C", { exact: true })).toBeVisible();
    const temperature = page
      .locator("section[data-target-band]")
      .filter({ has: page.getByRole("heading", { name: "Temperature (°C)" }) });
    await expect(temperature).toHaveAttribute("data-target-band", "18..21");
    await expect(page.locator("section[data-target-band]")).toHaveCount(2); // temperature and pressure
  } finally {
    await releaseTank(request);
  }
});

test.describe("alert lifecycle", () => {
  let batchId = "";
  let alertId = "";
  let baseline = 0; // unresolved alerts system-wide before this batch: other tanks may have their own

  test("opens live, then is acknowledged", async ({ page, request }) => {
    await releaseTank(request);
    await page.goto("/");
    await expect(page.getByRole("status", { name: "Connection: Live" })).toBeVisible({ timeout: 20_000 });
    baseline = await unresolvedAlertCount(request);
    await expect.poll(() => navCount(page)).toBe(baseline);

    // Started through the API while the page stays open: everything below arrives without a reload.
    const batch = await createBatch(request, uniqueName("E2E Alert"), UNATTAINABLE);
    batchId = batch.id;
    await startBatch(request, batch.id);

    await expect.poll(() => navCount(page), { timeout: ALERT_TIMEOUT }).toBe(baseline + 1);
    await expect(tankCard(page, BATCH_TANK).getByRole("link", { name: /unresolved alert/ })).toBeVisible();

    await alertsNavLink(page).click(); // client-side navigation
    await expect(page.getByRole("heading", { name: "Alerts" })).toBeVisible();
    // This test's alert, identified through its batch rather than by text shared with older runs.
    const [opened, ...rest] = await listBatchAlerts(request, batch.id);
    expect(rest).toHaveLength(0);
    expect(opened?.tank_id).toBe(BATCH_TANK);
    alertId = opened!.id;
    const alert = page.locator(`article[data-alert-id="${alertId}"]`);
    await expect(alert).toHaveCount(1);
    await expect(alert).toContainText("Temperature below target");
    await expect(alert).toContainText("Open");

    await alert.getByRole("button", { name: "Acknowledge" }).click();
    await expect(alert).toContainText("Acknowledged");
    await expect(alert.getByRole("button", { name: "Acknowledge" })).toHaveCount(0);
  });

  test("finishing the batch resolves its alert", async ({ page, request }) => {
    test.skip(batchId === "" || alertId === "", "needs the batch and alert from the previous test");
    await page.goto(`/batches/${batchId}`);
    await page.getByRole("button", { name: "Finish batch" }).click();
    await page.getByRole("button", { name: "Yes, finish batch" }).click();
    await expect(page.getByText("Finished", { exact: true })).toBeVisible();

    // Gone from the default (unresolved) list.
    await page.goto(`/alerts?tank=${BATCH_TANK}`);
    await expect(page.getByText("No alerts match these filters")).toBeVisible();

    // Present under Resolved, with the batch-finished note.
    // click + assert (not check()): the URL-driven filter re-renders after the click returns.
    await page.getByRole("checkbox", { name: "Resolved" }).click();
    await expect(page.getByRole("checkbox", { name: "Resolved" })).toBeChecked();
    const resolved = page.locator(`article[data-alert-id="${alertId}"]`);
    await expect(resolved).toContainText("Resolved because the batch was finished");
    const stored = await getAlert(request, alertId);
    expect(stored.status).toBe("resolved");
    expect(stored.details.resolution).toBe("batch_finished");

    // The counters go back to where they were before this batch.
    await page.goto("/");
    await expect(page.getByRole("list", { name: "Tanks" })).toBeVisible();
    await expect.poll(() => navCount(page)).toBe(baseline);
    await expect(tankCard(page, BATCH_TANK).getByRole("link", { name: /unresolved alert/ })).toHaveCount(0);
  });
});

test("warns about a conflicting change when saving a stale batch", async ({ page, request }) => {
  await releaseTank(request);
  try {
    const batch = await createBatch(request, uniqueName("E2E Conflict"), ATTAINABLE);
    const started = await startBatch(request, batch.id);

    await page.goto(`/batches/${batch.id}`);
    const name = page.getByLabel("Beer name");
    await expect(name).not.toHaveValue("");
    await name.fill("Edited in the browser");

    // Someone else saves the same batch first.
    const elsewhere = uniqueName("E2E Elsewhere");
    await patchBatch(request, batch.id, { beer_name: elsewhere, version: started.version });

    await page.getByRole("button", { name: "Save changes" }).click();
    await expect(page.getByText(/changed since you opened it/)).toBeVisible();
    await page.getByRole("button", { name: "Reload batch" }).click();
    await expect(name).toHaveValue(elsewhere);
  } finally {
    await releaseTank(request);
  }
});

// Reports share this file (and its serial mode) because they need the one tank too.
async function contentOf(download: Download): Promise<Buffer> {
  const path = await download.path();
  return readFile(path);
}

test("downloads the PDF and CSV reports of a batch, partial while active and complete once finished", async ({
  page,
  request,
}) => {
  await releaseTank(request);
  const beer = `E2E Report ${Date.now()}`;
  try {
    const batch = await createBatch(request, beer, ATTAINABLE);
    await page.goto(`/batches/${batch.id}`);
    await expect(page.getByRole("heading", { name: beer })).toBeVisible();
    // Planned batches have no report yet.
    await expect(page.getByRole("link", { name: "Download PDF" })).toHaveCount(0);

    await startBatch(request, batch.id);
    await page.reload();
    await expect(page.getByText(/report is partial/i)).toBeVisible();

    await page.getByRole("button", { name: "Finish batch" }).click();
    await page.getByRole("button", { name: "Yes, finish batch" }).click();
    await expect(page.getByText("Finished", { exact: true })).toBeVisible();
    await expect(page.getByText(/report is partial/i)).toHaveCount(0);

    const pdfDownload = page.waitForEvent("download");
    await page.getByRole("link", { name: "Download PDF" }).click();
    const pdf = await pdfDownload;
    expect(pdf.suggestedFilename()).toMatch(/^batch-.*\.pdf$/);
    expect((await contentOf(pdf)).subarray(0, 5).toString("latin1")).toBe("%PDF-");

    const csvDownload = page.waitForEvent("download");
    await page.getByRole("link", { name: "Download CSV" }).click();
    const csv = await csvDownload;
    expect(csv.suggestedFilename()).toMatch(/^batch-.*\.csv$/);
    expect((await contentOf(csv)).toString("utf8")).toContain("Batch summary");
  } finally {
    await releaseTank(request);
  }
});
