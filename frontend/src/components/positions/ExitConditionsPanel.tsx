import { useEffect, useRef } from 'react';
import type { ExitCondition } from '../../hooks/usePositionMonitor';

interface ExitConditionsPanelProps {
  conditions: ExitCondition[];
  positionSymbol?: string;
}

/**
 * Exit conditions panel showing all active exit rules for a position.
 * Displays met/not-met status with:
 * - Green checkmark for met conditions
 * - Gray circle for not-met conditions
 * - Flash/glow animation on transition from not-met → met
 *
 * Exit conditions: ema_cross, vwap_touch, consecutive_green, time_based
 *
 * Validates: Requirements 8.1-8.5
 */
export function ExitConditionsPanel({ conditions, positionSymbol }: ExitConditionsPanelProps) {
  const anyMet = conditions.some((c) => c.isMet);

  return (
    <div
      className="rounded-lg border border-dashboard-border bg-dashboard-card p-4"
      role="region"
      aria-label={`Exit conditions${positionSymbol ? ` for ${positionSymbol}` : ''}`}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-sm font-medium text-dashboard-text">Exit Conditions</h4>
        {anyMet && (
          <span
            className="text-xs font-medium text-yellow-400 bg-yellow-500/10 px-2 py-0.5 rounded-full"
            role="status"
            aria-live="polite"
          >
            Exit pending
          </span>
        )}
      </div>

      {/* Conditions list */}
      {conditions.length === 0 ? (
        <p className="text-xs text-dashboard-muted">No exit conditions configured.</p>
      ) : (
        <ul className="space-y-2" aria-label="Exit condition list">
          {conditions.map((condition) => (
            <ExitConditionRow key={condition.name} condition={condition} />
          ))}
        </ul>
      )}
    </div>
  );
}

// --- Sub-components ---

interface ExitConditionRowProps {
  condition: ExitCondition;
}

function ExitConditionRow({ condition }: ExitConditionRowProps) {
  const prevMetRef = useRef(condition.isMet);
  const justTransitioned = useRef(false);

  useEffect(() => {
    if (!prevMetRef.current && condition.isMet) {
      justTransitioned.current = true;
      // Reset the animation after it completes
      const timer = setTimeout(() => {
        justTransitioned.current = false;
      }, 2000);
      return () => clearTimeout(timer);
    }
    prevMetRef.current = condition.isMet;
  }, [condition.isMet]);

  // Determine if we should show the highlight animation
  const showGlow = !prevMetRef.current && condition.isMet || justTransitioned.current;

  const conditionIcon = getConditionIcon(condition.name);

  return (
    <li
      className={`flex items-start gap-3 rounded-lg px-3 py-2 transition-all duration-300 ${
        condition.isMet
          ? showGlow
            ? 'bg-profit/15 border border-profit/40 animate-pulse'
            : 'bg-profit/10 border border-profit/20'
          : 'bg-dashboard-bg/50 border border-transparent'
      }`}
      aria-label={`${condition.description}: ${condition.isMet ? 'met' : 'not met'}`}
    >
      {/* Status Icon */}
      <div className="mt-0.5 shrink-0">
        {condition.isMet ? (
          <span
            className={`flex items-center justify-center w-5 h-5 rounded-full bg-profit text-white text-xs ${
              showGlow ? 'ring-2 ring-profit/50 ring-offset-1 ring-offset-dashboard-card' : ''
            }`}
            aria-hidden="true"
          >
            ✓
          </span>
        ) : (
          <span
            className="flex items-center justify-center w-5 h-5 rounded-full border-2 border-dashboard-muted/40"
            aria-hidden="true"
          >
            <span className="w-2 h-2 rounded-full bg-dashboard-muted/30" />
          </span>
        )}
      </div>

      {/* Condition Info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm" aria-hidden="true">{conditionIcon}</span>
          <span
            className={`text-sm font-medium ${
              condition.isMet ? 'text-profit' : 'text-dashboard-text'
            }`}
          >
            {condition.description}
          </span>
        </div>
        {condition.details && (
          <p className="text-xs text-dashboard-muted mt-0.5 truncate">{condition.details}</p>
        )}
      </div>

      {/* Met/Not Met label */}
      <span
        className={`shrink-0 text-xs font-medium px-2 py-0.5 rounded ${
          condition.isMet
            ? 'bg-profit/20 text-profit'
            : 'bg-dashboard-bg text-dashboard-muted'
        }`}
      >
        {condition.isMet ? 'Met' : 'Not met'}
      </span>
    </li>
  );
}

/**
 * Returns a contextual icon for known exit condition types.
 */
function getConditionIcon(name: string): string {
  const iconMap: Record<string, string> = {
    ema_cross: '📈',
    vwap_touch: '📊',
    consecutive_green: '🟢',
    time_based: '⏰',
  };
  return iconMap[name] ?? '📋';
}
