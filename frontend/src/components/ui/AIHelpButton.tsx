import { useState } from 'react';
import { post, get } from '../../api/client';

type AIContext = 'position' | 'trade' | 'scanner' | 'analysis' | 'general';

interface AIHelpButtonProps {
  context: AIContext;
  data?: Record<string, unknown>;
  className?: string;
}

interface AIResponse {
  analysis?: string;
  recommendation?: string;
  risk_level?: string;
  confidence?: number;
  explanation?: string;
  warnings?: string[];
  narrative?: string;
  [key: string]: unknown;
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
          result = await post<AIResponse>('/api/v1/ai/exit-recommendation', {
            position_data: data,
          });
          break;
        case 'trade':
          result = await post<AIResponse>('/api/v1/ai/entry-suggestion', {
            trade_context: data,
          });
          break;
        case 'scanner':
          result = await post<AIResponse>('/api/v1/ai/analyze-signal', {
            signal_context: data,
          });
          break;
        case 'analysis':
          result = await get<AIResponse>('/api/v1/ai/market-narrative');
          break;
        case 'general':
        default:
          result = await get<AIResponse>('/api/v1/ai/risk-warnings');
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
          {response && (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-purple-400 bg-purple-500/10 px-2 py-0.5 rounded">AI Analysis</span>
                {response.risk_level && (
                  <span className={`text-xs font-medium px-2 py-0.5 rounded ${
                    response.risk_level === 'LOW' ? 'bg-profit/10 text-profit' :
                    response.risk_level === 'HIGH' ? 'bg-loss/10 text-loss' :
                    'bg-yellow-500/10 text-yellow-400'
                  }`}>{response.risk_level}</span>
                )}
                {response.confidence && (
                  <span className="text-xs text-dashboard-muted">
                    {response.confidence}% conf
                  </span>
                )}
              </div>

              {/* Main analysis text */}
              {response.analysis && (
                <p className="text-sm text-dashboard-text leading-relaxed">{response.analysis}</p>
              )}
              {response.recommendation && (
                <p className="text-sm text-dashboard-text leading-relaxed">{response.recommendation}</p>
              )}
              {response.explanation && (
                <p className="text-sm text-dashboard-text leading-relaxed">{response.explanation}</p>
              )}
              {response.narrative && (
                <p className="text-sm text-dashboard-text leading-relaxed">{response.narrative}</p>
              )}

              {/* Warnings */}
              {response.warnings && response.warnings.length > 0 && (
                <div className="bg-loss/5 border border-loss/20 rounded-lg p-2">
                  <p className="text-[10px] uppercase text-loss font-bold mb-1">Warnings</p>
                  {response.warnings.map((w, i) => (
                    <p key={i} className="text-xs text-loss/80">• {w}</p>
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
