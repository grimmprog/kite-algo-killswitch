import { useEffect, useState, useCallback } from 'react';
import { Card } from '../ui/Card';
import { useAI } from '../../hooks/useAI';
import type { AIRiskWarning } from '../../hooks/useAI';

interface AIRiskBannerProps {
  className?: string;
}

const severityConfig: Record<AIRiskWarning['severity'], { bg: string; border: string; text: string; icon: string; label: string }> = {
  info: {
    bg: 'bg-blue-500/10',
    border: 'border-blue-500/30',
    text: 'text-blue-400',
    icon: 'ℹ',
    label: 'Info',
  },
  warning: {
    bg: 'bg-amber-500/10',
    border: 'border-amber-500/30',
    text: 'text-amber-400',
    icon: '⚠',
    label: 'Warning',
  },
  critical: {
    bg: 'bg-red-500/10',
    border: 'border-red-500/30',
    text: 'text-red-400',
    icon: '🚨',
    label: 'Critical',
  },
};

const categoryLabels: Record<string, string> = {
  market_condition: 'Market Conditions',
  behavioral: 'Behavioral Pattern',
  rule_violation: 'Rule Violation',
};

/**
 * AI Risk Banner component displaying active risk warnings and daily risk score.
 *
 * Features:
 * - "Conditions Unfavorable" prominent banner when critical warnings exist
 * - Behavioral warnings (revenge trading, consecutive losses, etc.)
 * - Risk assessment score (1-10) display
 * - Severity-coded warning cards (info/warning/critical)
 * - Acknowledgment flow for blocking warnings
 * - Real-time updates via ai_risk_warning WebSocket event
 * - Graceful degradation when AI unavailable
 *
 * Validates: Requirements 24.1-24.6
 */
export function AIRiskBanner({ className = '' }: AIRiskBannerProps) {
  const { riskWarnings, riskScore, fetchRiskWarnings, fetchRiskScore, error } = useAI();
  const [isLoading, setIsLoading] = useState(false);
  const [hasFetched, setHasFetched] = useState(false);
  const [acknowledgedIds, setAcknowledgedIds] = useState<Set<number>>(new Set());

  useEffect(() => {
    let cancelled = false;

    async function loadRiskData() {
      setIsLoading(true);
      await Promise.all([fetchRiskWarnings(), fetchRiskScore()]);
      if (!cancelled) {
        setIsLoading(false);
        setHasFetched(true);
      }
    }

    loadRiskData();

    return () => {
      cancelled = true;
    };
  }, [fetchRiskWarnings, fetchRiskScore]);

  const handleAcknowledge = useCallback((index: number) => {
    setAcknowledgedIds((prev) => new Set([...prev, index]));
  }, []);

  // Loading state
  if (isLoading && !hasFetched) {
    return (
      <Card className={className}>
        <div className="space-y-3">
          <h4 className="text-xs font-medium text-dashboard-muted uppercase tracking-wide">
            AI Risk Assessment
          </h4>
          <div className="flex items-center gap-2 py-4">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-dashboard-muted border-t-transparent" />
            <span className="text-sm text-dashboard-muted">Assessing risk conditions…</span>
          </div>
        </div>
      </Card>
    );
  }

  // Error / unavailable state — only show if no data at all
  if (error && riskWarnings.length === 0 && riskScore === null && hasFetched) {
    return (
      <Card className={className}>
        <div className="space-y-3">
          <h4 className="text-xs font-medium text-dashboard-muted uppercase tracking-wide">
            AI Risk Assessment
          </h4>
          <div className="flex items-center gap-2 px-3 py-3 rounded-lg bg-dashboard-card/50 border border-dashboard-border">
            <span className="text-dashboard-muted" aria-hidden="true">⚡</span>
            <p className="text-sm text-dashboard-muted">AI risk assessment unavailable</p>
          </div>
        </div>
      </Card>
    );
  }

  // No warnings and no score — conditions are fine
  if (riskWarnings.length === 0 && riskScore === null && hasFetched) {
    return null;
  }

  const hasCritical = riskWarnings.some((w) => w.severity === 'critical');
  const hasBlockingWarnings = riskWarnings.some(
    (w) => w.requiresAcknowledgment && !acknowledgedIds.has(riskWarnings.indexOf(w))
  );

  // Risk score styling
  const getRiskScoreColor = (score: number) => {
    if (score <= 3) return 'text-green-400';
    if (score <= 5) return 'text-amber-400';
    if (score <= 7) return 'text-orange-400';
    return 'text-red-400';
  };

  const getRiskScoreBg = (score: number) => {
    if (score <= 3) return 'bg-green-500/15 ring-green-500/30';
    if (score <= 5) return 'bg-amber-500/15 ring-amber-500/30';
    if (score <= 7) return 'bg-orange-500/15 ring-orange-500/30';
    return 'bg-red-500/15 ring-red-500/30';
  };

  return (
    <div className={`space-y-3 ${className}`} aria-live="assertive" aria-atomic="false">
      {/* Conditions Unfavorable banner — shown when critical warnings exist */}
      {hasCritical && (
        <div
          className="flex items-center gap-3 px-4 py-3 rounded-xl bg-red-500/10 border border-red-500/30 ring-1 ring-inset ring-red-500/20"
          role="alert"
          aria-label="Market conditions unfavorable"
        >
          <span className="text-lg" aria-hidden="true">🚨</span>
          <div className="flex-1">
            <p className="text-sm font-semibold text-red-400">Conditions Unfavorable</p>
            <p className="text-xs text-dashboard-muted mt-0.5">
              AI has detected elevated risk — review warnings below before trading.
            </p>
          </div>
        </div>
      )}

      <Card>
        <div className="space-y-3">
          {/* Header with risk score */}
          <div className="flex items-center justify-between">
            <h4 className="text-xs font-medium text-dashboard-muted uppercase tracking-wide">
              Risk Assessment
            </h4>
            {riskScore !== null && (
              <span
                className={`
                  inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold
                  ring-1 ring-inset
                  ${getRiskScoreBg(riskScore)} ${getRiskScoreColor(riskScore)}
                `}
                role="status"
                aria-label={`Daily risk score: ${riskScore} out of 10`}
              >
                <span className="font-mono">{riskScore}/10</span>
              </span>
            )}
          </div>

          {/* Risk score bar */}
          {riskScore !== null && (
            <div className="space-y-1">
              <div className="flex justify-between text-[10px] text-dashboard-muted">
                <span>Low Risk</span>
                <span>High Risk</span>
              </div>
              <div className="h-2 w-full rounded-full bg-dashboard-border overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-700 ${
                    riskScore <= 3
                      ? 'bg-green-400'
                      : riskScore <= 5
                        ? 'bg-amber-400'
                        : riskScore <= 7
                          ? 'bg-orange-400'
                          : 'bg-red-400'
                  }`}
                  style={{ width: `${Math.min(100, (riskScore / 10) * 100)}%` }}
                  role="progressbar"
                  aria-valuenow={riskScore}
                  aria-valuemin={1}
                  aria-valuemax={10}
                  aria-label="Risk score"
                />
              </div>
            </div>
          )}

          {/* Warnings list */}
          {riskWarnings.length > 0 && (
            <div className="space-y-2" role="list" aria-label="Active risk warnings">
              {riskWarnings.map((warning, index) => {
                const config = severityConfig[warning.severity];
                const isAcknowledged = acknowledgedIds.has(index);
                const needsAcknowledgment = warning.requiresAcknowledgment && !isAcknowledged;

                return (
                  <div
                    key={index}
                    className={`
                      px-3 py-2.5 rounded-lg border
                      ${config.bg} ${config.border}
                      ${needsAcknowledgment ? 'ring-2 ring-inset ring-red-500/40' : ''}
                    `}
                    role="listitem"
                    aria-label={`${config.label} warning: ${warning.message}`}
                  >
                    <div className="flex items-start gap-2">
                      <span className={`shrink-0 mt-0.5 ${config.text}`} aria-hidden="true">
                        {config.icon}
                      </span>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-0.5">
                          <span className={`text-[10px] font-bold uppercase tracking-wider ${config.text}`}>
                            {config.label}
                          </span>
                          <span className="text-[10px] text-dashboard-muted">
                            {categoryLabels[warning.category] ?? warning.category}
                          </span>
                        </div>
                        <p className="text-sm text-dashboard-text leading-relaxed">
                          {warning.message}
                        </p>

                        {/* Acknowledgment button for blocking warnings */}
                        {needsAcknowledgment && (
                          <button
                            type="button"
                            onClick={() => handleAcknowledge(index)}
                            className="mt-2 px-3 py-1.5 text-xs font-medium text-red-400 border border-red-500/30 rounded-md
                              hover:bg-red-500/10 transition-colors cursor-pointer"
                            aria-label="Acknowledge this risk warning"
                          >
                            I Acknowledge This Risk
                          </button>
                        )}

                        {/* Acknowledged indicator */}
                        {warning.requiresAcknowledgment && isAcknowledged && (
                          <p className="mt-1.5 text-[10px] text-green-400 font-medium">
                            ✓ Acknowledged
                          </p>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Blocking notice */}
          {hasBlockingWarnings && (
            <div className="flex items-center gap-1.5 pt-2 border-t border-dashboard-border">
              <span className="text-red-400 text-xs" aria-hidden="true">⛔</span>
              <p className="text-[11px] text-red-400 font-medium">
                You must acknowledge all blocking warnings before executing new trades.
              </p>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
