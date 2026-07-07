# Strategy Layer

This directory contains the trading strategy engines for the hybrid trading system.

## Components

### Trend Engine (`trend_engine.py`)

The Trend Engine implements trend-following logic based on price structure analysis.

**Key Features:**
- Structure-based entry signals (pullbacks to HL/LH or EMA zones)
- Vertical extension detection to avoid chasing moves
- Multiple exit conditions:
  - Full exit on structure break
  - Full exit on opposite trend confirmation
  - Partial exit on trend weakening

**Entry Logic:**
- **Long Entry**: UPTREND + pullback to structure (previous HL or EMA zone) + not at vertical extension
- **Short Entry**: DOWNTREND + pullback to structure (previous LH or EMA zone) + not at vertical extension

**Exit Logic:**
- **Full Exit**: Structure break OR opposite trend confirmed (2 consecutive closes beyond structure)
- **Partial Exit**: Trend weakening detected (failure to make new HH/LL, reduced range candles, or close below/above impulse midpoint)

**Configuration Parameters:**
- `timeframe`: Timeframe for trend analysis (default: '15m')
- `base_position_size`: Base position size for trend trades
- `partial_exit_percentage`: Percentage to exit on trend weakening (default: 0.5 = 50%)
- `structure_proximity_atr_multiplier`: ATR multiplier for structure proximity check (default: 0.5)
- `vertical_extension_body_threshold`: Body size threshold for vertical extension (default: 2.0)
- `vertical_extension_distance_threshold`: Distance threshold for vertical extension (default: 2.0)
- `trend_weakening_candles`: Candles to check for HH/LL failure (default: 5)
- `trend_weakening_reduced_range_count`: Consecutive reduced range candles (default: 3)

### Trend Book (`trend_engine.py`)

The TrendBook class maintains the logical position book for trend-following trades.

**Features:**
- Tracks current position (positive = long, negative = short)
- Maintains average entry price
- Supports position additions and reductions
- FIFO accounting for exits

## Usage Example

```python
from hybrid_trading.strategy import TrendEngine, TrendBook
from hybrid_trading.analysis import MarketStateDetector
from hybrid_trading.data import IndicatorService
from hybrid_trading.config import TrendConfig

# Initialize components
config = TrendConfig(
    timeframe='15m',
    base_position_size=1,
    partial_exit_percentage=0.5
)

engine = TrendEngine(market_state, indicator_service, config)
trend_book = TrendBook()

# Evaluate trend conditions
current_price = 100.0
signal = engine.evaluate(trend_book, current_price)

if signal:
    print(f"Signal: {signal.signal_type}")
    print(f"Quantity: {signal.quantity}")
    print(f"Reason: {signal.reason}")
```

## Testing

Run tests with:
```bash
pytest hybrid_trading/strategy/test_trend_engine.py -v
```

## Requirements Validated

This implementation validates the following requirements:
- **Requirement 2.1**: Trend entry on pullback to structure in uptrend
- **Requirement 2.2**: Trend entry on pullback to structure in downtrend
- **Requirement 2.3**: Partial exit on trend weakening
- **Requirement 2.4**: Trend weakening detection conditions
- **Requirement 2.5**: Full exit on structure break
- **Requirement 2.6**: Full exit on opposite trend confirmation


### Mean Reversion Engine (`mr_engine.py`)

The Mean Reversion Engine implements counter-trend trading logic for risk management during extended moves.

**Key Features:**
- Only trades when trend position exists
- Enters counter to trend when market is extended
- Position size limited to 30% of trend position
- Ensures net position doesn't flip against trend
- Multiple exit conditions for risk management

**Entry Logic:**
- **MR Short Entry**: UPTREND + EXTENDED_UP + trend position exists + net position won't flip
- **MR Long Entry**: DOWNTREND + EXTENDED_DOWN + trend position exists + net position won't flip

**Exit Logic:**
- **Retracement Exit**: 40-60% retracement of impulse OR structure/EMA touch
- **Time Stop**: 5 candles (configurable)
- **Momentum Loss**: Large candle against MR position
- **End-of-Day**: Exit all MR trades before market close

**Configuration Parameters:**
- `timeframe`: Timeframe for MR analysis (default: '5m')
- `mr_base_size`: Base position size for MR trades
- `max_mr_position_pct`: Max MR position as % of trend position (default: 0.3 = 30%)
- `max_mr_trades_per_leg`: Max number of MR trades per trend leg (default: 3)
- `impulse_extension_threshold`: Impulse size threshold for extension (default: 1.5)
- `consecutive_large_candles_threshold`: Consecutive large candles for extension (default: 3)
- `vwap_distance_atr_multiplier`: VWAP distance threshold (default: 1.2)
- `retracement_target_min`: Minimum retracement % for exit (default: 40.0)
- `retracement_target_max`: Maximum retracement % for exit (default: 60.0)
- `time_stop_candles`: Candles before time stop exit (default: 5)
- `structure_touch_atr_multiplier`: ATR multiplier for structure touch (default: 0.3)
- `ema_touch_atr_multiplier`: ATR multiplier for EMA touch (default: 0.3)

### MR Book (`mr_engine.py`)

The MRBook class maintains the logical position book for mean reversion trades.

**Features:**
- Tracks active MR trades with entry details
- Maintains net MR position
- Supports multiple concurrent MR trades
- Tracks impulse range for retracement calculation

## Mean Reversion Usage Example

```python
from hybrid_trading.strategy import MeanReversionEngine, MRBook
from hybrid_trading.strategy import TrendBook
from hybrid_trading.analysis import MarketStateDetector
from hybrid_trading.data import IndicatorService
from hybrid_trading.config import MRConfig
from hybrid_trading.common.enums import TrendState

# Initialize components
config = MRConfig(
    timeframe='5m',
    mr_base_size=15,
    max_mr_trades_per_leg=3
)

engine = MeanReversionEngine(market_state, indicator_service, config)
mr_book = MRBook()
trend_book = TrendBook()

# Set up trend position
trend_book.position = 50  # Long position

# Evaluate MR conditions
current_price = 20300.0
signals = engine.evaluate(TrendState.UPTREND, trend_book, mr_book, current_price)

for signal in signals:
    print(f"Signal: {signal.signal_type}")
    print(f"Quantity: {signal.quantity}")
    print(f"Reason: {signal.reason}")
```

## Testing Mean Reversion Engine

Run tests with:
```bash
pytest hybrid_trading/strategy/test_mr_engine.py -v
```

Run verification script:
```bash
python hybrid_trading/verify_mr_engine.py
```

## Requirements Validated (Mean Reversion)

This implementation validates the following requirements:
- **Requirement 3.1**: MR entry on extended up in uptrend
- **Requirement 3.2**: MR entry on extended down in downtrend
- **Requirement 3.3**: MR only trades when trend position exists
- **Requirement 3.4**: MR exit on retracement target
- **Requirement 3.5**: MR exit on time stop
- **Requirement 3.6**: MR exit on momentum loss
- **Requirement 3.7**: MR exit all trades at end-of-day
- **Requirement 4.3**: Trend position sizing (100% of base)
- **Requirement 4.4**: MR position sizing (max 30% of trend)
- **Requirement 4.5**: Net position direction preservation

## Design Principles

1. **Structure Over Indicators**: Both engines use price structure (HH/HL/LL/LH patterns) as primary decision criteria
2. **Risk First, Profits Second**: MR engine exists primarily for risk management and drawdown reduction
3. **Logical Separation**: Two logical position books (Trend_Book, MR_Book) maintained for strategy tracking
4. **Position Constraints**: MR positions limited to 30% of trend position and cannot flip net position against trend
5. **Multiple Exit Conditions**: Both engines have multiple exit conditions to protect capital
