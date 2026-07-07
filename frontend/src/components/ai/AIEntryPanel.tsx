import { Card } from '../ui/Card';

interface AIEntryPanelProps {
  scannerEntry: number;
  scannerSl: number;
  aiSuggestedEntry?: number;
  aiSuggestedSl?: string;
  riskRewardDefault?: number;
  riskRewardAi?: number;
  timingRecommendation?: string;
  explanation?: string;
  className?: string;
}

/**
 * Determines if the AI entry differs from the scanner entry by more than 1%.
 */
function hasSignificantDifference(scannerEntry: number, aiEntry: number): boolean {
  if (scannerEntry === 0) return false;
  return Math.abs(aiEntry - scannerEntry) / scannerEntry > 0.01;
}

/**
 * Panel showing AI-suggested entry, SL, and R:R comparison against scanner values.
 * Highlights rows when AI entry differs from scanner entry by > 1%.
 *
 * Validates: Requirements 19.1-19.6
 */
export function AIEntryPanel({
  scannerEntry,
  scannerSl,
  aiSuggestedEntry,
  aiSuggestedSl,
  riskRewardDefault,
  riskRewardAi,
  timingRecommendation,
  explanation,
  className = '',
}: AIEntryPanelProps) {
  const entryDiffers = aiSuggestedEntry != null && hasSignificantDifference(scannerEntry, aiSuggestedEntry);

  return (
    <Card className={className}>
      <div className="space-y-3">
        <h4 className="text-xs font-medium text-dashboard-muted uppercase tracking-wide">
          AI Entry Comparison
        </h4>

        {/* Comparison table */}
        <div className="overflow-hidden rounded-lg border border-dashboard-border">
          <table className="w-full text-sm" role="table" aria-label="Scanner vs AI entry comparison">
            <thead>
              <tr className="border-b border-dashboard-border bg-dashboard-card/50">
                <th className="px-3 py-2 text-left text-xs font-medium text-dashboard-muted">
                  Metric
                </th>
                <th className="px-3 py-2 text-right text-xs font-medium text-dashboard-muted">
                  Scanner
                </th>
                <th className="px-3 py-2 text-right text-xs font-medium text-dashboard-muted">
                  AI Suggested
                </th>
              </tr>
            </thead>
            <tbody>
              {/* Entry price row — highlighted if differs > 1% */}
              <tr
                className={`border-b border-dashboard-border ${
                  entryDiffers
                    ? 'bg-amber-500/10 ring-1 ring-inset ring-amber-500/30'
                    : ''
                }`}
                aria-label={entryDiffers ? 'Entry price differs by more than 1%' : undefined}
              >
                <td className="px-3 py-2 text-dashboard-text font-medium">
                  Entry Price
                  {entryDiffers && (
                    <span className="ml-1.5 text-[10px] font-bold text-amber-400 uppercase">
                      &gt;1% diff
                    </span>
                  )}
                </td>
                <td className="px-3 py-2 text-right font-mono text-dashboard-text">
                  ₹{scannerEntry.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </td>
                <td className="px-3 py-2 text-right font-mono text-dashboard-text">
                  {aiSuggestedEntry != null
                    ? `₹${aiSuggestedEntry.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`
                    : '—'}
                </td>
              </tr>

              {/* Stop Loss row */}
              <tr className="border-b border-dashboard-border">
                <td className="px-3 py-2 text-dashboard-text font-medium">Stop Loss</td>
                <td className="px-3 py-2 text-right font-mono text-dashboard-text">
                  ₹{scannerSl.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </td>
                <td className="px-3 py-2 text-right font-mono text-dashboard-text">
                  {aiSuggestedSl ?? '—'}
                </td>
              </tr>

              {/* Risk:Reward row */}
              <tr>
                <td className="px-3 py-2 text-dashboard-text font-medium">Risk:Reward</td>
                <td className="px-3 py-2 text-right font-mono text-dashboard-text">
                  {riskRewardDefault != null ? `1:${riskRewardDefault.toFixed(2)}` : '—'}
                </td>
                <td className="px-3 py-2 text-right font-mono text-dashboard-text">
                  {riskRewardAi != null ? (
                    <span
                      className={
                        riskRewardAi > (riskRewardDefault ?? 0) ? 'text-green-400' : ''
                      }
                    >
                      1:{riskRewardAi.toFixed(2)}
                    </span>
                  ) : (
                    '—'
                  )}
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        {/* Timing recommendation */}
        {timingRecommendation && (
          <div className="flex items-start gap-2 px-3 py-2 rounded-lg bg-blue-500/10 border border-blue-500/20">
            <span className="text-blue-400 text-sm mt-0.5" aria-hidden="true">⏱</span>
            <div>
              <p className="text-xs font-medium text-blue-300 uppercase tracking-wide">Timing</p>
              <p className="text-sm text-dashboard-text mt-0.5">{timingRecommendation}</p>
            </div>
          </div>
        )}

        {/* AI Explanation */}
        {explanation && (
          <div className="px-3 py-2 rounded-lg bg-dashboard-card/50 border border-dashboard-border">
            <p className="text-xs font-medium text-dashboard-muted uppercase tracking-wide mb-1">
              AI Analysis
            </p>
            <p className="text-sm text-dashboard-text leading-relaxed">{explanation}</p>
          </div>
        )}
      </div>
    </Card>
  );
}
