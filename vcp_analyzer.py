import pandas as pd
import numpy as np

# Try importing sklearn, use statistical fallback if not available
try:
    from sklearn.ensemble import IsolationForest
    from sklearn.impute import SimpleImputer
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

# Technical indicators calculation in pure Pandas
def safe_convert_data(df):
    """Robust data cleaning with NaN handling"""
    df = df.copy()
    numeric_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
    
    # Check which of these columns exist
    present_cols = [c for c in numeric_cols if c in df.columns]
    df[present_cols] = df[present_cols].apply(pd.to_numeric, errors='coerce')
    df.dropna(subset=present_cols, how='all', inplace=True)
    df.ffill(inplace=True)
    df.bfill(inplace=True)
    return df

def calculate_technical_indicators(df, atr_period=14, kc_period=20, adx_period=14, rsi_period=14):
    """NaN-safe indicator calculation using pure Pandas/Numpy"""
    df = safe_convert_data(df)
    
    if len(df) < max(atr_period, kc_period, adx_period) * 2:
        return pd.DataFrame()
        
    try:
        # Price moving averages
        df['MA20'] = df['Close'].rolling(20, min_periods=10).mean()
        df['MA50'] = df['Close'].rolling(50, min_periods=25).mean()
        df['MA150'] = df['Close'].rolling(150, min_periods=75).mean()
        df['MA200'] = df['Close'].rolling(200, min_periods=100).mean()
        
        # Center line (EMA 20)
        df['EMA20'] = df['Close'].ewm(span=kc_period, min_periods=kc_period//2, adjust=False).mean()
        
        # ATR Calculation (Wilder's moving average)
        prev_close = df['Close'].shift(1)
        tr1 = df['High'] - df['Low']
        tr2 = (df['High'] - prev_close).abs()
        tr3 = (df['Low'] - prev_close).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df['ATR'] = tr.ewm(alpha=1/atr_period, adjust=False).mean()
        
        # Keltner Channels width
        df['Upper_KC'] = df['EMA20'] + 2 * df['ATR']
        df['Lower_KC'] = df['EMA20'] - 2 * df['ATR']
        df['KC_Width'] = (df['Upper_KC'] - df['Lower_KC']) / df['EMA20']
        
        # RSI Calculation (Wilder's smooth)
        delta = df['Close'].diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.ewm(alpha=1/rsi_period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/rsi_period, adjust=False).mean()
        rs = avg_gain / (avg_loss + 1e-8)
        df['RSI'] = 100 - (100 / (1 + rs))
        
        # ADX Calculation (Wilder's directional movement)
        prev_high = df['High'].shift(1)
        prev_low = df['Low'].shift(1)
        
        plus_dm = df['High'] - prev_high
        minus_dm = prev_low - df['Low']
        
        plus_dm_clean = np.where((plus_dm > minus_dm) & (plus_dm > 0), plus_dm, 0.0)
        minus_dm_clean = np.where((minus_dm > plus_dm) & (minus_dm > 0), minus_dm, 0.0)
        
        plus_dm_ser = pd.Series(plus_dm_clean, index=df.index)
        minus_dm_ser = pd.Series(minus_dm_clean, index=df.index)
        
        tr_smooth = tr.ewm(alpha=1/adx_period, adjust=False).mean()
        plus_dm_smooth = plus_dm_ser.ewm(alpha=1/adx_period, adjust=False).mean()
        minus_dm_smooth = minus_dm_ser.ewm(alpha=1/adx_period, adjust=False).mean()
        
        df['PlusDI'] = 100 * (plus_dm_smooth / (tr_smooth + 1e-8))
        df['MinusDI'] = 100 * (minus_dm_smooth / (tr_smooth + 1e-8))
        
        dx = 100 * (df['PlusDI'] - df['MinusDI']).abs() / (df['PlusDI'] + df['MinusDI'] + 1e-8)
        df['ADX'] = dx.ewm(alpha=1/adx_period, adjust=False).mean()
        
        # Anomaly Detection
        if SKLEARN_AVAILABLE:
            imputer = SimpleImputer(strategy='median')
            clean_data = imputer.fit_transform(df[['ATR', 'Volume']])
            model = IsolationForest(contamination=0.1, random_state=42)
            df['Anomaly_Score'] = model.fit_predict(clean_data)
        else:
            # Fallback to Z-score anomaly detection
            atr_clean = df['ATR'].fillna(df['ATR'].median())
            vol_clean = df['Volume'].fillna(df['Volume'].median())
            
            atr_z = (atr_clean - atr_clean.mean()) / (atr_clean.std() + 1e-8)
            vol_z = (vol_clean - vol_clean.mean()) / (vol_clean.std() + 1e-8)
            
            is_outlier = (atr_z.abs() > 3.0) | (vol_z.abs() > 3.0)
            df['Anomaly_Score'] = np.where(is_outlier, -1, 1)
            
        return df.dropna(subset=['ATR', 'RSI', 'ADX', 'KC_Width'])
        
    except Exception as e:
        print(f"Indicator calculation error: {str(e)}")
        return pd.DataFrame()

# Swing-based VCP pattern search
def find_swings(df, window=5):
    """Find local swing highs and lows"""
    highs = df['High'].values
    lows = df['Low'].values
    n = len(df)
    
    swing_highs = []
    swing_lows = []
    
    for i in range(window, n - window):
        if highs[i] == max(highs[i-window : i+window+1]):
            swing_highs.append((i, highs[i]))
        if lows[i] == min(lows[i-window : i+window+1]):
            swing_lows.append((i, lows[i]))
            
    return swing_highs, swing_lows

def get_swing_contractions(df, window=5):
    """Pairs alternating swing highs/lows and computes retracements"""
    sh, sl = find_swings(df, window)
    swings = []
    for idx, val in sh:
        swings.append({'idx': idx, 'type': 'high', 'val': val})
    for idx, val in sl:
        swings.append({'idx': idx, 'type': 'low', 'val': val})
    swings.sort(key=lambda x: x['idx'])
    
    # Alternate highs and lows (keep the most extreme one if consecutive)
    alt_swings = []
    for s in swings:
        if not alt_swings:
            alt_swings.append(s)
        else:
            prev = alt_swings[-1]
            if prev['type'] == s['type']:
                if prev['type'] == 'high' and s['val'] > prev['val']:
                    alt_swings[-1] = s
                elif prev['type'] == 'low' and s['val'] < prev['val']:
                    alt_swings[-1] = s
            else:
                alt_swings.append(s)
                
    # Create pullbacks
    pullbacks = []
    for i in range(len(alt_swings) - 1):
        s1 = alt_swings[i]
        s2 = alt_swings[i+1]
        # Pullback from high to low
        if s1['type'] == 'high' and s2['type'] == 'low':
            retracement = (s1['val'] - s2['val']) / s1['val']
            
            # KC Width in this pullback range
            kc_width = df['KC_Width'].iloc[s1['idx'] : s2['idx'] + 1].mean()
            
            # Volume during this pullback
            avg_volume = df['Volume'].iloc[s1['idx'] : s2['idx'] + 1].mean()
            
            pullbacks.append({
                'high_idx': int(s1['idx']),
                'low_idx': int(s2['idx']),
                'high_date': df.index[s1['idx']].strftime('%Y-%m-%d'),
                'low_date': df.index[s2['idx']].strftime('%Y-%m-%d'),
                'high_val': float(s1['val']),
                'low_val': float(s2['val']),
                'retracement': float(retracement),
                'kc_width': float(kc_width),
                'avg_volume': float(avg_volume)
            })
            
    return pullbacks

# Mark Minervini Trend Template Check
def check_minervini_trend(df):
    """
    Checks if the stock meets Mark Minervini's Trend Template rules:
    1. Close > 150 MA and Close > 200 MA
    2. 150 MA > 200 MA
    3. 200 MA is trending up (current 200 MA > 200 MA 20 days ago)
    4. 50 MA > 150 MA and 50 MA > 200 MA
    5. Close > 50 MA
    6. Close is at least 30% above 52-week low
    7. Close is within 25% of 52-week high
    """
    res = {
        'meets_template': False,
        'rules': {
            'rule1_close_above_ma150_200': False,
            'rule2_ma150_above_ma200': False,
            'rule3_ma200_trending_up': False,
            'rule4_ma50_above_ma150_200': False,
            'rule5_close_above_ma50': False,
            'rule6_above_52w_low_30pct': False,
            'rule7_within_52w_high_25pct': False
        },
        'values': {
            'close': 0.0,
            'ma50': 0.0,
            'ma150': 0.0,
            'ma200': 0.0,
            'ma200_pct_change': 0.0,
            'low_52w': 0.0,
            'high_52w': 0.0,
            'pct_above_52w_low': 0.0,
            'pct_below_52w_high': 0.0
        }
    }
    
    if df.empty or len(df) < 50:
        return res
        
    try:
        import math
        
        def sanitize(val):
            try:
                val = float(val)
                if math.isnan(val) or math.isinf(val):
                    return 0.0
                return val
            except Exception:
                return 0.0

        close = float(df['Close'].iloc[-1])
        ma50 = float(df['MA50'].iloc[-1]) if 'MA50' in df.columns else 0.0
        ma150 = float(df['MA150'].iloc[-1]) if 'MA150' in df.columns else float(df['Close'].rolling(150, min_periods=10).mean().iloc[-1])
        ma200 = float(df['MA200'].iloc[-1]) if 'MA200' in df.columns else float(df['Close'].rolling(200, min_periods=10).mean().iloc[-1])
        
        # Check MA200 trend (20 trading days ago)
        ma200_series = df['MA200'] if 'MA200' in df.columns else df['Close'].rolling(200, min_periods=10).mean()
        ma200_prev = float(ma200_series.iloc[-20]) if len(ma200_series) > 20 else float(ma200_series.iloc[0])
        
        ma200_val = sanitize(ma200)
        ma200_prev_val = sanitize(ma200_prev)
        ma200_trending_up = ma200_val > ma200_prev_val and ma200_val != 0.0
        ma200_pct_change = ((ma200_val - ma200_prev_val) / (ma200_prev_val + 1e-8)) * 100 if ma200_prev_val != 0.0 else 0.0
        
        # 52-week High and Low (250 trading days)
        window_52w = min(250, len(df))
        low_52w = float(df['Low'].tail(window_52w).min())
        high_52w = float(df['High'].tail(window_52w).max())
        
        low_52w_val = sanitize(low_52w)
        high_52w_val = sanitize(high_52w)
        
        pct_above_52w_low = ((close - low_52w_val) / (low_52w_val + 1e-8)) * 100 if low_52w_val != 0.0 else 0.0
        pct_below_52w_high = ((high_52w_val - close) / (high_52w_val + 1e-8)) * 100 if high_52w_val != 0.0 else 0.0
        
        ma50_val = sanitize(ma50)
        ma150_val = sanitize(ma150)
        
        r1 = close > ma150_val and close > ma200_val if ma150_val != 0.0 and ma200_val != 0.0 else False
        r2 = ma150_val > ma200_val if ma150_val != 0.0 and ma200_val != 0.0 else False
        r3 = bool(ma200_trending_up)
        r4 = ma50_val > ma150_val and ma50_val > ma200_val if ma50_val != 0.0 and ma150_val != 0.0 and ma200_val != 0.0 else False
        r5 = close > ma50_val if ma50_val != 0.0 else False
        r6 = pct_above_52w_low >= 30.0 if low_52w_val != 0.0 else False
        r7 = pct_below_52w_high <= 25.0 if high_52w_val != 0.0 else False
        
        res['rules'] = {
            'rule1_close_above_ma150_200': bool(r1),
            'rule2_ma150_above_ma200': bool(r2),
            'rule3_ma200_trending_up': bool(r3),
            'rule4_ma50_above_ma150_200': bool(r4),
            'rule5_close_above_ma50': bool(r5),
            'rule6_above_52w_low_30pct': bool(r6),
            'rule7_within_52w_high_25pct': bool(r7)
        }
        
        res['values'] = {
            'close': sanitize(close),
            'ma50': ma50_val,
            'ma150': ma150_val,
            'ma200': ma200_val,
            'ma200_pct_change': sanitize(ma200_pct_change),
            'low_52w': low_52w_val,
            'high_52w': high_52w_val,
            'pct_above_52w_low': sanitize(pct_above_52w_low),
            'pct_below_52w_high': sanitize(pct_below_52w_high)
        }
        
        res['meets_template'] = all([r1, r2, r3, r4, r5, r6, r7])
    except Exception as e:
        print(f"Error checking Minervini trend template: {e}")
        
    return res

# VCP Analysis logic
def analyze_vcp(symbol, df, min_base_duration=30, volume_spike_multiplier=1.5, contraction_ratio_threshold=0.9, min_volume=100000):
    """
    Analyzes whether a stock matches the Volatility Contraction Pattern (VCP).
    Returns a result dict.
    """
    result = {
        'Symbol': symbol,
        'VCP': False,
        'Minervini': False,
        'Contractions': 0,
        'Contraction_List': [],
        'Volatility_Decrease': 'N/A',
        'ADX_Strength': False,
        'DI_Bullish': False,
        'RSI_Value': 0.0,
        'Price_Increase_6M': '0%',
        'Anomaly_Free': False,
        'Volume_Contraction': False,
        'Breakout_Detected': False,
        'Minervini_Trend': {
            'meets_template': False,
            'rules': {
                'rule1_close_above_ma150_200': False,
                'rule2_ma150_above_ma200': False,
                'rule3_ma200_trending_up': False,
                'rule4_ma50_above_ma150_200': False,
                'rule5_close_above_ma50': False,
                'rule6_above_52w_low_30pct': False,
                'rule7_within_52w_high_25pct': False
            },
            'values': {}
        },
        'Reason': 'Initial error'
    }
    
    try:
        if df.empty or len(df) < min_base_duration:
            result['Reason'] = 'Insufficient data'
            return result
            
        # Check volume liquidity (20-day average volume)
        recent_20_avg_vol = df['Volume'].tail(20).mean()
        if recent_20_avg_vol < min_volume:
            result['Reason'] = f'Low volume (20-day avg: {int(recent_20_avg_vol):,} < {min_volume:,})'
            return result
            
        # 1. General technical metrics populated early (6M lookback approx 120 trading days)
        start_idx = max(0, len(df) - 120)
        start_price = df['Close'].iloc[start_idx]
        end_price = df['Close'].iloc[-1]
        price_increase = (end_price - start_price) / start_price
        result['Price_Increase_6M'] = f"{price_increase*100:.1f}%"
        
        result.update({
            'ADX_Strength': bool(df['ADX'].iloc[-1] > 25),
            'DI_Bullish': bool(df['PlusDI'].iloc[-1] > df['MinusDI'].iloc[-1]),
            'RSI_Value': float(round(df['RSI'].iloc[-1], 1)),
            'Anomaly_Free': bool(df['Anomaly_Score'].iloc[-1] == 1),
            'Volatility_Decrease': f"{(df['KC_Width'].iloc[-60:-30].mean()/df['KC_Width'].iloc[-10:].mean() - 1)*100:.1f}%" if len(df) > 60 else 'N/A'
        })
        
        # Rule: current price should be > 50-day moving average and 6M price increase should be positive (or > 15-30% for a strong template)
        current_close = df['Close'].iloc[-1]
        ma50_val = df['MA50'].iloc[-1]
        
        # We check that price is in general uptrend
        if current_close < ma50_val:
            result['Reason'] = 'Price below 50 MA (no uptrend)'
            return result
            
        # 2. Find contractions using swing pullbacks
        # We search swing pullbacks in the last 120 trading days (approx 6 months)
        recent_df = df.tail(120)
        pullbacks = get_swing_contractions(recent_df, window=5)
        
        if len(pullbacks) < 2:
            result['Reason'] = f'Found {len(pullbacks)} contraction(s), need at least 2'
            return result
            
        # We examine the last few pullbacks to see if they form a contracting series
        # In VCP, the newest pullbacks are at the end of the list
        # Let's take the last 2 to 5 pullbacks
        candidate_pullbacks = pullbacks[-4:] # Look at up to last 4 pullbacks
        
        # Check if the retracement drops sequentially (each is smaller than the previous)
        valid_contractions = True
        kc_contracting = True
        
        for idx in range(1, len(candidate_pullbacks)):
            prev_p = candidate_pullbacks[idx - 1]
            curr_p = candidate_pullbacks[idx]
            
            # Retracement should shrink (curr_retracement < prev_retracement * threshold)
            if curr_p['retracement'] > prev_p['retracement'] * contraction_ratio_threshold:
                valid_contractions = False
                
            # Keltner Channel width should also contract (volatility decreasing)
            if curr_p['kc_width'] > prev_p['kc_width']:
                kc_contracting = False
                
        result['Contractions'] = len(candidate_pullbacks)
        result['Contraction_List'] = candidate_pullbacks
        
        if not valid_contractions:
            result['Reason'] = 'Contraction retracements are not sequentially shrinking'
            return result
            
        # 3. Volume Contraction Check
        # Volume should contract during the latest consolidation phase (less supply coming to market)
        recent_20_avg_vol = df['Volume'].rolling(20).mean().iloc[-1]
        latest_pullback_vol = candidate_pullbacks[-1]['avg_volume']
        
        # The latest pullback average volume should be less than the 20-day average
        result['Volume_Contraction'] = bool(latest_pullback_vol < recent_20_avg_vol * 0.9)
        
        # 4. Breakout check
        # Breakout occurs if the current price closes above the recent resistance
        # We calculate the resistance as the highest high of the last 20 days (excluding today)
        resistance = df['High'].iloc[-20:-1].max()
        
        # Today's volume spike compared to 20-day average volume
        volume_spike = df['Volume'].iloc[-1] > recent_20_avg_vol * volume_spike_multiplier
        
        result['Breakout_Detected'] = bool(current_close > resistance and volume_spike)
        
        # 5. Technical strength indicators already updated early
        
        # 6. Final VCP decision
        # A valid VCP base is established if:
        # - We have valid shrinking contractions
        # - KC volatility is contracting
        # - Volume contracts during consolidation
        # - Anomaly score is clean (no weird price/volume outliers)
        result['VCP'] = all([
            valid_contractions,
            kc_contracting,
            result['Volume_Contraction'],
            result['Anomaly_Free']
        ])
        
        if result['VCP']:
            if result['Breakout_Detected']:
                result['Reason'] = 'VCP base formed with ACTIVE BREAKOUT'
            else:
                result['Reason'] = 'VCP base formed (consolidation phase)'
        else:
            reasons = []
            if not valid_contractions:
                reasons.append("Non-shrinking contractions")
            if not kc_contracting:
                reasons.append("KC width not contracting")
            if not result['Volume_Contraction']:
                reasons.append("Volume not contracting")
            if not result['Anomaly_Free']:
                reasons.append("Anomaly detected")
            result['Reason'] = "Failed checks: " + ", ".join(reasons)
            
        # Check Minervini Trend Template
        result['Minervini_Trend'] = check_minervini_trend(df)
        result['Minervini'] = result['Minervini_Trend']['meets_template']
            
    except Exception as e:
        result['Reason'] = f"Analysis error: {str(e)}"
        
    return result
