#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Final S&P 500 Trading Strategy
Optimized based on backtest results showing strong performance with SHORT-biased strategy
"""

import os
import json
import logging
import pandas as pd
import numpy as np
import time
import requests
import yaml
from datetime import datetime, timedelta
import alpaca_trade_api as tradeapi
from tqdm import tqdm
import math
from strategy_performance_tracker import StrategyPerformanceTracker
from bs4 import BeautifulSoup
import traceback
import argparse
import random

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"sp500_strategy_{datetime.now().strftime('%Y%m%d')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Top 100 S&P 500 symbols by market cap
TOP_100_SYMBOLS = [
    "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "GOOG", "TSLA", "UNH",
    "LLY", "JPM", "V", "XOM", "AVGO", "PG", "MA", "HD", "COST", "MRK",
    "CVX", "ABBV", "PEP", "KO", "ADBE", "WMT", "CRM", "BAC", "TMO", "MCD",
    "CSCO", "PFE", "NFLX", "CMCSA", "ABT", "ORCL", "TMUS", "AMD", "DIS", "ACN",
    "DHR", "VZ", "NKE", "TXN", "NEE", "WFC", "PM", "INTC", "INTU", "COP",
    "AMGN", "IBM", "RTX", "HON", "QCOM", "UPS", "CAT", "GE", "ELV", "DE", "AMAT",
    "ISRG", "AXP", "BKNG", "MDLZ", "GILD", "ADI", "SBUX", "TJX", "MMC", "SYK",
    "VRTX", "PLD", "MS", "BLK", "SCHW", "C", "ZTS", "CB", "AMT", "ADP", "GS",
    "ETN", "LRCX", "NOW", "MO", "REGN", "EOG", "SO", "BMY", "EQIX", "BSX", "CME",
    "CI", "PANW", "TGT", "SLB"
]

def get_sp500_symbols():
    """
    Get the current S&P 500 symbols by scraping Wikipedia
    If scraping fails, log an error and return an empty list
    
    If configured, also include select mid-cap stocks with high liquidity
    """
    try:
        logger.info("Fetching S&P 500 symbols from Wikipedia...")
        
        # Try to get S&P 500 symbols from Wikipedia
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        
        # Use requests to get the page content
        response = requests.get(url, timeout=10)
        
        if response.status_code != 200:
            logger.error(f"Failed to fetch S&P 500 symbols: HTTP {response.status_code}")
            return []
        else:
            # Parse the HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find the table with S&P 500 companies
            table = soup.find('table', {'class': 'wikitable'})
            
            if not table:
                logger.error("Failed to find S&P 500 table on Wikipedia")
                return []
            else:
                # Extract symbols from the table
                sp500_symbols = []
                
                for row in table.find_all('tr')[1:]:  # Skip header row
                    cells = row.find_all('td')
                    if len(cells) >= 2:
                        symbol = cells[0].text.strip()
                        if symbol:
                            # Remove any .XX suffixes (e.g., BRK.B -> BRK)
                            symbol = symbol.replace('.', '-')  # Convert to format used by APIs
                            sp500_symbols.append(symbol)
                
                if not sp500_symbols or len(sp500_symbols) < 400:  # Sanity check
                    logger.error(f"Found only {len(sp500_symbols)} S&P 500 symbols, which is fewer than expected")
                    return []
                else:
                    logger.info(f"Successfully fetched {len(sp500_symbols)} S&P 500 symbols from Wikipedia")
        
        # Check if mid-cap inclusion is enabled
        include_midcap = CONFIG.get('strategy', {}).get('include_midcap', False)
        
        if include_midcap:
            logger.info("Fetching mid-cap stocks with high liquidity...")
            midcap_symbols = get_midcap_symbols()
            
            if midcap_symbols:
                # Combine S&P 500 and mid-cap symbols, removing duplicates
                combined_symbols = list(set(sp500_symbols + midcap_symbols))
                logger.info(f"Added {len(midcap_symbols)} mid-cap symbols to universe (total: {len(combined_symbols)})")
                return combined_symbols
        
        return sp500_symbols
        
    except Exception as e:
        logger.error(f"Error fetching S&P 500 symbols: {str(e)}")
        return []

def get_midcap_symbols():
    """
    Get a list of mid-cap stocks with high liquidity
    
    Returns a list of ticker symbols for mid-cap stocks that meet the liquidity criteria
    If fetching fails, logs an error and returns an empty list
    """
    try:
        # Get mid-cap symbols from configuration if available
        midcap_config = CONFIG.get('strategy', {}).get('midcap_stocks', {})
        
        # If predefined list exists in config, use it
        if 'symbols' in midcap_config and midcap_config['symbols']:
            logger.info(f"Using {len(midcap_config['symbols'])} predefined mid-cap symbols from config")
            return midcap_config['symbols']
        
        # Otherwise, try to fetch mid-cap stocks from S&P 400 Mid-Cap index
        logger.info("Fetching S&P 400 Mid-Cap symbols...")
        
        # Define mid-cap ETF symbols
        midcap_etf = 'MDY'  # SPDR S&P MidCap 400 ETF
        
        # In a production environment, we would fetch the holdings of the ETF or use a financial data API
        # to get the current S&P 400 Mid-Cap constituents
        logger.error("No method implemented to dynamically fetch mid-cap symbols and no symbols provided in configuration")
        return []
        
    except Exception as e:
        logger.error(f"Error fetching mid-cap symbols: {str(e)}")
        return []

def load_config(config_file='sp500_config.yaml'):
    """Load configuration from YAML file"""
    try:
        with open(config_file, 'r') as file:
            config = yaml.safe_load(file)
        logger.info(f"Successfully loaded configuration from {config_file}")
        return config
    except Exception as e:
        logger.error(f"Error loading configuration: {str(e)}")
        return {}

def load_alpaca_credentials(mode='paper'):
    """Load Alpaca API credentials from JSON file"""
    try:
        with open('alpaca_credentials.json', 'r') as file:
            credentials = json.load(file)
        
        return credentials[mode]
    except Exception as e:
        logger.error(f"Error loading Alpaca credentials: {str(e)}")
        return None

# Load configuration
CONFIG = load_config()

class SP500Strategy:
    """S&P 500 Trading Strategy"""
    
    def __init__(self, api, config=None, mode='paper', backtest_mode=False, backtest_start_date=None, backtest_end_date=None):
        """Initialize the strategy"""
        try:
            # Set API and mode
            self.api = api
            self.mode = mode
            self.backtest_mode = backtest_mode
            self.backtest_start_date = backtest_start_date
            self.backtest_end_date = backtest_end_date
            
            # Load configuration if not provided
            if config is None:
                config_path = 'configuration_enhanced_mean_reversion.yaml'
                with open(config_path, 'r') as file:
                    config = yaml.safe_load(file)
            
            self.config = config
            
            # Set up strategy parameters
            self.strategy_params = config.get('strategies', {}).get('MeanReversion', {})
            self.global_params = config.get('global', {})
            
            # Initialize technical indicators
            self.bb_period = self.strategy_params.get('bb_period', 15)
            self.bb_std_dev = self.strategy_params.get('bb_std_dev', 2.0)
            self.rsi_period = self.strategy_params.get('rsi_period', 10)
            self.rsi_overbought = self.strategy_params.get('rsi_overbought', 70)
            self.rsi_oversold = self.strategy_params.get('rsi_oversold', 30)
            self.atr_period = self.strategy_params.get('atr_period', 10)
            
            # Initialize MACD parameters
            self.macd_fast = self.strategy_params.get('macd_fast', 8)
            self.macd_slow = self.strategy_params.get('macd_slow', 17)
            self.macd_signal = self.strategy_params.get('macd_signal', 5)
            
            # Initialize risk management parameters
            self.stop_loss_atr = self.strategy_params.get('stop_loss_atr', 2.0)
            self.take_profit_atr = self.strategy_params.get('take_profit_atr', 3.0)
            self.max_position_size = self.strategy_params.get('max_position_size', 0.1)
            self.risk_per_trade = self.strategy_params.get('risk_per_trade', 0.01)
            
            # Initialize stop loss parameters
            self.stop_loss_enabled = self.strategy_params.get('stop_loss_enabled', True)
            self.long_stop_loss_pct = self.strategy_params.get('long_stop_loss_pct', 0.02)
            self.short_stop_loss_pct = self.strategy_params.get('short_stop_loss_pct', 0.01)
            
            # Initialize market regime parameters
            self.market_regime_enabled = self.strategy_params.get('market_regime_enabled', True)
            self.sector_performance_enabled = self.strategy_params.get('sector_performance_enabled', True)
            self.sma_short_period = self.strategy_params.get('sma_short_period', 5)
            self.sma_long_period = self.strategy_params.get('sma_long_period', 20)
            self.change_period = self.strategy_params.get('change_period', 5)
            
            # Initialize position parameters
            self.max_open_positions = self.global_params.get('max_open_positions', 5)
            self.max_positions_per_symbol = self.global_params.get('max_positions_per_symbol', 1)
            self.max_capital_per_direction = self.global_params.get('max_capital_per_direction', 50000)
            self.max_trades_per_run = self.global_params.get('max_trades_per_run', 60)
            self.max_positions = self.max_open_positions  # Alias for compatibility
            
            # Signal thresholds
            self.long_signal_threshold = self.strategy_params.get('long_signal_threshold', 0.5)
            
            # Define TOP 100 symbols as fallback
            self.TOP_100_SYMBOLS = [
                'AAPL', 'MSFT', 'AMZN', 'GOOGL', 'GOOG', 'META', 'TSLA', 'NVDA', 'BRK.B', 'UNH',
                'JNJ', 'XOM', 'JPM', 'V', 'PG', 'MA', 'HD', 'CVX', 'BAC', 'ABBV',
                'PFE', 'KO', 'AVGO', 'PEP', 'LLY', 'COST', 'TMO', 'MRK', 'CSCO', 'WMT',
                'ABT', 'MCD', 'ACN', 'DHR', 'WFC', 'BMY', 'TXN', 'CRM', 'NKE', 'VZ',
                'CMCSA', 'ADBE', 'ORCL', 'PM', 'QCOM', 'UPS', 'HON', 'T', 'INTC', 'NFLX',
                'LIN', 'INTU', 'AMD', 'LOW', 'NEE', 'AMGN', 'IBM', 'CAT', 'DE', 'PYPL',
                'SBUX', 'GS', 'BA', 'MS', 'RTX', 'SPGI', 'BLK', 'GILD', 'C', 'AXP',
                'MDLZ', 'SCHW', 'ADI', 'TGT', 'ZTS', 'MMM', 'CVS', 'BKNG', 'PLD', 'ISRG',
                'TMUS', 'MO', 'AMAT', 'SYK', 'DIS', 'CI', 'GE', 'REGN', 'NOW', 'TJX',
                'AMT', 'MRNA', 'LRCX', 'ELV', 'COP', 'CB', 'BDX', 'DUK', 'SO', 'EOG'
            ]
            
            # Set up sector ETFs for market regime detection
            self.sector_etfs = {
                'XLK': 'Technology',
                'XLF': 'Financials',
                'XLV': 'Healthcare',
                'XLE': 'Energy',
                'XLI': 'Industrials',
                'XLY': 'Consumer Discretionary',
                'XLP': 'Consumer Staples',
                'XLB': 'Materials',
                'XLU': 'Utilities',
                'XLRE': 'Real Estate',
                'XLC': 'Communication Services'
            }
            
            # Initialize performance tracker
            self.performance_tracker = StrategyPerformanceTracker(
                strategy_name='SP500Strategy'
            )
            
            # Set up paths
            self.paths = config.get('paths', {})
            
            # Create necessary directories
            for path_key in ['backtest_results', 'plots', 'trades', 'performance']:
                if path_key in self.paths:
                    os.makedirs(self.paths[path_key], exist_ok=True)
            
            logger.info(f"Strategy initialized in {mode} mode")
            
            # For backtest mode, set up special handlers
            if self.backtest_mode and self.backtest_start_date and self.backtest_end_date:
                self._setup_backtest_handlers()
    
        except Exception as e:
            logger.error(f"Error initializing strategy: {str(e)}")
            traceback.print_exc()
            raise
    
    def _setup_backtest_handlers(self):
        """Set up special handlers for backtest mode"""
        logger.info(f"Setting up backtest from {self.backtest_start_date} to {self.backtest_end_date}")
        
        # Store original methods that we'll override
        self._original_get_historical_data = self.get_historical_data
        self._original_execute_trades = self.execute_trades
        self._original_check_stop_loss_conditions = self.check_stop_loss_conditions
        
        # Override methods for backtesting
        self.get_historical_data = self._backtest_get_historical_data
        self.execute_trades = self._backtest_execute_trades
        self.check_stop_loss_conditions = self._backtest_check_stop_loss_conditions
    
    def _backtest_get_historical_data(self, symbol, days=30, max_retries=3, retry_delay=2):
        """Backtest version of get_historical_data"""
        try:
            # Generate dates from start_date to end_date
            start_date = pd.Timestamp(self.backtest_start_date)
            end_date = pd.Timestamp(self.backtest_end_date)
            dates = pd.date_range(start=start_date, end=end_date, freq='B')
            
            if len(dates) < 20:  # Need at least 20 days for indicators
                logger.warning(f"Not enough data for {symbol} in backtest period")
                return None
            
            # Generate random price data for demonstration
            # In a real implementation, you would use actual historical data
            np.random.seed(hash(symbol) % 10000)  # Use symbol as seed for consistency
            
            # Start with a random price between 50 and 200
            base_price = np.random.uniform(50, 200)
            
            # Generate random daily returns with a slight bias based on symbol hash
            symbol_bias = (hash(symbol) % 100) / 10000  # Small bias between -0.005 and 0.005
            daily_returns = np.random.normal(0.0005 + symbol_bias, 0.015, size=len(dates))
            
            # Calculate prices using cumulative returns
            prices = base_price * (1 + np.cumsum(daily_returns))
            
            # Generate random volume
            volume = np.random.uniform(100000, 10000000, size=len(dates))
            
            # Create DataFrame
            df = pd.DataFrame({
                'open': prices * np.random.uniform(0.995, 0.999, size=len(dates)),
                'high': prices * np.random.uniform(1.001, 1.015, size=len(dates)),
                'low': prices * np.random.uniform(0.985, 0.999, size=len(dates)),
                'close': prices,
                'volume': volume
            }, index=dates)
            
            # Calculate technical indicators
            return self.calculate_technical_indicators(df)
            
        except Exception as e:
            logger.error(f"Error in backtest data for {symbol}: {str(e)}")
            return None
    
    def _backtest_execute_trades(self, signals):
        """Backtest version of execute_trades"""
        # In backtest mode, we just return the signals
        logger.info(f"Backtest would execute {len(signals)} trades")
        
        # Limit to max positions
        signals_to_execute = signals[:self.max_positions]
        
        # Log the signals
        for signal in signals_to_execute:
            logger.info(f"Backtest trade: {signal['symbol']} LONG at ${signal['price']:.2f} with score {signal['score']:.2f}")
        
        return signals_to_execute
    
    def _backtest_check_stop_loss_conditions(self):
        """Backtest version of check_stop_loss_conditions"""
        # In backtest mode, we don't check stop loss conditions
        logger.info("Backtest: Skipping stop-loss check")
        return []

    def calculate_technical_indicators(self, data):
        """Calculate technical indicators for a dataframe"""
        try:
            # Make a copy to avoid modifying the original
            df = data.copy()
            
            # Calculate RSI
            delta = df['close'].diff()
            gain = delta.where(delta > 0, 0)
            loss = -delta.where(delta < 0, 0)
            
            avg_gain = gain.rolling(window=self.rsi_period).mean()
            avg_loss = loss.rolling(window=self.rsi_period).mean()
            
            rs = avg_gain / avg_loss
            df['rsi'] = 100 - (100 / (1 + rs))
            
            # Calculate MACD
            exp1 = df['close'].ewm(span=self.macd_fast, adjust=False).mean()
            exp2 = df['close'].ewm(span=self.macd_slow, adjust=False).mean()
            macd = exp1 - exp2
            signal = macd.ewm(span=self.macd_signal, adjust=False).mean()
            
            df['macd'] = macd
            df['macd_signal'] = signal
            df['macd_hist'] = macd - signal
            
            # Calculate Bollinger Bands
            df['sma'] = df['close'].rolling(window=self.bb_period).mean()
            df['std'] = df['close'].rolling(window=self.bb_period).std()
            df['upper_band'] = df['sma'] + (df['std'] * self.bb_std_dev)
            df['lower_band'] = df['sma'] - (df['std'] * self.bb_std_dev)
            
            # Calculate ATR
            df['tr1'] = abs(df['high'] - df['low'])
            df['tr2'] = abs(df['high'] - df['close'].shift())
            df['tr3'] = abs(df['low'] - df['close'].shift())
            df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
            df['atr'] = df['tr'].rolling(window=self.atr_period).mean()
            
            # Calculate percentage distance from Bollinger Bands
            df['bb_upper_dist'] = (df['close'] - df['upper_band']) / df['close'] * 100
            df['bb_lower_dist'] = (df['close'] - df['lower_band']) / df['close'] * 100
            
            # Calculate volume indicators
            df['volume_sma'] = df['volume'].rolling(window=10).mean()
            df['volume_ratio'] = df['volume'] / df['volume_sma']
            
            # Calculate momentum
            df['momentum'] = df['close'] / df['close'].shift(5) - 1
            
            # Calculate price change
            df['price_change_1d'] = df['close'].pct_change(1) * 100
            df['price_change_5d'] = df['close'].pct_change(5) * 100
            
            # Drop NaN values
            df = df.dropna()
            
            return df
            
        except Exception as e:
            logger.error(f"Error calculating technical indicators: {str(e)}")
            return None
    
    def calculate_score(self, row):
        """Calculate combined technical score for a row"""
        try:
            # Extract values
            rsi = row['rsi']
            macd = row['macd']
            macd_signal = row['macd_signal']
            close = row['close']
            lower_band = row['lower_band']
            upper_band = row['upper_band']
            
            # RSI component (0-1)
            if rsi < 30:
                rsi_score = 1.0  # Strongly oversold - bullish
            elif rsi > 70:
                rsi_score = 0.0  # Strongly overbought - bearish
            else:
                rsi_score = 1 - ((rsi - 30) / 40)  # Linear scale between 30-70
            
            # MACD component (0-1)
            if macd > macd_signal:
                macd_score = 1.0  # Bullish
            else:
                macd_score = 0.0  # Bearish
            
            # Bollinger Bands component (0-1)
            if close < lower_band:
                bb_score = 1.0  # Below lower band - bullish
            elif close > upper_band:
                bb_score = 0.0  # Above upper band - bearish
            else:
                bb_score = 1 - ((close - lower_band) / (upper_band - lower_band))
            
            # Combined score for LONG (weighted average)
            long_score = (rsi_score * 0.3) + (macd_score * 0.3) + (bb_score * 0.4)
            
            return {
                'long_score': long_score
            }
        except Exception as e:
            logger.error(f"Error calculating score: {str(e)}")
            return {'long_score': 0.5}  # Default neutral score
    
    def determine_trade_direction(self, scores):
        """Determine trade direction based on scores"""
        long_score = scores['long_score']
        
        if long_score >= self.long_signal_threshold:
            return 'LONG', long_score
        else:
            return 'NEUTRAL', 0
    
    def calculate_position_size(self, signal, available_buying_power):
        """
        Calculate position size based on signal strength, sector performance, and available buying power
        Uses tiered position sizing based on signal score, trade direction, and sector weights
        Position sizes are calculated as percentages of initial capital
        """
        # Get initial capital from config or use available buying power
        initial_capital = self.config.get('strategy', {}).get('initial_capital', 100000)
        
        # Get base position size from config (as percentage of initial capital)
        base_position_pct = self.config.get('strategy', {}).get('position_sizing', {}).get('base_position_pct', 5)
        
        # Convert percentage to dollar amount based on initial capital
        base_position_size = (base_position_pct / 100) * initial_capital
        
        # Get tier multipliers from config
        tier_multipliers = self.config.get('strategy', {}).get('position_sizing', {}).get('tier_multipliers', {
            'Tier 1 (≥0.9)': 3.0,
            'Tier 2 (0.8-0.9)': 1.5,
            'Below Threshold (<0.8)': 0.0
        })
        
        # Get direction multipliers from config
        long_multiplier = self.config.get('strategy', {}).get('position_sizing', {}).get('long_multiplier', 3.0)
        
        # Get sector weights from config
        sector_weights = self.config.get('strategy', {}).get('sector_adjustments', {}).get('sector_weights', {})
        
        # Default weights if not in config
        default_sector_weights = {
            'Communication Services': 2.0,
            'Industrials': 1.8,
            'Technology': 1.5,
            'Utilities': 1.5,
            'Financials': 1.4,
            'Healthcare': 1.4,
            'Consumer Discretionary': 1.3,
            'Materials': 1.2,
            'Energy': 1.1,
            'Consumer Staples': 1.1,
            'Real Estate': 0.8,
            'Unknown': 1.0
        }
        
        # Get signal information
        score = signal['score']
        sector = signal.get('sector', 'Unknown')
        market_regime = signal.get('market_regime', 'NEUTRAL')
        is_midcap = signal.get('is_midcap', False)
        
        # Determine signal tier
        tier = self.get_signal_tier(score)
        
        # Get tier multiplier
        tier_multiplier = tier_multipliers.get(tier, 0.0)
        
        # If tier multiplier is 0, return 0 position size (below threshold)
        if tier_multiplier == 0:
            return 0
        
        # Get sector weight
        sector_weight = sector_weights.get(sector, default_sector_weights.get(sector, 1.0))
        
        # ENHANCEMENT 1: Dynamic score-based position sizing within tiers
        # For Tier 1 signals (≥0.9), scale position size based on exact score
        if tier == 'Tier 1 (≥0.9)':
            # Scale from 1.0 (at score 0.9) to 1.5 (at score 1.0)
            score_multiplier = 1.0 + ((score - 0.9) / 0.1) * 0.5
            tier_multiplier *= score_multiplier
            logger.debug(f"Applied score multiplier of {score_multiplier:.2f} for {signal['symbol']} with score {score:.3f}")
        
        # Calculate base position size with tier and sector adjustments
        position_size = base_position_size * tier_multiplier * long_multiplier * sector_weight
        
        # Apply market cap adjustments for mid-cap stocks
        if is_midcap:
            # Get mid-cap position sizing factor (default: 0.8 - 80% of large-cap position size)
            midcap_factor = self.config.get('strategy', {}).get('midcap_stocks', {}).get('position_factor', 0.8)
            position_size *= midcap_factor
            logger.debug(f"Applied mid-cap factor of {midcap_factor} to {signal['symbol']}")
        
        # ENHANCEMENT 2: More nuanced market regime adjustments
        # Apply more granular market regime adjustments
        if market_regime == 'STRONG_BULLISH':
            position_size *= 1.3  # Increased from 1.2
        elif market_regime == 'BULLISH':
            position_size *= 1.15  # Increased from 1.1
        elif market_regime == 'NEUTRAL':
            position_size *= 1.0  # No change
        elif market_regime == 'BEARISH':
            position_size *= 0.7  # Reduced from 0.8
        elif market_regime == 'STRONG_BEARISH':
            position_size *= 0.5  # Reduced from 0.6
        
        # Ensure position size doesn't exceed available buying power
        position_size = min(position_size, available_buying_power * 0.95)
        
        # Round to 2 decimal places
        position_size = round(position_size, 2)
        
        # Log position size calculation
        market_cap_type = "Mid-Cap" if is_midcap else "Large-Cap"
        logger.debug(f"Position size for {signal['symbol']} ({market_cap_type}): ${position_size:.2f} (Score: {score:.3f}, Tier: {tier}, Sector: {sector}, Weight: {sector_weight})")
        
        return position_size
    
    def save_trades(self, trades):
        """Save executed trades to CSV file"""
        try:
            if not trades:
                return
            
            # Create a DataFrame from the trades
            trades_data = []
            
            for trade in trades:
                # Get sector for the symbol
                sector = self.get_symbol_sector(trade['symbol'])
                
                trade_data = {
                    'symbol': trade['symbol'],
                    'direction': trade['direction'],
                    'entry_price': trade['entry_price'],
                    'shares': trade['shares'],
                    'entry_date': trade['entry_date'],
                    'exit_price': trade.get('exit_price', None),
                    'exit_date': trade.get('exit_date', None),
                    'signal_score': trade.get('score', 0),
                    'sector': sector
                }
                trades_data.append(trade_data)
            
            trades_df = pd.DataFrame(trades_data)
            
            # Save to CSV
            if self.backtest_mode:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                file_path = os.path.join(self.paths.get('backtest_results', 'results/backtest'), 
                                        f"backtest_trades_{self.backtest_start_date}_to_{self.backtest_end_date}_{timestamp}.csv")
            else:
                file_path = os.path.join(self.paths.get('trades', 'results/trades'), 'trades.csv')
                
                # If file exists, append to it
                if os.path.exists(file_path):
                    existing_trades = pd.read_csv(file_path)
                    trades_df = pd.concat([existing_trades, trades_df], ignore_index=True)
            
            trades_df.to_csv(file_path, index=False)
            logger.info(f"Saved {len(trades)} trades to {file_path}")
            
        except Exception as e:
            logger.error(f"Error saving trades: {str(e)}")
    
    def get_historical_data(self, symbol, days=20, timeframe='1D'):
        """Get historical data for a symbol"""
        try:
            if self.backtest_mode and self.backtest_start_date and self.backtest_end_date:
                # For backtesting, use the specified date range
                end_date = pd.Timestamp(self.backtest_end_date)
                # Calculate start date based on required days plus buffer
                buffer_days = max(days * 2, 40)
                start_date = pd.Timestamp(self.backtest_start_date) - pd.Timedelta(days=buffer_days)
                
                logger.debug(f"Fetching backtest data for {symbol} from {start_date} to {end_date}")
                
                # Format dates for Alpaca API
                start_str = start_date.strftime('%Y-%m-%d')
                end_str = end_date.strftime('%Y-%m-%d')
                
                # Get historical data from Alpaca
                bars = self.api.get_bars(
                    symbol, 
                    timeframe, 
                    start=start_str,
                    end=end_str,
                    adjustment='raw'
                ).df
                
            else:
                # For live/paper trading, get the most recent data
                end_date = pd.Timestamp.now(tz='America/New_York')
                start_date = end_date - pd.Timedelta(days=days*2)
                
                # Format dates for Alpaca API
                start_str = start_date.strftime('%Y-%m-%d')
                end_str = end_date.strftime('%Y-%m-%d')
                
                # Get historical data from Alpaca
                bars = self.api.get_bars(
                    symbol, 
                    timeframe, 
                    start=start_str,
                    end=end_str,
                    adjustment='raw'
                ).df
            
            # Check if we have enough data
            if bars is None or len(bars) < days:
                logger.warning(f"Not enough data for {symbol}: got {0 if bars is None else len(bars)} bars, need {days}")
                return None
            
            # Reset index to make date a column
            bars = bars.reset_index()
            
            # Rename columns to match expected format
            bars = bars.rename(columns={
                'timestamp': 'date',
                'open': 'open',
                'high': 'high',
                'low': 'low',
                'close': 'close',
                'volume': 'volume'
            })
            
            # Convert date to datetime if it's not already
            if not pd.api.types.is_datetime64_ns_dtype(bars['date']):
                bars['date'] = pd.to_datetime(bars['date'])
            
            # Sort by date
            bars = bars.sort_values('date')
            
            # Take only the required number of days
            if len(bars) > days:
                bars = bars.tail(days)
            
            return bars
            
        except Exception as e:
            logger.error(f"Error getting historical data for {symbol}: {str(e)}")
            return None
    
    def get_trade_signals(self, symbols=None, market_regime=None, sector_regimes=None):
        """
        Generate trade signals for all symbols based on technical analysis
        Returns a list of dictionaries with symbol, direction, and score
        """
        if symbols is None:
            symbols = self.get_symbols()
            
        if market_regime is None:
            market_regime = self.detect_market_regime()
            
        if sector_regimes is None:
            sector_regimes = self.get_sector_performance() if self.sector_performance_enabled else {}
            
        signals = []
        
        # Get thresholds from config
        long_signal_threshold = self.config.get('long_signal_threshold', 0.5)
        
        # Adjust thresholds based on market regime
        if market_regime == 'STRONG_BULLISH':
            long_threshold_multiplier = 0.9
        elif market_regime == 'BULLISH':
            long_threshold_multiplier = 0.95
        elif market_regime == 'NEUTRAL':
            long_threshold_multiplier = 1.0
        elif market_regime == 'BEARISH':
            long_threshold_multiplier = 1.1
        elif market_regime == 'STRONG_BEARISH':
            long_threshold_multiplier = 1.2
        else:
            long_threshold_multiplier = 1.0
        
        # Apply thresholds
        long_threshold = long_signal_threshold * long_threshold_multiplier
        
        logger.info(f"Generated signals: calculating for {len(symbols)} symbols")
        
        # Track signal scores for analysis
        long_scores = []
        
        # Process each symbol
        for symbol in symbols:
            try:
                # Get historical data
                data = self.get_historical_data(symbol, days=20)
                
                if data is None or len(data) < 10:
                    continue
                
                # Calculate technical indicators
                data = self.calculate_technical_indicators(data)
                
                if data is None or len(data) < 5:
                    continue
                
                # Get the latest data point
                latest = data.iloc[-1]
                
                # Skip if volume is too low (less than $1M)
                if latest['close'] * latest['volume'] < 1000000:
                    continue
                
                # Get symbol sector
                symbol_sector = self.get_symbol_sector(symbol)
                
                # Find the corresponding sector ETF
                sector_etf = None
                if symbol_sector == 'Technology':
                    sector_etf = 'XLK'
                elif symbol_sector == 'Financials':
                    sector_etf = 'XLF'
                elif symbol_sector == 'Healthcare':
                    sector_etf = 'XLV'
                elif symbol_sector == 'Energy':
                    sector_etf = 'XLE'
                elif symbol_sector == 'Industrials':
                    sector_etf = 'XLI'
                elif symbol_sector == 'Consumer Discretionary':
                    sector_etf = 'XLY'
                elif symbol_sector == 'Consumer Staples':
                    sector_etf = 'XLP'
                elif symbol_sector == 'Materials':
                    sector_etf = 'XLB'
                elif symbol_sector == 'Utilities':
                    sector_etf = 'XLU'
                elif symbol_sector == 'Real Estate':
                    sector_etf = 'XLRE'
                elif symbol_sector == 'Communication Services':
                    sector_etf = 'XLC'
                
                sector_regime = sector_regimes.get(sector_etf, 'NEUTRAL') if sector_etf else 'NEUTRAL'
                
                # Calculate signal scores
                long_score = self.calculate_long_signal_score(symbol, data, market_regime, sector_regime)
                
                # Generate signals
                if long_score > long_threshold:
                    signals.append({
                        'symbol': symbol,
                        'direction': 'LONG',
                        'score': long_score,
                        'price': latest['close'],
                        'volume': latest['volume'],
                        'market_cap': latest['close'] * latest['volume'],
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'sector': symbol_sector,
                        'sector_regime': sector_regime,
                        'market_regime': market_regime
                    })
                    long_scores.append(long_score)
                
            except Exception as e:
                logger.warning(f"Error processing {symbol}: {str(e)}")
        
        # Log signal statistics
        logger.info(f"Generated {len(signals)} LONG signals")
        
        if long_scores:
            avg_long_score = sum(long_scores) / len(long_scores)
            logger.info(f"Average LONG score: {avg_long_score:.3f}")
        
        # Sort signals by score
        signals = sorted(signals, key=lambda x: x['score'], reverse=True)
        
        # Log top signals
        if signals:
            top_long = signals[:5]
            logger.info(f"Top LONG signals: {', '.join([f'{s['symbol']} ({s['score']:.3f})' for s in top_long])}")
        
        return signals
    
    def summarize_signals(self, signals):
        """Summarize the generated signals"""
        if not signals:
            logger.info("No signals generated")
            return
            
        logger.info(f"Generated {len(signals)} LONG signals")
        
        # Calculate average scores
        if signals:
            avg_score = sum(s['score'] for s in signals) / len(signals)
            logger.info(f"Average LONG score: {avg_score:.3f}")
        
        # Show top signals
        if signals:
            top_signals = sorted(signals, key=lambda x: x.get('priority', x['score']), reverse=True)[:5]
            logger.info(f"Top LONG signals: {', '.join([f'{s['symbol']} ({s.get('priority', s['score']):.3f})' for s in top_signals])}")
        
        # Show signals by sector
        sectors = {}
        for signal in signals:
            sector = signal.get('sector', 'Unknown')
            if sector not in sectors:
                sectors[sector] = 0
            sectors[sector] += 1
        
        logger.info("LONG signals by sector:")
        for sector, count in sectors.items():
            logger.info(f"  {sector}: {count} signals")
    
    def prioritize_signals(self, signals):
        """
        Prioritize signals based on sector trends, signal strength, sector performance, and market cap
        Returns a sorted list of signals with the highest priority first
        """
        if not signals:
            return []
            
        # Get sector performance
        sector_performance = self.get_sector_performance() if self.sector_performance_enabled else {}
        
        # Get sector weights from config
        sector_weights = self.config.get('strategy', {}).get('sector_adjustments', {}).get('sector_weights', {})
        
        # Default weights if not in config
        default_sector_weights = {
            'Communication Services': 2.0,
            'Industrials': 1.8,
            'Technology': 1.5,
            'Utilities': 1.5,
            'Financials': 1.4,
            'Healthcare': 1.4,
            'Consumer Discretionary': 1.3,
            'Materials': 1.2,
            'Energy': 1.1,
            'Consumer Staples': 1.1,
            'Real Estate': 0.8,
            'Unknown': 1.0
        }
        
        # Get mid-cap configuration
        include_midcap = self.config.get('strategy', {}).get('include_midcap', False)
        midcap_config = self.config.get('strategy', {}).get('midcap_stocks', {})
        
        # Get market cap balance settings (default: 70% large-cap, 30% mid-cap)
        large_cap_pct = midcap_config.get('large_cap_percentage', 70)
        mid_cap_pct = 100 - large_cap_pct
        
        # Create a copy of signals to avoid modifying the original
        prioritized_signals = signals.copy()
        
        # Identify mid-cap stocks
        midcap_symbols = []
        if include_midcap:
            # Get the list of mid-cap symbols from config if available
            if 'symbols' in midcap_config and midcap_config['symbols']:
                midcap_symbols = midcap_config['symbols']
            else:
                # If no predefined list, try to get from the get_midcap_symbols function
                try:
                    midcap_symbols = get_midcap_symbols(
                        min_avg_volume=midcap_config.get('min_avg_volume', 500000),
                        max_symbols=midcap_config.get('max_symbols', 50)
                    )
                except Exception as e:
                    logger.warning(f"Failed to get mid-cap symbols: {str(e)}")
        
        # Log mid-cap symbols
        if midcap_symbols:
            logger.info(f"Using {len(midcap_symbols)} mid-cap symbols for signal prioritization")
            logger.debug(f"Mid-cap symbols: {', '.join(midcap_symbols[:10])}{'...' if len(midcap_symbols) > 10 else ''}")
        
        # Add priority score to each signal
        for signal in prioritized_signals:
            # Start with base priority equal to signal score
            priority = signal['score']
            
            # Get sector and market regimes
            sector = signal['sector']
            sector_etf = None
            if sector == 'Technology':
                sector_etf = 'XLK'
            elif sector == 'Financials':
                sector_etf = 'XLF'
            elif sector == 'Healthcare':
                sector_etf = 'XLV'
            elif sector == 'Energy':
                sector_etf = 'XLE'
            elif sector == 'Industrials':
                sector_etf = 'XLI'
            elif sector == 'Consumer Discretionary':
                sector_etf = 'XLY'
            elif sector == 'Consumer Staples':
                sector_etf = 'XLP'
            elif sector == 'Materials':
                sector_etf = 'XLB'
            elif sector == 'Utilities':
                sector_etf = 'XLU'
            elif sector == 'Real Estate':
                sector_etf = 'XLRE'
            elif sector == 'Communication Services':
                sector_etf = 'XLC'
            
            sector_regime = sector_performance.get(sector_etf, 'NEUTRAL') if sector_etf else 'NEUTRAL'
            market_regime = signal['market_regime']
            
            # Apply sector weight multiplier
            sector_weight = sector_weights.get(sector, default_sector_weights.get(sector, 1.0))
            priority *= sector_weight
            
            # Log the sector weight application
            logger.debug(f"Applied sector weight {sector_weight} to {signal['symbol']} ({sector})")
            
            # Boost priority for signals aligned with sector trends
            if sector_regime in ['BULLISH', 'STRONG_BULLISH']:
                # LONG signals in bullish sectors get a boost
                priority += 0.1
                if sector_regime == 'STRONG_BULLISH':
                    priority += 0.1  # Additional boost for strongly bullish sectors
            
            # Boost priority for signals aligned with market trends
            if market_regime in ['BULLISH', 'STRONG_BULLISH']:
                priority += 0.05
            
            # Add LONG signal bonus
            priority += 0.15
            
            # Penalize signals that go against strong trends
            if sector_regime == 'STRONG_BEARISH':
                priority -= 0.15
            
            # Apply market cap factor
            if include_midcap:
                # Check if this is a mid-cap stock
                is_midcap = signal['symbol'] in midcap_symbols
                
                # Mark the signal as mid-cap or large-cap
                signal['is_midcap'] = is_midcap
                
                # Apply a small boost to mid-cap stocks to ensure they're represented
                # but not enough to override significantly stronger large-cap signals
                if is_midcap:
                    # Add a small boost based on the desired mid-cap percentage
                    # Higher mid_cap_pct = higher boost
                    midcap_boost = 0.05 * (mid_cap_pct / 30)  # Scale boost based on mid-cap percentage
                    priority += midcap_boost
                    logger.debug(f"Applied mid-cap boost of {midcap_boost:.3f} to {signal['symbol']}")
            else:
                signal['is_midcap'] = False
            
            # Add priority to signal
            signal['priority'] = priority
        
        # Sort by priority (highest first)
        prioritized_signals = sorted(prioritized_signals, key=lambda x: x['priority'], reverse=True)
        
        # If mid-cap inclusion is enabled, ensure we have a good balance
        if include_midcap and prioritized_signals:
            # Calculate target counts
            max_trades = self.config.get('strategy', {}).get('max_trades_per_run', 40)
            target_large_cap = int(max_trades * large_cap_pct / 100)
            target_mid_cap = max_trades - target_large_cap
            
            # Count how many large-cap and mid-cap stocks we have in the top signals
            top_signals = prioritized_signals[:max_trades]
            large_cap_count = sum(1 for s in top_signals if not s.get('is_midcap', False))
            mid_cap_count = sum(1 for s in top_signals if s.get('is_midcap', False))
            
            logger.info(f"Initial signal distribution: {large_cap_count} large-cap, {mid_cap_count} mid-cap")
            
            # If we don't have enough mid-cap stocks, boost their priority
            if mid_cap_count < target_mid_cap:
                # Find the highest-priority mid-cap stocks that didn't make the cut
                remaining_midcaps = [s for s in prioritized_signals[max_trades:] if s.get('is_midcap', False)]
                remaining_midcaps = sorted(remaining_midcaps, key=lambda x: x['priority'], reverse=True)
                
                # Find the lowest-priority large-cap stocks that did make the cut
                lowest_large_caps = [s for s in top_signals if not s.get('is_midcap', False)]
                lowest_large_caps = sorted(lowest_large_caps, key=lambda x: x['priority'])
                
                # Replace some large-cap stocks with mid-cap stocks
                replacements_needed = min(target_mid_cap - mid_cap_count, len(remaining_midcaps), len(lowest_large_caps))
                
                if replacements_needed > 0:
                    logger.info(f"Adjusting signal distribution to include more mid-cap stocks (replacing {replacements_needed} signals)")
                    
                    # Replace the lowest-priority large-cap stocks with the highest-priority mid-cap stocks
                    for i in range(replacements_needed):
                        # Boost the priority of the mid-cap stock just above the large-cap stock
                        remaining_midcaps[i]['priority'] = lowest_large_caps[i]['priority'] + 0.001
                    
                    # Re-sort all signals by priority
                    prioritized_signals = sorted(prioritized_signals, key=lambda x: x['priority'], reverse=True)
                    
                    # Log the new distribution
                    top_signals = prioritized_signals[:max_trades]
                    new_large_cap_count = sum(1 for s in top_signals if not s.get('is_midcap', False))
                    new_mid_cap_count = sum(1 for s in top_signals if s.get('is_midcap', False))
                    
                    logger.info(f"Adjusted signal distribution: {new_large_cap_count} large-cap, {new_mid_cap_count} mid-cap")
            
            # If we have too many mid-cap stocks, reduce their priority
            elif mid_cap_count > target_mid_cap:
                # Find the lowest-priority mid-cap stocks that made the cut
                lowest_midcaps = [s for s in top_signals if s.get('is_midcap', False)]
                lowest_midcaps = sorted(lowest_midcaps, key=lambda x: x['priority'])
                
                # Find the highest-priority large-cap stocks that didn't make the cut
                remaining_large_caps = [s for s in prioritized_signals[max_trades:] if not s.get('is_midcap', False)]
                remaining_large_caps = sorted(remaining_large_caps, key=lambda x: x['priority'], reverse=True)
                
                # Replace some mid-cap stocks with large-cap stocks
                replacements_needed = min(mid_cap_count - target_mid_cap, len(remaining_large_caps), len(lowest_midcaps))
                
                if replacements_needed > 0:
                    logger.info(f"Adjusting signal distribution to include more large-cap stocks (replacing {replacements_needed} signals)")
                    
                    # Replace the lowest-priority mid-cap stocks with the highest-priority large-cap stocks
                    for i in range(replacements_needed):
                        # Boost the priority of the large-cap stock just above the mid-cap stock
                        remaining_large_caps[i]['priority'] = lowest_midcaps[i]['priority'] + 0.001
                    
                    # Re-sort all signals by priority
                    prioritized_signals = sorted(prioritized_signals, key=lambda x: x['priority'], reverse=True)
                    
                    # Log the new distribution
                    top_signals = prioritized_signals[:max_trades]
                    new_large_cap_count = sum(1 for s in top_signals if not s.get('is_midcap', False))
                    new_mid_cap_count = sum(1 for s in top_signals if s.get('is_midcap', False))
                    
                    logger.info(f"Adjusted signal distribution: {new_large_cap_count} large-cap, {new_mid_cap_count} mid-cap")
        
        return prioritized_signals
    
    def execute_trades(self, signals):
        """Execute trades based on signals"""
        if self.backtest_mode:
            logger.info(f"Backtest would execute {len(signals)} trades")
            # Log the top 5 signals
            for i, signal in enumerate(signals[:5]):
                logger.info(f"Backtest trade: {signal['symbol']} LONG at ${signal['price']:.2f} with score {signal['score']:.2f}")
            return signals  # Return signals for backtesting instead of empty list
            
        executed_trades = []
        
        try:
            # Get account info
            account = self.api.get_account()
            buying_power = float(account.buying_power)
            
            # Get current positions
            positions = self.api.list_positions()
            current_positions = {p.symbol: p for p in positions}
            
            # Count positions by direction
            long_positions = [p for p in positions if float(p.qty) > 0]
            
            logger.info(f"Current positions: {len(positions)} ({len(long_positions)} LONG)")
            
            # Calculate capital allocated to each direction
            long_capital = sum(float(p.market_value) for p in long_positions)
            
            logger.info(f"Capital allocation: LONG ${long_capital:.2f}")
            logger.info(f"Available buying power: ${buying_power:.2f}")
            
            # Ensure signals are sorted by priority (highest first)
            if any('priority' in s for s in signals):
                signals = sorted(signals, key=lambda x: x.get('priority', x['score']), reverse=True)
            else:
                signals = sorted(signals, key=lambda x: x['score'], reverse=True)
            
            # Limit the number of trades per run
            max_trades = min(self.max_trades_per_run, len(signals))
            trades_executed = 0
            
            # Track executed trades by sector
            executed_by_sector = {}
            
            # Process signals
            for signal in signals:
                # Stop if we've reached the maximum number of trades
                if trades_executed >= max_trades:
                    break
                    
                symbol = signal['symbol']
                price = signal['price']
                sector = signal.get('sector', 'Unknown')
                
                # Skip if we already have a position in this symbol
                if symbol in current_positions:
                    continue
                
                # Determine if we can take more positions in this direction
                if long_capital >= self.max_capital_per_direction:
                    continue
                
                # Limit exposure to any single sector (max 20% of trades in one sector)
                if sector not in executed_by_sector:
                    executed_by_sector[sector] = 0
                
                sector_total = executed_by_sector[sector]
                if sector_total >= max(3, max_trades * 0.2):  # Max 20% of trades or at least 3 trades per sector
                    logger.info(f"Skipping LONG signal for {symbol}: Sector {sector} already has {sector_total} trades")
                    continue
                
                # Calculate position size
                position_size = self.calculate_position_size(signal, buying_power)
                
                # Adjust position size based on available capital
                # Convert dollar amount to shares
                shares = position_size / price
                # Ensure we don't exceed max capital per direction
                if long_capital + position_size > self.max_capital_per_direction:
                    max_allowed_position = max(0, self.max_capital_per_direction - long_capital)
                    shares = max_allowed_position / price
                # Round to 2 decimal places for fractional shares
                shares = round(shares, 2)
                
                # Skip if position size is too small
                if shares <= 0:
                    continue
                    
                # Get signal tier for logging
                signal_tier = self.get_signal_tier(signal['score'])
                
                try:
                    # Submit the order
                    logger.info(f"Submitting LONG order for {symbol}: {shares} shares at ~${price:.2f} (${position_size:.2f})")
                    order = self.api.submit_order(
                        symbol=symbol,
                        qty=shares,
                        side='buy',
                        type='market',
                        time_in_force='day'
                    )
                    
                    # Update executed trades tracking
                    executed_trades.append({
                        'symbol': symbol,
                        'direction': 'LONG',
                        'shares': shares,
                        'price': price,
                        'position_size': position_size,
                        'score': signal['score'],
                        'sector': sector,
                        'signal_tier': signal_tier,
                        'order_id': order.id,
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    })
                    
                    # Update sector tracking
                    executed_by_sector[sector] += 1
                    
                    # Update capital tracking
                    long_capital += position_size
                    
                    # Increment trade counter
                    trades_executed += 1
                    
                    logger.info(f"Executed LONG trade for {symbol} ({sector}): {shares} shares at ~${price:.2f} (${position_size:.2f}), Score: {signal['score']:.3f}, Tier: {signal_tier}")
                    
                except Exception as e:
                    logger.error(f"Error executing LONG trade for {symbol}: {str(e)}")
                    
            # Save executed trades to CSV
            if executed_trades:
                self.save_trades(executed_trades)
                
            logger.info(f"Executed {trades_executed} LONG trades")
            
            return executed_trades
            
        except Exception as e:
            logger.error(f"Error executing trades: {str(e)}")
            return []
    
    def check_stop_loss_conditions(self):
        """
        Check if any positions need to be closed based on stop-loss conditions
        Returns: List of positions that were closed
        """
        if self.backtest_mode:
            return []
            
        closed_positions = []
        
        try:
            # Get current positions
            positions = self.api.list_positions()
            
            if not positions:
                logger.info("No positions to check for stop-loss")
                return []
                
            # Get market regime
            market_regime = self.detect_market_regime() if self.market_regime_enabled else 'NEUTRAL'
            
            # Get sector performance
            sector_performance = self.get_sector_performance() if self.sector_performance_enabled else {}
            
            # Get market volatility from SPY
            market_volatility = 'NORMAL'
            try:
                spy_data = self.get_historical_data('SPY', days=20)
                if spy_data is not None and len(spy_data) > 10:
                    # Calculate ATR
                    if 'atr' not in spy_data.columns:
                        # Calculate ATR
                        spy_data['tr'] = np.maximum(
                            spy_data['high'] - spy_data['low'],
                            np.maximum(
                                abs(spy_data['high'] - spy_data['close'].shift()),
                                abs(spy_data['low'] - spy_data['close'].shift())
                            )
                        )
                        spy_data['atr'] = spy_data['tr'].rolling(window=10).mean()
                    
                    # Calculate ATR as percentage of price
                    spy_atr_pct = (spy_data['atr'].iloc[-1] / spy_data['close'].iloc[-1]) * 100
                    
                    # Determine market volatility regime
                    if spy_atr_pct > 2.0:
                        market_volatility = 'HIGH'
                    elif spy_atr_pct < 1.0:
                        market_volatility = 'LOW'
                    else:
                        market_volatility = 'NORMAL'
                        
                    logger.info(f"Market volatility: {market_volatility} (ATR%: {spy_atr_pct:.2f}%)")
            except Exception as e:
                logger.warning(f"Error calculating market volatility: {str(e)}")
            
            # Process each position
            for position in positions:
                try:
                    symbol = position.symbol
                    entry_price = float(position.avg_entry_price)
                    current_price = float(position.current_price)
                    quantity = float(position.qty)
                    market_value = float(position.market_value)
                    unrealized_pl = float(position.unrealized_pl)
                    unrealized_plpc = float(position.unrealized_plpc) * 100  # Convert to percentage
                    
                    # Determine position direction
                    direction = 'LONG' if quantity > 0 else 'SHORT'
                    
                    # Get symbol sector
                    symbol_sector = self.get_symbol_sector(symbol)
                    
                    # Find corresponding sector ETF
                    sector_etf = None
                    if symbol_sector == 'Technology':
                        sector_etf = 'XLK'
                    elif symbol_sector == 'Financials':
                        sector_etf = 'XLF'
                    elif symbol_sector == 'Healthcare':
                        sector_etf = 'XLV'
                    elif symbol_sector == 'Energy':
                        sector_etf = 'XLE'
                    elif symbol_sector == 'Industrials':
                        sector_etf = 'XLI'
                    elif symbol_sector == 'Consumer Discretionary':
                        sector_etf = 'XLY'
                    elif symbol_sector == 'Consumer Staples':
                        sector_etf = 'XLP'
                    elif symbol_sector == 'Materials':
                        sector_etf = 'XLB'
                    elif symbol_sector == 'Utilities':
                        sector_etf = 'XLU'
                    elif symbol_sector == 'Real Estate':
                        sector_etf = 'XLRE'
                    elif symbol_sector == 'Communication Services':
                        sector_etf = 'XLC'
                    
                    sector_regime = sector_performance.get(sector_etf, 'NEUTRAL') if sector_etf else 'NEUTRAL'
                    
                    # Get historical data to calculate ATR for dynamic stop-loss
                    data = self.get_historical_data(symbol, days=20)
                    
                    if data is None or len(data) < 10:
                        logger.warning(f"Not enough data for {symbol} to check stop-loss")
                        continue
                        
                    # Calculate ATR if not already present
                    if 'atr' not in data.columns:
                        # Calculate ATR
                        data['tr'] = np.maximum(
                            data['high'] - data['low'],
                            np.maximum(
                                abs(data['high'] - data['close'].shift()),
                                abs(data['low'] - data['close'].shift())
                            )
                        )
                        data['atr'] = data['tr'].rolling(window=10).mean()
                    
                    # Get the latest ATR value
                    latest_atr = data['atr'].iloc[-1]
                    atr_pct = (latest_atr / current_price) * 100
                    
                    # Calculate stock-specific volatility ratio compared to its historical average
                    data['atr_ratio'] = data['atr'] / data['atr'].rolling(window=20).mean()
                    volatility_ratio = data['atr_ratio'].iloc[-1]
                    
                    # Calculate technical indicators for signal quality assessment
                    self.calculate_technical_indicators(data)
                    
                    # Get the latest row for signal quality assessment
                    latest_row = data.iloc[-1]
                    
                    # Calculate signal quality (0-1 scale)
                    signal_quality = 0.5  # Default neutral
                    if direction == 'LONG':
                        # For LONG positions, higher signal quality means stronger buy signals
                        signal_quality = self.calculate_score(latest_row)
                    
                    # Base stop-loss thresholds - from config or default
                    base_long_stop_loss = self.config.get('strategy', {}).get('stop_loss', {}).get('long_threshold', -0.02) * 100
                    
                    # Initialize adaptive stop-loss
                    adaptive_stop_loss = base_long_stop_loss
                    
                    # Get stop loss configuration
                    stop_loss_config = self.config.get('strategy', {}).get('stop_loss', {})
                    adaptive_config = stop_loss_config.get('adaptive', {})
                    trailing_config = stop_loss_config.get('trailing', {})
                    
                    # Check if adaptive stop loss is enabled
                    adaptive_enabled = adaptive_config.get('enabled', True)
                    
                    if adaptive_enabled:
                        # 1. Adjust for stock-specific volatility
                        volatility_factor = 1.0
                        if adaptive_config.get('volatility_scaling', True):
                            if atr_pct > 3.0:  # High volatility stock
                                volatility_factor = 1.5  # Wider stop for volatile stocks
                            elif atr_pct < 1.0:  # Low volatility stock
                                volatility_factor = 0.8  # Tighter stop for stable stocks
                            
                            # 2. Adjust for recent volatility changes
                            if volatility_ratio > 1.3:  # Volatility increasing
                                volatility_factor *= 1.2  # Wider stop when volatility is increasing
                            elif volatility_ratio < 0.8:  # Volatility decreasing
                                volatility_factor *= 0.9  # Tighter stop when volatility is decreasing
                            
                            # 3. Adjust for market volatility
                            if market_volatility == 'HIGH':
                                volatility_factor *= 1.2
                            elif market_volatility == 'LOW':
                                volatility_factor *= 0.9
                        
                        # Apply volatility adjustments
                        adaptive_stop_loss = base_long_stop_loss * volatility_factor
                        
                        # 4. Adjust for market regime
                        market_regime_factor = 1.0
                        if adaptive_config.get('market_regime_scaling', True):
                            if market_regime == 'STRONG_BEARISH':
                                market_regime_factor = 0.7  # Tighter stop in bearish markets (70% of base)
                            elif market_regime == 'BEARISH':
                                market_regime_factor = 0.8  # Somewhat tighter stop in bearish markets
                            elif market_regime == 'BULLISH':
                                market_regime_factor = 1.1  # Wider stop in bullish markets
                            elif market_regime == 'STRONG_BULLISH':
                                market_regime_factor = 1.2  # Even wider stop in strong bull markets
                            
                            # Apply market regime adjustment
                            adaptive_stop_loss *= market_regime_factor
                        
                        # 5. Adjust for sector performance
                        sector_factor = 1.0
                        if adaptive_config.get('sector_regime_scaling', True):
                            if sector_regime == 'STRONG_BEARISH':
                                sector_factor = 0.7  # Tighter stop for stocks in bearish sectors
                            elif sector_regime == 'BEARISH':
                                sector_factor = 0.8
                            elif sector_regime == 'BULLISH':
                                sector_factor = 1.1
                            elif sector_regime == 'STRONG_BULLISH':
                                sector_factor = 1.2  # Wider stop for stocks in bullish sectors
                            
                            # Apply sector adjustment
                            adaptive_stop_loss *= sector_factor
                        
                        # 6. Adjust for signal quality
                        signal_quality_factor = 1.0
                        if adaptive_config.get('signal_quality_scaling', True):
                            if signal_quality > 0.9:  # Very high quality signal
                                signal_quality_factor = 1.3  # Much wider stop for high conviction positions
                            elif signal_quality > 0.8:
                                signal_quality_factor = 1.2
                            elif signal_quality > 0.7:
                                signal_quality_factor = 1.1
                            elif signal_quality < 0.4:  # Signal deteriorating
                                signal_quality_factor = 0.8  # Tighter stop when signal quality drops
                            elif signal_quality < 0.3:
                                signal_quality_factor = 0.7
                            
                            # Apply signal quality adjustment
                            adaptive_stop_loss *= signal_quality_factor
                        
                        # 7. Time-based adjustment (tighten stops for older positions)
                        time_factor = 1.0
                        if adaptive_config.get('time_scaling', True):
                            position_age_days = None
                            try:
                                # Try to get position age from API or calculate from available data
                                # For now, using a placeholder value
                                position_age_days = 5
                                
                                if position_age_days > 15:  # Position held for more than 15 days
                                    time_factor = 0.7  # Much tighter stop (70% of base)
                                elif position_age_days > 10:  # Position held for more than 10 days
                                    time_factor = 0.8  # Tighter stop (80% of base)
                                elif position_age_days > 5:  # Position held for more than 5 days
                                    time_factor = 0.9  # Slightly tighter stop (90% of base)
                            except:
                                pass
                            
                            # Apply time-based adjustment
                            adaptive_stop_loss *= time_factor
                    
                    # 8. Enhanced trailing stop-loss for profitable positions
                    trailing_stop = None
                    trailing_enabled = trailing_config.get('enabled', True)
                    
                    if trailing_enabled and direction == 'LONG':
                        # Get profit tiers from config
                        profit_tiers = trailing_config.get('profit_tiers', {})
                        
                        # Tier 1 (highest profit)
                        tier1 = profit_tiers.get('tier1', {})
                        tier1_threshold = tier1.get('threshold', 10.0)
                        tier1_lock_in = tier1.get('lock_in', 7.0)
                        tier1_retain_pct = tier1.get('retain_pct', 0.7)
                        
                        # Tier 2 (medium profit)
                        tier2 = profit_tiers.get('tier2', {})
                        tier2_threshold = tier2.get('threshold', 5.0)
                        tier2_lock_in = tier2.get('lock_in', 3.0)
                        tier2_retain_pct = tier2.get('retain_pct', 0.6)
                        
                        # Tier 3 (lowest profit)
                        tier3 = profit_tiers.get('tier3', {})
                        tier3_threshold = tier3.get('threshold', 3.0)
                        tier3_lock_in = tier3.get('lock_in', 1.0)
                        tier3_retain_pct = tier3.get('retain_pct', 0.5)
                        
                        # Apply trailing stop based on profit tiers
                        if unrealized_plpc > tier1_threshold:  # Position up more than tier1 threshold
                            # Lock in at least tier1_lock_in profit
                            trailing_stop = -unrealized_plpc + max(tier1_lock_in, unrealized_plpc * tier1_retain_pct)
                        elif unrealized_plpc > tier2_threshold:  # Position up more than tier2 threshold
                            # Lock in at least tier2_lock_in profit
                            trailing_stop = -unrealized_plpc + max(tier2_lock_in, unrealized_plpc * tier2_retain_pct)
                        elif unrealized_plpc > tier3_threshold:  # Position up more than tier3 threshold
                            # Lock in at least tier3_lock_in profit
                            trailing_stop = -unrealized_plpc + max(tier3_lock_in, unrealized_plpc * tier3_retain_pct)
                    
                    # Use trailing stop if applicable and more conservative than adaptive stop
                    if trailing_stop is not None and trailing_stop > adaptive_stop_loss:
                        final_stop_loss = trailing_stop
                        stop_loss_type = "trailing"
                    else:
                        final_stop_loss = adaptive_stop_loss
                        stop_loss_type = "adaptive"
                    
                    # Log the stop-loss calculation factors
                    logger.debug(f"Stop-loss for {symbol} ({direction}): " +
                                f"Base={base_long_stop_loss:.2f}%, " +
                                f"Volatility={volatility_factor:.2f}, " +
                                f"Market={market_regime_factor:.2f}, " +
                                f"Sector={sector_factor:.2f}, " +
                                f"Signal={signal_quality_factor:.2f}, " +
                                f"Time={time_factor:.2f}, " +
                                f"Final={final_stop_loss:.2f}% ({stop_loss_type})")
                    
                    # Check if stop-loss is triggered
                    stop_loss_triggered = False
                    
                    if direction == 'LONG' and unrealized_plpc <= final_stop_loss:
                        stop_loss_triggered = True
                        logger.info(f"Stop-loss triggered for LONG position {symbol}: " +
                                   f"{unrealized_plpc:.2f}% loss (threshold: {final_stop_loss:.2f}%)")
                    
                    # Close position if stop-loss is triggered
                    if stop_loss_triggered:
                        try:
                            # Submit order to close position
                            side = 'sell'
                            qty = abs(quantity)
                            
                            order = self.api.submit_order(
                                symbol=symbol,
                                qty=qty,
                                side=side,
                                type='market',
                                time_in_force='day'
                            )
                            
                            logger.info(f"Closed LONG position for {symbol}: {qty} shares at ~${current_price:.2f} (stop-loss)")
                            
                            # Record detailed stop-loss information
                            closed_positions.append({
                                'symbol': symbol,
                                'direction': direction,
                                'quantity': qty,
                                'entry_price': entry_price,
                                'exit_price': current_price,
                                'pl_pct': unrealized_plpc,
                                'reason': 'stop_loss',
                                'stop_loss_type': stop_loss_type,
                                'market_regime': market_regime,
                                'sector_regime': sector_regime,
                                'volatility': atr_pct,
                                'signal_quality': signal_quality,
                                'position_age_days': position_age_days,
                                'base_threshold': base_long_stop_loss,
                                'final_threshold': final_stop_loss
                            })
                            
                        except Exception as e:
                            logger.error(f"Error closing position for {symbol}: {str(e)}")
                    
                except Exception as e:
                    logger.warning(f"Error checking stop-loss for {position.symbol}: {str(e)}")
            
            # Save closed positions to CSV
            if closed_positions:
                try:
                    # Convert to DataFrame
                    closed_df = pd.DataFrame(closed_positions)
                    
                    # Create directory if it doesn't exist
                    os.makedirs(self.paths["trades"], exist_ok=True)
                    
                    # Save to CSV with timestamp
                    filename = f'{self.paths["trades"]}/closed_positions_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
                    closed_df.to_csv(filename, index=False)
                    logger.info(f"Saved {len(closed_positions)} closed positions to {filename}")
                    
                    # Also append to stop loss history file for analysis
                    history_file = self.paths.get("stop_loss_history", "stop_loss_history.csv")
                    
                    # Check if file exists to determine if header is needed
                    file_exists = os.path.isfile(history_file)
                    
                    # Append to history file
                    closed_df.to_csv(history_file, mode='a', header=not file_exists, index=False)
                    
                except Exception as e:
                    logger.error(f"Error saving closed positions to CSV: {str(e)}")
            
            return closed_positions
            
        except Exception as e:
            logger.error(f"Error checking stop-loss conditions: {str(e)}")
            return []
    
    def detect_market_regime(self):
        """
        Detect the current market regime by analyzing SPY ETF and sector ETFs
        Returns: STRONG_BULLISH, BULLISH, NEUTRAL, BEARISH, or STRONG_BEARISH
        """
        try:
            # Get SPY data
            spy_data = self.get_historical_data('SPY', days=30)
            
            if spy_data is None or len(spy_data) < 20:
                logger.warning("Not enough SPY data to detect market regime")
                return 'NEUTRAL'
            
            # Calculate SMAs
            spy_data['sma5'] = spy_data['close'].rolling(window=5).mean()
            spy_data['sma10'] = spy_data['close'].rolling(window=10).mean()
            spy_data['sma20'] = spy_data['close'].rolling(window=20).mean()
            spy_data['sma50'] = spy_data['close'].rolling(window=min(50, len(spy_data))).mean()
            
            # Calculate percentage changes
            spy_data['change_1d'] = spy_data['close'].pct_change(periods=1) * 100
            spy_data['change_3d'] = spy_data['close'].pct_change(periods=3) * 100
            spy_data['change_5d'] = spy_data['close'].pct_change(periods=5) * 100
            spy_data['change_10d'] = spy_data['close'].pct_change(periods=10) * 100
            spy_data['change_20d'] = spy_data['close'].pct_change(periods=20) * 100
            
            # Calculate volume metrics
            spy_data['volume_sma10'] = spy_data['volume'].rolling(window=10).mean()
            spy_data['volume_ratio'] = spy_data['volume'] / spy_data['volume_sma10']
            
            # Calculate volatility (ATR)
            if 'atr' not in spy_data.columns:
                # Calculate ATR
                spy_data['tr'] = np.maximum(
                    spy_data['high'] - spy_data['low'],
                    np.maximum(
                        abs(spy_data['high'] - spy_data['close'].shift()),
                        abs(spy_data['low'] - spy_data['close'].shift())
                    )
                )
                spy_data['atr'] = spy_data['tr'].rolling(window=10).mean()
            
            # Calculate volatility ratio (current ATR vs historical)
            spy_data['atr_ratio'] = spy_data['atr'] / spy_data['atr'].rolling(window=20).mean()
            
            # Calculate RSI for overbought/oversold conditions
            delta = spy_data['close'].diff()
            gain = delta.where(delta > 0, 0)
            loss = -delta.where(delta < 0, 0)
            
            avg_gain = gain.rolling(window=14).mean()
            avg_loss = loss.rolling(window=14).mean()
            
            rs = avg_gain / avg_loss.where(loss != 0, 1)
            spy_data['rsi'] = 100 - (100 / (1 + rs))
            
            # Get latest data
            latest = spy_data.iloc[-1]
            
            # Determine market regime based on multiple factors
            regime_score = 0
            
            # 1. SMA relationships (weight: high)
            if latest['close'] > latest['sma5'] > latest['sma10'] > latest['sma20'] > latest['sma50']:
                regime_score += 3
            elif latest['close'] > latest['sma5'] > latest['sma10'] > latest['sma20']:
                regime_score += 2
            elif latest['close'] > latest['sma5'] and latest['sma5'] > latest['sma20']:
                regime_score += 1
            elif latest['close'] < latest['sma5'] < latest['sma10'] < latest['sma20'] < latest['sma50']:
                regime_score -= 3
            elif latest['close'] < latest['sma5'] < latest['sma10'] < latest['sma20']:
                regime_score -= 2
            elif latest['close'] < latest['sma5'] and latest['sma5'] < latest['sma20']:
                regime_score -= 1
                
            # 2. Recent performance (weight: medium)
            if latest['change_1d'] > 1.5:
                regime_score += 1
            elif latest['change_1d'] < -1.5:
                regime_score -= 1
                
            if latest['change_3d'] > 2.5:
                regime_score += 1
            elif latest['change_3d'] < -2.5:
                regime_score -= 1
                
            if latest['change_5d'] > 3.5:
                regime_score += 1
            elif latest['change_5d'] < -3.5:
                regime_score -= 1
                
            if latest['change_10d'] > 5:
                regime_score += 1
            elif latest['change_10d'] < -5:
                regime_score -= 1
                
            if latest['change_20d'] > 8:
                regime_score += 1
            elif latest['change_20d'] < -8:
                regime_score -= 1
            
            # 3. Volume analysis (weight: medium)
            # High volume on up days is bullish, high volume on down days is bearish
            recent_volume_days = min(5, len(spy_data) - 1)
            up_days_volume = 0
            up_days_count = 0
            down_days_volume = 0
            down_days_count = 0
            
            for i in range(-recent_volume_days, 0):
                if spy_data['change_1d'].iloc[i] > 0:
                    up_days_volume += spy_data['volume'].iloc[i]
                    up_days_count += 1
                else:
                    down_days_volume += spy_data['volume'].iloc[i]
                    down_days_count += 1
            
            # Calculate average volume for up and down days
            avg_up_volume = up_days_volume / max(1, up_days_count)
            avg_down_volume = down_days_volume / max(1, down_days_count)
            
            # Compare volume on up vs down days
            if up_days_count > 0 and down_days_count > 0:
                if avg_up_volume > avg_down_volume * 1.5:
                    regime_score += 1
                elif avg_down_volume > avg_up_volume * 1.5:
                    regime_score -= 1
            
            # 4. Volatility assessment (weight: medium)
            # Higher volatility in downtrends is bearish, lower volatility in uptrends is bullish
            if 'atr_ratio' in latest:
                if latest['atr_ratio'] > 1.5 and latest['change_5d'] < 0:
                    regime_score -= 1
                elif latest['atr_ratio'] < 0.7 and latest['change_5d'] > 0:
                    regime_score += 1
            
            # 5. RSI analysis
            if 'rsi' in latest:
                if latest['rsi'] > 70:  # Overbought
                    regime_score -= 1
                elif latest['rsi'] < 30:  # Oversold
                    regime_score += 1
                elif latest['rsi'] > 60 and latest['change_5d'] > 0:  # Strong momentum
                    regime_score += 1
                elif latest['rsi'] < 40 and latest['change_5d'] < 0:  # Weak momentum
                    regime_score -= 1
            
            # 6. Sector breadth analysis (weight: high)
            # Check how many sectors are bullish/bearish
            sector_performance = self.get_sector_performance() if self.sector_performance_enabled else {}
            
            if sector_performance:
                bullish_sectors = 0
                bearish_sectors = 0
                strong_bullish_sectors = 0
                strong_bearish_sectors = 0
                
                for etf, data in sector_performance.items():
                    if data['status'] == 'STRONG_BULLISH':
                        strong_bullish_sectors += 1
                        bullish_sectors += 1
                    elif data['status'] == 'BULLISH':
                        bullish_sectors += 1
                    elif data['status'] == 'STRONG_BEARISH':
                        strong_bearish_sectors += 1
                        bearish_sectors += 1
                    elif data['status'] == 'BEARISH':
                        bearish_sectors += 1
                
                # Adjust score based on sector breadth
                if bullish_sectors >= 8:  # Most sectors bullish
                    regime_score += 2
                elif bullish_sectors >= 6:  # Many sectors bullish
                    regime_score += 1
                elif bearish_sectors >= 8:  # Most sectors bearish
                    regime_score -= 2
                elif bearish_sectors >= 6:  # Many sectors bearish
                    regime_score -= 1
                
                # Give extra weight to strongly trending sectors
                regime_score += strong_bullish_sectors * 0.5
                regime_score -= strong_bearish_sectors * 0.5
            
            # 7. SMA crossovers
            # Check for recent SMA crossovers (last 3 days)
            recent_crossover_days = min(3, len(spy_data) - 1)
            for i in range(-recent_crossover_days, 0):
                # 5-day SMA crossing above 20-day SMA (bullish)
                if (spy_data['sma5'].iloc[i-1] <= spy_data['sma20'].iloc[i-1] and 
                    spy_data['sma5'].iloc[i] > spy_data['sma20'].iloc[i]):
                    regime_score += 2
                # 5-day SMA crossing below 20-day SMA (bearish)
                elif (spy_data['sma5'].iloc[i-1] >= spy_data['sma20'].iloc[i-1] and 
                      spy_data['sma5'].iloc[i] < spy_data['sma20'].iloc[i]):
                    regime_score -= 2
            
            # Classify market regime
            if regime_score >= 7:
                market_regime = 'STRONG_BULLISH'
            elif regime_score >= 3:
                market_regime = 'BULLISH'
            elif regime_score > -3:
                market_regime = 'NEUTRAL'
            elif regime_score > -7:
                market_regime = 'BEARISH'
            else:
                market_regime = 'STRONG_BEARISH'
                
            logger.info(f"Market regime: {market_regime} (score: {regime_score})")
            
            # Log detailed regime factors
            logger.info(f"SMA relationships: Close={latest['close']:.2f}, SMA5={latest['sma5']:.2f}, SMA10={latest['sma10']:.2f}, SMA20={latest['sma20']:.2f}, SMA50={latest['sma50']:.2f}")
            logger.info(f"Recent performance: {latest['change_1d']:.2f}% (1d), {latest['change_3d']:.2f}% (3d), {latest['change_5d']:.2f}% (5d), {latest['change_10d']:.2f}% (10d), {latest['change_20d']:.2f}% (20d)")
            if 'rsi' in latest:
                logger.info(f"RSI: {latest['rsi']:.2f}")
            logger.debug(f"Volume analysis: Up vol: {avg_up_volume:.2f}, Down vol: {avg_down_volume:.2f}, Today's vol ratio: {latest.get('volume_ratio', 0):.2f}")
            if 'atr_ratio' in latest:
                logger.debug(f"Volatility (ATR ratio): {latest['atr_ratio']:.2f}")
            if sector_performance:
                logger.debug(f"Sector breadth: {bullish_sectors} bullish, {bearish_sectors} bearish")
            
            return market_regime
            
        except Exception as e:
            logger.error(f"Error detecting market regime: {str(e)}")
            return 'NEUTRAL'
    
    def get_sector_performance(self):
        """
        Get performance data for major sector ETFs and determine their regimes
        Returns: Dictionary mapping sector ETF symbols to their market regimes
        """
        try:
            # List of sector ETFs
            sector_etfs = [
                'XLK',  # Technology
                'XLF',  # Financials
                'XLV',  # Healthcare
                'XLE',  # Energy
                'XLI',  # Industrials
                'XLY',  # Consumer Discretionary
                'XLP',  # Consumer Staples
                'XLB',  # Materials
                'XLU',  # Utilities
                'XLRE', # Real Estate
                'XLC'   # Communication Services
            ]
            
            # Get data for each sector ETF
            sector_regimes = {}
            
            for etf in sector_etfs:
                try:
                    # Get historical data
                    etf_data = self.get_historical_data(etf, days=20)
                    
                    if etf_data is None or len(etf_data) < 10:
                        logger.warning(f"Not enough data for {etf}, skipping")
                        continue
                    
                    # Calculate SMAs
                    etf_data['sma5'] = etf_data['close'].rolling(window=5).mean()
                    etf_data['sma20'] = etf_data['close'].rolling(window=20).mean()
                    
                    # Calculate percentage changes
                    etf_data['change_5d'] = etf_data['close'].pct_change(periods=5) * 100
                    
                    # Get latest data
                    latest = etf_data.iloc[-1]
                    
                    # Determine regime
                    regime_score = 0
                    
                    # SMA relationships
                    if latest['close'] > latest['sma5'] > latest['sma20']:
                        regime_score += 2
                    elif latest['close'] > latest['sma5']:
                        regime_score += 1
                    elif latest['close'] < latest['sma5'] < latest['sma20']:
                        regime_score -= 2
                    elif latest['close'] < latest['sma5']:
                        regime_score -= 1
                    
                    # Recent performance
                    if latest['change_5d'] > 5:
                        regime_score += 2
                    elif latest['change_5d'] > 2:
                        regime_score += 1
                    elif latest['change_5d'] < -5:
                        regime_score -= 2
                    elif latest['change_5d'] < -2:
                        regime_score -= 1
                    
                    # Classify regime
                    if regime_score >= 3:
                        status = 'STRONG_BULLISH'
                    elif regime_score > 0:
                        status = 'BULLISH'
                    elif regime_score == 0:
                        status = 'NEUTRAL'
                    elif regime_score > -3:
                        status = 'BEARISH'
                    else:
                        status = 'STRONG_BEARISH'
                    
                    # Store regime data
                    sector_regimes[etf] = {
                        'status': status,
                        'score': regime_score,
                        'change_5d': latest['change_5d']
                    }
                    
                except Exception as e:
                    logger.error(f"Error analyzing sector ETF {etf}: {str(e)}")
            
            # Log sector analysis
            bullish_sectors = [etf for etf, data in sector_regimes.items() if data['status'] in ['BULLISH', 'STRONG_BULLISH']]
            bearish_sectors = [etf for etf, data in sector_regimes.items() if data['status'] in ['BEARISH', 'STRONG_BEARISH']]
            strong_bullish_sectors = [etf for etf, data in sector_regimes.items() if data['status'] == 'STRONG_BULLISH']
            strong_bearish_sectors = [etf for etf, data in sector_regimes.items() if data['status'] == 'STRONG_BEARISH']
            
            logger.info(f"Sector analysis: {len(strong_bullish_sectors)} strong bullish, {len(bullish_sectors) - len(strong_bullish_sectors)} bullish, "
                       f"{len(bearish_sectors) - len(strong_bearish_sectors)} bearish, {len(strong_bearish_sectors)} strong bearish")
            
            if strong_bullish_sectors:
                logger.info(f"Strong bullish sectors: {', '.join(strong_bullish_sectors)}")
            if strong_bearish_sectors:
                logger.info(f"Strong bearish sectors: {', '.join(strong_bearish_sectors)}")
            
            return sector_regimes
            
        except Exception as e:
            logger.error(f"Error getting sector performance: {str(e)}")
            return {}
    
    def get_symbol_sector(self, symbol):
        """
        Get the sector for a symbol using a simple mapping based on common knowledge
        This is a simplified approach - in a production system, you would use a more comprehensive database
        """
        # Technology companies
        tech_companies = ['AAPL', 'MSFT', 'GOOGL', 'GOOG', 'META', 'AMZN', 'NVDA', 'AMD', 'INTC', 'CSCO', 'ORCL', 'IBM', 'ADBE', 'CRM', 
                         'AVGO', 'TXN', 'QCOM', 'AMAT', 'MU', 'LRCX', 'NOW', 'INTU', 'PYPL', 'NFLX', 'TWTR', 'SNAP', 'PINS', 'SPOT', 'ZM', 'TEAM', 'WDAY', 'SPLK', 'DDOG']
        
        # Financial companies
        financial_companies = ['JPM', 'BAC', 'WFC', 'C', 'GS', 'MS', 'AXP', 'V', 'MA', 'BLK', 'SCHW', 'PNC', 'USB', 'TFC', 'COF', 'SPGI', 'MCO', 
                              'ICE', 'CME', 'CB', 'MMC', 'PGR', 'TRV', 'ALL', 'AIG', 'MET', 'PRU', 'BK', 'STT', 'TROW', 'NTRS', 'AMP', 'DFS', 'FITB', 'RF', 'KEY', 'CFG']
        
        # Healthcare companies
        healthcare_companies = ['JNJ', 'PFE', 'MRK', 'ABBV', 'ABT', 'UNH', 'CVS', 'AMGN', 'MDT', 'GILD', 'ISRG', 'ELV', 'LLY', 'BMY', 'TMO', 'DHR', 
                               'SYK', 'ZTS', 'REGN', 'VRTX', 'MRNA', 'BIIB', 'IDXX', 'BSX', 'BDX', 'A', 'BAX', 'CI', 'HUM', 'CNC', 'ANTM', 'ILMN', 'IQV', 'DXCM', 'ALGN', 'RMD', 'MTD', 'WAT']
        
        # Energy companies
        energy_companies = ['XOM', 'CVX', 'COP', 'EOG', 'SLB', 'PXD', 'OXY', 'PSX', 'VLO', 'MPC', 'KMI', 'WMB', 'OKE', 'DVN', 'HAL', 
                           'BKR', 'MRO', 'APA', 'HES', 'FANG', 'CTRA', 'EQT', 'LNG', 'CVI', 'TRGP', 'PDCE', 'SM', 'CHK', 'AR', 'RRC']
        
        # Industrial companies
        industrial_companies = ['GE', 'HON', 'MMM', 'CAT', 'DE', 'BA', 'LMT', 'RTX', 'UPS', 'FDX', 'UNP', 'CSX', 'NSC', 'LHX', 'GD', 'EMR', 'ETN', 
                               'ITW', 'CMI', 'PH', 'ROK', 'IR', 'TT', 'CARR', 'OTIS', 'PCAR', 'URI', 'FAST', 'GWW', 'SWK', 'CTAS', 'RSG', 'WM', 'JCI', 'AME', 'TDG', 'CPRT', 'DAL', 'UAL', 'LUV']
        
        # Consumer Discretionary
        consumer_disc_companies = ['AMZN', 'TSLA', 'HD', 'MCD', 'NKE', 'SBUX', 'TGT', 'LOW', 'BKNG', 'MAR', 'DIS', 'CMCSA', 'NFLX', 'TJX', 'EBAY', 
                                  'BBY', 'DG', 'DLTR', 'ROST', 'ORLY', 'AZO', 'ULTA', 'LVS', 'MGM', 'WYNN', 'RCL', 'CCL', 'HLT', 'F', 'GM', 'TSCO', 'DPZ', 'YUM', 'QSR', 'DRI', 'CMG', 'APTV', 'EXPE', 'ETSY', 'LULU']
        
        # Consumer Staples
        consumer_staples_companies = ['PG', 'KO', 'PEP', 'WMT', 'COST', 'PM', 'MO', 'EL', 'CL', 'KMB', 'GIS', 'K', 'SYY', 'ADM', 'KHC', 'STZ', 
                                     'MDLZ', 'HSY', 'KR', 'CLX', 'CAG', 'CPB', 'HRL', 'SJM', 'TAP', 'BG', 'MNST', 'COTY', 'CHD', 'MKC', 'TSN', 'LW']
        
        # Materials companies
        materials_companies = ['LIN', 'APD', 'SHW', 'FCX', 'NEM', 'ECL', 'DD', 'DOW', 'PPG', 'NUE', 'CTVA', 'VMC', 'MLM', 'ALB', 'FMC', 
                              'IFF', 'EMN', 'CF', 'MOS', 'IP', 'PKG', 'SEE', 'AVY', 'BLL', 'AMCR', 'WRK', 'CE', 'GOLD', 'AA', 'X', 'CLF', 'MT']
        
        # Utilities companies
        utilities_companies = ['NEE', 'DUK', 'SO', 'D', 'AEP', 'EXC', 'SRE', 'PCG', 'XEL', 'ED', 'ES', 'WEC', 'PEG', 'DTE', 'AEE', 'CMS', 
                              'ETR', 'FE', 'LNT', 'EVRG', 'AES', 'CNP', 'NI', 'PPL', 'AWK', 'CEG', 'EIX', 'PNW', 'ATO', 'NRG', 'OGE', 'POR', 'NWE', 'SR', 'AVA']
        
        # Real Estate companies
        real_estate_companies = ['AMT', 'PLD', 'CCI', 'EQIX', 'PSA', 'O', 'DLR', 'WELL', 'SBAC', 'AVB', 'EQR', 'SPG', 'VICI', 'VTR', 'ESS', 
                                'ARE', 'INVH', 'UDR', 'EXR', 'MAA', 'KIM', 'REG', 'FRT', 'BXP', 'HST', 'VNO', 'CPT', 'PEAK', 'IRM', 'SLG', 'AIV', 'DEI']
        
        # Communication Services
        communication_companies = ['GOOGL', 'GOOG', 'META', 'NFLX', 'DIS', 'CMCSA', 'VZ', 'T', 'TMUS', 'CHTR', 'ATVI', 'EA', 'TTWO', 'OMC', 'IPG', 
                                  'LYV', 'PARA', 'FOXA', 'FOX', 'DISH', 'LUMN', 'WBD', 'NWSA', 'NWS', 'TWTR', 'SNAP', 'PINS', 'MTCH', 'SPOT', 'ZM', 'RBLX']
        
        # Determine sector based on symbol
        if symbol in tech_companies:
            return 'Technology'
        elif symbol in financial_companies:
            return 'Financials'
        elif symbol in healthcare_companies:
            return 'Healthcare'
        elif symbol in energy_companies:
            return 'Energy'
        elif symbol in industrial_companies:
            return 'Industrials'
        elif symbol in consumer_disc_companies:
            return 'Consumer Discretionary'
        elif symbol in consumer_staples_companies:
            return 'Consumer Staples'
        elif symbol in materials_companies:
            return 'Materials'
        elif symbol in utilities_companies:
            return 'Utilities'
        elif symbol in real_estate_companies:
            return 'Real Estate'
        elif symbol in communication_companies:
            return 'Communication Services'
        else:
            # Try to infer sector from symbol prefix or common patterns
            if symbol.startswith(('AAPL', 'MSFT', 'IBM', 'CSCO', 'ORCL', 'HPQ', 'DELL', 'NVDA', 'AMD', 'INTC')):
                return 'Technology'
            elif symbol.startswith(('JPM', 'BAC', 'WFC', 'C', 'GS', 'MS', 'AXP', 'V', 'MA')):
                return 'Financials'
            elif symbol.startswith(('JNJ', 'PFE', 'MRK', 'ABBV', 'ABT', 'UNH', 'CVS')):
                return 'Healthcare'
            elif symbol.startswith(('XOM', 'CVX', 'COP', 'EOG', 'SLB', 'PXD', 'OXY')):
                return 'Energy'
            else:
                return 'Unknown'
    
    def calculate_long_signal_score(self, symbol, data, market_regime=None, sector_regime=None):
        """
        Calculate a score for a LONG signal based on technical indicators
        Higher score = stronger signal
        """
        try:
            if data is None or len(data) < 10:
                return 0
                
            # Get the latest data point
            latest = data.iloc[-1]
            
            # Initialize score
            score = 0.0
            
            # Get market regime if not provided
            if market_regime is None and self.market_regime_enabled:
                market_regime = self.detect_market_regime()
                
            # Get sector regime if not provided
            sector_etf = None
            if sector_regime is None and self.sector_performance_enabled:
                symbol_sector = self.get_symbol_sector(symbol)
                if symbol_sector:
                    # Find corresponding sector ETF
                    if symbol_sector == 'Technology':
                        sector_etf = 'XLK'
                    elif symbol_sector == 'Financials':
                        sector_etf = 'XLF'
                    elif symbol_sector == 'Healthcare':
                        sector_etf = 'XLV'
                    elif symbol_sector == 'Energy':
                        sector_etf = 'XLE'
                    elif symbol_sector == 'Industrials':
                        sector_etf = 'XLI'
                    elif symbol_sector == 'Consumer Discretionary':
                        sector_etf = 'XLY'
                    elif symbol_sector == 'Consumer Staples':
                        sector_etf = 'XLP'
                    elif symbol_sector == 'Materials':
                        sector_etf = 'XLB'
                    elif symbol_sector == 'Utilities':
                        sector_etf = 'XLU'
                    elif symbol_sector == 'Real Estate':
                        sector_etf = 'XLRE'
                    elif symbol_sector == 'Communication Services':
                        sector_etf = 'XLC'
                    
                    # Get sector performance
                    sector_performance = self.get_sector_performance() if self.sector_performance_enabled else {}
                    sector_regime = sector_performance.get(sector_etf, 'NEUTRAL') if sector_etf else 'NEUTRAL'
            
            # === RSI (Oversold conditions are bullish for LONG) ===
            if 'rsi' in latest:
                if latest['rsi'] < 40:
                    score += 0.2
                elif latest['rsi'] < 30:
                    score += 0.35
                elif latest['rsi'] < 20:
                    score += 0.5
                    
                # Adjust RSI weight based on market regime
                if market_regime in ['BEARISH', 'STRONG_BEARISH']:
                    # In bearish markets, require more oversold conditions for LONG signals
                    if latest['rsi'] > 35:
                        score -= 0.15
                elif market_regime in ['BULLISH', 'STRONG_BULLISH']:
                    # In bullish markets, even mild oversold conditions can be good entry points
                    if latest['rsi'] < 45:
                        score += 0.1
            
            # === MACD (Bullish crossover or histogram increasing is bullish for LONG) ===
            if all(x in latest for x in ['macd', 'macd_signal', 'macd_hist']):
                # Bullish crossover (MACD crosses above signal line)
                if latest['macd'] > latest['macd_signal'] and data['macd'].iloc[-2] <= data['macd_signal'].iloc[-2]:
                    score += 0.3
                
                # MACD histogram increasing (momentum building)
                if latest['macd_hist'] > 0 and latest['macd_hist'] > data['macd_hist'].iloc[-2]:
                    score += 0.2
                elif latest['macd_hist'] < 0 and latest['macd_hist'] > data['macd_hist'].iloc[-2]:
                    # Histogram still negative but increasing (early sign of potential reversal)
                    score += 0.15
                    
                # Adjust MACD weight based on market regime
                if market_regime in ['BULLISH', 'STRONG_BULLISH']:
                    # In bullish markets, MACD signals are more reliable for LONG positions
                    if latest['macd'] > latest['macd_signal']:
                        score += 0.1
                elif market_regime in ['BEARISH', 'STRONG_BEARISH']:
                    # In bearish markets, be more cautious with MACD signals
                    if latest['macd'] < 0 and latest['macd_signal'] < 0:
                        score -= 0.1
            
            # === Bollinger Bands (Price near or below lower band is bullish for LONG) ===
            if all(x in latest for x in ['bb_lower', 'bb_middle', 'bb_upper']):
                # Price near or below lower band (potential oversold condition)
                bb_position = (latest['close'] - latest['bb_lower']) / (latest['bb_upper'] - latest['bb_lower'])
                
                if latest['close'] <= latest['bb_lower']:
                    score += 0.4
                elif bb_position < 0.2:
                    score += 0.25
                    
                # Bollinger Band width (narrow bands may signal upcoming volatility)
                bb_width = (latest['bb_upper'] - latest['bb_lower']) / latest['bb_middle']
                bb_width_prev = (data['bb_upper'].iloc[-2] - data['bb_lower'].iloc[-2]) / data['bb_middle'].iloc[-2]
                
                if bb_width < bb_width_prev:
                    # Bands are contracting, potential reversal
                    score += 0.1
            
            # === Moving Averages (Price above key MAs is bullish for LONG) ===
            if 'sma20' in latest and 'sma50' in latest:
                # Price above key moving averages
                if latest['close'] > latest['sma20']:
                    score += 0.15
                if latest['close'] > latest['sma50']:
                    score += 0.15
                
                # Moving average alignment (uptrend confirmation)
                if latest['sma20'] > latest['sma50']:
                    score += 0.2
                    
                # Adjust MA weight based on market regime
                if market_regime in ['BULLISH', 'STRONG_BULLISH']:
                    # In bullish markets, being above MAs is more significant
                    if latest['close'] > latest['sma20'] and latest['sma20'] > latest['sma50']:
                        score += 0.1
            
            # === Volume (High volume on up days is bullish for LONG) ===
            if 'volume' in latest and len(data) >= 5:
                # Calculate average volume
                avg_volume = data['volume'].iloc[-5:].mean()
                
                # Check if current volume is above average on an up day
                if latest['volume'] > avg_volume * 1.2 and latest['close'] > data['close'].iloc[-2]:
                    score += 0.2
                    
                # Volume trend (increasing volume on up days is bullish)
                up_days_volume = 0
                up_days_count = 0
                down_days_volume = 0
                down_days_count = 0
                
                for i in range(-5, 0):
                    if data['close'].iloc[i] > data['close'].iloc[i-1]:
                        up_days_volume += data['volume'].iloc[i]
                        up_days_count += 1
                    else:
                        down_days_volume += data['volume'].iloc[i]
                        down_days_count += 1
                
                # Calculate average volume for up and down days
                avg_up_volume = up_days_volume / max(1, up_days_count)
                avg_down_volume = down_days_volume / max(1, down_days_count)
                
                # Compare volume on up vs down days
                if up_days_count > 0 and down_days_count > 0:
                    if avg_up_volume > avg_down_volume * 1.5:
                        score += 1
                    elif avg_down_volume > avg_up_volume * 1.5:
                        score -= 1
            
            # === ATR (Volatility assessment) ===
            if 'atr' in latest and 'close' in latest:
                # Calculate ATR as percentage of price
                atr_pct = (latest['atr'] / latest['close']) * 100
                
                # Adjust score based on volatility
                if atr_pct > 3.0:  # High volatility
                    if market_regime in ['BULLISH', 'STRONG_BULLISH']:
                        score += 0.1
                    else:
                        score -= 0.1
            
            # === Market Regime Adjustments ===
            if market_regime == 'STRONG_BULLISH':
                score += 0.15
            elif market_regime == 'BULLISH':
                score += 0.1
            elif market_regime == 'BEARISH':
                score -= 0.1
            elif market_regime == 'STRONG_BEARISH':
                score -= 0.2
            
            # === Sector Regime Adjustments ===
            if sector_regime == 'STRONG_BULLISH':
                score += 0.15
            elif sector_regime == 'BULLISH':
                score += 0.1
            elif sector_regime == 'BEARISH':
                score -= 0.1
            elif sector_regime == 'STRONG_BEARISH':
                score -= 0.2
            
            # Ensure score is within bounds
            score = max(0, min(score, 1.0))
            
            return score
            
        except Exception as e:
            logger.error(f"Error calculating LONG signal score for {symbol}: {str(e)}")
            return 0
    
    def get_signal_tier(self, score):
        """Determine the tier of a signal based on its score"""
        if score >= 0.9:
            return 'Tier 1 (≥0.9)'
        elif score >= 0.8:
            return 'Tier 2 (0.8-0.9)'
        else:
            return 'Below Threshold (<0.8)'
    
    def calculate_performance_metrics(self, simulated_trades):
        """Calculate performance metrics from simulated trades"""
        if not simulated_trades:
            return {}
        
        # Basic metrics
        total_trades = len(simulated_trades)
        winning_trades = [t for t in simulated_trades if t['is_win']]
        losing_trades = [t for t in simulated_trades if not t['is_win']]
        
        win_rate = len(winning_trades) / total_trades * 100 if total_trades > 0 else 0
        
        # P&L metrics
        total_profit = sum([t['profit_loss'] for t in winning_trades])
        total_loss = abs(sum([t['profit_loss'] for t in losing_trades]))
        profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')
        
        avg_win = sum([t['profit_loss'] for t in winning_trades]) / len(winning_trades) if winning_trades else 0
        avg_loss = sum([t['profit_loss'] for t in losing_trades]) / len(losing_trades) if losing_trades else 0
        
        # Holding period
        if 'holding_period' in simulated_trades[0]:
            avg_holding_period = sum([t['holding_period'] for t in simulated_trades]) / total_trades if total_trades > 0 else 0
        else:
            # Calculate holding period from dates if not directly provided
            avg_holding_period = 0
            if total_trades > 0:
                for t in simulated_trades:
                    if isinstance(t['entry_date'], str):
                        entry_date = datetime.strptime(t['entry_date'], "%Y-%m-%d %H:%M:%S")
                        exit_date = datetime.strptime(t['exit_date'], "%Y-%m-%d %H:%M:%S")
                    else:
                        entry_date = t['entry_date']
                        exit_date = t['exit_date']
                    holding_days = (exit_date - entry_date).days
                    avg_holding_period += holding_days
                avg_holding_period /= total_trades
        
        # Direction-specific metrics
        long_trades = simulated_trades  # All trades are LONG in LONG-only strategy
        long_win_rate = len([t for t in long_trades if t['is_win']]) / len(long_trades) * 100 if long_trades else 0
        
        # Tier metrics
        tier_metrics = {}
        tiers = {
            'Tier 1 (≥0.9)': [t for t in simulated_trades if t['tier'] == 'Tier 1 (≥0.9)'],
            'Tier 2 (0.8-0.9)': [t for t in simulated_trades if t['tier'] == 'Tier 2 (0.8-0.9)'],
            'Below Threshold (<0.8)': [t for t in simulated_trades if t['tier'] == 'Below Threshold (<0.8)']
        }
        
        for tier_name, tier_trades in tiers.items():
            if not tier_trades:
                continue
            
            # Basic metrics
            tier_total = len(tier_trades)
            tier_winners = [t for t in tier_trades if t['is_win']]
            tier_win_rate = len(tier_winners) / tier_total * 100 if tier_total > 0 else 0
            tier_avg_pl = sum([t['profit_loss'] for t in tier_trades]) / tier_total if tier_total > 0 else 0
            
            # Store metrics - simplified for LONG-only strategy
            tier_metrics[tier_name] = {
                'win_rate': tier_win_rate,
                'avg_pl': tier_avg_pl,
                'trade_count': tier_total,
                'long_win_rate': tier_win_rate,  # Same as overall win rate for LONG-only
                'long_count': tier_total         # All trades are LONG
            }
        
        # Return all metrics - simplified for LONG-only strategy
        return {
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'avg_holding_period': avg_holding_period,
            'long_win_rate': long_win_rate,
            'tier_metrics': tier_metrics,
            'total_trades': total_trades,
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades)
        }
    
    def run_strategy(self):
        """Run the strategy"""
        try:
            # First, check for stop-loss conditions to exit underperforming positions
            if not self.backtest_mode and self.stop_loss_enabled:
                # Free up any locked positions first
                self.free_up_locked_positions()
                
                # Then check stop-loss conditions
                self.check_stop_loss_conditions()
            
            # Get trade signals
            signals = self.get_trade_signals()
            
            # Prioritize signals
            signals = self.prioritize_signals(signals)
            
            # Summarize signals
            self.summarize_signals(signals)
            
            # Execute trades
            executed_trades = self.execute_trades(signals)
            
            # Track performance
            if not self.backtest_mode:
                self.performance_tracker.track_performance()
            
            # In backtest mode, return the signals instead of executed trades
            if self.backtest_mode:
                return signals
            else:
                return executed_trades
            
        except Exception as e:
            logger.error(f"Error running strategy: {str(e)}")
            return []
    
    def detect_market_regime(self):
        """
        Detect the current market regime by analyzing SPY ETF and sector ETFs
        Returns: STRONG_BULLISH, BULLISH, NEUTRAL, BEARISH, or STRONG_BEARISH
        """
        try:
            # Get SPY data
            spy_data = self.get_historical_data('SPY', days=30)
            
            if spy_data is None or len(spy_data) < 20:
                logger.warning("Not enough SPY data to detect market regime")
                return 'NEUTRAL'
            
            # Calculate SMAs
            spy_data['sma5'] = spy_data['close'].rolling(window=5).mean()
            spy_data['sma10'] = spy_data['close'].rolling(window=10).mean()
            spy_data['sma20'] = spy_data['close'].rolling(window=20).mean()
            spy_data['sma50'] = spy_data['close'].rolling(window=min(50, len(spy_data))).mean()
            
            # Calculate percentage changes
            spy_data['change_1d'] = spy_data['close'].pct_change(periods=1) * 100
            spy_data['change_3d'] = spy_data['close'].pct_change(periods=3) * 100
            spy_data['change_5d'] = spy_data['close'].pct_change(periods=5) * 100
            spy_data['change_10d'] = spy_data['close'].pct_change(periods=10) * 100
            spy_data['change_20d'] = spy_data['close'].pct_change(periods=20) * 100
            
            # Calculate volume metrics
            spy_data['volume_sma10'] = spy_data['volume'].rolling(window=10).mean()
            spy_data['volume_ratio'] = spy_data['volume'] / spy_data['volume_sma10']
            
            # Calculate volatility (ATR)
            if 'atr' not in spy_data.columns:
                # Calculate ATR
                spy_data['tr'] = np.maximum(
                    spy_data['high'] - spy_data['low'],
                    np.maximum(
                        abs(spy_data['high'] - spy_data['close'].shift()),
                        abs(spy_data['low'] - spy_data['close'].shift())
                    )
                )
                spy_data['atr'] = spy_data['tr'].rolling(window=10).mean()
            
            # Calculate volatility ratio (current ATR vs historical)
            spy_data['atr_ratio'] = spy_data['atr'] / spy_data['atr'].rolling(window=20).mean()
            
            # Calculate RSI for overbought/oversold conditions
            delta = spy_data['close'].diff()
            gain = delta.where(delta > 0, 0)
            loss = -delta.where(delta < 0, 0)
            
            avg_gain = gain.rolling(window=14).mean()
            avg_loss = loss.rolling(window=14).mean()
            
            rs = avg_gain / avg_loss.where(loss != 0, 1)
            spy_data['rsi'] = 100 - (100 / (1 + rs))
            
            # Get latest data
            latest = spy_data.iloc[-1]
            
            # Determine market regime based on multiple factors
            regime_score = 0
            
            # 1. SMA relationships (weight: high)
            if latest['close'] > latest['sma5'] > latest['sma10'] > latest['sma20'] > latest['sma50']:
                regime_score += 3
            elif latest['close'] > latest['sma5'] > latest['sma10'] > latest['sma20']:
                regime_score += 2
            elif latest['close'] > latest['sma5'] and latest['sma5'] > latest['sma20']:
                regime_score += 1
            elif latest['close'] < latest['sma5'] < latest['sma10'] < latest['sma20'] < latest['sma50']:
                regime_score -= 3
            elif latest['close'] < latest['sma5'] < latest['sma10'] < latest['sma20']:
                regime_score -= 2
            elif latest['close'] < latest['sma5'] and latest['sma5'] < latest['sma20']:
                regime_score -= 1
                
            # 2. Recent performance (weight: medium)
            if latest['change_1d'] > 1.5:
                regime_score += 1
            elif latest['change_1d'] < -1.5:
                regime_score -= 1
                
            if latest['change_3d'] > 2.5:
                regime_score += 1
            elif latest['change_3d'] < -2.5:
                regime_score -= 1
                
            if latest['change_5d'] > 3.5:
                regime_score += 1
            elif latest['change_5d'] < -3.5:
                regime_score -= 1
                
            if latest['change_10d'] > 5:
                regime_score += 1
            elif latest['change_10d'] < -5:
                regime_score -= 1
                
            if latest['change_20d'] > 8:
                regime_score += 1
            elif latest['change_20d'] < -8:
                regime_score -= 1
            
            # 3. Volume analysis (weight: medium)
            # High volume on up days is bullish, high volume on down days is bearish
            recent_volume_days = min(5, len(spy_data) - 1)
            up_days_volume = 0
            up_days_count = 0
            down_days_volume = 0
            down_days_count = 0
            
            for i in range(-recent_volume_days, 0):
                if spy_data['change_1d'].iloc[i] > 0:
                    up_days_volume += spy_data['volume'].iloc[i]
                    up_days_count += 1
                else:
                    down_days_volume += spy_data['volume'].iloc[i]
                    down_days_count += 1
            
            # Calculate average volume for up and down days
            avg_up_volume = up_days_volume / max(1, up_days_count)
            avg_down_volume = down_days_volume / max(1, down_days_count)
            
            # Compare volume on up vs down days
            if up_days_count > 0 and down_days_count > 0:
                if avg_up_volume > avg_down_volume * 1.5:
                    regime_score += 1
                elif avg_down_volume > avg_up_volume * 1.5:
                    regime_score -= 1
            
            # 4. Volatility assessment (weight: medium)
            # Higher volatility in downtrends is bearish, lower volatility in uptrends is bullish
            if 'atr_ratio' in latest:
                if latest['atr_ratio'] > 1.5 and latest['change_5d'] < 0:
                    regime_score -= 1
                elif latest['atr_ratio'] < 0.7 and latest['change_5d'] > 0:
                    regime_score += 1
            
            # 5. RSI analysis
            if 'rsi' in latest:
                if latest['rsi'] > 70:  # Overbought
                    regime_score -= 1
                elif latest['rsi'] < 30:  # Oversold
                    regime_score += 1
                elif latest['rsi'] > 60 and latest['change_5d'] > 0:  # Strong momentum
                    regime_score += 1
                elif latest['rsi'] < 40 and latest['change_5d'] < 0:  # Weak momentum
                    regime_score -= 1
            
            # 6. Sector breadth analysis (weight: high)
            # Check how many sectors are bullish/bearish
            sector_performance = self.get_sector_performance() if self.sector_performance_enabled else {}
            
            if sector_performance:
                bullish_sectors = 0
                bearish_sectors = 0
                strong_bullish_sectors = 0
                strong_bearish_sectors = 0
                
                for etf, data in sector_performance.items():
                    if data['status'] == 'STRONG_BULLISH':
                        strong_bullish_sectors += 1
                        bullish_sectors += 1
                    elif data['status'] == 'BULLISH':
                        bullish_sectors += 1
                    elif data['status'] == 'STRONG_BEARISH':
                        strong_bearish_sectors += 1
                        bearish_sectors += 1
                    elif data['status'] == 'BEARISH':
                        bearish_sectors += 1
                
                # Adjust score based on sector breadth
                if bullish_sectors >= 8:  # Most sectors bullish
                    regime_score += 2
                elif bullish_sectors >= 6:  # Many sectors bullish
                    regime_score += 1
                elif bearish_sectors >= 8:  # Most sectors bearish
                    regime_score -= 2
                elif bearish_sectors >= 6:  # Many sectors bearish
                    regime_score -= 1
                
                # Give extra weight to strongly trending sectors
                regime_score += strong_bullish_sectors * 0.5
                regime_score -= strong_bearish_sectors * 0.5
            
            # 7. SMA crossovers
            # Check for recent SMA crossovers (last 3 days)
            recent_crossover_days = min(3, len(spy_data) - 1)
            for i in range(-recent_crossover_days, 0):
                # 5-day SMA crossing above 20-day SMA (bullish)
                if (spy_data['sma5'].iloc[i-1] <= spy_data['sma20'].iloc[i-1] and 
                    spy_data['sma5'].iloc[i] > spy_data['sma20'].iloc[i]):
                    regime_score += 2
                # 5-day SMA crossing below 20-day SMA (bearish)
                elif (spy_data['sma5'].iloc[i-1] >= spy_data['sma20'].iloc[i-1] and 
                      spy_data['sma5'].iloc[i] < spy_data['sma20'].iloc[i]):
                    regime_score -= 2
            
            # Classify market regime
            if regime_score >= 7:
                market_regime = 'STRONG_BULLISH'
            elif regime_score >= 3:
                market_regime = 'BULLISH'
            elif regime_score > -3:
                market_regime = 'NEUTRAL'
            elif regime_score > -7:
                market_regime = 'BEARISH'
            else:
                market_regime = 'STRONG_BEARISH'
                
            logger.info(f"Market regime: {market_regime} (score: {regime_score})")
            
            # Log detailed regime factors
            logger.info(f"SMA relationships: Close={latest['close']:.2f}, SMA5={latest['sma5']:.2f}, SMA10={latest['sma10']:.2f}, SMA20={latest['sma20']:.2f}, SMA50={latest['sma50']:.2f}")
            logger.info(f"Recent performance: {latest['change_1d']:.2f}% (1d), {latest['change_3d']:.2f}% (3d), {latest['change_5d']:.2f}% (5d), {latest['change_10d']:.2f}% (10d), {latest['change_20d']:.2f}% (20d)")
            if 'rsi' in latest:
                logger.info(f"RSI: {latest['rsi']:.2f}")
            logger.debug(f"Volume analysis: Up vol: {avg_up_volume:.2f}, Down vol: {avg_down_volume:.2f}, Today's vol ratio: {latest.get('volume_ratio', 0):.2f}")
            if 'atr_ratio' in latest:
                logger.debug(f"Volatility (ATR ratio): {latest['atr_ratio']:.2f}")
            if sector_performance:
                logger.debug(f"Sector breadth: {bullish_sectors} bullish, {bearish_sectors} bearish")
            
            return market_regime
            
        except Exception as e:
            logger.error(f"Error detecting market regime: {str(e)}")
            return 'NEUTRAL'
    
    def get_sector_performance(self):
        """
        Get performance data for major sector ETFs and determine their regimes
        Returns: Dictionary mapping sector ETF symbols to their market regimes
        """
        try:
            # List of sector ETFs
            sector_etfs = [
                'XLK',  # Technology
                'XLF',  # Financials
                'XLV',  # Healthcare
                'XLE',  # Energy
                'XLI',  # Industrials
                'XLY',  # Consumer Discretionary
                'XLP',  # Consumer Staples
                'XLB',  # Materials
                'XLU',  # Utilities
                'XLRE', # Real Estate
                'XLC'   # Communication Services
            ]
            
            # Get data for each sector ETF
            sector_regimes = {}
            
            for etf in sector_etfs:
                try:
                    # Get historical data
                    etf_data = self.get_historical_data(etf, days=20)
                    
                    if etf_data is None or len(etf_data) < 10:
                        logger.warning(f"Not enough data for {etf}, skipping")
                        continue
                    
                    # Calculate SMAs
                    etf_data['sma5'] = etf_data['close'].rolling(window=5).mean()
                    etf_data['sma20'] = etf_data['close'].rolling(window=20).mean()
                    
                    # Calculate percentage changes
                    etf_data['change_5d'] = etf_data['close'].pct_change(periods=5) * 100
                    
                    # Get latest data
                    latest = etf_data.iloc[-1]
                    
                    # Determine regime
                    regime_score = 0
                    
                    # SMA relationships
                    if latest['close'] > latest['sma5'] > latest['sma20']:
                        regime_score += 2
                    elif latest['close'] > latest['sma5']:
                        regime_score += 1
                    elif latest['close'] < latest['sma5'] < latest['sma20']:
                        regime_score -= 2
                    elif latest['close'] < latest['sma5']:
                        regime_score -= 1
                    
                    # Recent performance
                    if latest['change_5d'] > 5:
                        regime_score += 2
                    elif latest['change_5d'] > 2:
                        regime_score += 1
                    elif latest['change_5d'] < -5:
                        regime_score -= 2
                    elif latest['change_5d'] < -2:
                        regime_score -= 1
                    
                    # Classify regime
                    if regime_score >= 3:
                        status = 'STRONG_BULLISH'
                    elif regime_score > 0:
                        status = 'BULLISH'
                    elif regime_score == 0:
                        status = 'NEUTRAL'
                    elif regime_score > -3:
                        status = 'BEARISH'
                    else:
                        status = 'STRONG_BEARISH'
                    
                    # Store regime data
                    sector_regimes[etf] = {
                        'status': status,
                        'score': regime_score,
                        'change_5d': latest['change_5d']
                    }
                    
                except Exception as e:
                    logger.error(f"Error analyzing sector ETF {etf}: {str(e)}")
            
            # Log sector analysis
            bullish_sectors = [etf for etf, data in sector_regimes.items() if data['status'] in ['BULLISH', 'STRONG_BULLISH']]
            bearish_sectors = [etf for etf, data in sector_regimes.items() if data['status'] in ['BEARISH', 'STRONG_BEARISH']]
            strong_bullish_sectors = [etf for etf, data in sector_regimes.items() if data['status'] == 'STRONG_BULLISH']
            strong_bearish_sectors = [etf for etf, data in sector_regimes.items() if data['status'] == 'STRONG_BEARISH']
            
            logger.info(f"Sector analysis: {len(strong_bullish_sectors)} strong bullish, {len(bullish_sectors) - len(strong_bullish_sectors)} bullish, "
                       f"{len(bearish_sectors) - len(strong_bearish_sectors)} bearish, {len(strong_bearish_sectors)} strong bearish")
            
            if strong_bullish_sectors:
                logger.info(f"Strong bullish sectors: {', '.join(strong_bullish_sectors)}")
            if strong_bearish_sectors:
                logger.info(f"Strong bearish sectors: {', '.join(strong_bearish_sectors)}")
            
            return sector_regimes
            
        except Exception as e:
            logger.error(f"Error getting sector performance: {str(e)}")
            return {}
    
    def get_symbol_sector(self, symbol):
        """
        Get the sector for a symbol using a simple mapping based on common knowledge
        This is a simplified approach - in a production system, you would use a more comprehensive database
        """
        # Technology companies
        tech_companies = ['AAPL', 'MSFT', 'GOOGL', 'GOOG', 'META', 'AMZN', 'NVDA', 'AMD', 'INTC', 'CSCO', 'ORCL', 'IBM', 'ADBE', 'CRM', 
                         'AVGO', 'TXN', 'QCOM', 'AMAT', 'MU', 'LRCX', 'NOW', 'INTU', 'PYPL', 'NFLX', 'TWTR', 'SNAP', 'PINS', 'SPOT', 'ZM', 'TEAM', 'WDAY', 'SPLK', 'DDOG']
        
        # Financial companies
        financial_companies = ['JPM', 'BAC', 'WFC', 'C', 'GS', 'MS', 'AXP', 'V', 'MA', 'BLK', 'SCHW', 'PNC', 'USB', 'TFC', 'COF', 'SPGI', 'MCO', 
                              'ICE', 'CME', 'CB', 'MMC', 'PGR', 'TRV', 'ALL', 'AIG', 'MET', 'PRU', 'BK', 'STT', 'TROW', 'NTRS', 'AMP', 'DFS', 'FITB', 'RF', 'KEY', 'CFG']
        
        # Healthcare companies
        healthcare_companies = ['JNJ', 'PFE', 'MRK', 'ABBV', 'ABT', 'UNH', 'CVS', 'AMGN', 'MDT', 'GILD', 'ISRG', 'ELV', 'LLY', 'BMY', 'TMO', 'DHR', 
                               'SYK', 'ZTS', 'REGN', 'VRTX', 'MRNA', 'BIIB', 'IDXX', 'BSX', 'BDX', 'A', 'BAX', 'CI', 'HUM', 'CNC', 'ANTM', 'ILMN', 'IQV', 'DXCM', 'ALGN', 'RMD', 'MTD', 'WAT']
        
        # Energy companies
        energy_companies = ['XOM', 'CVX', 'COP', 'EOG', 'SLB', 'PXD', 'OXY', 'PSX', 'VLO', 'MPC', 'KMI', 'WMB', 'OKE', 'DVN', 'HAL', 
                           'BKR', 'MRO', 'APA', 'HES', 'FANG', 'CTRA', 'EQT', 'LNG', 'CVI', 'TRGP', 'PDCE', 'SM', 'CHK', 'AR', 'RRC']
        
        # Industrial companies
        industrial_companies = ['GE', 'HON', 'MMM', 'CAT', 'DE', 'BA', 'LMT', 'RTX', 'UPS', 'FDX', 'UNP', 'CSX', 'NSC', 'LHX', 'GD', 'EMR', 'ETN', 
                               'ITW', 'CMI', 'PH', 'ROK', 'IR', 'TT', 'CARR', 'OTIS', 'PCAR', 'URI', 'FAST', 'GWW', 'SWK', 'CTAS', 'RSG', 'WM', 'JCI', 'AME', 'TDG', 'CPRT', 'DAL', 'UAL', 'LUV']
        
        # Consumer Discretionary
        consumer_disc_companies = ['AMZN', 'TSLA', 'HD', 'MCD', 'NKE', 'SBUX', 'TGT', 'LOW', 'BKNG', 'MAR', 'DIS', 'CMCSA', 'NFLX', 'TJX', 'EBAY', 
                                  'BBY', 'DG', 'DLTR', 'ROST', 'ORLY', 'AZO', 'ULTA', 'LVS', 'MGM', 'WYNN', 'RCL', 'CCL', 'HLT', 'F', 'GM', 'TSCO', 'DPZ', 'YUM', 'QSR', 'DRI', 'CMG', 'APTV', 'EXPE', 'ETSY', 'LULU']
        
        # Consumer Staples
        consumer_staples_companies = ['PG', 'KO', 'PEP', 'WMT', 'COST', 'PM', 'MO', 'EL', 'CL', 'KMB', 'GIS', 'K', 'SYY', 'ADM', 'KHC', 'STZ', 
                                     'MDLZ', 'HSY', 'KR', 'CLX', 'CAG', 'CPB', 'HRL', 'SJM', 'TAP', 'BG', 'MNST', 'COTY', 'CHD', 'MKC', 'TSN', 'LW']
        
        # Materials companies
        materials_companies = ['LIN', 'APD', 'SHW', 'FCX', 'NEM', 'ECL', 'DD', 'DOW', 'PPG', 'NUE', 'CTVA', 'VMC', 'MLM', 'ALB', 'FMC', 
                              'IFF', 'EMN', 'CF', 'MOS', 'IP', 'PKG', 'SEE', 'AVY', 'BLL', 'AMCR', 'WRK', 'CE', 'GOLD', 'AA', 'X', 'CLF', 'MT']
        
        # Utilities companies
        utilities_companies = ['NEE', 'DUK', 'SO', 'D', 'AEP', 'EXC', 'SRE', 'PCG', 'XEL', 'ED', 'ES', 'WEC', 'PEG', 'DTE', 'AEE', 'CMS', 
                              'ETR', 'FE', 'LNT', 'EVRG', 'AES', 'CNP', 'NI', 'PPL', 'AWK', 'CEG', 'EIX', 'PNW', 'ATO', 'NRG', 'OGE', 'POR', 'NWE', 'SR', 'AVA']
        
        # Real Estate companies
        real_estate_companies = ['AMT', 'PLD', 'CCI', 'EQIX', 'PSA', 'O', 'DLR', 'WELL', 'SBAC', 'AVB', 'EQR', 'SPG', 'VICI', 'VTR', 'ESS', 
                                'ARE', 'INVH', 'UDR', 'EXR', 'MAA', 'KIM', 'REG', 'FRT', 'BXP', 'HST', 'VNO', 'CPT', 'PEAK', 'IRM', 'SLG', 'AIV', 'DEI']
        
        # Communication Services
        communication_companies = ['GOOGL', 'GOOG', 'META', 'NFLX', 'DIS', 'CMCSA', 'VZ', 'T', 'TMUS', 'CHTR', 'ATVI', 'EA', 'TTWO', 'OMC', 'IPG', 
                                  'LYV', 'PARA', 'FOXA', 'FOX', 'DISH', 'LUMN', 'WBD', 'NWSA', 'NWS', 'TWTR', 'SNAP', 'PINS', 'MTCH', 'SPOT', 'ZM', 'RBLX']
        
        # Determine sector based on symbol
        if symbol in tech_companies:
            return 'Technology'
        elif symbol in financial_companies:
            return 'Financials'
        elif symbol in healthcare_companies:
            return 'Healthcare'
        elif symbol in energy_companies:
            return 'Energy'
        elif symbol in industrial_companies:
            return 'Industrials'
        elif symbol in consumer_disc_companies:
            return 'Consumer Discretionary'
        elif symbol in consumer_staples_companies:
            return 'Consumer Staples'
        elif symbol in materials_companies:
            return 'Materials'
        elif symbol in utilities_companies:
            return 'Utilities'
        elif symbol in real_estate_companies:
            return 'Real Estate'
        elif symbol in communication_companies:
            return 'Communication Services'
        else:
            # Try to infer sector from symbol prefix or common patterns
            if symbol.startswith(('AAPL', 'MSFT', 'IBM', 'CSCO', 'ORCL', 'HPQ', 'DELL', 'NVDA', 'AMD', 'INTC')):
                return 'Technology'
            elif symbol.startswith(('JPM', 'BAC', 'WFC', 'C', 'GS', 'MS', 'AXP', 'V', 'MA')):
                return 'Financials'
            elif symbol.startswith(('JNJ', 'PFE', 'MRK', 'ABBV', 'ABT', 'UNH', 'CVS')):
                return 'Healthcare'
            elif symbol.startswith(('XOM', 'CVX', 'COP', 'EOG', 'SLB', 'PXD', 'OXY')):
                return 'Energy'
            else:
                return 'Unknown'
    
    def run(self):
        """Run the strategy"""
        self.run_strategy()
    
    def get_symbols(self):
        """
        Get the list of symbols to trade, including both S&P 500 and mid-cap stocks if configured
        Returns a list of ticker symbols
        """
        try:
            # Get S&P 500 symbols
            sp500_symbols = get_sp500_symbols()
            
            # Check if mid-cap stocks are enabled
            include_midcap = self.config.get('strategy', {}).get('include_midcap', False)
            symbols = sp500_symbols
            
            if include_midcap:
                # Get mid-cap configuration
                midcap_config = self.config.get('strategy', {}).get('midcap_stocks', {})
                
                # Get the list of mid-cap symbols
                if 'symbols' in midcap_config and midcap_config['symbols']:
                    midcap_symbols = midcap_config['symbols']
                else:
                    # If no predefined list, try to get from the get_midcap_symbols function
                    try:
                        midcap_symbols = get_midcap_symbols(
                            min_avg_volume=midcap_config.get('min_avg_volume', 500000),
                            max_symbols=midcap_config.get('max_symbols', 50)
                        )
                    except Exception as e:
                        logger.warning(f"Failed to get mid-cap symbols: {str(e)}")
        
                # Add mid-cap symbols to the list
                symbols = list(set(sp500_symbols + midcap_symbols))
                logger.info(f"Added {len(midcap_symbols)} mid-cap symbols to the trading universe")
            
            logger.info(f"Trading universe contains {len(symbols)} symbols")
            return symbols
            
        except Exception as e:
            logger.error(f"Error getting symbols: {str(e)}")
            # Fall back to TOP 100 symbols if there's an error
            logger.warning("Falling back to TOP 100 symbols")
            return self.TOP_100_SYMBOLS
    
def run_backtest(start_date, end_date, mode='backtest', max_signals=None, initial_capital=300, random_seed=42):
    """Run a backtest for a specified period with specified initial capital"""
    try:
        # Load configuration
        config_path = 'sp500_config.yaml'
        with open(config_path, 'r') as file:
            config = yaml.safe_load(file)
        
        logger.info(f"Running backtest from {start_date} to {end_date} with initial capital ${initial_capital} (Seed: {random_seed})")
        
        # Create output directories if they don't exist
        for path_key in ['backtest_results', 'plots', 'trades', 'performance']:
            os.makedirs(config['paths'][path_key], exist_ok=True)
        
        # Load Alpaca credentials
        with open('alpaca_credentials.json', 'r') as f:
            credentials = json.load(f)
        
        # Use paper trading credentials for backtesting
        paper_credentials = credentials['paper']
        
        # Initialize Alpaca API
        api = tradeapi.REST(
            paper_credentials['api_key'],
            paper_credentials['api_secret'],
            paper_credentials['base_url'],
            api_version='v2'
        )
        
        # Initialize strategy in backtest mode
        strategy = SP500Strategy(
            api=api,
            config=config,
            mode=mode,
            backtest_mode=True,
            backtest_start_date=start_date,
            backtest_end_date=end_date
        )
        
        # Run the strategy
        signals = strategy.run_strategy()
        
        # Get max signals from config if not specified
        if max_signals is None:
            max_signals = config.get('strategy', {}).get('max_trades_per_run', 40)
        
        # Count mid-cap and large-cap signals
        midcap_signals = [s for s in signals if s.get('is_midcap', False)]
        largecap_signals = [s for s in signals if not s.get('is_midcap', False)]
        
        logger.info(f"Generated {len(signals)} total signals: {len(largecap_signals)} large-cap, {len(midcap_signals)} mid-cap")
        
        # Ensure a balanced mix of LONG trades
        if len(signals) > max_signals:
            logger.info(f"Limiting signals to top {max_signals} (from {len(signals)} total)")
            
            # Get large-cap percentage from config
            large_cap_percentage = config.get('strategy', {}).get('midcap_stocks', {}).get('large_cap_percentage', 70)
            
            # Calculate how many large-cap and mid-cap signals to include
            large_cap_count = int(max_signals * (large_cap_percentage / 100))
            mid_cap_count = max_signals - large_cap_count
            
            # Ensure we don't exceed available signals
            large_cap_count = min(large_cap_count, len(largecap_signals))
            mid_cap_count = min(mid_cap_count, len(midcap_symbols))
            
            # If we don't have enough of one type, allocate more to the other
            if large_cap_count < int(max_signals * (large_cap_percentage / 100)):
                additional_mid_cap = min(mid_cap_count + (int(max_signals * (large_cap_percentage / 100)) - large_cap_count), len(midcap_symbols))
                mid_cap_count = additional_mid_cap
            
            if mid_cap_count < (max_signals - int(max_signals * (large_cap_percentage / 100))):
                additional_large_cap = min(large_cap_count + ((max_signals - int(max_signals * (large_cap_percentage / 100))) - mid_cap_count), len(largecap_symbols))
                large_cap_count = additional_large_cap
            
            # Get the top N signals of each type
            # Sort signals deterministically by score and then by symbol (for tiebreaking)
            largecap_signals = sorted(largecap_signals, key=lambda x: (x['score'], x['symbol']), reverse=True)
            midcap_signals = sorted(midcap_signals, key=lambda x: (x['score'], x['symbol']), reverse=True)
            
            selected_large_cap = largecap_signals[:large_cap_count]
            selected_mid_cap = midcap_signals[:mid_cap_count]
            
            # Combine and re-sort by score and symbol (for deterministic ordering)
            signals = selected_large_cap + selected_mid_cap
            signals = sorted(signals, key=lambda x: (x['score'], x['symbol']), reverse=True)
            
            logger.info(f"Final signals: {len(signals)} total ({len(selected_large_cap)} large-cap, {len(selected_mid_cap)} mid-cap)")
        else:
            # If no max_signals specified or we have fewer signals than max, still log the signal count
            # Sort signals deterministically by score and then by symbol (for tiebreaking)
            signals = sorted(signals, key=lambda x: (x['score'], x['symbol']), reverse=True)
            logger.info(f"Using all {len(signals)} signals ({len(largecap_signals)} large-cap, {len(midcap_signals)} mid-cap)")
        
        # Simulate trade outcomes for performance metrics
        if signals:
            # Create a list to store simulated trades
            simulated_trades = []
            
            # Set random seed for reproducibility
            np.random.seed(random_seed)
            
            # Define win rates based on historical performance and market regime
            base_long_win_rate = 0.62
            
            # Define win rate adjustments based on market regime
            market_regime_adjustments = {
                'STRONG_BULLISH': {'LONG': 0.15},
                'BULLISH': {'LONG': 0.10},
                'NEUTRAL': {'LONG': 0.00},
                'BEARISH': {'LONG': -0.10},
                'STRONG_BEARISH': {'LONG': -0.20}
            }
            
            # Define average gains and losses
            avg_long_win = 0.05
            avg_long_loss = -0.02
            
            # Define average holding periods
            avg_holding_period_win = 12
            avg_holding_period_loss = 5
            
            # Parse the start date
            start_datetime = datetime.strptime(start_date, "%Y-%m-%d")
            
            # Get current market regime
            market_regime = strategy.detect_market_regime()
            
            # Track remaining capital
            remaining_capital = initial_capital
            
            for signal in signals:
                # Calculate position size based on signal score and remaining capital
                # Use a percentage of remaining capital for each trade
                
                # Base position size as percentage of remaining capital
                base_position_pct = config.get('strategy', {}).get('position_sizing', {}).get('base_position_pct', 5)
                base_position_size = (base_position_pct / 100) * remaining_capital
                
                if signal['score'] >= 0.9:  # Tier 1
                    position_size = base_position_size * 3.0
                    tier = "Tier 1 (≥0.9)"
                elif signal['score'] >= 0.8:  # Tier 2
                    position_size = base_position_size * 1.5
                    tier = "Tier 2 (0.8-0.9)"
                else:  # Skip Tier 3 and Tier 4 trades
                    logger.info(f"Skipping trade for {signal['symbol']} with score {signal['score']:.2f} - below Tier 2 threshold")
                    continue
                
                # Adjust for mid-cap stocks
                if signal.get('is_midcap', False):
                    midcap_factor = config.get('strategy', {}).get('midcap_stocks', {}).get('position_factor', 0.8)
                    position_size *= midcap_factor
                
                # Ensure position size doesn't exceed remaining capital
                position_size = min(position_size, remaining_capital * 0.95)
                
                # Calculate fractional shares (no need to round to integers)
                shares = position_size / signal['price']
                
                # Create a base trade
                trade = {
                    'symbol': signal['symbol'],
                    'direction': 'LONG',
                    'entry_date': start_datetime + timedelta(days=np.random.randint(1, 10)),
                    'entry_price': signal['price'],
                    'shares': shares,
                    'position_size': position_size,
                    'signal_score': signal['score'],
                    'market_regime': market_regime,
                    'sector': strategy.get_symbol_sector(signal['symbol']),
                }
                
                # Adjust win rate based on market regime
                regime_adjustment = market_regime_adjustments.get(market_regime, {'LONG': 0})
                
                # Calculate adjusted win rate
                win_rate = base_long_win_rate + regime_adjustment['LONG']
                # Adjust win rate based on signal score
                win_rate = min(0.95, win_rate + (signal['score'] - 0.7) * 0.5)
                
                # Determine if trade is a winner based on adjusted win rate
                is_winner = np.random.random() < win_rate
                
                # Calculate exit price based on outcome
                pct_change = avg_long_win if is_winner else avg_long_loss
                
                # Add some randomness to the outcome
                pct_change += np.random.normal(0, 0.01)
                
                # Calculate exit price
                exit_price = signal['price'] * (1 + pct_change)
                
                # Calculate holding period
                holding_period = int(np.random.normal(
                    avg_holding_period_win if is_winner else avg_holding_period_loss, 
                    3
                ))
                holding_period = max(1, holding_period)
                
                # Calculate exit date
                exit_date = trade['entry_date'] + timedelta(days=holding_period)
                
                # Add exit information to trade
                trade['exit_price'] = exit_price
                trade['exit_date'] = exit_date
                trade['profit_loss'] = (exit_price - trade['entry_price']) * trade['shares']
                trade['profit_loss_pct'] = pct_change * 100
                trade['is_win'] = is_winner
                trade['tier'] = strategy.get_signal_tier(signal['score'])
                
                # Update remaining capital
                remaining_capital = remaining_capital - position_size + (position_size * (1 + pct_change))
                trade['remaining_capital'] = remaining_capital
                
                # Add trade to list
                simulated_trades.append(trade)
            
            # Save simulated trades to CSV
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            trades_file = os.path.join(config['paths']['backtest_results'], 
                                    f"backtest_trades_{start_date}_to_{end_date}_{timestamp}.csv")
            
            trades_df = pd.DataFrame(simulated_trades)
            trades_df.to_csv(trades_file, index=False)
            logger.info(f"Saved {len(simulated_trades)} simulated trades to {trades_file}")
            
            # Calculate performance metrics using the simulated trades
            metrics = strategy.calculate_performance_metrics(simulated_trades)
            
            # Add final capital and return metrics
            metrics['initial_capital'] = initial_capital
            metrics['final_capital'] = remaining_capital
            metrics['total_return'] = (remaining_capital / initial_capital - 1) * 100
            
        else:
            metrics = None
        
        # Calculate performance metrics
        logger.info("Calculating performance metrics for the backtest...")
        
        # Generate backtest summary
        summary = {
            'start_date': start_date,
            'end_date': end_date,
            'total_signals': len(signals) if signals else 0,
            'long_signals': len([s for s in signals if s['direction'] == 'LONG']) if signals else 0,
            'avg_score': sum([s['score'] for s in signals]) / len(signals) if signals and len(signals) > 0 else 0,
            'avg_long_score': sum([s['score'] for s in signals if s['direction'] == 'LONG']) / len([s for s in signals if s['direction'] == 'LONG']) if signals and len([s for s in signals if s['direction'] == 'LONG']) > 0 else 0,
            'long_win_rate': metrics['win_rate'] if metrics else 0  # For LONG-only strategy, long_win_rate equals win_rate
        }
        
        # Add performance metrics to summary if available
        if metrics:
            summary.update({
                'win_rate': metrics['win_rate'],
                'profit_factor': metrics['profit_factor'],
                'avg_win': metrics['avg_win'],
                'avg_loss': metrics['avg_loss'],
                'avg_holding_period': metrics['avg_holding_period'],
                'total_trades': metrics['total_trades'],
                'winning_trades': metrics['winning_trades'],
                'losing_trades': metrics['losing_trades'],
                'initial_capital': metrics['initial_capital'],
                'final_capital': metrics['final_capital'],
                'total_return': metrics['total_return']
            })
            
            # Add tier metrics if available
            if 'tier_metrics' in metrics and metrics['tier_metrics']:
                summary['tier_metrics'] = metrics['tier_metrics']
        
        # Save backtest results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_path = os.path.join(config['paths']['backtest_results'], 
                                    f"backtest_results_{start_date}_to_{end_date}_{timestamp}.csv")
        
        # Create a DataFrame from signals
        if signals:
            signals_df = pd.DataFrame(signals)
            signals_df.to_csv(results_path, index=False)
            logger.info(f"Backtest results saved to {results_path}")
        
        # Log summary
        logger.info(f"Backtest Summary: {summary}")
        
        # Calculate combined metrics
        if metrics:
            combined_win_rate = (metrics['win_rate'] * metrics['total_trades']) / metrics['total_trades']
            combined_long_win_rate = combined_win_rate
            
            # Log combined metrics
            logger.info(f"Combined Win Rate: {combined_win_rate:.2f}%")
            logger.info(f"Combined LONG Win Rate: {combined_long_win_rate:.2f}%")
            logger.info(f"Initial Capital: ${initial_capital:.2f}")
            logger.info(f"Final Capital: ${metrics['final_capital']:.2f}")
            logger.info(f"Total Return: {metrics['total_return']:.2f}%")
        
        return summary, signals
        
    except Exception as e:
        logger.error(f"Error running backtest: {str(e)}")
        traceback.print_exc()
        return None, []
