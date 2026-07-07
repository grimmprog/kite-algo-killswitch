import { useCallback, useEffect, useState } from 'react';
import { DashboardLayout } from '../components/dashboard/DashboardLayout';
import { Card } from '../components/ui/Card';
import { AIHelpButton } from '../components/ui/AIHelpButton';
import { getIndices, getRecommendation } from '../api/indexAnalyzer';
import type { IndexMetrics, IndexRecommendation, TrendDirection } from '../api/types';

/** Returns Tailwind text color class based on trend direction. */
function trendColor(direction: TrendDirection): string {
  switch (direction) {
    case 'bullish':
      return 'text-profit';
    case 'bearish':
      return 'text-loss';
    case 'neutral':
      return 'text-dashboard-muted';
  }
}

/** Returns a human-readable trend label with arrow. */
function trendLabel(direction: TrendDirection): string {
  switch (direction) {
    case 'bullish':
      return '▲ Bullish';
    case 'bearish':
      return '▼ Bearish';
    case 'neutral':
      return '— Neutral';
  }
}

/** Format a percentage value with sign. */
function formatPct(value: number): string {
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(2)}%`;
}

export function AnalysisPage() {
  const [indices, setIndices] = useState<IndexMetrics[]>([]);
  const [recommendation, setRecommendation] = useState<IndexRecommendation | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [indicesData, recData] = await Promise.all([
        getIndices(),
        getRecommendation(),
      ]);
      setIndices(indicesData);
      setRecommendation(recData);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch analysis data';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Page header with refresh */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold text-dashboard-text">Index Analysis</h1>
            <p className="text-xs text-dashboard-muted mt-0.5">
              Compare indices with momentum, volume, and trend scoring
            </p>
          </div>
          <div className="flex items-center gap-2">
            <AIHelpButton context="analysis" />
            <button
              onClick={fetchData}
              disabled={loading}
              className="px-4 py-2 text-sm font-medium rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              aria-label="Refresh analysis data"
            >
              {loading ? 'Refreshing…' : 'Refresh'}
            </button>
          </div>
        </div>

        {/* Error message */}
        {error && (
          <div
            role="alert"
            className="p-3 rounded-lg bg-loss/10 border border-loss/20 text-loss text-sm"
          >
            {error}
          </div>
        )}

        {/* Index comparison table */}
        <Card title="Index Comparison" padding="none">
          <div className="overflow-x-auto">
            <table className="w-full text-sm" aria-label="Index comparison table">
              <thead>
                <tr className="border-b border-dashboard-border">
                  <th className="text-left py-3 px-4 text-xs text-dashboard-muted font-medium">Symbol</th>
                  <th className="text-right py-3 px-4 text-xs text-dashboard-muted font-medium">Current Price</th>
                  <th className="text-right py-3 px-4 text-xs text-dashboard-muted font-medium">1h Change %</th>
                  <th className="text-right py-3 px-4 text-xs text-dashboard-muted font-medium">Daily Change %</th>
                  <th className="text-right py-3 px-4 text-xs text-dashboard-muted font-medium">Momentum</th>
                  <th className="text-right py-3 px-4 text-xs text-dashboard-muted font-medium">Volume</th>
                  <th className="text-center py-3 px-4 text-xs text-dashboard-muted font-medium">Trend</th>
                  <th className="text-right py-3 px-4 text-xs text-dashboard-muted font-medium">Composite Score</th>
                </tr>
              </thead>
              <tbody>
                {loading && indices.length === 0 && (
                  <tr>
                    <td colSpan={8} className="py-8 text-center text-sm text-dashboard-muted">
                      Loading index data…
                    </td>
                  </tr>
                )}
                {!loading && indices.length === 0 && !error && (
                  <tr>
                    <td colSpan={8} className="py-8 text-center text-sm text-dashboard-muted">
                      No index data available
                    </td>
                  </tr>
                )}
                {indices.map((idx) => {
                  const isBest = recommendation?.best_index === idx.symbol;
                  const rowBg = isBest
                    ? 'bg-blue-600/5 border-l-2 border-l-blue-500'
                    : '';

                  if (!idx.data_available) {
                    return (
                      <tr
                        key={idx.symbol}
                        className="border-b border-dashboard-border last:border-0 bg-yellow-500/5"
                      >
                        <td className="py-3 px-4 font-mono text-dashboard-text">
                          {idx.symbol}
                        </td>
                        <td colSpan={7} className="py-3 px-4 text-center">
                          <span
                            className="inline-flex items-center gap-1.5 text-yellow-500 text-xs font-medium"
                            role="alert"
                            aria-label={`Data unavailable for ${idx.symbol}`}
                          >
                            <svg
                              className="w-3.5 h-3.5"
                              fill="currentColor"
                              viewBox="0 0 20 20"
                              aria-hidden="true"
                            >
                              <path
                                fillRule="evenodd"
                                d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.168 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 6a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 6zm0 9a1 1 0 100-2 1 1 0 000 2z"
                                clipRule="evenodd"
                              />
                            </svg>
                            Data unavailable — market data could not be fetched for this index
                          </span>
                        </td>
                      </tr>
                    );
                  }

                  return (
                    <tr
                      key={idx.symbol}
                      className={`border-b border-dashboard-border last:border-0 ${rowBg}`}
                      aria-label={isBest ? `${idx.symbol} — recommended index` : undefined}
                    >
                      <td className="py-3 px-4 font-mono text-dashboard-text font-medium">
                        <span className="flex items-center gap-2">
                          {idx.symbol}
                          {isBest && (
                            <span className="text-[10px] font-semibold uppercase tracking-wide text-blue-400 bg-blue-500/10 px-1.5 py-0.5 rounded">
                              Best
                            </span>
                          )}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-right font-mono text-dashboard-text">
                        ₹{idx.current_price.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </td>
                      <td
                        className={`py-3 px-4 text-right font-mono ${
                          idx.change_1h_pct >= 0 ? 'text-profit' : 'text-loss'
                        }`}
                      >
                        {formatPct(idx.change_1h_pct)}
                      </td>
                      <td
                        className={`py-3 px-4 text-right font-mono ${
                          idx.change_daily_pct >= 0 ? 'text-profit' : 'text-loss'
                        }`}
                      >
                        {formatPct(idx.change_daily_pct)}
                      </td>
                      <td className="py-3 px-4 text-right font-mono text-dashboard-text">
                        {idx.momentum_score.toFixed(1)}
                      </td>
                      <td className="py-3 px-4 text-right font-mono text-dashboard-text">
                        {idx.volume_score.toFixed(1)}
                      </td>
                      <td className={`py-3 px-4 text-center font-medium text-xs ${trendColor(idx.trend_direction)}`}>
                        {trendLabel(idx.trend_direction)}
                      </td>
                      <td className="py-3 px-4 text-right font-mono font-semibold text-dashboard-text">
                        {idx.composite_score.toFixed(1)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>

        {/* Recommendation panel */}
        {recommendation && (
          <Card title="Trade Recommendation">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <div>
                <p className="text-xs text-dashboard-muted mb-1">Best Index</p>
                <p className="text-base font-mono font-semibold text-dashboard-text">
                  {recommendation.best_index}
                </p>
              </div>
              <div>
                <p className="text-xs text-dashboard-muted mb-1">Option Type</p>
                <p
                  className={`text-base font-mono font-semibold ${
                    recommendation.option_type === 'CE' ? 'text-profit' : 'text-loss'
                  }`}
                >
                  {recommendation.option_type}
                </p>
              </div>
              <div>
                <p className="text-xs text-dashboard-muted mb-1">Recommended Strike</p>
                <p className="text-base font-mono font-semibold text-dashboard-text">
                  ₹{recommendation.recommended_strike.toLocaleString('en-IN')}
                </p>
              </div>
              <div>
                <p className="text-xs text-dashboard-muted mb-1">Strike Step</p>
                <p className="text-base font-mono font-semibold text-dashboard-text">
                  {recommendation.strike_step}
                </p>
              </div>
            </div>
            {recommendation.reasoning && (
              <div className="mt-4 pt-4 border-t border-dashboard-border">
                <p className="text-xs text-dashboard-muted mb-1">Reasoning</p>
                <p className="text-sm text-dashboard-text">{recommendation.reasoning}</p>
              </div>
            )}
          </Card>
        )}
      </div>
    </DashboardLayout>
  );
}
