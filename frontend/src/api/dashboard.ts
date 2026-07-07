/**
 * Dashboard API client functions.
 * Fetches live account data from Kite Connect via backend.
 */
import { get } from './client';
import type { AccountDashboardResponse } from './types';

const DASHBOARD_BASE = '/api/v1/dashboard';

/** Get full account dashboard data (profile, margins, positions, trades, P&L, orders). */
export function getAccountDashboard(): Promise<AccountDashboardResponse> {
  return get<AccountDashboardResponse>(`${DASHBOARD_BASE}/account`);
}

/** Get full account dashboard data from Dhan broker. */
export function getDhanAccountDashboard(): Promise<AccountDashboardResponse> {
  return get<AccountDashboardResponse>(`${DASHBOARD_BASE}/dhan-account`);
}
