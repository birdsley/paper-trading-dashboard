"""
Email Notification System for Paper Trading
Sends daily portfolio updates via email
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import json
from pathlib import Path

class EmailNotifier:
    """Handles sending email notifications about portfolio updates."""
    
    def __init__(self, config_file='email_config.json'):
        self.config_file = config_file
        self.config = self.load_config()
        
        # Load email settings from config
        email_settings = self.config.get('email_settings', {})
        self.smtp_server = email_settings.get('smtp_server', 'smtp.gmail.com')
        self.smtp_port = email_settings.get('smtp_port', 587)
        self.sender_email = email_settings.get('sender_email')
        self.sender_password = email_settings.get('sender_password')
        
        # Load preferences
        self.preferences = self.config.get('email_preferences', {})
        
    def load_config(self):
        """Load email configuration from JSON file."""
        if not Path(self.config_file).exists():
            print(f"⚠️  No config file found. Creating {self.config_file}")
            default_config = {
                "email_settings": {
                    "smtp_server": "smtp.gmail.com",
                    "smtp_port": 587,
                    "sender_email": "your_email@gmail.com",
                    "sender_password": "your_app_password_here",
                    "use_gmail": True
                },
                "recipients": [
                    "your_email@gmail.com"
                ],
                "email_preferences": {
                    "send_on_no_trades": True,
                    "send_on_weekends": True,
                    "include_charts": True,
                    "timezone": "America/Chicago"
                }
            }
            with open(self.config_file, 'w') as f:
                json.dump(default_config, f, indent=2)
            return default_config
        
        with open(self.config_file, 'r') as f:
            return json.load(f)
        
    def load_recipients(self):
        """Load email recipients from config file."""
        recipients = self.config.get('recipients', [])
        
        if not recipients:
            print("⚠️  No recipients found in config file")
            return []
        
        return recipients
    
    def format_portfolio_report(self, portfolio_data, trades_executed):
        """Generate HTML email report from portfolio data."""
        
        latest = portfolio_data['daily_snapshots'][-1]
        initial = portfolio_data['initial_capital']
        
        # Calculate metrics
        portfolio_value = latest['portfolio_value']
        total_return = ((portfolio_value - initial) / initial * 100)
        cash = portfolio_data['current_cash']
        
        # Positions
        positions = portfolio_data['positions']
        closed = portfolio_data['closed_trades']
        
        # Premiums
        total_premiums = sum(pos.get('premium_collected', 0) for pos in positions)
        
        # Stats
        stats = portfolio_data.get('performance_stats', {})
        
        # Build HTML
        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                          color: white; padding: 20px; border-radius: 10px; }}
                .metric {{ background: #f7fafc; padding: 15px; margin: 10px 0; 
                         border-left: 4px solid #667eea; border-radius: 5px; }}
                .positive {{ color: #48bb78; font-weight: bold; }}
                .negative {{ color: #f56565; font-weight: bold; }}
                .trade {{ background: #fff3cd; padding: 10px; margin: 5px 0; 
                         border-left: 4px solid #ffc107; border-radius: 5px; }}
                table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
                th {{ background: #667eea; color: white; padding: 12px; text-align: left; }}
                td {{ padding: 10px; border-bottom: 1px solid #e2e8f0; }}
                tr:hover {{ background: #f7fafc; }}
                .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #e2e8f0;
                          color: #718096; font-size: 12px; text-align: center; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>📊 Paper Trading Daily Update</h1>
                <p>{datetime.now().strftime('%B %d, %Y at %I:%M %p CT')}</p>
            </div>
            
            <h2>Portfolio Summary</h2>
            <div class="metric">
                <strong>Portfolio Value:</strong> ${portfolio_value:,.2f} 
                <span class="{'positive' if total_return >= 0 else 'negative'}">
                    ({total_return:+.2f}%)
                </span>
            </div>
            
            <div class="metric">
                <strong>Cash:</strong> ${cash:,.2f}
            </div>
            
            <div class="metric">
                <strong>Premiums Collected:</strong> ${total_premiums:,.2f}
            </div>
            
            <div class="metric">
                <strong>Open Positions:</strong> {len(positions)} 
                | <strong>Closed Trades:</strong> {len(closed)}
            </div>
        """
        
        # Trades executed today
        if trades_executed > 0:
            html += f"""
            <h2>🎯 Today's Activity</h2>
            <div class="trade">
                <strong>✅ {trades_executed} new trade(s) executed today!</strong>
            </div>
            """
            
            # Show newest positions
            newest_positions = sorted(positions, key=lambda x: x['entry_date'], reverse=True)[:trades_executed]
            html += "<table>"
            html += "<tr><th>Ticker</th><th>Action</th><th>Strike</th><th>Contracts</th><th>Premium</th><th>Expiration</th></tr>"
            for pos in newest_positions:
                pnl = pos.get('premium_collected', 0) if pos['action'] == 'SELL' else -pos.get('premium_paid', 0)
                html += f"""
                <tr>
                    <td><strong>{pos['ticker']}</strong></td>
                    <td>{pos['action']}</td>
                    <td>${pos['strike']:.0f}</td>
                    <td>{pos['contracts']}</td>
                    <td class="positive">${pnl:,.2f}</td>
                    <td>{pos['expiration']}</td>
                </tr>
                """
            html += "</table>"
        else:
            html += f"""
            <h2>Today's Activity</h2>
            <div class="trade">
                <strong>⏸️  No new trades today</strong>
                <p>Strategy conditions not met or maximum positions reached.</p>
            </div>
            """
        
        # Open positions
        if len(positions) > 0:
            html += "<h2>Open Positions</h2>"
            html += "<table>"
            html += "<tr><th>Ticker</th><th>Strike</th><th>Contracts</th><th>Premium</th><th>Expiration</th><th>Days Held</th></tr>"
            
            for pos in positions:
                premium = pos.get('premium_collected', 0) if pos['action'] == 'SELL' else pos.get('premium_paid', 0)
                html += f"""
                <tr>
                    <td><strong>{pos['ticker']}</strong></td>
                    <td>${pos['strike']:.0f}</td>
                    <td>{pos['contracts']}</td>
                    <td>${premium:.2f}</td>
                    <td>{pos['expiration']}</td>
                    <td>{pos.get('days_held', 0)}</td>
                </tr>
                """
            html += "</table>"
        
        # Performance stats
        if stats.get('total_trades', 0) > 0:
            win_rate = (stats['winning_trades'] / stats['total_trades'] * 100)
            html += f"""
            <h2>Performance Statistics</h2>
            <div class="metric">
                <strong>Total Closed Trades:</strong> {stats['total_trades']}<br>
                <strong>Win Rate:</strong> {win_rate:.1f}% 
                ({stats['winning_trades']} wins, {stats['losing_trades']} losses)<br>
                <strong>Total P&L:</strong> 
                <span class="{'positive' if stats['total_pnl'] >= 0 else 'negative'}">
                    ${stats['total_pnl']:+,.2f}
                </span><br>
                <strong>Largest Win:</strong> ${stats['largest_win']:,.2f}<br>
                <strong>Largest Loss:</strong> ${stats['largest_loss']:,.2f}
            </div>
            """
        
        # Footer
        html += """
            <div class="footer">
                <p>🔴 This is a paper trading account - No real money involved</p>
                <p>Dashboard: <a href="http://localhost:8000/dashboard.html">View Live Dashboard</a></p>
            </div>
        </body>
        </html>
        """
        
        return html
    
    def send_email(self, subject, html_content, recipients=None):
        """Send email notification."""
        
        if recipients is None:
            recipients = self.load_recipients()
        
        if not recipients:
            print("⚠️  No recipients to send email to")
            return False
        
        print(f"\n📧 Preparing to send email to {len(recipients)} recipient(s)...")
        
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['From'] = self.sender_email
            msg['To'] = ', '.join(recipients)
            msg['Subject'] = subject
            
            # Attach HTML
            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)
            
            # Send email
            print(f"📤 Connecting to {self.smtp_server}...")
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                print(f"🔐 Logging in...")
                server.login(self.sender_email, self.sender_password)
                print(f"✉️  Sending email...")
                server.send_message(msg)
            
            print(f"✅ Email sent successfully to: {', '.join(recipients)}")
            return True
            
        except smtplib.SMTPAuthenticationError:
            print("❌ Email authentication failed!")
            print("   Make sure you're using an App Password (not your regular password)")
            print("   For Gmail: https://myaccount.google.com/apppasswords")
            return False
            
        except Exception as e:
            print(f"❌ Failed to send email: {e}")
            return False
    
    def send_daily_update(self, portfolio_file='portfolio_data.json', trades_executed=0):
        """Send daily portfolio update email."""
        
        # Load portfolio data
        if not Path(portfolio_file).exists():
            print(f"❌ Portfolio file not found: {portfolio_file}")
            return False
        
        with open(portfolio_file, 'r') as f:
            portfolio_data = json.load(f)
        
        # Generate report
        html_content = self.format_portfolio_report(portfolio_data, trades_executed)
        
        # Create subject
        latest = portfolio_data['daily_snapshots'][-1]
        portfolio_value = latest['portfolio_value']
        total_return = ((portfolio_value - portfolio_data['initial_capital']) / portfolio_data['initial_capital'] * 100)
        
        subject = f"📊 Paper Trading Update - ${portfolio_value:,.0f} ({total_return:+.1f}%)"
        
        if trades_executed > 0:
            subject += f" - {trades_executed} New Trade{'s' if trades_executed != 1 else ''}"
        
        # Send email
        return self.send_email(subject, html_content)


def test_email():
    """Test email configuration."""
    print("\n" + "="*70)
    print("📧 EMAIL CONFIGURATION TEST")
    print("="*70)
    
    notifier = EmailNotifier()
    
    # Check recipients file
    recipients = notifier.load_recipients()
    print(f"\n✅ Found {len(recipients)} recipient(s):")
    for email in recipients:
        print(f"   - {email}")
    
    # Test email
    print(f"\n📤 Sending test email...")
    test_html = """
    <html>
    <body>
        <h2>✅ Email Configuration Test</h2>
        <p>If you're reading this, your email notifications are working!</p>
        <p>You'll receive daily updates about your paper trading portfolio.</p>
    </body>
    </html>
    """
    
    success = notifier.send_email("📧 Paper Trading - Email Test", test_html, recipients)
    
    if success:
        print("\n✅ Test email sent successfully!")
        print("   Check your inbox (and spam folder)")
    else:
        print("\n❌ Test failed. Please check your configuration.")
    
    print("="*70 + "\n")


if __name__ == "__main__":
    # Send actual daily update instead of test
    print("\n" + "="*70)
    print("📧 SENDING DAILY PORTFOLIO UPDATE")
    print("="*70)
    
    notifier = EmailNotifier()
    
    # You can optionally pass trades_executed if you track it
    # For now, it defaults to 0
    success = notifier.send_daily_update(
        portfolio_file='portfolio_data.json',
        trades_executed=0  # Update this number based on your trading logic
    )
    
    if success:
        print("\n✅ Daily update email sent successfully!")
    else:
        print("\n❌ Failed to send daily update.")
    
    print("="*70 + "\n")