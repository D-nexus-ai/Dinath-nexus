import json
import sqlite3
from datetime import datetime, date, time, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="ASTRA | Astronaut Health & Mission Simulation", page_icon="🛰️", layout="wide", initial_sidebar_state="expanded")
DB_PATH = Path(__file__).with_name("astra_records.db")

st.markdown("""
<style>
.stApp { background:#07111f; color:#edf4ff; }
[data-testid="stSidebar"] { background:#0b1a2c; }
[data-testid="stMetric"] { background:linear-gradient(135deg,#10263b,#0c1b2d); border:1px solid #23425c; padding:14px 16px; border-radius:14px; }
.hero { padding:22px 24px; border:1px solid #23445f; border-radius:18px; background:linear-gradient(115deg,#102a42 0%,#102039 55%,#142044 100%); margin-bottom:18px; }
.eyebrow { color:#61d9d0; font-size:.8rem; letter-spacing:.16em; font-weight:700; }
.muted { color:#9db3ca; }
h1,h2,h3 { color:#f2f7ff; }
</style>
""", unsafe_allow_html=True)

# ---- Persistent storage (survives browser refreshes and Streamlit reruns on the same filesystem) ----
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

def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

init_db()

DEFAULTS = {
    "heart_rate":76, "spo2":98, "respiration":16, "skin_temp":36.7,
    "systolic":118, "diastolic":78, "fatigue":3, "sleep":7.5,
    "water":2.0, "exercise":30, "exercise_type":"Mixed / not specified", "calories":2200, "mood":7,
    "co2":1000, "oxygen":20.9, "cabin_pressure":101.3, "temperature":22.0,
    "humidity":45, "particles":5.0, "radiation":0.5, "simulation_minutes":0,
}
for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value

MISSIONS = ["Earth Orbit", "Lunar Mission", "Mars Transit"]
CREW = ["Crew Member A", "Crew Member B", "Crew Member C"]
page = st.sidebar.radio("MISSION CONSOLE", ["Overview", "Health Monitor", "Environment", "Simulation Lab", "Crew Logs & Records", "Mission Library", "Knowledge Base", "Data Export"])
st.sidebar.markdown("## 🛰️ ASTRA")
st.sidebar.caption("Astronaut Status • Telemetry • Risk Assessment")
mission = st.sidebar.selectbox("Mission scenario", MISSIONS)
crew = st.sidebar.selectbox("Crew member / record", CREW)
mode = st.sidebar.selectbox("Data source", ["Simulated data", "Manual demonstration inputs"])
st.sidebar.info("DEMO MODE — not connected to real sensors or medical systems.")
st.sidebar.caption("Record persistence depends on the host's filesystem. For durable production hosting, configure an external database.")

# All alerts are evaluated from one shared current state and shown consistently on all pages.
def current_values():
    return {k: float(st.session_state[k]) for k in ["heart_rate", "spo2", "respiration", "skin_temp", "systolic", "diastolic", "fatigue", "sleep", "mood", "water", "exercise", "calories", "co2", "oxygen", "cabin_pressure", "temperature", "humidity", "particles", "radiation"]}

def evaluate_rules(v):
    a=[]
    def add(level, key, msg): a.append((level,key,msg))
    if v["spo2"] < 90: add("HIGH","SpO₂","Oxygen saturation is below the illustrative review threshold; verify the input and follow approved procedures.")
    if v["heart_rate"] < 50 or v["heart_rate"] > 120: add("REVIEW","Heart rate","Heart-rate value is outside the illustrative review range; verify signal and context.")
    if v["respiration"] < 8 or v["respiration"] > 25: add("REVIEW","Respiration","Respiration is outside the illustrative review range.")
    if v["skin_temp"] < 33 or v["skin_temp"] > 38: add("REVIEW","Skin temperature","Skin temperature is outside the illustrative review range; check sensor placement and units.")
    if v["systolic"] < 90 or v["systolic"] > 140 or v["diastolic"] < 60 or v["diastolic"] > 90: add("REVIEW","Blood pressure","Blood pressure is outside the illustrative review range. Check the measurement and context.")
    if v["systolic"] <= v["diastolic"]: add("REVIEW","Blood pressure data quality","Systolic pressure should normally exceed diastolic pressure; verify the entered values.")
    if v["fatigue"] >= 8: add("REVIEW","Fatigue","High self-reported fatigue; review workload and crew check-in procedures.")
    if v["sleep"] < 6: add("REVIEW","Sleep","Reported sleep is below the illustrative review value.")
    if v["mood"] <= 3: add("REVIEW","Mood","Low self-reported mood score; consider a private crew wellbeing check-in.")
    if v["co2"] > 5000: add("HIGH","CO₂","CO₂ exceeds the illustrative prototype threshold.")
    if v["oxygen"] < 18 or v["oxygen"] > 25: add("HIGH","Oxygen concentration","Oxygen concentration is outside the illustrative review range; verify units and scenario assumptions.")
    if v["cabin_pressure"] < 70 or v["cabin_pressure"] > 110: add("HIGH","Cabin pressure","Cabin pressure is outside the illustrative scenario range.")
    if v["temperature"] < 18 or v["temperature"] > 28: add("REVIEW","Cabin temperature","Cabin temperature is outside the illustrative comfort-review range.")
    if v["humidity"] < 20 or v["humidity"] > 70: add("REVIEW","Relative humidity","Humidity is outside the illustrative review range.")
    if v["particles"] > 50: add("REVIEW","Particles","Particle concentration exceeds the illustrative review value; confirm sensor units and baseline.")
    if v["radiation"] > 2: add("REVIEW","Radiation","Review radiation units, dose-rate context and mission-specific limits.")
    return a

def render_alerts(alerts):
    if not alerts:
        st.success("No illustrative prototype rules triggered. This is not medical or flight clearance.")
        return
    for level, key, msg in alerts:
        (st.error if level == "HIGH" else st.warning)(f"**{level} · {key}:** {msg}")

def status_label(alerts):
    if any(x[0]=="HIGH" for x in alerts): return "ATTENTION REQUIRED"
    if alerts: return "REVIEW INPUTS"
    return "NO DEMO RULES TRIGGERED"

def values_to_db(v):
    return (v["heart_rate"],v["spo2"],v["respiration"],v["skin_temp"],v["systolic"],v["diastolic"],v["fatigue"],v["mood"],v["sleep"],v["water"],v["exercise"],st.session_state.exercise_type,v["calories"],v["co2"],v["oxygen"],v["cabin_pressure"],v["temperature"],v["humidity"],v["particles"],v["radiation"])

vals=current_values(); alerts=evaluate_rules(vals)
st.markdown(f"""<div class="hero"><div class="eyebrow">MISSION CONTROL / HUMAN SYSTEMS</div><h1 style="margin-bottom:4px;">ASTRA <span style="color:#61d9d0;">//</span> Crew Health Console</h1><div class="muted">Astronaut health trends • cabin telemetry • scenario simulation</div><br><span>{mission.upper()} &nbsp; | &nbsp; {crew.upper()} &nbsp; | &nbsp; {mode.upper()}</span><div class="muted" style="margin-top:12px;font-size:.8rem;">Interface refreshed: {utc_now()}</div></div>""", unsafe_allow_html=True)

if page == "Overview":
    st.subheader("Mission overview")
    st.caption("Illustrative demonstration values only; not medical thresholds or operational guidance.")
    cols=st.columns(4)
    for col,label,value in zip(cols,["Heart rate","SpO₂","Cabin CO₂","Fatigue"],[f"{vals['heart_rate']:.0f} bpm",f"{vals['spo2']:.1f}%",f"{vals['co2']:,.0f} ppm",f"{vals['fatigue']:.0f}/10"]): col.metric(label,value)
    render_alerts(alerts)
    st.markdown("### Current environmental review")
    env_keys=[("oxygen","Oxygen (%)"),("cabin_pressure","Cabin pressure (kPa)"),("temperature","Cabin temperature (°C)"),("humidity","Relative humidity (%)"),("particles","Particles (demo units)"),("radiation","Radiation (illustrative units/hour)")]
    st.dataframe(pd.DataFrame([{"Measurement":label,"Current value":vals[key]} for key,label in env_keys]),use_container_width=True,hide_index=True)
    logs=load_health_logs(crew)
    st.markdown("### Recent saved check-ins")
    st.dataframe(logs.head(5),use_container_width=True,hide_index=True) if not logs.empty else st.info("No saved check-ins for this crew member yet. Add one in Crew Logs & Records.")

elif page == "Health Monitor":
    st.subheader("Crew health monitor")
    st.caption("Controls update shared app state immediately. Flags are illustrative only.")
    c1,c2=st.columns(2)
    with c1:
        st.markdown("#### Vital signs")
        st.slider("Heart rate (bpm)",30,180,key="heart_rate")
        st.slider("Oxygen saturation — SpO₂ (%)",70,100,key="spo2")
        st.slider("Respiration (breaths/min)",4,40,key="respiration")
        st.slider("Skin temperature (°C)",30.0,42.0,key="skin_temp",step=0.1)
        st.slider("Systolic blood pressure (mmHg)",70,200,key="systolic")
        st.slider("Diastolic blood pressure (mmHg)",40,130,key="diastolic")
    with c2:
        st.markdown("#### Crew self-report")
        st.slider("Fatigue (1–10)",1,10,key="fatigue")
        st.slider("Sleep in last 24 hours (hours)",0.0,12.0,key="sleep",step=0.5)
        st.slider("Mood (1–10)",1,10,key="mood")
        st.number_input("Water intake (litres)",0.0,10.0,key="water",step=0.25)
        st.number_input("Exercise duration (minutes)",0,300,key="exercise",step=5)
        st.selectbox("Exercise type",["Mixed / not specified","Resistance","Cardio","Mobility","Rest day","Other"],key="exercise_type")
        st.number_input("Estimated calorie intake (kcal)",0,10000,key="calories",step=100)
    render_alerts(evaluate_rules(current_values()))
    if st.button("Save health snapshot to persistent records",type="primary"):
        v=current_values()
        with db_connect() as conn:
            conn.execute("INSERT INTO health_logs (logged_at,mission,crew,checkin,heart_rate,spo2,respiration,skin_temp,systolic,diastolic,fatigue,mood,sleep_hours,water_litres,exercise_minutes,exercise_type,calories,co2,oxygen,cabin_pressure,temperature,humidity,particles,radiation,notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (utc_now(),mission,crew,"Current snapshot",*values_to_db(v),"Saved from Health Monitor"))
        st.success("Saved to the local database. It should remain after a browser refresh on the same deployment filesystem.")

elif page == "Environment":
    st.subheader("Cabin & environmental telemetry")
    st.caption("Every environmental measurement is evaluated using shared illustrative rules.")
    a,b,c=st.columns(3)
    with a:
        st.slider("Carbon dioxide (ppm)",0,20000,key="co2",step=100)
        st.slider("Oxygen concentration (%)",0.0,30.0,key="oxygen",step=0.1)
    with b:
        st.slider("Cabin pressure (kPa)",0.0,150.0,key="cabin_pressure",step=0.5)
        st.slider("Cabin temperature (°C)",-20.0,50.0,key="temperature",step=0.5)
    with c:
        st.slider("Relative humidity (%)",0,100,key="humidity")
        st.slider("Particle concentration (demo units)",0.0,500.0,key="particles",step=1.0)
    st.slider("Radiation rate (illustrative units/hour)",0.0,10.0,key="radiation",step=0.1)
    render_alerts(evaluate_rules(current_values()))
    st.caption("Actual limits depend on vehicle, sensor, mission and approved procedures. These are not operational thresholds.")

elif page == "Simulation Lab":
    st.subheader("Simulation laboratory")
    st.caption("Edit values here and the shared values, overview and alerts update together. This is a rule-based demo, not a physiological model.")
    q1,q2,q3,q4=st.columns(4)
    if q1.button("Nominal demo"):
        for k,v in {"heart_rate":76,"spo2":98,"respiration":16,"skin_temp":36.7,"systolic":118,"diastolic":78,"fatigue":3,"sleep":7.5,"mood":7,"co2":1000,"oxygen":20.9,"cabin_pressure":101.3,"temperature":22.0,"humidity":45,"particles":5.0,"radiation":0.5}.items(): st.session_state[k]=v
        st.rerun()
    if q2.button("High CO₂ / low O₂"):
        st.session_state.co2=6500; st.session_state.oxygen=16.0; st.rerun()
    if q3.button("Fatigue / low sleep"):
        st.session_state.sleep=4.0; st.session_state.fatigue=9; st.rerun()
    if q4.button("Combined review"):
        for k,v in {"heart_rate":132,"spo2":94,"respiration":27,"skin_temp":38.5,"systolic":150,"diastolic":95,"fatigue":8,"sleep":4.5,"mood":3,"co2":6200,"oxygen":17.0,"cabin_pressure":101.3,"temperature":30.0,"humidity":78,"particles":75.0,"radiation":2.5}.items(): st.session_state[k]=v
        st.rerun()
    st.markdown("#### Editable simulation controls")
    with st.expander("Health and crew inputs",expanded=True):
        x,y,z=st.columns(3)
        with x:
            st.slider("Heart rate (bpm)",30,180,key="heart_rate")
            st.slider("SpO₂ (%)",70,100,key="spo2")
            st.slider("Respiration (breaths/min)",4,40,key="respiration")
            st.slider("Skin temperature (°C)",30.0,42.0,key="skin_temp",step=0.1)
            st.slider("Systolic BP (mmHg)",70,200,key="systolic")
            st.slider("Diastolic BP (mmHg)",40,130,key="diastolic")
        with y:
            st.slider("Fatigue (1–10)",1,10,key="fatigue")
            st.slider("Mood (1–10)",1,10,key="mood")
            st.slider("Sleep (hours)",0.0,12.0,key="sleep",step=0.5)
            st.number_input("Water (litres)",0.0,10.0,key="water",step=0.25)
            st.number_input("Exercise (minutes)",0,300,key="exercise",step=5)
            st.number_input("Calories (kcal)",0,10000,key="calories",step=100)
        with z:
            st.slider("CO₂ (ppm)",0,20000,key="co2",step=100)
            st.slider("Oxygen (%)",0.0,30.0,key="oxygen",step=0.1)
            st.slider("Cabin pressure (kPa)",0.0,150.0,key="cabin_pressure",step=0.5)
            st.slider("Temperature (°C)",-20.0,50.0,key="temperature",step=0.5)
            st.slider("Humidity (%)",0,100,key="humidity")
            st.slider("Particles (demo units)",0.0,500.0,key="particles",step=1.0)
            st.slider("Radiation (illustrative units/hour)",0.0,10.0,key="radiation",step=0.1)
    st.slider("Advance mission time (minutes)",0,1440,key="simulation_minutes",step=15)
    sim_vals=current_values(); sim_alerts=evaluate_rules(sim_vals)
    st.markdown("#### Simulation response")
    render_alerts(sim_alerts)
    st.write("Status:",status_label(sim_alerts))
    st.json({"mission":mission,"crew":crew,"simulated_minutes":st.session_state.simulation_minutes,"inputs":sim_vals,"status":status_label(sim_alerts),"note":"Illustrative only; no validated physiological or mission model."})
    if st.button("Save simulation snapshot",type="primary"):
        with db_connect() as conn:
            conn.execute("INSERT INTO simulation_logs (saved_at,mission,crew,simulated_minutes,inputs_json,status,alerts_json) VALUES (?,?,?,?,?,?,?)",(utc_now(),mission,crew,int(st.session_state.simulation_minutes),json.dumps(sim_vals),status_label(sim_alerts),json.dumps([x[2] for x in sim_alerts])))
        st.success("Simulation snapshot saved to the local database.")

elif page == "Crew Logs & Records":
    st.subheader("Crew check-ins & historical records")
    st.warning("Prototype privacy notice: use fictional/demo data only. Do not enter real sensitive health records into a public demo.")
    st.markdown("### Add a historical or twice-daily check-in")
    st.caption("Use the date and time fields to backfill older records. Check-ins are saved in SQLite, not just browser session state.")
    with st.form("crew_checkin_form",clear_on_submit=False):
        d1,d2=st.columns(2)
        with d1:
            log_date=st.date_input("Check-in date",value=date.today())
            log_time=st.time_input("Check-in time",value=time(8,0))
            checkin=st.selectbox("Check-in slot",["Morning", "Evening", "Additional / historical"])
            hr=st.number_input("Heart rate (bpm)",30.0,180.0,float(st.session_state.heart_rate),1.0)
            spo=st.number_input("SpO₂ (%)",70.0,100.0,float(st.session_state.spo2),0.5)
            resp=st.number_input("Respiration (breaths/min)",4.0,40.0,float(st.session_state.respiration),1.0)
            skin=st.number_input("Skin temperature (°C)",30.0,42.0,float(st.session_state.skin_temp),0.1)
            sys=st.number_input("Systolic BP (mmHg)",50.0,250.0,float(st.session_state.systolic),1.0)
            dia=st.number_input("Diastolic BP (mmHg)",30.0,160.0,float(st.session_state.diastolic),1.0)
        with d2:
            fatigue=st.slider("Fatigue (1–10)",1,10,int(st.session_state.fatigue),key="log_fatigue")
            mood=st.slider("Mood (1–10)",1,10,int(st.session_state.mood),key="log_mood")
            sleep=st.number_input("Sleep in last 24 hours (hours)",0.0,24.0,float(st.session_state.sleep),0.5)
            water=st.number_input("Water intake (litres)",0.0,15.0,float(st.session_state.water),0.25)
            exercise=st.number_input("Exercise duration (minutes)",0.0,600.0,float(st.session_state.exercise),5.0)
            exercise_type=st.selectbox("Exercise type",["Mixed / not specified","Resistance","Cardio","Mobility","Rest day","Other"])
            calories=st.number_input("Calories (kcal)",0.0,15000.0,float(st.session_state.calories),100.0)
            notes=st.text_area("Notes (optional; use demo text only)",max_chars=500)
        st.markdown("#### Environmental readings (optional for this check-in)")
        e1,e2,e3=st.columns(3)
        with e1: co2=st.number_input("CO₂ (ppm)",0.0,50000.0,float(st.session_state.co2),100.0); oxygen=st.number_input("Oxygen (%)",0.0,100.0,float(st.session_state.oxygen),0.1)
        with e2: pressure=st.number_input("Cabin pressure (kPa)",0.0,200.0,float(st.session_state.cabin_pressure),0.5); temperature=st.number_input("Cabin temperature (°C)",-50.0,80.0,float(st.session_state.temperature),0.5)
        with e3: humidity=st.number_input("Humidity (%)",0.0,100.0,float(st.session_state.humidity),1.0); particles=st.number_input("Particles (demo units)",0.0,10000.0,float(st.session_state.particles),1.0); radiation=st.number_input("Radiation (illustrative units/hour)",0.0,1000.0,float(st.session_state.radiation),0.1)
        submitted=st.form_submit_button("Save check-in permanently",type="primary")
    if submitted:
        stamp=f"{log_date.isoformat()} {log_time.strftime('%H:%M:%S')}"
        with db_connect() as conn:
            conn.execute("INSERT INTO health_logs (logged_at,mission,crew,checkin,heart_rate,spo2,respiration,skin_temp,systolic,diastolic,fatigue,mood,sleep_hours,water_litres,exercise_minutes,exercise_type,calories,co2,oxygen,cabin_pressure,temperature,humidity,particles,radiation,notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (stamp,mission,crew,checkin,hr,spo,resp,skin,sys,dia,fatigue,mood,sleep,water,exercise,exercise_type,calories,co2,oxygen,pressure,temperature,humidity,particles,radiation,notes))
        st.success(f"Saved {checkin.lower()} check-in for {crew} on {stamp}.")
    st.markdown("### Saved history")
    logs=load_health_logs(crew)
    if logs.empty: st.info("No saved records for this crew member yet.")
    else:
        st.caption(f"{len(logs)} saved check-in(s) for {crew}.")
        st.dataframe(logs,use_container_width=True,hide_index=True)
        st.download_button("Download this crew member's history (CSV)",logs.to_csv(index=False),file_name=f"astra_{crew.lower().replace(' ','_')}_health_logs.csv",mime="text/csv")
        ids=logs["id"].astype(int).tolist()
        delete_id=st.selectbox("Record ID to delete",ids,key="delete_record_id")
        confirm=st.checkbox("I confirm I want to delete this selected demo record")
        if st.button("Delete selected record",disabled=not confirm):
            with db_connect() as conn: conn.execute("DELETE FROM health_logs WHERE id=? AND crew=?",(int(delete_id),crew))
            st.success("Record deleted."); st.rerun()

elif page == "Mission Library":
    st.subheader("Mission scenario library")
    cards={"Earth Orbit":("Crew routine, exercise, sleep scheduling and cabin environmental trends.","Test nominal values, missing readings and fatigue trends."),"Lunar Mission":("Mission phase changes, surface operations, suit/environment transitions and radiation context.","Compare cabin-mode inputs with a separately documented surface-operation scenario."),"Mars Transit":("Long-duration trend review, sleep and workload patterns, communications constraints and radiation context.","Explore longer timelines and sensor staleness; do not extrapolate this toy model.")}
    selected=st.selectbox("Explore mission",MISSIONS,index=MISSIONS.index(mission)); st.markdown(f"### {selected}"); st.write("**Monitoring focus:**",cards[selected][0]); st.write("**Suggested simulation:**",cards[selected][1])
    st.info("Real mission profiles and thresholds must be sourced and validated for the relevant vehicle and mission.")
    st.markdown("- Which measurements are available in this mission phase?\n- What are the units, calibration needs and data-quality limits?\n- Which approved references define alert criteria?\n- What should happen when data is missing or stale?")

elif page == "Knowledge Base":
    st.subheader("Knowledge base")
    with st.expander("Why monitor multiple data streams?"): st.write("Health readings, self-reported wellbeing and cabin conditions provide different kinds of information. Display timestamps and limitations rather than assuming one reading explains another.")
    with st.expander("Why track trends?"): st.write("Trends can show change over time that a single reading misses. Clearly distinguish saved user-entered records from generated demonstration data.")
    with st.expander("Radiation measurements"): st.write("Count rate, absorbed dose and equivalent dose are different quantities. Record instrument, units and time interval.")
    with st.expander("AI and automation"): st.write("Automated flags should be explainable and validated. They are not diagnoses or replacements for qualified mission medical staff.")
    st.markdown("- [NASA Human Research Program](https://www.nasa.gov/hrp/)\n- [NASA Technical Reports Server](https://ntrs.nasa.gov/)\n- [NASA Space Apps Challenge](https://www.spaceappschallenge.org/)")

elif page == "Data Export":
    st.subheader("Saved data & export")
    logs=load_health_logs()
    if not logs.empty:
        st.markdown("### Health check-ins")
        st.dataframe(logs,use_container_width=True,hide_index=True)
        st.download_button("Download all health logs (CSV)",logs.to_csv(index=False),"astra_all_health_logs.csv","text/csv",type="primary")
        st.download_button("Download all health logs (JSON)",logs.to_json(orient="records",date_format="iso",indent=2),"astra_all_health_logs.json","application/json")
    else: st.info("No health check-ins saved yet.")
    with db_connect() as conn: sims=pd.read_sql_query("SELECT * FROM simulation_logs ORDER BY id DESC",conn)
    st.markdown("### Saved simulation snapshots")
    if not sims.empty:
        st.dataframe(sims,use_container_width=True,hide_index=True)
        st.download_button("Download simulation snapshots (CSV)",sims.to_csv(index=False),"astra_simulation_logs.csv","text/csv")
    else: st.info("No simulation snapshots saved yet.")
    st.caption("The SQLite database is stored beside app.py. Some cloud hosts may reset local files; use an external managed database for guaranteed long-term storage across redeployments/restarts. Use fictional data for this demo.")

st.markdown("---")
st.caption("ASTRA prototype • Educational competition project • Illustrative rules only • Not for clinical or flight use")
