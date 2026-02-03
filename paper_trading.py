"""
Paper Trading System for Consolidation Breakout Strategy
Simulates real trades without risking money
Tracks performance, generates reports, and builds confidence
"""
import datetime
import json
import os
import pandas as pd
from connect import get_kite_session
from notifier import send_telegram_message
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PaperTradingAccount:
    def __init__(self, starting_capital=40000):
        self.starting_capital = starting_capital
        self.capital = starting_capital
        self.trades = []
        self.open_positions = []
        self.trade_log_file = "paper_trades.json"
        self.load_trades()
        
    def load_trades(self):
        """Load previous paper trades"""
        if os.path.exists(self.trade_log_file):
            with open(self.trade_log_file, 'r') as f:
                data = json.load(f)
                self.trades = data.get('trades', [])
                self.capital = data.get('capital', self.starting_capital)
                self.open_positions = data.get('open_positions', [])
    
    def save_trades(self):
        """Save paper trades to file"""
        data = {
            'starting_capital': self.starting_capital,
            'capital': self.capital,
            'trades': self.trades,
            'open_positions': self.open_positions,
            'last_updated': datetime.datetime.now().isoformat()
        }
        with open(self.trade_log_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def enter_trade(self, symbol, strike, option_type, entry_price, quantity, 
                    stop_loss, target, setup_type='consolidation'):
        """
        Enter a paper trade
        """
        trade_id = len(self.trades) + 1
        investment = entry_price * quantity
        
        if investment > self.capital:
            logger.warning(f"Insufficient capital: Need ₹{investment:,.2f}, Have ₹{self.capital:,.2f}")
            return None
        
        trade = {
            'id': trade_id,
            'symbol': symbol,
            'strike': strike,
            'option_type': option_type,
            'entry_price': entry_price,
            'quantity': quantity,
            'stop_loss': stop_loss,
            'target': target,
            'setup_type': setup_type,
            'entry_time': datetime.datetime.now().isoformat(),
            'status': 'OPEN',
            'investment': investment,
            'current_price': entry_price,
            'current_pnl': 0,
            'exit_price': None,
            'exit_time': None,
            'exit_reason': None,
            'final_pnl': None
        }
        
        self.open_positions.append(trade)
        self.capital -= investment
        self.save_trades()
        
        # Send notification
        risk = abs(entry_price - stop_loss) * quantity
        reward = abs(target - entry_price) * quantity
        rr = reward / risk if risk > 0 else 0
        
        message = f"""
📝 PAPER TRADE ENTERED

Trade #{trade_id}
Symbol: {symbol} {strike} {option_type}
Entry: ₹{entry_price:.2f}
Quantity: {quantity}
Investment: ₹{investment:,.2f}

Stop Loss: ₹{stop_loss:.2f}
Target: ₹{target:.2f}

Risk: ₹{risk:,.2f}
Reward: ₹{reward:,.2f}
RR: 1:{rr:.1f}

Capital Remaining: ₹{self.capital:,.2f}
"""
        send_telegram_message(message)
        logger.info(f"Paper trade #{trade_id} entered")
        
        return trade_id
    
    def update_position(self, trade_id, current_price):
        """
        Update position with current price
        Check if stop loss or target hit
        """
        for position in self.open_positions:
            if position['id'] == trade_id:
                position['current_price'] = current_price
                position['current_pnl'] = (current_price - position['entry_price']) * position['quantity']
                
                # Check stop loss
                if current_price <= position['stop_loss']:
                    self.exit_trade(trade_id, position['stop_loss'], 'STOP_LOSS')
                    return 'STOPPED'
                
                # Check target
                if current_price >= position['target']:
                    self.exit_trade(trade_id, position['target'], 'TARGET')
                    return 'TARGET_HIT'
                
                self.save_trades()
                return 'OPEN'
        
        return None
    
    def exit_trade(self, trade_id, exit_price, reason='MANUAL'):
        """
        Exit a paper trade
        """
        for i, position in enumerate(self.open_positions):
            if position['id'] == trade_id:
                # Calculate P&L
                pnl = (exit_price - position['entry_price']) * position['quantity']
                roi = (pnl / position['investment']) * 100
                
                # Update trade
                position['exit_price'] = exit_price
                position['exit_time'] = datetime.datetime.now().isoformat()
                position['exit_reason'] = reason
                position['final_pnl'] = pnl
                position['roi'] = roi
                position['status'] = 'CLOSED'
                
                # Update capital
                exit_value = exit_price * position['quantity']
                self.capital += exit_value
                
                # Move to closed trades
                self.trades.append(position)
                self.open_positions.pop(i)
                self.save_trades()
                
                # Send notification
                duration = self._calculate_duration(position['entry_time'], position['exit_time'])
                
                emoji = "✅" if pnl > 0 else "❌"
                message = f"""
{emoji} PAPER TRADE CLOSED

Trade #{trade_id}
Symbol: {position['symbol']} {position['strike']} {position['option_type']}

Entry: ₹{position['entry_price']:.2f}
Exit: ₹{exit_price:.2f}
Reason: {reason}

P&L: ₹{pnl:+,.2f}
ROI: {roi:+.2f}%
Duration: {duration}

Capital: ₹{self.capital:,.2f}
Total P&L: ₹{self.get_total_pnl():+,.2f}
"""
                send_telegram_message(message)
                logger.info(f"Paper trade #{trade_id} closed: {reason}")
                
                return True
        
        return False
    
    def _calculate_duration(self, entry_time, exit_time):
        """Calculate trade duration"""
        entry = datetime.datetime.fromisoformat(entry_time)
        exit = datetime.datetime.fromisoformat(exit_time)
        duration = exit - entry
        
        minutes = int(duration.total_seconds() / 60)
        if minutes < 60:
            return f"{minutes} minutes"
        else:
            hours = minutes // 60
            mins = minutes % 60
            return f"{hours}h {mins}m"
    
    def get_total_pnl(self):
        """Calculate total P&L from all closed trades"""
        total = sum(trade.get('final_pnl', 0) for trade in self.trades)
        return total
    
    def get_statistics(self):
        """Generate trading statistics"""
        if not self.trades:
            return None
        
        total_trades = len(self.trades)
        winning_trades = [t for t in self.trades if t.get('final_pnl', 0) > 0]
        losing_trades = [t for t in self.trades if t.get('final_pnl', 0) < 0]
        
        win_rate = (len(winning_trades) / total_trades) * 100 if total_trades > 0 else 0
        
        total_pnl = self.get_total_pnl()
        total_wins = sum(t['final_pnl'] for t in winning_trades)
        total_losses = sum(t['final_pnl'] for t in losing_trades)
        
        avg_win = total_wins / len(winning_trades) if winning_trades else 0
        avg_loss = total_losses / len(losing_trades) if losing_trades else 0
        
        profit_factor = abs(total_wins / total_losses) if total_losses != 0 else float('inf')
        
        return {
            'total_trades': total_trades,
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'total_wins': total_wins,
            'total_losses': total_losses,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'current_capital': self.capital,
            'roi_on_capital': ((self.capital - self.starting_capital) / self.starting_capital) * 100
        }
    
    def print_report(self):
        """Print performance report"""
        stats = self.get_statistics()
        
        if not stats:
            print("\n📊 No trades yet")
            return
        
        print("\n" + "=" * 70)
        print("PAPER TRADING PERFORMANCE REPORT")
        print("=" * 70)
        
        print(f"\n💰 Capital")
        print(f"   Starting: ₹{self.starting_capital:,.2f}")
        print(f"   Current:  ₹{stats['current_capital']:,.2f}")
        print(f"   P&L:      ₹{stats['total_pnl']:+,.2f}")
        print(f"   ROI:      {stats['roi_on_capital']:+.2f}%")
        
        print(f"\n📈 Trade Statistics")
        print(f"   Total Trades:    {stats['total_trades']}")
        print(f"   Winning Trades:  {stats['winning_trades']}")
        print(f"   Losing Trades:   {stats['losing_trades']}")
        print(f"   Win Rate:        {stats['win_rate']:.1f}%")
        
        print(f"\n💵 P&L Breakdown")
        print(f"   Total Wins:      ₹{stats['total_wins']:+,.2f}")
        print(f"   Total Losses:    ₹{stats['total_losses']:,.2f}")
        print(f"   Average Win:     ₹{stats['avg_win']:,.2f}")
        print(f"   Average Loss:    ₹{stats['avg_loss']:,.2f}")
        print(f"   Profit Factor:   {stats['profit_factor']:.2f}")
        
        print(f"\n📊 Open Positions: {len(self.open_positions)}")
        for pos in self.open_positions:
            print(f"   #{pos['id']}: {pos['symbol']} {pos['strike']} {pos['option_type']}")
            print(f"   Entry: ₹{pos['entry_price']:.2f} | Current: ₹{pos['current_price']:.2f}")
            print(f"   P&L: ₹{pos['current_pnl']:+,.2f}")
        
        print("\n" + "=" * 70)


class PaperTradingScanner:
    """
    Scanner that works with paper trading account
    """
    def __init__(self, paper_account):
        self.kite = get_kite_session()
        self.account = paper_account
        
    def monitor_live(self, symbol='NIFTY', strike=25200, option_type='PE'):
        """
        Monitor live prices and update paper positions
        """
        try:
            # Get current option price
            instruments = self.kite.instruments("NFO")
            inst_df = pd.DataFrame(instruments)
            
            option_df = inst_df[
                (inst_df['name'] == symbol) &
                (inst_df['strike'] == strike) &
                (inst_df['instrument_type'] == option_type)
            ].sort_values('expiry')
            
            if option_df.empty:
                return None
            
            token = option_df.iloc[0]['instrument_token']
            quote = self.kite.quote(f"NFO:{token}")
            
            current_price = quote[f"NFO:{token}"]['last_price']
            
            # Update all open positions
            for position in self.account.open_positions:
                if (position['symbol'] == symbol and 
                    position['strike'] == strike and 
                    position['option_type'] == option_type):
                    
                    status = self.account.update_position(position['id'], current_price)
                    
                    if status == 'STOPPED':
                        logger.info(f"Trade #{position['id']} stopped out")
                    elif status == 'TARGET_HIT':
                        logger.info(f"Trade #{position['id']} target hit!")
            
            return current_price
            
        except Exception as e:
            logger.error(f"Error monitoring: {e}")
            return None


def main():
    """
    Paper trading interface
    """
    print("=" * 70)
    print("PAPER TRADING SYSTEM")
    print("=" * 70)
    
    account = PaperTradingAccount(starting_capital=40000)
    
    print(f"\nStarting Capital: ₹{account.starting_capital:,.2f}")
    print(f"Current Capital: ₹{account.capital:,.2f}")
    print(f"Open Positions: {len(account.open_positions)}")
    print(f"Closed Trades: {len(account.trades)}")
    
    while True:
        print("\n" + "=" * 70)
        print("OPTIONS:")
        print("1. Enter new paper trade")
        print("2. Update position manually")
        print("3. Close position")
        print("4. View open positions")
        print("5. View performance report")
        print("6. Start live monitoring")
        print("7. Exit")
        print("=" * 70)
        
        choice = input("\nSelect option (1-7): ").strip()
        
        if choice == '1':
            # Enter new trade
            print("\n📝 Enter New Paper Trade")
            symbol = input("Symbol (NIFTY/BANKNIFTY): ").strip().upper()
            strike = int(input("Strike: "))
            option_type = input("Type (PE/CE): ").strip().upper()
            entry_price = float(input("Entry Price: "))
            quantity = int(input("Quantity: "))
            stop_loss = float(input("Stop Loss: "))
            target = float(input("Target: "))
            
            trade_id = account.enter_trade(
                symbol, strike, option_type, entry_price, 
                quantity, stop_loss, target
            )
            
            if trade_id:
                print(f"\n✅ Paper trade #{trade_id} entered successfully!")
            
        elif choice == '2':
            # Update position
            if not account.open_positions:
                print("\n⚠️ No open positions")
                continue
            
            print("\nOpen Positions:")
            for pos in account.open_positions:
                print(f"  #{pos['id']}: {pos['symbol']} {pos['strike']} {pos['option_type']}")
            
            trade_id = int(input("\nTrade ID to update: "))
            current_price = float(input("Current Price: "))
            
            status = account.update_position(trade_id, current_price)
            print(f"\nStatus: {status}")
            
        elif choice == '3':
            # Close position
            if not account.open_positions:
                print("\n⚠️ No open positions")
                continue
            
            print("\nOpen Positions:")
            for pos in account.open_positions:
                print(f"  #{pos['id']}: {pos['symbol']} {pos['strike']} {pos['option_type']}")
            
            trade_id = int(input("\nTrade ID to close: "))
            exit_price = float(input("Exit Price: "))
            reason = input("Reason (MANUAL/TARGET/STOP_LOSS): ").strip().upper()
            
            if account.exit_trade(trade_id, exit_price, reason):
                print("\n✅ Position closed successfully!")
            
        elif choice == '4':
            # View positions
            if not account.open_positions:
                print("\n⚠️ No open positions")
            else:
                print("\n📊 Open Positions:")
                for pos in account.open_positions:
                    print(f"\n  Trade #{pos['id']}")
                    print(f"  {pos['symbol']} {pos['strike']} {pos['option_type']}")
                    print(f"  Entry: ₹{pos['entry_price']:.2f}")
                    print(f"  Current: ₹{pos['current_price']:.2f}")
                    print(f"  P&L: ₹{pos['current_pnl']:+,.2f}")
                    print(f"  Stop: ₹{pos['stop_loss']:.2f} | Target: ₹{pos['target']:.2f}")
            
        elif choice == '5':
            # Performance report
            account.print_report()
            
        elif choice == '6':
            # Live monitoring
            print("\n🔴 Live Monitoring (Press Ctrl+C to stop)")
            scanner = PaperTradingScanner(account)
            
            try:
                while True:
                    if account.open_positions:
                        for pos in account.open_positions:
                            price = scanner.monitor_live(
                                pos['symbol'], 
                                pos['strike'], 
                                pos['option_type']
                            )
                            if price:
                                print(f"Trade #{pos['id']}: ₹{price:.2f} | P&L: ₹{pos['current_pnl']:+,.2f}")
                    
                    import time
                    time.sleep(10)
                    
            except KeyboardInterrupt:
                print("\n\nMonitoring stopped")
            
        elif choice == '7':
            print("\n👋 Goodbye!")
            break
        
        else:
            print("\n❌ Invalid option")


if __name__ == "__main__":
    main()
