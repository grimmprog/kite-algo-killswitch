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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TradingBot:
    def __init__(self):
        self.kite = get_kite_session()
        self.capital = config.CAPITAL
        self.updater = Updater(token=config.TELEGRAM_BOT_TOKEN, use_context=True)
        self.setup_handlers()
        
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
        dp.add_handler(CommandHandler("risk", self.risk_command))
        
        # Scanner commands
        dp.add_handler(CommandHandler("scan", self.scan_command))
        dp.add_handler(CommandHandler("consolidation", self.consolidation_command))
        dp.add_handler(CommandHandler("cons", self.consolidation_command))  # Shortcut
        
        # Paper trading commands
        dp.add_handler(CommandHandler("paper", self.paper_command))
        dp.add_handler(CommandHandler("papertrades", self.paper_trades_command))
        
        # Orders & History
        dp.add_handler(CommandHandler("orders", self.orders_command))
        dp.add_handler(CommandHandler("history", self.history_command))
        
        # System commands
        dp.add_handler(CommandHandler("bot", self.bot_status_command))
        dp.add_handler(CommandHandler("time", self.time_command))
        
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
            "/capital - Check available capital\n"
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
            "/consolidation or /cons - Check consolidations\n\n"
            
            "📝 **Paper Trading**\n"
            "/paper - Paper trading status\n"
            "/papertrades - View paper trade history\n\n"
            
            "⚙️ **System**\n"
            "/bot - Bot status\n"
            "/time - Current time\n"
            "/help - Show this help\n\n"
            
            "💡 **Quick Actions**\n"
            "Use /status for interactive buttons!"
        )
        update.message.reply_text(message)
    
    def help_command(self, update: Update, context: CallbackContext):
        """Help message"""
        self.start_command(update, context)
    
    def get_total_pnl(self):
        """Get total P&L"""
        try:
            positions = self.kite.positions()
            day_pnl = sum([pos['pnl'] for pos in positions['day']])
            net_pnl = sum([pos['pnl'] for pos in positions['net']])
            return day_pnl, net_pnl
        except Exception as e:
            logger.error(f"Error fetching P&L: {e}")
            return 0, 0
    
    def get_open_positions(self):
        """Get open positions"""
        try:
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
            from advanced_killswitch import AdvancedKillSwitch
            ks = AdvancedKillSwitch()
            monitoring_status = "🟢 ON" if ks.is_monitoring() else "🔴 OFF"
        except:
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
            remaining_loss = 4000 - abs(day_pnl)
            message += f"\n⚠️ Loss: {loss_percent:.2f}%\n"
            if remaining_loss > 0:
                message += f"⚠️ ₹{remaining_loss:,.2f} until kill switch (₹4,000)\n"
            else:
                message += f"🚨 Kill switch threshold exceeded!\n"
        else:
            message += f"\n✅ Profit: {pnl_percent:.2f}%\n"
            if pnl_percent >= 10:
                message += f"🎯 Profit > 10% of capital!\n"
        
        update.message.reply_text(message)
    
    def positions_command(self, update: Update, context: CallbackContext):
        """Show open positions"""
        positions = self.get_open_positions()
        
        if not positions:
            update.message.reply_text("📭 No open positions")
            return
        
        message = f"📊 **OPEN POSITIONS** ({len(positions)})\n\n"
        
        for i, pos in enumerate(positions, 1):
            side = "🟢 LONG" if pos['quantity'] > 0 else "🔴 SHORT"
            pnl_emoji = "✅" if pos['pnl'] >= 0 else "❌"
            
            message += (
                f"{i}. {pos['tradingsymbol']}\n"
                f"   {side} | Qty: {abs(pos['quantity'])}\n"
                f"   Avg: ₹{pos['average_price']:.2f} | LTP: ₹{pos['last_price']:.2f}\n"
                f"   {pnl_emoji} P&L: ₹{pos['pnl']:.2f}\n\n"
            )
        
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
    
    def killswitch_command(self, update: Update, context: CallbackContext):
        """Kill switch status and activation"""
        day_pnl, _ = self.get_total_pnl()
        positions = self.get_open_positions()
        
        max_loss = 4000
        profit_warning = self.capital * 0.10
        
        message = f"🚨 **KILL SWITCH STATUS**\n\n"
        
        # Check conditions
        if day_pnl < -max_loss:
            message += f"🔴 **ACTIVATED** - Max loss exceeded!\n"
            message += f"Loss: ₹{day_pnl:,.2f} (Limit: ₹{max_loss:,})\n"
        elif day_pnl < 0:
            remaining = max_loss - abs(day_pnl)
            message += f"🟡 **MONITORING**\n"
            message += f"Loss: ₹{day_pnl:,.2f}\n"
            message += f"Remaining: ₹{remaining:,.2f} until activation\n"
        elif day_pnl >= profit_warning:
            message += f"🟢 **PROFIT WARNING**\n"
            message += f"Profit: ₹{day_pnl:,.2f} (>{profit_warning:,.0f})\n"
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
    
    def reactivate_command(self, update: Update, context: CallbackContext):
        """Reactivate trading after kill switch"""
        try:
            from advanced_killswitch import AdvancedKillSwitch
            
            ks = AdvancedKillSwitch()
            
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
        """Show capital and margin info"""
        try:
            margins = self.kite.margins()
            equity = margins['equity']
            
            message = (
                f"💰 **CAPITAL STATUS**\n\n"
                f"Available: ₹{equity['available']['live_balance']:,.2f}\n"
                f"Used: ₹{equity['utilised']['debits']:,.2f}\n"
                f"Total: ₹{equity['net']:,.2f}\n\n"
                f"Configured Capital: ₹{self.capital:,}\n"
            )
            update.message.reply_text(message)
        except Exception as e:
            update.message.reply_text(f"❌ Error fetching capital: {e}")
    
    def risk_command(self, update: Update, context: CallbackContext):
        """Show risk metrics"""
        day_pnl, _ = self.get_total_pnl()
        positions = self.get_open_positions()
        
        pnl_percent = (day_pnl / self.capital) * 100
        max_loss_pct = (4000 / self.capital) * 100
        
        message = (
            f"⚠️ **RISK METRICS**\n\n"
            f"Day P&L: ₹{day_pnl:,.2f} ({pnl_percent:+.2f}%)\n"
            f"Max Loss: ₹4,000 ({max_loss_pct:.1f}%)\n"
            f"Open Positions: {len(positions)}\n\n"
        )
        
        if day_pnl < 0:
            risk_used = abs(day_pnl) / 4000 * 100
            message += f"Risk Used: {risk_used:.1f}%\n"
        
        update.message.reply_text(message)
    
    def scan_command(self, update: Update, context: CallbackContext):
        """Manual scan trigger"""
        update.message.reply_text("🔍 Scanning for setups...\n\nThis will trigger the scanner manually.")
        # Add scanner trigger logic here
    
    def consolidation_command(self, update: Update, context: CallbackContext):
        """Check for consolidation setups"""
        update.message.reply_text(
            "📊 **Consolidation Scanner**\n\n"
            "Checking for tight range consolidations...\n"
            "This feature scans for 20-30 min consolidations\n"
            "with < 15% range for breakout opportunities."
        )
        # Add consolidation scanner logic here
    
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
            from advanced_killswitch import AdvancedKillSwitch
            
            ks = AdvancedKillSwitch()
            
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
            
            # Always deactivate segments (force mode)
            query.edit_message_text(f"{position_status}\n🔄 Deactivating trading segments...")
            
            # Deactivate all segments
            from segment_automation import ZerodhaSegmentAutomation
            
            automation = ZerodhaSegmentAutomation(headless=True)
            
            # Deactivate F&O segment
            segment_success = automation.deactivate_fno_segment()
            
            # Mark kill switch as active
            ks.is_active = True
            ks.save_status(True, "Manual activation via Telegram")
            
            day_pnl, _ = self.get_total_pnl()
            
            message = (
                f"⚡ **KILL SWITCH ACTIVATED**\n\n"
                f"{position_status}"
                f"💰 Final Day P&L: ₹{day_pnl:,.2f}\n"
                f"🕐 Time: {datetime.now().strftime('%H:%M:%S')}\n\n"
                f"**Actions Completed:**\n"
            )
            
            if positions:
                message += f"1. ✅ Positions closed\n"
            else:
                message += f"1. ℹ️ No positions to close\n"
            
            message += f"2. ✅ Bot stopped trading\n"
            
            if segment_success:
                message += f"3. ✅ F&O segment deactivated\n\n"
                message += f"🔒 No new F&O trades can be placed.\n\n"
            else:
                message += f"3. ⚠️ Segment deactivation failed\n\n"
                message += f"**MANUAL ACTION REQUIRED:**\n"
                message += f"Deactivate segments at:\n"
                message += f"https://console.zerodha.com/account/segment-activation\n\n"
            
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
                    f"Segment: {'✅ Deactivated' if segment_success else '⚠️ Manual action needed'}\n"
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
            from advanced_killswitch import AdvancedKillSwitch
            
            ks = AdvancedKillSwitch()
            
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
                    f"• Loss > ₹4,000\n"
                    f"• Profit drawdown: Peak ₹5,000 → Drop ₹2,000\n\n"
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
            from advanced_killswitch import AdvancedKillSwitch
            
            ks = AdvancedKillSwitch()
            
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
            from advanced_killswitch import AdvancedKillSwitch
            
            ks = AdvancedKillSwitch()
            
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
                    f"• Loss > ₹4,000\n"
                    f"• Profit drawdown\n\n"
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
            from advanced_killswitch import AdvancedKillSwitch
            
            ks = AdvancedKillSwitch()
            
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
            from advanced_killswitch import AdvancedKillSwitch
            
            ks = AdvancedKillSwitch()
            
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
