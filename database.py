import sqlite3
import os
from datetime import datetime

DB_FILE = "vcp_scanner.db"

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Watchlist Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS watchlist (
        symbol TEXT PRIMARY KEY,
        added_at TEXT
    )
    """)
    
    # 2. Daily Prices Cache Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS daily_prices (
        symbol TEXT,
        date TEXT,
        open REAL,
        high REAL,
        low REAL,
        close REAL,
        volume REAL,
        PRIMARY KEY (symbol, date)
    )
    """)
    
    # 3. Scan History Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS scan_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scan_date TEXT,
        symbol TEXT,
        vcp INTEGER,
        contractions INTEGER,
        price_increase_6m TEXT,
        volatility_decrease TEXT,
        volume_contraction INTEGER,
        breakout_detected INTEGER,
        reason TEXT
    )
    """)
    
    # Run dynamic schema migration to add minervini column if not exists
    try:
        cursor.execute("ALTER TABLE scan_history ADD COLUMN minervini INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass # Already exists
        
    conn.commit()
    conn.close()
    print("Database tables initialized successfully.")

# Watchlist Operations
def get_watchlist():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT symbol FROM watchlist ORDER BY added_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [r['symbol'] for r in rows]

def add_to_watchlist(symbol: str):
    symbol = symbol.strip().upper()
    if not symbol:
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT OR IGNORE INTO watchlist (symbol, added_at) VALUES (?, ?)", 
                       (symbol, datetime.now().isoformat()))
        conn.commit()
    finally:
        conn.close()

def remove_from_watchlist(symbol: str):
    symbol = symbol.strip().upper()
    if not symbol:
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM watchlist WHERE symbol = ?", (symbol,))
        conn.commit()
    finally:
        conn.close()

# Daily Prices Cache Operations
def get_cached_prices(symbol: str, lookback_date: str) -> list:
    """Gets cached prices for a symbol from lookback_date onwards"""
    symbol = symbol.strip().upper()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT date, open, high, low, close, volume 
    FROM daily_prices 
    WHERE symbol = ? AND date >= ? 
    ORDER BY date ASC
    """, (symbol, lookback_date))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_latest_cached_date(symbol: str) -> str:
    """Gets the date of the latest daily bar in cache"""
    symbol = symbol.strip().upper()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(date) as max_date FROM daily_prices WHERE symbol = ?", (symbol,))
    row = cursor.fetchone()
    conn.close()
    return row['max_date'] if row and row['max_date'] else None

def save_price_bars(symbol: str, bars: list):
    """Saves price bars to cache. bars is a list of dicts: {date, open, high, low, close, volume}"""
    symbol = symbol.strip().upper()
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.executemany("""
        INSERT OR REPLACE INTO daily_prices (symbol, date, open, high, low, close, volume)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [(symbol, b['date'], b['open'], b['high'], b['low'], b['close'], b['volume']) for b in bars])
        conn.commit()
    finally:
        conn.close()

# Scan History Operations
def save_scan_results(scan_date: str, results: list):
    """Saves a list of scan results for a specific date"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.executemany("""
        INSERT INTO scan_history 
        (scan_date, symbol, vcp, contractions, price_increase_6m, volatility_decrease, volume_contraction, breakout_detected, reason, minervini)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [(
            scan_date,
            r['Symbol'],
            1 if r['VCP'] else 0,
            r['Contractions'],
            r['Price_Increase_6M'],
            r['Volatility_Decrease'],
            1 if r['Volume_Contraction'] else 0,
            1 if r['Breakout_Detected'] else 0,
            r['Reason'],
            1 if r.get('Minervini_Trend', {}).get('meets_template', False) else 0
        ) for r in results])
        conn.commit()
    finally:
        conn.close()

def get_scan_dates() -> list:
    """Gets a sorted list of unique scan dates in the history"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT scan_date FROM scan_history ORDER BY scan_date DESC")
    rows = cursor.fetchall()
    conn.close()
    return [r['scan_date'] for r in rows]

def get_historical_scan(scan_date: str) -> list:
    """Retrieves all scan results for a specific date"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT symbol as Symbol, vcp as VCP, contractions as Contractions, 
           price_increase_6m as Price_Increase_6M, volatility_decrease as Volatility_Decrease,
           volume_contraction as Volume_Contraction, breakout_detected as Breakout_Detected,
           reason as Reason, COALESCE(minervini, 0) as Minervini
    FROM scan_history 
    WHERE scan_date = ?
    ORDER BY symbol ASC
    """, (scan_date,))
    rows = cursor.fetchall()
    conn.close()
    
    results = []
    for r in rows:
        d = dict(r)
        d['VCP'] = bool(d['VCP'])
        d['Volume_Contraction'] = bool(d['Volume_Contraction'])
        d['Breakout_Detected'] = bool(d['Breakout_Detected'])
        d['Minervini'] = bool(d['Minervini'])
        # Add default fields for display compatibility
        d['ADX_Strength'] = False
        d['DI_Bullish'] = False
        d['RSI_Value'] = 0.0
        d['Anomaly_Free'] = True
        d['Contraction_List'] = []
        results.append(d)
    return results

def get_scan_history_summary() -> list:
    """Gets summary stats for all scan dates in history"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT scan_date, 
           COUNT(*) as total_stocks,
           SUM(vcp) as vcp_count,
           SUM(COALESCE(minervini, 0)) as minervini_count,
           SUM(breakout_detected) as breakout_count
    FROM scan_history
    GROUP BY scan_date
    ORDER BY scan_date DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def delete_historical_scan(scan_date: str):
    """Deletes a specific past scan run by date"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM scan_history WHERE scan_date = ?", (scan_date,))
        conn.commit()
    finally:
        conn.close()

def clear_all_scan_history():
    """Clears all scan history runs"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM scan_history")
        conn.commit()
    finally:
        conn.close()
