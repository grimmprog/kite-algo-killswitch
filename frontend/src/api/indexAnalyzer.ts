/**
 * Index Analyzer API client functions.
 * Handles index comparison data and trade recommendations.
 */
import { get } from './client';
import type { IndexMetrics, IndexRecommendation } from './types';

const BASE = '/api/v1/analysis';

/** Fetch index comparison data for SENSEX, NIFTY 50, and BANK NIFTY. */
export function getIndices(): Promise<IndexMetrics[]> {
  return get<IndexMetrics[]>(`${BASE}/indices`);
}

/** Get trade recommendation based on composite scores. */
export function getRecommendation(): Promise<IndexRecommendation> {
  return get<IndexRecommendation>(`${BASE}/recommendation`);
}
