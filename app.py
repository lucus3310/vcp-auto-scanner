import threading
import time
import os
from typing import List, Optional
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

from vcp_analyzer import calculate_technical_indicators, analyze_vcp
import database
import ticker_fetcher

app = FastAPI(title="VCP Stock Scanner")

# Ensure static directory exists
os.makedirs("static", exist_ok=True)

# Mount static files directory
app.mount("/static", StaticFiles(directory="static"), name="static")

# Database startup initialization
@app.on_event("startup")
def startup_event():
    database.init_db()
    # Start the daily scheduler thread in the background
    threading.Thread(target=run_daily_scheduler, daemon=True).start()

# Global scanning state
scan_lock = threading.Lock()
scan_state = {
    "running": False,
    "progress": 0,
    "total": 0,
    "current_symbol": "",
    "results": [],
    "cancelled": False
}

# Scheduler State & Logic
scheduler_state = {
    "running": False,
    "last_run": "Never",
    "status": "Idle"
}
scheduler_lock = threading.Lock()

def run_scheduled_prefetch_and_scan():
    global scheduler_state
    with scheduler_lock:
        if scheduler_state["running"]:
            print("[Scheduler] Scheduler is already running.")
            return
        scheduler_state["running"] = True
        scheduler_state["status"] = "Running populator"
        
    try:
        import db_populator
        print("[Scheduler] Background scheduler: Populating/Updating database...")
        # Polite pre-fetch of all preset symbols + watchlist
        db_populator.populate_database(delay=1.5)
        
        with scheduler_lock:
            scheduler_state["status"] = "Running VCP analysis"
            
        print("[Scheduler] Background scheduler: Starting VCP analysis...")
        watchlist = database.get_watchlist()
        symbols = sorted(list(set(db_populator.ALL_SYMBOLS + watchlist)))
        
        results = []
        for idx, orig_symbol in enumerate(symbols):
            try:
                symbol, data, source = resolve_ticker(orig_symbol, period="6mo")
                if data.empty or len(data) < 10:
                    analysis = {
                        'Symbol': orig_symbol,
                        'VCP': False,
                        'Reason': 'No stock data found / invalid symbol',
                        'Contractions': 0,
                        'Contraction_List': [],
                        'Volatility_Decrease': 'N/A',
                        'ADX_Strength': False,
                        'DI_Bullish': False,
                        'RSI_Value': 0.0,
                        'Price_Increase_6M': '0%',
                        'Anomaly_Free': False,
                        'Volume_Contraction': False,
                        'Breakout_Detected': False
                    }
                else:
                    df_indicators = calculate_technical_indicators(data)
                    analysis = analyze_vcp(symbol, df_indicators)
            except Exception as e:
                analysis = {
                    'Symbol': orig_symbol,
                    'VCP': False,
                    'Reason': f"Processing error: {str(e)}",
                    'Contractions': 0,
                    'Contraction_List': [],
                    'Volatility_Decrease': 'N/A',
                    'ADX_Strength': False,
                    'DI_Bullish': False,
                    'RSI_Value': 0.0,
                    'Price_Increase_6M': '0%',
                    'Anomaly_Free': False,
                    'Volume_Contraction': False,
                    'Breakout_Detected': False
                }
            results.append(analysis)
            
        if results:
            scan_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " (Pre-fetched)"
            database.save_scan_results(scan_date, results)
            print(f"[Scheduler] Daily VCP scan completed. Saved {len(results)} results under: {scan_date}")
            
        with scheduler_lock:
            scheduler_state["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            scheduler_state["status"] = "Success"
    except Exception as e:
        print(f"[Scheduler] Error in scheduled run: {e}")
        with scheduler_lock:
            scheduler_state["status"] = f"Failed: {str(e)}"
    finally:
        with scheduler_lock:
            scheduler_state["running"] = False

def run_daily_scheduler():
    # Initial sleep to ensure server is fully up
    time.sleep(15)
    
    print("[Scheduler] Robust daily auto-update scheduler started. Checking every 5 minutes.")
    while True:
        try:
            now = datetime.now()
            today_str = now.strftime("%Y-%m-%d")
            
            # Trigger daily scan if:
            # 1. Current local time is past 4:00 AM (local time UTC+8)
            # 2. No scan has been recorded in the database for today yet
            if now.hour >= 4:
                latest_dates = database.get_scan_dates()
                has_today_scan = False
                for d in latest_dates:
                    if d.startswith(today_str):
                        has_today_scan = True
                        break
                
                if not has_today_scan:
                    print(f"[Scheduler] Time {now.strftime('%H:%M:%S')} is past 4:00 AM and no scan for today ({today_str}) exists. Triggering scan...")
                    run_scheduled_prefetch_and_scan()
                else:
                    # Daily scan already exists, idle until tomorrow
                    pass
            else:
                # Before 4:00 AM, wait
                pass
        except Exception as e:
            print(f"[Scheduler] Exception in scheduler loop: {e}")
            
        # Poll every 5 minutes (300 seconds)
        time.sleep(300)

class ScanRequest(BaseModel):
    symbols: List[str]
    lookback_period: str = "6mo"
    min_base_duration: int = 30
    volume_spike_multiplier: float = 1.5
    contraction_ratio_threshold: float = 0.95
    min_volume: int = 100000

# Presets of stock lists
SYMBOL_PRESETS = {
    "ALL": ticker_fetcher.get_all_tickers(),
    "US_TECH": ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "NFLX", "AVGO", "QCOM", "AMD", "INTC", "CSCO", "ORCL", "CRM"],
    "SP500_TOP": ["AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "TSLA", "BRK-B", "LLY", "AVGO", "JPM", "UNH", "V", "XOM", "MA", "HD", "PG", "COST", "JNJ", "ABBV"],
    "NASDAQ_100": ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "COST", "PEP", "CSCO", "NFLX", "ADBE", "AMD", "QCOM", "TXN", "AMGN", "INTU", "ISRG", "AMAT", "BKNG", "MU", "MDLZ", "GILD", "LRCX", "PANW", "REGN", "VRTX", "SNPS", "ADP", "CDNS", "KLAC", "MELI", "MAR", "FTNT", "ORLY", "CTAS", "NXPI", "WDAY", "ROP", "MNST", "ADSK", "CRWD", "MCHP", "PDD", "KDP", "EXC", "AEP", "PAYX", "PCAR", "DXCM", "ODFL", "BKR", "CPRT", "IDXX", "ROST", "MRVL", "AZO", "TEAM", "SIRI", "FAST", "DLTR", "CTSH", "ANSS", "CSX", "EA", "ALGN", "ILMN", "EBAY", "MGM", "JD", "BIDU", "NTES", "ZM", "DOCU", "DDOG", "OKTA", "ZS"],
    "TAIWAN_50": ["2330.TW", "2317.TW", "2454.TW", "2308.TW", "2881.TW", "2882.TW", "2382.TW", "3231.TW", "2303.TW", "2603.TW", "2891.TW", "2357.TW", "2886.TW", "3711.TW", "2412.TW", "1301.TW", "1303.TW", "2002.TW", "2884.TW", "2892.TW"],
    "TAIWAN_ALL": ["2330.TW", "2317.TW", "2454.TW", "2308.TW", "2881.TW", "2882.TW", "2382.TW", "3231.TW", "2303.TW", "2603.TW", "2891.TW", "2357.TW", "2886.TW", "3711.TW", "2412.TW", "1301.TW", "1303.TW", "2002.TW", "2884.TW", "2892.TW", "2885.TW", "2880.TW", "2890.TW", "2301.TW", "2324.TW", "2352.TW", "2353.TW", "2356.TW", "2379.TW", "2395.TW", "2408.TW", "2409.TW", "2449.TW", "2474.TW", "2609.TW", "2610.TW", "2615.TW", "2618.TW", "2801.TW", "2883.TW", "2887.TW", "2888.TW", "2912.TW", "3008.TW", "3034.TW", "3037.TW", "3045.TW", "3443.TW", "3481.TW", "3702.TW", "4904.TW", "4938.TW", "5871.TW", "5876.TW", "5880.TW", "6005.TW", "6505.TW", "6669.TW", "8046.TW", "8454.TW", "9904.TW", "9910.TW", "9921.TW", "9945.TW"]
}

@app.get("/")
def read_root():
    return FileResponse("static/index.html")

@app.get("/api/presets")
def get_presets():
    return SYMBOL_PRESETS

@app.get("/api/ticker-names")
def get_ticker_names():
    return ticker_fetcher.get_ticker_name_map()

@app.get("/api/progress")
def get_progress():
    with scan_lock:
        return JSONResponse(content=scan_state)

@app.post("/api/cancel")
def cancel_scan():
    with scan_lock:
        if scan_state["running"]:
            scan_state["cancelled"] = True
            return {"status": "Cancellation requested"}
        return {"status": "No scan is running"}

def get_lookback_date_str(period: str) -> str:
    """Calculate lookback date based on period"""
    today = datetime.now()
    if period == "3mo":
        days = 90
    elif period == "1y":
        days = 365
    elif period == "1.5y":
        days = 550
    elif period == "2y":
        days = 730
    else: # default 6mo
        days = 180
    return (today - timedelta(days=days)).strftime("%Y-%m-%d")

def get_market_today(symbol: str):
    """Calculate today's date in market's local timezone to prevent start_date > end_date errors in yfinance"""
    utc_now = datetime.utcnow()
    if symbol.upper().endswith(".TW") or symbol.upper().endswith(".TWO"):
        return (utc_now + timedelta(hours=8)).date()
    else:
        return (utc_now - timedelta(hours=5)).date()

def resolve_ticker(symbol: str, period: str = "6mo") -> tuple[str, pd.DataFrame, str]:
    """
    Downloads/updates stock data using SQLite database as cache.
    Returns a tuple of (resolved_symbol, dataframe, data_source).
    data_source is either 'local_cache' or 'live_download'.
    """
    symbol = symbol.strip().upper()
    resolved_sym = symbol
    
    # Resolve pure digit Taiwan stocks
    if symbol.isdigit():
        for suffix in [".TW", ".TWO"]:
            test_sym = f"{symbol}{suffix}"
            latest = database.get_latest_cached_date(test_sym)
            if latest:
                resolved_sym = test_sym
                break
        else:
            # Check live
            for suffix in [".TW", ".TWO"]:
                test_sym = f"{symbol}{suffix}"
                try:
                    data = yf.download(test_sym, period="5d", progress=False)
                    if not data.empty and len(data) >= 3:
                        resolved_sym = test_sym
                        break
                except Exception:
                    pass
                    
    db_period = "1.5y" if period == "1y" else "1y"
    lookback_date = get_lookback_date_str(db_period)
    latest_cached = database.get_latest_cached_date(resolved_sym)
    data_source = "local_cache"
    
    if latest_cached:
        latest_dt = datetime.strptime(latest_cached, "%Y-%m-%d").date()
        market_today = get_market_today(resolved_sym)
        
        # If cache is older than today in the market's timezone, fetch incrementally
        if latest_dt < market_today:
            try:
                start_date = (latest_dt + timedelta(days=1)).strftime("%Y-%m-%d")
                inc_data = yf.download(resolved_sym, start=start_date, progress=False)
                
                if not inc_data.empty:
                    if isinstance(inc_data.columns, pd.MultiIndex):
                        inc_data.columns = inc_data.columns.droplevel(1)
                    
                    bars = []
                    for idx, row in inc_data.iterrows():
                        bars.append({
                            "date": idx.strftime("%Y-%m-%d"),
                            "open": float(row["Open"]),
                            "high": float(row["High"]),
                            "low": float(row["Low"]),
                            "close": float(row["Close"]),
                            "volume": float(row["Volume"])
                        })
                    database.save_price_bars(resolved_sym, bars)
                    data_source = "live_download"
            except Exception as e:
                print(f"Incremental fetch failed for {resolved_sym}: {e}")
    else:
        # Full download and cache (fetch db_period to populate plenty of history)
        try:
            full_data = yf.download(resolved_sym, period=db_period, progress=False)
            if not full_data.empty:
                if isinstance(full_data.columns, pd.MultiIndex):
                    full_data.columns = full_data.columns.droplevel(1)
                
                bars = []
                for idx, row in full_data.iterrows():
                    bars.append({
                        "date": idx.strftime("%Y-%m-%d"),
                        "open": float(row["Open"]),
                        "high": float(row["High"]),
                        "low": float(row["Low"]),
                        "close": float(row["Close"]),
                        "volume": float(row["Volume"])
                    })
                database.save_price_bars(resolved_sym, bars)
                data_source = "live_download"
        except Exception as e:
            print(f"Full download failed for {resolved_sym}: {e}")
            
    # Load completed history from database
    cached_bars = database.get_cached_prices(resolved_sym, lookback_date)
    if not cached_bars:
        return resolved_sym, pd.DataFrame(), "none"
        
    df = pd.DataFrame(cached_bars)
    df['Date'] = pd.to_datetime(df['date'])
    df.set_index('Date', inplace=True)
    df.rename(columns={
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume"
    }, inplace=True)
    
    return resolved_sym, df, data_source

def run_background_scan(req: ScanRequest):
    global scan_state
    
    symbols = list(set([s.strip().upper() for s in req.symbols if s.strip()]))
    total = len(symbols)
    name_map = ticker_fetcher.get_ticker_name_map()
    
    with scan_lock:
        scan_state.update({
            "running": True,
            "progress": 0,
            "total": total,
            "current_symbol": "",
            "results": [],
            "cancelled": False
        })
        
    results = []
    
    for i, orig_symbol in enumerate(symbols):
        # Check for cancellation
        with scan_lock:
            if scan_state["cancelled"]:
                break
            scan_state["current_symbol"] = orig_symbol
            scan_state["progress"] = int((i / total) * 100)
            
        source = "none"
        try:
            # Resolve and download stock data (using cache)
            symbol, data, source = resolve_ticker(orig_symbol, period=req.lookback_period)
            
            # Check if dataframe is empty
            if data.empty or len(data) < 10:
                analysis = {
                    'Symbol': orig_symbol,
                    'VCP': False,
                    'Reason': 'No stock data found / invalid symbol',
                    'Contractions': 0,
                    'Contraction_List': [],
                    'Volatility_Decrease': 'N/A',
                    'ADX_Strength': False,
                    'DI_Bullish': False,
                    'RSI_Value': 0.0,
                    'Price_Increase_6M': '0%',
                    'Anomaly_Free': False,
                    'Volume_Contraction': False,
                    'Breakout_Detected': False
                }
            else:
                # Flatten columns if multi-indexed
                if isinstance(data.columns, pd.MultiIndex):
                    data.columns = data.columns.droplevel(1)
                    
                # Calculate indicators and run pattern recognition
                df_indicators = calculate_technical_indicators(data)
                analysis = analyze_vcp(
                    symbol, 
                    df_indicators, 
                    min_base_duration=req.min_base_duration,
                    volume_spike_multiplier=req.volume_spike_multiplier,
                    contraction_ratio_threshold=req.contraction_ratio_threshold,
                    min_volume=req.min_volume
                )
                
        except Exception as e:
            analysis = {
                'Symbol': orig_symbol,
                'VCP': False,
                'Reason': f"Processing error: {str(e)}",
                'Contractions': 0,
                'Contraction_List': [],
                'Volatility_Decrease': 'N/A',
                'ADX_Strength': False,
                'DI_Bullish': False,
                'RSI_Value': 0.0,
                'Price_Increase_6M': '0%',
                'Anomaly_Free': False,
                'Volume_Contraction': False,
                'Breakout_Detected': False
            }
            
        analysis['Name'] = name_map.get(orig_symbol, "")
        results.append(analysis)
        
        with scan_lock:
            scan_state["results"] = results
            
        # Small delay ONLY if we hit yfinance network download
        if source == "live_download":
            time.sleep(1.5)
        
    # Save scan results to history in database if not cancelled
    with scan_lock:
        is_cancelled = scan_state["cancelled"]
        
    if not is_cancelled and results:
        scan_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        database.save_scan_results(scan_date, results)
        
    with scan_lock:
        scan_state["running"] = False
        scan_state["progress"] = 100
        scan_state["current_symbol"] = "Completed"

@app.post("/api/scan")
def start_scan(req: ScanRequest, background_tasks: BackgroundTasks):
    with scan_lock:
        if scan_state["running"]:
            raise HTTPException(status_code=400, detail="A scan is already in progress")
            
    background_tasks.add_task(run_background_scan, req)
    return {"status": "Scan started", "total": len(req.symbols)}

@app.get("/api/chart-data")
def get_chart_data(symbol: str, lookback_period: str = "6mo"):
    try:
        resolved_symbol, data, source = resolve_ticker(symbol, period=lookback_period)
        if data.empty:
            raise HTTPException(status_code=404, detail=f"No data found for symbol {symbol}")
            
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.droplevel(1)
            
        df_indicators = calculate_technical_indicators(data)
        if df_indicators.empty:
            # If not enough data for all indicators, return raw data
            df_indicators = data.copy()
            df_indicators['EMA20'] = df_indicators['Close']
            df_indicators['Upper_KC'] = df_indicators['Close']
            df_indicators['Lower_KC'] = df_indicators['Close']
            df_indicators['KC_Width'] = 0.0
            df_indicators['ADX'] = 0.0
            df_indicators['RSI'] = 50.0
            df_indicators['PlusDI'] = 0.0
            df_indicators['MinusDI'] = 0.0
            df_indicators['Anomaly_Score'] = 1
            
        # Run scan parameters as default for visualization
        analysis = analyze_vcp(resolved_symbol, df_indicators)
        
        # Slice to requested lookback period for chart display
        chart_lookback_date = get_lookback_date_str(lookback_period)
        df_chart = df_indicators.loc[chart_lookback_date:]
        
        # Prepare list of price records for chart from df_chart
        records = []
        for idx, row in df_chart.iterrows():
            records.append({
                "time": idx.strftime('%Y-%m-%d'),
                "open": float(row['Open']),
                "high": float(row['High']),
                "low": float(row['Low']),
                "close": float(row['Close']),
                "volume": float(row['Volume']),
                "ema20": float(row['EMA20']) if 'EMA20' in row else None,
                "upper_kc": float(row['Upper_KC']) if 'Upper_KC' in row else None,
                "lower_kc": float(row['Lower_KC']) if 'Lower_KC' in row else None,
            })
            
        name_map = ticker_fetcher.get_ticker_name_map()
        return {
            "symbol": resolved_symbol,
            "name": name_map.get(resolved_symbol, ""),
            "chart_data": records,
            "data_source": source,
            "analysis": {
                "VCP": analysis["VCP"],
                "Reason": analysis["Reason"],
                "Contractions": analysis["Contractions"],
                "Contraction_List": analysis["Contraction_List"],
                "Breakout_Detected": analysis["Breakout_Detected"]
            }
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Watchlist API Endpoints
class WatchlistRequest(BaseModel):
    symbol: str

@app.get("/api/watchlist")
def get_watchlist():
    return database.get_watchlist()

@app.post("/api/watchlist")
def add_watchlist(req: WatchlistRequest):
    database.add_to_watchlist(req.symbol)
    return {"status": "success", "watchlist": database.get_watchlist()}

@app.delete("/api/watchlist/{symbol}")
def delete_watchlist(symbol: str):
    database.remove_from_watchlist(symbol)
    return {"status": "success", "watchlist": database.get_watchlist()}

# Scan History API Endpoints
@app.get("/api/history-dates")
def get_history_dates():
    return database.get_scan_dates()

@app.get("/api/history-results")
def get_history_results(date: str):
    results = database.get_historical_scan(date)
    name_map = ticker_fetcher.get_ticker_name_map()
    for r in results:
        r['Name'] = name_map.get(r['Symbol'], "")
    return results

@app.get("/api/history-summary")
def get_history_summary():
    return database.get_scan_history_summary()

@app.delete("/api/history-scan")
def delete_history_scan(date: str):
    database.delete_historical_scan(date)
    return {"status": "success"}

@app.delete("/api/history-clear-all")
def clear_all_history():
    database.clear_all_scan_history()
    return {"status": "success"}

# Scheduler API Endpoints
@app.get("/api/scheduler/status")
def get_scheduler_status():
    with scheduler_lock:
        return JSONResponse(content=scheduler_state)

@app.post("/api/scheduler/trigger")
def trigger_scheduler(background_tasks: BackgroundTasks):
    with scheduler_lock:
        if scheduler_state["running"]:
            raise HTTPException(status_code=400, detail="Scheduler is already running")
    background_tasks.add_task(run_scheduled_prefetch_and_scan)
    return {"status": "Scheduler triggered in background"}

if __name__ == "__main__":
    import argparse
    import json
    
    parser = argparse.ArgumentParser(description="VCP Stock Scanner Backend")
    parser.add_argument("--run-scan", action="store_true", help="Run daily scan once and exit (for CI/CD)")
    parser.add_argument("--sheet-id", type=str, default="", help="Google Sheets ID for export")
    args = parser.parse_args()

    if args.run_scan:
        print("[CLI] Starting single-run scan...")
        database.init_db()
        run_scheduled_prefetch_and_scan()
        print("[CLI] Scan finished.")
        
        # After scan, fetch latest results from database to export
        latest_dates = database.get_scan_dates()
        if latest_dates:
            latest_date = latest_dates[0]
            results = database.get_historical_scan(latest_date)
            
            # Export to static JSON for GitHub Pages
            with open("static/latest_scan.json", "w", encoding="utf-8") as f:
                json.dump({"date": latest_date, "results": results}, f, ensure_ascii=False, indent=2)
            print("[CLI] Exported latest_scan.json to static folder.")
            
            summary = database.get_scan_history_summary()
            with open("static/history_summary.json", "w", encoding="utf-8") as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)
            print("[CLI] Exported history_summary.json to static folder.")
            
            # Export to Google Sheets
            if args.sheet_id:
                try:
                    import google_sheets_exporter
                    google_sheets_exporter.export_to_google_sheets(results, args.sheet_id, scan_date=latest_date)
                except ImportError:
                    print("[CLI] google_sheets_exporter module not found. Skipping Google Sheets export.")
        else:
            print("[CLI] No scan results found in database after run.")
    else:
        import uvicorn
        # Use port 8000 by default
        uvicorn.run(app, host="127.0.0.1", port=8000)
