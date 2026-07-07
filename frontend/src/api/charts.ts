/**
 * Charts API client functions.
 * Handles candlestick data with indicators and signal overlays.
 */
import { get } from './client';
import type { ChartData, ChartWithSignal, ChartInterval } from './types';

const BASE = '/api/v1/charts';

/** Get candlestick chart data with EMA, VWAP, MACD indicators. */
export function getChartData(symbol: string, interval?: ChartInterval): Promise<ChartData> {
  const params = interval ? { interval } : undefined;
  return get<ChartData>(`${BASE}/${encodeURIComponent(symbol)}`, params as Record<string, unknown> | undefined);
}

/** Get chart data with a signal overlay (entry/SL markers). */
export function getChartWithSignal(symbol: string, signalId: string): Promise<ChartWithSignal> {
  return get<ChartWithSignal>(`${BASE}/${encodeURIComponent(symbol)}/signal/${signalId}`);
}
