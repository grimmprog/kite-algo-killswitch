import { useEffect, useState } from 'react';
import { Card } from '../ui/Card';
import { useAI } from '../../hooks/useAI';
import type { AIMarketNarrative } from '../../hooks/useAI';

interface AIMarketBriefProps {
  className?: string;
}

const biasConfig: Record<string, { label: string; bg: string; text: string; ring: string; icon: string }> = {
  bullish: {
    label: 'Bullish',
    bg: 'bg-green-500/15',
    text: 'text-green-400',
    ring: 'ring-green-500/30',
    icon: '▲',
  },
  bearish: {
    label: 'Bearish',
    bg: 'bg-red-500/15',
    text: 'text-red-400',
    ring: 'ring-red-500/30',
    icon: '▼',
  },
  neutral: {
    label: 'Neutral',
    bg: 'bg-slate-500/15',
    text: 'text-slate-400',
    ring: 'ring-slate-500/30',
    icon: '◆',
  },
};

const sessionLabels: Record<string, string> = {
  morning_brief: 'Morning Brief',
  mid_morning: 'Mid-Morning Update',
  lunch: 'Lunch Update',
  afternoon: 'Afternoon Session',
};

/**
 * AI Market Brief panel displaying the current market narrative.
 *
 * Features:
 * - Session-type header (Morning Brief, Mid-Morning, etc.)
 * - Max 5 key bullet points
 * - Bias indicator (bullish/bearish/neutral)
 * - Expected range (low–high)
 * - Key support/resistance levels
 * - "Read More" expandable for detailed analysis
 * - Real-time updates via ai_market_update WebSocket event
 * - Graceful "AI analysis unavailable" state
 *
 * Validates: Requirements 22.1-22.5
 */
export function AIMarketBrief({ className = '' }: AIMarketBriefProps) {
  const { marketNarrative, fetchMarketNarrative, error } = useAI();
  const [isLoading, setIsLoading] = useState(false);
  const [hasFetched, setHasFetched] = useState(false);
  const [showDetailed, setShowDetailed] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function loadNarrative() {
      setIsLoading(true);
      await fetchMarketNarrative();
      if (!cancelled) {
        setIsLoading(false);
        setHasFetched(true);
      }
    }

    loadNarrative();

    return () => {
      cancelled = true;
    };
  }, [fetchMarketNarrative]);

  // Loading state
  if (isLoading && !hasFetched) {
    return (
      <Card className={className}>
        <div className="space-y-3">
          <h4 className="text-xs font-medium text-dashboard-muted uppercase tracking-wide">
            AI Market Brief
          </h4>
          <div className="flex items-center gap-2 py-4">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-dashboard-muted border-t-transparent" />
            <span className="text-sm text-dashboard-muted">Loading market narrative…</span>
          </div>
        </div>
      </Card>
    );
  }

  // Error / unavailable state
  if ((error && !marketNarrative) || (!marketNarrative && hasFetched)) {
    return (
      <Card className={className}>
        <div className="space-y-3">
          <h4 className="text-xs font-medium text-dashboard-muted uppercase tracking-wide">
            AI Market Brief
          </h4>
          <div className="flex items-center gap-2 px-3 py-3 rounded-lg bg-dashboard-card/50 border border-dashboard-border">
            <span className="text-dashboard-muted" aria-hidden="true">⚡</span>
            <p className="text-sm text-dashboard-muted">AI market narrative unavailable</p>
          </div>
        </div>
      </Card>
    );
  }

  const narrative: AIMarketNarrative = marketNarrative!;
  const bias = biasConfig[narrative.bias] ?? biasConfig.neutral;
  const sessionLabel = sessionLabels[narrative.sessionType] ?? 'Market Update';
  // Enforce max 5 key points as per Requirement 22.5
  const keyPoints = narrative.keyPoints.slice(0, 5);

  return (
    <Card className={className} aria-live="polite" aria-atomic="true">
      <div className="space-y-3">
        {/* Header with session type */}
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-medium text-dashboard-muted uppercase tracking-wide">
            {sessionLabel}
          </h4>
          {/* Bias badge */}
          <span
            className={`
              inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold
              ring-1 ring-inset
              ${bias.bg} ${bias.text} ${bias.ring}
            `}
            role="status"
            aria-label={`Market bias: ${bias.label}`}
          >
            <span aria-hidden="true">{bias.icon}</span>
            <span>{bias.label}</span>
          </span>
        </div>

        {/* Key Points — max 5 bullet points */}
        {keyPoints.length > 0 && (
          <ul className="space-y-1.5" role="list" aria-label="Key market points">
            {keyPoints.map((point, index) => (
              <li
                key={index}
                className="flex items-start gap-2 text-sm text-dashboard-text leading-relaxed"
              >
                <span
                  className="shrink-0 mt-1.5 h-1.5 w-1.5 rounded-full bg-dashboard-muted"
                  aria-hidden="true"
                />
                <span>{point}</span>
              </li>
            ))}
          </ul>
        )}

        {/* Expected Range */}
        <div className="flex items-center gap-3 px-3 py-2 rounded-lg bg-dashboard-card/50 border border-dashboard-border">
          <div className="flex-1">
            <p className="text-xs font-medium text-dashboard-muted uppercase tracking-wide">
              Expected Range
            </p>
            <p className="text-sm font-mono text-dashboard-text mt-0.5">
              ₹{narrative.expectedRange.low.toLocaleString('en-IN')} – ₹{narrative.expectedRange.high.toLocaleString('en-IN')}
            </p>
          </div>
        </div>

        {/* Key Levels — Support & Resistance */}
        <div className="grid grid-cols-2 gap-2">
          {/* Support levels */}
          <div className="px-3 py-2 rounded-lg bg-green-500/5 border border-green-500/15">
            <p className="text-[10px] font-medium text-green-400 uppercase tracking-wide mb-1">
              Support
            </p>
            <div className="flex flex-wrap gap-1.5">
              {narrative.keyLevels.support.map((level, i) => (
                <span
                  key={i}
                  className="text-xs font-mono text-dashboard-text bg-green-500/10 px-1.5 py-0.5 rounded"
                >
                  {level.toLocaleString('en-IN')}
                </span>
              ))}
              {narrative.keyLevels.support.length === 0 && (
                <span className="text-xs text-dashboard-muted">—</span>
              )}
            </div>
          </div>

          {/* Resistance levels */}
          <div className="px-3 py-2 rounded-lg bg-red-500/5 border border-red-500/15">
            <p className="text-[10px] font-medium text-red-400 uppercase tracking-wide mb-1">
              Resistance
            </p>
            <div className="flex flex-wrap gap-1.5">
              {narrative.keyLevels.resistance.map((level, i) => (
                <span
                  key={i}
                  className="text-xs font-mono text-dashboard-text bg-red-500/10 px-1.5 py-0.5 rounded"
                >
                  {level.toLocaleString('en-IN')}
                </span>
              ))}
              {narrative.keyLevels.resistance.length === 0 && (
                <span className="text-xs text-dashboard-muted">—</span>
              )}
            </div>
          </div>
        </div>

        {/* Read More — toggle detailed analysis */}
        {narrative.detailedAnalysis && (
          <div>
            <button
              type="button"
              onClick={() => setShowDetailed(!showDetailed)}
              className="text-xs font-medium text-blue-400 hover:text-blue-300 transition-colors cursor-pointer"
              aria-expanded={showDetailed}
              aria-controls="ai-market-brief-detailed"
            >
              {showDetailed ? 'Show Less' : 'Read More'}
            </button>

            {showDetailed && (
              <div
                id="ai-market-brief-detailed"
                className="mt-2 px-3 py-2.5 rounded-lg bg-dashboard-card/50 border border-dashboard-border"
              >
                <p className="text-sm text-dashboard-text leading-relaxed whitespace-pre-line">
                  {narrative.detailedAnalysis}
                </p>
              </div>
            )}
          </div>
        )}
      </div>
    </Card>
  );
}
