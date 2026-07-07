# Analysis Module

This module contains the Market State Detector for analyzing price structure and determining trend and mean reversion states.

## Components

### MarketStateDetector

The `MarketStateDetector` class analyzes price structure to determine:
- **Trend State**: UPTREND, DOWNTREND, or NEUTRAL
- **Mean Reversion State**: EXTENDED_UP, EXTENDED_DOWN, or NORMAL

#### Key Features

**Structure-Based Analysis**
- Uses HH/HL/LH/LL (Higher Highs, Higher Lows, Lower Highs, Lower Lows) pattern recognition
- Identifies swing points in price action
- Detects structure breaks
- EMA used only as structural reference, not standalone signal

**Trend Detection**
- UPTREND: Higher highs AND higher lows AND close above 20-EMA AND no structure break in last 3 candles
- DOWNTREND: Lower highs AND lower lows AND close below 20-EMA
- NEUTRAL: Neither uptrend nor downtrend conditions met

**Mean Reversion Detection**
- EXTENDED_UP/DOWN when ANY of:
  - Impulse exceeds 1.5x recent average
  - 3+ consecutive large candles
  - Distance from VWAP > 1.2x ATR

**Helper Methods**
- `is_vertical_extension()`: Detects vertical moves with little/no pullback
- `find_structure_level()`: Locates previous HL (uptrend) or LH (downtrend)
- `detect_structure_break()`: Identifies structure breaks
- `detect_trend_weakening()`: Detects trend weakening via:
  - Failure to make new HH/LL after N candles
  - Consecutive candles with reduced range
  - Close below/above impulse midpoint

## Usage

```python
from hybrid_trading.data.candle_builder import CandleBuilder
from hybrid_trading.data.indicator_service import IndicatorService
from hybrid_trading.analysis import MarketStateDetector

# Initialize components
candle_builder = CandleBuilder(['15m', '5m'])
indicator_service = IndicatorService(candle_builder)
detector = MarketStateDetector(candle_builder, indicator_service)

# Detect trend state
trend_state = detector.detect_trend_state('15m')
print(f"Trend: {trend_state}")  # UPTREND, DOWNTREND, or NEUTRAL

# Detect mean reversion state
mr_state = detector.detect_mr_state('5m')
print(f"MR State: {mr_state}")  # EXTENDED_UP, EXTENDED_DOWN, or NORMAL

# Check for vertical extension
is_vertical = detector.is_vertical_extension('15m')
print(f"Vertical Extension: {is_vertical}")

# Find structure level
structure_level = detector.find_structure_level('15m', direction='up')
print(f"Structure Level: {structure_level}")

# Detect trend weakening
is_weakening = detector.detect_trend_weakening('15m', direction='up')
print(f"Trend Weakening: {is_weakening}")
```

## Testing

Run the test suite:
```bash
python -m pytest hybrid_trading/analysis/test_market_state_detector.py -v
```

The test suite includes:
- Trend state detection tests (uptrend, downtrend, neutral)
- Swing point identification tests
- Structure break detection tests
- Vertical extension detection tests
- Structure level finding tests
- Trend weakening detection tests
- Mean reversion state detection tests

## Requirements Validated

This implementation validates the following requirements:
- **1.1, 1.2, 1.3**: Market trend state classification
- **1.4, 1.5**: Mean reversion state detection
- **2.1, 2.2, 2.3, 2.4**: Trend weakening and structure-based logic

## Design Principles

1. **Structure Over Indicators**: Market state is based on price structure patterns, not lagging indicators
2. **Indicators as References**: EMA and VWAP serve as structural references only
3. **Consistent Logic**: Same structure-based rules apply across all timeframes
4. **Defensive Programming**: Handles insufficient data gracefully, returns safe defaults
