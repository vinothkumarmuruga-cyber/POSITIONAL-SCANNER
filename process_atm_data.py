import pandas as pd
import os
from datetime import datetime

def process_data():
    # File Paths
    bhav_file = 'BhavCopy_NSE_FO_0_0_0_20260129_F_0000.csv'
    json_file = 'NSE.json'
    output_file = 'ATM_Options_Map.csv'

    if not os.path.exists(bhav_file):
        print(f"Error: {bhav_file} not found.")
        return
    if not os.path.exists(json_file):
        print(f"Error: {json_file} not found.")
        return

    print("Loading NSE Bhavcopy...")
    try:
        df_bhav = pd.read_csv(bhav_file)
    except Exception as e:
        print(f"Failed to read CSV: {e}")
        return

    print("Loading Upstox JSON...")
    try:
        df_json = pd.read_json(json_file)
    except Exception as e:
        print(f"Failed to read JSON: {e}")
        return

    # --- Process Bhavcopy Futures ---
    print("Identifying Near-Month Futures...")
    # Filter for Futures (STF: Stock Futures, IDF: Index Futures)
    # Check if 'FinInstrmTp' exists, else check logic
    if 'FinInstrmTp' not in df_bhav.columns:
        print("Column 'FinInstrmTp' missing in Bhavcopy.")
        return

    futures = df_bhav[df_bhav['FinInstrmTp'].isin(['STF', 'IDF'])].copy()
    
    # Convert Expiry to datetime
    futures['XpryDt'] = pd.to_datetime(futures['XpryDt'])
    
    # Find the nearest expiry for each symbol
    # Sort by date and take the first one per symbol
    futures = futures.sort_values('XpryDt')
    near_futures = futures.groupby('TckrSymb').first().reset_index()
    
    # Keep relevant columns: Symbol, Future Price, Future Expiry
    near_futures = near_futures[['TckrSymb', 'ClsPric', 'XpryDt']]
    near_futures = near_futures.rename(columns={'ClsPric': 'FuturePrice', 'XpryDt': 'FutureExpiryDate'})
    
    print(f"Found {len(near_futures)} symbols with futures.")

    # --- Process Bhavcopy Options ---
    print("Processing Options and finding ATM Strikes...")
    options = df_bhav[df_bhav['OptnTp'].isin(['CE', 'PE'])].copy()
    options['XpryDt'] = pd.to_datetime(options['XpryDt'])
    
    # Join Options with Near Futures to match Expiry and calculate ATM
    # We only want options that match the Near Future Expiry
    merged = pd.merge(options, near_futures, on='TckrSymb')
    
    # Filter: Option Expiry == Future Expiry
    merged = merged[merged['XpryDt'] == merged['FutureExpiryDate']]
    
    # Calculate difference between Strike and Future Price
    merged['Diff'] = abs(merged['StrkPric'] - merged['FuturePrice'])
    
    # Find ATM Strike: Minimal Diff per Symbol
    # Note: We want the same ATM strike for both CE and PE.
    # So we group by Symbol and find min Diff across all its options
    min_diffs = merged.groupby('TckrSymb')['Diff'].min().reset_index()
    
    # Join back to get the rows matching the min diff
    atm_options = pd.merge(merged, min_diffs, on=['TckrSymb', 'Diff'])
    
    # Select columns
    # We expect CE and PE rows for the ATM strike(s)
    # ADDED 'ClsPric' here to preserve the option close price
    atm_rows = atm_options[['TckrSymb', 'XpryDt', 'StrkPric', 'OptnTp', 'FuturePrice', 'ClsPric', 'FinInstrmNm']]
    print(f"Identified {len(atm_rows)} ATM option contracts (CE+PE).")

    # --- Process Upstox JSON ---
    print("Processing Upstox Instrument Keys...")
    
    # Filter segment if available
    if 'segment' in df_json.columns:
        df_json = df_json[df_json['segment'] == 'NSE_FO']
    
    # Convert Expiry from ms timestamp to datetime (normalized to midnight)
    df_json['expiry_dt'] = pd.to_datetime(df_json['expiry'], unit='ms').dt.normalize()
    
    # Normalize keys for merging
    # Bhavcopy: TckrSymb, StrkPric, OptnTp, XpryDt
    # JSON: underlying_symbol, strike_price, instrument_type, expiry_dt
    
    # Ensure Bhavcopy dates are normalized
    atm_rows['XpryDt'] = atm_rows['XpryDt'].dt.normalize()
    
    # Merge
    # We merge on Symbol, Strike, OptionType, Expiry
    result = pd.merge(
        atm_rows,
        df_json,
        left_on=['TckrSymb', 'StrkPric', 'OptnTp', 'XpryDt'],
        right_on=['underlying_symbol', 'strike_price', 'instrument_type', 'expiry_dt'],
        how='inner'
    )
    
    # Select Final Columns
    # Added 'ClsPric' next to 'FuturePrice'
    final_df = result[[
        'TckrSymb', 
        'XpryDt', 
        'StrkPric', 
        'OptnTp', 
        'FuturePrice', 
        'ClsPric',
        'instrument_key', 
        'trading_symbol', 
        'FinInstrmNm'
    ]]
    
    # Rename for clarity
    final_df = final_df.rename(columns={
        'TckrSymb': 'Symbol',
        'XpryDt': 'ExpiryDate',
        'StrkPric': 'StrikePrice',
        'OptnTp': 'OptionType',
        'ClsPric': 'Trigger',
        'FinInstrmNm': 'BhavcopySymbol',
        'trading_symbol': 'UpstoxSymbol'
    })
    
    # Save
    final_df.to_csv(output_file, index=False)
    print(f"Success! Mapped data saved to {output_file} with {len(final_df)} rows.")
    print("Sample rows:")
    print(final_df.head())

if __name__ == "__main__":
    process_data()
