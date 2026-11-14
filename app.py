import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timezone
import json

st.set_page_config(
    page_title="ASTRA | Astronaut Health & Mission Simulation",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------- Visual theme ----------
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

def evaluate_demo_rules(v):
    alerts = []
    # These are clearly labelled prototype rules, not medical thresholds.
    if v["spo2"] < 90:
        alerts.append(("HIGH", "Oxygen saturation is below the prototype threshold. Verify the input and escalate according to approved mission procedures."))
    if v["heart_rate"] < 50 or v["heart_rate"] > 120:
        alerts.append(("REVIEW", "Heart-rate value is outside the prototype review range. Check signal quality and context."))
    if v["respiration"] < 8 or v["respiration"] > 25:
        alerts.append(("REVIEW", "Respiration value is outside the prototype review range. Verify the reading."))
    if v["fatigue"] >= 8:
        alerts.append(("REVIEW", "High self-reported fatigue. Review workload, sleep and crew check-in procedures."))
    if v["sleep"] < 6:
        alerts.append(("REVIEW", "Reported sleep is below the prototype review value. Review the schedule and recovery opportunity."))
    if v["co2"] > 5000:
        alerts.append(("HIGH", "CO₂ exceeds the illustrative prototype threshold. Check the simulated sensor and follow approved environmental procedures."))
    if v["cabin_pressure"] < 70 or v["cabin_pressure"] > 110:
        alerts.append(("HIGH", "Cabin pressure is outside this scenario's illustrative range. Validate units and consult approved procedures."))
    if v["radiation"] > 2:
        alerts.append(("REVIEW", "Radiation-rate input exceeds the illustrative scenario value. Check units, cumulative exposure and mission-specific limits."))
    return alerts

def status_label(alerts):
    if any(level == "HIGH" for level, _ in alerts):
        return "ATTENTION REQUIRED"
    if alerts:
        return "REVIEW INPUTS"
    return "NO DEMO RULES TRIGGERED"

# ---------- Sidebar ----------
st.sidebar.markdown("## 🛰️ ASTRA")
st.sidebar.caption("Astronaut Status • Telemetry • Risk Assessment")
st.sidebar.markdown("---")
page = st.sidebar.radio(
    "MISSION CONSOLE",
    ["Overview", "Health Monitor", "Environment", "Simulation Lab", "Mission Library", "Knowledge Base", "Data Export"],
)
st.sidebar.markdown("---")
mission = st.sidebar.selectbox("Mission scenario", ["Earth Orbit", "Lunar Mission", "Mars Transit"])
astronaut = st.sidebar.selectbox("Crew member", ["Crew Member A", "Crew Member B", "Crew Member C"])
mode = st.sidebar.selectbox("Data source", ["Simulated data", "Manual demonstration inputs"])
st.sidebar.info("DEMO MODE — not connected to real sensors or medical systems.")

# ---------- Session defaults ----------
defaults = {
    "heart_rate": 76, "spo2": 98, "respiration": 16, "skin_temp": 36.7,
    "systolic": 118, "diastolic": 78, "fatigue": 3, "sleep": 7.5,
    "water": 2.0, "exercise": 30, "calories": 2200, "mood": 7,
    "co2": 1000, "oxygen": 20.9, "cabin_pressure": 101.3,
    "temperature": 22.0, "humidity": 45, "particles": 5.0,
    "radiation": 0.5, "simulation_minutes": 0, "snapshots": [],
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# Scenario preset changes happen explicitly from Simulation Lab buttons.
def current_values():
    return {
        "heart_rate": float(st.session_state.heart_rate),
        "spo2": float(st.session_state.spo2),
        "respiration": float(st.session_state.respiration),
        "fatigue": float(st.session_state.fatigue),
        "sleep": float(st.session_state.sleep),
        "co2": float(st.session_state.co2),
        "cabin_pressure": float(st.session_state.cabin_pressure),
        "radiation": float(st.session_state.radiation),
    }

vals = current_values()
alerts = evaluate_demo_rules(vals)
status = status_label(alerts)

# ---------- Header ----------
st.markdown(f"""
<div class="hero">
  <div class="eyebrow">MISSION CONTROL / HUMAN SYSTEMS</div>
  <h1 style="margin-bottom:4px;">ASTRA <span style="color:#61d9d0;">//</span> Crew Health Console</h1>
  <div class="muted">Astronaut health trends • cabin telemetry • scenario simulation</div>
  <br>
  <span class="pill">{mission.upper()}</span>
  <span class="pill">{astronaut.upper()}</span>
  <span class="pill">{"SIMULATED" if mode == "Simulated data" else "MANUAL INPUTS"}</span>
  <div class="muted" style="margin-top:12px;font-size:0.8rem;">Last interface refresh: {utc_now()}</div>
</div>
""", unsafe_allow_html=True)

if page == "Overview":
    st.subheader("Mission overview")
    st.caption("A decision-support prototype using demonstration values. All status rules are illustrative.")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Heart rate", f"{st.session_state.heart_rate} bpm")
    m2.metric("SpO₂", f"{st.session_state.spo2}%")
    m3.metric("Cabin CO₂", f"{st.session_state.co2:,.0f} ppm")
    m4.metric("Fatigue", f"{st.session_state.fatigue}/10")
    if any(level == "HIGH" for level, _ in alerts):
        st.error("SYSTEM FLAG: one or more prototype rules require attention.")
    elif alerts:
        st.warning("SYSTEM FLAG: review one or more prototype inputs.")
    else:
        st.success("No prototype alert rules triggered. This does not establish that a person is medically safe.")
    left, right = st.columns([1.4, 1])
    with left:
        st.markdown("### Telemetry trend preview")
        hist = create_demo_history(st.session_state.heart_rate, st.session_state.spo2, st.session_state.fatigue, st.session_state.co2)
        metric = st.selectbox("Trend to view", ["Heart rate (bpm)", "SpO₂ (%)", "Fatigue (1–10)", "CO₂ (ppm)"])
        st.line_chart(hist.set_index("Time")[[metric]], height=280)
        st.caption("Synthetic history for visual demonstration; not historical sensor measurements.")
    with right:
        st.markdown("### Current alert queue")
        if alerts:
            for level, msg in alerts:
                if level == "HIGH":
                    st.error(f"**{level}** · {msg}")
                else:
                    st.warning(f"**{level}** · {msg}")
        else:
            st.info("No prototype rules triggered.")
        st.markdown("### Data quality")
        st.write("Source:", mode)
        st.write("Timestamp:", utc_now())
        st.write("Mission time:", f"{st.session_state.simulation_minutes} simulated minutes")

elif page == "Health Monitor":
    st.subheader("Crew health monitor")
    st.caption("Adjust values to explore the prototype. Inputs are illustrative and are not medical advice.")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### Vital signs")
        st.slider("Heart rate (bpm)", 30, 180, key="heart_rate")
        st.slider("Oxygen saturation — SpO₂ (%)", 70, 100, key="spo2")
        st.slider("Respiration (breaths/min)", 4, 40, key="respiration")
        st.slider("Skin temperature (°C)", 30.0, 42.0, key="skin_temp", step=0.1)
        st.slider("Systolic blood pressure (mmHg)", 70, 200, key="systolic")
        st.slider("Diastolic blood pressure (mmHg)", 40, 130, key="diastolic")
    with c2:
        st.markdown("#### Crew daily check-in")
        st.slider("Fatigue (1–10)", 1, 10, key="fatigue")
        st.slider("Sleep in last 24 hours (hours)", 0.0, 12.0, key="sleep", step=0.5)
        st.slider("Mood (1–10)", 1, 10, key="mood")
        st.number_input("Water intake (litres)", 0.0, 10.0, key="water", step=0.25)
        st.number_input("Exercise duration (minutes)", 0, 300, key="exercise", step=5)
        st.number_input("Estimated calorie intake (kcal)", 0, 10000, key="calories", step=100)
    st.markdown("#### Derived review flags")
    health_alerts = evaluate_demo_rules(current_values())
    if health_alerts:
        for level, msg in health_alerts:
            (st.error if level == "HIGH" else st.warning)(f"**{level}** · {msg}")
    else:
        st.success("No prototype rules triggered. Not a medical clearance.")
    if st.button("Record health snapshot", type="primary"):
        snap = {
            "timestamp_utc": utc_now(), "mission": mission, "crew": astronaut,
            "heart_rate_bpm": st.session_state.heart_rate,
            "spo2_percent": st.session_state.spo2,
            "respiration_bpm": st.session_state.respiration,
            "skin_temp_c": st.session_state.skin_temp,
            "blood_pressure_systolic_mmhg": st.session_state.systolic,
            "blood_pressure_diastolic_mmhg": st.session_state.diastolic,
            "fatigue_1_10": st.session_state.fatigue,
            "sleep_hours": st.session_state.sleep,
            "mood_1_10": st.session_state.mood,
            "water_litres": st.session_state.water,
            "exercise_minutes": st.session_state.exercise,
            "calorie_intake_kcal": st.session_state.calories,
            "alerts": [msg for _, msg in health_alerts],
        }
        st.session_state.snapshots.append(snap)
        st.success("Snapshot added to this session's export queue.")

elif page == "Environment":
    st.subheader("Cabin & environmental telemetry")
    st.caption("Use the controls to simulate changing spacecraft conditions.")
    a, b, c = st.columns(3)
    with a:
        st.slider("Carbon dioxide (ppm)", 0, 20000, key="co2", step=100)
        st.slider("Oxygen concentration (%)", 0.0, 30.0, key="oxygen", step=0.1)
    with b:
        st.slider("Cabin pressure (kPa)", 0.0, 150.0, key="cabin_pressure", step=0.5)
        st.slider("Cabin temperature (°C)", -20.0, 50.0, key="temperature", step=0.5)
    with c:
        st.slider("Relative humidity (%)", 0, 100, key="humidity")
        st.slider("Particle concentration (demo units)", 0.0, 500.0, key="particles", step=1.0)
    st.slider("Radiation rate (illustrative units/hour)", 0.0, 10.0, key="radiation", step=0.1)
    st.markdown("#### Environmental review flags")
    env_alerts = []
    if st.session_state.co2 > 5000:
        env_alerts.append(("HIGH", "CO₂ exceeds the illustrative prototype threshold."))
    if not 70 <= st.session_state.cabin_pressure <= 110:
        env_alerts.append(("HIGH", "Cabin pressure is outside the illustrative scenario range."))
    if st.session_state.radiation > 2:
        env_alerts.append(("REVIEW", "Review radiation units, dose-rate context and mission-specific limits."))
    if st.session_state.oxygen < 18 or st.session_state.oxygen > 25:
        env_alerts.append(("REVIEW", "Oxygen value is outside the illustrative review range."))
    if env_alerts:
        for level, msg in env_alerts:
            (st.error if level == "HIGH" else st.warning)(f"**{level}** · {msg}")
    else:
        st.success("No environmental prototype rules triggered.")
    st.caption("Actual cabin limits depend on the vehicle, sensor, mission and approved procedures. These demo values are not operational limits.")

elif page == "Simulation Lab":
    st.subheader("Simulation laboratory")
    st.caption("Change the scenario and inspect how the prototype's rules respond. This is a rule-based demonstration, not a physiological model.")
    st.markdown("#### Quick scenarios")
    q1, q2, q3, q4 = st.columns(4)
    if q1.button("Nominal demo"):
        for k, v in {"heart_rate": 76, "spo2": 98, "respiration": 16, "fatigue": 3, "sleep": 7.5, "co2": 1000, "cabin_pressure": 101.3, "radiation": 0.5}.items():
            st.session_state[k] = v
        st.rerun()
    if q2.button("High CO₂"):
        st.session_state.co2 = 6500
        st.rerun()
    if q3.button("Low sleep / fatigue"):
        st.session_state.sleep = 4.0
        st.session_state.fatigue = 9
        st.rerun()
    if q4.button("Combined review"):
        for k, v in {"heart_rate": 132, "spo2": 94, "respiration": 27, "fatigue": 8, "sleep": 4.5, "co2": 6200, "cabin_pressure": 101.3, "radiation": 2.5}.items():
            st.session_state[k] = v
        st.rerun()
    st.markdown("#### Simulation controls")
    st.slider("Advance mission time (minutes)", 0, 1440, key="simulation_minutes", step=15)
    st.write(f"Selected mission: **{mission}** · Simulated time offset: **{st.session_state.simulation_minutes} minutes**")
    sim_vals = current_values()
    sim_alerts = evaluate_demo_rules(sim_vals)
    st.markdown("#### Simulation response")
    if sim_alerts:
        for level, msg in sim_alerts:
            (st.error if level == "HIGH" else st.warning)(f"**{level}** · {msg}")
    else:
        st.success("No prototype rules triggered under current settings.")
    st.markdown("#### Scenario state")
    st.json({
        "mission": mission,
        "crew": astronaut,
        "simulated_minutes": st.session_state.simulation_minutes,
        "inputs": sim_vals,
        "prototype_status": status_label(sim_alerts),
        "warning": "Illustrative simulation only; no validated physiological or mission model."
    })
    if st.button("Save simulation snapshot", type="primary"):
        st.session_state.snapshots.append({
            "timestamp_utc": utc_now(), "mission": mission, "crew": astronaut,
            "simulation_minutes": st.session_state.simulation_minutes,
            "inputs": sim_vals, "status": status_label(sim_alerts),
            "alerts": [msg for _, msg in sim_alerts]
        })
        st.success("Simulation snapshot added to this session's export queue.")

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
    selected = st.selectbox("Explore mission", list(mission_cards.keys()), index=list(mission_cards.keys()).index(mission))
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
    # Research library: source-derived context, not a live NASA/CSA data feed.
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
        for col, item in zip(cols, hazard_cards[start:start+2]):
            with col:
                st.markdown(f"<div class='section-card' style='min-height:142px;'><div style='font-size:1.35rem;'>{item[0]}</div><h4 style='margin:6px 0;color:#f2f7ff;'>{item[1]}</h4><div class='muted' style='font-size:.92rem;'>{item[2]}</div></div>", unsafe_allow_html=True)

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
    for label, source, limitation in mapping:
        with st.expander(label):
            st.write("**Research connection:**", source)
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
        st.markdown(f"<div class='section-card'><div class='eyebrow'>{kind}</div><h4 style='margin:6px 0;color:#f2f7ff;'>{title}</h4><div class='muted' style='font-size:.92rem;margin-bottom:10px;'>{summary}</div><a href='{url}' target='_blank' rel='noopener noreferrer' style='color:#61d9d0;font-weight:700;text-decoration:none;'>Open official source ↗</a></div>", unsafe_allow_html=True)

    st.markdown("### Scientific integrity & data provenance")
    st.warning("ASTRA is an educational simulation prototype. The health and environmental values shown elsewhere in the app are synthetic or manually entered demonstration inputs. The references above inform the research context; they are not imported datasets. No live NASA or Canadian Space Agency feed is connected.")
    st.caption("Use the original agency pages for full context. Research summaries in this tab are concise paraphrases; agency sources remain authoritative.")

elif page == "Data Export":
    st.subheader("Session data & export")
    st.caption("Snapshots are held in the current app session. This prototype does not yet use a permanent database.")
    snaps = st.session_state.snapshots
    if snaps:
        st.write(f"Snapshots recorded in this session: **{len(snaps)}**")
        df = pd.json_normalize(snaps)
        st.dataframe(df, use_container_width=True)
        st.download_button(
            "Download snapshots as JSON",
            data=json.dumps(snaps, indent=2),
            file_name="astra_session_snapshots.json",
            mime="application/json",
            type="primary",
        )
        st.download_button(
            "Download snapshots as CSV",
            data=df.to_csv(index=False),
            file_name="astra_session_snapshots.csv",
            mime="text/csv",
        )
    else:
        st.info("No snapshots recorded yet. Record a health snapshot or save a simulation snapshot first.")
    st.markdown("#### Data handling notes")
    st.write("- Exported values are demonstration inputs, not real astronaut health records.")
    st.write("- A production version needs persistent storage, access controls, audit logs, and a privacy plan.")
    st.write("- Never put real sensitive health data, passwords, API keys or access tokens into a public repository.")

st.markdown("---")
st.caption("ASTRA prototype • Educational competition project • Demonstration-only rules • Not for clinical or flight use")
