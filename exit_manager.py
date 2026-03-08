import logging
from strategy import strategy_engine 
# We might need indicator calcs here, or assume df passed has them.
# The `strategy_engine.prepare_data` can be reused.

logger = logging.getLogger(__name__)

class ExitManager:
    def __init__(self):
        pass

    def check_exit_conditions(self, df, position):
        """
        Checks if an open position should be exited.
        position: dict containing {entry_price, quantity, stop_loss, type, symbol, entry_time}
        """
        # Ensure DF has indicators
        df = strategy_engine.prepare_data(df)
        last = df.iloc[-1]
        
        current_price = last['close'] # This is Index price, not Option price.
        # Note: If position is an Option, we need to track Option Price for SL/Target?
        # User Conditions: "SL = high of pullback candle (Index)". "Book 50% at 1:1 R:R (Index or Option? Usually Spot refers to Spot)".
        
        # Let's assume we are tracking SPOT price for logical exits, and Option price for PnL exits.
        # But `position` might hold Option symbol. We need to know which one we are checking.
        # If this function is passed the INDEX dataframe, we check Index conditions.
        
        reasons = []
        should_exit = False
        exit_type = None # 'PARTIAL', 'FULL'
        
        # 7️⃣ TARGET & EXIT CONDITIONS
        
        # 1. Candle closes above 20 EMA (for PUT)
        # "Candle closes above 20 EMA (PUT)" -> Bullish close above EMA
        if last['close'] > last['ema_20']:
            return True, "FULL", "Close above 20 EMA"

        # 2. Price touches VWAP
        if last['high'] >= last['vwap']: # Touching VWAP from below
             return True, "FULL", "Touched VWAP"

        # 3. Two consecutive candles against position (Green candles)
        if len(df) >= 2:
            prev = df.iloc[-2]
            if last['color'] == 'GREEN' and prev['color'] == 'GREEN':
                return True, "FULL", "2 Consecutive Green Candles"
                
        # 4. Time > 11:30 and no momentum (Optional check)
        # Not implementing complex momentum check yet, but time check:
        # User: "Time > 11:30 and no momentum"
        
        # SL Check (Index based)
        if position.get('stop_loss'):
            if last['high'] >= position['stop_loss']:
                return True, "FULL", "Index SL Hit"
                
        return False, None, None

exit_manager = ExitManager()
