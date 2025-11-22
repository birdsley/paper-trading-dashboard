#!/usr/bin/env python3
"""
Simple HTTP Server for Paper Trading Dashboard
Run this script, then open http://localhost:8000 in your browser

Usage:
    python dashboard_server.py
"""

import http.server
import socketserver
import os
import webbrowser
from pathlib import Path

PORT = 8000

class MyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # Add CORS headers to allow local file access
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        self.send_header('Expires', '0')
        super().end_headers()

    def log_message(self, format, *args):
        # Cleaner log format
        if args[0].startswith('GET'):
            print(f"✅ Served: {args[0]}")

def main():
    # Change to script directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    print("\n" + "="*70)
    print("🚀 PAPER TRADING DASHBOARD SERVER")
    print("="*70)
    print(f"\n📁 Serving files from: {os.getcwd()}")
    
    # Check for required files
    if not Path('dashboard.html').exists():
        print("\n❌ ERROR: dashboard.html not found in current directory!")
        print("   Make sure this script is in the same folder as dashboard.html")
        return
    
    if not Path('portfolio_data.json').exists():
        print("\n⚠️  WARNING: portfolio_data.json not found!")
        print("   Run 'python live_trading_backend.py' first to generate it.")
        print("   Starting server anyway...")
    else:
        print("\n✅ Found portfolio_data.json")
    
    # Start server
    Handler = MyHTTPRequestHandler
    
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        url = f"http://localhost:{PORT}/dashboard.html"
        print(f"\n🌐 Server running at: {url}")
        print("\n📊 Opening dashboard in your browser...")
        print("\n💡 Press Ctrl+C to stop the server")
        print("="*70 + "\n")
        
        # Open browser
        try:
            webbrowser.open(url)
        except:
            print("Could not open browser automatically. Please open manually:")
            print(f"   {url}")
        
        # Serve forever
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n\n👋 Server stopped. Goodbye!")

if __name__ == "__main__":
    main()
