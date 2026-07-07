/**
 * Position Monitor API client functions.
 * Handles monitored positions, exit rules, manual exits, and monitor toggling.
 */
import { get, post, put } from './client';
import type {
  MonitoredPosition,
  ExitCondition,
  ManualExitRequest,
  MonitorToggleRequest,
  MonitorToggleResponse,
} from './types';

const BASE = '/api/v1/positions';

/** Get all monitored positions with SL/Target status. */
export function getMonitoredPositions(): Promise<MonitoredPosition[]> {
  return get<MonitoredPosition[]>(`${BASE}/monitor`);
}

/** Get exit conditions for a specific position. */
export function getExitRules(positionId: number): Promise<ExitCondition[]> {
  return get<ExitCondition[]>(`${BASE}/${positionId}/exit-rules`);
}

/** Manually exit a position. */
export function exitPosition(positionId: number, request?: ManualExitRequest): Promise<{ success: boolean; message: string }> {
  return post<{ success: boolean; message: string }>(`${BASE}/${positionId}/exit`, request);
}

/** Start or stop the auto-monitor. */
export function toggleMonitor(request: MonitorToggleRequest): Promise<MonitorToggleResponse> {
  return put<MonitorToggleResponse>('/api/v1/monitor/toggle', request);
}
