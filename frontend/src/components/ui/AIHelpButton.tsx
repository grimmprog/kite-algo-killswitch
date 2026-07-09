import { useState } from 'react';
import { post, get } from '../../api/client';

type AIContext = 'position' | 'trade' | 'scanner' | 'analysis' | 'general';

interface AIHelpButtonProps {
  context: AIContext;
  data?: Record<string, unknown>;
  className?: string;
}

interface AIResponse {
  success?: boolean;
  data?: Record<string, unknown>;
  analysis?: string;
  recommendation?: string;
  risk_level?: string;
  confidence?: number;
  explanation?: string;
  warnings?: unknown[];
  narrative?: string;
  message?: string;
  quality_rating?: string;
  bias?: string;
  key_points?: string[];
  detailed_analysis?: string;
  reasoning?: string;
  timing_recommendation?: string;
  suggested_entry?: number;
  suggested_sl?: number;
  warning_count?: number;
  has_critical?: boolean;
}

/**
 * Reusable AI help button — shows a sparkle icon, fetches AI analysis
 * for the given context, and displays the result in a popover.
 */
export function AIHelpButton({ context, data, className = '' }: AIHelpButtonProps) {
  const [loading, setLoading] = useState(false);
  const [response, setResponse] = useState<AIResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  const handleClick = async () => {
    if (open && response) {
      setOpen(false);
      return;
    }

    setLoading(true);
    setError(null);
    setOpen(true);

    try {
      let result: AIResponse;

      switch (context) {
        case 'position':
          result = await get<AIResponse>('/api/v1/ai/risk-warnings');
          break;
        case 'trade':
          result = await post<AIResponse>('/api/v1/ai/entry-suggestion', {
            signal_context: data || { symbol: 'NIFTY', action: 'entry' },
            market_data: { bid: 0, ask: 0, vwap: 0 },
          });
          break;
        case 'scanner':
          result = await post<AIResponse>('/api/v1/ai/analyze-signal', {
            signal_context: data || { symbol: 'NIFTY', scan_type: 'trend_pullback' },
          });
          break;
        case 'analysis':
          result = await get<AIResponse>('/api/v1/ai/market-narrative');
          break;
        case 'general':
        default:
          result = await get<AIResponse>('/api/v1/ai/risk-score');
          break;
      }

      setResponse(result);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'AI analysis failed';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  // Unwrap nested response: API returns {success, data, message}
  const displayData: AIResponse | null = response
    ? (response.data && typeof response.data === 'object' && !Array.isArray(response.data)
        ? { ...response, ...(response.data as AIResponse) }
        : response)
    : null;

  return (
    <div className={`relative inline-block ${className}`}>
      {/* AI Button */}
      <button
        onClick={handleClick}
        disabled={loading}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-gradient-to-r from-purple-600 to-blue-600 text-white hover:from-purple-700 hover:to-blue-700 transition-all shadow-sm disabled:opacity-50"
        title="Ask AI for analysis"
      >
        {loading ? (
          <div className="animate-spin h-3.5 w-3.5 border-2 border-white border-t-transparent rounded-full" />
        ) : (
          <svg className="h-3.5 w-3.5" fill="currentColor" viewBox="0 0 20 20">
            <path d="M10 2a1 1 0 011 1v1.323l3.954 1.582 1.599-.8a1 1 0 01.894 1.79l-1.233.616 1.738 5.42a1 1 0 01-.285 1.05A3.989 3.989 0 0115 15a3.989 3.989 0 01-2.667-1.019 1 1 0 01-.285-1.05l1.715-5.349L11 6.477V16h2a1 1 0 110 2H7a1 1 0 110-2h2V6.477L6.237 7.582l1.715 5.349a1 1 0 01-.285 1.05A3.989 3.989 0 015 15a3.989 3.989 0 01-2.667-1.019 1 1 0 01-.285-1.05l1.738-5.42-1.233-.617a1 1 0 01.894-1.788l1.599.799L9 4.323V3a1 1 0 011-1z" />
          </svg>
        )}
        AI
      </button>

      {/* Popover */}
      {open && (response || error) && (
        <div className="absolute right-0 top-full mt-2 w-80 max-h-96 overflow-y-auto z-50 bg-dashboard-card border border-dashboard-border rounded-xl shadow-2xl p-4">
          {/* Close button */}
          <button
            onClick={() => setOpen(false)}
            className="absolute top-2 right-2 text-dashboard-muted hover:text-dashboard-text"
          >
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>

          {/* Error */}
          {error && (
            <div className="text-sm text-loss">{error}</div>
          )}

          {/* AI Response */}
          {displayData && (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-purple-400 bg-purple-500/10 px-2 py-0.5 rounded">AI Analysis</span>
                {displayData.risk_level && (
                  <span className={`text-xs font-medium px-2 py-0.5 rounded ${
                    displayData.risk_level === 'LOW' || displayData.risk_level === 'low' ? 'bg-profit/10 text-profit' :
                    displayData.risk_level === 'HIGH' || displayData.risk_level === 'high' ? 'bg-loss/10 text-loss' :
                    'bg-yellow-500/10 text-yellow-400'
                  }`}>{String(displayData.risk_level).toUpperCase()}</span>
                )}
                {displayData.quality_rating && (
                  <span className={`text-xs font-medium px-2 py-0.5 rounded ${
                    String(displayData.quality_rating).includes('Strong') ? 'bg-profit/10 text-profit' :
                    String(displayData.quality_rating).includes('Avoid') ? 'bg-loss/10 text-loss' :
                    'bg-yellow-500/10 text-yellow-400'
                  }`}>{String(displayData.quality_rating)}</span>
                )}
                {displayData.bias && (
                  <span className={`text-xs font-medium px-2 py-0.5 rounded ${
                    displayData.bias === 'bullish' ? 'bg-profit/10 text-profit' :
                    displayData.bias === 'bearish' ? 'bg-loss/10 text-loss' :
                    'bg-yellow-500/10 text-yellow-400'
                  }`}>{String(displayData.bias).toUpperCase()}</span>
                )}
                {displayData.confidence && (
                  <span className="text-xs text-dashboard-muted">
                    {displayData.confidence}% conf
                  </span>
                )}
              </div>

              {/* Signal analysis: explanation field */}
              {displayData.explanation && (
                <p className="text-sm text-dashboard-text leading-relaxed">{String(displayData.explanation)}</p>
              )}

              {/* Entry suggestion: reasoning + timing */}
              {displayData.reasoning && (
                <p className="text-sm text-dashboard-text leading-relaxed">{String(displayData.reasoning)}</p>
              )}
              {displayData.timing_recommendation && (
                <p className="text-sm font-medium text-blue-400 mt-1">
                  {'⏱ '}{String(displayData.timing_recommendation)}
                </p>
              )}
              {displayData.suggested_entry && (
                <div className="flex gap-3 text-xs mt-1">
                  <span className="text-dashboard-muted">{'Entry: '}<span className="text-dashboard-text font-mono">{'₹'}{String(displayData.suggested_entry)}</span></span>
                  {displayData.suggested_sl && (
                    <span className="text-dashboard-muted">{'SL: '}<span className="text-loss font-mono">{'₹'}{String(displayData.suggested_sl)}</span></span>
                  )}
                </div>
              )}

              {/* Market narrative: key_points array */}
              {displayData.key_points && Array.isArray(displayData.key_points) && (
                <ul className="space-y-1.5">
                  {displayData.key_points.map((point: string, i: number) => (
                    <li key={i} className="text-sm text-dashboard-text leading-relaxed flex gap-2">
                      <span className="text-purple-400 flex-shrink-0">{'•'}</span>
                      <span>{String(point)}</span>
                    </li>
                  ))}
                </ul>
              )}

              {/* Market narrative: detailed_analysis */}
              {displayData.detailed_analysis && (
                <p className="text-xs text-dashboard-muted leading-relaxed mt-2">{String(displayData.detailed_analysis).slice(0, 300)}</p>
              )}

              {/* Generic fields */}
              {displayData.analysis && (
                <p className="text-sm text-dashboard-text leading-relaxed">{String(displayData.analysis)}</p>
              )}
              {displayData.recommendation && (
                <p className="text-sm text-dashboard-text leading-relaxed">{String(displayData.recommendation)}</p>
              )}
              {displayData.narrative && (
                <p className="text-sm text-dashboard-text leading-relaxed">{String(displayData.narrative)}</p>
              )}

              {/* Risk warnings: count indicator */}
              {displayData.warning_count !== undefined && (
                <p className="text-xs text-dashboard-muted">
                  {Number(displayData.warning_count) === 0
                    ? '✅ No active risk warnings'
                    : `⚠️ ${displayData.warning_count} active warning(s)`}
                </p>
              )}

              {/* Fallback message when nothing else rendered */}
              {displayData.message
                && !displayData.analysis && !displayData.recommendation
                && !displayData.explanation && !displayData.narrative
                && !displayData.key_points
                && !displayData.reasoning
                && !displayData.quality_rating
                && displayData.warning_count === undefined && (
                <p className="text-sm text-dashboard-text leading-relaxed">{String(displayData.message)}</p>
              )}

              {/* Warnings array */}
              {displayData.warnings && Array.isArray(displayData.warnings) && displayData.warnings.length > 0 && (
                <div className="bg-loss/5 border border-loss/20 rounded-lg p-2">
                  <p className="text-[10px] uppercase text-loss font-bold mb-1">Warnings</p>
                  {displayData.warnings.map((w: unknown, i: number) => (
                    <p key={i} className="text-xs text-loss/80">{'• '}{typeof w === 'string' ? w : String((w as Record<string, string>)?.message || JSON.stringify(w))}</p>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
