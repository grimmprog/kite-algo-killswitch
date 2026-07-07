/**
 * System Status API client functions.
 * Handles market hours, session status, worker health, and capital/margin data.
 */
import { get } from './client';
import type { SystemStatus, CapitalStatus } from './types';

const BASE = '/api/v1/status';

/** Get system status: market state, countdown, session, and worker health. */
export function getSystemStatus(): Promise<SystemStatus> {
  return get<SystemStatus>(`${BASE}/system`);
}

/** Get capital and margin breakdown from Zerodha. */
export function getCapitalStatus(): Promise<CapitalStatus> {
  return get<CapitalStatus>(`${BASE}/capital`);
}
