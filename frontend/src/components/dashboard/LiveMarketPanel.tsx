import { useState, useEffect, useCallback, useRef } from 'react';
import { Card } from '../ui/Card';
import { getLiveMarketData } from '../../api/settings';
import type { IndexData, LiveMarketResponse } from '../../api/types';

const POLL_INTERVAL_MS = 30_000; // 30 seconds

/**
 * LiveMarketPanel — Dashboard widget displaying real-time NSE/BSE index values.
 * - Shows NIFTY 50, SENSEX, BANK NIFTY, NIFTY IT with daily change
 * - Green/red coloring based on positive/negative change
 * - Polls every 30 seconds during market hours
 * - Shows "Market Closed" indicator outside market hours
 * - Shows "Data Unavailable" with last successful fetch timestamp on failure
 * - Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7
 */
export function LiveMarketPanel() {
  const [data, setData] = useState<LiveMarketResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastSuccessfulFetch, setLastSuccessfulFetch] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const result = await getLiveMarketData();
      setData(result);
      setError(null);
      setLastSuccessfulFetch(new Date().toLocaleTimeString('en-IN', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      }));
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch market data';
      setError(message);
      // Keep previous data for display, but show error state
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Initial fetch and polling setup
  useEffect(() => {
    fetchData();

    intervalRef.current = setInterval(fetchData, POLL_INTERVAL_MS);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [fetchData]);

  if (isLoading && !data) {
    return (
      <Card title="Live Market">
        <div className="animate-pulse space-y-3" aria-label="Loading market data">
          <div className="h-4 bg-dashboard-border rounded w-3/4" />
          <div className="h-4 bg-dashboard-border rounded w-1/2" />
          <div className="h-4 bg-dashboard-border rounded w-2/3" />
          <div className="h-4 bg-dashboard-border rounded w-1/2" />
        </div>
      </Card>
    );
  }

  // Error state with no data at all
  if (error && !data) {
    return (
      <Card title="Live Market">
        <div className="space-y-2">
          <p className="text-xs text-loss" role="alert">
            Data Unavailable
          </p>
          {lastSuccessfulFetch && (
            <p className="text-[10px] text-dashboard-muted">
              Last updated: {lastSuccessfulFetch}
            </p>
          )}
        </div>
      </Card>
    );
  }

  const marketOpen = data?.market_open ?? false;

  return (
    <Card title="Live Market">
      <div className="space-y-3">
        {/* Market status badge */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <span
              className={`w-2 h-2 rounded-full ${marketOpen ? 'bg-profit' : 'bg-dashboard-muted'}`}
              aria-hidden="true"
            />
            <span
              className={`text-[10px] font-medium ${
                marketOpen ? 'text-profit' : 'text-dashboard-muted'
              }`}
            >
              {marketOpen ? 'Market Open' : 'Market Closed'}
            </span>
          </div>
          {error && (
            <span className="text-[10px] text-amber-400" role="alert">
              Data Unavailable
            </span>
          )}
        </div>

        {/* Error banner with last fetch time */}
        {error && lastSuccessfulFetch && (
          <p className="text-[10px] text-dashboard-muted">
            Last updated: {lastSuccessfulFetch}
          </p>
        )}

        {/* Index values */}
        <div className="space-y-2" role="list" aria-label="Market indices">
          {data?.indices.map((index) => (
            <IndexRow key={index.symbol} index={index} />
          ))}
        </div>
      </div>
    </Card>
  );
}

interface IndexRowProps {
  index: IndexData;
}

function IndexRow({ index }: IndexRowProps) {
  const isPositive = index.change_points >= 0;
  const changeColor = isPositive ? 'text-profit' : 'text-loss';
  const sign = isPositive ? '+' : '';

  return (
    <div
      className="flex items-center justify-between py-1"
      role="listitem"
      aria-label={`${index.symbol}: ${index.value.toLocaleString('en-IN', { minimumFractionDigits: 2 })} ${sign}${index.change_points.toFixed(2)} points (${sign}${index.change_percent.toFixed(2)}%)`}
    >
      <div>
        <p className="text-xs font-medium text-dashboard-text">{index.symbol}</p>
        <p className="text-sm font-mono font-semibold text-dashboard-text">
          {index.value.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </p>
      </div>
      <div className="text-right">
        <p className={`text-xs font-mono font-medium ${changeColor}`}>
          {sign}{index.change_points.toFixed(2)}
        </p>
        <p className={`text-[10px] font-mono ${changeColor}`}>
          {sign}{index.change_percent.toFixed(2)}%
        </p>
      </div>
    </div>
  );
}
