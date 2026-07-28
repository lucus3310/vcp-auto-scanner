import yfinance as yf
import pandas as pd
from vcp_analyzer import calculate_technical_indicators, analyze_vcp

def main():
    test_symbols = ["AAPL", "MSFT", "NVDA", "TSLA", "TQQQ"]
    print("Starting verification scan on:", test_symbols)
    
    for symbol in test_symbols:
        try:
            print(f"\nScanning {symbol}...")
            # Download 6 months of data
            data = yf.download(symbol, period="6mo", progress=False)
            if data.empty:
                print(f"  Error: No data downloaded for {symbol}")
                continue
                
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.droplevel(1)
                
            df_indicators = calculate_technical_indicators(data)
            if df_indicators.empty:
                print(f"  Error: Failed to calculate indicators for {symbol} (insufficient data)")
                continue
                
            res = analyze_vcp(symbol, df_indicators)
            print(f"  VCP Pattern Detected: {res['VCP']}")
            print(f"  6M Price Increase: {res['Price_Increase_6M']}")
            print(f"  Total Contractions: {res['Contractions']}")
            print(f"  Breakout Detected: {res['Breakout_Detected']}")
            print(f"  RSI: {res['RSI_Value']}, ADX: {res['ADX_Strength']}, Anomaly Free: {res['Anomaly_Free']}")
            print(f"  判定原因: {res['Reason']}")
            
            if len(res['Contraction_List']) > 0:
                print("  Contraction Details:")
                for idx, c in enumerate(res['Contraction_List']):
                    print(f"    C{idx+1}: {c['high_date']} (High=${c['high_val']:.2f}) -> {c['low_date']} (Low=${c['low_val']:.2f}) | Retracement: {(c['retracement']*100).toFixed(1) if hasattr(c['retracement'], 'toFixed') else f'{c['retracement']*100:.1f}'}% | Volatility Width: {c['kc_width']:.4f}")
        except Exception as e:
            print(f"  Error during scan of {symbol}: {str(e)}")

if __name__ == "__main__":
    main()
