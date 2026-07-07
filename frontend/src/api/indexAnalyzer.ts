/**
 * Index Analyzer API client functions.
 * Handles index comparison data and trade recommendations.
 */
import { get } from './client';
import type { IndexMetrics, IndexRecommendation } from './types';

const BASE = '/api/v1/analysis';

/** Fetch index comparison data for SENSEX, NIFTY 50, and BANK NIFTY. */
export async function getIndices(): Promise<IndexMetrics[]> {
  const response = await get<{ indices: IndexMetrics[]; count: number }>(`${BASE}/indices`);
  return Array.isArray(response) ? response : (response.indices || []);
}

/** Get trade recommendation based on composite scores. */
export function getRecommendation(): Promise<IndexRecommendation> {
  return get<IndexRecommendation>(`${BASE}/recommendation`);
}
