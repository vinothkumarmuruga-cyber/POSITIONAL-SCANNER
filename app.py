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
import json
import re

# ============================================================
# IST
# ============================================================

IST_OFFSET = timedelta(hours=5, minutes=30)
IST = timezone(IST_OFFSET)


def get_ist_now():
    return datetime.now(IST)


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="Positional Stock Option Scanner",
    layout="wide"
)


# ============================================================
# CUSTOM CSS
# ============================================================

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

        /* Tabs */

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

        /* Prevent graying during refresh */

        .stApp {
            transition: none !important;
        }

        [data-testid="stAppViewContainer"],
        [data-testid="stHeader"] {
            opacity: 1 !important;
            transition: none !important;
        }

        /* Hide uploader instructions */

        [data-testid="stFileUploaderDropzone"] div div span {
            display: none !important;
        }

        [data-testid="stFileUploaderDropzone"] div div small {
            display: none !important;
        }

        /* Dataframe */

        div[data-testid="stDataFrame"] {
            font-weight: 600 !important;
        }

    </style>
""", unsafe_allow_html=True)


# ============================================================
# PERSISTENT STORAGE
# ============================================================

DATA_DIR = "data"

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)


BLACKLIST_FILE = os.path.join(
    DATA_DIR,
    "blacklist.json"
)

TOKEN_FILE = os.path.join(
    DATA_DIR,
    "token.json"
)

META_FILE = os.path.join(
    DATA_DIR,
    "meta.json"
)

LTP_CACHE_FILE = os.path.join(
    DATA_DIR,
    "ltp_cache.json"
)

TRIGGER_ALERT_FILE = os.path.join(
    DATA_DIR,
    "trigger_alert_state.json"
)


FILES = {
    "Monthly": os.path.join(DATA_DIR, "monthly.csv"),
    "Weekly": os.path.join(DATA_DIR, "weekly.csv"),
    "Intraday": os.path.join(DATA_DIR, "intraday.csv")
}


# ============================================================
# PRIORITY SETTINGS
# ============================================================

# Kept only for the visual highlight band in the table
# (90-110% shows amber, >110% shows dark green, 80-90% shows
# light green). Row ORDERING no longer uses this - the table
# is sorted purely by change % descending now.
PRIORITY_MIN = 90.0
PRIORITY_MAX = 110.0


# ============================================================
# META
# ============================================================

def load_meta():

    if os.path.exists(META_FILE):

        try:

            with open(META_FILE, "r") as f:
                return json.load(f)

        except:
            pass

    return {}


def save_meta(key, date_str):

    try:

        meta = load_meta()

        meta[key] = date_str

        with open(META_FILE, "w") as f:
            json.dump(meta, f)

    except:
        pass


# ============================================================
# LTP CACHE
# ============================================================

def load_ltp_cache():

    if os.path.exists(LTP_CACHE_FILE):

        try:

            with open(LTP_CACHE_FILE, "r") as f:
                return json.load(f)

        except:
            pass

    return {}


def save_ltp_cache(new_data):

    try:

        cache = load_ltp_cache()

        cache.update(new_data)

        with open(LTP_CACHE_FILE, "w") as f:
            json.dump(cache, f)

    except:
        pass


# ============================================================
# DATE FROM FILE NAME
# ============================================================

def extract_date_from_filename(filename):

    match = re.search(r"(\d{8})", filename)

    if match:

        d = match.group(1)

        return (
            f"{d[:4]}-"
            f"{d[4:6]}-"
            f"{d[6:]}"
        )

    return None


# ============================================================
# ZIP -> CSV
# ============================================================

def extract_csv_from_zip(zip_file):

    try:

        with zipfile.ZipFile(zip_file) as z:

            csv_files = [
                f for f in z.namelist()
                if f.lower().endswith(".csv")
            ]

            if not csv_files:

                st.error(
                    "No CSV file found in the ZIP archive."
                )

                return None, None

            csv_filename = csv_files[0]

            with z.open(csv_filename) as f:

                return f.read(), csv_filename

    except Exception as e:

        st.error(
            f"Error extracting ZIP file: {e}"
        )

        return None, None


# ============================================================
# TOKEN
# ============================================================

def load_token():

    if os.path.exists(TOKEN_FILE):

        try:

            with open(TOKEN_FILE, "r") as f:

                data = json.load(f)

                if (
                    data.get("date")
                    ==
                    get_ist_now().strftime("%Y-%m-%d")
                ):

                    return data.get("token", "")

        except:
            pass

    return ""


def save_token(token):

    try:

        data = {
            "date":
                get_ist_now().strftime("%Y-%m-%d"),

            "token":
                token
        }

        with open(TOKEN_FILE, "w") as f:

            json.dump(data, f)

    except:
        pass


# ============================================================
# BLACKLIST
# ============================================================

def load_blacklist():

    if os.path.exists(BLACKLIST_FILE):

        try:

            with open(BLACKLIST_FILE, "r") as f:

                data = json.load(f)

                if (
                    data.get("date")
                    ==
                    get_ist_now().strftime("%Y-%m-%d")
                ):

                    return set(
                        data.get("keys", [])
                    )

        except:
            pass

    return set()


def save_blacklist(keys):

    try:

        data = {
            "date":
                get_ist_now().strftime("%Y-%m-%d"),

            "keys":
                list(keys)
        }

        with open(BLACKLIST_FILE, "w") as f:

            json.dump(data, f)

    except:
        pass


# ============================================================
# TELEGRAM TRIGGER-ALERT STATE
#
# Persisted to disk (not just st.session_state) so alert
# de-duplication survives Streamlit Cloud restarts / fragment
# reruns. Resets automatically each new trading day.
# Each entry is "<tab>:<instrument_key>" so Monthly/Weekly/
# Intraday tabs track their own alert history independently.
# ============================================================

def load_trigger_alert_state():

    if os.path.exists(TRIGGER_ALERT_FILE):

        try:

            with open(TRIGGER_ALERT_FILE, "r") as f:

                data = json.load(f)

                if (
                    data.get("date")
                    ==
                    get_ist_now().strftime("%Y-%m-%d")
                ):

                    return set(
                        data.get("keys", [])
                    )

        except:
            pass

    return set()


def save_trigger_alert_state(keys):

    try:

        data = {
            "date":
                get_ist_now().strftime("%Y-%m-%d"),

            "keys":
                list(keys)
        }

        with open(TRIGGER_ALERT_FILE, "w") as f:

            json.dump(data, f)

    except:
        pass


# ============================================================
# NSE JSON
# ============================================================

NSE_JSON_PATH = "NSE.json"


@st.cache_data
def load_nse_json():

    if os.path.exists(NSE_JSON_PATH):

        try:

            df = pd.read_json(
                NSE_JSON_PATH
            )

            if "segment" in df.columns:

                df = df[
                    df["segment"] == "NSE_FO"
                ]

            df["expiry_dt"] = (
                pd.to_datetime(
                    df["expiry"],
                    unit="ms"
                ).dt.normalize()
            )

            return df

        except Exception as e:

            st.error(
                f"Error loading NSE.json: {e}"
            )

            return pd.DataFrame()

    else:

        st.error(
            f"NSE.json not found at "
            f"{NSE_JSON_PATH}"
        )

        return pd.DataFrame()


# ============================================================
# PROCESS BHAVCOPY
# ============================================================

def process_bhavcopy(
    bhav_file,
    df_json,
    target_expiry_index=0
):

    try:

        df_bhav = pd.read_csv(
            bhav_file
        )

        required_cols = [
            "FinInstrmTp",
            "TckrSymb",
            "XpryDt",
            "ClsPric",
            "StrkPric",
            "OptnTp",
            "HghPric",
            "LwPric",
            "LastPric"
        ]

        if not all(
            col in df_bhav.columns
            for col in required_cols
        ):

            st.error(
                "Uploaded file missing "
                f"required columns: {required_cols}"
            )

            return pd.DataFrame()

        # ====================================================
        # FUTURES
        # ====================================================

        futures = df_bhav[
            df_bhav["FinInstrmTp"].isin(
                ["STF", "IDF"]
            )
        ].copy()

        if futures.empty:

            st.warning(
                "No Futures data found "
                "in uploaded file."
            )

            return pd.DataFrame()

        futures["XpryDt"] = pd.to_datetime(
            futures["XpryDt"]
        )

        ist_now = get_ist_now()

        today = (
            ist_now
            .replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0
            )
            .replace(tzinfo=None)
        )

        futures = futures[
            futures["XpryDt"] >= today
        ]

        if futures.empty:

            st.warning(
                "No future expiries found "
                "in the uploaded file."
            )

            return pd.DataFrame()

        futures = futures.sort_values(
            "XpryDt"
        )

        available_expiries = sorted(
            futures["XpryDt"].unique()
        )

        if not available_expiries:

            st.warning(
                "No future expiry dates found "
                "in uploaded file."
            )

            return pd.DataFrame(), None, []

        if (
            target_expiry_index
            >= len(available_expiries)
        ):

            target_expiry = (
                available_expiries[-1]
            )

        else:

            target_expiry = (
                available_expiries[
                    target_expiry_index
                ]
            )

        near_futures = futures[
            futures["XpryDt"]
            ==
            target_expiry
        ].copy()

        near_futures = near_futures[
            [
                "TckrSymb",
                "ClsPric",
                "XpryDt"
            ]
        ]

        near_futures = near_futures.rename(
            columns={
                "ClsPric":
                    "FuturePrice",

                "XpryDt":
                    "FutureExpiryDate"
            }
        )

        # ====================================================
        # OPTIONS
        # ====================================================

        options = df_bhav[
            df_bhav["OptnTp"].isin(
                ["CE", "PE"]
            )
        ].copy()

        if options.empty:

            st.warning(
                "No Options data found "
                "in uploaded file."
            )

            return (
                pd.DataFrame(),
                target_expiry,
                available_expiries
            )

        options["XpryDt"] = pd.to_datetime(
            options["XpryDt"]
        )

        merged = pd.merge(
            options,
            near_futures,
            on="TckrSymb"
        )

        merged = merged[
            merged["XpryDt"]
            ==
            merged["FutureExpiryDate"]
        ]

        # ====================================================
        # ATM
        # ====================================================

        merged["Diff"] = (
            abs(
                merged["StrkPric"]
                -
                merged["FuturePrice"]
            )
        )

        best_strikes = (
            merged[
                [
                    "TckrSymb",
                    "StrkPric",
                    "Diff"
                ]
            ]
            .drop_duplicates()
        )

        best_strikes = (
            best_strikes
            .sort_values(
                by=[
                    "TckrSymb",
                    "Diff",
                    "StrkPric"
                ]
            )
        )

        best_strikes = (
            best_strikes
            .groupby("TckrSymb")
            .first()
            .reset_index()
        )

        atm_options = pd.merge(
            merged,
            best_strikes[
                [
                    "TckrSymb",
                    "StrkPric"
                ]
            ],
            on=[
                "TckrSymb",
                "StrkPric"
            ]
        )

        atm_rows = atm_options[
            [
                "TckrSymb",
                "XpryDt",
                "StrkPric",
                "OptnTp",
                "FuturePrice",
                "ClsPric",
                "FinInstrmNm",
                "HghPric",
                "LwPric",
                "LastPric"
            ]
        ].copy()

        atm_rows["XpryDt"] = (
            atm_rows["XpryDt"]
            .dt.normalize()
        )

        # ====================================================
        # MERGE WITH NSE JSON
        # ====================================================

        result = pd.merge(

            atm_rows,

            df_json,

            left_on=[
                "TckrSymb",
                "StrkPric",
                "OptnTp",
                "XpryDt"
            ],

            right_on=[
                "underlying_symbol",
                "strike_price",
                "instrument_type",
                "expiry_dt"
            ],

            how="inner"
        )

        if (
            result.empty
            and not atm_rows.empty
        ):

            st.error(
                "Data mismatch: Found options "
                "in Bhavcopy but couldn't find "
                "them in NSE.json. Please update "
                "NSE.json via the sidebar."
            )

        final_df = result[
            [
                "TckrSymb",
                "XpryDt",
                "StrkPric",
                "OptnTp",
                "FuturePrice",
                "ClsPric",
                "instrument_key",
                "HghPric",
                "LwPric",
                "LastPric"
            ]
        ].copy()

        final_df = final_df.rename(
            columns={
                "TckrSymb":
                    "Symbol",

                "XpryDt":
                    "ExpiryDate",

                "StrkPric":
                    "StrikePrice",

                "OptnTp":
                    "OptionType",

                "ClsPric":
                    "Trigger",

                "HghPric":
                    "HighPrice",

                "LwPric":
                    "LowPrice",

                "LastPric":
                    "LastPrice"
            }
        )

        # ====================================================
        # CAMARILLA R4
        # ====================================================

        final_df["Camarilla_R4"] = (
            final_df["Trigger"]
            +
            (
                final_df["HighPrice"]
                -
                final_df["LowPrice"]
            )
            * 1.1
            / 2
        )

        # ====================================================
        # USER RULE
        # TRIGGER x 2
        # ====================================================

        if "Trigger" in final_df.columns:

            final_df["Trigger"] = (
                final_df["Trigger"] * 2
            )

        return (
            final_df,
            target_expiry,
            available_expiries
        )

    except Exception as e:

        st.error(
            f"Error processing file: {e}"
        )

        return (
            pd.DataFrame(),
            None,
            []
        )


# ============================================================
# FETCH LTP
# ============================================================

def fetch_ltp(
    instrument_keys,
    token
):

    if not token:
        return {}

    url = (
        "https://api.upstox.com/v3/"
        "market-quote/ltp"
    )

    headers = {
        "Accept":
            "application/json",

        "Authorization":
            f"Bearer {token}"
    }

    batch_size = 50

    ltp_map = {}

    batches = [
        instrument_keys[i:i + batch_size]
        for i in range(
            0,
            len(instrument_keys),
            batch_size
        )
    ]

    def fetch_batch(batch):

        params = {
            "instrument_key":
                ",".join(batch)
        }

        try:

            response = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=10
            )

            if response.status_code == 200:

                data = response.json()

                if (
                    data.get("status")
                    ==
                    "success"
                ):

                    quotes = data.get(
                        "data",
                        {}
                    )

                    result = {}

                    for key, details in (
                        quotes.items()
                    ):

                        inst_token = (
                            details.get(
                                "instrument_token"
                            )
                        )

                        last_price = (
                            details.get(
                                "last_price"
                            )
                        )

                        if inst_token is not None:

                            result[
                                inst_token
                            ] = last_price

                    return result

        except Exception:
            pass

        return {}

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=10
    ) as executor:

        futures = [
            executor.submit(
                fetch_batch,
                batch
            )
            for batch in batches
        ]

        for future in concurrent.futures.as_completed(
            futures
        ):

            try:

                batch_result = (
                    future.result()
                )

                if batch_result:

                    ltp_map.update(
                        batch_result
                    )

            except Exception:
                pass

    return ltp_map


# ============================================================
# TELEGRAM TRIGGER BOT
#
# Sends a Telegram alert the moment an option's change %
# (LTP / Trigger x 100) crosses 100% - i.e. LTP has crossed
# the Trigger price. Fires once per option per tab per day
# (de-duped via TRIGGER_ALERT_FILE), regardless of the
# 90-110% highlight band used purely for visual styling.
# ============================================================

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

        response = requests.post(
            url,
            json=payload,
            timeout=10
        )

        if response.status_code == 200:
            return True, None

        return False, f"HTTP {response.status_code}: {response.text[:200]}"

    except Exception as e:

        return False, f"Exception: {e}"


def check_and_alert_triggers(
    df,
    key_suffix,
    telegram_enabled,
    bot_token,
    chat_id
):

    if not telegram_enabled:
        return

    if df.empty:
        return

    if "instrument_key" not in df.columns:
        return

    alerted = load_trigger_alert_state()

    newly_triggered = []

    for _, row in df.iterrows():

        inst_key = row.get("instrument_key")

        if not inst_key:
            continue

        alert_id = f"{key_suffix}:{inst_key}"

        change_pct = row.get("change %", 0.0)

        try:
            change_pct = float(change_pct)
        except:
            continue

        if change_pct >= 100 and alert_id not in alerted:

            newly_triggered.append(row)

            alerted.add(alert_id)

    if not newly_triggered:
        return

    message_lines = [
        f"🚀 <b>Trigger Crossed — {key_suffix}</b>"
    ]

    for row in newly_triggered:

        message_lines.append(
            f"\n<b>{row['Symbol']} {row['StrikePrice']:.0f} {row['OptionType']}</b>\n"
            f"LTP: {row['ltp']:.2f}  ›  Trigger: {row['Trigger']:.2f}\n"
            f"Change: {row['change %']:.2f}%"
        )

    message = "\n".join(message_lines)

    success, error = send_telegram_alert(
        bot_token,
        chat_id,
        message
    )

    if success:

        save_trigger_alert_state(alerted)

        st.sidebar.success(
            f"Telegram alert sent for {len(newly_triggered)} "
            f"trigger cross(es) on {key_suffix}."
        )

    else:

        st.sidebar.warning(
            f"Telegram alert failed: {error}"
        )


# ============================================================
# DISPLAY OPTION CHAIN
# ============================================================

def display_option_chain(
    df,
    access_token,
    key_suffix,
    telegram_enabled=False,
    telegram_bot_token="",
    telegram_chat_id=""
):

    st.caption(
        "Last Updated: "
        f"{get_ist_now().strftime('%H:%M:%S')} IST"
    )

    if df.empty:

        st.info(
            "No data to display. "
            "Please upload a valid "
            "Bhavcopy in the sidebar."
        )

        return

    # ========================================================
    # FETCH LTP
    # ========================================================

    if access_token:

        all_keys = (
            df["instrument_key"]
            .dropna()
            .unique()
            .tolist()
        )

        ist_now = get_ist_now()

        current_time = ist_now.time()

        start_time = datetime.strptime(
            "09:00",
            "%H:%M"
        ).time()

        end_time = datetime.strptime(
            "15:40",
            "%H:%M"
        ).time()

        is_market_hours = (
            start_time
            <=
            current_time
            <=
            end_time
        )

        ltp_cache = load_ltp_cache()

        missing_keys = [
            k
            for k in all_keys
            if k not in ltp_cache
        ]

        force_refresh = (
            st.session_state.get(
                "force_refresh_ltp",
                False
            )
        )

        should_fetch = False

        # ----------------------------------------------------
        # Market hours = live update
        # ----------------------------------------------------

        if is_market_hours:

            should_fetch = True

        # ----------------------------------------------------
        # Manual refresh
        # ----------------------------------------------------

        elif force_refresh:

            should_fetch = True

            st.session_state[
                "force_refresh_ltp"
            ] = False

        # ----------------------------------------------------
        # Missing data
        # ----------------------------------------------------

        elif missing_keys:

            should_fetch = True

        # ----------------------------------------------------
        # Fetch
        # ----------------------------------------------------

        if should_fetch:

            if is_market_hours:

                keys_to_fetch = all_keys

            else:

                keys_to_fetch = missing_keys

            fetched_data = fetch_ltp(
                keys_to_fetch,
                access_token
            )

            if fetched_data:

                save_ltp_cache(
                    fetched_data
                )

                ltp_cache = (
                    load_ltp_cache()
                )

        # ----------------------------------------------------
        # Read cache
        # ----------------------------------------------------

        ltp_data = {
            k:
                ltp_cache.get(
                    k,
                    0.0
                )
            for k in all_keys
        }

        df["ltp"] = (
            df["instrument_key"]
            .map(ltp_data)
            .fillna(0.0)
        )

    else:

        df["ltp"] = 0.0

        st.warning(
            "Enter Access Token in sidebar "
            "to see live LTP."
        )

    # ========================================================
    # INTRADAY TRIGGER
    # ========================================================

    if (
        key_suffix == "Intraday"
        and
        "Camarilla_R4" in df.columns
    ):

        df["Trigger"] = (
            df["Camarilla_R4"]
        )

    # ========================================================
    # CHANGE %
    # ========================================================

    def calculate_numeric_change(row):

        try:

            ocp = float(
                row["Trigger"]
            )

            ltp = float(
                row["ltp"]
            )

            if (
                ocp > 0
                and
                ltp > 0
            ):

                return (
                    ltp
                    /
                    ocp
                    *
                    100
                )

            return 0.0

        except:

            return 0.0

    df["change_val"] = (
        df.apply(
            calculate_numeric_change,
            axis=1
        )
    )

    df["change %"] = (
        df["change_val"]
    )

    # ========================================================
    # INTRADAY BLACKLIST
    # ========================================================

    if key_suffix == "Intraday":

        blacklist = load_blacklist()

        current_time = (
            get_ist_now().time()
        )

        cutoff_time = datetime.strptime(
            "09:30",
            "%H:%M"
        ).time()

        # Before 09:30 blacklist >= 100%
        if current_time < cutoff_time:

            violators = (
                df[
                    df["change %"] >= 100
                ]["instrument_key"]
                .tolist()
            )

            if violators:

                blacklist.update(
                    violators
                )

                save_blacklist(
                    blacklist
                )

        # Remove blacklist
        if blacklist:

            df = df[
                ~df[
                    "instrument_key"
                ].isin(blacklist)
            ]

    # ========================================================
    # TELEGRAM TRIGGER ALERTS
    #
    # Runs on the full (CE+PE) dataframe, after change % is
    # computed and blacklist filtering applied, before the
    # CE/PE split below.
    # ========================================================

    check_and_alert_triggers(
        df,
        key_suffix,
        telegram_enabled,
        telegram_bot_token,
        telegram_chat_id
    )

    # ========================================================
    # SPLIT CE / PE
    # ========================================================

    calls_df = df[
        df["OptionType"] == "CE"
    ].copy()

    puts_df = df[
        df["OptionType"] == "PE"
    ].copy()

    # ========================================================
    # NORMAL SORT ORDER (change % descending)
    #
    # Priority re-ordering (90-110% pulled to top) removed -
    # rows now stay in plain highest-change%-first order.
    # ========================================================

    calls_df = calls_df.sort_values(
        by="change %",
        ascending=False
    )

    puts_df = puts_df.sort_values(
        by="change %",
        ascending=False
    )

    # ========================================================
    # DISPLAY COLUMNS
    # ========================================================

    display_cols = [
        "Symbol",
        "StrikePrice",
        "Trigger",
        "ltp",
        "change %"
    ]

    # ========================================================
    # STYLING
    # ========================================================

    def color_change(val):

        try:

            val = float(val)

        except:

            return ""

        # ----------------------------------------------------
        # 90 - 110 = highlight band
        # ----------------------------------------------------

        if (
            PRIORITY_MIN
            <=
            val
            <=
            PRIORITY_MAX
        ):

            return (
                "background-color: #fff2cc;"
                "color: #000000;"
                "font-weight: bold;"
            )

        # ----------------------------------------------------
        # Above 110
        # ----------------------------------------------------

        elif val > PRIORITY_MAX:

            return (
                "background-color: darkgreen;"
                "color: white;"
                "font-weight: bold;"
            )

        # ----------------------------------------------------
        # 80 - 90
        # ----------------------------------------------------

        elif val >= 80:

            return (
                "background-color: lightgreen;"
                "color: black;"
            )

        return ""

    # ========================================================
    # FORMAT
    # ========================================================

    format_dict = {

        "change %":
            "{:.2f}%",

        "Trigger":
            "{:.2f}",

        "ltp":
            "{:.2f}",

        "StrikePrice":
            "{:.2f}"
    }

    # ========================================================
    # TWO COLUMNS
    # ========================================================

    col1, col2 = st.columns(2)

    # ========================================================
    # CALLS
    # ========================================================

    with col1:

        st.subheader(
            "Calls (CE)"
        )

        st.dataframe(

            calls_df[
                display_cols
            ]
            .style
            .map(
                color_change,
                subset=["change %"]
            )
            .format(
                format_dict
            )
            .set_properties(
                **{
                    "font-weight":
                        "600",

                    "text-align":
                        "center",

                    "font-size":
                        "16px"
                }
            ),

            hide_index=True,

            use_container_width=True,

            height=1800
        )

    # ========================================================
    # PUTS
    # ========================================================

    with col2:

        st.subheader(
            "Puts (PE)"
        )

        st.dataframe(

            puts_df[
                display_cols
            ]
            .style
            .map(
                color_change,
                subset=["change %"]
            )
            .format(
                format_dict
            )
            .set_properties(
                **{
                    "font-weight":
                        "600",

                    "text-align":
                        "center",

                    "font-size":
                        "16px"
                }
            ),

            hide_index=True,

            use_container_width=True,

            height=1800
        )


# ============================================================
# CONFIGURATION
# ============================================================

is_client_view = (
    "UPSTOX_ACCESS_TOKEN"
    in st.secrets
    and
    st.secrets[
        "UPSTOX_ACCESS_TOKEN"
    ].strip()
    != ""
)


# ============================================================
# CLIENT VIEW
# ============================================================

if is_client_view:

    access_token = (
        st.secrets[
            "UPSTOX_ACCESS_TOKEN"
        ]
    )

    st.markdown("""
        <style>
            [data-testid="stSidebar"] {
                display: none;
            }
        </style>
    """, unsafe_allow_html=True)

    auto_refresh = True

    refresh_interval = 15

    target_expiry_idx = 0

    expiry_type = "Current Month"

    # --------------------------------------------------------
    # Telegram config in client view comes from secrets only,
    # since the sidebar (with its manual controls) is hidden.
    # --------------------------------------------------------

    telegram_bot_token = st.secrets.get("TELEGRAM_BOT_TOKEN", "")

    telegram_chat_id = st.secrets.get("TELEGRAM_CHAT_ID", "")

    telegram_enabled = bool(
        telegram_bot_token and telegram_chat_id
    )


# ============================================================
# ADMIN VIEW
# ============================================================

else:

    with st.sidebar:

        st.header(
            "Configuration"
        )

        # ----------------------------------------------------
        # TOKEN
        # ----------------------------------------------------

        saved_token = load_token()

        access_token = st.text_input(
            "Upstox Access Token",
            value=saved_token,
            type="password"
        )

        if (
            access_token
            and
            access_token != saved_token
        ):

            save_token(
                access_token
            )

        st.markdown("---")

        # ----------------------------------------------------
        # EXPIRY
        # ----------------------------------------------------

        st.header(
            "Expiry Settings"
        )

        expiry_type = st.radio(

            "Select Expiry Month",

            options=[
                "Current Month",
                "Next Month"
            ],

            index=0,

            help=(
                "Choose which expiry "
                "month to display data for."
            )
        )

        target_expiry_idx = (
            0
            if expiry_type
            ==
            "Current Month"
            else
            1
        )

        st.markdown("---")

        # ----------------------------------------------------
        # TELEGRAM TRIGGER ALERTS
        # ----------------------------------------------------

        st.header(
            "Telegram Alerts"
        )

        telegram_enabled = st.checkbox(
            "Enable Trigger Alerts",
            value=st.session_state.get(
                "telegram_enabled", False
            ),
            key="telegram_enabled",
            help=(
                "Sends a Telegram message the moment an "
                "option's LTP crosses its Trigger price "
                "(change % >= 100)."
            )
        )

        telegram_bot_token = st.text_input(
            "Bot Token",
            type="password",
            value=st.session_state.get(
                "telegram_bot_token", ""
            ),
            key="telegram_bot_token",
            help="Create a bot via @BotFather on Telegram to get this token."
        )

        telegram_chat_id = st.text_input(
            "Chat ID",
            value=st.session_state.get(
                "telegram_chat_id", ""
            ),
            key="telegram_chat_id",
            help="Your personal or group chat ID. Message @userinfobot to find yours."
        )

        tg_col1, tg_col2 = st.columns(2)

        test_telegram_clicked = tg_col1.button(
            "Send Test",
            use_container_width=True
        )

        reset_alert_state_clicked = tg_col2.button(
            "Reset Alerts",
            use_container_width=True
        )

        if reset_alert_state_clicked:

            save_trigger_alert_state(set())

            st.success(
                "Alert state cleared — "
                "already-triggered options "
                "will alert again."
            )

        if test_telegram_clicked:

            success, error = send_telegram_alert(
                telegram_bot_token,
                telegram_chat_id,
                "✅ Test alert from Positional Option Scanner — "
                "Telegram is wired up correctly."
            )

            if success:

                st.success(
                    "Test message sent — check Telegram."
                )

            else:

                st.error(
                    f"Test message failed: {error}"
                )

        st.markdown("---")

        # ----------------------------------------------------
        # DATA MANAGEMENT
        # ----------------------------------------------------

        st.header(
            "Data Management"
        )

        if st.button(
            "⚡ Refresh LTP Now",
            use_container_width=True
        ):

            st.session_state[
                "force_refresh_ltp"
            ] = True

            st.rerun()

        # ----------------------------------------------------
        # NSE JSON
        # ----------------------------------------------------

        st.subheader(
            "NSE Instrument JSON"
        )

        if st.button(
            "🔄 Download Latest"
        ):

            try:

                with st.spinner(
                    "Downloading latest NSE.json..."
                ):

                    url = (
                        "https://assets.upstox.com/"
                        "market-quote/instruments/"
                        "exchange/NSE.json.gz"
                    )

                    headers = {
                        "User-Agent":
                            "Mozilla/5.0"
                    }

                    response = requests.get(
                        url,
                        headers=headers,
                        stream=True
                    )

                    if response.status_code == 200:

                        with open(
                            NSE_JSON_PATH,
                            "wb"
                        ) as f_out:

                            with gzip.GzipFile(
                                fileobj=response.raw
                            ) as f_in:

                                shutil.copyfileobj(
                                    f_in,
                                    f_out
                                )

                        st.cache_data.clear()

                        st.success(
                            "Updated successfully!"
                        )

                        time.sleep(1)

                        st.rerun()

                    else:

                        st.error(
                            "Failed to download. "
                            f"Status: "
                            f"{response.status_code}"
                        )

            except Exception as e:

                st.error(
                    f"Error: {e}"
                )

        # ====================================================
        # MONTHLY UPLOAD
        # ====================================================

        st.subheader(
            "Monthly"
        )

        up_m = st.file_uploader(
            "Upload Monthly Bhavcopy",
            type=["zip"],
            key="m_up"
        )

        if up_m is not None:

            csv_content, csv_name = (
                extract_csv_from_zip(
                    up_m
                )
            )

            if csv_content:

                with open(
                    FILES["Monthly"],
                    "wb"
                ) as f:

                    f.write(
                        csv_content
                    )

                date_str = (
                    extract_date_from_filename(
                        csv_name
                    )
                )

                if date_str:

                    save_meta(
                        "Monthly",
                        date_str
                    )

                st.success(
                    f"Monthly file updated "
                    f"from {csv_name}!"
                )

        meta = load_meta()

        if (
            "Monthly" in meta
            and
            os.path.exists(
                FILES["Monthly"]
            )
        ):

            st.caption(
                f"📅 Data Date: "
                f"{meta['Monthly']}"
            )

        elif os.path.exists(
            FILES["Monthly"]
        ):

            m_time = os.path.getmtime(
                FILES["Monthly"]
            )

            st.caption(
                "📅 Last Updated: "
                f"{datetime.fromtimestamp(m_time).strftime('%Y-%m-%d %H:%M')}"
            )

        # ====================================================
        # WEEKLY UPLOAD
        # ====================================================

        st.subheader(
            "Weekly"
        )

        up_w = st.file_uploader(
            "Upload Weekly Bhavcopy",
            type=["zip"],
            key="w_up"
        )

        if up_w is not None:

            csv_content, csv_name = (
                extract_csv_from_zip(
                    up_w
                )
            )

            if csv_content:

                with open(
                    FILES["Weekly"],
                    "wb"
                ) as f:

                    f.write(
                        csv_content
                    )

                date_str = (
                    extract_date_from_filename(
                        csv_name
                    )
                )

                if date_str:

                    save_meta(
                        "Weekly",
                        date_str
                    )

                st.success(
                    f"Weekly file updated "
                    f"from {csv_name}!"
                )

        if (
            "Weekly" in meta
            and
            os.path.exists(
                FILES["Weekly"]
            )
        ):

            st.caption(
                f"📅 Data Date: "
                f"{meta['Weekly']}"
            )

        elif os.path.exists(
            FILES["Weekly"]
        ):

            w_time = os.path.getmtime(
                FILES["Weekly"]
            )

            st.caption(
                "📅 Last Updated: "
                f"{datetime.fromtimestamp(w_time).strftime('%Y-%m-%d %H:%M')}"
            )

        # ====================================================
        # INTRADAY UPLOAD
        # ====================================================

        st.subheader(
            "Intraday"
        )

        up_i = st.file_uploader(
            "Upload Intraday Bhavcopy",
            type=["zip"],
            key="i_up"
        )

        if up_i is not None:

            csv_content, csv_name = (
                extract_csv_from_zip(
                    up_i
                )
            )

            if csv_content:

                with open(
                    FILES["Intraday"],
                    "wb"
                ) as f:

                    f.write(
                        csv_content
                    )

                date_str = (
                    extract_date_from_filename(
                        csv_name
                    )
                )

                if date_str:

                    save_meta(
                        "Intraday",
                        date_str
                    )

                st.success(
                    f"Intraday file updated "
                    f"from {csv_name}!"
                )

        if (
            "Intraday" in meta
            and
            os.path.exists(
                FILES["Intraday"]
            )
        ):

            st.caption(
                f"📅 Data Date: "
                f"{meta['Intraday']}"
            )

        elif os.path.exists(
            FILES["Intraday"]
        ):

            i_time = os.path.getmtime(
                FILES["Intraday"]
            )

            st.caption(
                "📅 Last Updated: "
                f"{datetime.fromtimestamp(i_time).strftime('%Y-%m-%d %H:%M')}"
            )

        # ====================================================
        # AUTO REFRESH
        # ====================================================

        st.markdown("---")

        st.header(
            "Auto Refresh"
        )

        auto_refresh = st.checkbox(
            "Enable Auto-Refresh",
            value=False
        )

        refresh_interval = st.slider(
            "Refresh Interval (seconds)",
            min_value=5,
            max_value=60,
            value=15
        )


# ============================================================
# MAIN PAGE
# ============================================================

st.title(
    "Positional Stock Option Scanner"
)


# ============================================================
# LOAD NSE JSON
# ============================================================

nse_json_df = load_nse_json()


if not nse_json_df.empty:

    tab1, tab2, tab3 = st.tabs(
        [
            "Monthly",
            "Weekly",
            "Intraday"
        ]
    )

    run_every = (
        refresh_interval
        if auto_refresh
        else None
    )

    # ========================================================
    # MONTHLY
    # ========================================================

    with tab1:

        st.header(
            "Monthly Options "
            f"({expiry_type})"
        )

        if os.path.exists(
            FILES["Monthly"]
        ):

            @st.fragment(
                run_every=run_every
            )
            def show_monthly():

                df_m, target_exp, all_exps = (
                    process_bhavcopy(
                        FILES["Monthly"],
                        nse_json_df,
                        target_expiry_index=
                            target_expiry_idx
                    )
                )

                if target_exp:

                    st.info(
                        "📅 Displaying Expiry: "
                        f"**{target_exp.strftime('%d-%b-%Y')}**"
                    )

                display_option_chain(
                    df_m,
                    access_token,
                    "Monthly",
                    telegram_enabled,
                    telegram_bot_token,
                    telegram_chat_id
                )

            show_monthly()

        else:

            st.warning(
                "Monthly Bhavcopy file not found. "
                "Please upload in the sidebar."
            )

    # ========================================================
    # WEEKLY
    # ========================================================

    with tab2:

        st.header(
            "Weekly Options "
            f"({expiry_type})"
        )

        if os.path.exists(
            FILES["Weekly"]
        ):

            @st.fragment(
                run_every=run_every
            )
            def show_weekly():

                df_w, target_exp, all_exps = (
                    process_bhavcopy(
                        FILES["Weekly"],
                        nse_json_df,
                        target_expiry_index=
                            target_expiry_idx
                    )
                )

                if target_exp:

                    st.info(
                        "📅 Displaying Expiry: "
                        f"**{target_exp.strftime('%d-%b-%Y')}**"
                    )

                display_option_chain(
                    df_w,
                    access_token,
                    "Weekly",
                    telegram_enabled,
                    telegram_bot_token,
                    telegram_chat_id
                )

            show_weekly()

        else:

            st.warning(
                "Weekly Bhavcopy file not found. "
                "Please upload in the sidebar."
            )

    # ========================================================
    # INTRADAY
    # ========================================================

    with tab3:

        st.header(
            "Intraday Options"
        )

        if os.path.exists(
            FILES["Intraday"]
        ):

            @st.fragment(
                run_every=run_every
            )
            def show_intraday():

                df_i, target_exp, all_exps = (
                    process_bhavcopy(
                        FILES["Intraday"],
                        nse_json_df,
                        target_expiry_index=0
                    )
                )

                if target_exp:

                    st.info(
                        "📅 Displaying Expiry: "
                        f"**{target_exp.strftime('%d-%b-%Y')}**"
                    )

                display_option_chain(
                    df_i,
                    access_token,
                    "Intraday",
                    telegram_enabled,
                    telegram_bot_token,
                    telegram_chat_id
                )

            show_intraday()

        else:

            st.warning(
                "Intraday Bhavcopy file not found. "
                "Please upload in the sidebar."
            )


else:

    st.error(
        "Critical Error: "
        "NSE.json could not be loaded."
    )
