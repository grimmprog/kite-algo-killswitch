/**
 * Scanner API client functions.
 * Handles trend-pullback scans, consolidation patterns, and scan signal history.
 */
import { get, post } from './client';
import type { ScanSignal, ConsolidationPattern, TrendPullbackRequest } from './types';

const BASE = '/api/v1/scanner';

/** Trigger a trend-pullback scan for the configured watchlist. */
export function triggerTrendPullbackScan(request?: TrendPullbackRequest): Promise<ScanSignal[]> {
  return post<ScanSignal[]>(`${BASE}/trend-pullback`, request);
}

/** Get active consolidation patterns for monitored symbols. */
export function getConsolidationPatterns(): Promise<ConsolidationPattern[]> {
  return get<ConsolidationPattern[]>(`${BASE}/consolidation`);
}

/** Get scan signal results/history. */
export function getScanSignals(): Promise<ScanSignal[]> {
  return get<ScanSignal[]>(`${BASE}/signals`);
}
