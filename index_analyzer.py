"""
Index Analyzer - Determines Best Index and Option to Trade
Analyzes SENSEX, NIFTY 50, and BANK NIFTY to find the best trading opportunity
"""
import logging
import pandas as pd
import datetime
from typing import Dict, List, Tuple, Optional
import yfinance as yf

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class IndexAnalyzer:
    """Analyzes multiple indices to find the best trading opportunity"""
    
    def __init__(self):
        self.indices = {
            'NIFTY 50': {
                'ticker': '^NSEI',
                'name': 'NIFTY 50',
                'option_symbol': 'NIFTY',
                'lot_size': 50,
                'strike_gap': 50
            },
            'BANK NIFTY': {
                'ticker': '^NSEBANK',
                'name': 'BANK NIFTY',
                'option_symbol': 'BANKNIFTY',
                'lot_size': 15,
                'strike_gap': 100
            },
            'SENSEX': {
                'ticker': '^BSESN',
                'name': 'SENSEX',
                'option_symbol': 'SENSEX',
                'lot_size': 10,
                'strike_gap': 100
            }
        }
    
    def fetch_index_data(self, ticker: str, period: str = '5d') -> pd.DataFrame:
        """Fetch historical data for an index"""
        try:
            stock = yf.Ticker(ticker)
            df = stock.history(period=period, interval='5m')
            
            if df.empty:
                logger.warning(f"No data for {ticker}")
                return pd.DataFrame()
            
            df = df.rename(columns={
                'Open': 'open',
                'High': 'high',
                'Low': 'low',
                'Close': 'close',
                'Volume': 'volume'
            })
            
            return df
            
        except Exception as e:
            logger.error(f"Error fetching data for {ticker}: {e}")
            return pd.DataFrame()
    
    def calculate_momentum(self, df: pd.DataFrame) -> Dict:
        """Calculate momentum indicators"""
        if df.empty or len(df) < 20:
            return {}
        
        try:
            current_price = df['close'].iloc[-1]
            
            # Price changes
            change_1h = ((current_price - df['close'].iloc[-12]) / df['close'].iloc[-12]) * 100 if len(df) >= 12 else 0
            change_1d = ((current_price - df['close'].iloc[-78]) / df['close'].iloc[-78]) * 100 if len(df) >= 78 else 0
            
            # Volatility (ATR-like)
            df['tr'] = df[['high', 'low']].apply(lambda x: x['high'] - x['low'], axis=1)
            atr = df['tr'].rolling(14).mean().iloc[-1]
            atr_pct = (atr / current_price) * 100
            
            # Volume analysis
            avg_volume = df['volume'].rolling(20).mean().iloc[-1]
            current_volume = df['volume'].iloc[-1]
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1
            
            # Trend strength (simple moving averages)
            sma_20 = df['close'].rolling(20).mean().iloc[-1]
            sma_50 = df['close'].rolling(50).mean().iloc[-1] if len(df) >= 50 else sma_20
            
            trend = 'BULLISH' if current_price > sma_20 > sma_50 else 'BEARISH' if current_price < sma_20 < sma_50 else 'NEUTRAL'
            
            # Range analysis
            high_1d = df['high'].iloc[-78:].max() if len(df) >= 78 else df['high'].max()
            low_1d = df['low'].iloc[-78:].min() if len(df) >= 78 else df['low'].min()
            range_position = ((current_price - low_1d) / (high_1d - low_1d)) * 100 if high_1d != low_1d else 50
            
            return {
                'current_price': current_price,
                'change_1h': change_1h,
                'change_1d': change_1d,
                'atr_pct': atr_pct,
                'volume_ratio': volume_ratio,
                'trend': trend,
                'sma_20': sma_20,
                'sma_50': sma_50,
                'range_position': range_position,
                'high_1d': high_1d,
                'low_1d': low_1d
            }
            
        except Exception as e:
            logger.error(f"Error calculating momentum: {e}")
            return {}
    
    def calculate_score(self, metrics: Dict) -> float:
        """Calculate trading opportunity score (0-100)"""
        if not metrics:
            return 0
        
        score = 0
        
        # Momentum score (30 points)
        abs_change_1h = abs(metrics.get('change_1h', 0))
        if abs_change_1h > 1.0:
            score += 30
        elif abs_change_1h > 0.5:
            score += 20
        elif abs_change_1h > 0.25:
            score += 10
        
        # Volatility score (20 points) - higher volatility = better for options
        atr_pct = metrics.get('atr_pct', 0)
        if atr_pct > 1.5:
            score += 20
        elif atr_pct > 1.0:
            score += 15
        elif atr_pct > 0.5:
            score += 10
        
        # Volume score (20 points)
        volume_ratio = metrics.get('volume_ratio', 1)
        if volume_ratio > 1.5:
            score += 20
        elif volume_ratio > 1.2:
            score += 15
        elif volume_ratio > 1.0:
            score += 10
        
        # Trend clarity score (20 points)
        trend = metrics.get('trend', 'NEUTRAL')
        if trend in ['BULLISH', 'BEARISH']:
            score += 20
        else:
            score += 5
        
        # Range position score (10 points) - extremes are better
        range_pos = metrics.get('range_position', 50)
        if range_pos > 80 or range_pos < 20:
            score += 10
        elif range_pos > 70 or range_pos < 30:
            score += 5
        
        return min(score, 100)
    
    def suggest_option_type(self, metrics: Dict) -> Tuple[str, str]:
        """Suggest CE or PE based on analysis"""
        if not metrics:
            return 'PE', 'NEUTRAL'
        
        trend = metrics.get('trend', 'NEUTRAL')
        change_1h = metrics.get('change_1h', 0)
        range_pos = metrics.get('range_position', 50)
        
        # Strong bullish signals
        if trend == 'BULLISH' and change_1h > 0.3 and range_pos < 70:
            return 'CE', 'STRONG_BULLISH'
        
        # Strong bearish signals
        if trend == 'BEARISH' and change_1h < -0.3 and range_pos > 30:
            return 'PE', 'STRONG_BEARISH'
        
        # Moderate bullish
        if change_1h > 0.2 or (trend == 'BULLISH' and range_pos < 60):
            return 'CE', 'BULLISH'
        
        # Moderate bearish
        if change_1h < -0.2 or (trend == 'BEARISH' and range_pos > 40):
            return 'PE', 'BEARISH'
        
        # Default to PE (safer in uncertain conditions)
        return 'PE', 'NEUTRAL'
    
    def suggest_strike(self, current_price: float, option_type: str, strike_gap: int, 
                      trend_strength: str) -> int:
        """Suggest strike price based on current price and trend"""
        
        # Round to nearest strike
        base_strike = round(current_price / strike_gap) * strike_gap
        
        # Adjust based on trend strength
        if trend_strength == 'STRONG_BULLISH':
            # Slightly OTM for CE
            return base_strike + strike_gap if option_type == 'CE' else base_strike
        elif trend_strength == 'STRONG_BEARISH':
            # Slightly OTM for PE
            return base_strike - strike_gap if option_type == 'PE' else base_strike
        elif trend_strength in ['BULLISH', 'BEARISH']:
            # ATM
            return base_strike
        else:
            # Slightly ITM for safety
            return base_strike - strike_gap if option_type == 'CE' else base_strike + strike_gap
    
    def analyze_all_indices(self) -> List[Dict]:
        """Analyze all indices and return sorted by opportunity score"""
        results = []
        
        logger.info("Analyzing indices...")
        
        for index_name, index_info in self.indices.items():
            logger.info(f"Analyzing {index_name}...")
            
            # Fetch data
            df = self.fetch_index_data(index_info['ticker'])
            
            if df.empty:
                logger.warning(f"Skipping {index_name} - no data")
                continue
            
            # Calculate metrics
            metrics = self.calculate_momentum(df)
            
            if not metrics:
                logger.warning(f"Skipping {index_name} - no metrics")
                continue
            
            # Calculate score
            score = self.calculate_score(metrics)
            
            # Suggest option type
            option_type, trend_strength = self.suggest_option_type(metrics)
            
            # Suggest strike
            strike = self.suggest_strike(
                metrics['current_price'],
                option_type,
                index_info['strike_gap'],
                trend_strength
            )
            
            result = {
                'index': index_name,
                'option_symbol': index_info['option_symbol'],
                'score': score,
                'current_price': metrics['current_price'],
                'change_1h': metrics['change_1h'],
                'change_1d': metrics['change_1d'],
                'trend': metrics['trend'],
                'trend_strength': trend_strength,
                'option_type': option_type,
                'suggested_strike': strike,
                'lot_size': index_info['lot_size'],
                'atr_pct': metrics['atr_pct'],
                'volume_ratio': metrics['volume_ratio'],
                'range_position': metrics['range_position']
            }
            
            results.append(result)
            
            logger.info(f"✅ {index_name}: Score={score:.0f}, {option_type} {strike}")
        
        # Sort by score (highest first)
        results.sort(key=lambda x: x['score'], reverse=True)
        
        return results
    
    def get_best_trade(self) -> Optional[Dict]:
        """Get the single best trading opportunity"""
        results = self.analyze_all_indices()
        
        if not results:
            logger.warning("No trading opportunities found")
            return None
        
        best = results[0]
        
        logger.info(f"🏆 Best opportunity: {best['index']} {best['option_type']} {best['suggested_strike']}")
        logger.info(f"   Score: {best['score']:.0f}/100")
        logger.info(f"   Trend: {best['trend_strength']}")
        
        return best
    
    def format_analysis_report(self, results: List[Dict]) -> str:
        """Format analysis results as a readable report"""
        if not results:
            return "❌ No data available for analysis"
        
        report = "📊 **INDEX ANALYSIS REPORT**\n\n"
        report += f"Analyzed: {len(results)} indices\n"
        report += f"Time: {datetime.datetime.now().strftime('%H:%M:%S')}\n\n"
        
        for i, result in enumerate(results, 1):
            emoji = "🏆" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "📍"
            
            report += f"{emoji} **{result['index']}** (Score: {result['score']:.0f}/100)\n"
            report += f"   Price: ₹{result['current_price']:.2f} ({result['change_1h']:+.2f}% 1H)\n"
            report += f"   Trend: {result['trend']} ({result['trend_strength']})\n"
            report += f"   **Suggested: {result['option_type']} {result['suggested_strike']}**\n"
            report += f"   Lot Size: {result['lot_size']} | Vol: {result['volume_ratio']:.2f}x\n"
            
            # Add reasoning
            if result['score'] >= 70:
                report += f"   ✅ Strong opportunity - High momentum & volatility\n"
            elif result['score'] >= 50:
                report += f"   🟡 Moderate opportunity - Decent setup\n"
            else:
                report += f"   ⚠️ Weak opportunity - Low conviction\n"
            
            report += "\n"
        
        # Add recommendation
        best = results[0]
        report += "🎯 **RECOMMENDATION**\n"
        report += f"Trade: {best['option_symbol']} {best['option_type']} {best['suggested_strike']}\n"
        report += f"Reason: {best['trend_strength']} trend with {best['score']:.0f}/100 score\n"
        
        return report


# Global instance
index_analyzer = IndexAnalyzer()


def main():
    """Test the analyzer"""
    print("=" * 70)
    print("INDEX ANALYZER - FIND BEST TRADING OPPORTUNITY")
    print("=" * 70)
    
    analyzer = IndexAnalyzer()
    
    # Analyze all indices
    results = analyzer.analyze_all_indices()
    
    if not results:
        print("\n❌ No data available")
        return
    
    # Print report
    report = analyzer.format_analysis_report(results)
    print("\n" + report)
    
    # Get best trade
    best = analyzer.get_best_trade()
    
    if best:
        print("\n" + "=" * 70)
        print("BEST TRADE SETUP")
        print("=" * 70)
        print(f"Index: {best['index']}")
        print(f"Option: {best['option_symbol']} {best['option_type']} {best['suggested_strike']}")
        print(f"Score: {best['score']:.0f}/100")
        print(f"Trend: {best['trend_strength']}")
        print(f"Lot Size: {best['lot_size']}")
        print(f"Current Price: ₹{best['current_price']:.2f}")
        print(f"1H Change: {best['change_1h']:+.2f}%")


if __name__ == "__main__":
    main()
