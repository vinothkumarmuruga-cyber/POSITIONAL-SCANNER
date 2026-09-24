import streamlit as st
import pandas as pd
import requests
import math
import os
import time
import gzip
import shutil
import html
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

TOKEN_FILE = os.path.join(DATA_DIR, 'token.json')
META_FILE = os.path.join(DATA_DIR, 'meta.json')
LTP_CACHE_FILE = os.path.join(DATA_DIR, 'ltp_cache.json')
TRIGGER_ALERT_FILE = os.path.join(DATA_DIR, 'trigger_alert_state.json')
TELEGRAM_CFG_FILE = os.path.join(DATA_DIR, 'telegram_cfg.json')

# ============================================================
# INDEX TAB SYMBOL UNIVERSE
#
# The "Index" tab is NOT the NIFTY/BANKNIFTY index options - it's
# the individual STOCKS that make up the Nifty 50 and Bank Nifty
# indices (RELIANCE, BAJAJ-AUTO, HDFCBANK, ICICIBANK, etc).
# Symbols must match NSE Bhavcopy's TckrSymb exactly.
# ============================================================

NIFTY50_SYMBOLS = [
    'ADANIENT', 'ADANIPORTS', 'APOLLOHOSP', 'ASIANPAINT', 'AXISBANK',
    'BAJAJ-AUTO', 'BAJFINANCE', 'BAJAJFINSV', 'BEL', 'BHARTIARTL',
    'CIPLA', 'COALINDIA', 'DRREDDY', 'EICHERMOT', 'ETERNAL',
    'GRASIM', 'HCLTECH', 'HDFCBANK', 'HDFCLIFE', 'HINDALCO',
    'HINDUNILVR', 'ICICIBANK', 'INDIGO', 'INFY', 'ITC',
    'JIOFIN', 'JSWSTEEL', 'KOTAKBANK', 'LT', 'M&M',
    'MARUTI', 'MAXHEALTH', 'NESTLEIND', 'NTPC', 'ONGC',
    'POWERGRID', 'RELIANCE', 'SBILIFE', 'SHRIRAMFIN', 'SBIN',
    'SUNPHARMA', 'TCS', 'TATACONSUM', 'TATAMOTORS', 'TMPV', 'TATASTEEL',
    'TECHM', 'TITAN', 'TRENT', 'ULTRACEMCO', 'WIPRO'
]

BANKNIFTY_SYMBOLS = [
    'HDFCBANK', 'ICICIBANK', 'SBIN', 'AXISBANK', 'KOTAKBANK',
    'INDUSINDBK', 'FEDERALBNK', 'AUBANK', 'IDFCFIRSTB', 'BANKBARODA',
    'CANBK', 'PNB', 'UNIONBANK', 'YESBANK'
]

# Combined, de-duplicated universe for the Index tab (order preserved)
INDEX_SYMBOLS = list(dict.fromkeys(NIFTY50_SYMBOLS + BANKNIFTY_SYMBOLS))
BREADTH_GROUPS = {'NIFTY 50': NIFTY50_SYMBOLS, 'BANK NIFTY': BANKNIFTY_SYMBOLS}

FILES = {
    'Monthly': os.path.join(DATA_DIR, 'monthly.csv'),
    'Weekly': os.path.join(DATA_DIR, 'weekly.csv'),
    'Index': os.path.join(DATA_DIR, 'index.csv')
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


# ============================================================
# TELEGRAM CONFIG (separate for Monthly, Weekly and Index)
#
# Each tab has its own enable flag, bot token and chat ID, so
# alerts can go to a different bot / chat per tab.
# Saved to disk so values survive Streamlit Cloud restarts.
# ============================================================

TG_TABS = ['Monthly', 'Weekly', 'Index']

def load_telegram_cfg():
    if os.path.exists(TELEGRAM_CFG_FILE):
        try:
            with open(TELEGRAM_CFG_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_telegram_cfg(cfg):
    try:
        with open(TELEGRAM_CFG_FILE, 'w') as f:
            json.dump(cfg, f)
    except:
        pass


# ============================================================
# TELEGRAM TRIGGER-ALERT STATE
#
# Persisted to disk (not just st.session_state) so alert
# de-duplication survives Streamlit Cloud restarts / fragment
# reruns. Resets automatically each new trading day.
# Each entry is "<tab>:<instrument_key>" so Monthly/Weekly/Index
# tabs track their own alert history independently.
# ============================================================

def load_trigger_alert_state():
    if os.path.exists(TRIGGER_ALERT_FILE):
        try:
            with open(TRIGGER_ALERT_FILE, 'r') as f:
                data = json.load(f)
                if data.get('date') == get_ist_now().strftime('%Y-%m-%d'):
                    return set(data.get('keys', []))
        except:
            pass
    return set()

def save_trigger_alert_state(keys):
    try:
        data = {
            'date': get_ist_now().strftime('%Y-%m-%d'),
            'keys': list(keys)
        }
        with open(TRIGGER_ALERT_FILE, 'w') as f:
            json.dump(data, f)
    except:
        pass

def reset_trigger_alert_state_for_tab(tab_name):
    """Clears alert history for ONE tab only (Monthly, Weekly or Index)."""
    keys = load_trigger_alert_state()
    keys = {k for k in keys if not k.startswith(f"{tab_name}:")}
    save_trigger_alert_state(keys)


def send_telegram_alert(bot_token, chat_id, message):
    if not bot_token or not chat_id:
        return False, "Missing bot token or chat ID"

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            return True, None
        return False, f"HTTP {response.status_code}: {response.text[:200]}"
    except Exception as e:
        return False, f"Exception: {e}"


# Telegram's hard limit is 4096 characters per message. Stay well under it.
TG_MAX_CHARS = 3500

def check_and_alert_triggers(df, key_suffix, tg_cfg):
    """
    Sends a Telegram alert the moment an option's change %
    (LTP / Trigger x 100) crosses 100% - i.e. LTP has crossed
    the Trigger price. Fires once per option per tab per day.

    All newly-triggered options found in one refresh are split across as
    many messages as needed to stay under Telegram's 4096-char limit
    (previously one giant message -> "message is too long" and the alert
    was retried and failed on every refresh). An option is only marked
    as alerted once the message carrying it was actually delivered, so a
    failed chunk is retried on the next refresh.

    tg_cfg is the config dict for THIS tab only:
        {'enabled': bool, 'bot_token': str, 'chat_id': str}
    """
    if not tg_cfg or not tg_cfg.get('enabled'):
        return

    if df.empty:
        return

    if 'instrument_key' not in df.columns:
        return

    alerted = load_trigger_alert_state()
    pending = []  # list of (alert_id, text_block)

    for _, row in df.iterrows():
        inst_key = row.get('instrument_key')
        if not inst_key:
            continue

        alert_id = f"{key_suffix}:{inst_key}"
        if alert_id in alerted:
            continue

        try:
            change_pct = float(row.get('change %', 0.0))
        except:
            continue

        if change_pct >= 100:
            block = (
                f"\n<b>{html.escape(str(row['Symbol']))} {row['StrikePrice']:.0f} {row['OptionType']}</b>\n"
                f"LTP: {row['ltp']:.2f}  ›  Trigger: {row['Trigger']:.2f}\n"
                f"Change: {row['change %']:.2f}%"
            )
            pending.append((alert_id, block))

    if not pending:
        return

    # Pack blocks into chunks under TG_MAX_CHARS
    chunks = []  # each: list of (alert_id, block)
    current, current_len = [], 0
    for alert_id, block in pending:
        if current and current_len + len(block) > TG_MAX_CHARS:
            chunks.append(current)
            current, current_len = [], 0
        current.append((alert_id, block))
        current_len += len(block)
    if current:
        chunks.append(current)

    sent_count = 0
    last_error = None
    for i, chunk in enumerate(chunks, start=1):
        part = f" ({i}/{len(chunks)})" if len(chunks) > 1 else ""
        message = f"🚀 <b>Trigger Crossed — {key_suffix}</b>{part}" + "".join(b for _, b in chunk)
        success, error = send_telegram_alert(tg_cfg.get('bot_token', ''), tg_cfg.get('chat_id', ''), message)
        if success:
            for alert_id, _ in chunk:
                alerted.add(alert_id)
            save_trigger_alert_state(alerted)
            sent_count += len(chunk)
        else:
            last_error = error
        if i < len(chunks):
            time.sleep(1.1)  # Telegram allows ~1 msg/sec per chat

    if sent_count:
        st.sidebar.success(f"Telegram alert sent for {sent_count} trigger cross(es) on {key_suffix}.")
    if last_error:
        st.sidebar.warning(f"Telegram alert failed ({key_suffix}): {last_error}")


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

def process_bhavcopy(bhav_file, df_json, target_expiry_index=0, symbol_filter=None):
    """
    symbol_filter: optional list of TckrSymb values to restrict processing to
    (used by the Index tab to keep only Nifty 50 / Bank Nifty stocks - the
    ATM-vs-future logic below is otherwise IDENTICAL to Monthly/Weekly).
    """
    try:
        df_bhav = pd.read_csv(bhav_file)
        
        # Check required columns
        required_cols = ['FinInstrmTp', 'TckrSymb', 'XpryDt', 'ClsPric', 'StrkPric', 'OptnTp', 'HghPric', 'LwPric', 'LastPric']
        if not all(col in df_bhav.columns for col in required_cols):
            st.error(f"Uploaded file missing required columns: {required_cols}")
            return pd.DataFrame(), None, []

        if symbol_filter:
            df_bhav = df_bhav[df_bhav['TckrSymb'].isin(symbol_filter)].copy()
            if df_bhav.empty:
                st.warning("None of the selected symbols were found in the uploaded file.")
                return pd.DataFrame(), None, []

        # --- Process Bhavcopy Futures ---
        futures = df_bhav[df_bhav['FinInstrmTp'].isin(['STF', 'IDF'])].copy()
        if futures.empty:
            st.warning("No Futures data found in uploaded file.")
            return pd.DataFrame(), None, []

        futures['XpryDt'] = pd.to_datetime(futures['XpryDt'])
        
        # Filter out past expiries (Keep today and future)
        # We use IST time to match the environment's expectation
        ist_now = get_ist_now()
        today = ist_now.replace(hour=0, minute=0, second=0, microsecond=0).replace(tzinfo=None)
        
        futures = futures[futures['XpryDt'] >= today]
        if futures.empty:
            st.warning("No future expiries found in the uploaded file.")
            return pd.DataFrame(), None, []

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

def render_breadth_summary(df, groups):
    """
    Renders a small breadth/trend table above the CE/PE columns.

    For each group (e.g. 'NIFTY 50', 'BANK NIFTY'), counts how many of
    that group's stocks currently have a CE (call) with change % >= 100
    versus a PE (put) with change % >= 100, and the total distinct
    stocks from that group present in the uploaded file.

    Interpretation: more CE triggers than PE triggers across the basket
    suggests broad-based upside strength (more calls doubling up than
    puts) -> "Bullish"; more PE triggers suggests downside strength ->
    "Bearish"; equal counts -> "Neutral".
    """
    if df.empty or 'change %' not in df.columns:
        return

    rows = []
    for label, symbols in groups.items():
        sub = df[df['Symbol'].isin(symbols)]
        if sub.empty:
            continue
        ce_above = sub[(sub['OptionType'] == 'CE') & (sub['change %'] >= 100)].shape[0]
        pe_above = sub[(sub['OptionType'] == 'PE') & (sub['change %'] >= 100)].shape[0]
        total_stocks = sub['Symbol'].nunique()

        if ce_above > pe_above:
            trend = "🔼 Up"
        elif pe_above > ce_above:
            trend = "🔽 Down"
        else:
            trend = "➖ Neutral"

        rows.append({
            'Symbol': label,
            'No of CE Abv 100': ce_above,
            'No of PE Abv 100': pe_above,
            'Total Stocks': total_stocks,
            'Trend': trend
        })

    if not rows:
        return

    summary_df = pd.DataFrame(rows)

    def color_trend(val):
        if isinstance(val, str):
            if 'Up' in val:
                return 'background-color: darkgreen; color: white'
            elif 'Down' in val:
                return 'background-color: darkred; color: white'
        return ''

    def color_symbol(val):
        if val == 'BANK NIFTY':
            return 'background-color: #8e44ad; color: white'  # purple
        elif val == 'NIFTY 50':
            return 'background-color: #2980b9; color: white'  # blue
        return ''

    st.subheader("📊 Trend Summary")
    st.dataframe(
        summary_df.style
        .map(color_trend, subset=['Trend'])
        .map(color_symbol, subset=['Symbol'])
        .set_properties(**{'font-weight': '600', 'text-align': 'center', 'font-size': '16px'}),
        hide_index=True,
        use_container_width=True
    )
    st.markdown("---")


def get_index_futures_pc(bhav_file, target_expiry_index=0):
    """
    Reads the Index Bhavcopy and pulls the Previous Close (ClsPric) of the
    NIFTY and BANKNIFTY INDEX FUTURES (FinInstrmTp == 'IDF') for the
    selected expiry (same Current/Next Month choice as Monthly/Weekly/Index
    tabs). Returns {'NIFTY': pc, 'BANK NIFTY': pc}.
    """
    pc_map = {'NIFTY': 0.0, 'BANK NIFTY': 0.0}
    try:
        df_bhav = pd.read_csv(bhav_file)
        required_cols = ['FinInstrmTp', 'TckrSymb', 'XpryDt', 'ClsPric']
        if not all(col in df_bhav.columns for col in required_cols):
            return pc_map

        idx_futures = df_bhav[
            (df_bhav['FinInstrmTp'] == 'IDF') &
            (df_bhav['TckrSymb'].isin(['NIFTY', 'BANKNIFTY']))
        ].copy()
        if idx_futures.empty:
            return pc_map

        idx_futures['XpryDt'] = pd.to_datetime(idx_futures['XpryDt'])
        ist_now = get_ist_now()
        today = ist_now.replace(hour=0, minute=0, second=0, microsecond=0).replace(tzinfo=None)
        idx_futures = idx_futures[idx_futures['XpryDt'] >= today]
        if idx_futures.empty:
            return pc_map

        symbol_to_label = {'NIFTY': 'NIFTY', 'BANKNIFTY': 'BANK NIFTY'}
        for sym, grp in idx_futures.groupby('TckrSymb'):
            exps = sorted(grp['XpryDt'].unique())
            if not exps:
                continue
            idx = target_expiry_index if target_expiry_index < len(exps) else len(exps) - 1
            target_exp = exps[idx]
            pc_val = grp[grp['XpryDt'] == target_exp]['ClsPric'].iloc[0]
            pc_map[symbol_to_label.get(sym, sym)] = float(pc_val)

        return pc_map
    except Exception:
        return pc_map


def display_option_chain(df, access_token, key_suffix, tg_cfg=None, breadth_groups=None, highlight_symbols=None, show_index_tracker=False, index_bhav_file=None, target_expiry_idx=0, section_title=None, expiry=None):
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

    # --- Telegram Trigger Alerts (per-tab config) ---
    # Runs on the full (CE+PE) dataframe, after change % is
    # computed, before the CE/PE split below.
    check_and_alert_triggers(df, key_suffix, tg_cfg)

    # --- Trend Summary ---
    if breadth_groups:
        render_breadth_summary(df, breadth_groups)

    if section_title:
        st.header(section_title)
    if expiry is not None:
        st.info(f"📅 Displaying Expiry: **{expiry.strftime('%d-%b-%Y')}**")
    st.caption(f"Last Updated: {get_ist_now().strftime('%H:%M:%S')} IST")
    if not access_token:
        st.warning("Enter Access Token in sidebar to see live LTP.")

    # Split Calls/Puts
    calls_df = df[df['OptionType'] == 'CE'].copy()
    puts_df = df[df['OptionType'] == 'PE'].copy()

    # Sort
    calls_df = calls_df.sort_values(by='change %', ascending=False)
    puts_df = puts_df.sort_values(by='change %', ascending=False)

    # --- Pin NIFTY / BANK NIFTY (futures PC as Trigger, live LTP) at the
    # top of BOTH tables, every refresh - so the index level is always
    # visible regardless of how the rest of the table is sorted.
    if show_index_tracker and index_bhav_file:
        pc_map = get_index_futures_pc(index_bhav_file, target_expiry_idx)
        NIFTY_INDEX_KEY = "NSE_INDEX|Nifty 50"
        BANKNIFTY_INDEX_KEY = "NSE_INDEX|Nifty Bank"

        idx_ltp_map = {}
        if access_token:
            idx_ltp_map = fetch_ltp([NIFTY_INDEX_KEY, BANKNIFTY_INDEX_KEY], access_token)

        nifty_pc = pc_map.get('NIFTY', 0.0)
        bn_pc = pc_map.get('BANK NIFTY', 0.0)
        nifty_ltp = idx_ltp_map.get(NIFTY_INDEX_KEY, 0.0) or 0.0
        bn_ltp = idx_ltp_map.get(BANKNIFTY_INDEX_KEY, 0.0) or 0.0

        def _idx_change(strike, ltp):
            try:
                if strike > 0 and ltp > 0:
                    return (ltp / strike) * 100
                return 0.0
            except:
                return 0.0

        index_pin_rows = pd.DataFrame([
            {'Symbol': 'NIFTY', 'StrikePrice': nifty_pc, 'Trigger': nifty_pc, 'ltp': nifty_ltp, 'change %': _idx_change(nifty_pc, nifty_ltp)},
            {'Symbol': 'BANK NIFTY', 'StrikePrice': bn_pc, 'Trigger': bn_pc, 'ltp': bn_ltp, 'change %': _idx_change(bn_pc, bn_ltp)},
        ])
        calls_df = pd.concat([index_pin_rows, calls_df], ignore_index=True)
        puts_df = pd.concat([index_pin_rows, puts_df], ignore_index=True)

    display_cols = ['Symbol', 'StrikePrice', 'Trigger', 'ltp', 'change %']
    
    # Styling
    def color_change(val):
        if isinstance(val, (int, float)):
            if val >= 100:
                return 'background-color: darkgreen; color: white'
            elif val >= 90:
                return 'background-color: lightgreen; color: black'
        return ''

    def color_bn_symbol(val):
        if val == 'BANK NIFTY':
            return 'background-color: #8e44ad; color: white'  # purple - Bank Nifty index
        elif val == 'NIFTY':
            return 'background-color: #2980b9; color: white'  # blue - Nifty index
        elif highlight_symbols and val in highlight_symbols:
            return 'background-color: #8e44ad; color: white'  # purple - Bank Nifty stock
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
            .map(color_bn_symbol, subset=['Symbol'])
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
            .map(color_bn_symbol, subset=['Symbol'])
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

# Per-tab Telegram config: {'Monthly': {...}, 'Weekly': {...}, 'Index': {...}}
telegram_cfgs = {
    'Monthly': {'enabled': False, 'bot_token': '', 'chat_id': ''},
    'Weekly': {'enabled': False, 'bot_token': '', 'chat_id': ''},
    'Index': {'enabled': False, 'bot_token': '', 'chat_id': ''},
}

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

    # Telegram config in client view comes from secrets only,
    # since the sidebar (with its manual controls) is hidden.
    #   Monthly: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID
    #   Weekly : TELEGRAM_WEEKLY_BOT_TOKEN / TELEGRAM_WEEKLY_CHAT_ID
    #            (falls back to the Monthly values if not set)
    #   Index  : TELEGRAM_INDEX_BOT_TOKEN / TELEGRAM_INDEX_CHAT_ID
    #            (falls back to the Monthly values if not set)
    m_token = st.secrets.get("TELEGRAM_BOT_TOKEN", "")
    m_chat = st.secrets.get("TELEGRAM_CHAT_ID", "")
    w_token = st.secrets.get("TELEGRAM_WEEKLY_BOT_TOKEN", "") or m_token
    w_chat = st.secrets.get("TELEGRAM_WEEKLY_CHAT_ID", "") or m_chat
    i_token = st.secrets.get("TELEGRAM_INDEX_BOT_TOKEN", "") or m_token
    i_chat = st.secrets.get("TELEGRAM_INDEX_CHAT_ID", "") or m_chat

    telegram_cfgs['Monthly'] = {'enabled': bool(m_token and m_chat), 'bot_token': m_token, 'chat_id': m_chat}
    telegram_cfgs['Weekly'] = {'enabled': bool(w_token and w_chat), 'bot_token': w_token, 'chat_id': w_chat}
    telegram_cfgs['Index'] = {'enabled': bool(i_token and i_chat), 'bot_token': i_token, 'chat_id': i_chat}
    
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
        # Expiry Selection for Monthly/Weekly/Index
        expiry_type = st.radio(
            "Select Expiry Month",
            options=["Current Month", "Next Month"],
            index=0,
            help="Choose which expiry month to display data for."
        )
        target_expiry_idx = 0 if expiry_type == "Current Month" else 1

        st.markdown("---")
        st.header("Telegram Alerts")

        # Load saved Telegram config once per session into widget state
        saved_tg = load_telegram_cfg()
        for _tab in TG_TABS:
            _k = _tab.lower()
            _saved = saved_tg.get(_tab, {})
            st.session_state.setdefault(f"tg_{_k}_enabled", _saved.get('enabled', False))
            st.session_state.setdefault(f"tg_{_k}_token", _saved.get('bot_token', ''))
            st.session_state.setdefault(f"tg_{_k}_chat", _saved.get('chat_id', ''))

        # One expander per tab — each with its own bot token / chat ID
        for _tab in TG_TABS:
            _k = _tab.lower()
            with st.expander(f"📨 {_tab} Alerts", expanded=(_tab == 'Weekly')):
                _enabled = st.checkbox(
                    f"Enable {_tab} Trigger Alerts",
                    key=f"tg_{_k}_enabled",
                    help=f"Sends a Telegram message when a {_tab} option's LTP crosses its Trigger price (change % >= 100)."
                )
                _token = st.text_input(
                    "Bot Token",
                    type="password",
                    key=f"tg_{_k}_token",
                    help="Create a bot via @BotFather on Telegram to get this token."
                )
                _chat = st.text_input(
                    "Chat ID",
                    key=f"tg_{_k}_chat",
                    help="Your personal or group chat ID. Message @userinfobot to find yours."
                )

                _c1, _c2 = st.columns(2)
                _test = _c1.button("Send Test", key=f"tg_{_k}_test", use_container_width=True)
                _reset = _c2.button("Reset Alerts", key=f"tg_{_k}_reset", use_container_width=True)

                if _reset:
                    reset_trigger_alert_state_for_tab(_tab)
                    st.success(f"{_tab} alert state cleared — already-triggered options will alert again.")

                if _test:
                    ok, err = send_telegram_alert(
                        _token,
                        _chat,
                        f"✅ Test alert from Positional Option Scanner — <b>{_tab}</b> Telegram is wired up correctly."
                    )
                    if ok:
                        st.success("Test message sent — check Telegram.")
                    else:
                        st.error(f"Test message failed: {err}")

                telegram_cfgs[_tab] = {'enabled': _enabled, 'bot_token': _token, 'chat_id': _chat}

        # Persist config so it survives restarts
        if telegram_cfgs != saved_tg:
            save_telegram_cfg(telegram_cfgs)
    
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

        # Index Uploader (Nifty 50 + Bank Nifty stocks only)
        st.subheader("Index (Nifty 50 + Bank Nifty Stocks)")
        up_i = st.file_uploader("Upload Index Bhavcopy", type=['zip'], key='i_up')
        if up_i is not None:
            csv_content, csv_name = extract_csv_from_zip(up_i)
            if csv_content:
                with open(FILES['Index'], "wb") as f:
                    f.write(csv_content)
                # Extract and save date
                date_str = extract_date_from_filename(csv_name)
                if date_str:
                    save_meta('Index', date_str)
                st.success(f"Index file updated from {csv_name}!")

        if 'Index' in meta and os.path.exists(FILES['Index']):
            st.caption(f"📅 Data Date: {meta['Index']}")
        elif os.path.exists(FILES['Index']):
            i_time = os.path.getmtime(FILES['Index'])
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
    tab1, tab2, tab3 = st.tabs(["Monthly", "Weekly", "Index"])
    
    run_every = refresh_interval if auto_refresh else None

    with tab1:
        if os.path.exists(FILES['Monthly']):
            @st.fragment(run_every=run_every)
            def show_monthly():
                df_m, target_exp, all_exps = process_bhavcopy(FILES['Monthly'], nse_json_df, target_expiry_index=target_expiry_idx)
                display_option_chain(
                    df_m, access_token, "Monthly", telegram_cfgs['Monthly'],
                    breadth_groups=BREADTH_GROUPS,
                    section_title=f"Monthly Options ({expiry_type if not is_client_view else 'Current Month'})",
                    expiry=target_exp
                )
            show_monthly()
        else:
            st.warning("Monthly Bhavcopy file not found. Please upload in the sidebar.")

    with tab2:
        if os.path.exists(FILES['Weekly']):
            @st.fragment(run_every=run_every)
            def show_weekly():
                df_w, target_exp, all_exps = process_bhavcopy(FILES['Weekly'], nse_json_df, target_expiry_index=target_expiry_idx)
                display_option_chain(
                    df_w, access_token, "Weekly", telegram_cfgs['Weekly'],
                    breadth_groups=BREADTH_GROUPS,
                    section_title=f"Weekly Options ({expiry_type if not is_client_view else 'Current Month'})",
                    expiry=target_exp
                )
            show_weekly()
        else:
            st.warning("Weekly Bhavcopy file not found. Please upload in the sidebar.")

    with tab3:
        if os.path.exists(FILES['Index']):
            @st.fragment(run_every=run_every)
            def show_index():
                df_i, target_exp, all_exps = process_bhavcopy(
                    FILES['Index'], nse_json_df,
                    target_expiry_index=target_expiry_idx,
                    symbol_filter=INDEX_SYMBOLS
                )
                display_option_chain(
                    df_i, access_token, "Index", telegram_cfgs['Index'],
                    breadth_groups=BREADTH_GROUPS,
                    highlight_symbols=BANKNIFTY_SYMBOLS,
                    show_index_tracker=True,
                    index_bhav_file=FILES['Index'],
                    target_expiry_idx=target_expiry_idx,
                    section_title=f"Index Options — Nifty 50 & Bank Nifty Stocks ({expiry_type if not is_client_view else 'Current Month'})",
                    expiry=target_exp
                )
            show_index()
        else:
            st.warning("Index Bhavcopy file not found. Please upload in the sidebar.")

else:
    st.error("Critical Error: NSE.json could not be loaded.")
