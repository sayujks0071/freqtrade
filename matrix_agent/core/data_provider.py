"""
Data Provider - Market Data Management
=======================================
Data fetching and processing module for the Matrix Agent system.

Handles:
- OHLCV data retrieval
- Multiple timeframe support (5m, 15m, 1h, 4h, 1d)
- Indicator calculation
- Funding rate and OI data

Author: Matrix Agent
Version: 1.0.0
"""

import numpy as np
import pandas as pd
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

from .models import MarketState, PriceLevel, TrendDirection

logger = logging.getLogger(__name__)


@dataclass
class DataConfig:
    """Data provider configuration."""
    exchange: str = "binance"
    default_timeframes: List[str] = None
    lookback_periods: Dict[str, int] = None
    refresh_interval_seconds: int = 60


class DataProvider:
    """
    Data Provider - Market Data Management
    
    Centralized data handling for the trading system:
    - Fetches OHLCV data from exchange
    - Processes multiple timeframes
    - Calculates technical indicators
    - Manages data caching
    """
    
    def __init__(self, config: Optional[DataConfig] = None):
        """
        Initialize Data Provider.
        
        Args:
            config: DataConfig with provider settings
        """
        self.config = config or self._default_config()
        
        self.exchange = self.config.exchange
        self.default_timeframes = self.config.default_timeframes or ['5m', '15m', '1h', '4h', '1d']
        self.lookback_periods = self.config.lookback_periods or {
            '5m': 1000,    # ~3.5 days
            '15m': 1000,   # ~10 days
            '1h': 1000,    # ~42 days
            '4h': 1000,    # ~167 days
            '1d': 365      # ~1 year
        }
        
        # Data cache
        self._data_cache: Dict[str, Dict[str, pd.DataFrame]] = {}
        self._last_refresh: Dict[str, datetime] = {}
        
    def _default_config(self) -> DataConfig:
        """Return default configuration."""
        return DataConfig(
            exchange="binance",
            default_timeframes=['5m', '15m', '1h', '4h', '1d'],
            lookback_periods={
                '5m': 1000,
                '15m': 1000,
                '1h': 1000,
                '4h': 1000,
                '1d': 365
            },
            refresh_interval_seconds=60
        )
    
    def fetch_ohlcv(
        self,
        pair: str,
        timeframe: str = "5m",
        since: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Fetch OHLCV data for a trading pair.
        
        Args:
            pair: Trading pair (e.g., 'BTC/USDT')
            timeframe: Candle timeframe
            since: Start time
            limit: Maximum number of candles
            
        Returns:
            DataFrame with OHLCV data
        """
        # Use default lookback if no limit specified
        if limit is None:
            limit = self.lookback_periods.get(timeframe, 1000)
        
        # Check cache first
        cache_key = f"{pair}_{timeframe}"
        if self._is_cache_valid(cache_key):
            return self._data_cache[cache_key].copy()
        
        # In production, fetch from exchange API
        # For now, generate mock data for demonstration
        data = self._generate_mock_data(pair, timeframe, limit)
        
        # Cache the data
        self._cache_data(cache_key, data)
        
        return data
    
    def _generate_mock_data(
        self,
        pair: str,
        timeframe: str,
        limit: int
    ) -> pd.DataFrame:
        """
        Generate mock OHLCV data for testing.
        
        Args:
            pair: Trading pair
            timeframe: Candle timeframe
            limit: Number of candles
            
        Returns:
            DataFrame with OHLCV data
        """
        # Calculate timeframe in minutes
        timeframe_minutes = self._timeframe_to_minutes(timeframe)
        
        # Generate timestamps
        end_time = datetime.now()
        start_time = end_time - timedelta(minutes=timeframe_minutes * limit)
        
        timestamps = []
        current_time = start_time
        while current_time <= end_time:
            timestamps.append(current_time)
            current_time += timedelta(minutes=timeframe_minutes)
        
        # Generate price data with realistic movement
        base_price = self._get_base_price(pair)
        
        # Create price series with random walk + trend
        np.random.seed(42)  # For reproducibility
        returns = np.random.normal(0.0001, 0.02, len(timestamps))  # 0.01% drift, 2% daily vol
        
        close_prices = [base_price]
        for i in range(1, len(timestamps)):
            new_price = close_prices[-1] * (1 + returns[i])
            close_prices.append(new_price)
        
        # Generate OHLC from close prices
        opens = close_prices[:-1]
        closes = close_prices[1:]
        
        # Generate highs and lows
        intraday_volatility = 0.02
        highs = []
        lows = []
        
        for i in range(len(opens)):
            high = max(opens[i], closes[i]) * (1 + np.random.uniform(0, intraday_volatility))
            low = min(opens[i], closes[i]) * (1 - np.random.uniform(0, intraday_volatility))
            highs.append(high)
            lows.append(low)
        
        # Generate volume
        base_volume = self._get_base_volume(pair)
        volumes = [base_volume * (1 + np.random.uniform(-0.3, 0.5)) for _ in range(len(closes))]
        
        # Create DataFrame
        df = pd.DataFrame({
            'timestamp': timestamps[1:],
            'open': opens,
            'high': highs,
            'low': lows,
            'close': closes,
            'volume': volumes
        })
        
        # Set timestamp as index
        df.set_index('timestamp', inplace=True)
        
        # Add timeframe column for reference
        df['timeframe'] = timeframe
        
        return df
    
    def _timeframe_to_minutes(self, timeframe: str) -> int:
        """Convert timeframe string to minutes."""
        if timeframe.endswith('m'):
            return int(timeframe[:-1])
        elif timeframe.endswith('h'):
            return int(timeframe[:-1]) * 60
        elif timeframe.endswith('d'):
            return int(timeframe[:-1]) * 24 * 60
        else:
            return 5  # Default to 5m
    
    def _get_base_price(self, pair: str) -> float:
        """Get base price for a trading pair."""
        prices = {
            'BTC/USDT': 65000.0,
            'ETH/USDT': 3500.0,
            'SOL/USDT': 150.0
        }
        return prices.get(pair, 1000.0)
    
    def _get_base_volume(self, pair: str) -> float:
        """Get base volume for a trading pair."""
        volumes = {
            'BTC/USDT': 1000000000,  # 1B USDT
            'ETH/USDT': 500000000,   # 500M USDT
            'SOL/USDT': 100000000    # 100M USDT
        }
        return volumes.get(pair, 1000000)
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cached data is still valid."""
        if cache_key not in self._data_cache:
            return False
        
        if cache_key not in self._last_refresh:
            return False
        
        last_refresh = self._last_refresh[cache_key]
        elapsed = (datetime.now() - last_refresh).total_seconds()
        
        return elapsed < self.config.refresh_interval_seconds
    
    def _cache_data(self, cache_key: str, data: pd.DataFrame):
        """Cache data with timestamp."""
        self._data_cache[cache_key] = data
        self._last_refresh[cache_key] = datetime.now()
    
    def fetch_multiple_timeframes(
        self,
        pair: str,
        timeframes: Optional[List[str]] = None
    ) -> Dict[str, pd.DataFrame]:
        """
        Fetch data for multiple timeframes.
        
        Args:
            pair: Trading pair
            timeframes: List of timeframes (default: all configured)
            
        Returns:
            Dictionary of DataFrames by timeframe
        """
        if timeframes is None:
            timeframes = self.default_timeframes
        
        result = {}
        for tf in timeframes:
            try:
                result[tf] = self.fetch_ohlcv(pair, tf)
            except Exception as e:
                logger.error(f"Error fetching {pair} {tf}: {e}")
                result[tf] = pd.DataFrame()
        
        return result
    
    def get_market_state(
        self,
        pair: str,
        funding_rate: float = 0.0,
        open_interest: float = 0.0
    ) -> MarketState:
        """
        Get comprehensive market state for a pair.
        
        Args:
            pair: Trading pair
            funding_rate: Current funding rate
            open_interest: Current open interest
            
        Returns:
            MarketState object with all indicators
        """
        # Fetch multiple timeframe data
        data_5m = self.fetch_ohlcv(pair, "5m")
        data_4h = self.fetch_ohlcv(pair, "4h")
        data_1d = self.fetch_ohlcv(pair, "1d")
        
        if data_5m.empty:
            return MarketState(
                pair=pair,
                current_price=0,
                timestamp=datetime.now()
            )
        
        current_price = data_5m['close'].iloc[-1]
        current_time = data_5m.index[-1]
        
        # Calculate indicators
        rsi_5m = self.calculate_rsi(data_5m['close'].values, period=14)
        rsi_4h = self.calculate_rsi(data_4h['close'].values, period=14)
        rsi_1d = self.calculate_rsi(data_1d['close'].values, period=14)
        
        # Detect trends
        trend_4h = self.detect_trend(data_4h)
        trend_1d = self.detect_trend(data_1d)
        
        # Calculate volatility
        volatility = self.calculate_volatility(data_5m['close'])
        
        # Get 24h volume
        volume_24h = data_5m['volume'].sum() if len(data_5m) >= 288 else 0  # 24h of 5m candles
        
        # Find key levels
        key_levels = self.find_key_levels(data_5m)
        
        return MarketState(
            pair=pair,
            current_price=current_price,
            timestamp=current_time,
            trend_4h=trend_4h,
            trend_1d=trend_1d,
            rsi_4h=rsi_4h,
            rsi_1d=rsi_1d,
            funding_rate=funding_rate,
            open_interest=open_interest,
            volume_24h=volume_24h,
            volatility=volatility,
            key_levels=key_levels
        )
    
    def calculate_rsi(self, data: np.ndarray, period: int = 14) -> float:
        """
        Calculate RSI indicator.
        
        Args:
            data: Price data array
            period: RSI period
            
        Returns:
            Current RSI value
        """
        if len(data) < period + 1:
            return 50.0
        
        delta = np.diff(data)
        gain = np.where(delta > 0, delta, 0)
        loss = np.where(delta < 0, -delta, 0)
        
        avg_gain = np.mean(gain[:period])
        avg_loss = np.mean(loss[:period])
        
        for i in range(period, len(delta)):
            avg_gain = (avg_gain * (period - 1) + gain[i]) / period
            avg_loss = (avg_loss * (period - 1) + loss[i]) / period
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def detect_trend(self, dataframe: pd.DataFrame) -> TrendDirection:
        """
        Detect trend direction from price data.
        
        Args:
            dataframe: OHLCV DataFrame
            
        Returns:
            TrendDirection enum value
        """
        if dataframe is None or len(dataframe) < 50:
            return TrendDirection.UNKNOWN
        
        close = dataframe['close'].values
        
        # Use EMAs for trend detection
        ema_9 = self.calculate_ema(close, 9)
        ema_21 = self.calculate_ema(close, 21)
        ema_50 = self.calculate_ema(close, 50)
        
        current_close = close[-1]
        current_ema_9 = ema_9[-1] if len(ema_9) > 0 else current_close
        current_ema_21 = ema_21[-1] if len(ema_21) > 0 else current_close
        current_ema_50 = ema_50[-1] if len(ema_50) > 0 else current_close
        
        # Check for strong uptrend
        if (current_close > current_ema_50 > current_ema_21 > current_ema_9):
            # Check if price is making higher highs
            recent_highs = dataframe['high'].values[-20:]
            if all(recent_highs[i] <= recent_highs[i+1] for i in range(len(recent_highs)-1)):
                return TrendDirection.UP
        
        # Check for strong downtrend
        if (current_close < current_ema_50 < current_ema_21 < current_ema_9):
            # Check if price is making lower lows
            recent_lows = dataframe['low'].values[-20:]
            if all(recent_lows[i] >= recent_lows[i+1] for i in range(len(recent_lows)-1)):
                return TrendDirection.DOWN
        
        # Check for range-bound
        price_range = max(close[-50:]) - min(close[-50:])
        avg_price = np.mean(close[-50:])
        range_pct = price_range / avg_price if avg_price > 0 else 0
        
        if range_pct < 0.03:
            return TrendDirection.RANGE
        
        return TrendDirection.RANGE  # Default to range
    
    def calculate_ema(self, data: np.ndarray, period: int) -> np.ndarray:
        """Calculate Exponential Moving Average."""
        if len(data) < period:
            return np.array(data)
        
        ema = np.zeros(len(data))
        ema[:period] = data[:period]
        
        multiplier = 2 / (period + 1)
        
        for i in range(period, len(data)):
            ema[i] = (data[i] - ema[i-1]) * multiplier + ema[i-1]
        
        return ema
    
    def calculate_volatility(self, data: pd.Series, period: int = 14) -> float:
        """
        Calculate price volatility.
        
        Args:
            data: Price series
            period: Calculation period
            
        Returns:
            Volatility percentage
        """
        if len(data) < period:
            return 0.02  # Default 2%
        
        returns = data.pct_change().dropna()
        volatility = returns.std() * np.sqrt(1440 / 5)  # Annualize to daily
        
        return min(volatility, 0.5)  # Cap at 50%
    
    def find_key_levels(self, dataframe: pd.DataFrame, num_levels: int = 5) -> List[PriceLevel]:
        """
        Find significant key levels in price data.
        
        Args:
            dataframe: OHLCV DataFrame
            num_levels: Number of levels to find
            
        Returns:
            List of PriceLevel objects
        """
        high = dataframe['high'].values
        low = dataframe['low'].values
        close = dataframe['close'].values
        volume = dataframe['volume'].values
        
        levels = []
        
        # Find swing highs and lows
        lookback = min(50, len(dataframe))
        
        for i in range(lookback, len(dataframe)):
            # Check for swing high
            if high[i] >= max(high[max(0, i-5):min(len(high), i+6)]):
                level = self._create_price_level(
                    high[i], dataframe.index[i], volume[i], 'resistance', close[-1]
                )
                levels.append(level)
            
            # Check for swing low
            if low[i] <= min(low[max(0, i-5):min(len(low), i+6)]):
                level = self._create_price_level(
                    low[i], dataframe.index[i], volume[i], 'support', close[-1]
                )
                levels.append(level)
        
        # Sort and deduplicate
        levels.sort(key=lambda x: x.price)
        
        # Remove levels that are too close
        filtered_levels = []
        min_distance_pct = 0.02  # 2% minimum distance
        
        for level in levels:
            if not filtered_levels:
                filtered_levels.append(level)
            else:
                last = filtered_levels[-1]
                if abs(level.price - last.price) / last.price > min_distance_pct:
                    filtered_levels.append(level)
        
        return filtered_levels[:num_levels]
    
    def _create_price_level(
        self,
        price: float,
        timestamp: datetime,
        volume: float,
        level_type: str,
        current_price: float
    ) -> PriceLevel:
        """Create a PriceLevel object."""
        return PriceLevel(
            price=price,
            timestamp=timestamp,
            volume=volume,
            is_key_level=True,
            level_type=level_type
        )
    
    def get_funding_rate(self, pair: str) -> float:
        """
        Get current funding rate for a pair.
        
        Args:
            pair: Trading pair
            
        Returns:
            Current funding rate
        """
        # In production, fetch from exchange API
        # For now, return mock data
        np.random.seed(hash(pair) % (2**32))
        return np.random.uniform(-0.001, 0.001)
    
    def get_open_interest(self, pair: str) -> float:
        """
        Get current open interest for a pair.
        
        Args:
            pair: Trading pair
            
        Returns:
            Current open interest
        """
        # In production, fetch from exchange API
        # For now, return mock data
        return 100000000  # 100M USDT equivalent
    
    def clear_cache(self):
        """Clear all cached data."""
        self._data_cache.clear()
        self._last_refresh.clear()
        logger.info("Data cache cleared")
    
    def get_cache_status(self) -> Dict[str, Any]:
        """Get cache status and statistics."""
        return {
            'cached_pairs': list(self._data_cache.keys()),
            'cache_entries': len(self._data_cache),
            'last_refreshes': {
                k: v.isoformat() 
                for k, v in self._last_refresh.items()
            }
        }
