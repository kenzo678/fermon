import { readFile } from "node:fs/promises";

import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

import { BATCH_TANK, releaseTank, setTankName } from "./batches-api";
import { adminApiContext } from "./session";

// The thesis flow end to end, as the admin: quality profile -> batch -> lab analysis -> tank name ->
// reports. It needs the shared tank (one active batch per tank) and renames it, which would race with
// the other specs, so it runs in its own project after them (see playwright.config.ts) and only on desktop.

test.beforeAll(async ({ playwright }) => {
  const request = await adminApiContext(playwright);
  await releaseTank(request);
  await setTankName(request, BATCH_TANK, null);
  await request.dispose();
});

test.afterAll(async ({ playwright }) => {
  const request = await adminApiContext(playwright);
  await releaseTank(request);
  await setTankName(request, BATCH_TANK, null);
  await request.dispose();
});

/** Fills the value of the row whose parameter select shows `code` (rows follow the profile's specs). */
async function fillValue(page: Page, code: string, value: string): Promise<void> {
  const selects = page.getByLabel(/^Parameter \d+$/);
  const count = await selects.count();
  for (let index = 0; index < count; index += 1) {
    if ((await selects.nth(index).inputValue()) === code) {
      await page.getByLabel(`Value ${index + 1}`, { exact: true }).fill(value);
      return;
    }
  }
  throw new Error(`no row for parameter ${code}`);
}

test("creates a profile, runs a batch with a lab analysis, renames the tank and downloads the reports", async ({
  page,
}) => {
  const stamp = Date.now();
  const profileName = `E2E Pale lager ${stamp}`;
  const beer = `E2E Thesis ${stamp}`;
  const tankName = `E2E Fermenter ${stamp}`;

  // 1. A quality profile from the pale_lager template.
  await page.goto("/quality-profiles");
  await page.getByRole("button", { name: "New profile" }).click();
  await page.getByLabel("Name").fill(profileName);
  await page.getByLabel("Template").selectOption("pale_lager");
  await page.getByRole("button", { name: "Create profile" }).click();
  await expect(page.getByRole("heading", { level: 2, name: profileName })).toBeVisible();

  // 2. A batch with that profile, started.
  await page.goto("/batches/new");
  await page.getByLabel("Tank").selectOption(BATCH_TANK);
  await page.getByLabel("Template").selectOption("ale");
  await page.getByLabel("Beer name").fill(beer);
  await page.getByLabel("Style").fill("Pale Lager");
  await page.getByLabel("Quality profile").selectOption({ label: profileName });
  await page.getByRole("button", { name: "Create batch" }).click();
  await expect(page.getByRole("heading", { name: beer })).toBeVisible();
  await page.getByRole("button", { name: "Start batch" }).click();
  await expect(page.getByText("Active", { exact: true })).toBeVisible();

  // 3. A brewhouse analysis. With the pale_lager template: original extract 11.4 is inside both the
  // acceptance (10.5-12.5) and internal (11.0-12.0) ranges, pH 5.6 is above the acceptance maximum
  // (5.5), and wort oxygen 7.0 is acceptable (6-14) but under the internal minimum (8).
  await page.getByRole("button", { name: "Record analysis" }).click();
  await page.getByLabel("Stage").selectOption("brewhouse");
  await expect(page.getByLabel(/^Parameter \d+$/)).toHaveCount(6); // the profile's brewhouse specs
  await fillValue(page, "original_extract", "11.4");
  await fillValue(page, "ph", "5.6");
  await fillValue(page, "wort_oxygen", "7.0");
  await page.getByLabel("Analyst").fill("E2E Analyst");
  await page.getByRole("button", { name: "Save analysis" }).click();

  // 4. Each value with its status.
  await expect(page.getByText("Analysis recorded.")).toBeVisible();
  const card = page.getByRole("article").filter({ hasText: "E2E Analyst" });
  const rowOf = (parameter: string) => card.getByRole("row").filter({ has: page.getByRole("rowheader", { name: parameter }) });
  await expect(rowOf("Original extract")).toContainText("In spec");
  await expect(rowOf("pH")).toContainText("Out of spec");
  await expect(rowOf("Wort oxygen")).toContainText("Warning");

  // 5. Rename the tank.
  await page.goto(`/tanks/${BATCH_TANK}`);
  await page.getByRole("button", { name: "Rename" }).click();
  await page.getByLabel("Display name").fill(tankName);
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("heading", { level: 2, name: tankName })).toBeVisible();
  await page.getByRole("link", { name: "Back to tanks" }).click();
  await expect(page.getByRole("list", { name: "Tanks" }).getByRole("link", { name: tankName })).toBeVisible();

  // 6. Finish the batch and download the PDF.
  await page.goto("/batches");
  await page.getByRole("link", { name: beer }).click();
  await page.getByRole("button", { name: "Finish batch" }).click();
  await page.getByRole("button", { name: "Yes, finish batch" }).click();
  await expect(page.getByText("Finished", { exact: true })).toBeVisible();

  const pdfDownload = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download PDF" }).click();
  const pdf = await readFile(await (await pdfDownload).path());
  expect(pdf.subarray(0, 5).toString("latin1")).toBe("%PDF-");

  // 7. The CSV carries the summary only (lab analyses are in the PDF, whose text is compressed).
  const csvDownload = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download CSV" }).click();
  const csv = (await readFile(await (await csvDownload).path())).toString("utf8");
  expect(csv).toContain(beer);
  expect(csv).toContain(profileName);
});
