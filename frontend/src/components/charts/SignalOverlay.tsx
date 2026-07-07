/**
 * Signal overlay component for the candlestick chart.
 * Draws horizontal lines for entry (blue), stop-loss (red), and target (green)
 * with price labels on the right side.
 *
 * Validates: Requirements 15.4
 */

interface SignalOverlayProps {
  /** Entry price level */
  signalEntry?: number;
  /** Stop-loss price level */
  signalSl?: number;
  /** Target price level */
  signalTarget?: number;
  /** Y-axis scaling function from parent chart */
  scaleY: (price: number) => number;
  /** Total chart width */
  chartWidth: number;
  /** Left padding of chart area */
  paddingLeft: number;
  /** Right padding of chart area */
  paddingRight: number;
}

interface SignalLineConfig {
  price: number;
  color: string;
  label: string;
  dashArray?: string;
}

export function SignalOverlay({
  signalEntry,
  signalSl,
  signalTarget,
  scaleY,
  chartWidth,
  paddingLeft,
  paddingRight,
}: SignalOverlayProps) {
  const lines: SignalLineConfig[] = [];

  if (signalEntry) {
    lines.push({ price: signalEntry, color: '#3b82f6', label: 'Entry' });
  }
  if (signalSl) {
    lines.push({ price: signalSl, color: '#ef4444', label: 'SL', dashArray: '6 3' });
  }
  if (signalTarget) {
    lines.push({ price: signalTarget, color: '#22c55e', label: 'Target', dashArray: '6 3' });
  }

  if (lines.length === 0) return null;

  const lineStart = paddingLeft;
  const lineEnd = chartWidth - paddingRight;

  return (
    <g aria-label="Signal overlay markers">
      {lines.map(({ price, color, label, dashArray }) => {
        const y = scaleY(price);
        return (
          <g key={label} aria-label={`${label} at ₹${price.toFixed(2)}`}>
            {/* Horizontal signal line */}
            <line
              x1={lineStart}
              y1={y}
              x2={lineEnd}
              y2={y}
              stroke={color}
              strokeWidth={1.5}
              strokeDasharray={dashArray}
              opacity={0.85}
            />
            {/* Price label background */}
            <rect
              x={lineEnd + 2}
              y={y - 8}
              width={52}
              height={16}
              rx={3}
              fill={color}
              opacity={0.9}
            />
            {/* Price label text */}
            <text
              x={lineEnd + 6}
              y={y + 3}
              fontSize={9}
              fontWeight="bold"
              fill="#ffffff"
            >
              {label} {formatSignalPrice(price)}
            </text>
          </g>
        );
      })}
    </g>
  );
}

function formatSignalPrice(price: number): string {
  if (price >= 10000) return price.toFixed(0);
  if (price >= 100) return price.toFixed(1);
  return price.toFixed(2);
}
