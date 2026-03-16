"""
Telegram Bot Interface for Trading Control
Send commands via Telegram to check status, close positions, etc.
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext
from connect import get_kite_session
import config
from datetime import datetime
import logging
import pandas as pd
from start_bot_with_monitor import get_global_kill_switch

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TradingBot:
    def __init__(self):
        self.kite = None  # Will be initialized after ensuring valid token
        self.capital = config.CAPITAL
        self.updater = Updater(token=config.TELEGRAM_BOT_TOKEN, use_context=True)
        
        # Calculate thresholds based on config
        if config.LOSS_THRESHOLD_PERCENT > 0:
            self.max_loss_threshold = (config.LOSS_THRESHOLD_PERCENT / 100) * self.capital
            self.loss_display = f"{config.LOSS_THRESHOLD_PERCENT}% (₹{self.max_loss_threshold:,.0f})"
        else:
            self.max_loss_threshold = config.LOSS_THRESHOLD
            self.loss_display = f"₹{self.max_loss_threshold:,.0f}"
        
        if config.PROFIT_THRESHOLD_PERCENT > 0:
            self.profit_threshold = (config.PROFIT_THRESHOLD_PERCENT / 100) * self.capital
            self.profit_display = f"{config.PROFIT_THRESHOLD_PERCENT}% (₹{self.profit_threshold:,.0f})"
        else:
            self.profit_threshold = config.PROFIT_THRESHOLD
            self.profit_display = f"₹{self.profit_threshold:,.0f}"
        
        # Drawdown threshold (percentage of peak profit)
        if config.DRAWDOWN_THRESHOLD_PERCENT > 0:
            self.drawdown_percent = config.DRAWDOWN_THRESHOLD_PERCENT
            self.drawdown_display = f"{config.DRAWDOWN_THRESHOLD_PERCENT}% of peak"
        else:
            self.profit_drawdown = config.DRAWDOWN_THRESHOLD
            self.drawdown_percent = 0
            self.drawdown_display = f"₹{self.profit_drawdown:,.0f}"
        
        self.setup_handlers()
        
        # Initialize Kite session after handlers are set up
        self.initialize_kite_session()
    
    def initialize_kite_session(self):
        """Initialize or reinitialize Kite session"""
        try:
            self.kite = get_kite_session()
            # Verify session is valid
            profile = self.kite.profile()
            logger.info(f"✅ Kite session initialized for user: {profile.get('user_name', 'Unknown')}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to initialize Kite session: {e}")
            self.kite = None
            return False
    
    def ensure_kite_session(self):
        """Ensure Kite session is valid, reinitialize if needed"""
        if self.kite is None:
            return self.initialize_kite_session()
        
        try:
            # Quick check if session is still valid
            self.kite.profile()
            return True
        except Exception as e:
            logger.warning(f"Kite session invalid, reinitializing: {e}")
            return self.initialize_kite_session()
        
    def setup_handlers(self):
        dp = self.updater.dispatcher
        
        # Basic commands
        dp.add_handler(CommandHandler("start", self.start_command))
        dp.add_handler(CommandHandler("help", self.help_command))
        
        # Status & P&L commands
        dp.add_handler(CommandHandler("status", self.status_command))
        dp.add_handler(CommandHandler("pnl", self.pnl_command))
        dp.add_handler(CommandHandler("positions", self.positions_command))
        dp.add_handler(CommandHandler("pos", self.positions_command))  # Shortcut
        
        # Trading commands
        dp.add_handler(CommandHandler("close", self.close_command))
        dp.add_handler(CommandHandler("closeall", self.close_command))  # Alias
        
        # Kill switch commands
        dp.add_handler(CommandHandler("killswitch", self.killswitch_command))
        dp.add_handler(CommandHandler("ks", self.killswitch_command))  # Shortcut
        dp.add_handler(CommandHandler("reactivate", self.reactivate_command))
        dp.add_handler(CommandHandler("segments", self.segments_command))
        dp.add_handler(CommandHandler("monitor", self.monitor_command))
        dp.add_handler(CommandHandler("stopmonitor", self.stopmonitor_command))
        dp.add_handler(CommandHandler("thresholds", self.thresholds_command))
        dp.add_handler(CommandHandler("setthreshold", self.setthreshold_command))
        
        # Capital & Risk commands
        dp.add_handler(CommandHandler("capital", self.capital_command))
        dp.add_handler(CommandHandler("setcapital", self.setcapital_command))
        dp.add_handler(CommandHandler("risk", self.risk_command))
        
        # Scanner commands
        dp.add_handler(CommandHandler("scan", self.scan_command))
        dp.add_handler(CommandHandler("consolidation", self.consolidation_command))
        dp.add_handler(CommandHandler("cons", self.consolidation_command))  # Shortcut
        dp.add_handler(CommandHandler("analyze", self.analyze_command))
        dp.add_handler(CommandHandler("best", self.best_trade_command))
        dp.add_handler(CommandHandler("indices", self.analyze_command))  # Alias
        
        # Paper trading commands
        dp.add_handler(CommandHandler("paper", self.paper_command))
        dp.add_handler(CommandHandler("papertrades", self.paper_trades_command))
        
        # Orders & History
        dp.add_handler(CommandHandler("orders", self.orders_command))
        dp.add_handler(CommandHandler("history", self.history_command))
        
        # System commands
        dp.add_handler(CommandHandler("bot", self.bot_status_command))
        dp.add_handler(CommandHandler("time", self.time_command))
        dp.add_handler(CommandHandler("logout", self.logout_command))
        dp.add_handler(CommandHandler("reconnect", self.reconnect_command))
        dp.add_handler(CommandHandler("refresh", self.reconnect_command))  # Alias
        
        # Button handlers
        dp.add_handler(CallbackQueryHandler(self.button_handler))
    
    def start_command(self, update: Update, context: CallbackContext):
        """Welcome message"""
        message = (
            "🤖 **Kite Algo Trading Bot**\n\n"
            "📊 **Status & P&L**\n"
            "/status - Quick P&L status with buttons\n"
            "/pnl - Detailed P&L breakdown\n"
            "/positions or /pos - View open positions\n"
            "/capital - Check available capital & sync from Kite\n"
            "/setcapital <amount> - Update trading capital\n"
            "/risk - View risk metrics\n\n"
            
            "🎯 **Trading**\n"
            "/close or /closeall - Close all positions\n"
            "/killswitch or /ks - Activate kill switch\n"
            "/monitor - Start auto-monitoring\n"
            "/stopmonitor - Stop auto-monitoring\n"
            "/reactivate - Reactivate trading after kill switch\n"
            "/segments - Manage trading segments\n"
            "/thresholds - View kill switch thresholds\n"
            "/setthreshold - Guide to update thresholds\n"
            "/orders - View today's orders\n"
            "/history - Trade history\n\n"
            
            "🔍 **Scanning**\n"
            "/scan - Manual scan for setups\n"
            "/consolidation or /cons - Check consolidations\n"
            "/analyze or /indices - Analyze all indices\n"
            "/best - Get best trading opportunity\n\n"
            
            "📝 **Paper Trading**\n"
            "/paper - Paper trading status\n"
            "/papertrades - View paper trade history\n\n"
            
            "⚙️ **System**\n"
            "/bot - Bot status\n"
            "/time - Current time\n"
            "/reconnect or /refresh - Reinitialize Kite session\n"
            "/logout - Logout and invalidate session\n"
            "/help - Show this help\n\n"
            
            "💡 **Quick Actions**\n"
            "Use /status for interactive buttons!"
        )
        update.message.reply_text(message)
    
    def help_command(self, update: Update, context: CallbackContext):
        """Help message"""
        self.start_command(update, context)
    
    def get_total_pnl(self):
        """Get total P&L with live LTP"""
        try:
            # Ensure session is valid
            if not self.ensure_kite_session():
                logger.error("Cannot fetch P&L - Kite session invalid")
                return 0, 0
            
            positions = self.kite.positions()
            
            # Get all open positions for live LTP
            open_positions = [pos for pos in positions['net'] if pos['quantity'] != 0]
            
            if open_positions:
                # Fetch live LTP
                instruments = [f"{pos['exchange']}:{pos['tradingsymbol']}" for pos in open_positions]
                try:
                    ltp_data = self.kite.ltp(instruments)
                except Exception as e:
                    logger.error(f"Failed to fetch live LTP for P&L: {e}")
                    ltp_data = {}
                
                # Recalculate P&L with live LTP
                day_pnl = 0
                for pos in positions['day']:
                    if pos['quantity'] != 0:
                        instrument_key = f"{pos['exchange']}:{pos['tradingsymbol']}"
                        if instrument_key in ltp_data:
                            live_ltp = ltp_data[instrument_key]['last_price']
                            pnl = (live_ltp - pos['average_price']) * pos['quantity']
                            day_pnl += pnl
                        else:
                            day_pnl += pos['pnl']
                    else:
                        day_pnl += pos['pnl']  # Closed positions use Kite's P&L
                
                net_pnl = day_pnl  # For intraday, day and net are same
            else:
                # No open positions, use Kite's P&L
                day_pnl = sum([pos['pnl'] for pos in positions['day']])
                net_pnl = sum([pos['pnl'] for pos in positions['net']])
            
            return day_pnl, net_pnl
        except Exception as e:
            logger.error(f"Error fetching P&L: {e}")
            return 0, 0
    
    def get_open_positions(self):
        """Get open positions"""
        try:
            # Ensure session is valid
            if not self.ensure_kite_session():
                logger.error("Cannot fetch positions - Kite session invalid")
                return []
            
            positions = self.kite.positions()['net']
            return [pos for pos in positions if pos['quantity'] != 0]
        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            return []
    
    def status_command(self, update: Update, context: CallbackContext):
        """Quick status check"""
        day_pnl, net_pnl = self.get_total_pnl()
        positions = self.get_open_positions()
        
        status_emoji = "🟢" if day_pnl >= 0 else "🔴"
        pnl_percent = (day_pnl / self.capital) * 100
        
        # Check if monitoring is active
        try:
            ks = get_global_kill_switch()
            monitoring_status = "🟢 ON" if ks.is_monitoring() else "🔴 OFF"
            logger.debug(f"Status check using global kill switch instance: {id(ks)}")
        except Exception as e:
            logger.error(f"Failed to get global kill switch for status check: {e}")
            monitoring_status = "❓"
        
        message = (
            f"{status_emoji} **QUICK STATUS**\n\n"
            f"Day P&L: ₹{day_pnl:,.2f} ({pnl_percent:+.2f}%)\n"
            f"Open Positions: {len(positions)}\n"
            f"Auto-Monitor: {monitoring_status}\n"
            f"Time: {datetime.now().strftime('%H:%M:%S')}"
        )
        
        # Add action buttons
        keyboard = [
            [
                InlineKeyboardButton("📊 Detailed P&L", callback_data='detailed_pnl'),
                InlineKeyboardButton("📍 Positions", callback_data='show_positions')
            ],
            [
                InlineKeyboardButton("🚨 Close All", callback_data='close_all_confirm'),
                InlineKeyboardButton("⚡ Kill Switch", callback_data='killswitch_confirm')
            ],
            [
                InlineKeyboardButton("👁️ Start Monitor", callback_data='monitor_start'),
                InlineKeyboardButton("⏹️ Stop Monitor", callback_data='monitor_stop')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        update.message.reply_text(message, reply_markup=reply_markup)
    
    def pnl_command(self, update: Update, context: CallbackContext):
        """Detailed P&L breakdown"""
        day_pnl, net_pnl = self.get_total_pnl()
        positions = self.get_open_positions()
        
        status_emoji = "🟢" if day_pnl >= 0 else "🔴"
        pnl_percent = (day_pnl / self.capital) * 100
        
        message = (
            f"{status_emoji} **DETAILED P&L REPORT**\n\n"
            f"📅 Day P&L: ₹{day_pnl:,.2f} ({pnl_percent:+.2f}%)\n"
            f"💼 Net P&L: ₹{net_pnl:,.2f}\n"
            f"💰 Capital: ₹{self.capital:,}\n"
            f"📊 Open Positions: {len(positions)}\n"
            f"🕐 Time: {datetime.now().strftime('%d-%b-%Y %H:%M:%S')}\n"
        )
        
        # Risk metrics
        if day_pnl < 0:
            loss_percent = abs(pnl_percent)
            remaining_loss = self.max_loss_threshold - abs(day_pnl)
            message += f"\n⚠️ Loss: {loss_percent:.2f}%\n"
            if remaining_loss > 0:
                message += f"⚠️ ₹{remaining_loss:,.2f} until kill switch ({self.loss_display})\n"
            else:
                message += f"🚨 Kill switch threshold exceeded!\n"
        else:
            message += f"\n✅ Profit: {pnl_percent:.2f}%\n"
            profit_threshold_pct = (self.profit_threshold / self.capital) * 100
            if pnl_percent >= profit_threshold_pct:
                message += f"🎯 Profit > {profit_threshold_pct:.1f}% of capital!\n"
        
        update.message.reply_text(message)
    
    def positions_command(self, update: Update, context: CallbackContext):
        """Show open positions with best available LTP"""
        positions = self.get_open_positions()
        
        if not positions:
            update.message.reply_text("📭 No open positions")
            return
        
        message = f"📊 **OPEN POSITIONS** ({len(positions)})\n\n"
        
        # Try to fetch live data (quote API as fallback)
        live_prices = {}
        instruments = [f"{pos['exchange']}:{pos['tradingsymbol']}" for pos in positions]
        
        try:
            # Try quote API first (more likely to be available)
            quote_data = self.kite.quote(instruments)
            for key, data in quote_data.items():
                live_prices[key] = data['last_price']
        except Exception as e:
            logger.warning(f"Quote API not available: {e}")
            # Fallback to positions data
            pass
        
        for i, pos in enumerate(positions, 1):
            side = "🟢 LONG" if pos['quantity'] > 0 else "🔴 SHORT"
            
            # Get best available LTP
            instrument_key = f"{pos['exchange']}:{pos['tradingsymbol']}"
            if instrument_key in live_prices:
                live_ltp = live_prices[instrument_key]
                # Recalculate P&L with live data
                pnl = (live_ltp - pos['average_price']) * pos['quantity']
                ltp_source = "🔴"  # Live indicator
            else:
                # Use positions data (may be delayed)
                live_ltp = pos['last_price']
                pnl = pos['pnl']
                ltp_source = "⏱️"  # Delayed indicator
            
            pnl_emoji = "✅" if pnl >= 0 else "❌"
            
            message += (
                f"{i}. {pos['tradingsymbol']}\n"
                f"   {side} | Qty: {abs(pos['quantity'])}\n"
                f"   Avg: ₹{pos['average_price']:.2f} | LTP: ₹{live_ltp:.2f} {ltp_source}\n"
                f"   {pnl_emoji} P&L: ₹{pnl:.2f}\n\n"
            )
        
        message += "\n🔴 = Live | ⏱️ = Delayed (refresh for update)"
        update.message.reply_text(message)
    
    def close_command(self, update: Update, context: CallbackContext):
        """Initiate close all positions"""
        positions = self.get_open_positions()
        
        if not positions:
            update.message.reply_text("📭 No open positions to close")
            return
        
        day_pnl, _ = self.get_total_pnl()
        
        message = (
            f"⚠️ **CLOSE ALL POSITIONS?**\n\n"
            f"Current Day P&L: ₹{day_pnl:,.2f}\n"
            f"Open Positions: {len(positions)}\n\n"
            f"This will close all positions immediately!"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("✅ YES, CLOSE ALL", callback_data='close_all_execute'),
                InlineKeyboardButton("❌ CANCEL", callback_data='close_all_cancel')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        update.message.reply_text(message, reply_markup=reply_markup)
    
    def button_handler(self, update: Update, context: CallbackContext):
        """Handle button clicks"""
        query = update.callback_query
        query.answer()
        
        if query.data == 'detailed_pnl':
            self.pnl_command_callback(query)
        elif query.data == 'show_positions':
            self.positions_command_callback(query)
        elif query.data == 'close_all_confirm':
            self.close_command_callback(query)
        elif query.data == 'close_all_execute':
            self.execute_close_all(query)
        elif query.data == 'close_all_cancel':
            query.edit_message_text("❌ Close all cancelled")
        elif query.data == 'killswitch_confirm':
            self.killswitch_confirm_callback(query)
        elif query.data == 'killswitch_activate':
            self.execute_killswitch(query)
        elif query.data == 'killswitch_cancel':
            query.edit_message_text("❌ Kill switch cancelled")
        elif query.data.startswith('sync_capital_'):
            self.sync_capital_callback(query)
        elif query.data == 'segments_menu_deactivate':
            self.show_segment_selector(query, action='deactivate')
        elif query.data == 'segments_menu_activate':
            self.show_segment_selector(query, action='activate')
        elif query.data == 'segments_deactivate_all':
            self.confirm_all_segments(query, action='deactivate')
        elif query.data == 'segments_activate_all':
            self.confirm_all_segments(query, action='activate')
        elif query.data.startswith('segment_deactivate_'):
            segment = query.data.replace('segment_deactivate_', '')
            self.toggle_segment(query, segment, activate=False)
        elif query.data.startswith('segment_activate_'):
            segment = query.data.replace('segment_activate_', '')
            self.toggle_segment(query, segment, activate=True)
        elif query.data == 'segments_deactivate_all_confirm':
            self.execute_segments_deactivation(query)
        elif query.data == 'segments_activate_all_confirm':
            self.execute_segments_activation(query)
        elif query.data == 'segments_back':
            self.segments_menu_callback(query)
        elif query.data == 'monitor_start':
            self.start_monitor_callback(query)
        elif query.data == 'monitor_stop':
            self.stop_monitor_callback(query)
        elif query.data.startswith('cons_execute_'):
            self.execute_consolidation_setup(query, context)
        elif query.data.startswith('cons_details_'):
            self.show_consolidation_details(query, context)
        elif query.data.startswith('cons_cancel_'):
            query.edit_message_text("❌ Consolidation trade cancelled")
        elif query.data.startswith('index_trade_'):
            self.execute_index_trade(query, context)
        elif query.data == 'index_refresh':
            self.refresh_index_analysis(query, context)
        elif query.data == 'index_compare':
            self.compare_indices(query, context)
        elif query.data == 'index_best_refresh':
            self.refresh_best_trade(query, context)
        elif query.data == 'logout_execute':
            self.execute_logout(query)
        elif query.data == 'logout_cancel':
            query.edit_message_text("❌ Logout cancelled")
        elif query.data == 'auto_ks_confirm':
            self.auto_ks_confirm_callback(query)
        elif query.data == 'auto_ks_cancel':
            self.auto_ks_cancel_callback(query)
    
    def pnl_command_callback(self, query):
        """Detailed P&L from button"""
        day_pnl, net_pnl = self.get_total_pnl()
        positions = self.get_open_positions()
        
        status_emoji = "🟢" if day_pnl >= 0 else "🔴"
        pnl_percent = (day_pnl / self.capital) * 100
        
        message = (
            f"{status_emoji} **DETAILED P&L**\n\n"
            f"Day P&L: ₹{day_pnl:,.2f} ({pnl_percent:+.2f}%)\n"
            f"Net P&L: ₹{net_pnl:,.2f}\n"
            f"Capital: ₹{self.capital:,}\n"
            f"Open: {len(positions)}\n"
            f"Time: {datetime.now().strftime('%H:%M:%S')}"
        )
        
        query.edit_message_text(message)
    
    def positions_command_callback(self, query):
        """Show positions from button"""
        positions = self.get_open_positions()
        
        if not positions:
            query.edit_message_text("📭 No open positions")
            return
        
        message = f"📊 **OPEN POSITIONS** ({len(positions)})\n\n"
        
        for pos in positions:
            side = "LONG" if pos['quantity'] > 0 else "SHORT"
            message += f"• {pos['tradingsymbol']}: {side} {abs(pos['quantity'])} | P&L: ₹{pos['pnl']:.2f}\n"
        
        query.edit_message_text(message)
    
    def close_command_callback(self, query):
        """Close all confirmation from button"""
        positions = self.get_open_positions()
        
        if not positions:
            query.edit_message_text("📭 No open positions")
            return
        
        day_pnl, _ = self.get_total_pnl()
        
        message = (
            f"⚠️ **CLOSE ALL?**\n\n"
            f"Day P&L: ₹{day_pnl:,.2f}\n"
            f"Positions: {len(positions)}\n"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("✅ YES", callback_data='close_all_execute'),
                InlineKeyboardButton("❌ NO", callback_data='close_all_cancel')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        query.edit_message_text(message, reply_markup=reply_markup)
    
    def execute_close_all(self, query):
        """Execute close all positions"""
        positions = self.get_open_positions()
        
        if not positions:
            query.edit_message_text("📭 No positions to close")
            return
        
        query.edit_message_text("🔄 Closing all positions...")
        
        success_count = 0
        for pos in positions:
            try:
                transaction_type = "SELL" if pos['quantity'] > 0 else "BUY"
                order_id = self.kite.place_order(
                    variety=self.kite.VARIETY_REGULAR,
                    exchange=pos['exchange'],
                    tradingsymbol=pos['tradingsymbol'],
                    transaction_type=transaction_type,
                    quantity=abs(pos['quantity']),
                    product=pos['product'],
                    order_type=self.kite.ORDER_TYPE_MARKET
                )
                success_count += 1
            except Exception as e:
                logger.error(f"Failed to close {pos['tradingsymbol']}: {e}")
        
        day_pnl, _ = self.get_total_pnl()
        
        message = (
            f"✅ **POSITIONS CLOSED**\n\n"
            f"Closed: {success_count}/{len(positions)}\n"
            f"Final Day P&L: ₹{day_pnl:,.2f}\n"
            f"Time: {datetime.now().strftime('%H:%M:%S')}"
        )
        
        query.edit_message_text(message)
    
    def execute_logout(self, query):
        """Execute logout - invalidate session"""
        query.edit_message_text("🔄 Logging out...")
        
        try:
            import os
            token_path = os.path.join(config.BASE_DIR, "access_token.txt")
            
            # Try to invalidate session with Kite API
            token_invalidated = False
            if os.path.exists(token_path):
                try:
                    with open(token_path, 'r') as f:
                        access_token = f.read().strip()
                    
                    if access_token:
                        from kiteconnect import KiteConnect
                        kite_logout = KiteConnect(api_key=config.API_KEY)
                        kite_logout.set_access_token(access_token)
                        kite_logout.invalidate_access_token()
                        token_invalidated = True
                        logger.info("Session invalidated on Kite servers")
                except Exception as e:
                    logger.warning(f"Could not invalidate on Kite: {e}")
                
                # Delete local token file
                try:
                    os.remove(token_path)
                    logger.info("Access token file deleted")
                except Exception as e:
                    logger.error(f"Failed to delete token: {e}")
            
            message = (
                f"✅ **LOGGED OUT**\n\n"
                f"Time: {datetime.now().strftime('%H:%M:%S')}\n"
                f"Session: {'Invalidated' if token_invalidated else 'Token removed'}\n\n"
                f"⚠️ **Bot will stop shortly**\n\n"
                f"**To restart:**\n"
                f"1. Login manually:\n"
                f"   `python auto_login.py`\n\n"
                f"2. Restart service:\n"
                f"   `sudo systemctl restart kite-trading-bot`\n\n"
                f"**Note:** Auto-login via service doesn't work\n"
                f"due to Chrome display requirements.\n"
                f"Use cron for daily auto-login at 9:10 AM."
            )
            
            query.edit_message_text(message)
            
            # Stop the bot after a delay
            import threading
            def stop_bot():
                import time
                time.sleep(5)
                logger.info("Stopping bot after logout...")
                import os
                os._exit(0)
            
            threading.Thread(target=stop_bot, daemon=True).start()
            
        except Exception as e:
            logger.error(f"Logout error: {e}")
            query.edit_message_text(f"❌ Logout failed: {e}")
    
    def killswitch_command(self, update: Update, context: CallbackContext):
        """Kill switch status and activation"""
        day_pnl, _ = self.get_total_pnl()
        positions = self.get_open_positions()
        
        message = f"🚨 **KILL SWITCH STATUS**\n\n"
        
        # Check conditions
        if day_pnl < -self.max_loss_threshold:
            message += f"🔴 **ACTIVATED** - Max loss exceeded!\n"
            message += f"Loss: ₹{day_pnl:,.2f} (Limit: {self.loss_display})\n"
        elif day_pnl < 0:
            remaining = self.max_loss_threshold - abs(day_pnl)
            message += f"🟡 **MONITORING**\n"
            message += f"Loss: ₹{day_pnl:,.2f}\n"
            message += f"Remaining: ₹{remaining:,.2f} until activation\n"
        elif day_pnl >= self.profit_threshold:
            message += f"🟢 **PROFIT WARNING**\n"
            message += f"Profit: ₹{day_pnl:,.2f} (>{self.profit_display})\n"
            message += f"Consider booking profits!\n"
        else:
            message += f"🟢 **SAFE**\n"
            message += f"P&L: ₹{day_pnl:,.2f}\n"
        
        message += f"\nOpen Positions: {len(positions)}\n"
        
        if positions:
            keyboard = [[InlineKeyboardButton("⚡ ACTIVATE KILL SWITCH", callback_data='killswitch_confirm')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            update.message.reply_text(message, reply_markup=reply_markup)
        else:
            update.message.reply_text(message)
    
    def auto_ks_confirm_callback(self, query):
        """User confirmed auto kill switch"""
        ks = get_global_kill_switch()
        ks._ks_confirmed = True
        ks._ks_confirm_event.set()
        query.edit_message_text("⚡ Confirmed — closing all positions now...")

    def auto_ks_cancel_callback(self, query):
        """User cancelled auto kill switch"""
        ks = get_global_kill_switch()
        ks._ks_confirmed = False
        ks._ks_confirm_event.set()
        query.edit_message_text("✅ Auto kill switch cancelled. Monitoring continues.")

    def reactivate_command(self, update: Update, context: CallbackContext):
        """Reactivate trading after kill switch"""
        try:
            ks = get_global_kill_switch()
            logger.info(f"Reactivate command using global instance: {id(ks)}")

            if not ks.is_active:
                update.message.reply_text(
                    "ℹ️ Kill switch is not active.\n"
                    "Trading is already enabled."
                )
                return

            # Deactivate kill switch
            ks.deactivate()

            message = (
                "✅ **KILL SWITCH DEACTIVATED**\n\n"
                "Bot can trade again.\n\n"
                "⚠️ **IMPORTANT:**\n"
                "Reactivate F&O segment on Zerodha Console:\n"
                "https://console.zerodha.com/account/segment-activation\n\n"
                "Check status: /killswitch"
            )

            update.message.reply_text(message)

        except Exception as e:
            logger.error(f"Reactivate error: {e}")
            update.message.reply_text(f"❌ Error: {e}")

    
    def segments_command(self, update: Update, context: CallbackContext):
        """Show segment management menu"""
        message = (
            "🔒 **SEGMENT MANAGEMENT**\n\n"
            "Choose an action:"
        )
        
        keyboard = [
            [InlineKeyboardButton("🔒 Deactivate Segments", callback_data='segments_menu_deactivate')],
            [InlineKeyboardButton("✅ Activate Segments", callback_data='segments_menu_activate')],
            [InlineKeyboardButton("🔒 Deactivate ALL", callback_data='segments_deactivate_all')],
            [InlineKeyboardButton("✅ Activate ALL", callback_data='segments_activate_all')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        update.message.reply_text(message, reply_markup=reply_markup)
    
    def segments_menu_callback(self, query):
        """Show segment management menu from callback"""
        message = (
            "🔒 **SEGMENT MANAGEMENT**\n\n"
            "Choose an action:"
        )
        
        keyboard = [
            [InlineKeyboardButton("🔒 Deactivate Segments", callback_data='segments_menu_deactivate')],
            [InlineKeyboardButton("✅ Activate Segments", callback_data='segments_menu_activate')],
            [InlineKeyboardButton("🔒 Deactivate ALL", callback_data='segments_deactivate_all')],
            [InlineKeyboardButton("✅ Activate ALL", callback_data='segments_activate_all')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        query.edit_message_text(message, reply_markup=reply_markup)
    
    def capital_command(self, update: Update, context: CallbackContext):
        """Show capital and margin info with option to sync from Kite"""
        try:
            margins = self.kite.margins()
            equity = margins['equity']
            
            available = equity['available']['live_balance']
            used = equity['utilised']['debits']
            total = equity['net']
            
            message = (
                f"💰 **CAPITAL STATUS**\n\n"
                f"📊 **Kite Account:**\n"
                f"Available: ₹{available:,.2f}\n"
                f"Used: ₹{used:,.2f}\n"
                f"Total: ₹{total:,.2f}\n\n"
                f"⚙️ **Bot Configuration:**\n"
                f"Configured Capital: ₹{self.capital:,}\n"
                f"Loss Threshold: {self.loss_display}\n"
                f"Profit Threshold: {self.profit_display}\n"
                f"Drawdown Threshold: {self.drawdown_display}\n\n"
                f"💡 Use /setcapital <amount> to update capital\n"
                f"Example: /setcapital 30000"
            )
            
            # Add button to sync from Kite
            keyboard = [[InlineKeyboardButton("🔄 Sync from Kite Account", callback_data=f'sync_capital_{int(available)}')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            update.message.reply_text(message, reply_markup=reply_markup)
        except Exception as e:
            update.message.reply_text(f"❌ Error fetching capital: {e}")
    
    def setcapital_command(self, update: Update, context: CallbackContext):
        """Set trading capital and recalculate thresholds"""
        if not context.args:
            update.message.reply_text(
                "❌ Please provide capital amount\n\n"
                "Usage: /setcapital <amount>\n"
                "Example: /setcapital 30000\n\n"
                "Or use /capital to sync from Kite account"
            )
            return
        
        try:
            new_capital = float(context.args[0])
            if new_capital <= 0:
                update.message.reply_text("❌ Capital must be greater than 0")
                return
            
            old_capital = self.capital
            self.capital = new_capital
            
            # Recalculate thresholds
            if config.LOSS_THRESHOLD_PERCENT > 0:
                self.max_loss_threshold = (config.LOSS_THRESHOLD_PERCENT / 100) * self.capital
                self.loss_display = f"{config.LOSS_THRESHOLD_PERCENT}% (₹{self.max_loss_threshold:,.0f})"
            
            if config.PROFIT_THRESHOLD_PERCENT > 0:
                self.profit_threshold = (config.PROFIT_THRESHOLD_PERCENT / 100) * self.capital
                self.profit_display = f"{config.PROFIT_THRESHOLD_PERCENT}% (₹{self.profit_threshold:,.0f})"
            
            # Drawdown doesn't change with capital (it's % of peak profit, not capital)
            # But update display for consistency
            if config.DRAWDOWN_THRESHOLD_PERCENT > 0:
                self.drawdown_percent = config.DRAWDOWN_THRESHOLD_PERCENT
                self.drawdown_display = f"{config.DRAWDOWN_THRESHOLD_PERCENT}% of peak"
            
            message = (
                f"✅ **CAPITAL UPDATED**\n\n"
                f"Old Capital: ₹{old_capital:,}\n"
                f"New Capital: ₹{self.capital:,}\n\n"
                f"📊 **Updated Thresholds:**\n"
                f"Loss Threshold: {self.loss_display}\n"
                f"Profit Threshold: {self.profit_display}\n"
                f"Drawdown Threshold: {self.drawdown_display}\n\n"
                f"⚠️ Note: This change is temporary.\n"
                f"To make it permanent, update CAPITAL in .env file"
            )
            update.message.reply_text(message)
            
        except ValueError:
            update.message.reply_text("❌ Invalid amount. Please provide a number.")
    
    def sync_capital_callback(self, query):
        """Sync capital from Kite account"""
        try:
            # Extract capital from callback data
            new_capital = int(query.data.replace('sync_capital_', ''))
            old_capital = self.capital
            self.capital = new_capital
            
            # Recalculate thresholds
            if config.LOSS_THRESHOLD_PERCENT > 0:
                self.max_loss_threshold = (config.LOSS_THRESHOLD_PERCENT / 100) * self.capital
                self.loss_display = f"{config.LOSS_THRESHOLD_PERCENT}% (₹{self.max_loss_threshold:,.0f})"
            
            if config.PROFIT_THRESHOLD_PERCENT > 0:
                self.profit_threshold = (config.PROFIT_THRESHOLD_PERCENT / 100) * self.capital
                self.profit_display = f"{config.PROFIT_THRESHOLD_PERCENT}% (₹{self.profit_threshold:,.0f})"
            
            # Drawdown doesn't change with capital (it's % of peak profit, not capital)
            if config.DRAWDOWN_THRESHOLD_PERCENT > 0:
                self.drawdown_percent = config.DRAWDOWN_THRESHOLD_PERCENT
                self.drawdown_display = f"{config.DRAWDOWN_THRESHOLD_PERCENT}% of peak"
            
            message = (
                f"✅ **CAPITAL SYNCED FROM KITE**\n\n"
                f"Old Capital: ₹{old_capital:,}\n"
                f"New Capital: ₹{self.capital:,}\n\n"
                f"📊 **Updated Thresholds:**\n"
                f"Loss Threshold: {self.loss_display}\n"
                f"Profit Threshold: {self.profit_display}\n"
                f"Drawdown Threshold: {self.drawdown_display}\n\n"
                f"⚠️ Note: This change is temporary.\n"
                f"To make it permanent, update CAPITAL in .env file"
            )
            query.edit_message_text(message)
            
        except Exception as e:
            query.edit_message_text(f"❌ Error syncing capital: {e}")
    
    def risk_command(self, update: Update, context: CallbackContext):
        """Show risk metrics"""
        day_pnl, _ = self.get_total_pnl()
        positions = self.get_open_positions()
        
        pnl_percent = (day_pnl / self.capital) * 100
        max_loss_pct = (self.max_loss_threshold / self.capital) * 100
        
        message = (
            f"⚠️ **RISK METRICS**\n\n"
            f"Day P&L: ₹{day_pnl:,.2f} ({pnl_percent:+.2f}%)\n"
            f"Max Loss: {self.loss_display} ({max_loss_pct:.1f}%)\n"
            f"Open Positions: {len(positions)}\n\n"
        )
        
        if day_pnl < 0:
            risk_used = abs(day_pnl) / self.max_loss_threshold * 100
            message += f"Risk Used: {risk_used:.1f}%\n"
        
        update.message.reply_text(message)
    
    def scan_command(self, update: Update, context: CallbackContext):
        """Manual scan trigger - Enhanced with CE/PE and ATM/ITM strikes"""
        update.message.reply_text("🔍 Scanning for setups...")
        
        try:
            from enhanced_scanner import enhanced_scanner
            
            signals = enhanced_scanner.scan()
            
            if not signals:
                update.message.reply_text(
                    "📊 **SCAN COMPLETE**\n\n"
                    "No trading signals found.\n"
                    "Market conditions not favorable."
                )
                return
            
            message = f"📊 **SCAN RESULTS**\n\n"
            message += f"Found {len(signals)} signal(s):\n\n"
            
            for i, signal in enumerate(signals, 1):
                direction_emoji = "📈" if signal['direction'] == 'BULLISH' else "📉"
                message += (
                    f"{direction_emoji} **{signal['index']}** ({signal['exchange']})\n"
                    f"Direction: {signal['direction']}\n"
                    f"Option: {signal['option_type']}\n"
                    f"Spot: ₹{signal['spot_price']:.2f}\n"
                    f"ATM Strike: {signal['strikes']['ATM']}\n"
                    f"ITM Strike: {signal['strikes']['ITM']}\n"
                    f"Confidence: {signal['confidence']}%\n"
                    f"Stop Loss: ₹{signal['stop_loss']:.2f}\n\n"
                )
            
            update.message.reply_text(message)
            
        except Exception as e:
            logger.error(f"Scan error: {e}")
            update.message.reply_text(f"❌ Scan failed: {e}")
    
    def consolidation_command(self, update: Update, context: CallbackContext):
        """Check for consolidation setups"""
        update.message.reply_text("📊 Scanning for consolidations...")
        
        try:
            from consolidation_breakout_scanner import ConsolidationBreakoutScanner
            
            scanner = ConsolidationBreakoutScanner()
            
            # Get NIFTY current level for strike selection
            # You can make this configurable
            symbols_to_scan = [
                ('NIFTY', 25200, 'PE'),
                ('NIFTY', 25200, 'CE'),
                ('BANKNIFTY', 54000, 'PE'),
                ('BANKNIFTY', 54000, 'CE'),
            ]
            
            found_setups = []
            
            for symbol, strike, option_type in symbols_to_scan:
                setup = scanner.scan_for_setup(symbol, strike, option_type)
                if setup:
                    found_setups.append(setup)
            
            if not found_setups:
                update.message.reply_text(
                    "📊 **CONSOLIDATION SCAN COMPLETE**\n\n"
                    "No consolidation breakouts found.\n\n"
                    "Looking for:\n"
                    "• Tight range < 15%\n"
                    "• 6+ candles (18+ min)\n"
                    "• Breakout > 10% above range"
                )
                return
            
            message = f"🚀 **CONSOLIDATION BREAKOUTS FOUND**\n\n"
            message += f"Found {len(found_setups)} setup(s):\n\n"
            
            for i, setup in enumerate(found_setups, 1):
                message += (
                    f"{i}. {setup['symbol']} {setup['strike']} {setup['option_type']}\n"
                    f"   Entry: ₹{setup['entry_price']:.2f}\n"
                    f"   Stop: ₹{setup['stop_loss']:.2f}\n"
                    f"   Strength: {setup['breakout_strength']:.1f}%\n"
                    f"   Duration: {setup['consolidation_duration']} candles\n\n"
                )
            
            # Add action buttons for first setup
            if found_setups:
                keyboard = [
                    [InlineKeyboardButton("✅ Execute First Setup", callback_data=f'cons_execute_0')],
                    [InlineKeyboardButton("📊 View Details", callback_data=f'cons_details_0')]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                update.message.reply_text(message, reply_markup=reply_markup)
                
                # Store setups in context for later use
                context.bot_data['consolidation_setups'] = found_setups
            else:
                update.message.reply_text(message)
            
        except Exception as e:
            logger.error(f"Consolidation scan error: {e}")
            update.message.reply_text(f"❌ Consolidation scan failed: {e}")
    
    def analyze_command(self, update: Update, context: CallbackContext):
        """Analyze all indices (SENSEX, NIFTY, BANK NIFTY)"""
        update.message.reply_text("📊 Analyzing SENSEX, NIFTY 50, and BANK NIFTY...")
        
        try:
            from index_analyzer import index_analyzer
            
            # Analyze all indices
            results = index_analyzer.analyze_all_indices()
            
            if not results:
                update.message.reply_text(
                    "❌ **ANALYSIS FAILED**\n\n"
                    "Could not fetch data for indices.\n"
                    "Please try again later."
                )
                return
            
            # Format report
            report = index_analyzer.format_analysis_report(results)
            
            # Add action buttons for best trade
            best = results[0]
            keyboard = [
                [InlineKeyboardButton(
                    f"✅ Trade {best['option_symbol']} {best['option_type']} {best['suggested_strike']}", 
                    callback_data=f'index_trade_{best["option_symbol"]}_{best["option_type"]}_{best["suggested_strike"]}'
                )],
                [InlineKeyboardButton("🔄 Refresh Analysis", callback_data='index_refresh')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            update.message.reply_text(report, reply_markup=reply_markup)
            
            # Store results in context
            context.bot_data['index_analysis'] = results
            
        except Exception as e:
            logger.error(f"Index analysis error: {e}")
            update.message.reply_text(f"❌ Analysis failed: {e}")
    
    def best_trade_command(self, update: Update, context: CallbackContext):
        """Get the single best trading opportunity"""
        update.message.reply_text("🎯 Finding best trading opportunity...")
        
        try:
            from index_analyzer import index_analyzer
            
            # Get best trade
            best = index_analyzer.get_best_trade()
            
            if not best:
                update.message.reply_text(
                    "❌ **NO OPPORTUNITIES**\n\n"
                    "Could not find any trading opportunities.\n"
                    "Market conditions may not be favorable."
                )
                return
            
            # Format message
            score_emoji = "🔥" if best['score'] >= 70 else "✅" if best['score'] >= 50 else "⚠️"
            
            message = (
                f"{score_emoji} **BEST TRADING OPPORTUNITY**\n\n"
                f"**Index:** {best['index']}\n"
                f"**Trade:** {best['option_symbol']} {best['option_type']} {best['suggested_strike']}\n"
                f"**Score:** {best['score']:.0f}/100\n\n"
                f"**Analysis:**\n"
                f"• Current Price: ₹{best['current_price']:.2f}\n"
                f"• 1H Change: {best['change_1h']:+.2f}%\n"
                f"• 1D Change: {best['change_1d']:+.2f}%\n"
                f"• Trend: {best['trend']} ({best['trend_strength']})\n"
                f"• Volatility: {best['atr_pct']:.2f}%\n"
                f"• Volume: {best['volume_ratio']:.2f}x average\n"
                f"• Range Position: {best['range_position']:.0f}%\n\n"
                f"**Trade Details:**\n"
                f"• Lot Size: {best['lot_size']}\n"
                f"• Strike: {best['suggested_strike']}\n"
                f"• Type: {best['option_type']}\n\n"
            )
            
            # Add reasoning
            if best['score'] >= 70:
                message += "✅ **Strong Setup** - High conviction trade\n"
            elif best['score'] >= 50:
                message += "🟡 **Moderate Setup** - Decent opportunity\n"
            else:
                message += "⚠️ **Weak Setup** - Low conviction, trade carefully\n"
            
            # Add action buttons
            keyboard = [
                [InlineKeyboardButton(
                    f"✅ Execute Trade", 
                    callback_data=f'index_trade_{best["option_symbol"]}_{best["option_type"]}_{best["suggested_strike"]}'
                )],
                [InlineKeyboardButton("📊 Compare All Indices", callback_data='index_compare')],
                [InlineKeyboardButton("🔄 Refresh", callback_data='index_best_refresh')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            update.message.reply_text(message, reply_markup=reply_markup)
            
            # Store in context
            context.bot_data['best_trade'] = best
            
        except Exception as e:
            logger.error(f"Best trade error: {e}")
            update.message.reply_text(f"❌ Failed to find best trade: {e}")
    
    def paper_command(self, update: Update, context: CallbackContext):
        """Paper trading status"""
        try:
            import json
            import os
            
            if os.path.exists('paper_trades.json'):
                with open('paper_trades.json', 'r') as f:
                    data = json.load(f)
                
                capital = data.get('capital', 40000)
                starting = data.get('starting_capital', 40000)
                trades = data.get('trades', [])
                open_pos = data.get('open_positions', [])
                
                pnl = capital - starting
                roi = (pnl / starting) * 100
                
                message = (
                    f"📝 **PAPER TRADING STATUS**\n\n"
                    f"Starting: ₹{starting:,.2f}\n"
                    f"Current: ₹{capital:,.2f}\n"
                    f"P&L: ₹{pnl:+,.2f} ({roi:+.2f}%)\n\n"
                    f"Total Trades: {len(trades)}\n"
                    f"Open Positions: {len(open_pos)}\n"
                )
            else:
                message = "📝 No paper trading data found.\n\nRun: python paper_trading.py"
            
            update.message.reply_text(message)
        except Exception as e:
            update.message.reply_text(f"❌ Error: {e}")
    
    def paper_trades_command(self, update: Update, context: CallbackContext):
        """Show paper trade history"""
        try:
            import json
            import os
            
            if os.path.exists('paper_trades.json'):
                with open('paper_trades.json', 'r') as f:
                    data = json.load(f)
                
                trades = data.get('trades', [])
                
                if not trades:
                    update.message.reply_text("📝 No paper trades yet")
                    return
                
                # Show last 5 trades
                recent = trades[-5:]
                message = f"📝 **RECENT PAPER TRADES** (Last 5)\n\n"
                
                for trade in recent:
                    emoji = "✅" if trade.get('final_pnl', 0) > 0 else "❌"
                    message += (
                        f"{emoji} #{trade['id']}: {trade['symbol']} {trade['strike']} {trade['option_type']}\n"
                        f"   P&L: ₹{trade.get('final_pnl', 0):+,.2f} | {trade.get('exit_reason', 'N/A')}\n\n"
                    )
                
                update.message.reply_text(message)
            else:
                update.message.reply_text("📝 No paper trading data")
        except Exception as e:
            update.message.reply_text(f"❌ Error: {e}")
    
    def orders_command(self, update: Update, context: CallbackContext):
        """Show today's orders"""
        try:
            orders = self.kite.orders()
            
            if not orders:
                update.message.reply_text("📋 No orders today")
                return
            
            message = f"📋 **TODAY'S ORDERS** ({len(orders)})\n\n"
            
            for order in orders[-5:]:  # Last 5 orders
                status_emoji = "✅" if order['status'] == 'COMPLETE' else "⏳" if order['status'] == 'OPEN' else "❌"
                message += (
                    f"{status_emoji} {order['tradingsymbol']}\n"
                    f"   {order['transaction_type']} {order['quantity']} @ ₹{order.get('average_price', order['price']):.2f}\n"
                    f"   Status: {order['status']}\n\n"
                )
            
            update.message.reply_text(message)
        except Exception as e:
            update.message.reply_text(f"❌ Error: {e}")
    
    def history_command(self, update: Update, context: CallbackContext):
        """Trade history"""
        update.message.reply_text(
            "📊 **TRADE HISTORY**\n\n"
            "Use /orders for today's orders\n"
            "Use /pnl for current P&L\n"
            "Use /papertrades for paper trading history"
        )
    
    def bot_status_command(self, update: Update, context: CallbackContext):
        """Bot system status"""
        import psutil
        import platform
        
        cpu = psutil.cpu_percent()
        memory = psutil.virtual_memory().percent
        
        message = (
            f"🤖 **BOT STATUS**\n\n"
            f"Status: ✅ Running\n"
            f"Platform: {platform.system()}\n"
            f"CPU: {cpu}%\n"
            f"Memory: {memory}%\n"
            f"Time: {datetime.now().strftime('%H:%M:%S')}\n"
        )
        
        update.message.reply_text(message)
    
    def time_command(self, update: Update, context: CallbackContext):
        """Current time"""
        now = datetime.now()
        market_open = now.replace(hour=9, minute=15, second=0)
        market_close = now.replace(hour=15, minute=30, second=0)
        
        is_open = market_open <= now <= market_close
        status = "🟢 OPEN" if is_open else "🔴 CLOSED"
        
        message = (
            f"🕐 **TIME**\n\n"
            f"Current: {now.strftime('%d-%b-%Y %H:%M:%S')}\n"
            f"Market: {status}\n"
        )
        
        if not is_open:
            if now < market_open:
                time_to_open = (market_open - now).seconds // 60
                message += f"Opens in: {time_to_open} minutes\n"
            else:
                message += f"Closed for the day\n"
        
        update.message.reply_text(message)
    
    def reconnect_command(self, update: Update, context: CallbackContext):
        """Reconnect/refresh Kite session"""
        update.message.reply_text("🔄 Reinitializing Kite session...")
        
        try:
            # Force reinitialize
            success = self.initialize_kite_session()
            
            if success:
                # Test with a P&L fetch
                day_pnl, net_pnl = self.get_total_pnl()
                positions = self.get_open_positions()
                
                message = (
                    f"✅ **SESSION RECONNECTED**\n\n"
                    f"Day P&L: ₹{day_pnl:,.2f}\n"
                    f"Net P&L: ₹{net_pnl:,.2f}\n"
                    f"Open Positions: {len(positions)}\n"
                    f"Time: {datetime.now().strftime('%H:%M:%S')}\n\n"
                    f"Session is now active and working!"
                )
            else:
                message = (
                    f"❌ **RECONNECTION FAILED**\n\n"
                    f"Could not initialize Kite session.\n\n"
                    f"Possible issues:\n"
                    f"• Access token invalid or expired\n"
                    f"• Network connectivity\n"
                    f"• Kite API down\n\n"
                    f"Try:\n"
                    f"1. Check if access_token.txt exists\n"
                    f"2. Restart service: `sudo systemctl restart kite-trading-bot`\n"
                    f"3. Manual login: `python auto_login.py`"
                )
            
            update.message.reply_text(message)
            
        except Exception as e:
            logger.error(f"Reconnect error: {e}")
            update.message.reply_text(f"❌ Reconnection failed: {e}")
    
    def logout_command(self, update: Update, context: CallbackContext):
        """Logout and invalidate session"""
        message = (
            "⚠️ **LOGOUT CONFIRMATION**\n\n"
            "This will:\n"
            "• Invalidate current access token\n"
            "• Stop the bot temporarily\n"
            "• Require service restart to auto-login\n\n"
            "Use this to test if auto-login works on service restart.\n\n"
            "Proceed with logout?"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("✅ YES, LOGOUT", callback_data='logout_execute'),
                InlineKeyboardButton("❌ CANCEL", callback_data='logout_cancel')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        update.message.reply_text(message, reply_markup=reply_markup)

    
    def killswitch_confirm_callback(self, query):
        """Kill switch confirmation from button"""
        positions = self.get_open_positions()
        day_pnl, _ = self.get_total_pnl()
        
        message = (
            f"⚡ **ACTIVATE KILL SWITCH?**\n\n"
            f"⚠️ This will:\n"
        )
        
        if positions:
            message += f"1. Close all {len(positions)} position(s)\n"
        else:
            message += f"1. No positions to close\n"
        
        message += (
            f"2. Stop bot from trading\n"
            f"3. Deactivate F&O segment\n\n"
            f"Current Day P&L: ₹{day_pnl:,.2f}\n\n"
            f"⚠️ **This action cannot be undone!**"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("⚡ YES, ACTIVATE", callback_data='killswitch_activate'),
                InlineKeyboardButton("❌ CANCEL", callback_data='killswitch_cancel')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        query.edit_message_text(message, reply_markup=reply_markup)
    
    def execute_killswitch(self, query):
        """Execute kill switch using advanced_killswitch.py - works even without positions"""
        query.edit_message_text("⚡ Activating Kill Switch...")
        
        positions = self.get_open_positions()
        
        try:
            # Use the advanced kill switch system
            ks = get_global_kill_switch()
            logger.info(f"Killswitch command using global instance: {id(ks)}")
            
            # Analyze positions by exchange
            if positions:
                segments_to_disable, exchange_summary = ks.analyze_positions_by_exchange(positions)
                
                query.edit_message_text(
                    f"⚡ Activating Kill Switch...\n\n"
                    f"Detected positions:\n" + "\n".join([f"• {s}" for s in exchange_summary])
                )
            
            # Close positions if any exist
            if positions:
                query.edit_message_text(f"⚡ Closing {len(positions)} position(s)...")
                
                success_count = 0
                for pos in positions:
                    try:
                        transaction_type = "SELL" if pos['quantity'] > 0 else "BUY"
                        order_id = self.kite.place_order(
                            variety=self.kite.VARIETY_REGULAR,
                            exchange=pos['exchange'],
                            tradingsymbol=pos['tradingsymbol'],
                            transaction_type=transaction_type,
                            quantity=abs(pos['quantity']),
                            product=pos['product'],
                            order_type=self.kite.ORDER_TYPE_MARKET
                        )
                        success_count += 1
                        logger.info(f"Closed {pos['tradingsymbol']}: Order ID {order_id}")
                    except Exception as e:
                        logger.error(f"Failed to close {pos['tradingsymbol']}: {e}")
                
                position_status = f"✅ Closed {success_count}/{len(positions)} positions\n"
            else:
                position_status = "ℹ️ No open positions\n"
            
            # Deactivate relevant segments (smart detection)
            query.edit_message_text(f"{position_status}\n🔄 Deactivating trading segments...")
            
            if positions:
                segments_to_disable, exchange_summary = ks.analyze_positions_by_exchange(positions)
                segment_success, segment_message = ks.deactivate_segments(segments_to_disable)
            else:
                segment_success = True
                segment_message = "No segments needed deactivation"
                segments_to_disable = []
            
            # Mark kill switch as active
            ks.is_active = True
            ks.save_status(True, "Manual activation via Telegram")
            
            day_pnl, _ = self.get_total_pnl()
            
            message = (
                f"⚡ **KILL SWITCH ACTIVATED**\n\n"
                f"{position_status}"
                f"💰 Final Day P&L: ₹{day_pnl:,.2f}\n"
                f"🕐 Time: {datetime.now().strftime('%H:%M:%S')}\n\n"
            )
            
            if positions and exchange_summary:
                message += "**Position Breakdown:**\n"
                for summary in exchange_summary:
                    message += f"• {summary}\n"
                message += "\n"
            
            message += "**Actions Completed:**\n"
            
            if positions:
                message += f"1. ✅ Positions closed\n"
            else:
                message += f"1. ℹ️ No positions to close\n"
            
            message += f"2. ✅ Bot stopped trading\n"
            
            if segments_to_disable:
                if segment_success:
                    message += f"3. ✅ Segments deactivated: {', '.join(segments_to_disable)}\n\n"
                    message += f"🔒 Trading disabled on: {', '.join(segments_to_disable).upper()}\n\n"
                else:
                    message += f"3. ⚠️ {segment_message}\n\n"
                    message += f"**MANUAL ACTION REQUIRED:**\n"
                    message += f"Deactivate segments at:\n"
                    message += f"https://console.zerodha.com/account/segment-activation\n\n"
            else:
                message += f"3. ℹ️ No segments needed deactivation\n\n"
            
            message += f"To reactivate: Send /reactivate"
            
            query.edit_message_text(message)
            
            # Send notification
            try:
                from notifier import notifier
                notifier.send_message(
                    f"🚨 **KILL SWITCH ACTIVATED**\n\n"
                    f"Reason: Manual activation via Telegram\n"
                    f"{position_status}"
                    f"Final P&L: ₹{day_pnl:,.2f}\n"
                    f"Segments: {segment_message}\n"
                    f"Time: {datetime.now().strftime('%H:%M:%S')}"
                )
            except Exception as e:
                logger.error(f"Failed to send notification: {e}")
                
        except Exception as e:
            logger.error(f"Kill switch error: {e}")
            query.edit_message_text(
                f"❌ **KILL SWITCH ERROR**\n\n"
                f"Error: {str(e)}\n\n"
                f"**MANUAL ACTION REQUIRED:**\n"
                f"1. Close positions manually on Kite\n"
                f"2. Deactivate segments at:\n"
                f"https://console.zerodha.com/account/segment-activation"
            )
    
    def show_segment_selector(self, query, action='deactivate'):
        """Show segment selection menu"""
        action_text = "Deactivate" if action == 'deactivate' else "Activate"
        emoji = "🔒" if action == 'deactivate' else "✅"
        
        message = (
            f"{emoji} **{action_text.upper()} SEGMENTS**\n\n"
            f"Select segment to {action_text.lower()}:"
        )
        
        callback_prefix = f'segment_{action}_'
        
        keyboard = [
            [InlineKeyboardButton(f"{emoji} NSE Equity", callback_data=f'{callback_prefix}nse_equity')],
            [InlineKeyboardButton(f"{emoji} BSE Equity", callback_data=f'{callback_prefix}bse_equity')],
            [InlineKeyboardButton(f"{emoji} NSE F&O", callback_data=f'{callback_prefix}nfo')],
            [InlineKeyboardButton(f"{emoji} BSE F&O", callback_data=f'{callback_prefix}bfo')],
            [InlineKeyboardButton("« Back", callback_data='segments_back')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        query.edit_message_text(message, reply_markup=reply_markup)
    
    def confirm_all_segments(self, query, action='deactivate'):
        """Confirm activate/deactivate all segments"""
        action_text = "Deactivate" if action == 'deactivate' else "Activate"
        emoji = "🔒" if action == 'deactivate' else "✅"
        
        message = (
            f"{emoji} **{action_text.upper()} ALL SEGMENTS?**\n\n"
            f"This will {action_text.lower()}:\n"
            f"• NSE Equity\n"
            f"• BSE Equity\n"
            f"• NSE F&O (NFO)\n"
            f"• BSE F&O (BFO)\n\n"
        )
        
        if action == 'deactivate':
            message += "⚠️ No trading will be possible until reactivated!"
        else:
            message += "✅ All trading will be enabled!"
        
        callback_confirm = f'segments_{action}_all_confirm'
        
        keyboard = [
            [InlineKeyboardButton(f"{emoji} YES, {action_text.upper()} ALL", callback_data=callback_confirm)],
            [InlineKeyboardButton("❌ Cancel", callback_data='segments_back')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        query.edit_message_text(message, reply_markup=reply_markup)
    
    def toggle_segment(self, query, segment, activate=False):
        """Toggle a single segment"""
        action_text = "Activating" if activate else "Deactivating"
        
        segment_names = {
            'nse_equity': 'NSE Equity',
            'bse_equity': 'BSE Equity',
            'nfo': 'NSE F&O',
            'bfo': 'BSE F&O'
        }
        
        segment_name = segment_names.get(segment, segment)
        
        query.edit_message_text(f"{action_text} {segment_name}...")
        
        try:
            from segment_automation import ZerodhaSegmentAutomation
            
            automation = ZerodhaSegmentAutomation(headless=True)
            
            # Login using Selenium
            if not automation.login_to_zerodha_selenium():
                query.edit_message_text(f"❌ Login failed")
                automation.close()
                return
            
            # Navigate to segment page
            automation.driver.get("https://console.zerodha.com/account/segment-activation")
            import time
            time.sleep(3)
            
            if "login" in automation.driver.current_url.lower():
                query.edit_message_text(f"❌ Failed to navigate to segment page")
                automation.close()
                return
            
            # Map segment keys
            segment_map = {
                'nse_equity': 'equity',
                'bse_equity': 'bse_equity',
                'nfo': 'nfo',
                'bfo': 'bfo'
            }
            
            # Toggle segment
            success = automation.toggle_segment(segment_map[segment], activate=activate)
            
            if not success:
                automation.close()
                query.edit_message_text(f"❌ Failed to toggle {segment_name}")
                return
            
            # Click Continue button to save changes
            if not automation.click_continue_button():
                logger.warning("Could not click Continue button")
            
            automation.close()
            
            if success:
                emoji = "✅" if activate else "🔒"
                action_past = "activated" if activate else "deactivated"
                message = (
                    f"{emoji} **{segment_name.upper()} {action_past.upper()}**\n\n"
                    f"Status: {emoji} {action_past.capitalize()}\n"
                    f"Time: {datetime.now().strftime('%H:%M:%S')}\n\n"
                    f"Manage more segments: /segments"
                )
            else:
                message = (
                    f"⚠️ **{segment_name.upper()}**\n\n"
                    f"Status uncertain. Please check manually:\n"
                    f"https://console.zerodha.com/account/segment-activation"
                )
            
            query.edit_message_text(message)
            
            # Send notification
            try:
                from notifier import notifier
                notifier.send_message(
                    f"{'✅' if activate else '🔒'} **{segment_name} {action_past}**\n"
                    f"Time: {datetime.now().strftime('%H:%M:%S')}"
                )
            except Exception as e:
                logger.error(f"Failed to send notification: {e}")
                
        except Exception as e:
            logger.error(f"Segment toggle error: {e}")
            query.edit_message_text(
                f"❌ **ERROR**\n\n"
                f"Failed to {action_text.lower()} {segment_name}\n"
                f"Error: {str(e)}\n\n"
                f"Please try manually:\n"
                f"https://console.zerodha.com/account/segment-activation"
            )
    
    def execute_segments_deactivation(self, query):
        """Deactivate all trading segments"""
        query.edit_message_text("🔒 Deactivating all segments...")
        
        try:
            from deactivate_all_segments import deactivate_all_segments
            
            success_count, total_count, results = deactivate_all_segments(headless=True)
            
            message = (
                f"🔒 **SEGMENTS DEACTIVATION**\n\n"
                f"Completed: {success_count}/{total_count}\n\n"
            )
            
            # Show results for each segment
            segment_names = {
                'nse_equity': 'NSE Equity',
                'bse_equity': 'BSE Equity',
                'nfo': 'NSE F&O',
                'bfo': 'BSE F&O'
            }
            
            for segment_key, segment_name in segment_names.items():
                if segment_key in results:
                    status = "✅" if results[segment_key] else "❌"
                    message += f"{status} {segment_name}\n"
            
            message += f"\n🕐 Time: {datetime.now().strftime('%H:%M:%S')}\n\n"
            
            if success_count == total_count:
                message += "✅ All segments deactivated!\n"
                message += "🔒 No trading possible until reactivated."
            elif success_count > 0:
                message += f"⚠️ Partial success\n"
                message += f"Check manually at:\n"
                message += f"https://console.zerodha.com/account/segment-activation"
            else:
                message += f"❌ Deactivation failed\n"
                message += f"Deactivate manually at:\n"
                message += f"https://console.zerodha.com/account/segment-activation"
            
            query.edit_message_text(message)
            
            # Send notification
            try:
                from notifier import notifier
                notifier.send_message(
                    f"🔒 **SEGMENTS DEACTIVATED**\n\n"
                    f"Success: {success_count}/{total_count}\n"
                    f"Time: {datetime.now().strftime('%H:%M:%S')}"
                )
            except Exception as e:
                logger.error(f"Failed to send notification: {e}")
                
        except Exception as e:
            logger.error(f"Segments deactivation error: {e}")
            query.edit_message_text(
                f"❌ **SEGMENTS DEACTIVATION FAILED**\n\n"
                f"Error: {str(e)}\n\n"
                f"Please deactivate manually at:\n"
                f"https://console.zerodha.com/account/segment-activation"
            )
    
    def execute_segments_activation(self, query):
        """Activate all trading segments"""
        query.edit_message_text("✅ Activating all segments...")
        
        try:
            from segment_automation import ZerodhaSegmentAutomation
            
            segments = {
                'nse_equity': 'NSE Equity',
                'bse_equity': 'BSE Equity',
                'nfo': 'NSE F&O',
                'bfo': 'BSE F&O'
            }
            
            results = {}
            success_count = 0
            
            automation = ZerodhaSegmentAutomation(headless=True)
            
            # Login using Selenium
            if not automation.login_to_zerodha_selenium():
                query.edit_message_text("❌ Login failed")
                automation.close()
                return
            
            # Navigate to segment page
            automation.driver.get("https://console.zerodha.com/account/segment-activation")
            import time
            time.sleep(3)
            
            if "login" in automation.driver.current_url.lower():
                query.edit_message_text("❌ Failed to navigate to segment page")
                automation.close()
                return
            
            # Activate each segment
            segment_map = {
                'nse_equity': 'equity',
                'bse_equity': 'bse_equity',
                'nfo': 'nfo',
                'bfo': 'bfo'
            }
            
            for segment_key, segment_name in segments.items():
                try:
                    success = automation.toggle_segment(segment_map[segment_key], activate=True)
                    results[segment_key] = success
                    if success:
                        success_count += 1
                except Exception as e:
                    logger.error(f"Failed to activate {segment_name}: {e}")
                    results[segment_key] = False
            
            # Click Continue button to save all changes
            if not automation.click_continue_button():
                logger.warning("Could not click Continue button")
            
            automation.close()
            
            message = (
                f"✅ **SEGMENTS ACTIVATION**\n\n"
                f"Completed: {success_count}/{len(segments)}\n\n"
            )
            
            # Show results
            for segment_key, segment_name in segments.items():
                if segment_key in results:
                    status = "✅" if results[segment_key] else "❌"
                    message += f"{status} {segment_name}\n"
            
            message += f"\n🕐 Time: {datetime.now().strftime('%H:%M:%S')}\n\n"
            
            if success_count == len(segments):
                message += "✅ All segments activated!\n"
                message += "🟢 Trading is now enabled."
            elif success_count > 0:
                message += f"⚠️ Partial success\n"
                message += f"Check manually at:\n"
                message += f"https://console.zerodha.com/account/segment-activation"
            else:
                message += f"❌ Activation failed\n"
                message += f"Activate manually at:\n"
                message += f"https://console.zerodha.com/account/segment-activation"
            
            query.edit_message_text(message)
            
            # Send notification
            try:
                from notifier import notifier
                notifier.send_message(
                    f"✅ **SEGMENTS ACTIVATED**\n\n"
                    f"Success: {success_count}/{len(segments)}\n"
                    f"Time: {datetime.now().strftime('%H:%M:%S')}"
                )
            except Exception as e:
                logger.error(f"Failed to send notification: {e}")
                
        except Exception as e:
            logger.error(f"Segments activation error: {e}")
            query.edit_message_text(
                f"❌ **SEGMENTS ACTIVATION FAILED**\n\n"
                f"Error: {str(e)}\n\n"
                f"Please activate manually at:\n"
                f"https://console.zerodha.com/account/segment-activation"
            )
    
    def monitor_command(self, update: Update, context: CallbackContext):
        """Start auto-monitoring kill switch"""
        try:
            ks = get_global_kill_switch()
            logger.info(f"Monitor command using global instance: {id(ks)}")
            
            if ks.is_active:
                update.message.reply_text(
                    "⚠️ Kill switch is already active.\n"
                    "Cannot start monitoring.\n\n"
                    "Send /reactivate first."
                )
                return
            
            if ks.is_monitoring():
                update.message.reply_text(
                    "✅ Monitoring is already active!\n\n"
                    "Auto-monitoring P&L and will trigger kill switch on conditions.\n\n"
                    "Send /stopmonitor to stop."
                )
                return
            
            success, message_text = ks.start_monitoring(check_interval=5)
            
            if success:
                update.message.reply_text(
                    f"👁️ **AUTO-MONITORING STARTED**\n\n"
                    f"Monitoring P&L every 5 seconds\n\n"
                    f"**Will auto-trigger on:**\n"
                    f"• Loss > {ks.loss_display}\n"
                    f"• Profit threshold: {ks.profit_display}\n"
                    f"• Drawdown: {ks.drawdown_display}\n\n"
                    f"**Actions when triggered:**\n"
                    f"1. Close all positions\n"
                    f"2. Deactivate F&O segment\n"
                    f"3. Stop bot trading\n\n"
                    f"Send /stopmonitor to stop monitoring"
                )
            else:
                update.message.reply_text(f"❌ {message_text}")
                
        except Exception as e:
            logger.error(f"Monitor command error: {e}")
            update.message.reply_text(f"❌ Error: {e}")
    
    def stopmonitor_command(self, update: Update, context: CallbackContext):
        """Stop auto-monitoring"""
        try:
            ks = get_global_kill_switch()
            logger.info(f"Stop monitor command using global instance: {id(ks)}")
            
            if not ks.is_monitoring():
                update.message.reply_text(
                    "ℹ️ Monitoring is not active.\n\n"
                    "Send /monitor to start."
                )
                return
            
            success, message_text = ks.stop_monitoring()
            
            if success:
                update.message.reply_text(
                    f"⏹️ **MONITORING STOPPED**\n\n"
                    f"Auto-monitoring has been stopped.\n\n"
                    f"Send /monitor to restart."
                )
            else:
                update.message.reply_text(f"❌ {message_text}")
                
        except Exception as e:
            logger.error(f"Stop monitor command error: {e}")
            update.message.reply_text(f"❌ Error: {e}")
    
    def start_monitor_callback(self, query):
        """Start monitoring from button"""
        try:
            ks = get_global_kill_switch()
            logger.info(f"Monitor callback using global instance: {id(ks)}")
            
            if ks.is_active:
                query.edit_message_text(
                    "⚠️ Kill switch is already active.\n"
                    "Cannot start monitoring.\n\n"
                    "Send /reactivate first."
                )
                return
            
            if ks.is_monitoring():
                query.edit_message_text(
                    "✅ Monitoring is already active!\n\n"
                    "Send /stopmonitor to stop."
                )
                return
            
            success, message_text = ks.start_monitoring(check_interval=5)
            
            if success:
                query.edit_message_text(
                    f"👁️ **MONITORING STARTED**\n\n"
                    f"Checking P&L every 5 seconds\n\n"
                    f"Will auto-trigger on:\n"
                    f"• Loss > {ks.loss_display}\n"
                    f"• Profit threshold: {ks.profit_display}\n"
                    f"• Drawdown: {ks.drawdown_display}\n\n"
                    f"Send /stopmonitor to stop"
                )
            else:
                query.edit_message_text(f"❌ {message_text}")
                
        except Exception as e:
            logger.error(f"Start monitor callback error: {e}")
            query.edit_message_text(f"❌ Error: {e}")
    
    def stop_monitor_callback(self, query):
        """Stop monitoring from button"""
        try:
            ks = get_global_kill_switch()
            logger.info(f"Stop monitor callback using global instance: {id(ks)}")
            
            if not ks.is_monitoring():
                query.edit_message_text(
                    "ℹ️ Monitoring is not active.\n\n"
                    "Click 'Start Monitor' to begin."
                )
                return
            
            success, message_text = ks.stop_monitoring()
            
            if success:
                query.edit_message_text(
                    f"⏹️ **MONITORING STOPPED**\n\n"
                    f"Auto-monitoring stopped.\n\n"
                    f"Send /monitor to restart."
                )
            else:
                query.edit_message_text(f"❌ {message_text}")
                
        except Exception as e:
            logger.error(f"Stop monitor callback error: {e}")
            query.edit_message_text(f"❌ Error: {e}")
    
    def thresholds_command(self, update: Update, context: CallbackContext):
        """Show current kill switch thresholds"""
        try:
            ks = get_global_kill_switch()
            logger.debug(f"Thresholds command using global instance: {id(ks)}")
            
            message = (
                f"⚙️ **KILL SWITCH THRESHOLDS**\n\n"
                f"💰 Capital: ₹{ks.capital:,}\n\n"
                f"📉 **Loss Threshold:**\n"
                f"   {ks.loss_display}\n\n"
                f"📈 **Profit Threshold:**\n"
                f"   {ks.profit_display}\n\n"
                f"📊 **Drawdown Threshold:**\n"
                f"   {ks.drawdown_display}\n\n"
                f"To change thresholds:\n"
                f"1. Edit `.env` file on server\n"
                f"2. Restart the bot\n\n"
                f"**Example .env settings:**\n"
                f"```\n"
                f"# Percentage-based (recommended)\n"
                f"LOSS_THRESHOLD_PERCENT=10\n"
                f"PROFIT_THRESHOLD_PERCENT=12.5\n"
                f"DRAWDOWN_THRESHOLD_PERCENT=40\n"
                f"CAPITAL=40000\n\n"
                f"# OR Fixed amount\n"
                f"# LOSS_THRESHOLD=4000\n"
                f"# PROFIT_THRESHOLD=5000\n"
                f"# DRAWDOWN_THRESHOLD=2000\n"
                f"```\n\n"
                f"💡 Percentage-based scales with your capital!"
            )
            
            update.message.reply_text(message)
            
        except Exception as e:
            logger.error(f"Thresholds command error: {e}")
            update.message.reply_text(f"❌ Error: {e}")
    
    def setthreshold_command(self, update: Update, context: CallbackContext):
        """Set threshold dynamically (requires restart)"""
        if not context.args or len(context.args) < 2:
            message = (
                "⚙️ **SET THRESHOLD**\n\n"
                "Usage:\n"
                "`/setthreshold <type> <value>`\n\n"
                "**Types:**\n"
                "• `loss_pct` - Loss threshold %\n"
                "• `profit_pct` - Profit threshold %\n"
                "• `drawdown_pct` - Drawdown threshold %\n"
                "• `loss` - Loss threshold ₹\n"
                "• `profit` - Profit threshold ₹\n"
                "• `drawdown` - Drawdown threshold ₹\n\n"
                "**Examples:**\n"
                "`/setthreshold loss_pct 10`\n"
                "`/setthreshold profit_pct 12.5`\n"
                "`/setthreshold drawdown_pct 40`\n"
                "`/setthreshold loss 4000`\n\n"
                "⚠️ **Note:** Changes require bot restart to take effect.\n"
                "Edit `.env` file directly for permanent changes."
            )
            update.message.reply_text(message)
            return
        
        threshold_type = context.args[0].lower()
        try:
            value = float(context.args[1])
        except ValueError:
            update.message.reply_text("❌ Invalid value. Must be a number.")
            return
        
        # Map threshold types to env variable names
        threshold_map = {
            'loss_pct': 'LOSS_THRESHOLD_PERCENT',
            'profit_pct': 'PROFIT_THRESHOLD_PERCENT',
            'drawdown_pct': 'DRAWDOWN_THRESHOLD_PERCENT',
            'loss': 'LOSS_THRESHOLD',
            'profit': 'PROFIT_THRESHOLD',
            'drawdown': 'DRAWDOWN_THRESHOLD'
        }
        
        if threshold_type not in threshold_map:
            update.message.reply_text(
                f"❌ Invalid threshold type: {threshold_type}\n\n"
                f"Valid types: {', '.join(threshold_map.keys())}"
            )
            return
        
        env_var = threshold_map[threshold_type]
        
        message = (
            f"⚙️ **THRESHOLD UPDATE**\n\n"
            f"To set `{env_var}={value}`:\n\n"
            f"1. SSH to your server\n"
            f"2. Edit `.env` file:\n"
            f"   `nano ~/kite-algo/.env`\n\n"
            f"3. Add or update:\n"
            f"   `{env_var}={value}`\n\n"
            f"4. Restart bot:\n"
            f"   `sudo systemctl restart kite-trading-bot`\n\n"
            f"5. Verify with `/thresholds`\n\n"
            f"💡 Tip: Use percentage-based thresholds for better scaling!"
        )
        
        update.message.reply_text(message)
    
    def execute_consolidation_setup(self, query, context):
        """Execute a consolidation breakout setup"""
        try:
            # Extract setup index from callback data
            setup_idx = int(query.data.split('_')[-1])
            
            # Get stored setups
            setups = context.bot_data.get('consolidation_setups', [])
            
            if not setups or setup_idx >= len(setups):
                query.edit_message_text("❌ Setup not found or expired. Run /consolidation again.")
                return
            
            setup = setups[setup_idx]
            
            query.edit_message_text("🔄 Executing consolidation breakout trade...")
            
            # Calculate quantity (example: ₹2000 risk per trade)
            risk_per_trade = 2000
            risk_per_lot = abs(setup['entry_price'] - setup['stop_loss'])
            quantity = int(risk_per_trade / risk_per_lot) if risk_per_lot > 0 else 65
            
            # Calculate target (1:2 RR)
            risk = abs(setup['entry_price'] - setup['stop_loss'])
            target = setup['entry_price'] + (risk * 2)
            
            # Place order
            try:
                # Get instrument token
                instruments = self.kite.instruments("NFO")
                inst_df = pd.DataFrame(instruments)
                
                option_df = inst_df[
                    (inst_df['name'] == setup['symbol']) &
                    (inst_df['strike'] == setup['strike']) &
                    (inst_df['instrument_type'] == setup['option_type'])
                ].sort_values('expiry')
                
                if option_df.empty:
                    query.edit_message_text(f"❌ Option instrument not found")
                    return
                
                option = option_df.iloc[0]
                tradingsymbol = option['tradingsymbol']
                
                # Place market order
                order_id = self.kite.place_order(
                    variety=self.kite.VARIETY_REGULAR,
                    exchange='NFO',
                    tradingsymbol=tradingsymbol,
                    transaction_type='BUY',
                    quantity=quantity,
                    product=self.kite.PRODUCT_MIS,
                    order_type=self.kite.ORDER_TYPE_MARKET
                )
                
                message = (
                    f"✅ **CONSOLIDATION BREAKOUT EXECUTED**\n\n"
                    f"Symbol: {setup['symbol']} {setup['strike']} {setup['option_type']}\n"
                    f"Entry: ₹{setup['entry_price']:.2f}\n"
                    f"Target: ₹{target:.2f}\n"
                    f"Stop Loss: ₹{setup['stop_loss']:.2f}\n"
                    f"Quantity: {quantity}\n\n"
                    f"Order ID: {order_id}\n"
                    f"Breakout Strength: {setup['breakout_strength']:.1f}%\n"
                    f"Consolidation: {setup['consolidation_duration']} candles\n\n"
                    f"Risk: ₹{risk * quantity:,.2f}\n"
                    f"Reward: ₹{risk * 2 * quantity:,.2f}\n"
                    f"R:R = 1:2"
                )
                
                query.edit_message_text(message)
                
                # Send notification
                try:
                    from notifier import notifier
                    notifier.send_message(
                        f"🚀 **CONSOLIDATION BREAKOUT**\n\n"
                        f"{tradingsymbol}\n"
                        f"Entry: ₹{setup['entry_price']:.2f}\n"
                        f"Target: ₹{target:.2f}\n"
                        f"SL: ₹{setup['stop_loss']:.2f}\n"
                        f"Qty: {quantity}\n"
                        f"Order: {order_id}"
                    )
                except Exception as e:
                    logger.error(f"Failed to send notification: {e}")
                
            except Exception as order_error:
                logger.error(f"Order placement error: {order_error}")
                query.edit_message_text(f"❌ Order failed: {order_error}")
                
        except Exception as e:
            logger.error(f"Execute consolidation error: {e}")
            query.edit_message_text(f"❌ Execution failed: {e}")
    
    def show_consolidation_details(self, query, context):
        """Show detailed information about a consolidation setup"""
        try:
            # Extract setup index from callback data
            setup_idx = int(query.data.split('_')[-1])
            
            # Get stored setups
            setups = context.bot_data.get('consolidation_setups', [])
            
            if not setups or setup_idx >= len(setups):
                query.edit_message_text("❌ Setup not found or expired. Run /consolidation again.")
                return
            
            setup = setups[setup_idx]
            
            # Calculate metrics
            risk = abs(setup['entry_price'] - setup['stop_loss'])
            target = setup['entry_price'] + (risk * 2)
            range_size = setup['range_high'] - setup['range_low']
            range_pct = (range_size / setup['range_low']) * 100
            
            message = (
                f"📊 **CONSOLIDATION DETAILS**\n\n"
                f"**Symbol:** {setup['symbol']} {setup['strike']} {setup['option_type']}\n\n"
                f"**Breakout:**\n"
                f"• Direction: {setup['breakout_direction']}\n"
                f"• Strength: {setup['breakout_strength']:.1f}%\n"
                f"• Entry: ₹{setup['entry_price']:.2f}\n\n"
                f"**Consolidation:**\n"
                f"• Range: ₹{setup['range_low']:.2f} - ₹{setup['range_high']:.2f}\n"
                f"• Range Size: {range_pct:.1f}%\n"
                f"• Duration: {setup['consolidation_duration']} candles ({setup['consolidation_duration'] * 3} min)\n\n"
                f"**Trade Plan:**\n"
                f"• Entry: ₹{setup['entry_price']:.2f}\n"
                f"• Target: ₹{target:.2f} (1:2 RR)\n"
                f"• Stop Loss: ₹{setup['stop_loss']:.2f}\n"
                f"• Risk per lot: ₹{risk:.2f}\n\n"
                f"**Time:** {setup['timestamp'].strftime('%H:%M:%S')}"
            )
            
            keyboard = [
                [InlineKeyboardButton("✅ Execute Trade", callback_data=f'cons_execute_{setup_idx}')],
                [InlineKeyboardButton("❌ Cancel", callback_data=f'cons_cancel_{setup_idx}')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            query.edit_message_text(message, reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"Show consolidation details error: {e}")
            query.edit_message_text(f"❌ Error: {e}")
    
    def execute_index_trade(self, query, context):
        """Execute trade based on index analysis"""
        try:
            # Parse callback data: index_trade_NIFTY_CE_25200
            parts = query.data.split('_')
            symbol = parts[2]
            option_type = parts[3]
            strike = int(parts[4])
            
            query.edit_message_text(f"🔄 Executing {symbol} {option_type} {strike}...")
            
            # Get exchange and lot size from stored analysis results
            results = context.bot_data.get('index_analysis', [])
            exchange = "NFO"  # Default to NFO
            lot_size = 65  # Default lot size
            
            for result in results:
                if result['option_symbol'] == symbol:
                    exchange = result.get('exchange', 'NFO')
                    lot_size = result.get('lot_size', 65)
                    break
            
            # Fallback: determine exchange and lot size based on symbol if not in results
            if symbol == "SENSEX":
                exchange = "BFO"
                lot_size = 20
            elif symbol == "BANKNIFTY":
                exchange = "NFO"
                lot_size = 30
            elif symbol == "NIFTY":
                exchange = "NFO"
                lot_size = 65
            
            # Get instrument details
            instruments = self.kite.instruments(exchange)
            inst_df = pd.DataFrame(instruments)
            
            option_df = inst_df[
                (inst_df['name'] == symbol) &
                (inst_df['strike'] == strike) &
                (inst_df['instrument_type'] == option_type)
            ].sort_values('expiry')
            
            if option_df.empty:
                query.edit_message_text(f"❌ Option not found: {symbol} {strike} {option_type} on {exchange}")
                return
            
            option = option_df.iloc[0]
            tradingsymbol = option['tradingsymbol']
            
            # Get current LTP (Last Traded Price)
            try:
                ltp_data = self.kite.ltp([f"{exchange}:{tradingsymbol}"])
                ltp = ltp_data[f"{exchange}:{tradingsymbol}"]['last_price']
            except:
                ltp = 100  # Fallback estimate
            
            # Calculate quantity based on risk and lot size
            risk_per_trade = 2000  # ₹2000 risk per trade
            estimated_lots = max(1, int(risk_per_trade / (ltp * lot_size)))
            quantity = estimated_lots * lot_size  # Must be multiple of lot size
            
            investment = ltp * quantity
            
            # Place order
            order_id = self.kite.place_order(
                variety=self.kite.VARIETY_REGULAR,
                exchange=exchange,
                tradingsymbol=tradingsymbol,
                transaction_type='BUY',
                quantity=quantity,
                product=self.kite.PRODUCT_MIS,
                order_type=self.kite.ORDER_TYPE_MARKET
            )
            
            message = (
                f"✅ **TRADE EXECUTED**\n\n"
                f"Symbol: {tradingsymbol}\n"
                f"Exchange: {exchange}\n"
                f"Type: {option_type}\n"
                f"Strike: {strike}\n"
                f"Lot Size: {lot_size}\n"
                f"Lots: {estimated_lots}\n"
                f"Quantity: {quantity}\n"
                f"LTP: ₹{ltp:.2f}\n"
                f"Investment: ₹{investment:,.2f}\n"
                f"Order ID: {order_id}\n\n"
                f"Based on index analysis recommendation"
            )
            
            query.edit_message_text(message)
            
            # Send notification
            try:
                from notifier import notifier
                notifier.send_message(
                    f"✅ **INDEX TRADE EXECUTED**\n\n"
                    f"{tradingsymbol} ({exchange})\n"
                    f"Qty: {quantity} ({estimated_lots} lots)\n"
                    f"Investment: ₹{investment:,.2f}\n"
                    f"Order: {order_id}"
                )
            except Exception as e:
                logger.error(f"Failed to send notification: {e}")
                
        except Exception as e:
            logger.error(f"Execute index trade error: {e}")
            query.edit_message_text(f"❌ Trade execution failed: {e}")
    
    def refresh_index_analysis(self, query, context):
        """Refresh index analysis"""
        query.edit_message_text("🔄 Refreshing analysis...")
        
        try:
            from index_analyzer import index_analyzer
            
            results = index_analyzer.analyze_all_indices()
            
            if not results:
                query.edit_message_text("❌ Could not refresh analysis")
                return
            
            report = index_analyzer.format_analysis_report(results)
            
            best = results[0]
            keyboard = [
                [InlineKeyboardButton(
                    f"✅ Trade {best['option_symbol']} {best['option_type']} {best['suggested_strike']}", 
                    callback_data=f'index_trade_{best["option_symbol"]}_{best["option_type"]}_{best["suggested_strike"]}'
                )],
                [InlineKeyboardButton("🔄 Refresh Again", callback_data='index_refresh')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            query.edit_message_text(report, reply_markup=reply_markup)
            context.bot_data['index_analysis'] = results
            
        except Exception as e:
            logger.error(f"Refresh analysis error: {e}")
            query.edit_message_text(f"❌ Refresh failed: {e}")
    
    def compare_indices(self, query, context):
        """Show comparison of all indices"""
        try:
            results = context.bot_data.get('index_analysis', [])
            
            if not results:
                query.edit_message_text("❌ No analysis data. Run /analyze first.")
                return
            
            message = "📊 **INDEX COMPARISON**\n\n"
            
            for i, result in enumerate(results, 1):
                emoji = "🏆" if i == 1 else "🥈" if i == 2 else "🥉"
                message += (
                    f"{emoji} **{result['index']}**\n"
                    f"   Score: {result['score']:.0f}/100\n"
                    f"   Trend: {result['trend_strength']}\n"
                    f"   Suggested: {result['option_type']} {result['suggested_strike']}\n"
                    f"   1H: {result['change_1h']:+.2f}% | Vol: {result['volume_ratio']:.2f}x\n\n"
                )
            
            keyboard = [
                [InlineKeyboardButton("🔄 Refresh", callback_data='index_refresh')],
                [InlineKeyboardButton("« Back", callback_data='index_best_refresh')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            query.edit_message_text(message, reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"Compare indices error: {e}")
            query.edit_message_text(f"❌ Comparison failed: {e}")
    
    def refresh_best_trade(self, query, context):
        """Refresh best trade recommendation"""
        query.edit_message_text("🎯 Finding best opportunity...")
        
        try:
            from index_analyzer import index_analyzer
            
            best = index_analyzer.get_best_trade()
            
            if not best:
                query.edit_message_text("❌ No opportunities found")
                return
            
            score_emoji = "🔥" if best['score'] >= 70 else "✅" if best['score'] >= 50 else "⚠️"
            
            message = (
                f"{score_emoji} **BEST TRADING OPPORTUNITY**\n\n"
                f"**Index:** {best['index']}\n"
                f"**Trade:** {best['option_symbol']} {best['option_type']} {best['suggested_strike']}\n"
                f"**Score:** {best['score']:.0f}/100\n\n"
                f"**Analysis:**\n"
                f"• Price: ₹{best['current_price']:.2f} ({best['change_1h']:+.2f}% 1H)\n"
                f"• Trend: {best['trend']} ({best['trend_strength']})\n"
                f"• Volatility: {best['atr_pct']:.2f}%\n"
                f"• Volume: {best['volume_ratio']:.2f}x\n\n"
            )
            
            if best['score'] >= 70:
                message += "✅ Strong Setup - High conviction\n"
            elif best['score'] >= 50:
                message += "🟡 Moderate Setup - Decent opportunity\n"
            else:
                message += "⚠️ Weak Setup - Low conviction\n"
            
            keyboard = [
                [InlineKeyboardButton(
                    f"✅ Execute Trade", 
                    callback_data=f'index_trade_{best["option_symbol"]}_{best["option_type"]}_{best["suggested_strike"]}'
                )],
                [InlineKeyboardButton("📊 Compare All", callback_data='index_compare')],
                [InlineKeyboardButton("🔄 Refresh", callback_data='index_best_refresh')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            query.edit_message_text(message, reply_markup=reply_markup)
            context.bot_data['best_trade'] = best
            
        except Exception as e:
            logger.error(f"Refresh best trade error: {e}")
            query.edit_message_text(f"❌ Refresh failed: {e}")
    
    def start(self):
        """Start the bot"""
        logger.info("Starting Telegram Trading Bot...")
        self.updater.start_polling()
        logger.info("Bot is running. Press Ctrl+C to stop.")
        self.updater.idle()

def main():
    bot = TradingBot()
    bot.start()

if __name__ == "__main__":
    main()
