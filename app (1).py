import json
import sqlite3
from datetime import datetime, date, time, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

import astra_ui
import mars_mission as mm
import astra_insights as insights

st.set_page_config(
    page_title="ASTRA | Astronaut Health & Mission Simulation",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded",
)

DB_PATH = Path(__file__).with_name("astra_records.db")

# ---------- Visual theme (Combined CSS from both files) ----------
st.markdown("""
<style>
    .stApp { background: #07111f; color: #edf4ff; }
    [data-testid="stSidebar"] { background: #0b1a2c; }
    [data-testid="stMetric"] {
        background: linear-gradient(135deg, #10263b, #0c1b2d);
        border: 1px solid #23425c;
        padding: 14px 16px;
        border-radius: 14px;
    }
    div[data-testid="stAlert"] { border-radius: 12px; }
    .hero {
        padding: 22px 24px; border: 1px solid #23445f; border-radius: 18px;
        background: linear-gradient(115deg, #102a42 0%, #102039 55%, #142044 100%);
        margin-bottom: 18px;
    }
    .eyebrow { color: #61d9d0; font-size: 0.8rem; letter-spacing: 0.16em; font-weight: 700; }
    .muted { color: #9db3ca; }
    .pill {
        display: inline-block; border: 1px solid #31536f; border-radius: 999px;
        padding: 4px 10px; color: #aeece7; font-size: 0.8rem; margin-right: 6px;
    }
    .section-card {
        background: linear-gradient(145deg, #0d2033, #0b1929); border: 1px solid #24445e; padding: 16px;
        border-radius: 14px; margin-bottom: 10px; box-shadow: 0 8px 22px rgba(0,0,0,.12);
    }
    div[data-testid="stTabs"] button { color: #b8cde1; }
    div[data-testid="stTabs"] button[aria-selected="true"] { color: #61d9d0; }
    h1, h2, h3 { color: #f2f7ff; }
</style>
""", unsafe_allow_html=True)
astra_ui.inject_css()

# ---------- Persistent storage ----------
def db_connect():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    with db_connect() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS health_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, logged_at TEXT NOT NULL, mission TEXT NOT NULL,
            crew TEXT NOT NULL, checkin TEXT NOT NULL, heart_rate REAL, spo2 REAL, respiration REAL,
            skin_temp REAL, systolic REAL, diastolic REAL, fatigue REAL, mood REAL, sleep_hours REAL,
            water_litres REAL, exercise_minutes REAL, exercise_type TEXT, calories REAL,
            co2 REAL, oxygen REAL, cabin_pressure REAL, temperature REAL, humidity REAL,
            particles REAL, radiation REAL, notes TEXT)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS simulation_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, saved_at TEXT NOT NULL, mission TEXT NOT NULL,
            crew TEXT NOT NULL, simulated_minutes INTEGER, inputs_json TEXT NOT NULL,
            status TEXT NOT NULL, alerts_json TEXT NOT NULL)""")

def load_health_logs(crew=None):
    with db_connect() as conn:
        if crew:
            return pd.read_sql_query("SELECT * FROM health_logs WHERE crew=? ORDER BY logged_at DESC, id DESC", conn, params=(crew,))
        return pd.read_sql_query("SELECT * FROM health_logs ORDER BY logged_at DESC, id DESC", conn)

init_db()

# ---------- Helpers ----------
def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

def clamp_num(value, low, high):
    return max(low, min(high, value))

def create_demo_history(heart_rate, spo2, fatigue, co2, hours=24):
    rng = np.random.default_rng(21)
    times = pd.date_range(end=pd.Timestamp.now(), periods=hours, freq="h")
    n = len(times)
    return pd.DataFrame({
        "Time": times,
        "Heart rate (bpm)": np.clip(heart_rate + rng.normal(0, 4, n), 35, 180),
        "SpO₂ (%)": np.clip(spo2 + rng.normal(0, 0.7, n), 70, 100),
        "Fatigue (1–10)": np.clip(fatigue + rng.normal(0, 0.8, n), 1, 10),
        "CO₂ (ppm)": np.clip(co2 + rng.normal(0, max(20, co2 * 0.035), n), 0, 30000),
    })

# ---------- Data sources & Navigation ----------
MANUAL = "Manual input"
MISSION_SOURCES = {mm.LABEL: mm}
SOURCES = [MANUAL] + list(MISSION_SOURCES)
PAGES = [
    "Overview",
    "Sensor Lab",
    "Crew Logs & Records",
    "Crew Resilience",
    "Mission Debrief",
    "Mission Library",
    "Knowledge Base",
    "Data Export",
]
CREW = ["Crew Member A", "Crew Member B", "Crew Member C"]
MISSION_PROFILES = ["Earth Orbit", "Lunar Mission", "Mars Transit"]

DEFAULTS = {
    "heart_rate": 76, "spo2": 98, "respiration": 16, "skin_temp": 36.7,
    "systolic": 118, "diastolic": 78, "fatigue": 3, "sleep": 7.5,
    "water": 2.0, "exercise": 30, "exercise_type": "Mixed / not specified", "calories": 2200, "mood": 7,
    "co2": 1000, "oxygen": 20.9, "cabin_pressure": 101.3, "temperature": 22.0,
    "humidity": 45, "particles": 5.0, "radiation": 0.5, "simulation_minutes": 0,
    "crew": CREW[0], "mission_profile": MISSION_PROFILES[0], "snapshots": [],
}
for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value
for key in DEFAULTS:
    st.session_state[key] = st.session_state[key]

st.sidebar.markdown("## 🛰️ ASTRA")
st.sidebar.caption("Astronaut Status • Telemetry • Risk Assessment")
st.sidebar.markdown("---")
page = st.sidebar.radio("MISSION CONSOLE", PAGES)
st.sidebar.markdown("---")

source = st.sidebar.selectbox("Data source", SOURCES, key="data_source")
mission_mod = MISSION_SOURCES.get(source)
for _mod in MISSION_SOURCES.values():
    _mod.sync_session(_mod is mission_mod, page == "Overview")

if mission_mod is None:
    mission = st.sidebar.selectbox("Mission scenario", MISSION_PROFILES, key="mission_profile")
else:
    mission = source

crew = st.sidebar.selectbox("Crew member", CREW, key="crew")
st.sidebar.info("DEMO MODE — not connected to real sensors or medical systems.")
st.sidebar.caption("Record persistence depends on the host's filesystem. For durable production hosting, configure an external database.")

# ---------- Rules & Evaluation ----------
def current_values():
    keys = [
        "heart_rate", "spo2", "respiration", "skin_temp", "systolic", "diastolic",
        "fatigue", "sleep", "mood", "water", "exercise", "calories",
        "co2", "oxygen", "cabin_pressure", "temperature", "humidity", "particles", "radiation"
    ]
    return {k: float(st.session_state[k]) for k in keys}

def evaluate_rules(v):
    a = []
    def add(level, key, msg): a.append((level, key, msg))
    if v["spo2"] < 90:
        add("HIGH", "SpO₂", "Oxygen saturation is below the illustrative review threshold; verify the input and follow approved procedures.")
    if v["heart_rate"] < 50 or v["heart_rate"] > 120:
        add("REVIEW", "Heart rate", "Heart-rate value is outside the illustrative review range; verify signal and context.")
    if v["respiration"] < 8 or v["respiration"] > 25:
        add("REVIEW", "Respiration", "Respiration is outside the illustrative review range.")
    if v["skin_temp"] < 33 or v["skin_temp"] > 38:
        add("REVIEW", "Skin temperature", "Skin temperature is outside the illustrative review range; check sensor placement and units.")
    if v["systolic"] < 90 or v["systolic"] > 140 or v["diastolic"] < 60 or v["diastolic"] > 90:
        add("REVIEW", "Blood pressure", "Blood pressure is outside the illustrative review range. Check the measurement and context.")
    if v["systolic"] <= v["diastolic"]:
        add("REVIEW", "Blood pressure data quality", "Systolic pressure should normally exceed diastolic pressure; verify the entered values.")
    if v["fatigue"] >= 8:
        add("REVIEW", "Fatigue", "High self-reported fatigue; review workload and crew check-in procedures.")
    if v["sleep"] < 6:
        add("REVIEW", "Sleep", "Reported sleep is below the illustrative review value.")
    if v["mood"] <= 3:
        add("REVIEW", "Mood", "Low self-reported mood score; consider a private crew wellbeing check-in.")
    if v["co2"] > 5000:
        add("HIGH", "CO₂", "CO₂ exceeds the illustrative prototype threshold.")
    if v["oxygen"] < 18 or v["oxygen"] > 25:
        add("HIGH", "Oxygen concentration", "Oxygen concentration is outside the illustrative review range; verify units and scenario assumptions.")
    if v["cabin_pressure"] < 70 or v["cabin_pressure"] > 110:
        add("HIGH", "Cabin pressure", "Cabin pressure is outside the illustrative scenario range.")
    if v["temperature"] < 18 or v["temperature"] > 28:
        add("REVIEW", "Cabin temperature", "Cabin temperature is outside the illustrative comfort-review range.")
    if v["humidity"] < 20 or v["humidity"] > 70:
        add("REVIEW", "Relative humidity", "Humidity is outside the illustrative review range.")
    if v["particles"] > 50:
        add("REVIEW", "Particles", "Particle concentration exceeds the illustrative review value; confirm sensor units and baseline.")
    if v["radiation"] > 2:
        add("REVIEW", "Radiation", "Review radiation units, dose-rate context and mission-specific limits.")
    return a

def render_alerts(alerts):
    if not alerts:
        st.success("No illustrative prototype rules triggered. This is not medical or flight clearance.")
        return
    for level, key, msg in alerts:
        (st.error if level == "HIGH" else st.warning)(f"**{level} · {key}:** {msg}")

def status_label(alerts):
    if any(x[0] == "HIGH" for x in alerts):
        return "ATTENTION REQUIRED"
    if alerts:
        return "REVIEW INPUTS"
    return "NO DEMO RULES TRIGGERED"

def values_to_db(v):
    return (
        v["heart_rate"], v["spo2"], v["respiration"], v["skin_temp"], v["systolic"], v["diastolic"],
        v["fatigue"], v["mood"], v["sleep"], v["water"], v["exercise"], st.session_state.exercise_type,
        v["calories"], v["co2"], v["oxygen"], v["cabin_pressure"], v["temperature"], v["humidity"],
        v["particles"], v["radiation"]
    )

vals = current_values()
alerts = evaluate_rules(vals)

if mission_mod is None:
    astra_ui.manual_toasts(alerts, st.session_state)
else:
    st.session_state.pop("_ax_prev_alerts", None)

# ---------- Header ----------
st.markdown(f"""
<div class="hero">
  <div class="eyebrow">MISSION CONTROL / HUMAN SYSTEMS</div>
  <h1 style="margin-bottom:4px;">ASTRA <span style="color:#61d9d0;">//</span> Crew Health Console</h1>
  <div class="muted">Astronaut health trends • cabin telemetry • scenario simulation</div>
  <br>
  <span class="pill">{mission.upper()}</span>
  <span class="pill">{crew.upper()}</span>
  <span class="pill">{source.upper()}</span>
  <div class="muted" style="margin-top:12px;font-size:0.8rem;">Last interface refresh: {utc_now()}</div>
</div>
""", unsafe_allow_html=True)

# ---------- Pages ----------
if page == "Overview":
    insights.render_seven_day_dashboard_alerts(DB_PATH, crew)
    if mission_mod is not None:
        mission_mod.render_console(evaluate_rules)
    else:
        st.subheader("Mission overview")
        st.caption("Illustrative demonstration values only; not medical thresholds or operational guidance.")
        astra_ui.render_overview(vals, alerts)

        st.markdown("### Telemetry trend preview")
        hist = create_demo_history(
            st.session_state.heart_rate,
            st.session_state.spo2,
            st.session_state.fatigue,
            st.session_state.co2,
        )
        metric = st.selectbox("Trend to view", ["Heart rate (bpm)", "SpO₂ (%)", "Fatigue (1–10)", "CO₂ (ppm)"])
        st.line_chart(hist.set_index("Time")[[metric]], height=260)
        st.caption("Synthetic 24-hour history for visual demonstration; not historical sensor measurements.")

        st.markdown("### Recent saved check-ins")
        logs = load_health_logs()
        if not logs.empty:
            st.dataframe(logs.head(5), use_container_width=True, hide_index=True)
        else:
            st.info("No saved check-ins yet. Add one in Crew Logs & Records.")

elif page == "Sensor Lab":
    locked = mission_mod is not None
    st.subheader("Sensor lab")
    st.caption("Crew and cabin sensors in one place. Edit values here and the shared values, overview and alerts update together. This is a rule-based demo, not a physiological model.")
    if locked:
        st.info(f"Inputs are read-only because they are driven by the **{source}** replay on the Overview page. Choose **{MANUAL}** as the data source to edit them.")

    st.markdown("#### Quick scenarios")
    q1, q2, q3, q4 = st.columns(4)
    if q1.button("Nominal demo", disabled=locked):
        for k, v in {
            "heart_rate": 76, "spo2": 98, "respiration": 16, "skin_temp": 36.7, "systolic": 118,
            "diastolic": 78, "fatigue": 3, "sleep": 7.5, "mood": 7, "co2": 1000, "oxygen": 20.9,
            "cabin_pressure": 101.3, "temperature": 22.0, "humidity": 45, "particles": 5.0, "radiation": 0.5
        }.items():
            st.session_state[k] = v
        st.rerun()
    if q2.button("High CO₂ / low O₂", disabled=locked):
        st.session_state.co2 = 6500
        st.session_state.oxygen = 16.0
        st.rerun()
    if q3.button("Fatigue / low sleep", disabled=locked):
        st.session_state.sleep = 4.0
        st.session_state.fatigue = 9
        st.rerun()
    if q4.button("Combined review", disabled=locked):
        for k, v in {
            "heart_rate": 132, "spo2": 94, "respiration": 27, "skin_temp": 38.5, "systolic": 150,
            "diastolic": 95, "fatigue": 8, "sleep": 4.5, "mood": 3, "co2": 6200, "oxygen": 17.0,
            "cabin_pressure": 101.3, "temperature": 30.0, "humidity": 78, "particles": 75.0, "radiation": 2.5
        }.items():
            st.session_state[k] = v
        st.rerun()

    x, y, z = st.columns(3)
    with x:
        st.markdown("#### Vital signs")
        st.slider("Heart rate (bpm)", 30, 180, key="heart_rate", disabled=locked)
        st.slider("SpO₂ (%)", 70, 100, key="spo2", disabled=locked)
        st.slider("Respiration (breaths/min)", 4, 40, key="respiration", disabled=locked)
        st.slider("Skin temperature (°C)", 30.0, 42.0, key="skin_temp", step=0.1, disabled=locked)
        st.slider("Systolic BP (mmHg)", 70, 200, key="systolic", disabled=locked)
        st.slider("Diastolic BP (mmHg)", 40, 130, key="diastolic", disabled=locked)
    with y:
        st.markdown("#### Crew self-report")
        st.slider("Fatigue (1–10)", 1, 10, key="fatigue", disabled=locked)
        st.slider("Mood (1–10)", 1, 10, key="mood", disabled=locked)
        st.slider("Sleep (hours)", 0.0, 12.0, key="sleep", step=0.5, disabled=locked)
        st.number_input("Water (litres)", 0.0, 10.0, key="water", step=0.25, disabled=locked)
        st.number_input("Exercise (minutes)", 0, 300, key="exercise", step=5, disabled=locked)
        st.selectbox("Exercise type", ["Mixed / not specified", "Resistance", "Cardio", "Mobility", "Rest day", "Other"], key="exercise_type", disabled=locked)
        st.number_input("Calories (kcal)", 0, 10000, key="calories", step=100, disabled=locked)
    with z:
        st.markdown("#### Cabin environment")
        st.slider("CO₂ (ppm)", 0, 20000, key="co2", step=100, disabled=locked)
        st.slider("Oxygen (%)", 0.0, 30.0, key="oxygen", step=0.1, disabled=locked)
        st.slider("Cabin pressure (kPa)", 0.0, 150.0, key="cabin_pressure", step=0.5, disabled=locked)
        st.slider("Temperature (°C)", -20.0, 50.0, key="temperature", step=0.5, disabled=locked)
        st.slider("Humidity (%)", 0, 100, key="humidity", disabled=locked)
        st.slider("Particles (demo units)", 0.0, 500.0, key="particles", step=1.0, disabled=locked)
        st.slider("Radiation (illustrative units/hour)", 0.0, 10.0, key="radiation", step=0.1, disabled=locked)

    st.caption("Actual limits depend on vehicle, sensor, mission and approved procedures. These are not operational thresholds.")
    st.slider("Advance mission time (minutes)", 0, 1440, key="simulation_minutes", step=15, disabled=locked)
    sim_vals = current_values()
    sim_alerts = evaluate_rules(sim_vals)

    st.markdown("#### Simulation response")
    render_alerts(sim_alerts)
    st.write("Status:", status_label(sim_alerts))
    st.json({
        "mission": mission,
        "crew": crew,
        "simulated_minutes": st.session_state.simulation_minutes,
        "inputs": sim_vals,
        "status": status_label(sim_alerts),
        "note": "Illustrative only; no validated physiological or mission model."
    })

    s1, s2 = st.columns(2)
    if s1.button("Save simulation snapshot", type="primary"):
        with db_connect() as conn:
            conn.execute(
                "INSERT INTO simulation_logs (saved_at,mission,crew,simulated_minutes,inputs_json,status,alerts_json) VALUES (?,?,?,?,?,?,?)",
                (utc_now(), mission, crew, int(st.session_state.simulation_minutes), json.dumps(sim_vals), status_label(sim_alerts), json.dumps([x[2] for x in sim_alerts]))
            )
        st.session_state.snapshots.append({
            "timestamp_utc": utc_now(), "mission": mission, "crew": crew,
            "simulation_minutes": st.session_state.simulation_minutes,
            "inputs": sim_vals, "status": status_label(sim_alerts),
            "alerts": [x[2] for x in sim_alerts]
        })
        st.success("Simulation snapshot saved to the local database and session queue.")

    if s2.button("Save health snapshot to persistent records"):
        with db_connect() as conn:
            conn.execute(
                "INSERT INTO health_logs (logged_at,mission,crew,checkin,heart_rate,spo2,respiration,skin_temp,systolic,diastolic,fatigue,mood,sleep_hours,water_litres,exercise_minutes,exercise_type,calories,co2,oxygen,cabin_pressure,temperature,humidity,particles,radiation,notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (utc_now(), mission, crew, "Current snapshot", *values_to_db(sim_vals), "Saved from Sensor Lab")
            )
        st.success("Saved to the local database. It should remain after a browser refresh on the same deployment filesystem.")

elif page == "Crew Logs & Records":
    st.subheader("Crew check-ins & historical records")
    st.warning("Prototype privacy notice: use fictional/demo data only. Do not enter real sensitive health records into a public demo.")
    st.markdown("### Add a historical or twice-daily check-in")
    st.caption(
        "Use the date and time fields to backfill older records. Check-ins are saved in SQLite, not just browser session state."
        + (f" The form is pre-filled from the current {source} sample." if mission_mod is not None else "")
    )
    with st.form("crew_checkin_form", clear_on_submit=False):
        d1, d2 = st.columns(2)
        with d1:
            log_date = st.date_input("Check-in date", value=date.today())
            log_time = st.time_input("Check-in time", value=time(8, 0))
            checkin = st.selectbox("Check-in slot", ["Morning", "Evening", "Additional / historical"])
            hr = st.number_input("Heart rate (bpm)", 30.0, 180.0, float(st.session_state.heart_rate), 1.0)
            spo = st.number_input("SpO₂ (%)", 70.0, 100.0, float(st.session_state.spo2), 0.5)
            resp = st.number_input("Respiration (breaths/min)", 4.0, 40.0, float(st.session_state.respiration), 1.0)
            skin = st.number_input("Skin temperature (°C)", 30.0, 42.0, float(st.session_state.skin_temp), 0.1)
            sys = st.number_input("Systolic BP (mmHg)", 50.0, 250.0, float(st.session_state.systolic), 1.0)
            dia = st.number_input("Diastolic BP (mmHg)", 30.0, 160.0, float(st.session_state.diastolic), 1.0)
        with d2:
            fatigue = st.slider("Fatigue (1–10)", 1, 10, int(st.session_state.fatigue), key="log_fatigue")
            mood = st.slider("Mood (1–10)", 1, 10, int(st.session_state.mood), key="log_mood")
            sleep = st.number_input("Sleep in last 24 hours (hours)", 0.0, 24.0, float(st.session_state.sleep), 0.5)
            water = st.number_input("Water intake (litres)", 0.0, 15.0, float(st.session_state.water), 0.25)
            exercise = st.number_input("Exercise duration (minutes)", 0.0, 600.0, float(st.session_state.exercise), 5.0)
            exercise_type = st.selectbox("Exercise type", ["Mixed / not specified", "Resistance", "Cardio", "Mobility", "Rest day", "Other"])
            calories = st.number_input("Calories (kcal)", 0.0, 15000.0, float(st.session_state.calories), 100.0)
            notes = st.text_area("Notes (optional; use demo text only)", max_chars=500)
        st.markdown("#### Environmental readings (optional for this check-in)")
        e1, e2, e3 = st.columns(3)
        with e1:
            co2 = st.number_input("CO₂ (ppm)", 0.0, 50000.0, float(st.session_state.co2), 100.0)
            oxygen = st.number_input("Oxygen (%)", 0.0, 100.0, float(st.session_state.oxygen), 0.1)
        with e2:
            pressure = st.number_input("Cabin pressure (kPa)", 0.0, 200.0, float(st.session_state.cabin_pressure), 0.5)
            temperature = st.number_input("Cabin temperature (°C)", -50.0, 80.0, float(st.session_state.temperature), 0.5)
        with e3:
            humidity = st.number_input("Humidity (%)", 0.0, 100.0, float(st.session_state.humidity), 1.0)
            particles = st.number_input("Particles (demo units)", 0.0, 10000.0, float(st.session_state.particles), 1.0)
            radiation = st.number_input("Radiation (illustrative units/hour)", 0.0, 1000.0, float(st.session_state.radiation), 0.1)
        submitted = st.form_submit_button("Save check-in permanently", type="primary")

    if submitted:
        stamp = f"{log_date.isoformat()} {log_time.strftime('%H:%M:%S')}"
        with db_connect() as conn:
            conn.execute(
                "INSERT INTO health_logs (logged_at,mission,crew,checkin,heart_rate,spo2,respiration,skin_temp,systolic,diastolic,fatigue,mood,sleep_hours,water_litres,exercise_minutes,exercise_type,calories,co2,oxygen,cabin_pressure,temperature,humidity,particles,radiation,notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (stamp, mission, crew, checkin, hr, spo, resp, skin, sys, dia, fatigue, mood, sleep, water, exercise, exercise_type, calories, co2, oxygen, pressure, temperature, humidity, particles, radiation, notes)
            )
        st.success(f"Saved {checkin.lower()} check-in for {crew} on {stamp}.")

    st.markdown("### Saved history")
    logs = load_health_logs(crew)
    if logs.empty:
        st.info("No saved records for this crew member yet.")
    else:
        st.caption(f"{len(logs)} saved check-in(s) for {crew}.")
        st.dataframe(logs, use_container_width=True, hide_index=True)
        st.download_button(
            "Download this crew member's history (CSV)",
            logs.to_csv(index=False),
            file_name=f"astra_{crew.lower().replace(' ', '_')}_health_logs.csv",
            mime="text/csv"
        )
        ids = logs["id"].astype(int).tolist()
        delete_id = st.selectbox("Record ID to delete", ids, key="delete_record_id")
        confirm = st.checkbox("I confirm I want to delete this selected demo record")
        if st.button("Delete selected record", disabled=not confirm):
            with db_connect() as conn:
                conn.execute("DELETE FROM health_logs WHERE id=? AND crew=?", (int(delete_id), crew))
            st.success("Record deleted.")
            st.rerun()

elif page == "Crew Resilience":
    insights.render_crew_resilience(DB_PATH, CREW, mm)

elif page == "Mission Debrief":
    insights.render_mission_debrief(DB_PATH, mm, CREW, mm.LABEL)

elif page == "Mission Library":
    st.subheader("Mission scenario library")
    st.caption("Illustrative presets for exploring how mission context changes the questions the team should ask.")
    mission_cards = {
        "Earth Orbit": {
            "focus": "Crew routine, exercise, sleep scheduling, cabin environmental trends.",
            "demo": "Use nominal values, then test missing readings and fatigue trends.",
            "note": "A real mission profile must be based on documented vehicle and mission data."
        },
        "Lunar Mission": {
            "focus": "Mission phase changes, surface operations, suit/environment transitions, radiation context.",
            "demo": "Compare cabin-mode inputs with a separately documented surface-operation scenario.",
            "note": "Do not apply cabin thresholds to spacesuit or surface data without appropriate validation."
        },
        "Mars Transit": {
            "focus": "Long-duration trend review, sleep and workload patterns, communications constraints, radiation exposure context.",
            "demo": "Use a longer synthetic timeline and explore trend alerts and stale sensor data.",
            "note": "Long-duration and radiation models require sourced assumptions; do not extrapolate from this toy model."
        },
    }
    default_idx = list(mission_cards.keys()).index(mission) if mission in mission_cards else 0
    selected = st.selectbox("Explore mission", list(mission_cards.keys()), index=default_idx)
    card = mission_cards[selected]
    st.markdown(f"### {selected}")
    st.write("**Monitoring focus:**", card["focus"])
    st.write("**Suggested simulation:**", card["demo"])
    st.info(card["note"])
    st.markdown("#### Research questions")
    st.write("- Which sensor measurements are available in this mission phase?")
    st.write("- What are the sensor units, calibration needs, and data-quality limits?")
    st.write("- Which approved references define alert criteria?")
    st.write("- What should the interface do when a measurement is missing or stale?")

elif page == "Knowledge Base":
    st.markdown("""
    <div class="hero" style="margin-top:4px;">
      <div class="eyebrow">ASTRA RESEARCH ARCHIVE / HUMAN SPACEFLIGHT</div>
      <h2 style="margin:8px 0 6px;">Knowledge Base <span style="color:#61d9d0;">✦</span></h2>
      <div class="muted">The science behind the signals — hazards, health risks, research directions and radiation-monitoring technology.</div>
    </div>
    """, unsafe_allow_html=True)

    st.info("SOURCE STATUS · These are authoritative research and educational references. They inform ASTRA's design, but they do not provide a live astronaut telemetry feed or direct CANS instrument readings to this prototype.")

    k1, k2, k3 = st.columns(3)
    k1.metric("NASA HRP hazards", "5", help="NASA groups human-spaceflight hazards into five broad categories.")
    k2.metric("Research lens", "Health + performance")
    k3.metric("Live external feeds", "Not connected")

    st.markdown("### The five hazards of human spaceflight")
    st.caption("NASA's Human Research Program identifies these interacting hazards as important considerations for journeys to the Moon and Mars.")
    hazard_cards = [
        ("☢️", "Space radiation", "Radiation exposure is a major spaceflight hazard. ASTRA includes an illustrative radiation input so users can explore why units, time interval and mission context matter."),
        ("🧑‍🚀", "Isolation & confinement", "Long periods in a confined environment can affect behaviour and team dynamics. ASTRA's check-in concept can support discussion of crew wellbeing, but does not assess mental health."),
        ("📡", "Distance from Earth", "As missions travel farther away, receiving instructions, supplies and medical support becomes more difficult. This is a mission-context consideration, not a sensor value in ASTRA."),
        ("🪐", "Gravity fields", "The body must adapt to different gravity environments. Cardiovascular, balance, bone and muscle changes are research areas; ASTRA does not model these physiological mechanisms."),
        ("🌡️", "Hostile / closed environments", "Spacecraft habitability involves temperature, pressure, lighting, noise, microbes and immune response. ASTRA's cabin controls are simplified simulated environmental inputs."),
    ]
    for start in range(0, len(hazard_cards), 2):
        cols = st.columns(2)
        for col, item in zip(cols, hazard_cards[start:start + 2]):
            with col:
                st.markdown(
                    f"<div class='section-card' style='min-height:142px;'><div style='font-size:1.35rem;'>{item[0]}</div>"
                    f"<h4 style='margin:6px 0;color:#f2f7ff;'>{item[1]}</h4>"
                    f"<div class='muted' style='font-size:.92rem;'>{item[2]}</div></div>",
                    unsafe_allow_html=True
                )

    st.markdown("### What researchers are investigating")
    tab1, tab2, tab3 = st.tabs(["Physiology", "Crew & performance", "Research examples"])
    with tab1:
        st.markdown("""
        - **Cardiovascular adaptation:** weightlessness changes circulation and how the heart and blood vessels function.
        - **Immune-system responses:** spaceflight stressors can affect immune responses.
        - **Sensorimotor and vestibular function:** gravity transitions can be associated with motion sickness, dizziness and coordination challenges.
        - **Bone and muscle changes:** research investigates ways to preserve strength and fitness during missions.
        - **Radiation-related health risks:** NASA identifies radiation-induced cancer risk as an area requiring mitigation research.
        """)
    with tab2:
        st.markdown("""
        - **Behavioural health:** isolation and other mission stressors can affect crew wellbeing.
        - **Teamwork:** prolonged confinement makes communication and effective collaboration important.
        - **Sleep and schedules:** sleep loss, demanding workloads and irregular biological timing are ongoing research concerns.
        - **Operational support:** future crews may need to solve unexpected problems with limited real-time support from Earth.
        """)
    with tab3:
        st.markdown("""
        - **ARCHeR (Artemis II):** monitored astronaut wellbeing, activity and sleep patterns to learn about health and performance in deep space.
        - **Artemis II Standard Measures:** gathered a consistent set of crew health information for future research.
        - **CIPHER:** a suite of studies examining how the human body changes while orbiting Earth.
        - **Omics Archive:** collects biological samples to study how long-duration spaceflight influences health at the molecular level.
        - **Tempus Pro:** explores collection and integration of health data using a commercial telemedicine device.
        """)

    st.markdown("### Radiation monitoring spotlight")
    left, right = st.columns([1.15, 1])
    with left:
        st.markdown("""
        <div class="section-card">
          <div class="eyebrow">CANADIAN SPACE AGENCY / CANS</div>
          <h3 style="margin:8px 0;">Canadian Active Neutron Spectrometer</h3>
          <p class="muted">The Canadian Space Agency describes CANS as a compact, autonomous instrument being developed to measure neutron radiation exposure in space. Its intended continuous, autonomous operation is relevant to the challenge of understanding astronaut radiation exposure.</p>
          <div class="pill">Radiation research</div><div class="pill">ISS technology context</div>
        </div>
        """, unsafe_allow_html=True)
        st.write("The CSA article reports that neutron radiation contributes about 30% of total radiation on the ISS. That figure is presented here as a statement from the cited CSA article, not as a measurement made by ASTRA.")
    with right:
        st.markdown("""
        <div class="section-card">
          <h4 style="color:#f2f7ff;margin-top:0;">Measurement matters</h4>
          <p class="muted">Radiation count rate, absorbed dose and equivalent dose are not interchangeable. A meaningful record needs the quantity, unit, instrument, timestamp and measurement interval.</p>
          <hr style="border-color:#23445f;">
          <h4 style="color:#f2f7ff;">ASTRA implementation</h4>
          <p class="muted">The current radiation slider is an illustrative scenario input only. It is not calibrated to CANS, does not calculate dose, and is not connected to an ISS instrument.</p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("### How this research informs ASTRA")
    mapping = [
        ("Sleep & fatigue check-ins", "NASA research on sleep, schedules and crew performance", "Conceptual alignment; ASTRA uses manually entered / synthetic values."),
        ("Heart-rate and health fields", "NASA research on cardiovascular adaptation and standard measures", "Prototype fields only; no clinical interpretation or validated risk model."),
        ("Cabin environment controls", "NASA's closed-environment and habitability hazard", "Simulated CO₂, pressure, temperature and related controls."),
        ("Radiation scenario input", "NASA space-radiation hazard + CSA CANS monitoring context", "Illustrative input only; no CANS data, radiation dose calculation or live feed."),
    ]
    for label, src, limitation in mapping:
        with st.expander(label):
            st.write("**Research connection:**", src)
            st.write("**Current prototype boundary:**", limitation)

    st.markdown("### Source library")
    sources = [
        ("NASA · Five Hazards of Human Spaceflight", "NASA Human Research Program overview of space radiation, isolation and confinement, distance from Earth, gravity fields, and hostile/closed environments.", "https://www.nasa.gov/hrp/hazards/", "NASA research overview"),
        ("NASA · Risks of Human Spaceflight", "Identifies physiological, behavioural-performance and radiation-related risks, including cardiovascular adaptation, sleep and teamwork.", "https://www.nasa.gov/hrp/risks/", "NASA risk framework"),
        ("NASA · Ongoing HRP Research", "Examples of ongoing and past investigations, including ARCHeR, Standard Measures, CIPHER, Omics Archive and Tempus Pro.", "https://www.nasa.gov/hrp/ongoing-hrp-research/", "NASA research portfolio"),
        ("Canadian Space Agency · Monitoring radiation for astronaut health", "Describes development of the Canadian Active Neutron Spectrometer (CANS) and its intended autonomous neutron-radiation monitoring role.", "https://www.asc-csa.gc.ca/eng/news/articles/2026/2026-02-26-monitoring-radiation-astronaut-health.asp", "CSA technology article · 26 Feb 2026"),
        ("Canadian Space Agency · Why conduct science experiments in space?", "Explains how ISS research supports preparation for deep-space missions and can produce knowledge useful on Earth.", "https://www.asc-csa.gc.ca/eng/iss/science/why-do-we-conduct-science-experiments-in-space.asp", "CSA research explainer"),
    ]
    search_term = st.text_input("Search the source library", placeholder="Try: radiation, sleep, CANS, research…")
    for title, summary, url, kind in sources:
        if search_term.strip() and search_term.casefold() not in (title + " " + summary + " " + kind).casefold():
            continue
        st.markdown(
            f"<div class='section-card'><div class='eyebrow'>{kind}</div>"
            f"<h4 style='margin:6px 0;color:#f2f7ff;'>{title}</h4>"
            f"<div class='muted' style='font-size:.92rem;margin-bottom:10px;'>{summary}</div>"
            f"<a href='{url}' target='_blank' rel='noopener noreferrer' style='color:#61d9d0;font-weight:700;text-decoration:none;'>Open official source ↗</a></div>",
            unsafe_allow_html=True
        )

    st.markdown("### Scientific integrity & data provenance")
    st.warning("ASTRA is an educational simulation prototype. The health and environmental values shown elsewhere in the app are synthetic or manually entered demonstration inputs. The references above inform the research context; they are not imported datasets. No live NASA or Canadian Space Agency feed is connected.")
    st.caption("Use the original agency pages for full context. Research summaries in this tab are concise paraphrases; agency sources remain authoritative.")

elif page == "Data Export":
    st.subheader("Saved data & export")
    logs = load_health_logs()
    if not logs.empty:
        st.markdown("### Persistent health check-ins (SQLite)")
        st.dataframe(logs, use_container_width=True, hide_index=True)
        st.download_button("Download all health logs (CSV)", logs.to_csv(index=False), "astra_all_health_logs.csv", "text/csv", type="primary")
        st.download_button("Download all health logs (JSON)", logs.to_json(orient="records", date_format="iso", indent=2), "astra_all_health_logs.json", "application/json")
    else:
        st.info("No health check-ins saved in the database yet.")

    with db_connect() as conn:
        sims = pd.read_sql_query("SELECT * FROM simulation_logs ORDER BY id DESC", conn)
    st.markdown("### Persistent simulation snapshots (SQLite)")
    if not sims.empty:
        st.dataframe(sims, use_container_width=True, hide_index=True)
        st.download_button("Download simulation snapshots (CSV)", sims.to_csv(index=False), "astra_simulation_logs.csv", "text/csv")
    else:
        st.info("No simulation snapshots saved in the database yet.")

    snaps = st.session_state.snapshots
    if snaps:
        st.markdown("### Current session snapshots")
        df_snaps = pd.json_normalize(snaps)
        st.dataframe(df_snaps, use_container_width=True)
        st.download_button("Download session snapshots (JSON)", json.dumps(snaps, indent=2), "astra_session_snapshots.json", "application/json")

    st.markdown("#### Data handling notes")
    st.write("- Exported values are demonstration inputs, not real astronaut health records.")
    st.write("- The SQLite database is stored beside `app.py`. Some cloud hosts may reset local files; use an external managed database for guaranteed long-term storage across redeployments/restarts.")
    st.write("- Never put real sensitive health data, passwords, API keys or access tokens into a public repository.")

st.markdown("---")
st.caption("ASTRA prototype • Educational competition project • Illustrative rules only • Not for clinical or flight use")
