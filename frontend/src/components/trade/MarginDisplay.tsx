import type { MarginEstimateResponse } from '../../api/orders';

interface MarginDisplayProps {
  data: MarginEstimateResponse;
}

/**
 * Displays margin estimation results with a clear pass/fail indicator.
 * Shows required margin, available funds, and shortfall if insufficient.
 */
export function MarginDisplay({ data }: MarginDisplayProps) {
  const formatCurrency = (val: number) =>
    `₹${val.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  return (
    <div
      className={`rounded-lg border p-3 space-y-2 ${
        data.sufficient_funds
          ? 'border-profit/40 bg-profit/5'
          : 'border-loss/40 bg-loss/5'
      }`}
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-dashboard-text">
          Margin Check ({data.broker.toUpperCase()})
        </span>
        <span
          className={`text-xs font-bold px-2 py-0.5 rounded-full ${
            data.sufficient_funds
              ? 'bg-profit/20 text-profit'
              : 'bg-loss/20 text-loss'
          }`}
        >
          {data.sufficient_funds ? '✓ SUFFICIENT' : '✗ INSUFFICIENT'}
        </span>
      </div>

      {/* Details */}
      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="flex justify-between">
          <span className="text-dashboard-muted">Required:</span>
          <span className="font-mono text-dashboard-text">{formatCurrency(data.required_margin)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-dashboard-muted">Available:</span>
          <span className="font-mono text-dashboard-text">{formatCurrency(data.available_margin)}</span>
        </div>
      </div>

      {/* Shortfall warning */}
      {!data.sufficient_funds && data.shortfall > 0 && (
        <div className="flex items-center gap-2 text-xs text-loss bg-loss/10 rounded px-2 py-1.5">
          <svg className="w-3.5 h-3.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
          </svg>
          <span>
            Short by <strong>{formatCurrency(data.shortfall)}</strong> — this order will likely be rejected by the broker.
          </span>
        </div>
      )}

      {/* Breakdown (collapsible) */}
      {data.breakdown && Object.keys(data.breakdown).length > 0 && (
        <details className="text-[10px] text-dashboard-muted">
          <summary className="cursor-pointer hover:text-dashboard-text">View breakdown</summary>
          <div className="mt-1 grid grid-cols-2 gap-1 pl-2">
            {Object.entries(data.breakdown).map(([key, val]) => (
              <div key={key} className="flex justify-between">
                <span>{key}:</span>
                <span className="font-mono">{typeof val === 'number' ? formatCurrency(val) : String(val)}</span>
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
