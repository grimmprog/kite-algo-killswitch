# Data Layer Components

This directory contains the data layer components for the hybrid trading system.

## Components

### 1. Models (`models.py`)
Core data structures:
- **Tick**: Represents a single tick of market data with timestamp, symbol, price, and volume
- **Candle**: Represents an OHLC candle with validation and utility properties

### 2. CandleBuilder (`candle_builder.py`)
Builds OHLC candles from tick data across multiple timeframes.

**Features:**
- Multi-timeframe support (1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 1d)
- Automatic candle completion detection
- Historical candle buffer (configurable, default 50 candles)
- Proper timeframe boundary handling

**Usage:**
```python
from hybrid_trading.data import CandleBuilder, Tick
from datetime import datetime

# Initialize with timeframes
builder = CandleBuilder(['5m', '15m'])

# Process ticks
tick = Tick(
    timestamp=datetime.now(),
    symbol='NIFTY',
    last_price=21000.0,
    volume=100
)

completed_candles = builder.on_tick(tick)

# Get historical candles
candles_5m = builder.get_candles('5m', count=20)
```

### 3. IndicatorService (`indicator_service.py`)
Calculates technical indicators from candle data.

**Indicators:**
- **VWAP**: Volume Weighted Average Price (calculated on futures data)
- **ATR**: Average True Range (standard formula)
- **EMA**: Exponential Moving Average (standard formula)
- **SMA**: Simple Moving Average

**Helper Methods:**
- `calculate_impulse_size()`: Calculate size of impulse moves
- `calculate_average_body_size()`: Average candle body size
- `calculate_average_range()`: Average candle range
- `count_consecutive_large_candles()`: Count consecutive large candles

**Usage:**
```python
from hybrid_trading.data import IndicatorService

# Initialize with CandleBuilder
service = IndicatorService(builder)

# Calculate indicators
vwap = service.calculate_vwap('5m', lookback=20)
atr = service.calculate_atr('15m', period=14)
ema = service.calculate_ema('15m', period=20)
```

## Testing

Run tests with:
```bash
pytest hybrid_trading/data/test_candle_builder.py -v
```

All tests pass (18/18):
- CandleBuilder: 8 tests covering initialization, tick processing, candle completion, and multi-timeframe support
- IndicatorService: 10 tests covering all indicators and helper methods

## Requirements Validated

This implementation satisfies the following requirements from the spec:
- **Requirement 7.1**: Tick data updates candles for all configured timeframes
- **Requirement 7.2**: Candle finalization on timeframe period completion
- **Requirement 7.3**: VWAP calculation on futures data
- **Requirement 7.4**: ATR calculation using standard formula
- **Requirement 7.5**: EMA calculation using standard formula
- **Requirement 7.6**: Minimum 50 candles maintained per timeframe
