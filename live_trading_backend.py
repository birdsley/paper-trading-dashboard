"""
Live Paper Trading System - Daily Execution Script
Runs every day at market open to evaluate and execute trades

Portfolio: $1,000 split across SPY, VOO, VTI, QQQ ($250 each)
Strategy: Black-Scholes volatility arbitrage (sell overpriced options)

To run daily: Set up a cron job or Task Scheduler to run this at 9:35 AM ET
"""

import numpy as np
import pandas as pd
from scipy.stats import norm
import yfinance as yf
from datetime import datetime, timedelta
import json
import os
import warnings
warnings.filterwarnings('ignore')

# =============================================================================
# BLACK-SCHOLES AND OPTIONS PRICING
# =============================================================================

def black_scholes(S, K, T, r, sigma, option_type='call'):
    """Calculate Black-Scholes option price."""
    if T <= 0 or sigma <= 0:
        return max(S - K, 0) if option_type == 'call' else max(K - S, 0)
    
    try:
        d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)
        
        if option_type == 'call':
            return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
        else:
            return K * norm.cdf(-d2) * np.exp(-r * T) - S * norm.cdf(-d1)
    except:
        return 0

def calculate_historical_vol(ticker, window=30):
    """Calculate historical volatility for a ticker."""
    stock = yf.Ticker(ticker)
    hist = stock.history(period=f'{window + 10}d')
    returns = hist['Close'].pct_change().dropna()
    
    if len(returns) < window:
        return 0.20  # Default
    
    return returns.iloc[-window:].std() * np.sqrt(252)

# =============================================================================
# PORTFOLIO MANAGER
# =============================================================================

class PaperTradingPortfolio:
    """Manages the $1,000 paper trading portfolio."""
    
    def __init__(self, data_file='portfolio_data.json'):
        self.data_file = data_file
        self.tickers = ['SPY', 'VOO', 'VTI', 'QQQ']
        self.allocation_per_ticker = 250
        self.r = 0.045  # Risk-free rate
        
        # Trading parameters - CONSERVATIVE
        self.max_positions_per_ticker = 1  # Max 1 position per ticker
        self.max_total_positions = 4  # Max 4 total positions
        self.position_size_pct = 0.02  # 2% of allocation per trade
        self.min_iv_edge = 0.03  # IV must be 3%+ above HV
        self.min_price_edge = 0.05  # Price must be 5%+ above theoretical
        self.target_dte = 30  # Target 30 days to expiration
        self.min_moneyness = 1.05  # Min 5% OTM
        self.max_moneyness = 1.15  # Max 15% OTM
        
        # Load or initialize portfolio
        if os.path.exists(data_file):
            with open(data_file, 'r') as f:
                self.portfolio = json.load(f)
            print(f"📂 Loaded existing portfolio from {data_file}")
            print(f"   Current value: ${self.portfolio.get('daily_snapshots', [{'portfolio_value': 1000}])[-1]['portfolio_value']:,.2f}")
            print(f"   Open positions: {len(self.portfolio.get('positions', []))}")
            print(f"   Closed trades: {len(self.portfolio.get('closed_trades', []))}")
        else:
            self.portfolio = self.initialize_portfolio()
            self.save_portfolio()
            print(f"🆕 Created new portfolio")
    
    def initialize_portfolio(self):
        """Create a new portfolio."""
        today = datetime.now()
        
        # Get initial prices for benchmarks
        initial_prices = {}
        for ticker in self.tickers:
            try:
                stock = yf.Ticker(ticker)
                initial_prices[ticker] = stock.history(period='1d')['Close'].iloc[-1]
            except:
                initial_prices[ticker] = 250  # Fallback
        
        return {
            'start_date': today.strftime('%Y-%m-%d'),
            'initial_capital': 1000,
            'current_cash': 1000,
            'positions': [],
            'closed_trades': [],
            'daily_snapshots': [{
                'date': today.strftime('%Y-%m-%d'),
                'portfolio_value': 1000,
                'cash': 1000,
                'positions_value': 0,
                'spy_benchmark': 250,
                'voo_benchmark': 250,
                'vti_benchmark': 250,
                'qqq_benchmark': 250
            }],
            'benchmark_shares': {
                ticker: 250 / initial_prices[ticker] for ticker in self.tickers
            },
            'performance_stats': {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'total_pnl': 0,
                'largest_win': 0,
                'largest_loss': 0
            }
        }
    
    def save_portfolio(self):
        """Save portfolio to JSON file."""
        with open(self.data_file, 'w') as f:
            json.dump(self.portfolio, f, indent=2)
        print(f"💾 Portfolio saved to {self.data_file}")
    
    def get_current_price(self, ticker):
        """Fetch current stock price."""
        stock = yf.Ticker(ticker)
        return stock.history(period='1d')['Close'].iloc[-1]
    
    def find_option_opportunity(self, ticker):
        """
        Find a trading opportunity for a given ticker.
        Returns trade signal if opportunity found, None otherwise.
        """
        print(f"\n🔍 Analyzing {ticker}...")
        
        try:
            stock = yf.Ticker(ticker)
            current_price = stock.history(period='1d')['Close'].iloc[-1]
            
            # Get options chain
            expirations = stock.options
            if len(expirations) == 0:
                print(f"  ⚠️  No options available for {ticker}")
                return None
            
            # Find 30-day expiration
            today = pd.Timestamp.now()
            target_exp = None
            min_diff = float('inf')
            
            for exp in expirations:
                exp_date = pd.Timestamp(exp)
                dte = (exp_date - today).days
                if abs(dte - 30) < min_diff and dte > 0:
                    min_diff = abs(dte - 30)
                    target_exp = exp
            
            if target_exp is None:
                print(f"  ⚠️  No suitable expiration for {ticker}")
                return None
            
            T = (pd.Timestamp(target_exp) - today).days / 365
            print(f"  📅 Using expiration: {target_exp} (T={T:.3f} years)")
            
            # Get call options
            chain = stock.option_chain(target_exp)
            calls = chain.calls
            
            # Filter liquid options
            liquid_calls = calls[(calls['volume'] > 10) & (calls['bid'] > 0.10)]
            
            if len(liquid_calls) == 0:
                print(f"  ⚠️  No liquid options for {ticker}")
                return None
            
            # Calculate historical volatility
            hist_vol = calculate_historical_vol(ticker, window=30)
            print(f"  📊 Historical Vol: {hist_vol:.2%}")
            
            # Analyze each option
            best_opportunity = None
            best_edge = 0
            
            for idx, row in liquid_calls.iterrows():
                K = row['strike']
                moneyness = K / current_price
                
                # Focus on slightly OTM options (5-15% OTM)
                if moneyness < 1.05 or moneyness > 1.15:
                    continue
                
                market_price = (row['bid'] + row['ask']) / 2
                iv = row.get('impliedVolatility', hist_vol * 1.1)
                
                # Calculate theoretical price
                theo_price = black_scholes(current_price, K, T, self.r, hist_vol, 'call')
                
                # Check for edge
                iv_edge = iv - hist_vol
                price_edge_pct = (market_price - theo_price) / theo_price if theo_price > 0 else 0
                
                # SELL criteria: IV > HV + 3% AND price > theo + 5%
                if iv_edge > 0.03 and price_edge_pct > 0.05:
                    edge = market_price - theo_price
                    
                    if edge > best_edge:
                        best_edge = edge
                        best_opportunity = {
                            'ticker': ticker,
                            'action': 'SELL',
                            'strike': K,
                            'expiration': target_exp,
                            'price': row['bid'],  # Sell at bid
                            'market_mid': market_price,
                            'theoretical': theo_price,
                            'iv': iv,
                            'hv': hist_vol,
                            'iv_edge': iv_edge,
                            'price_edge': edge,
                            'price_edge_pct': price_edge_pct,
                            'moneyness': moneyness,
                            'current_stock_price': current_price,
                            'T': T
                        }
            
            if best_opportunity:
                print(f"  ✅ FOUND OPPORTUNITY!")
                print(f"     Strike: ${best_opportunity['strike']:.0f} ({best_opportunity['moneyness']:.1%} moneyness)")
                print(f"     Price: ${best_opportunity['price']:.2f} (Theo: ${best_opportunity['theoretical']:.2f})")
                print(f"     IV: {best_opportunity['iv']:.1%} vs HV: {best_opportunity['hv']:.1%}")
                print(f"     Edge: ${best_opportunity['price_edge']:.2f} ({best_opportunity['price_edge_pct']:.1%})")
                return best_opportunity
            else:
                print(f"  ❌ No opportunities meeting criteria")
                return None
                
        except Exception as e:
            print(f"  ❌ Error analyzing {ticker}: {str(e)}")
            return None
    
    def execute_trade(self, opportunity):
        """Execute a trade if capital is available."""
        ticker = opportunity['ticker']
        allocation = self.allocation_per_ticker
        
        # Check for duplicate position (same ticker, strike, expiration)
        for pos in self.portfolio['positions']:
            if (pos['ticker'] == ticker and 
                pos['strike'] == opportunity['strike'] and 
                pos['expiration'] == opportunity['expiration'] and
                pos['action'] == opportunity['action']):
                print(f"  ⏭️  SKIPPING: Duplicate position already exists")
                print(f"     {ticker} ${opportunity['strike']} {opportunity['expiration']}")
                return False
        
        # Calculate position size - CONSERVATIVE: 2% of allocation
        premium_per_contract = opportunity['price'] * 100
        contracts = max(1, int(allocation * 0.02 / premium_per_contract))  # 2% instead of 5%
        total_premium = contracts * premium_per_contract
        
        # Check if we have cash
        if total_premium > self.portfolio['current_cash']:
            print(f"  ⚠️  Insufficient cash (need ${total_premium:.2f}, have ${self.portfolio['current_cash']:.2f})")
            return False
        
        # Execute trade
        trade = {
            'id': f"trade_{len(self.portfolio['positions']) + len(self.portfolio['closed_trades'])}",
            'entry_date': datetime.now().strftime('%Y-%m-%d'),
            'ticker': ticker,
            'action': opportunity['action'],
            'strike': opportunity['strike'],
            'expiration': opportunity['expiration'],
            'contracts': contracts,
            'entry_price': opportunity['price'],
            'premium_collected': total_premium if opportunity['action'] == 'SELL' else 0,
            'premium_paid': total_premium if opportunity['action'] == 'BUY' else 0,
            'entry_stock_price': opportunity['current_stock_price'],
            'entry_iv': opportunity['iv'],
            'status': 'OPEN',
            'days_held': 0,
            'current_pnl': 0
        }
        
        # Update cash
        if opportunity['action'] == 'SELL':
            self.portfolio['current_cash'] += total_premium
        else:
            self.portfolio['current_cash'] -= total_premium
        
        # Add position
        self.portfolio['positions'].append(trade)
        
        print(f"\n  ✅ TRADE EXECUTED!")
        print(f"     {opportunity['action']} {contracts}x {ticker} ${opportunity['strike']:.0f} Call")
        print(f"     Premium: ${opportunity['price']:.2f} → Total: ${total_premium:.2f}")
        print(f"     Cash remaining: ${self.portfolio['current_cash']:.2f}")
        
        return True
    
    def update_positions(self):
        """Update all open positions and close expired ones."""
        print("\n📋 Updating positions...")
        
        today = datetime.now()
        new_positions = []
        
        for pos in self.portfolio['positions']:
            entry_date = datetime.strptime(pos['entry_date'], '%Y-%m-%d')
            exp_date = datetime.strptime(pos['expiration'], '%Y-%m-%d')
            days_held = (today - entry_date).days
            
            pos['days_held'] = days_held
            
            # Check if expired
            if today >= exp_date:
                print(f"\n  🔒 CLOSING EXPIRED: {pos['ticker']} {pos['strike']} Call")
                
                # Get current stock price
                current_price = self.get_current_price(pos['ticker'])
                intrinsic = max(current_price - pos['strike'], 0)
                
                # Calculate P&L
                if pos['action'] == 'SELL':
                    pnl = pos['premium_collected'] - (intrinsic * pos['contracts'] * 100)
                else:
                    pnl = (intrinsic * pos['contracts'] * 100) - pos['premium_paid']
                
                # Update performance stats
                if 'performance_stats' not in self.portfolio:
                    self.portfolio['performance_stats'] = {
                        'total_trades': 0,
                        'winning_trades': 0,
                        'losing_trades': 0,
                        'total_pnl': 0,
                        'largest_win': 0,
                        'largest_loss': 0
                    }
                
                self.portfolio['performance_stats']['total_trades'] += 1
                self.portfolio['performance_stats']['total_pnl'] += pnl
                
                if pnl > 0:
                    self.portfolio['performance_stats']['winning_trades'] += 1
                    if pnl > self.portfolio['performance_stats']['largest_win']:
                        self.portfolio['performance_stats']['largest_win'] = pnl
                else:
                    self.portfolio['performance_stats']['losing_trades'] += 1
                    if pnl < self.portfolio['performance_stats']['largest_loss']:
                        self.portfolio['performance_stats']['largest_loss'] = pnl
                
                pos['exit_date'] = today.strftime('%Y-%m-%d')
                pos['exit_stock_price'] = current_price
                pos['intrinsic_value'] = intrinsic
                pos['pnl'] = pnl
                pos['status'] = 'CLOSED'
                
                # Update cash
                self.portfolio['current_cash'] += pnl
                
                # Move to closed trades
                self.portfolio['closed_trades'].append(pos)
                
                print(f"     Intrinsic: ${intrinsic:.2f} | P&L: ${pnl:+.2f}")
                
                # Show win/loss emoji
                if pnl > 0:
                    print(f"     ✅ WINNER! +${pnl:.2f}")
                else:
                    print(f"     ❌ LOSER: ${pnl:.2f}")
                    
                print(f"     Cash: ${self.portfolio['current_cash']:.2f}")
            else:
                new_positions.append(pos)
        
        self.portfolio['positions'] = new_positions
        print(f"\n  Open positions: {len(self.portfolio['positions'])}")
        print(f"  Closed trades: {len(self.portfolio['closed_trades'])}")
    
    def update_daily_snapshot(self):
        """Record daily portfolio value and benchmarks."""
        today = datetime.now().strftime('%Y-%m-%d')
        
        # Calculate positions value (mark-to-market)
        positions_value = 0
        for pos in self.portfolio['positions']:
            if pos['action'] == 'SELL':
                # Liability (we owe the option value)
                current_price = self.get_current_price(pos['ticker'])
                days_to_exp = (datetime.strptime(pos['expiration'], '%Y-%m-%d') - datetime.now()).days
                T = max(days_to_exp / 365, 0.001)
                option_value = black_scholes(current_price, pos['strike'], T, self.r, pos['entry_iv'], 'call')
                positions_value -= option_value * pos['contracts'] * 100
            else:
                # Asset
                current_price = self.get_current_price(pos['ticker'])
                days_to_exp = (datetime.strptime(pos['expiration'], '%Y-%m-%d') - datetime.now()).days
                T = max(days_to_exp / 365, 0.001)
                option_value = black_scholes(current_price, pos['strike'], T, self.r, pos['entry_iv'], 'call')
                positions_value += option_value * pos['contracts'] * 100
        
        portfolio_value = self.portfolio['current_cash'] + positions_value
        
        # Update benchmarks
        benchmarks = {}
        for ticker in self.tickers:
            current_price = self.get_current_price(ticker)
            # Initialize shares if first day
            if len(self.portfolio['daily_snapshots']) == 1:
                self.portfolio['benchmark_shares'][ticker] = 250 / current_price
            
            shares = self.portfolio['benchmark_shares'][ticker]
            benchmarks[f'{ticker.lower()}_benchmark'] = shares * current_price
        
        snapshot = {
            'date': today,
            'portfolio_value': round(portfolio_value, 2),
            'cash': round(self.portfolio['current_cash'], 2),
            'positions_value': round(positions_value, 2),
            **{k: round(v, 2) for k, v in benchmarks.items()}
        }
        
        self.portfolio['daily_snapshots'].append(snapshot)
        
        print(f"\n📊 Daily Snapshot:")
        print(f"   Portfolio Value: ${portfolio_value:,.2f}")
        print(f"   Cash: ${self.portfolio['current_cash']:,.2f}")
        print(f"   Positions Value: ${positions_value:,.2f}")
    
    def generate_report(self):
        """Generate summary report."""
        latest = self.portfolio['daily_snapshots'][-1]
        initial = self.portfolio['initial_capital']
        
        total_return = (latest['portfolio_value'] - initial) / initial * 100
        spy_return = (latest['spy_benchmark'] - 250) / 250 * 100
        
        # Performance stats
        stats = self.portfolio.get('performance_stats', {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'total_pnl': 0,
            'largest_win': 0,
            'largest_loss': 0
        })
        
        win_rate = (stats['winning_trades'] / stats['total_trades'] * 100) if stats['total_trades'] > 0 else 0
        
        print("\n" + "="*70)
        print("DAILY PORTFOLIO REPORT")
        print("="*70)
        print(f"Date: {latest['date']}")
        print(f"Days Trading: {len(self.portfolio['daily_snapshots'])}")
        print()
        print(f"{'PORTFOLIO VALUE':^70}")
        print(f"Current Value: ${latest['portfolio_value']:,.2f}")
        print(f"Total Return: {total_return:+.2f}%")
        print(f"Cash: ${self.portfolio['current_cash']:,.2f}")
        print()
        print(f"{'BENCHMARK COMPARISON':^70}")
        print(f"SPY Benchmark: {spy_return:+.2f}%")
        print(f"Alpha: {total_return - spy_return:+.2f}%")
        print()
        print(f"{'TRADING STATISTICS':^70}")
        print(f"Open Positions: {len(self.portfolio['positions'])}/{self.max_total_positions}")
        print(f"Closed Trades: {stats['total_trades']}")
        print(f"Win Rate: {win_rate:.1f}% ({stats['winning_trades']} wins, {stats['losing_trades']} losses)")
        print(f"Total P&L: ${stats['total_pnl']:+,.2f}")
        print(f"Largest Win: ${stats['largest_win']:+,.2f}")
        print(f"Largest Loss: ${stats['largest_loss']:+,.2f}")
        print()
        print(f"{'RISK METRICS':^70}")
        
        # Calculate max drawdown
        values = [s['portfolio_value'] for s in self.portfolio['daily_snapshots']]
        peak = values[0]
        max_dd = 0
        for v in values:
            if v > peak:
                peak = v
            dd = (v - peak) / peak * 100
            if dd < max_dd:
                max_dd = dd
        
        print(f"Max Drawdown: {max_dd:.2f}%")
        print(f"Position Utilization: {len(self.portfolio['positions'])}/{self.max_total_positions} ({len(self.portfolio['positions'])/self.max_total_positions*100:.0f}%)")
        print("="*70)

# =============================================================================
# DAILY EXECUTION
# =============================================================================

def run_daily_update():
    """Main function - run this daily at market open."""
    print("\n" + "="*70)
    print(f"🚀 DAILY PAPER TRADING UPDATE - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    
    # Initialize portfolio
    portfolio = PaperTradingPortfolio()
    
    # Step 1: Update existing positions
    portfolio.update_positions()
    
    # Step 2: Look for new opportunities
    print("\n🔎 Scanning for new opportunities...")
    opportunities_found = 0
    total_open_positions = len(portfolio.portfolio['positions'])
    
    # SAFETY LIMIT: Max 4 total positions across all tickers (was unlimited before)
    if total_open_positions >= 4:
        print(f"\n⏸️  SKIPPING NEW TRADES: Already at maximum (4/4 positions)")
        print(f"   This prevents over-leverage. Wait for positions to close.")
    else:
        for ticker in portfolio.tickers:
            # Only open 1 position per ticker maximum (was 2 before)
            ticker_positions = len([p for p in portfolio.portfolio['positions'] if p['ticker'] == ticker])
            
            if ticker_positions >= 1:
                print(f"\n⏭️  Skipping {ticker} (already have {ticker_positions} position)")
                continue
            
            # Check if we can still open positions
            if total_open_positions >= 4:
                print(f"\n⏸️  Reached maximum positions (4), stopping scan")
                break
            
            opportunity = portfolio.find_option_opportunity(ticker)
            
            if opportunity:
                success = portfolio.execute_trade(opportunity)
                if success:
                    opportunities_found += 1
                    total_open_positions += 1
    
    print(f"\n📈 Executed {opportunities_found} new trades today")
    print(f"📊 Total open positions: {total_open_positions}/4")
    
    # Step 3: Update daily snapshot
    portfolio.update_daily_snapshot()
    
    # Step 4: Save portfolio
    portfolio.save_portfolio()
    
    # Step 5: Generate report
    portfolio.generate_report()
    
    print("\n✅ Daily update complete!\n")

# =============================================================================
# EXECUTION
# =============================================================================

if __name__ == "__main__":
    run_daily_update()
    
# End of script - no additional content below this line