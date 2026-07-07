import { useState, useEffect, useMemo, useCallback } from 'react';
import { getChartData } from '../../api/charts';
import { Card } from '../ui/Card';
import { SignalOverlay } from './SignalOverlay';
import type { ChartData, ChartInterval, CandleData } from '../../api/types';

/**
 * SVG-based candlestick chart with EMA(20), VWAP, and MACD overlays.
 * Supports 3-min, 5-min, and 15-min intervals with 50 candles default.
 *
 * Validates: Requirements 15.1-15.5
 */

interface CandlestickChartProps {
  symbol: string;
  /** Optional signal overlay prices */
  signalEntry?: number;
  signalSl?: number;
  signalTarget?: number;
  /** Initial interval (default 5min) */
  defaultInterval?: ChartInterval;
}

const INTERVALS: { value: ChartInterval; label: string }[] = [
  { value: '3min', label: '3 Min' },
  { value: '5min', label: '5 Min' },
  { value: '15min', label: '15 Min' },
];

// Chart layout constants
const CHART_WIDTH = 800;
const CHART_HEIGHT = 400;
const MACD_HEIGHT = 100;
const PADDING = { top: 20, right: 60, bottom: 30, left: 60 };
const CANDLE_GAP = 2;

export function CandlestickChart({
  symbol,
  signalEntry,
  signalSl,
  signalTarget,
  defaultInterval = '5min',
}: CandlestickChartProps) {
  const [interval, setInterval] = useState<ChartInterval>(defaultInterval);
  const [chartData, setChartData] = useState<ChartData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getChartData(symbol, interval);
      setChartData(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load chart data');
      setChartData(null);
    } finally {
      setLoading(false);
    }
  }, [symbol, interval]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  if (loading) {
    return (
      <Card title={`${symbol} Chart`}>
        <div className="flex items-center justify-center py-16">
          <div className="animate-pulse text-sm text-dashboard-muted">Loading chart data…</div>
        </div>
      </Card>
    );
  }

  if (error || !chartData || chartData.candles.length === 0) {
    return (
      <Card title={`${symbol} Chart`}>
        <IntervalTabs current={interval} onChange={setInterval} />
        <div className="flex items-center justify-center py-16">
          <p className="text-sm text-dashboard-muted">
            {error || 'Data unavailable'}
          </p>
        </div>
      </Card>
    );
  }

  return (
    <Card title={`${symbol} Chart`} padding="sm">
      <IntervalTabs current={interval} onChange={setInterval} />
      <ChartSVG
        chartData={chartData}
        signalEntry={signalEntry}
        signalSl={signalSl}
        signalTarget={signalTarget}
      />
    </Card>
  );
}

// ─── Interval Tab Bar ────────────────────────────────────────────────────────

interface IntervalTabsProps {
  current: ChartInterval;
  onChange: (interval: ChartInterval) => void;
}

function IntervalTabs({ current, onChange }: IntervalTabsProps) {
  return (
    <div className="flex gap-1 mb-3" role="tablist" aria-label="Chart interval">
      {INTERVALS.map(({ value, label }) => (
        <button
          key={value}
          role="tab"
          aria-selected={current === value}
          onClick={() => onChange(value)}
          className={`px-3 py-1.5 text-xs font-medium rounded transition-colors ${
            current === value
              ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
              : 'text-dashboard-muted hover:text-dashboard-text hover:bg-dashboard-card/60 border border-transparent'
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

// ─── Main Chart SVG ──────────────────────────────────────────────────────────

interface ChartSVGProps {
  chartData: ChartData;
  signalEntry?: number;
  signalSl?: number;
  signalTarget?: number;
}

function ChartSVG({ chartData, signalEntry, signalSl, signalTarget }: ChartSVGProps) {
  const { candles, indicators } = chartData;

  // Compute price scale for candlestick area
  const { priceMin, priceMax, candleWidth, scaleY, scaleX } = useMemo(() => {
    const allPrices = candles.flatMap((c) => [c.high, c.low]);
    // Include EMA and VWAP in range
    if (indicators.ema20.length > 0) allPrices.push(...indicators.ema20.filter(Boolean));
    if (indicators.vwap.length > 0) allPrices.push(...indicators.vwap.filter(Boolean));
    // Include signal levels
    if (signalEntry) allPrices.push(signalEntry);
    if (signalSl) allPrices.push(signalSl);
    if (signalTarget) allPrices.push(signalTarget);

    const min = Math.min(...allPrices);
    const max = Math.max(...allPrices);
    const padding = (max - min) * 0.05 || 1;
    const pMin = min - padding;
    const pMax = max + padding;

    const mainH = CHART_HEIGHT - PADDING.top - PADDING.bottom;
    const drawableWidth = CHART_WIDTH - PADDING.left - PADDING.right;
    const cWidth = Math.max(2, (drawableWidth - CANDLE_GAP * candles.length) / candles.length);

    const sY = (price: number) =>
      PADDING.top + mainH - ((price - pMin) / (pMax - pMin)) * mainH;
    const sX = (index: number) =>
      PADDING.left + index * (cWidth + CANDLE_GAP) + cWidth / 2;

    return { priceMin: pMin, priceMax: pMax, candleWidth: cWidth, scaleY: sY, scaleX: sX };
  }, [candles, indicators, signalEntry, signalSl, signalTarget]);

  // MACD scale
  const { macdScaleY } = useMemo(() => {
    if (!indicators.macd || indicators.macd.length === 0) {
      return { macdMax: 1, macdScaleY: () => 0 };
    }
    const histValues = indicators.macd.map((m) => Math.abs(m.histogram));
    const mMax = Math.max(...histValues, 0.01);

    const macdTop = CHART_HEIGHT + 10;
    const macdMid = macdTop + MACD_HEIGHT / 2;

    const mScaleY = (val: number) => macdMid - (val / mMax) * (MACD_HEIGHT / 2 - 5);
    return { macdMax: mMax, macdScaleY: mScaleY };
  }, [indicators.macd]);

  const totalHeight = CHART_HEIGHT + MACD_HEIGHT + 20;

  return (
    <div className="overflow-x-auto">
      <svg
        viewBox={`0 0 ${CHART_WIDTH} ${totalHeight}`}
        className="w-full h-auto min-w-[600px]"
        aria-label={`Candlestick chart for ${chartData.symbol} at ${chartData.interval} interval`}
        role="img"
      >
        {/* Price grid lines */}
        <PriceGrid
          priceMin={priceMin}
          priceMax={priceMax}
          scaleY={scaleY}
        />

        {/* Candlesticks */}
        {candles.map((candle, i) => (
          <Candle
            key={i}
            candle={candle}
            x={scaleX(i)}
            width={candleWidth}
            scaleY={scaleY}
          />
        ))}

        {/* EMA(20) line */}
        {indicators.ema20.length > 0 && (
          <IndicatorLine
            values={indicators.ema20}
            scaleX={scaleX}
            scaleY={scaleY}
            color="#f59e0b"
            label="EMA20"
            dashed={false}
          />
        )}

        {/* VWAP dashed line */}
        {indicators.vwap.length > 0 && (
          <IndicatorLine
            values={indicators.vwap}
            scaleX={scaleX}
            scaleY={scaleY}
            color="#8b5cf6"
            label="VWAP"
            dashed
          />
        )}

        {/* Signal Overlay */}
        {(signalEntry || signalSl || signalTarget) && (
          <SignalOverlay
            signalEntry={signalEntry}
            signalSl={signalSl}
            signalTarget={signalTarget}
            scaleY={scaleY}
            chartWidth={CHART_WIDTH}
            paddingLeft={PADDING.left}
            paddingRight={PADDING.right}
          />
        )}

        {/* MACD Section separator */}
        <line
          x1={PADDING.left}
          y1={CHART_HEIGHT + 5}
          x2={CHART_WIDTH - PADDING.right}
          y2={CHART_HEIGHT + 5}
          stroke="#374151"
          strokeWidth={0.5}
        />
        <text
          x={PADDING.left}
          y={CHART_HEIGHT + 18}
          className="fill-dashboard-muted"
          fontSize={9}
        >
          MACD
        </text>

        {/* MACD Histogram */}
        {indicators.macd && indicators.macd.length > 0 && (
          <MACDHistogram
            macd={indicators.macd}
            scaleX={scaleX}
            macdScaleY={macdScaleY}
            candleWidth={candleWidth}
          />
        )}

        {/* Y-axis price labels */}
        <PriceLabels priceMin={priceMin} priceMax={priceMax} scaleY={scaleY} />

        {/* Legend */}
        <Legend />
      </svg>
    </div>
  );
}

// ─── Sub-components ──────────────────────────────────────────────────────────

interface CandleProps {
  candle: CandleData;
  x: number;
  width: number;
  scaleY: (price: number) => number;
}

function Candle({ candle, x, width, scaleY }: CandleProps) {
  const isBullish = candle.close >= candle.open;
  const color = isBullish ? '#22c55e' : '#ef4444';
  const bodyTop = scaleY(Math.max(candle.open, candle.close));
  const bodyBottom = scaleY(Math.min(candle.open, candle.close));
  const bodyHeight = Math.max(1, bodyBottom - bodyTop);

  return (
    <g aria-label={`${isBullish ? 'Bullish' : 'Bearish'} candle O:${candle.open} H:${candle.high} L:${candle.low} C:${candle.close}`}>
      {/* Wick */}
      <line
        x1={x}
        y1={scaleY(candle.high)}
        x2={x}
        y2={scaleY(candle.low)}
        stroke={color}
        strokeWidth={1}
      />
      {/* Body */}
      <rect
        x={x - width / 2}
        y={bodyTop}
        width={width}
        height={bodyHeight}
        fill={isBullish ? color : color}
        stroke={color}
        strokeWidth={0.5}
        opacity={isBullish ? 0.9 : 0.9}
      />
    </g>
  );
}

interface IndicatorLineProps {
  values: number[];
  scaleX: (index: number) => number;
  scaleY: (price: number) => number;
  color: string;
  label: string;
  dashed: boolean;
}

function IndicatorLine({ values, scaleX, scaleY, color, dashed }: IndicatorLineProps) {
  const points = values
    .map((val, i) => (val ? `${scaleX(i)},${scaleY(val)}` : null))
    .filter(Boolean)
    .join(' ');

  if (!points) return null;

  return (
    <polyline
      points={points}
      fill="none"
      stroke={color}
      strokeWidth={1.5}
      strokeDasharray={dashed ? '4 2' : undefined}
      opacity={0.8}
    />
  );
}

interface MACDHistogramProps {
  macd: { macd: number; signal: number; histogram: number }[];
  scaleX: (index: number) => number;
  macdScaleY: (val: number) => number;
  candleWidth: number;
}

function MACDHistogram({ macd, scaleX, macdScaleY, candleWidth }: MACDHistogramProps) {
  const zeroY = macdScaleY(0);

  return (
    <g>
      {/* Zero line */}
      <line
        x1={PADDING.left}
        y1={zeroY}
        x2={CHART_WIDTH - PADDING.right}
        y2={zeroY}
        stroke="#4b5563"
        strokeWidth={0.5}
        strokeDasharray="2 2"
      />
      {/* Histogram bars */}
      {macd.map((m, i) => {
        const barY = macdScaleY(m.histogram);
        const barHeight = Math.abs(barY - zeroY);
        const isPositive = m.histogram >= 0;

        return (
          <rect
            key={i}
            x={scaleX(i) - candleWidth / 2}
            y={isPositive ? barY : zeroY}
            width={candleWidth}
            height={Math.max(0.5, barHeight)}
            fill={isPositive ? '#22c55e' : '#ef4444'}
            opacity={0.7}
          />
        );
      })}
    </g>
  );
}

interface PriceGridProps {
  priceMin: number;
  priceMax: number;
  scaleY: (price: number) => number;
}

function PriceGrid({ priceMin, priceMax, scaleY }: PriceGridProps) {
  const range = priceMax - priceMin;
  const step = calculateGridStep(range);
  const lines: number[] = [];

  const start = Math.ceil(priceMin / step) * step;
  for (let price = start; price <= priceMax; price += step) {
    lines.push(price);
  }

  return (
    <g>
      {lines.map((price) => (
        <line
          key={price}
          x1={PADDING.left}
          y1={scaleY(price)}
          x2={CHART_WIDTH - PADDING.right}
          y2={scaleY(price)}
          stroke="#1f2937"
          strokeWidth={0.5}
        />
      ))}
    </g>
  );
}

interface PriceLabelsProps {
  priceMin: number;
  priceMax: number;
  scaleY: (price: number) => number;
}

function PriceLabels({ priceMin, priceMax, scaleY }: PriceLabelsProps) {
  const range = priceMax - priceMin;
  const step = calculateGridStep(range);
  const labels: number[] = [];

  const start = Math.ceil(priceMin / step) * step;
  for (let price = start; price <= priceMax; price += step) {
    labels.push(price);
  }

  return (
    <g>
      {labels.map((price) => (
        <text
          key={price}
          x={CHART_WIDTH - PADDING.right + 5}
          y={scaleY(price) + 3}
          fontSize={9}
          className="fill-dashboard-muted"
        >
          {formatPrice(price)}
        </text>
      ))}
    </g>
  );
}

function Legend() {
  return (
    <g>
      {/* EMA legend */}
      <line x1={PADDING.left} y1={8} x2={PADDING.left + 20} y2={8} stroke="#f59e0b" strokeWidth={1.5} />
      <text x={PADDING.left + 24} y={11} fontSize={9} className="fill-dashboard-muted">EMA(20)</text>

      {/* VWAP legend */}
      <line x1={PADDING.left + 80} y1={8} x2={PADDING.left + 100} y2={8} stroke="#8b5cf6" strokeWidth={1.5} strokeDasharray="4 2" />
      <text x={PADDING.left + 104} y={11} fontSize={9} className="fill-dashboard-muted">VWAP</text>
    </g>
  );
}

// ─── Utility functions ───────────────────────────────────────────────────────

function calculateGridStep(range: number): number {
  const rawStep = range / 5;
  const magnitude = Math.pow(10, Math.floor(Math.log10(rawStep)));
  const normalized = rawStep / magnitude;

  if (normalized <= 1) return magnitude;
  if (normalized <= 2) return 2 * magnitude;
  if (normalized <= 5) return 5 * magnitude;
  return 10 * magnitude;
}

function formatPrice(price: number): string {
  if (price >= 10000) return price.toFixed(0);
  if (price >= 100) return price.toFixed(1);
  return price.toFixed(2);
}
