import { useEffect } from 'react';
import { useScanner } from '../../hooks/useScanner';
import { Card } from '../ui/Card';
import type { ConsolidationPattern } from '../../hooks/useScanner';

/**
 * Displays active consolidation patterns with range high/low, duration,
 * and breakout signals. Receives real-time updates via WebSocket
 * consolidation_update events through the useScanner hook.
 *
 * Validates: Requirements 2.1-2.5
 */
export function ConsolidationPanel() {
  const { consolidations, fetchConsolidations, scanError } = useScanner();

  // Fetch consolidation patterns on mount
  useEffect(() => {
    fetchConsolidations();
  }, [fetchConsolidations]);

  if (scanError) {
    return (
      <Card title="Consolidation Patterns">
        <div className="text-center py-6">
          <p className="text-sm text-loss">{scanError}</p>
        </div>
      </Card>
    );
  }

  if (consolidations.length === 0) {
    return (
      <Card title="Consolidation Patterns">
        <div className="text-center py-8">
          <p className="text-sm text-dashboard-muted">
            No active consolidations detected
          </p>
          <p className="text-xs text-dashboard-muted mt-1">
            Patterns will appear when tight-range consolidations are found on monitored symbols.
          </p>
        </div>
      </Card>
    );
  }

  return (
    <Card title="Consolidation Patterns" subtitle={`${consolidations.length} active`}>
      <div className="space-y-3">
        {consolidations.map((pattern) => (
          <ConsolidationCard key={pattern.symbol} pattern={pattern} />
        ))}
      </div>
    </Card>
  );
}

interface ConsolidationCardProps {
  pattern: ConsolidationPattern;
}

function ConsolidationCard({ pattern }: ConsolidationCardProps) {
  const rangeSpread = pattern.rangeHigh - pattern.rangeLow;
  const spreadPct = pattern.avgPrice > 0
    ? ((rangeSpread / pattern.avgPrice) * 100).toFixed(2)
    : '0.00';

  const isDataUnavailable = pattern.avgPrice === 0 && pattern.candleCount === 0;

  if (isDataUnavailable) {
    return (
      <div
        className="rounded-lg border border-dashboard-border bg-dashboard-card/50 p-4"
        aria-label={`Consolidation pattern for ${pattern.symbol} - data unavailable`}
      >
        <div className="flex items-center justify-between">
          <span className="font-mono font-medium text-dashboard-text">
            {pattern.symbol}
          </span>
          <span className="text-xs px-2 py-0.5 rounded bg-yellow-500/10 text-yellow-400 border border-yellow-500/20">
            Data Unavailable
          </span>
        </div>
        <p className="text-xs text-dashboard-muted mt-2">
          Option data is currently unavailable for this symbol.
        </p>
      </div>
    );
  }

  return (
    <div
      className={`rounded-lg border p-4 transition-colors ${
        pattern.isBreakout
          ? 'border-green-500/50 bg-green-500/5'
          : 'border-dashboard-border bg-dashboard-card/50'
      }`}
      aria-label={`Consolidation pattern for ${pattern.symbol}${pattern.isBreakout ? ' - breakout detected' : ''}`}
    >
      {/* Header row: symbol + breakout badge */}
      <div className="flex items-center justify-between mb-3">
        <span className="font-mono font-medium text-dashboard-text">
          {pattern.symbol}
        </span>
        {pattern.isBreakout ? (
          <span className="text-xs px-2 py-0.5 rounded-full bg-green-500/20 text-green-400 border border-green-500/30 font-medium">
            ⬆ Breakout
          </span>
        ) : (
          <span className="text-xs px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/20">
            Consolidating
          </span>
        )}
      </div>

      {/* Metrics grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <MetricItem label="Range High" value={`₹${pattern.rangeHigh.toFixed(2)}`} />
        <MetricItem label="Range Low" value={`₹${pattern.rangeLow.toFixed(2)}`} />
        <MetricItem label="Avg Price" value={`₹${pattern.avgPrice.toFixed(2)}`} />
        <MetricItem label="Candles" value={String(pattern.candleCount)} />
        <MetricItem label="Duration" value={`${pattern.durationMinutes} min`} />
        <MetricItem label="Spread" value={`${spreadPct}%`} />
      </div>

      {/* Breakout details */}
      {pattern.isBreakout && pattern.breakoutPrice != null && (
        <div className="mt-3 pt-3 border-t border-green-500/20">
          <div className="flex items-center justify-between">
            <span className="text-xs text-dashboard-muted">Breakout Price</span>
            <span className="font-mono text-sm font-medium text-green-400">
              ₹{pattern.breakoutPrice.toFixed(2)}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

interface MetricItemProps {
  label: string;
  value: string;
}

function MetricItem({ label, value }: MetricItemProps) {
  return (
    <div>
      <p className="text-xs text-dashboard-muted">{label}</p>
      <p className="text-sm font-mono text-dashboard-text">{value}</p>
    </div>
  );
}
