import streamlit as st
import pandas as pd
import requests
import math
import os
import time
import gzip
import shutil
from datetime import datetime, timedelta, timezone
import concurrent.futures
import zipfile

# IST Offset
IST_OFFSET = timedelta(hours=5, minutes=30)
IST = timezone(IST_OFFSET)

def get_ist_now():
    return datetime.now(IST)

# Set page configuration
st.set_page_config(page_title="Positional Stock Option Scanner", layout="wide")

# Custom CSS for compact layout and button-like tabs
st.markdown("""
    <style>
        .block-container {
            padding-top: 1rem !important;
            padding-bottom: 1rem !important;
        }
        h1 {
            font-size: 1.8rem !important;
            margin-bottom: 0rem !important;
            white-space: nowrap !important;
        }
        h2 {
            font-size: 1.1rem !important;
            padding-top: 0.2rem !important;
            margin-bottom: 0.1rem !important;
        }
        h3 {
            font-size: 1.0rem !important;
            padding-top: 0.1rem !important;
            margin-bottom: 0.1rem !important;
        }
        
        /* Tab Styling */
        .stTabs [data-baseweb="tab-list"] {
            gap: 10px;
        }
        .stTabs [data-baseweb="tab"] {
            height: 45px;
            white-space: pre-wrap;
            background-color: #f0f2f6;
            border-radius: 5px;
            padding: 10px 20px;
            font-size: 1.1rem;
            font-weight: 600;
            border: 1px solid #d6d6d6;
        }
        .stTabs [aria-selected="true"] {
            background-color: #007bff;
            color: white !important;
            border-color: #007bff;
        }
        
        /* Prevent graying out during refresh */
        .stApp {
            transition: none !important;
        }
        [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
            opacity: 1 !important;
            transition: none !important;
        }
        
        /* Hide File Uploader Instructions */
        [data-testid="stFileUploaderDropzone"] div div span {
           display: none !important;
        }
        [data-testid="stFileUploaderDropzone"] div div small {
           display: none !important;
        }
        
        /* Force Dataframe Font Weight */
        div[data-testid="stDataFrame"] {
            font-weight: 600 !important;
        }
    </style>
""", unsafe_allow_html=True)

import json
import re

# Paths for persistent storage
DATA_DIR = 'data'
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

BLACKLIST_FILE = os.path.join(DATA_DIR, 'blacklist.json')
TOKEN_FILE = os.path.join(DATA_DIR, 'token.json')
META_FILE = os.path.join(DATA_DIR, 'meta.json')
LTP_CACHE_FILE = os.path.join(DATA_DIR, 'ltp_cache.json')

FILES = {
    'Monthly': os.path.join(DATA_DIR, 'monthly.csv'),
    'Weekly': os.path.join(DATA_DIR, 'weekly.csv'),
    'Intraday': os.path.join(DATA_DIR, 'intraday.csv')
}

def load_meta():
    if os.path.exists(META_FILE):
        try:
            with open(META_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_meta(key, date_str):
    try:
        meta = load_meta()
        meta[key] = date_str
        with open(META_FILE, 'w') as f:
            json.dump(meta, f)
    except:
        pass

def load_ltp_cache():
    if os.path.exists(LTP_CACHE_FILE):
        try:
            with open(LTP_CACHE_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_ltp_cache(new_data):
    try:
        cache = load_ltp_cache()
        cache.update(new_data)
        with open(LTP_CACHE_FILE, 'w') as f:
            json.dump(cache, f)
    except:
        pass

def extract_date_from_filename(filename):
    # Regex to find 8-digit date like 20260130
    match = re.search(r'(\d{8})', filename)
    if match:
        d = match.group(1)
        # Format as YYYY-MM-DD
        return f"{d[:4]}-{d[4:6]}-{d[6:]}"
    return None

def extract_csv_from_zip(zip_file):
    try:
        # zip_file is a UploadedFile object from streamlit
        with zipfile.ZipFile(zip_file) as z:
            # Find the first CSV file in the ZIP
            csv_files = [f for f in z.namelist() if f.lower().endswith('.csv')]
            if not csv_files:
                st.error("No CSV file found in the ZIP archive.")
                return None, None
            
            # Extract the first CSV found
            csv_filename = csv_files[0]
            with z.open(csv_filename) as f:
                return f.read(), csv_filename
    except Exception as e:
        st.error(f"Error extracting ZIP file: {e}")
        return None, None

def load_token():
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, 'r') as f:
                data = json.load(f)
                if data.get('date') == get_ist_now().strftime('%Y-%m-%d'):
                    return data.get('token', '')
        except:
            pass
    return ''

def save_token(token):
    try:
        data = {
            'date': get_ist_now().strftime('%Y-%m-%d'),
            'token': token
        }
        with open(TOKEN_FILE, 'w') as f:
            json.dump(data, f)
    except:
        pass

def load_blacklist():
    if os.path.exists(BLACKLIST_FILE):
        try:
            with open(BLACKLIST_FILE, 'r') as f:
                data = json.load(f)
                if data.get('date') == get_ist_now().strftime('%Y-%m-%d'):
                    return set(data.get('keys', []))
        except:
            pass
    return set()

def save_blacklist(keys):
    try:
        data = {
            'date': get_ist_now().strftime('%Y-%m-%d'),
            'keys': list(keys)
        }
        with open(BLACKLIST_FILE, 'w') as f:
            json.dump(data, f)
    except:
        pass

# Constant for NSE JSON
NSE_JSON_PATH = 'NSE.json'

@st.cache_data
def load_nse_json():
    if os.path.exists(NSE_JSON_PATH):
        try:
            df = pd.read_json(NSE_JSON_PATH)
            # Pre-process JSON
            if 'segment' in df.columns:
                df = df[df['segment'] == 'NSE_FO']
            df['expiry_dt'] = pd.to_datetime(df['expiry'], unit='ms').dt.normalize()
            return df
        except Exception as e:
            st.error(f"Error loading NSE.json: {e}")
            return pd.DataFrame()
    else:
        st.error(f"NSE.json not found at {NSE_JSON_PATH}")
        return pd.DataFrame()

def process_bhavcopy(bhav_file, df_json, target_expiry_index=0):
    try:
        df_bhav = pd.read_csv(bhav_file)
        
        # Check required columns
        required_cols = ['FinInstrmTp', 'TckrSymb', 'XpryDt', 'ClsPric', 'StrkPric', 'OptnTp', 'HghPric', 'LwPric', 'LastPric']
        if not all(col in df_bhav.columns for col in required_cols):
            st.error(f"Uploaded file missing required columns: {required_cols}")
            return pd.DataFrame()

        # --- Process Bhavcopy Futures ---
        futures = df_bhav[df_bhav['FinInstrmTp'].isin(['STF', 'IDF'])].copy()
        if futures.empty:
            st.warning("No Futures data found in uploaded file.")
            return pd.DataFrame()

        futures['XpryDt'] = pd.to_datetime(futures['XpryDt'])
        
        # Filter out past expiries (Keep today and future)
        # We use IST time to match the environment's expectation
        ist_now = get_ist_now()
        today = ist_now.replace(hour=0, minute=0, second=0, microsecond=0).replace(tzinfo=None)
        
        futures = futures[futures['XpryDt'] >= today]
        if futures.empty:
            st.warning("No future expiries found in the uploaded file.")
            return pd.DataFrame()

        futures = futures.sort_values('XpryDt')
        
        # Identify unique expiry dates available in the bhavcopy
        available_expiries = sorted(futures['XpryDt'].unique())
        
        if not available_expiries:
            st.warning("No future expiry dates found in the uploaded file.")
            return pd.DataFrame(), None, []

        # Select target expiry based on index (0 for Near, 1 for Next)
        if target_expiry_index >= len(available_expiries):
            # Fallback to the latest available if index is out of range
            target_expiry = available_expiries[-1]
        else:
            target_expiry = available_expiries[target_expiry_index]

        # Filter futures for the target expiry per symbol
        near_futures = futures[futures['XpryDt'] == target_expiry].copy()
        
        # If a symbol doesn't have the target expiry, it will be skipped
        near_futures = near_futures[['TckrSymb', 'ClsPric', 'XpryDt']]
        near_futures = near_futures.rename(columns={'ClsPric': 'FuturePrice', 'XpryDt': 'FutureExpiryDate'})

        # --- Process Bhavcopy Options ---
        options = df_bhav[df_bhav['OptnTp'].isin(['CE', 'PE'])].copy()
        if options.empty:
            st.warning("No Options data found in uploaded file.")
            return pd.DataFrame(), target_expiry, available_expiries

        options['XpryDt'] = pd.to_datetime(options['XpryDt'])

        # Merge Options with selected Futures expiry
        merged = pd.merge(options, near_futures, on='TckrSymb')
        merged = merged[merged['XpryDt'] == merged['FutureExpiryDate']]
        
        # Calculate ATM
        merged['Diff'] = abs(merged['StrkPric'] - merged['FuturePrice'])
        
        # Find best strike per symbol (Minimize Diff, then tie-break with StrikePrice)
        # This ensures only ONE strike is selected per symbol, eliminating duplicates
        best_strikes = merged[['TckrSymb', 'StrkPric', 'Diff']].drop_duplicates()
        best_strikes = best_strikes.sort_values(by=['TckrSymb', 'Diff', 'StrkPric'])
        best_strikes = best_strikes.groupby('TckrSymb').first().reset_index()
        
        atm_options = pd.merge(merged, best_strikes[['TckrSymb', 'StrkPric']], on=['TckrSymb', 'StrkPric'])
        atm_rows = atm_options[['TckrSymb', 'XpryDt', 'StrkPric', 'OptnTp', 'FuturePrice', 'ClsPric', 'FinInstrmNm', 'HghPric', 'LwPric', 'LastPric']].copy()
        
        # Normalize dates for merging
        atm_rows['XpryDt'] = atm_rows['XpryDt'].dt.normalize()

        # Merge with Upstox JSON
        result = pd.merge(
            atm_rows,
            df_json,
            left_on=['TckrSymb', 'StrkPric', 'OptnTp', 'XpryDt'],
            right_on=['underlying_symbol', 'strike_price', 'instrument_type', 'expiry_dt'],
            how='inner'
        )

        if result.empty and not atm_rows.empty:
            st.error("Data mismatch: Found options in Bhavcopy but couldn't find them in NSE.json. Please update NSE.json via the sidebar.")

        final_df = result[[
            'TckrSymb', 'XpryDt', 'StrkPric', 'OptnTp', 
            'FuturePrice', 'ClsPric', 'instrument_key',
            'HghPric', 'LwPric', 'LastPric'
        ]]

        final_df = final_df.rename(columns={
            'TckrSymb': 'Symbol',
            'XpryDt': 'ExpiryDate',
            'StrkPric': 'StrikePrice',
            'OptnTp': 'OptionType',
            'ClsPric': 'Trigger',
            'HghPric': 'HighPrice',
            'LwPric': 'LowPrice',
            'LastPric': 'LastPrice'
        })
        
        # Calculate Camarilla R4
        # Formula: Close + (High - Low) * 1.1 / 2
        final_df['Camarilla_R4'] = final_df['Trigger'] + (final_df['HighPrice'] - final_df['LowPrice']) * 1.1 / 2

        # Multiply Trigger by 2 (User Rule)
        if 'Trigger' in final_df.columns:
            final_df['Trigger'] = final_df['Trigger'] * 2
            
        return final_df, target_expiry, available_expiries

    except Exception as e:
        st.error(f"Error processing file: {e}")
        return pd.DataFrame(), None, []

def fetch_ltp(instrument_keys, token):
    if not token:
        return {}
    
    url = "https://api.upstox.com/v3/market-quote/ltp"
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}'
    }
    
    batch_size = 50
    ltp_map = {}
    
    batches = [instrument_keys[i:i + batch_size] for i in range(0, len(instrument_keys), batch_size)]
    
    def fetch_batch(batch):
        params = {'instrument_key': ','.join(batch)}
        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'success':
                    quotes = data.get('data', {})
                    result = {}
                    for key, details in quotes.items():
                        inst_token = details.get('instrument_token')
                        last_price = details.get('last_price')
                        if inst_token is not None:
                            result[inst_token] = last_price
                    return result
        except Exception:
            pass
        return {}
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(fetch_batch, batch) for batch in batches]
        for future in concurrent.futures.as_completed(futures):
            try:
                batch_result = future.result()
                if batch_result:
                    ltp_map.update(batch_result)
            except Exception:
                pass
    
    return ltp_map

def display_option_chain(df, access_token, key_suffix):
    st.caption(f"Last Updated: {get_ist_now().strftime('%H:%M:%S')} IST")
    if df.empty:
        st.info("No data to display. Please upload a valid Bhavcopy in the sidebar.")
        return

    # Fetch LTP if token provided
    if access_token:
        all_keys = df['instrument_key'].dropna().unique().tolist()
        
        # Time-based Fetch Logic
        ist_now = get_ist_now()
        current_time = ist_now.time()
        start_time = datetime.strptime("09:00", "%H:%M").time()
        end_time = datetime.strptime("15:40", "%H:%M").time()
        
        is_market_hours = start_time <= current_time <= end_time
        
        # Load Cache
        ltp_cache = load_ltp_cache()
        
        # Identify missing keys
        missing_keys = [k for k in all_keys if k not in ltp_cache]
        
        # Check if user requested a manual refresh
        force_refresh = st.session_state.get('force_refresh_ltp', False)
        
        should_fetch = False
        fetch_reason = ""
        
        if is_market_hours:
            should_fetch = True
            fetch_reason = "Live Market Update"
        elif force_refresh:
            should_fetch = True
            fetch_reason = "Manual Refresh"
            # Reset the flag after planning to fetch
            st.session_state['force_refresh_ltp'] = False
        elif missing_keys:
            should_fetch = True
            fetch_reason = "Populating Missing Data"
        
        ltp_data = {}
        
        if should_fetch:
            keys_to_fetch = all_keys if is_market_hours else missing_keys
            # Fetch silently
            fetched_data = fetch_ltp(keys_to_fetch, access_token)
            if fetched_data:
                save_ltp_cache(fetched_data)
                # Reload cache to get complete set
                ltp_cache = load_ltp_cache()
        
        # Use data from cache
        ltp_data = {k: ltp_cache.get(k, 0.0) for k in all_keys}
        
        df['ltp'] = df['instrument_key'].map(ltp_data).fillna(0.0)
    else:
        df['ltp'] = 0.0
        st.warning("Enter Access Token in sidebar to see live LTP.")

    # If Intraday, replace Trigger with Camarilla_R4
    if key_suffix == 'Intraday' and 'Camarilla_R4' in df.columns:
        df['Trigger'] = df['Camarilla_R4']

    # Calculate Change %
    def calculate_numeric_change(row):
        try:
            ocp = row['Trigger']
            ltp = row['ltp']
            if ocp > 0 and ltp > 0:
                return (ltp / ocp * 100)
            return 0.0
        except:
            return 0.0

    df['change_val'] = df.apply(calculate_numeric_change, axis=1)
    df['change %'] = df['change_val']

    # --- Intraday Blacklist Logic ---
    if key_suffix == 'Intraday':
        # Load existing blacklist
        blacklist = load_blacklist()
        
        # Check time condition (before 09:30)
        current_time = get_ist_now().time()
        cutoff_time = datetime.strptime("09:30", "%H:%M").time()
        
        if current_time < cutoff_time:
            # Identify new violators
            violators = df[df['change %'] >= 100]['instrument_key'].tolist()
            if violators:
                blacklist.update(violators)
                save_blacklist(blacklist)
        
        # Filter out blacklisted keys
        if blacklist:
            original_count = len(df)
            df = df[~df['instrument_key'].isin(blacklist)]
            filtered_count = len(df)
            diff = original_count - filtered_count
            # if diff > 0:
            #     st.caption(f"ℹ️ {diff} symbols hidden (Change % >= 100 before 09:30)")

    # Split Calls/Puts
    calls_df = df[df['OptionType'] == 'CE'].copy()
    puts_df = df[df['OptionType'] == 'PE'].copy()

    # Sort
    calls_df = calls_df.sort_values(by='change %', ascending=False)
    puts_df = puts_df.sort_values(by='change %', ascending=False)

    display_cols = ['Symbol', 'StrikePrice', 'Trigger', 'ltp', 'change %']
    
    # Styling
    def color_change(val):
        if isinstance(val, (int, float)):
            if val >= 100:
                return 'background-color: darkgreen; color: white'
            elif val >= 90:
                return 'background-color: lightgreen; color: black'
        return ''

    format_dict = {
        'change %': '{:.2f}%',
        'Trigger': '{:.2f}',
        'ltp': '{:.2f}',
        'StrikePrice': '{:.2f}'
    }

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Calls (CE)")
        st.dataframe(
            calls_df[display_cols].style
            .map(color_change, subset=['change %'])
            .format(format_dict)
            .set_properties(**{'font-weight': '600', 'text-align': 'center', 'font-size': '16px'}),
            hide_index=True, 
            use_container_width=True,
            height=1800
        )

    with col2:
        st.subheader("Puts (PE)")
        st.dataframe(
            puts_df[display_cols].style
            .map(color_change, subset=['change %'])
            .format(format_dict)
            .set_properties(**{'font-weight': '600', 'text-align': 'center', 'font-size': '16px'}),
            hide_index=True, 
            use_container_width=True,
            height=1800
        )

# --- Configuration Logic (Before Sidebar) ---
# Check if we should enter "Client View" (No Sidebar, Token from Secrets)
# To see the sidebar (Admin View), remove or comment out UPSTOX_ACCESS_TOKEN in .streamlit/secrets.toml
is_client_view = "UPSTOX_ACCESS_TOKEN" in st.secrets and st.secrets["UPSTOX_ACCESS_TOKEN"].strip() != ""

if is_client_view:
    # CLIENT VIEW DEFAULTS
    access_token = st.secrets["UPSTOX_ACCESS_TOKEN"]
    # Hide sidebar completely for clients
    st.markdown("""
    <style>
        [data-testid="stSidebar"] {display: none;}
    </style>
    """, unsafe_allow_html=True)
    
    # Default refresh settings for clients
    auto_refresh = True
    refresh_interval = 15
    target_expiry_idx = 0 # Default to current month for clients
    
else:
    # ADMIN VIEW (Show Sidebar)
    with st.sidebar:
        st.header("Configuration")
        
        # Local Token Logic
        saved_token = load_token()
        access_token = st.text_input("Upstox Access Token", value=saved_token, type="password")
        
        if access_token and access_token != saved_token:
            save_token(access_token)

        st.markdown("---")
        st.header("Expiry Settings")
        # Expiry Selection for Monthly/Weekly/Intraday
        expiry_type = st.radio(
            "Select Expiry Month",
            options=["Current Month", "Next Month"],
            index=0,
            help="Choose which expiry month to display data for."
        )
        target_expiry_idx = 0 if expiry_type == "Current Month" else 1
    
        st.markdown("---")
        st.header("Data Management")
        
        # LTP Force Refresh
        if st.button("⚡ Refresh LTP Now", use_container_width=True):
            st.session_state['force_refresh_ltp'] = True
            st.rerun()

        # NSE JSON Uploader
        st.subheader("NSE Instrument JSON")
        
        if st.button("🔄 Download Latest"):
            try:
                with st.spinner("Downloading latest NSE.json from Upstox..."):
                    url = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
                    headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                    }
                    response = requests.get(url, headers=headers, stream=True)
                    if response.status_code == 200:
                        with open(NSE_JSON_PATH, "wb") as f_out:
                            with gzip.GzipFile(fileobj=response.raw) as f_in:
                                shutil.copyfileobj(f_in, f_out)
                        st.cache_data.clear()
                        st.success("Updated successfully!")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(f"Failed to download. Status: {response.status_code}")
            except Exception as e:
                st.error(f"Error: {e}")

        
        # Monthly Uploader
        st.subheader("Monthly")
        up_m = st.file_uploader("Upload Monthly Bhavcopy", type=['zip'], key='m_up')
        if up_m is not None:
            csv_content, csv_name = extract_csv_from_zip(up_m)
            if csv_content:
                with open(FILES['Monthly'], "wb") as f:
                    f.write(csv_content)
                # Extract and save date from the CSV filename within the ZIP
                date_str = extract_date_from_filename(csv_name)
                if date_str:
                    save_meta('Monthly', date_str)
                st.success(f"Monthly file updated from {csv_name}!")
        
        meta = load_meta()
        if 'Monthly' in meta and os.path.exists(FILES['Monthly']):
            st.caption(f"📅 Data Date: {meta['Monthly']}")
        elif os.path.exists(FILES['Monthly']):
            # Fallback to file time if no meta date
            m_time = os.path.getmtime(FILES['Monthly'])
            st.caption(f"📅 Last Updated: {datetime.fromtimestamp(m_time).strftime('%Y-%m-%d %H:%M')}")
        
        # Weekly Uploader
        st.subheader("Weekly")
        up_w = st.file_uploader("Upload Weekly Bhavcopy", type=['zip'], key='w_up')
        if up_w is not None:
            csv_content, csv_name = extract_csv_from_zip(up_w)
            if csv_content:
                with open(FILES['Weekly'], "wb") as f:
                    f.write(csv_content)
                # Extract and save date
                date_str = extract_date_from_filename(csv_name)
                if date_str:
                    save_meta('Weekly', date_str)
                st.success(f"Weekly file updated from {csv_name}!")

        if 'Weekly' in meta and os.path.exists(FILES['Weekly']):
            st.caption(f"📅 Data Date: {meta['Weekly']}")
        elif os.path.exists(FILES['Weekly']):
            w_time = os.path.getmtime(FILES['Weekly'])
            st.caption(f"📅 Last Updated: {datetime.fromtimestamp(w_time).strftime('%Y-%m-%d %H:%M')}")
        
        # Intraday Uploader
        st.subheader("Intraday")
        up_i = st.file_uploader("Upload Intraday Bhavcopy", type=['zip'], key='i_up')
        if up_i is not None:
            csv_content, csv_name = extract_csv_from_zip(up_i)
            if csv_content:
                with open(FILES['Intraday'], "wb") as f:
                    f.write(csv_content)
                # Extract and save date
                date_str = extract_date_from_filename(csv_name)
                if date_str:
                    save_meta('Intraday', date_str)
                st.success(f"Intraday file updated from {csv_name}!")
        
        if 'Intraday' in meta and os.path.exists(FILES['Intraday']):
            st.caption(f"📅 Data Date: {meta['Intraday']}")
        elif os.path.exists(FILES['Intraday']):
            i_time = os.path.getmtime(FILES['Intraday'])
            st.caption(f"📅 Last Updated: {datetime.fromtimestamp(i_time).strftime('%Y-%m-%d %H:%M')}")
            
        st.markdown("---")
        st.header("Auto Refresh")
        auto_refresh = st.checkbox("Enable Auto-Refresh", value=False)
        refresh_interval = st.slider("Refresh Interval (seconds)", min_value=5, max_value=60, value=15)

# --- Main Page ---
st.title("Positional Stock Option Scanner")
# st.caption(f"Last Updated: {get_ist_now().strftime('%H:%M:%S')} IST")

nse_json_df = load_nse_json()

if not nse_json_df.empty:
    tab1, tab2, tab3 = st.tabs(["Monthly", "Weekly", "Intraday"])
    
    run_every = refresh_interval if auto_refresh else None

    with tab1:
        st.header(f"Monthly Options ({expiry_type if not is_client_view else 'Current Month'})")
        if os.path.exists(FILES['Monthly']):
            @st.fragment(run_every=run_every)
            def show_monthly():
                df_m, target_exp, all_exps = process_bhavcopy(FILES['Monthly'], nse_json_df, target_expiry_index=target_expiry_idx)
                if target_exp:
                    st.info(f"📅 Displaying Expiry: **{target_exp.strftime('%d-%b-%Y')}**")
                display_option_chain(df_m, access_token, "Monthly")
            show_monthly()
        else:
            st.warning("Monthly Bhavcopy file not found. Please upload in the sidebar.")

    with tab2:
        st.header(f"Weekly Options ({expiry_type if not is_client_view else 'Current Month'})")
        if os.path.exists(FILES['Weekly']):
            @st.fragment(run_every=run_every)
            def show_weekly():
                df_w, target_exp, all_exps = process_bhavcopy(FILES['Weekly'], nse_json_df, target_expiry_index=target_expiry_idx)
                if target_exp:
                    st.info(f"📅 Displaying Expiry: **{target_exp.strftime('%d-%b-%Y')}**")
                display_option_chain(df_w, access_token, "Weekly")
            show_weekly()
        else:
            st.warning("Weekly Bhavcopy file not found. Please upload in the sidebar.")

    with tab3:
        st.header("Intraday Options")
        if os.path.exists(FILES['Intraday']):
            @st.fragment(run_every=run_every)
            def show_intraday():
                # For Intraday, we usually always look at the nearest (0)
                df_i, target_exp, all_exps = process_bhavcopy(FILES['Intraday'], nse_json_df, target_expiry_index=0)
                if target_exp:
                    st.info(f"📅 Displaying Expiry: **{target_exp.strftime('%d-%b-%Y')}**")
                display_option_chain(df_i, access_token, "Intraday")
            show_intraday()
        else:
            st.warning("Intraday Bhavcopy file not found. Please upload in the sidebar.")

else:
    st.error("Critical Error: NSE.json could not be loaded.")
