import streamlit as st
import pandas as pd
from datetime import date
import plotly.express as px
import plotly.graph_objects as go
from fpdf import FPDF
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
                    s_df = pd.DataFrame(columns=["Username", "calorie_goal", "goal_weight", "dark_mode", "unit"])
                    
                default_goal = 150.0 if new_unit == "lb" else 70.0
                new_s_df = pd.DataFrame([{"Username": new_user, "calorie_goal": 2000, "goal_weight": default_goal, "dark_mode": False, "unit": new_unit}])
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

if "celebrated_today" not in st.session_state: st.session_state.celebrated_today = False
if "goal_celebrated" not in st.session_state: st.session_state.goal_celebrated = False

# Load Settings specific to logged-in user
# --- Replace load_settings with this safe version ---
@st.cache_data(ttl=5)
def load_settings(username):
    try:
        s_df = conn.read(worksheet="Settings", ttl=0).dropna(how="all")
        user_s = s_df[s_df['Username'] == username]
        if not user_s.empty:
            unit_val = str(user_s.iloc[0].get('unit', 'lb'))
            if unit_val.lower() in ['nan', 'none', '']:
                unit_val = 'lb'
                
            return {
                "calorie_goal": int(user_s.iloc[0]['calorie_goal']),
                "goal_weight": float(user_s.iloc[0]['goal_weight']),
                "dark_mode": bool(user_s.iloc[0]['dark_mode']),
                "unit": unit_val
            }
    except Exception:
        pass
    return {"calorie_goal": 1900, "goal_weight": 170.0, "dark_mode": False, "unit": "lb"}

settings = load_settings(st.session_state.username)
CALORIE_GOAL = settings["calorie_goal"]
GOAL_WEIGHT = settings["goal_weight"]
DARK_MODE = settings["dark_mode"]
UNIT = settings["unit"]

# Math Conversions based on Unit
CALS_PER_UNIT = 3500 if UNIT == "lb" else 7700
PROTEIN_MULTIPLIER = 0.8 if UNIT == "lb" else 1.76

# Apply Dark Mode CSS
if DARK_MODE:
    st.markdown("""
        <style>
        .stApp { background-color: #121212; color: #FFFFFF; }
        div[data-testid="metric-container"] { background-color: #1E1E1E !important; border-left: 6px solid #4DA6FF !important; }
        .streak-box, .badge-box { background-color: #1E1E1E !important; color: #4DA6FF !important; border: 1px solid #4DA6FF; }
        h1, h2, h3, p, span { color: #E0E0E0 !important; }
        </style>
    """, unsafe_allow_html=True)
    theme_template = "plotly_dark"
else:
    st.markdown("""
        <style>
        div[data-testid="metric-container"] { background-color: #F0F8FF; border-radius: 10px; border-left: 6px solid #00509E; box-shadow: 2px 2px 5px rgba(0,0,0,0.05); }
        .streak-box { background-color: #E6F2FF; padding: 15px; border-radius: 10px; text-align: center; color: #00509E; font-weight: bold; font-size: 1.2rem; margin-bottom: 20px; }
        .badge-box { background-color: #00509E; color: white; padding: 15px; border-radius: 10px; text-align: center; font-weight: bold; font-size: 1.1rem; margin-bottom: 20px; }
        h1, h2, h3 { color: #00509E !important; font-family: 'Helvetica Neue', sans-serif;}
        </style>
    """, unsafe_allow_html=True)
    theme_template = "plotly_white"

# --- 3. LOAD CLOUD DATA (FILTERED BY USER) ---
try:
    df_all = conn.read(worksheet="Data", ttl=0).dropna(how="all")
    
    if df_all.empty:
        df_all = pd.DataFrame(columns=["Username", "Date", "Weight", "Calories", "Protein_g", "Workout_Day", "Notes"])
    
    if 'Weight_lb' in df_all.columns:
        df_all.rename(columns={'Weight_lb': 'Weight'}, inplace=True)
        
    for col in ["Weight", "Calories", "Protein_g"]:
        if col in df_all.columns:
            df_all[col] = pd.to_numeric(df_all[col], errors='coerce')
            
    df = df_all[df_all['Username'] == st.session_state.username].copy()
    if not df.empty:
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df = df.dropna(subset=['Date']).sort_values(by='Date').reset_index(drop=True)
except Exception:
    df_all = pd.DataFrame(columns=["Username", "Date", "Weight", "Calories", "Protein_g", "Workout_Day", "Notes"])
    df = pd.DataFrame()

# --- WEEKLY RECAP POP-UP (SUNDAYS) ---
if not df.empty and pd.Timestamp.now().day_name() == "Sunday" and "recap_shown" not in st.session_state:
    st.balloons()
    st.toast("📅 Happy Sunday! Check your Weekly Recap below!", icon="🎉")
    st.session_state.recap_shown = True

# --- TABS ---
tab_dashboard, tab_log, tab_sim, tab_data, tab_settings = st.tabs(["📊 Dashboard", "✍️ Log Entry", "🔮 Simulator", "📁 Edit History", "⚙️ Settings"])

# --- TAB: LOG ENTRY ---
with tab_log:
    st.header("Add or Update an Entry")
    with st.form("data_form", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            entry_date = st.date_input("Select Date", value=date.today())
            workout_day = st.checkbox("Did you workout today?")
        with col2:
            weight_input = st.number_input(f"Weight ({UNIT})", min_value=0.0, format="%.1f")
            notes_input = st.text_area("Notes", placeholder="How did you feel?", height=68)
        with col3:
            calorie_input = st.number_input("Calories", min_value=0, step=1)
            protein_input = st.number_input("Protein (g)", min_value=0, step=1)
        
        submitted = st.form_submit_button("Save Entry to Cloud", use_container_width=True)

        if submitted:
            entry_date_str = str(entry_date)
            new_data = {
                "Username": st.session_state.username, 
                "Date": entry_date_str, 
                "Weight": weight_input, 
                "Calories": calorie_input, 
                "Protein_g": protein_input, 
                "Workout_Day": workout_day, 
                "Notes": notes_input
            }
            
            mask = (df_all['Username'] == st.session_state.username) & (pd.to_datetime(df_all['Date'], errors='coerce').dt.strftime('%Y-%m-%d') == entry_date_str)
            if not df_all[mask].empty:
                idx = df_all[mask].index[0]
                for key, val in new_data.items():
                    df_all.at[idx, key] = val
                st.toast("Cloud entry updated!", icon="✅")
            else:
                new_entry_df = pd.DataFrame([new_data])
                df_all = pd.concat([df_all, new_entry_df], ignore_index=True)
                st.toast("New entry saved to Cloud!", icon="🎉")
            
            df_upload = df_all.copy()
            df_upload['Date'] = pd.to_datetime(df_upload['Date'], errors='coerce').dt.strftime('%Y-%m-%d')
            df_upload = df_upload.dropna(subset=['Date'])
            
            # Save to Cloud
            conn.update(worksheet="Data", data=df_upload)
            
            # Clear cache & rerun to show data instantly
            st.cache_data.clear()
            st.rerun()

# --- TAB: DASHBOARD ---
with tab_dashboard:
    if not df.empty:
        df['7-Day Avg'] = df['Weight'].rolling(window=7, min_periods=1).mean()
        first_weight = df.iloc[0]['Weight']
        current_weight = df.iloc[-1]['Weight']
        total_lost = first_weight - current_weight
        
        # --- BULLETPROOF STREAK & FREEZES ---
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
                    if gap == 1:
                        streak += 1
                    elif gap == 2 and freezes_used < freezes_earned:
                        streak += 1 
                        freezes_used += 1
                    else:
                        break
                        
        freezes_left = freezes_earned - freezes_used
        if streak > 0:
            freeze_text = f" (🧊 {freezes_left} Freezes Available)" if freezes_left > 0 else ""
            st.markdown(f"<div class='streak-box'>🔥 You are on a {streak}-day logging streak!{freeze_text}</div>", unsafe_allow_html=True)
        
        if "recap_shown" in st.session_state and pd.Timestamp.now().day_name() == "Sunday":
            with st.expander("✨ Your Weekly Recap (Sunday Special!)", expanded=True):
                st.write(f"**Great job this week!** You protected your streak ({streak} days).")
                st.write(f"Total weight lost since you started: **{total_lost:.1f} {UNIT}**.")

        # --- CORE METRICS ---
        col1, col2, col3, col4 = st.columns(4)
        col1.metric(f"Current Weight", f"{current_weight:.1f} {UNIT}")
        col2.metric(f"Distance to Goal", f"{(current_weight - GOAL_WEIGHT):.1f} {UNIT}")
        col3.metric(f"Total Lost", f"{total_lost:.1f} {UNIT}")
        col4.metric("Avg Cal (7D)", f"{df.tail(7)['Calories'].mean():.0f} kcal")
        
        # --- DYNAMIC REWARD TRACKER ---
        st.markdown("### 🎁 Next Reward Tracker")
        
        if st.session_state.username.lower() == "yani":
            rewards = [
                (181.9, "Video game", "-20 lb"), (176.9, "New gym shirt(s)", "-25 lb"),
                (171.9, "Arcade trip", "-30 lb"), (166.9, "New hat", "-35 lb"),
                (161.9, "Bowling trip", "-40 lb"), (156.9, "New gym pants", "-45 lb"),
                (151.9, "Nose piercing", "-50 lb"), (146.9, "New shoes", "-55 lb"),
                (141.9, "Cheat day", "-60 lb")
            ]
        else:
            # Generic Milestones for Friends
            rewards = [
                (first_weight - 5, "Level 1 Milestone", f"-5 {UNIT}"),
                (first_weight - 10, "Level 2 Milestone", f"-10 {UNIT}"),
                (first_weight - 15, "Level 3 Milestone", f"-15 {UNIT}"),
                (first_weight - 20, "Level 4 Milestone", f"-20 {UNIT}"),
                (first_weight - 25, "Level 5 Milestone", f"-25 {UNIT}")
            ]
        
        next_reward = None
        previous_target = first_weight
        for target, name, label in rewards:
            if current_weight > target:
                next_reward = (target, name, label, previous_target)
                break
            previous_target = target
            
        if next_reward:
            target_wt, reward_name, label, start_wt = next_reward
            progress_val = (start_wt - current_weight) / (start_wt - target_wt)
            progress_val = max(0.0, min(1.0, progress_val)) 
            amount_to_go = current_weight - target_wt
            st.write(f"**Next Unlock:** {reward_name} ({label}) — *Only {amount_to_go:.1f} {UNIT} to go!*")
            st.progress(progress_val)
        else:
            st.success("🎉 You have unlocked EVERY reward on your roadmap!")

        st.markdown("<hr>", unsafe_allow_html=True)
        
        # --- DATE FILTER ---
        st.write("### 📅 Timeframe Filter")
        time_filter = st.radio("Select range to view:", ["Last 7 Days", "Last 14 Days", "Last 30 Days", "All Time"], horizontal=True, label_visibility="collapsed")
        
        df_filtered = df.copy()
        now = pd.Timestamp.now().normalize()
        
        if time_filter == "Last 7 Days": df_filtered = df[df['Date'] >= (now - pd.Timedelta(days=7))]
        elif time_filter == "Last 14 Days": df_filtered = df[df['Date'] >= (now - pd.Timedelta(days=14))]
        elif time_filter == "Last 30 Days": df_filtered = df[df['Date'] >= (now - pd.Timedelta(days=30))]

        if df_filtered.empty:
            df_filtered = df.copy()

        # --- TDEE ESTIMATOR ---
        current_deficit = 0
        if len(df) >= 14:
            weight_diff = df.iloc[0]['Weight'] - df.iloc[-1]['Weight']
            avg_cals = df['Calories'].mean()
            est_tdee = avg_cals + ((weight_diff * CALS_PER_UNIT) / len(df))
            current_deficit = est_tdee - CALORIE_GOAL

        # --- WEIGHT CHART ---
        st.subheader("Weight Trend & Goal Forecast")
        fig_weight = go.Figure()
        fig_weight.add_trace(go.Scatter(x=df_filtered['Date'], y=df_filtered['Weight'], mode='markers', name=f'Daily Weight', marker=dict(color='#80BFFF', size=6)))
        fig_weight.add_trace(go.Scatter(x=df_filtered['Date'], y=df_filtered['7-Day Avg'], mode='lines', name='7-Day Trend', line=dict(color='#00509E', width=3)))
        fig_weight.add_hline(y=GOAL_WEIGHT, line_dash="dash", line_color="#28a745", annotation_text="Goal Weight", annotation_position="bottom left")
        
        if current_deficit > 0 and current_weight > GOAL_WEIGHT:
            days_to_goal = (current_weight - GOAL_WEIGHT) * CALS_PER_UNIT / current_deficit
            target_date = df['Date'].iloc[-1] + pd.Timedelta(days=days_to_goal)
            fig_weight.add_trace(go.Scatter(x=[df['Date'].iloc[-1], target_date], y=[current_weight, GOAL_WEIGHT], mode='lines', name='Goal Forecast', line=dict(color='#28a745', dash='dot', width=3)))
        
        fig_weight.update_layout(margin=dict(l=0, r=0, t=30, b=0), hovermode="x unified", legend=dict(yanchor="top", y=0.99, xanchor="right", x=0.99), template=theme_template)
        st.plotly_chart(fig_weight, use_container_width=True)

        # --- NUTRITION CHARTS ---
        st.subheader("Nutrition Insights")
        chart_col1, chart_col2 = st.columns([2, 1])
        
        with chart_col1:
            fig_nut = go.Figure()
            fig_nut.add_trace(go.Bar(x=df_filtered['Date'], y=df_filtered['Calories'], name='Calories', marker_color='#4DA6FF'))
            fig_nut.add_hline(y=CALORIE_GOAL, line_dash="dash", line_color="#FF0000", annotation_text="Calorie Target")
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
            
        # --- DEFICIT VS REALITY & DOW ---
        if len(df) >= 14:
            st.subheader("⚖️ Deficit vs. Reality")
            df_chart = df_filtered.copy()
            start_wt_chart = df_chart.iloc[0]['Weight']
            df_chart['Daily_Deficit'] = est_tdee - df_chart['Calories']
            df_chart['Cumulative_Deficit'] = df_chart['Daily_Deficit'].cumsum()
            df_chart['Expected_Weight'] = start_wt_chart - (df_chart['Cumulative_Deficit'] / CALS_PER_UNIT)
            
            fig_def = go.Figure()
            fig_def.add_trace(go.Scatter(x=df_chart['Date'], y=df_chart['Expected_Weight'], mode='lines', name='Math Expectation', line=dict(color='#80BFFF', dash='dot')))
            fig_def.add_trace(go.Scatter(x=df_chart['Date'], y=df_chart['7-Day Avg'], mode='lines', name='Actual Trend', line=dict(color='#FF9900', width=3)))
            fig_def.update_layout(margin=dict(l=0, r=0, t=30, b=0), hovermode="x unified", template=theme_template)
            st.plotly_chart(fig_def, use_container_width=True)

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
    st.write("Play with the numbers to see how your future changes.")
    if not df.empty and len(df) >= 14:
        weight_diff = df.iloc[0]['Weight'] - df.iloc[-1]['Weight']
        avg_cals = df['Calories'].mean()
        est_tdee = avg_cals + ((weight_diff * CALS_PER_UNIT) / len(df))

        sim_cals = st.slider("If I eat this many calories a day...", min_value=1200, max_value=3000, value=CALORIE_GOAL, step=50)
        sim_days = st.slider("For this many days...", min_value=7, max_value=90, value=30, step=7)
        
        daily_deficit = est_tdee - sim_cals
        sim_weight_lost = (daily_deficit * sim_days) / CALS_PER_UNIT
        sim_final_weight = df.iloc[-1]['Weight'] - sim_weight_lost
        
        if sim_weight_lost > 0:
            st.success(f"In {sim_days} days, you would lose **{sim_weight_lost:.1f} {UNIT}**, weighing exactly **{sim_final_weight:.1f} {UNIT}**!")
        else:
            st.warning(f"At {sim_cals} calories, you would gain **{abs(sim_weight_lost):.1f} {UNIT}**, weighing **{sim_final_weight:.1f} {UNIT}**.")
    else:
        st.info("Log 14 days of data to unlock the simulator (it needs your metabolism data first).")

# --- TAB: EDIT HISTORY & NOTES ---
with tab_data:
    st.header("Manage Cloud Data")
    
    # --- CSV IMPORT TOOL ---
    st.subheader("📤 Import Old Local Data")
    st.write("Upload your old `my_tracking_data.csv` file from your PC to merge it into the cloud database.")
    uploaded_file = st.file_uploader("Upload CSV File", type=["csv"])
    
    if uploaded_file is not None:
        if st.button("Merge Data to Cloud", type="primary"):
            old_df = pd.read_csv(uploaded_file)
            
            if 'Weight_lb' in old_df.columns:
                old_df.rename(columns={'Weight_lb': 'Weight'}, inplace=True)
            for col in ['Protein_g', 'Workout_Day']:
                if col not in old_df.columns:
                    old_df[col] = 0 if col == 'Protein_g' else False
            if 'Notes' not in old_df.columns: 
                old_df['Notes'] = ""
            
            old_df['Username'] = st.session_state.username
            
            old_df['Date'] = pd.to_datetime(old_df['Date'], errors='coerce')
            old_df = old_df.dropna(subset=['Date'])
            
            for col in ["Weight", "Calories", "Protein_g"]:
                old_df[col] = pd.to_numeric(old_df[col], errors='coerce')
            
            combined_df = pd.concat([df_all, old_df]).drop_duplicates(subset=['Username', 'Date'], keep='last')
            combined_df['Date'] = pd.to_datetime(combined_df['Date'])
            combined_df = combined_df.sort_values(by='Date').reset_index(drop=True)
            
            upload_df = combined_df.copy()
            combined_df['Date'] = pd.to_datetime(combined_df['Date'], errors='coerce')
            combined_df = combined_df.dropna(subset=['Date'])
            conn.update(worksheet="Data", data=upload_df)
            
            st.success("Your old data was successfully merged into the cloud! Your streak is restored.")
            st.cache_data.clear()
            st.rerun()
            
    st.markdown("<hr>", unsafe_allow_html=True)
    st.write("**Manual Editor:** Double-click a cell below to edit it directly.")
    
    if not df.empty:
        df_edit = df.copy()
        df_edit['Date'] = pd.to_datetime(df_edit['Date'])
        df_edit['Date'] = df_edit['Date'].dt.strftime('%Y-%m-%d')
        edited_df = st.data_editor(df_edit.sort_values(by='Date', ascending=False), num_rows="dynamic", use_container_width=True)
        if st.button("💾 Save Edits to Cloud", type="primary"):
            edited_df = edited_df.dropna(subset=['Date', 'Weight'])
            
            df_all_others = df_all[df_all['Username'] != st.session_state.username]
            new_df_all = pd.concat([df_all_others, edited_df])
            new_df_all['Date'] = pd.to_datetime(new_df_all['Date'], errors='coerce').dt.strftime('%Y-%m-%d')
            new_df_all = new_df_all.dropna(subset=['Date'])
            
            conn.update(worksheet="Data", data=new_df_all)
            st.success("Cloud database updated!")
            st.rerun()

# --- TAB: GOALS & SETTINGS ---
with tab_settings:
    st.header("⚙️ Cloud Settings")
    col1, col2, col3, col4 = st.columns(4)
    with col1: new_cal = st.number_input("Daily Calorie Goal", value=CALORIE_GOAL, step=50)
    with col2: new_weight = st.number_input(f"Goal Weight ({UNIT})", value=GOAL_WEIGHT, format="%.1f")
    with col3: new_unit = st.selectbox("Preferred Unit", ["lb", "kg"], index=0 if UNIT == "lb" else 1)
    with col4: 
        st.write("UI Theme")
        new_dark_mode = st.toggle("Enable Dark Mode", value=DARK_MODE)
        
    if st.button("Save Settings to Cloud", type="primary", use_container_width=True):
        s_df = conn.read(worksheet="Settings", ttl=0).dropna(how="all")
        s_df_others = s_df[s_df['Username'] != st.session_state.username]
        new_s_df = pd.DataFrame([{"Username": st.session_state.username, "calorie_goal": new_cal, "goal_weight": new_weight, "dark_mode": new_dark_mode, "unit": new_unit}])
        updated_s_df = pd.concat([s_df_others, new_s_df], ignore_index=True)
        
        conn.update(worksheet="Settings", data=updated_s_df)
        st.success("Cloud settings updated! Please wait a few seconds and refresh to see changes.")
        st.cache_data.clear()
        st.rerun()
        
    st.markdown("<hr>", unsafe_allow_html=True)
    st.subheader("📄 Generate PDF Report")
    if st.button("Generate Monthly PDF") and not df.empty:
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", 'B', 16)
        pdf.cell(200, 10, txt=f"{st.session_state.username}'s Health Report", ln=True, align='C')
        pdf.set_font("Arial", size=12)
        pdf.cell(200, 10, txt=f"Generated on: {date.today()}", ln=True, align='C')
        pdf.ln(10)
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(200, 10, txt="Core Metrics:", ln=True)
        pdf.set_font("Arial", size=12)
        pdf.cell(200, 10, txt=f"- Starting Weight: {df.iloc[0]['Weight']} {UNIT}", ln=True)
        pdf.cell(200, 10, txt=f"- Current Weight: {df.iloc[-1]['Weight']} {UNIT}", ln=True)
        pdf.cell(200, 10, txt=f"- Total Lost: {df.iloc[0]['Weight'] - df.iloc[-1]['Weight']:.1f} {UNIT}", ln=True)
        st.download_button(label="Download PDF Report", data=pdf.output(dest='S').encode('latin-1'), file_name=f"{st.session_state.username}_health_report.pdf", mime="application/pdf", type="primary")
