import time
import argparse
import sys
import os
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

import database

import ticker_fetcher
ALL_SYMBOLS = ticker_fetcher.get_all_tickers()

def get_market_today(symbol: str):
    """Calculate today's date in market's local timezone to prevent start_date > end_date errors in yfinance"""
    from datetime import datetime, timedelta
    utc_now = datetime.utcnow()
    if symbol.upper().endswith(".TW") or symbol.upper().endswith(".TWO"):
        return (utc_now + timedelta(hours=8)).date()
    else:
        return (utc_now - timedelta(hours=5)).date()

def populate_database(limit=None, delay=1.0):
    print("Initializing Database tables...")
    database.init_db()
    
    # Load user's watchlist symbols as well
    watchlist = database.get_watchlist()
    symbols_to_load = sorted(list(set(ALL_SYMBOLS + watchlist)))
    
    if limit:
        symbols_to_load = symbols_to_load[:limit]
        print(f"Limiting populate operation to first {limit} symbols.")
        
    total = len(symbols_to_load)
    print(f"Checking cache status for {total} symbols...")
    
    need_full = []
    need_inc = []
    skipped_count = 0
    
    for symbol in symbols_to_load:
        latest_cached = database.get_latest_cached_date(symbol)
        if not latest_cached:
            need_full.append(symbol)
        else:
            latest_dt = datetime.strptime(latest_cached, "%Y-%m-%d").date()
            market_today = get_market_today(symbol)
            if latest_dt >= market_today:
                skipped_count += 1
            else:
                need_inc.append(symbol)
                
    print(f"Cache status check complete:")
    print(f"  - Up to date: {skipped_count}")
    print(f"  - Need full download (1y): {len(need_full)}")
    print(f"  - Need incremental update (1mo): {len(need_inc)}")
    
    # Helper to download and save in bulk chunks
    def download_and_save_chunks(symbols_list, period_str, chunk_size=100):
        total_syms = len(symbols_list)
        success_count = 0
        
        for idx in range(0, total_syms, chunk_size):
            chunk = symbols_list[idx : idx + chunk_size]
            print(f"Downloading chunk [{idx+1}-{min(idx+chunk_size, total_syms)}/{total_syms}] ({period_str})...")
            
            try:
                # yf.download in bulk
                df = yf.download(chunk, period=period_str, group_by="ticker", progress=False)
                
                # Sleep a little to be polite
                time.sleep(delay)
                
                # Save each ticker
                for sym in chunk:
                    try:
                        if isinstance(df.columns, pd.MultiIndex):
                            if sym in df.columns.levels[0]:
                                ticker_df = df[sym].dropna()
                                if not ticker_df.empty:
                                    bars = []
                                    for bar_idx, row in ticker_df.iterrows():
                                        bars.append({
                                            "date": bar_idx.strftime("%Y-%m-%d"),
                                            "open": float(row["Open"]),
                                            "high": float(row["High"]),
                                            "low": float(row["Low"]),
                                            "close": float(row["Close"]),
                                            "volume": float(row["Volume"])
                                        })
                                    database.save_price_bars(sym, bars)
                                    success_count += 1
                        else:
                            # Single ticker result
                            if not df.empty:
                                ticker_df = df.dropna()
                                bars = []
                                for bar_idx, row in ticker_df.iterrows():
                                    bars.append({
                                        "date": bar_idx.strftime("%Y-%m-%d"),
                                        "open": float(row["Open"]),
                                        "high": float(row["High"]),
                                        "low": float(row["Low"]),
                                        "close": float(row["Close"]),
                                        "volume": float(row["Volume"])
                                    })
                                database.save_price_bars(sym, bars)
                                success_count += 1
                    except Exception as e:
                        print(f"  -> Error saving {sym}: {e}")
            except Exception as e:
                print(f"  -> Bulk download failed for chunk: {e}")
                
        return success_count

    success_full = 0
    success_inc = 0
    
    if need_full:
        print("\n=== Executing Full Downloads (1y) ===")
        success_full = download_and_save_chunks(need_full, "1y")
        
    if need_inc:
        print("\n=== Executing Incremental Updates (1mo) ===")
        success_inc = download_and_save_chunks(need_inc, "1mo")
        
    print("\n=== Pre-fetch Operations Completed ===")
    print(f"Total: {total} | Up to date: {skipped_count} | Full downloaded: {success_full}/{len(need_full)} | Incremental updated: {success_inc}/{len(need_inc)}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pre-populate SQLite price cache politely.")
    parser.add_argument("--limit", type=int, default=None, help="Limit the number of stocks to process.")
    parser.add_argument("--delay", type=float, default=1.5, help="Sleep delay between yfinance downloads.")
    args = parser.parse_args()
    
    populate_database(limit=args.limit, delay=args.delay)
