import type { APIRequestContext } from "@playwright/test";

import { API_URL } from "./session";

/** Direct API access for test setup and cleanup; the UI under test is never used for these. */

/** Only one batch can be active per tank, and these specs run serially, so they all share this tank. */
export const BATCH_TANK = "tank-1";

export interface ApiBatch {
  id: string;
  version: number;
  status: string;
}

interface TargetsInput {
  temperature_min: number;
  temperature_max: number;
  pressure_max: number;
}

async function ok<T>(response: Awaited<ReturnType<APIRequestContext["get"]>>): Promise<T> {
  if (!response.ok()) throw new Error(`${response.url()} -> ${response.status()} ${await response.text()}`);
  return (await response.json()) as T;
}

export async function createBatch(
  request: APIRequestContext,
  beerName: string,
  targets: TargetsInput,
): Promise<ApiBatch> {
  return ok(
    await request.post(`${API_URL}/batches`, {
      data: { tank_id: BATCH_TANK, beer_name: beerName, style: "E2E", template: "custom", targets },
    }),
  );
}

export async function startBatch(request: APIRequestContext, id: string): Promise<ApiBatch> {
  return ok(await request.post(`${API_URL}/batches/${id}/start`));
}

export async function patchBatch(request: APIRequestContext, id: string, data: object): Promise<ApiBatch> {
  return ok(await request.patch(`${API_URL}/batches/${id}`, { data }));
}

export interface ApiAlert {
  id: string;
  tank_id: string;
  batch_id: string;
  status: string;
  details: { resolution?: string };
}

/** Alerts of one batch in any status. */
export async function listBatchAlerts(request: APIRequestContext, batchId: string): Promise<ApiAlert[]> {
  return ok(
    await request.get(`${API_URL}/alerts?batch_id=${batchId}&status=open&status=acknowledged&status=resolved`),
  );
}

export async function getAlert(request: APIRequestContext, id: string): Promise<ApiAlert> {
  return ok(await request.get(`${API_URL}/alerts/${id}`));
}

/** System-wide unresolved alerts: what the header counter shows (sum of `open_alerts` per tank). */
export async function unresolvedAlertCount(request: APIRequestContext): Promise<number> {
  const tanks = await ok<Array<{ open_alerts: number }>>(await request.get(`${API_URL}/tanks`));
  return tanks.reduce((sum, tank) => sum + tank.open_alerts, 0);
}

/** Finishes whatever is active on the shared tank so the next test starts from a usable state. */
export async function releaseTank(request: APIRequestContext): Promise<void> {
  const active = await ok<ApiBatch[]>(
    await request.get(`${API_URL}/batches`, { params: { tank_id: BATCH_TANK, status: "active" } }),
  );
  for (const batch of active) await ok(await request.post(`${API_URL}/batches/${batch.id}/finish`));
}
