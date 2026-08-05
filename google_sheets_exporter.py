from datetime import datetime
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials

def export_to_google_sheets(results, spreadsheet_id, scan_date=None):
    """
    Exports the scan results to a Google Sheet using a single batch update to minimize API calls.
    Filters the results to only include stocks that match VCP or Minervini criteria.
    Includes the scan timestamp in each row.
    """
    if not results:
        print("[Google Sheets] No results provided to export.")
        return
        
    if not scan_date:
        scan_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
    creds_file = 'credentials.json'
    if not os.path.exists(creds_file):
        print(f"[Google Sheets] Error: {creds_file} not found. Skipping export.")
        return
        
    try:
        scope = [
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive'
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_name(creds_file, scope)
        client = gspread.authorize(creds)
        
        sheet = client.open_by_key(spreadsheet_id).sheet1
        
        # Prepare data for batch update
        headers = ['Scan Time', 'Symbol', 'Name', 'VCP', 'Minervini', 'Contractions', 'Volatility Decrease', 'RSI', 'Price Increase 6M', 'Breakout', 'Reason']
        
        data_rows = [headers]
        for r in results:
            if not r.get('VCP') and not r.get('Minervini'):
                continue
                
            row = [
                scan_date,
                r.get('Symbol', ''),
                r.get('Name', ''),
                'Yes' if r.get('VCP') else 'No',
                'Yes' if r.get('Minervini') else 'No',
                r.get('Contractions', 0),
                r.get('Volatility_Decrease', ''),
                round(r.get('RSI_Value', 0), 2) if isinstance(r.get('RSI_Value'), (int, float)) else r.get('RSI_Value', ''),
                r.get('Price_Increase_6M', ''),
                'Yes' if r.get('Breakout_Detected') else 'No',
                r.get('Reason', '')
            ]
            data_rows.append(row)
            
        # Clear the sheet and update with new data in one batch
        sheet.clear()
        
        num_rows = len(data_rows)
        num_cols = len(headers)
        
        if num_rows > 1: # More than just headers
            # Convert column number to letter (A, B, C...)
            def col_num_to_letter(n):
                string = ""
                while n > 0:
                    n, remainder = divmod(n - 1, 26)
                    string = chr(65 + remainder) + string
                return string
                
            end_col_letter = col_num_to_letter(num_cols)
            range_name = f'A1:{end_col_letter}{num_rows}'
            sheet.update(range_name, data_rows)
            print(f"[Google Sheets] Successfully exported {num_rows - 1} matching stocks to Google Sheets using 1 Batch Update API call.")
        else:
            print("[Google Sheets] No stocks matched VCP or Minervini criteria today. Sheet cleared.")
            
    except Exception as e:
        print(f"[Google Sheets] Error exporting to Google Sheets: {e}")

if __name__ == "__main__":
    # Test script usage
    # export_to_google_sheets([{'Symbol': 'TEST', 'VCP': True}], '1aLqh_x_1bHoz2Xhlh_Ha3DTmhASIg32TRmwBPdU9lo0')
    pass
