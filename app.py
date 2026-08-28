import streamlit as st
import pandas as pd
from datetime import date, datetime
import plotly.express as px
import plotly.graph_objects as go
from streamlit_gsheets import GSheetsConnection
import hashlib

# --- HELPER FUNCTION: PASSWORD ENCRYPTION ---
def make_hash(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

# --- 1. UI & STATE CONFIGURATION ---
st.set_page_config(page_title="Health Tracker", layout="wide")

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""

# Connect to Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 2. SECURE LOGIN & REGISTRATION SYSTEM ---
if not st.session_state.logged_in:
    st.title("🔒 Health Dashboard")
    
    try:
        users_df = conn.read(worksheet="Users", ttl=0).dropna(how="all")
    except Exception:
        users_df = pd.DataFrame(columns=["Username", "Password"])
        
    tab_login, tab_register = st.tabs(["Login", "Create Account"])
    
    with tab_login:
        st.write("Welcome back! Please log in.")
        user_login = st.text_input("Username", key="log_user")
        pwd_login = st.text_input("Password", type="password", key="log_pwd")
        
        if st.button("Login", type="primary"):
            if user_login in users_df['Username'].values:
                stored_hash = users_df[users_df['Username'] == user_login]['Password'].iloc[0]
                if stored_hash == make_hash(pwd_login):
                    st.session_state.logged_in = True
                    st.session_state.username = user_login
                    st.rerun()
                else:
                    st.error("Incorrect password.")
            else:
                st.error("Username not found. Please create an account.")
                
    with tab_register:
        st.write("Join the dashboard and track your progress.")
        new_user = st.text_input("New Username", key="reg_user")
        new_pwd = st.text_input("New Password", type="password", key="reg_pwd")
        new_unit = st.selectbox("Preferred Unit", ["lb", "kg"])
        
        if st.button("Create Account"):
            if new_user in users_df['Username'].values:
                st.error("Username already taken! Please choose another.")
            elif new_user == "" or new_pwd == "":
                st.warning("Please enter a username and password.")
            else:
                new_user_df = pd.DataFrame([{"Username": new_user, "Password": make_hash(new_pwd)}])
                users_df = pd.concat([users_df, new_user_df], ignore_index=True)
                conn.update(worksheet="Users", data=users_df)
                
                try:
                    s_df = conn.read(worksheet="Settings", ttl=0).dropna(how="all")
                except Exception:
                    s_df = pd.DataFrame(columns=["Username", "calorie_goal", "goal_weight", "dark_mode", "unit", "age", "height", "bf_pct", "manual_tdee"])
                    
                default_goal = 150.0 if new_unit == "lb" else 70.0
                new_s_df = pd.DataFrame([{"Username": new_user, "calorie_goal": 1900, "goal_weight": default_goal, "dark_mode": False, "unit": new_unit, "age": 25, "height": 65.0, "bf_pct": 0.0, "manual_tdee": 2000}])
                s_df = pd.concat([s_df, new_s_df], ignore_index=True)
                conn.update(worksheet="Settings", data=s_df)
                
                st.success("Account successfully created! You can now log in.")
    st.stop() 

# --- (APP CONTINUES BELOW IF LOGGED IN) ---

st.sidebar.write(f"👤 Logged in as: **{st.session_state.username}**")
if st.sidebar.button("Logout"):
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.rerun()

# Load Settings specific to logged-in user
@st.cache_data(ttl=5)
def load_settings(username):
    try:
        s_df = conn.read(worksheet="Settings", ttl=0).dropna(how="all")
        user_s = s_df[s_df['Username'] == username]
        if not user_s.empty:
            unit_val = user_s.iloc[0].get('unit', 'lb')
            if pd.isna(unit_val) or str(unit_val).lower() == 'nan' or str(unit_val).strip() == '':
                unit_val = "lb"
                
            return {
                "calorie_goal": int(user_s.iloc[0]['calorie_goal']),
                "goal_weight": float(user_s.iloc[0]['goal_weight']),
                "dark_mode": bool(user_s.iloc[0]['dark_mode']),
                "unit": str(unit_val),
                "age": int(user_s.iloc[0].get('age', 25)),
                "height": float(user_s.iloc[0].get('height', 65.0)),
                "bf_pct": float(user_s.iloc[0].get('bf_pct', 0.0)),
                # Fallback to the old ai_tdee column name so it doesn't break your existing cloud data
                "manual_tdee": float(user_s.iloc[0].get('ai_tdee', 2000.0)) 
            }
    except Exception:
        pass
    return {"calorie_goal": 1900, "goal_weight": 170.0, "dark_mode": False, "unit": "lb", "age": 25, "height": 65.0, "bf_pct": 0.0, "manual_tdee": 2000.0}

settings = load_settings(st.session_state.username)
BASE_CALORIE_GOAL = settings["calorie_goal"]
GOAL_WEIGHT = settings["goal_weight"]
DARK_MODE = settings["dark_mode"]
UNIT = settings["unit"]
AGE = settings["age"]
HEIGHT = settings["height"]
BF_PCT = settings["bf_pct"]
MANUAL_TDEE = settings["manual_tdee"]

CALS_PER_UNIT = 3500 if UNIT == "lb" else 7700
PROTEIN_MULTIPLIER = 0.8 if UNIT == "lb" else 1.76
HEIGHT_UNIT = "inches" if UNIT == "lb" else "cm"
WEIGHT_UNIT = "lbs" if UNIT == "lb" else "kg"

# --- UI COLOR & THEME INJECTION ---
if DARK_MODE:
    st.markdown("""
        <style>
        .stApp { background-color: #121212; color: #FFFFFF; }
        h1, h2, h3, p, span { color: #E0E0E0 !important; }
        div[data-testid="stMetric"] { background: linear-gradient(145deg, #1E1E1E, #2A2A2A); padding: 15px !important; border-radius: 12px !important; border-left: 6px solid #4DA6FF !important; box-shadow: 0 4px 10px rgba(0, 0, 0, 0.5) !important; transition: transform 0.2s ease, box-shadow 0.2s ease !important; height: 100%;}
        div[data-testid="stMetric"]:hover { transform: translateY(-5px) !important; box-shadow: 0 8px 15px rgba(77, 166, 255, 0.15) !important; }
        .streak-box { background: linear-gradient(145deg, #1E1E1E, #2A2A2A) !important; color: #4DA6FF !important; border: 1px solid #4DA6FF; padding: 15px; border-radius: 12px; text-align: center; font-weight: bold; font-size: 1.2rem; margin-bottom: 20px; box-shadow: 0 4px 10px rgba(0,0,0,0.5); transition: transform 0.2s ease; }
        .streak-box:hover { transform: translateY(-3px); }
        button[data-baseweb="tab"] { background-color: transparent !important; padding: 10px 20px !important; border-radius: 8px !important; margin-right: 5px !important; transition: all 0.3s ease !important; color: #A0A0A0 !important; }
        button[data-baseweb="tab"]:hover { background-color: rgba(77, 166, 255, 0.15) !important; transform: translateY(-2px); color: #4DA6FF !important; }
        button[data-baseweb="tab"][aria-selected="true"] { background-color: #4DA6FF !important; color: #121212 !important; font-weight: bold !important; box-shadow: 0 4px 6px rgba(77, 166, 255, 0.2) !important; }
        div[data-baseweb="tab-highlight"] { display: none !important; }
        div[data-baseweb="input"]:focus-within, div[data-baseweb="select"]:focus-within, div[data-baseweb="textarea"]:focus-within, div[data-testid="stChatInput"] textarea:focus { border-color: #4DA6FF !important; box-shadow: 0 0 0 1px #4DA6FF !important;}
        button[kind="primary"] { background-color: #4DA6FF !important; color: #121212 !important; border-color: #4DA6FF !important; font-weight: bold; }
        button[kind="primary"]:hover { background-color: #3388DD !important; border-color: #3388DD !important; }
        </style>
    """, unsafe_allow_html=True)
    theme_template = "plotly_dark"
else:
    st.markdown("""
        <style>
        .stApp { background-color: #F8F9FA; }
        h1, h2, h3 { color: #00509E !important; font-family: 'Helvetica Neue', sans-serif;}
        div[data-testid="stMetric"] { background: linear-gradient(145deg, #ffffff, #F0F8FF); padding: 15px !important; border-radius: 12px !important; border-left: 6px solid #4DA6FF !important; box-shadow: 0 4px 10px rgba(0, 80, 158, 0.08) !important; transition: transform 0.2s ease, box-shadow 0.2s ease !important; height: 100%;}
        div[data-testid="stMetric"]:hover { transform: translateY(-5px) !important; box-shadow: 0 8px 15px rgba(0, 80, 158, 0.15) !important; }
        .streak-box { background: linear-gradient(145deg, #E6F2FF, #ffffff); padding: 15px; border-radius: 12px; text-align: center; color: #00509E; font-weight: bold; font-size: 1.2rem; margin-bottom: 20px; box-shadow: 0 4px 10px rgba(0, 80, 158, 0.08); border: 1px solid #cce5ff; transition: transform 0.2s ease; }
        .streak-box:hover { transform: translateY(-3px); }
        button[data-baseweb="tab"] { background-color: transparent !important; padding: 10px 20px !important; border-radius: 8px !important; margin-right: 5px !important; transition: all 0.3s ease !important; color: #555555 !important; font-weight: 600 !important; }
        button[data-baseweb="tab"]:hover { background-color: rgba(0, 80, 158, 0.05) !important; transform: translateY(-2px); color: #00509E !important;}
        button[data-baseweb="tab"][aria-selected="true"] { background-color: #00509E !important; color: white !important; box-shadow: 0 4px 6px rgba(0, 80, 158, 0.2) !important; }
        div[data-baseweb="tab-highlight"] { display: none !important; }
        div[data-baseweb="input"]:focus-within, div[data-baseweb="select"]:focus-within, div[data-baseweb="textarea"]:focus-within, div[data-testid="stChatInput"] textarea:focus { border-color: #4DA6FF !important; box-shadow: 0 0 0 1px #4DA6FF !important;}
        button[kind="primary"] { background-color: #00509E !important; border-color: #00509E !important; }
        button[kind="primary"]:hover { background-color: #4DA6FF !important; border-color: #4DA6FF !important; color: white !important;}
        </style>
    """, unsafe_allow_html=True)
    theme_template = "plotly_white"

# --- 3. LOAD CLOUD DATA (FILTERED BY USER) ---
try:
    df_all = conn.read(worksheet="Data", ttl=0).dropna(how="all")
    if 'Weight_lb' in df_all.columns: df_all.rename(columns={'Weight_lb': 'Weight'}, inplace=True)
    if 'Weight_Timestamp' not in df_all.columns: df_all['Weight_Timestamp'] = ""
    else: df_all['Weight_Timestamp'] = df_all['Weight_Timestamp'].fillna("")
        
    for col in ["Weight", "Calories", "Protein_g"]:
        if col in df_all.columns:
            df_all[col] = pd.to_numeric(df_all[col], errors='coerce')
            
    df = df_all[df_all['Username'] == st.session_state.username].copy()
    if not df.empty:
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.sort_values(by='Date').reset_index(drop=True)
except Exception:
    df_all = pd.DataFrame(columns=["Username", "Date", "Weight_Timestamp", "Weight", "Calories", "Protein_g", "Workout_Day", "Notes"])
    df = pd.DataFrame()

# TDEE CALCULATION (Auto-Adaptive Engine)
if len(df) >= 14:
    weight_diff = df.iloc[0]['Weight'] - df.iloc[-1]['Weight']
    avg_cals = df['Calories'].mean()
    est_tdee = avg_cals + ((weight_diff * CALS_PER_UNIT) / len(df))
    adaptive_active = True
else:
    est_tdee = MANUAL_TDEE
    adaptive_active = False

# YANI PROTOCOL: Diet Break Trigger
diet_break_triggered = False
if st.session_state.username.lower() == "yani" and len(df) >= 7:
    recent_7 = df.tail(7)
    if recent_7.iloc[0]['Weight'] <= recent_7.iloc[-1]['Weight']:
        diet_break_triggered = True
        CALORIE_GOAL = int(est_tdee) 
    else:
        CALORIE_GOAL = BASE_CALORIE_GOAL
else:
    CALORIE_GOAL = BASE_CALORIE_GOAL

# --- TABS ---
tab_dashboard, tab_log, tab_sim, tab_data, tab_settings = st.tabs(["📊 Dashboard", "✍️ Log Entry", "🔮 Simulator", "📁 Edit History", "⚙️ Settings"])

# --- TAB: LOG ENTRY ---
with tab_log:
    st.header("Daily Tracking")
    log_tab1, log_tab2 = st.tabs(["🌅 Morning Weigh-In", "🌙 Evening Nutrition"])
    
    with log_tab1:
        with st.form("morning_form", clear_on_submit=True):
            col_m1, col_m2 = st.columns(2)
            with col_m1:
                entry_date_m = st.date_input("Date", value=date.today(), key="m_date")
                weight_input = st.number_input(f"Weight ({UNIT})", min_value=0.0, format="%.1f")
            
            with col_m2:
                st.markdown("<p style='font-size: 14px; color: #555555; margin-bottom: 5px;'>Time of Weigh-In</p>", unsafe_allow_html=True)
                
                # Default current time for quick-logging
                now = datetime.now()
                
                t_col1, t_col2 = st.columns([2, 1])
                with t_col1:
                    time_val = st.text_input("Time (HH:MM)", value=now.strftime("%I:%M"), key="weigh_time_text", label_visibility="collapsed")
                with t_col2:
                    ampm_val = st.selectbox("AM/PM", ["AM", "PM"], index=0 if now.strftime("%p") == "AM" else 1, key="weigh_ampm", label_visibility="collapsed")
                
                time_str = f"{time_val} {ampm_val}"
            
            if st.form_submit_button("Save Morning Weigh-In", use_container_width=True):
                entry_date_str = str(entry_date_m)
                mask = (df_all['Username'] == st.session_state.username) & (pd.to_datetime(df_all['Date']).dt.strftime('%Y-%m-%d') == entry_date_str)
                if not df_all[mask].empty:
                    idx = df_all[mask].index[0]
                    df_all.at[idx, 'Weight'] = weight_input
                    df_all.at[idx, 'Weight_Timestamp'] = time_str
                    st.toast("Morning weigh-in updated!", icon="✅")
                else:
                    new_entry = pd.DataFrame([{"Username": st.session_state.username, "Date": entry_date_str, "Weight_Timestamp": time_str, "Weight": weight_input, "Calories": 0, "Protein_g": 0, "Workout_Day": False, "Notes": ""}])
                    df_all = pd.concat([df_all, new_entry], ignore_index=True)
                    st.toast("Morning weigh-in saved!", icon="🎉")
                
                df_upload = df_all.copy()
                df_upload['Date'] = pd.to_datetime(df_upload['Date']).dt.strftime('%Y-%m-%d')
                conn.update(worksheet="Data", data=df_upload)
                
                st.rerun()

    with log_tab2:
        with st.form("evening_form", clear_on_submit=True):
            entry_date_e = st.date_input("Date", value=date.today(), key="e_date")
            col_e1, col_e2 = st.columns(2)
            with col_e1:
                calorie_input = st.number_input("Calories", min_value=0, step=1)
                protein_input = st.number_input("Protein (g)", min_value=0, step=1)
            with col_e2:
                workout_day = st.checkbox("Did you workout today?")
                notes_input = st.text_area("Notes", placeholder="How did you feel?", height=68)
            
            if st.form_submit_button("Save Evening Nutrition", use_container_width=True):
                entry_date_str = str(entry_date_e)
                mask = (df_all['Username'] == st.session_state.username) & (pd.to_datetime(df_all['Date']).dt.strftime('%Y-%m-%d') == entry_date_str)
                if not df_all[mask].empty:
                    idx = df_all[mask].index[0]
                    df_all.at[idx, 'Calories'] = calorie_input
                    df_all.at[idx, 'Protein_g'] = protein_input
                    df_all.at[idx, 'Workout_Day'] = workout_day
                    df_all.at[idx, 'Notes'] = notes_input
                    st.toast("Evening nutrition updated!", icon="✅")
                else:
                    new_entry = pd.DataFrame([{"Username": st.session_state.username, "Date": entry_date_str, "Weight_Timestamp": "", "Weight": 0.0, "Calories": calorie_input, "Protein_g": protein_input, "Workout_Day": workout_day, "Notes": notes_input}])
                    df_all = pd.concat([df_all, new_entry], ignore_index=True)
                    st.toast("Evening nutrition saved!", icon="🎉")
                df_upload = df_all.copy()
                df_upload['Date'] = pd.to_datetime(df_upload['Date']).dt.strftime('%Y-%m-%d')
                conn.update(worksheet="Data", data=df_upload)
                st.rerun()

# --- TAB: DASHBOARD ---
with tab_dashboard:
    if diet_break_triggered:
        st.warning(f"⚠️ **Diet Break Protocol Engaged:** Your weight hasn't dropped in 7 days. Your calorie goal has been temporarily raised to maintenance ({int(est_tdee)} kcal) to reset your metabolism.")

    if not df.empty:
        df['7-Day Avg'] = df['Weight'].rolling(window=7, min_periods=1).mean()
        first_weight = df.iloc[0]['Weight']
        current_weight = df.iloc[-1]['Weight']
        
        prev_weight = df.iloc[-2]['Weight'] if len(df) > 1 else current_weight
        weight_delta = current_weight - prev_weight
        total_lost = first_weight - current_weight
        
        last_time = df.iloc[-1].get('Weight_Timestamp', '')
        time_display = f" at {last_time}" if pd.notna(last_time) and str(last_time).strip() != "" else ""
        
        df_desc = df.sort_values(by='Date', ascending=False).reset_index(drop=True)
        streak = 0
        freezes_earned = len(df) // 7
        freezes_used = 0
        
        check_date = pd.Timestamp.now().normalize()
        if not df_desc.empty:
            last_log = df_desc.loc[0, 'Date'].normalize()
            if (check_date - last_log).days <= 1:
                streak = 1
                for i in range(1, len(df_desc)):
                    gap = (df_desc.loc[i-1, 'Date'] - df_desc.loc[i, 'Date']).days
                    if gap == 1: streak += 1
                    elif gap == 2 and freezes_used < freezes_earned: streak += 1; freezes_used += 1
                    else: break
                        
        freezes_left = freezes_earned - freezes_used
        if streak > 0:
            freeze_text = f" (🧊 {freezes_left} Freezes Available)" if freezes_left > 0 else ""
            st.markdown(f"<div class='streak-box'>🔥 You are on a {streak}-day logging streak!{freeze_text}</div>", unsafe_allow_html=True)
        
        # Inserted the calculated TDEE right onto the dashboard
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric(f"Current Weight", f"{current_weight:.1f} {UNIT}", delta=f"{weight_delta:+.1f} {UNIT}" if weight_delta != 0 else None, delta_color="inverse", help=f"Last logged{time_display}")
        
        tdee_label = f"{est_tdee:.0f} kcal"
        tdee_delta = "Adaptive (Auto)" if adaptive_active else "Manual Baseline"
        tdee_color = "normal" if adaptive_active else "off"
        col2.metric("Est. TDEE", tdee_label, delta=tdee_delta, delta_color=tdee_color)
        
        col3.metric(f"Distance to Goal", f"{(current_weight - GOAL_WEIGHT):.1f} {UNIT}", delta=" ", delta_color="off")
        col4.metric(f"Total Lost", f"{total_lost:.1f} {UNIT}", delta=" ", delta_color="off")
        col5.metric("Avg Cal (7D)", f"{df.tail(7)['Calories'].mean():.0f} kcal", delta=" ", delta_color="off")
        
        st.markdown("### 🎁 Next Reward Tracker")
        if st.session_state.username.lower() == "yani":
            rewards = [(181.9, "Video game", f"-20 {UNIT}"), (176.9, "New gym shirt(s)", f"-25 {UNIT}"), (171.9, "Arcade trip", f"-30 {UNIT}"), (166.9, "New hat", f"-35 {UNIT}"), (161.9, "Bowling trip", f"-40 {UNIT}"), (156.9, "New gym pants", f"-45 {UNIT}"), (151.9, "Nose piercing", f"-50 {UNIT}"), (146.9, "New shoes", f"-55 {UNIT}"), (141.9, "Cheat day", f"-60 {UNIT}")]
        else:
            rewards = [(first_weight - 5, "Level 1 Milestone", f"-5 {UNIT}"), (first_weight - 10, "Level 2 Milestone", f"-10 {UNIT}"), (first_weight - 15, "Level 3 Milestone", f"-15 {UNIT}"), (first_weight - 20, "Level 4 Milestone", f"-20 {UNIT}"), (first_weight - 25, "Level 5 Milestone", f"-25 {UNIT}")]
        
        next_reward = None
        previous_target = first_weight
        for target, name, label in rewards:
            if current_weight > target:
                next_reward = (target, name, label, previous_target)
                break
            previous_target = target
            
        if next_reward:
            target_wt, reward_name, label, start_wt = next_reward
            progress_val = max(0.0, min(1.0, (start_wt - current_weight) / (start_wt - target_wt))) 
            st.write(f"**Next Unlock:** {reward_name} ({label}) — *Only {(current_weight - target_wt):.1f} {UNIT} to go!*")
            st.progress(progress_val)
        else:
            st.success("🎉 You have unlocked EVERY reward on your roadmap!")

        st.markdown("<hr>", unsafe_allow_html=True)
        
        time_filter = st.radio("Select range to view:", ["Last 7 Days", "Last 14 Days", "Last 30 Days", "All Time"], horizontal=True, label_visibility="collapsed")
        df_filtered = df.copy()
        now = pd.Timestamp.now().normalize()
        
        if time_filter == "Last 7 Days": df_filtered = df[df['Date'] >= (now - pd.Timedelta(days=7))]
        elif time_filter == "Last 14 Days": df_filtered = df[df['Date'] >= (now - pd.Timedelta(days=14))]
        elif time_filter == "Last 30 Days": df_filtered = df[df['Date'] >= (now - pd.Timedelta(days=30))]
        if df_filtered.empty: df_filtered = df.copy()

        current_deficit = est_tdee - CALORIE_GOAL

        st.subheader("Weight Trend & Goal Forecast")
        fig_weight = go.Figure()
        fig_weight.add_trace(go.Scatter(x=df_filtered['Date'], y=df_filtered['Weight'], mode='markers', name=f'Daily Weight', marker=dict(color='#80BFFF', size=6)))
        fig_weight.add_trace(go.Scatter(x=df_filtered['Date'], y=df_filtered['7-Day Avg'], mode='lines', name='7-Day Trend', line=dict(color='#00509E', width=3)))
        fig_weight.add_hline(y=GOAL_WEIGHT, line_dash="dash", line_color="#28a745", annotation_text="Goal Weight", annotation_position="bottom left")
        
        if current_deficit > 50 and current_weight > GOAL_WEIGHT:
            days_to_goal = (current_weight - GOAL_WEIGHT) * CALS_PER_UNIT / current_deficit
            if days_to_goal < 3650:
                target_date = df['Date'].iloc[-1] + pd.Timedelta(days=days_to_goal)
                fig_weight.add_trace(go.Scatter(x=[df['Date'].iloc[-1], target_date], y=[current_weight, GOAL_WEIGHT], mode='lines', name='Goal Forecast', line=dict(color='#28a745', dash='dot', width=3)))
        
        fig_weight.update_layout(margin=dict(l=0, r=0, t=30, b=0), hovermode="x unified", legend=dict(yanchor="top", y=0.99, xanchor="right", x=0.99), template=theme_template)
        st.plotly_chart(fig_weight, use_container_width=True)

        st.subheader("Nutrition Insights")
        chart_col1, chart_col2 = st.columns([2, 1])
        with chart_col1:
            fig_nut = go.Figure()
            fig_nut.add_trace(go.Bar(x=df_filtered['Date'], y=df_filtered['Calories'], name='Calories', marker_color='#4DA6FF'))
            fig_nut.add_hline(y=CALORIE_GOAL, line_dash="dash", line_color="#FF0000", annotation_text=f"Target ({CALORIE_GOAL} kcal)")
            fig_nut.add_trace(go.Scatter(x=df_filtered['Date'], y=df_filtered['Protein_g'], name='Protein (g)', mode='lines+markers', line=dict(color='#FF9900', width=3), yaxis='y2'))
            fig_nut.update_layout(margin=dict(l=0, r=0, t=30, b=0), hovermode="x unified", yaxis=dict(title="Calories"), yaxis2=dict(title="Protein (g)", overlaying="y", side="right", showgrid=False), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1), template=theme_template)
            st.plotly_chart(fig_nut, use_container_width=True)
            
        with chart_col2:
            recent_protein = df_filtered['Protein_g'].mean()
            recent_cals = df_filtered['Calories'].mean()
            pie_data = pd.DataFrame({"Source": ["Protein Cals", "Other Cals"], "Calories": [recent_protein * 4, max(recent_cals - (recent_protein * 4), 0)]})
            fig_pie = px.pie(pie_data, values='Calories', names='Source', hole=0.5, color_discrete_sequence=['#FF9900', '#80BFFF'])
            fig_pie.update_layout(margin=dict(l=20, r=20, t=30, b=20), legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5), template=theme_template)
            st.plotly_chart(fig_pie, use_container_width=True)
            
        col_dow, col_scatter = st.columns(2)
        with col_dow:
            st.subheader("📅 Day-of-Week Trends")
            df_filtered['DayOfWeek'] = df_filtered['Date'].dt.day_name()
            dow_stats = df_filtered.groupby('DayOfWeek')['Calories'].mean().reindex(['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']).reset_index()
            fig_dow = px.bar(dow_stats, x='DayOfWeek', y='Calories', color_discrete_sequence=['#4DA6FF'])
            fig_dow.add_hline(y=CALORIE_GOAL, line_dash="dash", line_color="#FF0000", annotation_text="Goal")
            fig_dow.update_layout(margin=dict(l=0, r=0, t=30, b=0), template=theme_template)
            st.plotly_chart(fig_dow, use_container_width=True)
            
        with col_scatter:
            st.subheader("🎯 Protein Efficiency")
            fig_scatter = px.scatter(df_filtered, x='Calories', y='Protein_g', hover_data=['Date'], color='Protein_g', color_continuous_scale=['#99ccff', '#00509E'])
            fig_scatter.add_vline(x=CALORIE_GOAL, line_dash="dash", line_color="#FF0000", annotation_text="Limit")
            fig_scatter.add_hline(y=GOAL_WEIGHT * PROTEIN_MULTIPLIER, line_dash="dash", line_color="#FF0000", annotation_text="Target")
            fig_scatter.update_layout(margin=dict(l=0, r=0, t=30, b=0), coloraxis_showscale=False, template=theme_template)
            st.plotly_chart(fig_scatter, use_container_width=True)

    else:
        st.info("No data yet. Head over to the 'Log Entry' tab!")

# --- TAB: SIMULATOR ---
with tab_sim:
    st.header("🔮 'What-If' Simulator")
    if not df.empty:
        sim_cals = st.slider("If I eat this many calories a day...", min_value=1200, max_value=3500, value=CALORIE_GOAL, step=50)
        sim_days = st.slider("For this many days...", min_value=7, max_value=90, value=30, step=7)
        
        daily_deficit = est_tdee - sim_cals
        sim_weight_lost = (daily_deficit * sim_days) / CALS_PER_UNIT
        sim_final_weight = df.iloc[-1]['Weight'] - sim_weight_lost
        
        if sim_weight_lost > 0:
            st.success(f"In {sim_days} days, you would lose **{sim_weight_lost:.1f} {UNIT}**, weighing exactly **{sim_final_weight:.1f} {UNIT}**!")
        else:
            st.warning(f"At {sim_cals} calories, you would gain **{abs(sim_weight_lost):.1f} {UNIT}**, weighing **{sim_final_weight:.1f} {UNIT}**.")

# --- TAB: EDIT HISTORY & NOTES ---
with tab_data:
    st.header("Manage Cloud Data")
    st.write("**Manual Editor:** Double-click a cell below to edit it directly.")
    if not df.empty:
        df_edit = df.copy()
        df_edit['Date'] = pd.to_datetime(df_edit['Date']).dt.strftime('%Y-%m-%d')
        edited_df = st.data_editor(df_edit.sort_values(by='Date', ascending=False), num_rows="dynamic", use_container_width=True)
        if st.button("💾 Save Edits to Cloud", type="primary"):
            edited_df = edited_df.dropna(subset=['Date', 'Weight'])
            df_all_others = df_all[df_all['Username'] != st.session_state.username]
            new_df_all = pd.concat([df_all_others, edited_df])
            new_df_all['Date'] = pd.to_datetime(new_df_all['Date']).dt.strftime('%Y-%m-%d')
            conn.update(worksheet="Data", data=new_df_all)
            st.success("Cloud database updated!")
            st.rerun()

# --- TAB: GOALS & SETTINGS ---
with tab_settings:
    st.header("⚙️ Cloud Settings & Profile")
    
    col1, col2, col3 = st.columns(3)
    with col1: 
        new_cal = st.number_input("Base Calorie Goal", value=BASE_CALORIE_GOAL, step=50)
        new_age = st.number_input("Age", value=AGE, step=1)
    with col2: 
        new_weight = st.number_input(f"Goal Weight ({UNIT})", value=GOAL_WEIGHT, format="%.1f")
        new_height = st.number_input(f"Total Height ({HEIGHT_UNIT})", value=HEIGHT, format="%.1f")
    with col3: 
        new_unit = st.selectbox("Preferred Unit", ["lb", "kg"], index=0 if UNIT == "lb" else 1)
        # Allows manually forcing a TDEE baseline before the system auto-calculates after 14 days
        new_manual_tdee = st.number_input("Manual TDEE Baseline", value=int(MANUAL_TDEE), step=50)
        
    new_bf = st.number_input("Body Fat % (Leave at 0 to ignore)", value=BF_PCT, format="%.1f")
    new_dark_mode = st.toggle("Enable Dark Mode", value=DARK_MODE)
        
    if st.button("Save Settings to Cloud", type="primary", use_container_width=True):
        s_df = conn.read(worksheet="Settings", ttl=0).dropna(how="all")
        s_df_others = s_df[s_df['Username'] != st.session_state.username]
        # We save 'new_manual_tdee' back into the 'ai_tdee' column so it doesn't break the existing cloud schema
        new_s_df = pd.DataFrame([{"Username": st.session_state.username, "calorie_goal": new_cal, "goal_weight": new_weight, "dark_mode": new_dark_mode, "unit": new_unit, "age": new_age, "height": new_height, "bf_pct": new_bf, "ai_tdee": new_manual_tdee}])
        updated_s_df = pd.concat([s_df_others, new_s_df], ignore_index=True)
        
        conn.update(worksheet="Settings", data=updated_s_df)
        st.success("Cloud settings updated!")
        st.cache_data.clear()
        st.rerun()
