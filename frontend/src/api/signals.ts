/**
 * Signal Approval API client functions.
 * Handles pending signals, approval, rejection, and signal history.
 */
import { get, post } from './client';
import type { TradingSignal, SignalActionResponse } from './types';

const BASE = '/api/v1/signals';

/** Get all pending signals with remaining countdown time. */
export function getPendingSignals(): Promise<TradingSignal[]> {
  return get<TradingSignal[]>(`${BASE}/pending`);
}

/** Approve a signal for trade execution. */
export function approveSignal(signalId: string): Promise<SignalActionResponse> {
  return post<SignalActionResponse>(`${BASE}/${signalId}/approve`);
}

/** Reject and dismiss a signal. */
export function rejectSignal(signalId: string): Promise<SignalActionResponse> {
  return post<SignalActionResponse>(`${BASE}/${signalId}/reject`);
}

/** Get signal history (approved, rejected, expired). */
export function getSignalHistory(): Promise<TradingSignal[]> {
  return get<TradingSignal[]>(`${BASE}/history`);
}
