#!/usr/bin/env python3
"""
Master Automation Script
Runs complete daily workflow:
1. Execute trading script
2. Start dashboard server
3. Send email notifications

Schedule this to run at 9:35 AM Central Time every weekday
"""

import subprocess
import sys
import os
import webbrowser
import time
from datetime import datetime
from pathlib import Path

def log(message):
    """Print timestamped log message."""
    timestamp = datetime.now().strftime('%H:%M:%S')
    print(f"[{timestamp}] {message}")

def run_trading_script():
    """Execute the trading script."""
    log("🚀 Running trading script...")
    
    try:
        result = subprocess.run(
            [sys.executable, 'live_trading_backend.py'],
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        # Print output
        print(result.stdout)
        
        if result.returncode == 0:
            log("✅ Trading script completed successfully")
            return True
        else:
            log(f"❌ Trading script failed with code {result.returncode}")
            print(result.stderr)
            return False
            
    except subprocess.TimeoutExpired:
        log("❌ Trading script timed out after 5 minutes")
        return False
    except Exception as e:
        log(f"❌ Error running trading script: {e}")
        return False

def start_dashboard_server(auto_open=True):
    """Start the dashboard server in background."""
    log("🌐 Starting dashboard server...")
    
    try:
        # Start server as background process
        process = subprocess.Popen(
            [sys.executable, 'dashboard_server.py'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Give it a moment to start
        time.sleep(2)
        
        if process.poll() is None:  # Still running
            log("✅ Dashboard server started (PID: {})".format(process.pid))
            
            if auto_open:
                time.sleep(1)
                webbrowser.open('http://localhost:8000/dashboard.html')
                log("📊 Dashboard opened in browser")
            
            return process
        else:
            log("❌ Dashboard server failed to start")
            return None
            
    except Exception as e:
        log(f"❌ Error starting dashboard: {e}")
        return None

def check_requirements():
    """Check that all required files exist."""
    log("🔍 Checking requirements...")
    
    required_files = [
        'live_trading_backend.py',
        'dashboard.html',
        'dashboard_server.py'
    ]
    
    optional_files = [
        'email_config.json',
        'portfolio_data.json'
    ]
    
    all_good = True
    
    for file in required_files:
        if Path(file).exists():
            log(f"  ✅ {file}")
        else:
            log(f"  ❌ {file} - REQUIRED FILE MISSING!")
            all_good = False
    
    for file in optional_files:
        if Path(file).exists():
            log(f"  ✅ {file}")
        else:
            log(f"  ⚠️  {file} - optional, will be created if needed")
    
    return all_good

def main():
    """Main automation workflow."""
    print("\n" + "="*70)
    print("🤖 PAPER TRADING AUTOMATION - MASTER SCRIPT")
    print("="*70)
    log(f"Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Check requirements
    if not check_requirements():
        log("❌ Missing required files. Please check your setup.")
        sys.exit(1)
    
    print()
    
    # Step 1: Run trading script
    trading_success = run_trading_script()
    
    if not trading_success:
        log("⚠️  Trading script failed, but continuing...")
    
    print()
    
    # Step 2: Start dashboard server
    dashboard_process = start_dashboard_server(auto_open=True)
    
    print()
    print("="*70)
    log("✅ AUTOMATION COMPLETE")
    print("="*70)
    print()
    print("📊 Dashboard: http://localhost:8000/dashboard.html")
    print("📧 Email sent (if configured)")
    print()
    print("💡 The dashboard server is running in the background.")
    print("   You can close this window, the server will keep running.")
    print("   To stop the server, find the process and kill it:")
    print("   ps aux | grep dashboard_server")
    print()
    
    # Keep script running if dashboard is running
    if dashboard_process:
        log("Press Ctrl+C to stop the dashboard server and exit")
        try:
            dashboard_process.wait()
        except KeyboardInterrupt:
            log("\n\n👋 Stopping dashboard server...")
            dashboard_process.terminate()
            dashboard_process.wait()
            log("✅ Dashboard stopped. Goodbye!")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Automation interrupted. Goodbye!")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)
