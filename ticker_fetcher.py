import os
import json
import ssl
import urllib.request
import time
import csv
import io
from datetime import datetime, timedelta

CACHE_FILE = "ticker_cache.json"

def fetch_taiwan_tickers():
    context = ssl._create_unverified_context()
    ticker_map = {}
    
    # Mode 2: Listed stocks, Mode 4: OTC stocks
    for mode, suffix in [("2", ".TW"), ("4", ".TWO")]:
        try:
            url = f"https://isin.twse.com.tw/isin/C_public.jsp?strMode={mode}"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, context=context) as response:
                html = response.read().decode('cp950', errors='ignore')
                
            rows = html.split("<tr>")
            for row in rows:
                tds = row.split("<td")
                if len(tds) < 7:
                    continue
                    
                cfi_col = tds[6].split(">")[1].split("<")[0].strip()
                if cfi_col != "ESVUFR":
                    continue
                    
                first_col = tds[1].split(">")[1].split("<")[0].strip()
                parts = first_col.replace("\u3000", " ").split()
                if not parts:
                    continue
                    
                ticker = parts[0]
                if len(ticker) == 4 and ticker.isdigit():
                    symbol = f"{ticker}{suffix}"
                    name = parts[1] if len(parts) > 1 else ""
                    ticker_map[symbol] = name
        except Exception as e:
            print(f"[Ticker Fetcher] Error fetching Taiwan tickers for mode {mode}: {e}")
            
    return ticker_map

def fetch_us_tickers():
    ticker_map = {}
    try:
        url = "https://raw.githubusercontent.com/Ate329/top-us-stock-tickers/main/tickers/all.csv"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            csv_content = response.read().decode('utf-8', errors='ignore')
            
        reader = csv.reader(io.StringIO(csv_content))
        next(reader, None)  # Skip header
        for row in reader:
            if len(row) >= 2:
                sym = row[0].strip()
                name = row[1].strip()
                if sym.isalpha():  # Filter to ensure valid alphabetic ticker
                    ticker_map[sym] = name
    except Exception as e:
        print(f"[Ticker Fetcher] Error fetching US tickers: {e}")
    return ticker_map

def get_all_tickers(force_refresh=False):
    # Check if cache exists and is fresh (less than 7 days old)
    if not force_refresh and os.path.exists(CACHE_FILE):
        mtime = os.path.getmtime(CACHE_FILE)
        if datetime.now() - datetime.fromtimestamp(mtime) < timedelta(days=7):
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    cache_data = json.load(f)
                    print(f"[Ticker Fetcher] Loaded {len(cache_data['symbols'])} symbols from local cache.")
                    return cache_data["symbols"]
            except Exception as e:
                print(f"[Ticker Fetcher] Error reading cache file: {e}")
                
    print("[Ticker Fetcher] Fetching tickers from online exchanges...")
    tw_map = fetch_taiwan_tickers()
    us_map = fetch_us_tickers()
    
    # Fallback to defaults if online fetch returned nothing
    if not tw_map:
        tw_map = {
            "2330.TW": "台積電", "2317.TW": "鴻海", "2454.TW": "聯發科", 
            "2308.TW": "台達電", "2881.TW": "富邦金", "2882.TW": "國泰金", 
            "2382.TW": "廣達", "3231.TW": "緯創"
        }
    if not us_map:
        us_map = {
            "AAPL": "Apple Inc.", "MSFT": "Microsoft Corporation", "NVDA": "NVIDIA Corporation", 
            "AMZN": "Amazon.com Inc.", "GOOGL": "Alphabet Inc. Class A", "META": "Meta Platforms Inc.", 
            "TSLA": "Tesla Inc.", "NFLX": "Netflix Inc.", "AVGO": "Broadcom Inc.", "QCOM": "QUALCOMM Incorporated"
        }
        
    combined_map = {**tw_map, **us_map}
    combined_symbols = sorted(list(combined_map.keys()))
    
    # Save cache
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "symbols": combined_symbols, 
                "names": combined_map,
                "updated_at": datetime.now().isoformat()
            }, f, ensure_ascii=False, indent=2)
        print(f"[Ticker Fetcher] Saved {len(combined_symbols)} symbols to local cache.")
    except Exception as e:
        print(f"[Ticker Fetcher] Error writing cache file: {e}")
        
    return combined_symbols

def get_ticker_name_map():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cache_data = json.load(f)
                return cache_data.get("names", {})
        except Exception as e:
            print(f"[Ticker Fetcher] Error reading names from cache: {e}")
    return {}

if __name__ == "__main__":
    syms = get_all_tickers(force_refresh=True)
    print(f"Total symbols retrieved: {len(syms)}")
