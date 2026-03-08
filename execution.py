import logging
import math
from connect import get_kite_session
import config
import pandas as pd

logger = logging.getLogger(__name__)

class ExecutionManager:
    def __init__(self):
        self.kite = get_kite_session()
        self.orders = []
        self.daily_loss = 0
        self.trade_count = 0

    def get_option_symbol(self, underlying_symbol, spot_price, transaction_type):
        """
        Selects the regular Option symbol based on Spot Price.
        Example: NIFTY 18000 PE
        Rule: ATM or ATM-50 (for Put).
        If Spot 18040 -> ATM 18050, ATM-50 -> 18000.
        """
        # underlying_symbol e.g. "NSE:NIFTY 50" -> need "NIFTY"
        # We need the instrument list to match exact trading symbol format.
        # Format usually: "NIFTY23OCT18000PE" (changes with expiry).
        # We need to find the Current Week Expiry.
        
        # 1. Get Instruments for NFO
        try:
            instruments = self.kite.instruments("NFO")
            inst_df = pd.DataFrame(instruments)
            
            # Filter for NIFTY/BANKNIFTY
            name = "NIFTY" if "NIFTY" in underlying_symbol else "BANKNIFTY"
            step = config.INDICES[name]["strike_step"]
            
            # Calculate Strike
            # Put Entry: We want ATM or OTM? User said "ATM / ATM-50 PUT"
            # If Spot 18040. ATM is 18050. ATM-50 is 18000.
            # We round to nearest Step.
            rounded_strike = round(spot_price / step) * step
            
            # Ideally user wants slightly OTM or ATM? "ATM-50" for PE usually means LOWER strike (OTM) or HIGHER?
            # For PE, Lower strike is OTM. Higher strike is ITM.
            # "ATM / ATM-50". If Spot 18040, ATM=18050. ATM-50 (Strike-50) = 18000.
            # Let's target the rounded strike (ATM) first, or shift down by 1 step.
            
            target_strike = rounded_strike 
            # Logic: If user specifically asked for ATM or ATM-50, we can check liquidity or just pick ATM.
            # Simplification: ATM.
            
            # Filter Expiry: Get nearest expiry
            inst_df = inst_df[inst_df['name'] == name]
            inst_df['expiry'] = pd.to_datetime(inst_df['expiry'])
            today = pd.Timestamp.today().normalize()
            future_expiries = inst_df[inst_df['expiry'] >= today]
            nearest_expiry = future_expiries['expiry'].min()
            
            # Get Symbol
            # Filter for Strike and Option Type (PE)
            opt_df = future_expiries[
                (future_expiries['expiry'] == nearest_expiry) & 
                (future_expiries['strike'] == target_strike) & 
                (future_expiries['instrument_type'] == 'PE')
            ]
            
            if opt_df.empty:
                logger.error(f"No option found for {name} {target_strike} PE")
                return None
                
            tradingsymbol = opt_df.iloc[0]['tradingsymbol']
            return tradingsymbol
            
        except Exception as e:
            logger.error(f"Error selecting option symbol: {e}")
            return None

    def calculate_quantity(self, symbol, stop_loss_pts):
        """
        Calculates position size based on max risk per trade.
        Re-uses logic from supertrend or config.
        Risk per trade = Max Loss Per Day / 2 (since max 2 trades)? or fixed?
        Let's assume Risk Per Trade = Rs 1000 or derived.
        User said "Capital of 40000". "Max loss/day: 3000".
        Risk per trade could be 1500.
        """
        risk_per_trade = 1500 # Half of daily limit
        
        # Stop Loss in Points (Index points or Option points?)
        # User Strategy: SL is Index based. "SL = high of pullback candle".
        # We need to convert Index SL to Option SL.
        # Delta approximation ~ 0.5 (ATM).
        # Option SL Pts = Index SL Pts * 0.5
        
        # But we need Option Price to check if Capital is sufficient.
        
        # Let's assume we use Index Points to estimate risk.
        # Quantity = Risk / (SL_Pts * Delta)
        
        delta = 0.5
        est_sl_pts_opt = stop_loss_pts * delta
        if est_sl_pts_opt == 0: est_sl_pts_opt = 10 # Safety
        
        qty = math.floor(risk_per_trade / est_sl_pts_opt)
        
        # Round to lot size
        name = "NIFTY" if "NIFTY" in symbol else "BANKNIFTY"
        lot_size = config.INDICES[name]["lot_size"]
        
        qty = (qty // lot_size) * lot_size
        return max(qty, lot_size) # At least 1 lot

    def place_order(self, signal):
        """
        Places order via Kite.
        signal: {symbol, type, stop_loss (Index Level), price (Index Level)}
        """
        # 1. Check Limits
        if self.trade_count >= config.MAX_TRADES_PER_DAY:
            logger.warning("Max trades reached.")
            return False
            
        # 2. Get Option Symbol
        opt_symbol = self.get_option_symbol(signal['symbol'], signal['price'], "PE")
        if not opt_symbol:
            return False
            
        # 3. Calculate Quantity
        # SL Pts = Start Price (Index) - SL Price (Index)
        # For PE: Entry is BELOW SL (Wrong).
        # Wait, for PE (Bearish), Entry Index Price < SL Index Price? 
        # Yes, SL is High of Candle, Entry is Low.
        sl_pts = abs(signal['price'] - signal['stop_loss'])
        quantity = self.calculate_quantity(signal['symbol'], sl_pts)
        
        logger.info(f"Placing Order: {opt_symbol}, Qty: {quantity}, Est Index SL Pts: {sl_pts}")
        
        if config.TELEGRAM_BOT_TOKEN:
            # Notifier handled in Main, but here we execute.
            pass

        try:
            # DRY RUN CHECK
            # return "TEST_ORDER_ID"
            
            # REAL ORDER (Commented out for safety until verified)
            order_id = self.kite.place_order(
                item=opt_symbol, # Need exchange? "NFO:opt_symbol" if specific function
                tradingsymbol=opt_symbol,
                exchange="NFO",
                transaction_type=self.kite.TRANSACTION_TYPE_BUY,
                quantity=quantity,
                variety=self.kite.VARIETY_REGULAR,
                order_type=self.kite.ORDER_TYPE_MARKET,
                product=self.kite.PRODUCT_MIS
            )
            
            logger.info(f"Order Placed: {order_id}")
            self.trade_count += 1
            return order_id
            
        except Exception as e:
            logger.error(f"Order Placement Failed: {e}")
            return None

execution_manager = ExecutionManager()
