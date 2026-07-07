"""
Configuration schema for the hybrid trading system.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import yaml
import json
from pathlib import Path


@dataclass
class TrendConfig:
    """Configuration for the trend engine."""
    timeframe: str = '15m'
    base_position_size: int = 1
    partial_exit_percentage: float = 0.5
    structure_proximity_atr_multiplier: float = 0.5
    vertical_extension_body_threshold: float = 2.0
    vertical_extension_distance_threshold: float = 2.0
    trend_weakening_candles: int = 5
    trend_weakening_reduced_range_count: int = 3
    ema_period: int = 20
    
    def validate(self) -> None:
        """Validate trend configuration parameters."""
        if self.base_position_size <= 0:
            raise ValueError(f"base_position_size must be positive: {self.base_position_size}")
        if not 0 < self.partial_exit_percentage < 1:
            raise ValueError(f"partial_exit_percentage must be between 0 and 1: {self.partial_exit_percentage}")
        if self.structure_proximity_atr_multiplier <= 0:
            raise ValueError(f"structure_proximity_atr_multiplier must be positive: {self.structure_proximity_atr_multiplier}")
        if self.vertical_extension_body_threshold <= 0:
            raise ValueError(f"vertical_extension_body_threshold must be positive: {self.vertical_extension_body_threshold}")
        if self.vertical_extension_distance_threshold <= 0:
            raise ValueError(f"vertical_extension_distance_threshold must be positive: {self.vertical_extension_distance_threshold}")
        if self.trend_weakening_candles <= 0:
            raise ValueError(f"trend_weakening_candles must be positive: {self.trend_weakening_candles}")
        if self.trend_weakening_reduced_range_count <= 0:
            raise ValueError(f"trend_weakening_reduced_range_count must be positive: {self.trend_weakening_reduced_range_count}")
        if self.ema_period <= 0:
            raise ValueError(f"ema_period must be positive: {self.ema_period}")


@dataclass
class MRConfig:
    """Configuration for the mean reversion engine."""
    timeframe: str = '5m'
    mr_base_size: int = 1
    max_mr_position_pct: float = 0.3
    max_mr_trades_per_leg: int = 3
    impulse_extension_threshold: float = 1.5
    consecutive_large_candles_threshold: int = 3
    vwap_distance_atr_multiplier: float = 1.2
    retracement_target_min: float = 40.0
    retracement_target_max: float = 60.0
    time_stop_candles: int = 5
    structure_touch_atr_multiplier: float = 0.3
    ema_touch_atr_multiplier: float = 0.3
    
    def validate(self) -> None:
        """Validate mean reversion configuration parameters."""
        if self.mr_base_size <= 0:
            raise ValueError(f"mr_base_size must be positive: {self.mr_base_size}")
        if not 0 < self.max_mr_position_pct <= 1:
            raise ValueError(f"max_mr_position_pct must be between 0 and 1: {self.max_mr_position_pct}")
        if self.max_mr_trades_per_leg <= 0:
            raise ValueError(f"max_mr_trades_per_leg must be positive: {self.max_mr_trades_per_leg}")
        if self.impulse_extension_threshold <= 0:
            raise ValueError(f"impulse_extension_threshold must be positive: {self.impulse_extension_threshold}")
        if self.consecutive_large_candles_threshold <= 0:
            raise ValueError(f"consecutive_large_candles_threshold must be positive: {self.consecutive_large_candles_threshold}")
        if self.vwap_distance_atr_multiplier <= 0:
            raise ValueError(f"vwap_distance_atr_multiplier must be positive: {self.vwap_distance_atr_multiplier}")
        if not 0 <= self.retracement_target_min < self.retracement_target_max <= 100:
            raise ValueError(f"Invalid retracement targets: min={self.retracement_target_min}, max={self.retracement_target_max}")
        if self.time_stop_candles <= 0:
            raise ValueError(f"time_stop_candles must be positive: {self.time_stop_candles}")
        if self.structure_touch_atr_multiplier <= 0:
            raise ValueError(f"structure_touch_atr_multiplier must be positive: {self.structure_touch_atr_multiplier}")
        if self.ema_touch_atr_multiplier <= 0:
            raise ValueError(f"ema_touch_atr_multiplier must be positive: {self.ema_touch_atr_multiplier}")


@dataclass
class RiskConfig:
    """Configuration for risk management."""
    max_daily_loss_pct: float = 2.0
    max_net_position: int = 10
    atr_spike_threshold: float = 2.0
    data_feed_timeout_seconds: int = 60
    order_slippage_tolerance_pct: float = 0.5
    atr_period: int = 14
    
    def validate(self) -> None:
        """Validate risk configuration parameters."""
        if self.max_daily_loss_pct <= 0:
            raise ValueError(f"max_daily_loss_pct must be positive: {self.max_daily_loss_pct}")
        if self.max_net_position <= 0:
            raise ValueError(f"max_net_position must be positive: {self.max_net_position}")
        if self.atr_spike_threshold <= 0:
            raise ValueError(f"atr_spike_threshold must be positive: {self.atr_spike_threshold}")
        if self.data_feed_timeout_seconds <= 0:
            raise ValueError(f"data_feed_timeout_seconds must be positive: {self.data_feed_timeout_seconds}")
        if self.order_slippage_tolerance_pct < 0:
            raise ValueError(f"order_slippage_tolerance_pct cannot be negative: {self.order_slippage_tolerance_pct}")
        if self.atr_period <= 0:
            raise ValueError(f"atr_period must be positive: {self.atr_period}")


@dataclass
class ExecutionConfig:
    """Configuration for order execution."""
    symbol: str = 'NIFTY'
    exchange: str = 'NFO'
    product: str = 'MIS'
    order_timeout: int = 30
    max_retry_attempts: int = 3
    retry_backoff_seconds: float = 1.0
    
    def validate(self) -> None:
        """Validate execution configuration parameters."""
        if not self.symbol:
            raise ValueError("symbol cannot be empty")
        if not self.exchange:
            raise ValueError("exchange cannot be empty")
        if not self.product:
            raise ValueError("product cannot be empty")
        if self.order_timeout <= 0:
            raise ValueError(f"order_timeout must be positive: {self.order_timeout}")
        if self.max_retry_attempts < 0:
            raise ValueError(f"max_retry_attempts cannot be negative: {self.max_retry_attempts}")
        if self.retry_backoff_seconds < 0:
            raise ValueError(f"retry_backoff_seconds cannot be negative: {self.retry_backoff_seconds}")


@dataclass
class SystemConfig:
    """Main system configuration."""
    timeframes: List[str] = field(default_factory=lambda: ['1m', '3m', '5m', '15m', '30m'])
    instruments: List[str] = field(default_factory=lambda: ['NIFTY FUT'])
    execution_mode: str = 'automated'  # 'automated' or 'semi-manual'
    start_of_day_capital: float = 100000.0
    vwap_lookback: int = 20
    historical_candles_buffer: int = 50
    
    trend_config: TrendConfig = field(default_factory=TrendConfig)
    mr_config: MRConfig = field(default_factory=MRConfig)
    risk_config: RiskConfig = field(default_factory=RiskConfig)
    execution_config: ExecutionConfig = field(default_factory=ExecutionConfig)
    
    def validate(self) -> None:
        """
        Validate all configuration parameters.
        
        Raises:
            ValueError: If any configuration parameter is invalid
        """
        # Validate timeframes
        valid_timeframes = ['1m', '3m', '5m', '15m', '30m', '1h', '1d']
        for tf in self.timeframes:
            if tf not in valid_timeframes:
                raise ValueError(f"Invalid timeframe: {tf}. Must be one of {valid_timeframes}")
        
        if not self.timeframes:
            raise ValueError("timeframes cannot be empty")
        
        # Validate instruments
        if not self.instruments:
            raise ValueError("instruments cannot be empty")
        
        # Validate execution mode
        if self.execution_mode not in ('automated', 'semi-manual'):
            raise ValueError(f"Invalid execution_mode: {self.execution_mode}. Must be 'automated' or 'semi-manual'")
        
        # Validate capital
        if self.start_of_day_capital <= 0:
            raise ValueError(f"start_of_day_capital must be positive: {self.start_of_day_capital}")
        
        # Validate lookback periods
        if self.vwap_lookback <= 0:
            raise ValueError(f"vwap_lookback must be positive: {self.vwap_lookback}")
        if self.historical_candles_buffer <= 0:
            raise ValueError(f"historical_candles_buffer must be positive: {self.historical_candles_buffer}")
        
        # Validate sub-configurations
        self.trend_config.validate()
        self.mr_config.validate()
        self.risk_config.validate()
        self.execution_config.validate()
    
    @classmethod
    def from_file(cls, filepath: str) -> 'SystemConfig':
        """
        Load configuration from a YAML or JSON file.
        
        Args:
            filepath: Path to configuration file
            
        Returns:
            SystemConfig instance
            
        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file format is invalid or configuration is invalid
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {filepath}")
        
        # Load file based on extension
        with open(path, 'r') as f:
            if path.suffix in ('.yaml', '.yml'):
                data = yaml.safe_load(f)
            elif path.suffix == '.json':
                data = json.load(f)
            else:
                raise ValueError(f"Unsupported file format: {path.suffix}. Use .yaml, .yml, or .json")
        
        # Parse nested configurations
        config_dict = {}
        
        # Top-level fields
        for field_name in ['timeframes', 'instruments', 'execution_mode', 'start_of_day_capital', 
                          'vwap_lookback', 'historical_candles_buffer']:
            if field_name in data:
                config_dict[field_name] = data[field_name]
        
        # Nested configurations
        if 'trend_config' in data:
            config_dict['trend_config'] = TrendConfig(**data['trend_config'])
        if 'mr_config' in data:
            config_dict['mr_config'] = MRConfig(**data['mr_config'])
        if 'risk_config' in data:
            config_dict['risk_config'] = RiskConfig(**data['risk_config'])
        if 'execution_config' in data:
            config_dict['execution_config'] = ExecutionConfig(**data['execution_config'])
        
        config = cls(**config_dict)
        config.validate()
        return config
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert configuration to dictionary.
        
        Returns:
            Dictionary representation of configuration
        """
        return {
            'timeframes': self.timeframes,
            'instruments': self.instruments,
            'execution_mode': self.execution_mode,
            'start_of_day_capital': self.start_of_day_capital,
            'vwap_lookback': self.vwap_lookback,
            'historical_candles_buffer': self.historical_candles_buffer,
            'trend_config': {
                'timeframe': self.trend_config.timeframe,
                'base_position_size': self.trend_config.base_position_size,
                'partial_exit_percentage': self.trend_config.partial_exit_percentage,
                'structure_proximity_atr_multiplier': self.trend_config.structure_proximity_atr_multiplier,
                'vertical_extension_body_threshold': self.trend_config.vertical_extension_body_threshold,
                'vertical_extension_distance_threshold': self.trend_config.vertical_extension_distance_threshold,
                'trend_weakening_candles': self.trend_config.trend_weakening_candles,
                'trend_weakening_reduced_range_count': self.trend_config.trend_weakening_reduced_range_count,
                'ema_period': self.trend_config.ema_period,
            },
            'mr_config': {
                'timeframe': self.mr_config.timeframe,
                'mr_base_size': self.mr_config.mr_base_size,
                'max_mr_position_pct': self.mr_config.max_mr_position_pct,
                'max_mr_trades_per_leg': self.mr_config.max_mr_trades_per_leg,
                'impulse_extension_threshold': self.mr_config.impulse_extension_threshold,
                'consecutive_large_candles_threshold': self.mr_config.consecutive_large_candles_threshold,
                'vwap_distance_atr_multiplier': self.mr_config.vwap_distance_atr_multiplier,
                'retracement_target_min': self.mr_config.retracement_target_min,
                'retracement_target_max': self.mr_config.retracement_target_max,
                'time_stop_candles': self.mr_config.time_stop_candles,
                'structure_touch_atr_multiplier': self.mr_config.structure_touch_atr_multiplier,
                'ema_touch_atr_multiplier': self.mr_config.ema_touch_atr_multiplier,
            },
            'risk_config': {
                'max_daily_loss_pct': self.risk_config.max_daily_loss_pct,
                'max_net_position': self.risk_config.max_net_position,
                'atr_spike_threshold': self.risk_config.atr_spike_threshold,
                'data_feed_timeout_seconds': self.risk_config.data_feed_timeout_seconds,
                'order_slippage_tolerance_pct': self.risk_config.order_slippage_tolerance_pct,
                'atr_period': self.risk_config.atr_period,
            },
            'execution_config': {
                'symbol': self.execution_config.symbol,
                'exchange': self.execution_config.exchange,
                'product': self.execution_config.product,
                'order_timeout': self.execution_config.order_timeout,
                'max_retry_attempts': self.execution_config.max_retry_attempts,
                'retry_backoff_seconds': self.execution_config.retry_backoff_seconds,
            }
        }
