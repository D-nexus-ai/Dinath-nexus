"""mars_mission.py - ASTRA Earth-to-Mars mission replay (mission plug-in).

EDUCATIONAL DEMONSTRATION. ALL DATA ARE SIMULATED AND FICTIONAL. This is NOT a validated
physiological, radiation, or spacecraft-trajectory model and must not be used for real operations.

Mission plug-in interface (see astra_ui.py): LABEL, sync_session(active, visible), render_console(evaluate_rules).
Other public helpers: telemetry(), get_snapshot(i_or_timestamp), snapshot_values(i), apply_snapshot(i, state),
advance(state), render_svg(i).  To add another mission, write a module with the same three plug-in names and
register it in MISSION_SOURCES in app.py.
"""
from __future__ import annotations

import hashlib
import html
import marshal
import math
import textwrap
from functools import lru_cache

import numpy as np
import pandas as pd
import streamlit as st

import astra_ui as ui

LABEL = "Earth → Mars mission"
N, SEED, DAY = 1000, 2026, 86400.0
EPOCH = pd.Timestamp("2026-12-01 14:00:00")          # fictional T0 (UTC)
ASTRA_VARS = ["heart_rate", "spo2", "respiration", "skin_temp", "systolic", "diastolic", "fatigue", "sleep",
              "mood", "water", "exercise", "calories", "co2", "oxygen", "cabin_pressure", "temperature",
              "humidity", "particles", "radiation"]
INT_VARS = {"heart_rate", "spo2", "respiration", "systolic", "diastolic", "fatigue", "mood", "exercise",
            "calories", "co2", "humidity"}               # same types as ASTRA DEFAULTS (others are float)
RANGES = {"heart_rate": (30, 180), "spo2": (70, 100), "respiration": (4, 40), "skin_temp": (30, 42),
          "systolic": (70, 200), "diastolic": (40, 130), "fatigue": (1, 10), "sleep": (0, 12), "mood": (1, 10),
          "water": (0, 10), "exercise": (0, 300), "calories": (0, 10000), "co2": (0, 20000), "oxygen": (0, 30),
          "cabin_pressure": (0, 150), "temperature": (-20, 50), "humidity": (0, 100), "particles": (0, 500),
          "radiation": (0, 10)}                          # = ASTRA slider / number_input bounds
EX_TYPES = ["Mixed / not specified", "Resistance", "Cardio", "Mobility", "Rest day", "Other"]

# ----------------------------------------------------------------------------- orbital mechanics (toy)
R_E, R_M, DTH = 1.0, 1.524, math.radians(150)            # circular orbits (AU); transfer angle 150 deg
ECC = (R_M - R_E) / (R_E - R_M * math.cos(DTH))          # transfer ellipse, perihelion at Earth
A_AU = R_E * (1 + ECC) / (1 - ECC ** 2)
T_ORB = 365.256 * A_AU ** 1.5                            # days
NE, NM, TH0 = 2 * math.pi / 365.256, 2 * math.pi / 686.98, math.radians(105)
T_DEP = 12540.0                                          # TMI cutoff (s MET)


def _t_of_f(f):
    E = 2 * math.atan2(math.sqrt(1 - ECC) * math.sin(f / 2), math.sqrt(1 + ECC) * math.cos(f / 2))
    return (E - ECC * math.sin(E)) / (2 * math.pi) * T_ORB * DAY


T_ARR = T_DEP + _t_of_f(DTH)                             # Mars arrival (s MET), ~201 d transfer
T_MOI_END, T_E = T_ARR + 7200.0, T_ARR + 7200.0 + DAY    # end of MOI; EDL start
T_END = T_E + 900.0
MU_M, R_MARS, AP_KM, PE_KM = 42828.0, 3390.0, 33000.0, 500.0
A_CAP = (2 * R_MARS + AP_KM + PE_KM) / 2
E_CAP = 1 - (R_MARS + PE_KM) / A_CAP
T_CAP = 2 * math.pi * math.sqrt(A_CAP ** 3 / MU_M)
PHASES = [  # name, samples, start MET s, end MET s, routine description
    ("Pre-launch countdown", 50, -10800.0, 0.0, "Countdown: crew strapped in, final checks"),
    ("Liftoff & atmospheric ascent", 60, 0.0, 150.0, "Ascent: full thrust through the atmosphere"),
    ("Stage separation & upper-stage burn", 60, 150.0, 540.0, "Upper stage accelerating to orbital speed"),
    ("Earth parking orbit", 100, 540.0, 11340.0, "Parking orbit: systems checkout, waiting for TMI window"),
    ("Trans-Mars injection burn", 40, 11340.0, T_DEP, "TMI burn: leaving Earth orbit"),
    ("Heliocentric transfer", 440, T_DEP, T_ARR - 5 * DAY, "Cruise: routine crew operations"),
    ("Mars approach", 80, T_ARR - 5 * DAY, T_ARR, "Approach: Mars growing in the forward window"),
    ("Mars orbit insertion", 40, T_ARR, T_MOI_END, "MOI: retro-burn for orbit capture"),
    ("Mars capture orbit", 50, T_MOI_END, T_E, "Capture orbit: preparing for descent"),
    ("Entry, descent & landing", 80, T_E, T_END, "EDL: entry, parachutes, powered descent"),
]
PH_START = np.cumsum([0] + [p[1] for p in PHASES])       # first sample index of each phase
EVENTS = {  # id: (name, onset, peak, hold_end, end, texts: onset/escalating/peak/recovery/resolved)
    "SPE": ("Solar particle event", 380, 386, 395, 480,
            ("SPE ONSET: radiation rising, crew ordered to storm shelter", "SPE: dose rate climbing",
             "SPE PEAK: highest radiation rate of the mission, crew sheltering",
             "SPE: flux declining, crew remains in shelter", "SPE RESOLVED: radiation back to background")),
    "CREW": ("Crew health / wellbeing anomaly", 520, 545, 575, 620,
             ("CREW ANOMALY: sleep disruption and fatigue reported", "Crew wellbeing declining, flight surgeon alerted",
              "CREW ANOMALY PEAK: severe fatigue, low mood, raised blood pressure",
              "Recovery: rest schedule and private conference started", "CREW RECOVERED: vitals back to baseline")),
    "CABIN": ("Cabin environmental anomaly (CO2 scrubber)", 655, 675, 700, 745,
              ("CABIN ANOMALY: CO2 scrubber degradation detected", "CO2 rising, oxygen falling, pressure slowly dropping",
               "CABIN ANOMALY PEAK: CO2 and O2 out of range, crew in masks",
               "Scrubber bed swapped, cabin air recovering", "CABIN RECOVERED: atmosphere nominal")),
}
MILESTONES = [("Terminal count (T-10 min)", -600), ("LIFTOFF", 0), ("Max-Q (peak aerodynamic pressure)", 70),
              ("Stage 1 cutoff & separation", 150), ("Fairing / escape-tower jettison", 200),
              ("SECO: parking-orbit insertion", 540), ("TMI burn start", 11340), ("TMI cutoff: Mars-bound", T_DEP),
              ("Trajectory correction TCM-1", T_DEP + 10 * DAY), ("Trajectory correction TCM-2", T_DEP + 100 * DAY),
              ("Mars approach: TCM-3", T_ARR - 5 * DAY), ("MOI burn start", T_ARR),
              ("MOI cutoff: captured by Mars", T_ARR + 4500), ("De-orbit burn / entry interface (125 km)", T_E),
              ("Peak heating", T_E + 170), ("Parachute deploy", T_E + 300), ("Heat-shield jettison", T_E + 360),
              ("Powered descent start", T_E + 560), ("TOUCHDOWN", T_END)]


def fmt_met(s: float) -> str:
    sign, s = ("T-" if s < 0 else "T+"), int(round(abs(s)))
    d, h, m, sec = s // 86400, s % 86400 // 3600, s % 3600 // 60, s % 60
    return f"{sign}{d}d {h:02d}:{m:02d}:{sec:02d}" if d else f"{sign}{h:02d}:{m:02d}:{sec:02d}"


def _planets(t_s):
    td = np.asarray(t_s, float) / DAY
    th_dep = TH0 + NE * T_DEP / DAY
    return TH0 + NE * td, th_dep + DTH + NM * (td - T_ARR / DAY), th_dep


def _craft(t_s):
    t_s = np.asarray(t_s, float)
    M = 2 * np.pi * np.clip(t_s - T_DEP, 0, T_ARR - T_DEP) / (T_ORB * DAY)
    E = M.copy()
    for _ in range(40):
        E = E - (E - ECC * np.sin(E) - M) / (1 - ECC * np.cos(E))
    f = 2 * np.arctan2(np.sqrt(1 + ECC) * np.sin(E / 2), np.sqrt(1 - ECC) * np.cos(E / 2))
    r = A_AU * (1 - ECC * np.cos(E))
    thE, thM, th_dep = _planets(t_s)
    ex, ey, mx, my = np.cos(thE), np.sin(thE), R_M * np.cos(thM), R_M * np.sin(thM)
    cx, cy = r * np.cos(th_dep + f), r * np.sin(th_dep + f)
    x = np.where(t_s < T_DEP, ex, np.where(t_s > T_ARR, mx, cx))
    y = np.where(t_s < T_DEP, ey, np.where(t_s > T_ARR, my, cy))
    return x, y, ex, ey, mx, my, r


def _ss(x):
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)


def _env(i, on, pk, hold, end):
    i = np.asarray(i, float)
    return np.where(i < pk, _ss((i - on) / (pk - on)), np.where(i <= hold, 1.0, 1 - _ss((i - hold) / (end - hold))))


# ----------------------------------------------------------------------------- telemetry generator
@lru_cache(maxsize=1)
def telemetry() -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    i = np.arange(N)
    met = np.concatenate([np.linspace(p[2], p[3], p[1], endpoint=(k == len(PHASES) - 1)) for k, p in enumerate(PHASES)])
    met = np.round(met, 3)
    pid = np.repeat(np.arange(len(PHASES)), [p[1] for p in PHASES])
    td = met / DAY
    circ = np.sin(2 * np.pi * (td - 0.25))

    def A(pts):
        return np.interp(i, *zip(*pts))

    def noise(sig, phi=0.85):
        e, out = rng.normal(0, sig * math.sqrt(1 - phi ** 2), N), np.empty(N)
        out[0] = rng.normal(0, sig)
        for k in range(1, N):
            out[k] = phi * out[k - 1] + e[k]
        return out

    def spikes(sig, p=0.012, k=3.2):                     # occasional measurement-noise outliers
        return np.where(rng.random(N) < p, rng.choice([-1, 1], N) * sig * k, 0.0)

    stress = A([(0, .1), (40, .3), (49, .45), (50, .7), (78, 1), (109, .85), (140, .6), (169, .4), (200, .2),
                (269, .1), (270, .6), (300, .55), (309, .4), (330, .1), (700, .08), (749, .12), (829, .3),
                (830, .75), (869, .5), (880, .2), (919, .3), (920, .7), (945, .95), (975, 1), (999, .6)])
    ev = {k: _env(i, *v[1:5]) for k, v in EVENTS.items()}
    spe, crew, cab = ev["SPE"], ev["CREW"], ev["CABIN"]

    # --- nominal streams, kept inside the existing alert bands (events push them out) ------------
    hr = np.clip(71 + 42 * stress + 2 * circ + noise(2) + spikes(5), 58, 119)
    spo2 = np.clip(98.3 - 1.8 * stress + noise(.35) + spikes(1.2), 95, 100)
    resp = np.clip(15 + 6 * stress + noise(.5) + spikes(2), 11, 23)
    skin = np.clip(36.6 + .12 * circ + .35 * stress + noise(.07) + spikes(.2), 35.2, 37.6)
    sysb = np.clip(117 + 14 * stress + noise(2) + spikes(8), 100, 134)
    dia = np.clip(77 + 6 * stress + noise(1.5) + spikes(4), 64, 85)
    fat = np.clip(A([(0, 2), (110, 3), (310, 2.5), (450, 3.4), (700, 4), (749, 4.5), (830, 4), (999, 4)])
                  + 1.6 * stress + noise(.25), 1, 6)
    sleep = np.clip(A([(0, 6.5), (170, 6.2), (310, 7), (400, 7.4), (749, 7.2), (830, 6.6), (920, 6.3), (999, 6.2)])
                    + noise(.2), 6.0, 9.0)
    mood = np.clip(A([(0, 7.5), (50, 8.5), (170, 8), (310, 7), (500, 6.2), (749, 6.5), (830, 7.5), (999, 8.5)])
                   + noise(.3), 5, 9)
    water = np.clip(A([(0, 2), (50, 1.6), (170, 2), (310, 2.5), (749, 2.5), (999, 2.2)]) + noise(.12), 1.0, 3.5)
    cal = A([(0, 2300), (50, 1900), (170, 2000), (270, 2400), (310, 2650), (749, 2650), (830, 2450), (999, 2200)]) + noise(60)
    day = np.floor(td).astype(int)
    rest = (day % 7 == 6)
    ex = np.where(pid == 5, np.where(rest, 0, 60 + 15 * np.sin(day * 1.7)),
                  np.where(pid == 6, 30, np.where(pid == 8, 20, 0))).astype(float)
    co2 = np.clip(A([(0, 900), (50, 1100), (170, 1400), (270, 1900), (310, 2300), (749, 2500), (830, 2100),
                     (920, 1700), (999, 1300)]) + 150 * circ + noise(120) + spikes(500), 300, 4200)
    o2 = np.clip(20.9 + noise(.06), 20.5, 21.3)
    pres = np.clip(101.3 - .3 * stress + noise(.15), 100.8, 101.8)
    temp = np.clip(22 + .35 * circ + .6 * stress + noise(.15), 20.5, 24.5)
    hum = np.clip(44 + 3 * circ + 3 * stress + noise(1.2), 34, 58)
    part = np.clip(4.5 + 14 * np.clip(stress - .5, 0, 1) + 30 * _ss((i - 985) / 14) + noise(.4, .8) + spikes(2), 1, 45)
    rad = A([(0, .08), (60, .1), (110, .2), (170, .3), (269, .35), (310, .9), (330, .75), (749, .75), (830, .7),
             (920, .55), (930, .3), (999, .12)]) + 1.3 * np.exp(-((i - 285) / 9) ** 2) \
        + .12 * np.clip(np.sin(2 * np.pi * (met / 5420)), 0, 1) * ((pid == 3) * 1.0) + noise(.03)
    rad = np.clip(rad, .02, 1.95)

    # --- scripted emergencies ----------------------------------------------------------------------
    hr = hr + 4 * spe + 8 * crew + 10 * cab
    spo2 = spo2 - 4.5 * cab
    resp = resp + 1 * spe + 3 * crew + 6 * cab
    skin = skin + .3 * crew + .4 * cab
    sysb = sysb + 4 * spe + 25 * crew + 6 * cab
    dia = dia + 2 * spe + 14 * crew + 3 * cab
    fat = fat * (1 - crew) + 9 * crew + 1 * spe + 3 * cab
    sleep = sleep * (1 - crew) + 4.0 * crew - 1.0 * cab
    mood = mood * (1 - crew) + 2 * crew - 1.5 * spe - 2 * cab
    ex = ex * (1 - np.maximum(np.maximum(spe, crew), cab))
    co2 = co2 + 5200 * cab
    o2 = o2 - 3.6 * cab
    pres = pres - 6.5 * cab
    temp = temp + 2.0 * cab
    hum = hum + 9 * cab
    rad = rad + 7.3 * spe
    water = water - .5 * cab

    df = pd.DataFrame({
        "sample": i, "met_s": met, "met_label": [fmt_met(s) for s in met],
        "phase_id": pid, "phase": [PHASES[k][0] for k in pid],
        "heart_rate": hr, "spo2": spo2, "respiration": resp, "skin_temp": skin, "systolic": sysb, "diastolic": dia,
        "fatigue": fat, "sleep": sleep, "mood": mood, "water": water, "exercise": ex, "calories": cal,
        "co2": co2, "oxygen": o2, "cabin_pressure": pres, "temperature": temp, "humidity": hum,
        "particles": part, "radiation": rad})
    quant = {"sleep": .5, "water": .25}
    for k in ASTRA_VARS:
        v = df[k].to_numpy(float)
        if k in quant:
            v = np.round(v / quant[k]) * quant[k]
        elif k == "exercise":
            v = np.round(v / 5) * 5
        elif k == "calories":
            v = np.round(v / 50) * 50
        elif k in ("oxygen", "cabin_pressure", "temperature", "skin_temp", "particles"):
            v = np.round(v, 1)
        elif k == "radiation":
            v = np.round(v, 2)
        v = np.clip(v, *RANGES[k])
        df[k] = np.rint(v).astype("int64") if k in INT_VARS else v.astype("float64")
    df["exercise_type"] = np.where(df.exercise == 0, np.where(pid == 5, "Rest day", "Mixed / not specified"),
                                   np.array(["Resistance", "Cardio", "Mobility"])[day % 3])

    # --- trajectory / position ---------------------------------------------------------------------
    x, y, ex_, ey_, mx_, my_, r = _craft(met)
    df["pos_x_au"], df["pos_y_au"] = np.round(x, 6), np.round(y, 6)
    d_e, d_m = np.hypot(x - ex_, y - ey_), np.hypot(x - mx_, y - my_)
    df["dist_earth_au"], df["dist_mars_au"] = np.round(d_e, 6), np.round(d_m, 6)
    alt, spd = np.zeros(N), np.zeros(N)
    m = pid == 1; t = met[m]
    alt[m], spd[m] = 65 * (t / 150) ** 2, 2.3 * (t / 150) ** 1.4
    m = pid == 2; s = (met[m] - 150) / 390
    alt[m], spd[m] = 65 + 235 * s ** .8, 2.3 + 5.43 * s ** .9
    m = pid == 3; alt[m], spd[m] = 300, 7.73
    m = pid == 4; s = (met[m] - 11340) / 1200
    a_ = 300 + 11700 * s ** 1.6
    en = -398600 / (2 * 6671) + (4.2 + 398600 / (2 * 6671)) * _ss(s)
    alt[m], spd[m] = a_, np.sqrt(2 * (en + 398600 / (6371 + a_)))
    m = pid == 5
    alt[m] = d_e[m] * 149597870.7 + 12000
    spd[m] = 29.78 * np.sqrt(2 / r[m] - 1 / A_AU)
    m = pid == 6
    alt[m] = d_m[m] * 149597870.7 + PE_KM
    spd[m] = np.sqrt(5.6 ** 2 + 2 * MU_M / (R_MARS + alt[m]))
    m = pid == 7; s = (met[m] - T_ARR) / 7200
    alt[m], spd[m] = PE_KM, 7.3 - 2.84 * _ss((s - .3) / .4)
    m = pid == 8
    Mn = 2 * np.pi * (met[m] - T_MOI_END) / T_CAP; Ea = Mn.copy()
    for _ in range(40):
        Ea = Ea - (Ea - E_CAP * np.sin(Ea) - Mn) / (1 - E_CAP * np.cos(Ea))
    rr = A_CAP * (1 - E_CAP * np.cos(Ea))
    alt[m], spd[m] = rr - R_MARS, np.sqrt(MU_M * (2 / rr - 1 / A_CAP))
    m = pid == 9; t = met[m] - T_E
    ta = [0, 120, 180, 240, 300, 360, 560, 760, 850, 900]
    alt[m] = np.interp(t, ta, [125, 70, 40, 22, 11, 8, 3, 1.2, .15, 0])
    spd[m] = np.interp(t, ta, [4.7, 3.0, 2.2, 1.1, .45, .12, .06, .03, .01, 0])
    df["altitude_km"], df["speed_km_s"] = np.round(alt, 3), np.round(spd, 4)
    df["engine_on"] = ((pid == 1) | (pid == 2) | (pid == 4) | ((pid == 7) & (np.abs((met - T_ARR) / 7200 - .5) < .2))
                       | ((pid == 9) & (met - T_E >= 560) & (alt > 0)))

    # --- event descriptions & markers ---------------------------------------------------------------
    text = np.array([PHASES[k][4] for k in pid], dtype=object)
    emerg, marker = np.array([""] * N, dtype=object), np.zeros(N, bool)
    used = set()
    for name, t_ in MILESTONES:
        j = int(np.argmin(np.abs(met - t_)))
        while j in used:
            j += 1
        used.add(j); text[j] = name.upper() if name in ("LIFTOFF", "TOUCHDOWN") else name; marker[j] = True
    for eid, (name, on, pk, hold, end, tx) in EVENTS.items():
        for j in range(on, end + 1):
            emerg[j] = eid
            text[j] = tx[0] if j == on else tx[1] if j < pk else tx[2] if j == pk else tx[3] if j < end else tx[4]
            if j in (on, pk, hold, end):
                marker[j] = True
    df["event"], df["emergency"], df["marker"] = text, emerg, marker
    df.index = pd.DatetimeIndex(EPOCH + pd.to_timedelta(met, unit="s"), name="timestamp_utc")
    return df


@lru_cache(maxsize=1)
def _records():
    return telemetry().reset_index().assign(timestamp_utc=lambda d: d.timestamp_utc.dt.strftime("%Y-%m-%d %H:%M:%S")
                                            ).to_dict("records")


def _native(rec):
    return {k: (int(v) if k in INT_VARS or k in ("sample", "phase_id") else float(v)) if k in ASTRA_VARS else
            (v.item() if hasattr(v, "item") else v) for k, v in rec.items()}


def get_snapshot(key) -> dict:
    """Complete snapshot (all columns) for a sample index (int) or a timestamp (str / pd.Timestamp)."""
    if isinstance(key, (int, np.integer)):
        i = int(key)
    else:
        i = int(np.argmin(np.abs((telemetry().index - pd.Timestamp(key)).to_numpy())))
    return _native(dict(_records()[min(max(i, 0), N - 1)]))


def snapshot_values(i) -> dict:
    s = get_snapshot(i)
    return {k: float(s[k]) for k in ASTRA_VARS}


def apply_snapshot(i, state=None):
    """Copy snapshot i into the matching ASTRA session_state variables (same names, units, types)."""
    state = st.session_state if state is None else state
    s = get_snapshot(i)
    for k in ASTRA_VARS:
        state[k] = s[k]
    state["exercise_type"] = s["exercise_type"]
    state["mm_applied"] = int(i)
    return s


# ----------------------------------------------------------------------------- playback state
SPEEDS = [0.5, 1, 2, 4, 8, 16, 32]
TICK = 0.4                                                # seconds between animation frames
PAUSE_OPTIONS = ["Off", "HIGH hazards", "Any hazard"]
PAUSE_RANK = {"Off": 9, "HIGH hazards": 2, "Any hazard": 1}
TREND_WINDOWS = {"Last 60 samples": 60, "Last 250 samples": 250, "Full mission": None}


def init_state(ss=None):
    ss = st.session_state if ss is None else ss
    for k, v in {"mm_idx": 0, "mm_slider": 0, "mm_playing": False, "mm_speed": 4, "mm_acc": 0.0, "mm_pause_on": "HIGH hazards",
                 "mm_notified": 0, "mm_ack": [], "mm_trend": "heart_rate", "mm_window": "Full mission",
                 "mm_alert_sig": None, "mm_alerts": None, "mm_eps": None}.items():
        if k not in ss:
            ss[k] = v


def advance(ss):
    """One playback tick. ONE index (mm_idx) drives the animation, the slider, telemetry and ASTRA variables."""
    if ss["mm_playing"]:
        ss["mm_acc"] += float(ss["mm_speed"])
        n = int(ss["mm_acc"]); ss["mm_acc"] -= n
        ss["mm_idx"] = min(N - 1, int(ss["mm_idx"]) + n)
        if ss["mm_idx"] >= N - 1:
            ss["mm_playing"] = False
    ss["mm_slider"] = int(ss["mm_idx"])


def ensure_alerts(evaluate_rules, ss=None):
    """Evaluate ASTRA's own rules on every sample once (re-done only if the rule function itself changes)."""
    ss = st.session_state if ss is None else ss
    init_state(ss)
    sig = hashlib.md5(marshal.dumps(evaluate_rules.__code__)).hexdigest()
    if ss["mm_alert_sig"] != sig:
        ss["mm_alerts"] = [evaluate_rules(snapshot_values(i)) for i in range(N)]
        ss["mm_eps"] = ui.build_episodes(ss["mm_alerts"])
        ss["mm_alert_sig"] = sig


def notify(ss, i):
    """Hazards that began between the last evaluated sample and i (forward movement only); moves the marker."""
    new = ui.new_since(ss["mm_eps"], ss["mm_notified"], i)
    ss["mm_notified"] = i
    return new


def tick(ss):
    """One playback step: advance, detect hazards that just began, auto-pause if requested. Returns the new hazards."""
    was = ss["mm_playing"]
    advance(ss)
    new = notify(ss, int(ss["mm_idx"]))
    if new and was and ss["mm_playing"] and any(ui.LEVEL_RANK[e["level"]] >= PAUSE_RANK[ss["mm_pause_on"]] for e in new):
        ss["mm_playing"] = False
    return new


def _cb_toggle():
    ss = st.session_state
    if not ss.mm_playing and ss.mm_idx >= N - 1:
        ss.mm_idx, ss.mm_acc, ss.mm_slider, ss.mm_notified = 0, 0.0, 0, 0
    ss.mm_playing = not ss.mm_playing


def _cb_reset():
    ss = st.session_state
    ss.mm_idx = ss.mm_slider = ss.mm_notified = 0; ss.mm_acc = 0.0; ss.mm_playing = False; ss.mm_ack = []


def _cb_slider():
    st.session_state.mm_idx = int(st.session_state.mm_slider)


def _cb_jump(i):
    ss = st.session_state
    ss.mm_idx = ss.mm_slider = int(i); ss.mm_playing = False


def _cb_ack():
    ss = st.session_state
    ss.mm_ack = sorted(set(ss.mm_ack) | {e["id"] for e in ui.active_at(ss.mm_eps, int(ss.mm_idx))})


def sync_session(active, visible=True):
    """Plug-in hook, called by app.py on every run BEFORE current_values()."""
    init_state()
    ss = st.session_state
    if not (active and visible):
        ss.mm_playing = False                              # replay never runs in the background
    if active:
        apply_snapshot(ss.mm_idx)                          # re-applied every run: Streamlit drops widget keys of hidden pages


# ----------------------------------------------------------------------------- SVG rendering
LX, LY, LW, LH, CX, GY = 610, 20, 550, 420, 885, 400
_r = np.random.default_rng(7)
STARS = [(float(_r.uniform(0, LW)), float(_r.uniform(0, LH)), float(_r.choice([.6, .9, 1.3]))) for _ in range(90)]
DEFS = """<defs>
<radialGradient id="sun"><stop offset="0" stop-color="#fff7c2"/><stop offset=".5" stop-color="#ffb62e"/><stop offset="1" stop-color="#ff7a00" stop-opacity="0"/></radialGradient>
<radialGradient id="earth" cx=".35" cy=".35"><stop offset="0" stop-color="#6fc3ff"/><stop offset=".6" stop-color="#1f6fc4"/><stop offset="1" stop-color="#0a2c5c"/></radialGradient>
<radialGradient id="mars" cx=".35" cy=".35"><stop offset="0" stop-color="#f0a068"/><stop offset=".6" stop-color="#c0602f"/><stop offset="1" stop-color="#5a2412"/></radialGradient>
<linearGradient id="fl" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff6d0"/><stop offset=".35" stop-color="#ffb347"/><stop offset="1" stop-color="#ff4d1a" stop-opacity="0"/></linearGradient>
<linearGradient id="smoke" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".55"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
<filter id="glow" x="-80%" y="-80%" width="260%" height="260%"><feGaussianBlur stdDeviation="2.5"/></filter>
<clipPath id="lc"><rect x="610" y="20" width="550" height="420" rx="14"/></clipPath></defs>"""


def _lerp(a, b, t):
    t = min(max(t, 0), 1)
    A, B = [int(a[k:k + 2], 16) for k in (1, 3, 5)], [int(b[k:k + 2], 16) for k in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(x + (y - x) * t) for x, y in zip(A, B))


def _tx(x, y, s, size=13, fill="#cfe3ff", anchor="start", w=400):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" text-anchor="{anchor}" '
            f'font-weight="{w}" font-family="Segoe UI,Helvetica,Arial,sans-serif">{html.escape(str(s))}</text>')


def _flame(x, y, L, w):
    return (f'<path d="M{x - w:.1f},{y:.1f} Q{x:.1f},{y + L * 1.3:.1f} {x + w:.1f},{y:.1f}Z" fill="url(#fl)" filter="url(#glow)"/>'
            f'<path d="M{x - w * .5:.1f},{y:.1f} Q{x:.1f},{y + L * .8:.1f} {x + w * .5:.1f},{y:.1f}Z" fill="#fff6d0"/>')


_UPPER = ('<rect x="-8" y="-32" width="16" height="32" fill="#cfd8e6"/><path d="M-8,-32Q0,-62 8,-32Z" fill="#f2f6fb"/>'
          '<rect x="-8" y="-14" width="16" height="3" fill="#d94b4b"/><rect x="-6" y="0" width="12" height="3" fill="#4a5262"/>')
_BOOST = ('<path d="M-9,-8L-18,6L-9,-24Z M9,-8L18,6L9,-24Z" fill="#7d8aa0"/><rect x="-9" y="-72" width="18" height="72" '
          'fill="#eef3fa"/><rect x="-9" y="-34" width="18" height="5" fill="#27303f"/><rect x="-7" y="0" width="14" height="4" fill="#4a5262"/>')


def _rocket(x, y, s, fl=0.0, booster=True, ang=0.0):
    g = f'<g transform="translate({x:.1f},{y:.1f}) rotate({ang:.1f}) scale({s:.2f})">'
    if fl:
        g += _flame(0, 2, fl, 8 if booster else 5)
    return g + (_BOOST + f'<g transform="translate(0,-72)">{_UPPER}</g>' if booster else _UPPER) + "</g>"


def _stars(o, off=0.0, a=1.0):
    o.append(f'<g fill="#fff" opacity="{a:.2f}">' + "".join(
        f'<circle cx="{LX + (sx - off) % LW:.1f}" cy="{LY + sy:.1f}" r="{sr}"/>' for sx, sy, sr in STARS) + "</g>")


def _mars(o, x, y, rad):
    o.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rad:.1f}" fill="url(#mars)"/>')
    o.append(f'<g opacity=".4" fill="#4a1f10"><ellipse cx="{x + .15 * rad:.1f}" cy="{y + .1 * rad:.1f}" rx="{.28 * rad:.1f}" ry="{.16 * rad:.1f}"/>'
             f'<ellipse cx="{x - .35 * rad:.1f}" cy="{y - .15 * rad:.1f}" rx="{.2 * rad:.1f}" ry="{.12 * rad:.1f}"/>'
             f'<ellipse cx="{x + .1 * rad:.1f}" cy="{y + .5 * rad:.1f}" rx="{.3 * rad:.1f}" ry="{.1 * rad:.1f}"/></g>')
    o.append(f'<ellipse cx="{x:.1f}" cy="{y - .93 * rad:.1f}" rx="{.28 * rad:.1f}" ry="{.07 * rad:.1f}" fill="#fff" opacity=".85"/>')


def _ship(x, y, ang, k=1.0, burn=0.0, spin=0.0):
    g = f'<g transform="translate({x:.1f},{y:.1f}) rotate({ang:.1f}) scale({k:.2f})">'
    if burn:
        g += f'<g transform="rotate(90)">{_flame(0, 34, 38 * burn, 9)}</g>'
    g += ('<rect x="-60" y="-3" width="130" height="6" fill="#8190a6"/><rect x="-100" y="-12" width="40" height="24" rx="4" fill="#b9c3d3"/>'
          '<path d="M-100,-8L-114,-14L-114,14L-100,8Z" fill="#5d6a80"/><rect x="10" y="-15" width="72" height="30" rx="14" fill="#e3e9f3"/>'
          '<rect x="-44" y="-70" width="24" height="60" fill="#1f4b99" stroke="#8fb3ff"/><rect x="-44" y="10" width="24" height="60" fill="#1f4b99" stroke="#8fb3ff"/>'
          '<ellipse cx="46" cy="0" rx="9" ry="42" fill="none" stroke="#dfe7f2" stroke-width="2.5"/>')
    c, s_ = math.cos(spin), math.sin(spin)
    g += f'<line x1="46" y1="0" x2="{46 + 9 * c:.1f}" y2="{42 * s_:.1f}" stroke="#dfe7f2" stroke-width="2"/>'
    g += f'<line x1="46" y1="0" x2="{46 - 9 * c:.1f}" y2="{-42 * s_:.1f}" stroke="#dfe7f2" stroke-width="2"/>'
    return g + '<circle cx="76" cy="0" r="3" fill="#61d9d0"/></g>'


def _local(o, r, i):
    """Phase-specific close-up scene (right-hand panel)."""
    pid, met, alt = r["phase_id"], r["met_s"], r["altitude_km"]
    fl = .8 + .4 * (((i * 37) % 11) / 11)
    emg = r["emergency"]
    if pid == 0:
        o.append(f'<linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#0b1a35"/><stop offset="1" stop-color="#46618f"/></linearGradient>'
                 f'<rect x="{LX}" y="{LY}" width="{LW}" height="{LH}" fill="url(#sky)"/>')
        _stars(o, 0, .5)
        o.append(f'<rect x="{LX}" y="{GY}" width="{LW}" height="40" fill="#14241b"/><rect x="{CX - 70}" y="{GY - 6}" width="140" height="8" fill="#6a7384"/>'
                 f'<rect x="{CX + 52}" y="{GY - 240}" width="14" height="240" fill="#59647a"/><path d="M{CX + 52},{GY - 240}L{CX + 66},{GY - 200}M{CX + 66},{GY - 240}L{CX + 52},{GY - 200}'
                 f'M{CX + 52},{GY - 160}L{CX + 66},{GY - 120}M{CX + 66},{GY - 160}L{CX + 52},{GY - 120}" stroke="#8a95aa"/>'
                 f'<rect x="{CX + 10}" y="{GY - 175}" width="45" height="5" fill="#8a95aa"/>')
        o.append(_rocket(CX, GY - 6, 2.0))
        puffs = max(0, min(1, (met + 900) / 900))
        o.append("".join(f'<circle cx="{CX + (k - 2) * 26}" cy="{GY - 6 - (k % 2) * 8}" r="{10 + 7 * puffs + 3 * ((i + k) % 3)}" fill="#fff" opacity="{.18 * puffs:.2f}"/>' for k in range(5)))
        o.append(_tx(LX + 22, LY + 40, r["met_label"], 30, "#ffd479", w=700))
        o.append(_tx(LX + 22, LY + 62, "COUNTDOWN · launch pad (illustrative)", 12, "#9db3ca"))
    elif pid in (1, 2):
        t = min(max(alt / 80, 0), 1)
        o.append(f'<linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{_lerp("#1e6fd0", "#000308", t * 1.3)}"/>'
                 f'<stop offset="1" stop-color="{_lerp("#bfe3ff", "#06122a", t * 1.3)}"/></linearGradient>'
                 f'<rect x="{LX}" y="{LY}" width="{LW}" height="{LH}" fill="url(#sky)"/>')
        _stars(o, 0, max(0, (t - .3) / .7))
        by = GY - 70 * min(1, alt / 30) if pid == 1 else GY - 70
        gy = GY + 12 * alt if pid == 1 else 0
        if pid == 1 and gy < LY + LH:
            o.append(f'<rect x="{LX}" y="{gy:.1f}" width="{LW}" height="{LY + LH - gy:.1f}" fill="#14241b"/>')
        if pid == 2:
            top = 372 + .12 * (alt - 65)
            o.append(f'<circle cx="{CX}" cy="{top + 1400:.1f}" r="1400" fill="#0c3a78"/><circle cx="{CX}" cy="{top + 1400:.1f}" r="1404" fill="none" stroke="#6fc3ff" stroke-width="6" opacity=".55"/>')
            dt = met - 150
            if dt < 140:
                o.append(f'<g opacity="{max(0, 1 - dt / 140):.2f}"><g transform="translate({CX - dt * .6:.1f},{by + 40 + dt * 3.2 + .02 * dt * dt:.1f}) rotate({-dt * .9:.1f})">'
                         f'<g transform="scale(1.6)">{_BOOST}</g></g></g>')
            if 50 <= met - 150 < 110:
                d2 = met - 150 - 50
                o.append(f'<path d="M{CX - 10 - d2 * .7:.1f},{by - 110 - d2 * .2:.1f}l-7,-22l9,3Z M{CX + 10 + d2 * .7:.1f},{by - 110 - d2 * .2:.1f}l7,-22l-9,3Z" fill="#dfe7f2"/>')
        if pid == 1:
            o.append(f'<rect x="{CX - 9}" y="{by:.1f}" width="18" height="{LY + LH - by:.1f}" fill="url(#smoke)"/>')
            if abs(met - 70) < 9:
                o.append(f'<ellipse cx="{CX}" cy="{by - 150:.1f}" rx="46" ry="13" fill="none" stroke="#fff" opacity=".7"/>' + _tx(CX + 60, by - 150, "MAX-Q", 14, "#ffd479", w=700))
        o.append(_rocket(CX, by, 1.6, 40 * fl, booster=(pid == 1)) if pid == 1 else _rocket(CX, by - 20, 1.7, 40 * fl, booster=False))
    elif pid == 3:
        o.append(f'<rect x="{LX}" y="{LY}" width="{LW}" height="{LH}" fill="#02050d"/>')
        _stars(o)
        ex_, ey_ = CX, 235
        o.append(f'<circle cx="{ex_}" cy="{ey_}" r="112" fill="url(#earth)"/><circle cx="{ex_}" cy="{ey_}" r="116" fill="none" stroke="#6fc3ff" opacity=".35" stroke-width="5"/>'
                 f'<ellipse cx="{ex_ - 30}" cy="{ey_ - 20}" rx="38" ry="22" fill="#3e8f4e" opacity=".7"/><ellipse cx="{ex_ + 40}" cy="{ey_ + 40}" rx="30" ry="18" fill="#3e8f4e" opacity=".6"/>'
                 f'<circle cx="{ex_}" cy="{ey_}" r="155" fill="none" stroke="#61d9d0" stroke-dasharray="5 6" opacity=".7"/>')
        a = 2 * math.pi * (met - 540) / 5420 - math.pi / 2
        o.append(f'<g transform="translate({ex_ + 155 * math.cos(a):.1f},{ey_ + 155 * math.sin(a):.1f}) rotate({math.degrees(a) + 180:.1f})">'
                 f'<rect x="-10" y="-5" width="20" height="10" fill="#e3e9f3"/><rect x="-4" y="-22" width="8" height="44" fill="#1f4b99"/></g>')
        o.append(_tx(LX + 20, LY + 34, "LEO parking orbit ~300 km (not to scale)", 14, "#61d9d0", w=600))
    elif pid == 4:
        o.append(f'<rect x="{LX}" y="{LY}" width="{LW}" height="{LH}" fill="#02050d"/>')
        _stars(o)
        ex_, ey_, p = CX - 110, 245, (met - 11340) / 1200

        def path(q):
            ph = -math.pi / 2 + q * 1.55
            rr = 135 + 330 * q ** 2
            return ex_ + rr * math.cos(ph), ey_ + rr * math.sin(ph)
        o.append(f'<circle cx="{ex_}" cy="{ey_}" r="100" fill="url(#earth)"/><circle cx="{ex_}" cy="{ey_}" r="135" fill="none" stroke="#61d9d0" stroke-dasharray="4 6" opacity=".5"/>')
        pts = [path(q) for q in np.linspace(0, 1, 40)]
        o.append('<polyline fill="none" stroke="#2a5a6a" stroke-dasharray="3 5" points="' + " ".join(f"{x:.1f},{y:.1f}" for x, y in pts) + '"/>')
        k = max(2, int(p * 39) + 1)
        o.append('<polyline fill="none" stroke="#61d9d0" stroke-width="2.5" points="' + " ".join(f"{x:.1f},{y:.1f}" for x, y in pts[:k]) + '"/>')
        x1, y1 = path(p); x0, y0 = path(max(0, p - .03))
        ang = math.degrees(math.atan2(y1 - y0, x1 - x0))
        o.append(f'<g transform="translate({x1:.1f},{y1:.1f}) rotate({ang:.1f})"><g transform="rotate(90) translate(0,-8)">{_flame(0, 0, 40 * fl, 6)}</g>'
                 '<rect x="-14" y="-6" width="26" height="12" fill="#e3e9f3"/><rect x="-6" y="-24" width="9" height="48" fill="#1f4b99"/></g>')
        o.append(_tx(LX + 20, LY + 34, "TMI burn: Earth orbit → escape trajectory to Mars", 14, "#ffb454", w=600))
        o.append(_tx(LX + LW - 20, LY + LH - 20, "to Mars →", 14, "#ff9d66", "end", 700))
    elif pid == 5:
        o.append(f'<rect x="{LX}" y="{LY}" width="{LW}" height="{LH}" fill="#02050d"/>')
        _stars(o, i * 3.0)
        if emg == "SPE":
            al = min(1, (r["radiation"] - .8) / 6)
            o.append(f'<g stroke="#ffb454" stroke-width="2" opacity="{al:.2f}">' + "".join(
                f'<line x1="{LX + (k * 53 + i * 41) % LW:.1f}" y1="{LY + (k * 71) % LH:.1f}" x2="{LX + (k * 53 + i * 41) % LW + 34:.1f}" y2="{LY + (k * 71) % LH + 12:.1f}"/>' for k in range(26)) + '</g>')
            o.append(_tx(LX + 20, LY + 34, "SOLAR PARTICLE EVENT: crew in shelter", 15, "#ffb454", w=700))
        o.append(_ship(CX, 230, 0, 1.25, spin=i * .15))
        if emg == "CABIN":
            on = (i // 2) % 2 == 0
            o.append(f'<rect x="{CX - 20}" y="{200}" width="170" height="60" rx="26" fill="none" stroke="#ff5d6c" stroke-width="3" opacity="{1 if on else .3}"/>'
                     + _tx(LX + 20, LY + 34, "CABIN ALARM: CO2 high / O2 low", 15, "#ff5d6c", w=700))
        if emg == "CREW":
            o.append(_tx(LX + 20, LY + 34, "CREW WELLBEING ANOMALY: flight surgeon review", 15, "#ffb454", w=700))
        de, dm = r["dist_earth_au"] * 149.5978707, r["dist_mars_au"] * 149.5978707
        o.append(_tx(LX + 20, LY + LH - 46, f"Earth  {de:,.1f} million km", 14, "#7fb8ff") + _tx(LX + 20, LY + LH - 24, f"Mars   {dm:,.1f} million km", 14, "#ff9d66")
                 + _tx(LX + LW - 20, LY + LH - 24, "Heliocentric cruise (coasting)", 13, "#9db3ca", "end"))
    elif pid == 6:
        o.append(f'<rect x="{LX}" y="{LY}" width="{LW}" height="{LH}" fill="#02050d"/>')
        _stars(o, i * 2.0)
        rad = 14 + 215 * min(1, max(0, (6.4 - math.log10(alt + 1)) / 3.7)) ** 1.3 if alt > 1 else 230
        _mars(o, CX + 120, 225, rad)
        o.append(_ship(LX + 120, 330, -12, .8))
        o.append(_tx(LX + 20, LY + 34, f"Mars approach · range {alt:,.0f} km", 14, "#ff9d66", w=600))
    elif pid == 7:
        o.append(f'<rect x="{LX}" y="{LY}" width="{LW}" height="{LH}" fill="#02050d"/>')
        _stars(o, 0)
        mx_, my_, p = CX - 40, 235, (met - T_ARR) / 7200

        def path(q):
            rr = 135 + 115 * (1 - _ss(q / .4)) + 70 * _ss((q - .7) / .3)
            ph = math.radians(-155 + 190 * q)
            return mx_ + rr * math.cos(ph), my_ + rr * math.sin(ph)
        _mars(o, mx_, my_, 85)
        pts = [path(q) for q in np.linspace(0, 1, 50)]
        o.append('<polyline fill="none" stroke="#2a5a6a" stroke-dasharray="3 5" points="' + " ".join(f"{x:.1f},{y:.1f}" for x, y in pts) + '"/>')
        k = max(2, int(p * 49) + 1)
        o.append('<polyline fill="none" stroke="#61d9d0" stroke-width="2.5" points="' + " ".join(f"{x:.1f},{y:.1f}" for x, y in pts[:k]) + '"/>')
        x1, y1 = path(p); x0, y0 = path(max(0, p - .03))
        ang = math.degrees(math.atan2(y1 - y0, x1 - x0))
        o.append(_ship(x1, y1, ang, .35, burn=fl if r["engine_on"] else 0, spin=i * .2))
        o.append(_tx(LX + 20, LY + 34, "MOI retro-burn: hyperbolic approach → capture", 14, "#ffb454", w=600))
    elif pid == 8:
        o.append(f'<rect x="{LX}" y="{LY}" width="{LW}" height="{LH}" fill="#02050d"/>')
        _stars(o)
        a_px = 190.0; sc = a_px / A_CAP; fx = 985.0; b_px = a_px * math.sqrt(1 - E_CAP ** 2); cxo = fx - a_px * E_CAP
        o.append(f'<ellipse cx="{cxo:.1f}" cy="235" rx="{a_px}" ry="{b_px:.1f}" fill="none" stroke="#61d9d0" stroke-dasharray="5 6" opacity=".7"/>')
        _mars(o, fx, 235, R_MARS * sc)
        Mn = 2 * math.pi * (met - T_MOI_END) / T_CAP; Ea = Mn
        for _ in range(40):
            Ea -= (Ea - E_CAP * math.sin(Ea) - Mn) / (1 - E_CAP * math.cos(Ea))
        sx, sy = fx + a_px * (math.cos(Ea) - E_CAP), 235 - b_px * math.sin(Ea)
        o.append(f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="6" fill="#fff" stroke="#61d9d0" stroke-width="2"/>')
        o.append(_tx(LX + 20, LY + 34, "1-sol capture orbit 500 × 33,000 km (to scale)", 14, "#61d9d0", w=600))
        o.append(_tx(LX + 20, LY + LH - 24, f"altitude {alt:,.0f} km · {r['speed_km_s']:.2f} km/s", 13, "#9db3ca"))
    else:
        u = min(1, math.log10(1 + alt * 8) / math.log10(1 + 125 * 8))
        o.append(f'<linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{_lerp("#c9885a", "#02050d", u)}"/><stop offset="1" stop-color="{_lerp("#e8b184", "#2a1008", u)}"/></linearGradient>'
                 f'<rect x="{LX}" y="{LY}" width="{LW}" height="{LH}" fill="url(#sky)"/>')
        _stars(o, 0, u * .9)
        o.append(f'<circle cx="{CX}" cy="{GY + 1500 + 25 * u:.1f}" r="1500" fill="#8a3c1f"/><ellipse cx="{CX - 120}" cy="{GY + 18}" rx="90" ry="8" fill="#6a2a14"/>')
        t = met - T_E; y = 60 + (GY - 20 - 60) * (1 - u); x = CX + 50 * (1 - u) * math.sin(t / 90)
        if 90 <= t < 300 and alt > 25:
            o.append(f'<ellipse cx="{x:.1f}" cy="{y + 26:.1f}" rx="26" ry="{30 + 6 * fl:.1f}" fill="#ffb347" opacity=".75" filter="url(#glow)"/>')
        if 300 <= t < 560:
            o.append(f'<path d="M{x - 55:.1f},{y - 120:.1f}Q{x:.1f},{y - 175:.1f} {x + 55:.1f},{y - 120:.1f}Z" fill="#f4f0e8"/><path d="M{x - 55:.1f},{y - 120:.1f}L{x - 8:.1f},{y - 28:.1f}M{x + 55:.1f},{y - 120:.1f}L{x + 8:.1f},{y - 28:.1f}" stroke="#d8d2c6"/>')
        if t >= 560 and t < 900:
            o.append(f'<path d="M{x - 55 + (t - 560) * .6:.1f},{y - 140 - (t - 560) * .5:.1f}Q{x + (t - 560) * .6:.1f},{y - 195 - (t - 560) * .5:.1f} {x + 55 + (t - 560) * .6:.1f},{y - 140 - (t - 560) * .5:.1f}Z" fill="#f4f0e8" opacity=".6"/>')
            if r["engine_on"]:
                o.append(_flame(x - 12, y + 6, 36 * fl, 5) + _flame(x + 12, y + 6, 36 * fl, 5))
        o.append(f'<g transform="translate({x:.1f},{y:.1f})"><path d="M-10,-30L10,-30L18,0L-18,0Z" fill="#cfd6e4"/>'
                 + ('' if t >= 360 else '<path d="M-18,0Q0,14 18,0Z" fill="#3a3f4a"/>')
                 + ('<path d="M-12,0L-20,12M12,0L20,12" stroke="#8a95aa" stroke-width="3"/>' if t >= 760 else '') + '</g>')
        if t >= 360 and t < 470:
            o.append(f'<path d="M{x - 14:.1f},{y + 20 + (t - 360) * 2:.1f}Q{x:.1f},{y + 34 + (t - 360) * 2:.1f} {x + 14:.1f},{y + 20 + (t - 360) * 2:.1f}Z" fill="#3a3f4a"/>')
        if alt < .2:
            o.append(f'<ellipse cx="{x:.1f}" cy="{GY - 4}" rx="{60 + 80 * (1 - alt / .2):.0f}" ry="14" fill="#d9a073" opacity=".55"/>')
        o.append(_tx(LX + 20, LY + 34, f"EDL · altitude {alt:,.2f} km · {r['speed_km_s'] * 1000:,.0f} m/s", 14, "#fff", w=700))


def render_svg(i: int) -> str:
    """Full animation frame for timestamp index i (same record that feeds telemetry and alerts)."""
    i = int(min(max(i, 0), N - 1)); r = _records()[i]
    met = r["met_s"]
    S, HX, HY = 170.0, 300.0, 300.0
    o = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1180 650" width="1180" height="650">', DEFS,
         '<rect width="1180" height="650" fill="#050b16"/>',
         '<rect x="20" y="20" width="560" height="560" rx="14" fill="#06101f" stroke="#23445f"/>',
         f'<rect x="{LX}" y="{LY}" width="{LW}" height="{LH}" rx="14" fill="#07111f" stroke="#23445f"/>']
    _stars_h = "".join(f'<circle cx="{20 + sx}" cy="{20 + sy * 1.3:.0f}" r="{sr * .8}"/>' for sx, sy, sr in STARS)
    o.append(f'<g fill="#fff" opacity=".35">{_stars_h}</g>')
    # heliocentric map
    o.append(f'<circle cx="{HX}" cy="{HY}" r="{S * R_E}" fill="none" stroke="#2c5d8a" stroke-dasharray="3 5"/>'
             f'<circle cx="{HX}" cy="{HY}" r="{S * R_M}" fill="none" stroke="#8a4a2c" stroke-dasharray="3 5"/>')
    ts = np.linspace(T_DEP, T_ARR, 200)
    ax, ay = _craft(ts)[:2]
    pts = [(HX + S * x, HY - S * y) for x, y in zip(ax, ay)]
    o.append('<polyline fill="none" stroke="#3a6a78" stroke-dasharray="4 5" points="' + " ".join(f"{x:.1f},{y:.1f}" for x, y in pts) + '"/>')
    k = int((ts <= met).sum())
    if k > 1:
        o.append('<polyline fill="none" stroke="#61d9d0" stroke-width="3" points="' + " ".join(f"{x:.1f},{y:.1f}" for x, y in pts[:k]) + '"/>')
    o.append(f'<circle cx="{HX}" cy="{HY}" r="34" fill="url(#sun)"/><circle cx="{HX}" cy="{HY}" r="11" fill="#ffd45a"/>' + _tx(HX, HY + 30, "Sun", 12, "#ffd45a", "middle"))
    thE, thM, _ = _planets(met)
    px_e, py_e = HX + S * math.cos(thE), HY - S * math.sin(thE)
    px_m, py_m = HX + S * R_M * math.cos(thM), HY - S * R_M * math.sin(thM)
    o.append(f'<circle cx="{px_e:.1f}" cy="{py_e:.1f}" r="8" fill="url(#earth)"/>' + _tx(px_e + 12, py_e - 8, "Earth", 13, "#7fb8ff", w=600))
    o.append(f'<circle cx="{px_m:.1f}" cy="{py_m:.1f}" r="6.5" fill="url(#mars)"/>' + _tx(px_m + 11, py_m - 8, "Mars", 13, "#ff9d66", w=600))
    dx, dy = HX + S * math.cos(TH0 + NE * T_DEP / DAY), HY - S * math.sin(TH0 + NE * T_DEP / DAY)
    o.append(_tx(dx + 10, dy + 18, "TMI", 11, "#9db3ca") + _tx(pts[-1][0] + 10, pts[-1][1] + 16, "MOI", 11, "#9db3ca"))
    sx, sy = HX + S * r["pos_x_au"], HY - S * r["pos_y_au"]
    if r["emergency"] == "SPE":
        o.append(f'<line x1="{HX}" y1="{HY}" x2="{sx:.1f}" y2="{sy:.1f}" stroke="#ffb454" stroke-dasharray="2 4" opacity=".7"/>')
    col = {"SPE": "#ffb454", "CREW": "#ffb454", "CABIN": "#ff5d6c"}.get(r["emergency"], "#61d9d0")
    o.append(f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="{9 + (i % 4)}" fill="none" stroke="{col}" opacity=".8"/><circle cx="{sx:.1f}" cy="{sy:.1f}" r="4" fill="#fff"/>'
             + _tx(sx + 12, sy + 20, "ASTRA-1 crew" + (f" · {r['emergency']}" if r["emergency"] else ""), 12, col, w=700))
    o.append(_tx(36, 46, "HELIOCENTRIC VIEW (ecliptic, toy two-body model)", 12, "#9db3ca", w=600) + _tx(564, 566, "circle radii: 1.0 / 1.524 AU", 11, "#6d86a3", "end"))
    # local scene
    o.append('<g clip-path="url(#lc)">'); _local(o, r, i); o.append("</g>")
    # read-outs
    alarm = r["emergency"] != ""
    o.append(_tx(LX, 470, r["phase"], 22, "#61d9d0", w=700) + _tx(LX + LW, 470, "ENGINE " + ("BURN" if r["engine_on"] else "OFF"), 14, "#ff7a45" if r["engine_on"] else "#6d86a3", "end", 700))
    o.append(_tx(LX, 498, f"MET {r['met_label']}   ·   {r['timestamp_utc']} UTC   ·   sample {i + 1}/{N}", 13, "#cfe3ff"))
    lt = r["dist_earth_au"] * 8.317
    o.append(_tx(LX, 522, f"alt {r['altitude_km']:,.0f} km   ·   speed {r['speed_km_s']:.2f} km/s   ·   Earth link delay {lt:.1f} min (one-way)", 13, "#9db3ca"))
    for n_, line in enumerate(textwrap.wrap(r["event"], 58)[:2]):
        o.append(_tx(LX, 552 + 20 * n_, line, 14, "#ff9d8a" if alarm else "#cfe3ff", w=700 if alarm else 400))
    o.append(_tx(LX, 592, "SIMULATED DATA · FICTIONAL · educational demonstration only", 11, "#6d86a3"))
    # timeline strip
    X0, W_ = 20.0, 1140.0
    xi = lambda k: X0 + W_ * k / (N - 1)
    for k, (nm, n, *_rest) in enumerate(PHASES):
        a_, b_ = PH_START[k], PH_START[k + 1] - 1
        o.append(f'<rect x="{xi(a_):.1f}" y="604" width="{max(1, xi(b_) - xi(a_)):.1f}" height="22" fill="{"#12304a" if k % 2 else "#0e2238"}"/>')
    for eid, (nm, on, pk, hold, end, _t) in EVENTS.items():
        c = "#ff5d6c" if eid == "CABIN" else "#ffb454"
        o.append(f'<rect x="{xi(on):.1f}" y="604" width="{xi(end) - xi(on):.1f}" height="22" fill="{c}" opacity=".55"/>' + _tx(xi(on), 642, eid, 10, c, w=700))
    for j in np.flatnonzero(telemetry().marker.to_numpy()):
        o.append(f'<line x1="{xi(j):.1f}" y1="604" x2="{xi(j):.1f}" y2="626" stroke="#7fb8ff" opacity=".5"/>')
    for k, lab in ((50, "LIFTOFF"), (270, "TMI"), (750, "APPROACH"), (830, "MOI"), (920, "EDL")):
        o.append(_tx(xi(k), 642, lab, 10, "#6d86a3"))
    o.append(f'<line x1="{xi(i):.1f}" y1="598" x2="{xi(i):.1f}" y2="630" stroke="#fff" stroke-width="2.5"/><path d="M{xi(i) - 5:.1f},596 L{xi(i) + 5:.1f},596 L{xi(i):.1f},603Z" fill="#fff"/>')
    o.append("</svg>")
    return "".join(o)


# ----------------------------------------------------------------------------- Streamlit console
@lru_cache(maxsize=1)
def _csv() -> str:
    return telemetry().reset_index().to_csv(index=False)


@lru_cache(maxsize=1)
def _met_labels():
    return telemetry().met_label.tolist()


@lru_cache(maxsize=32)
def _series(var):
    return telemetry()[var].astype(float).tolist()


def _bands():
    short = {"SPE": "Solar particle event", "CREW": "Crew anomaly", "CABIN": "Cabin anomaly"}
    return [(short[k], v[1], v[4], "#ff5d6c" if k == "CABIN" else "#ffb454") for k, v in EVENTS.items()]


def _live(evaluate_rules):
    ss, was = st.session_state, st.session_state.mm_playing
    new = tick(ss)                                                    # 1) move the single shared index (+ hazard detection)
    st.slider("⏱ Time-warp: drag to jump to any of the 1,000 timestamps", 0, N - 1, key="mm_slider", on_change=_cb_slider)
    i = int(ss.mm_idx)
    apply_snapshot(i)                                                  # 2) ASTRA session variables = snapshot i
    rec = get_snapshot(i)
    st.markdown(ui.img_html(render_svg(i), "width:100%;border-radius:14px"), unsafe_allow_html=True)   # 3) frame i
    vals = snapshot_values(i)
    alerts = evaluate_rules(vals)                                      # 4) ASTRA rules on the same snapshot i
    if new:
        ui.toast_episodes(new, lambda k: _met_labels()[k])             # 5) hazard notifications
    hist = {k: v for k, v in telemetry()[ASTRA_VARS].iloc[max(0, i - 59):i + 1].to_dict("list").items()}
    st.markdown(ui.status_bar_html(alerts, f"{rec['phase']} · {rec['met_label']} · sample {i + 1}/{N}"), unsafe_allow_html=True)
    left, right = st.columns([5, 3])
    left.markdown(ui.tiles_html(vals, ui.var_levels(alerts), hist), unsafe_allow_html=True)
    with right:
        ui.notification_center(ss.mm_eps, i, set(ss.mm_ack), lambda k: _met_labels()[k], _cb_ack)
    with st.expander("📈 Trend explorer: any variable over the whole mission", expanded=True):
        c1, c2 = st.columns([2, 3])
        c1.selectbox("Variable", list(ui.VAR_LABELS), index=list(ui.VAR_LABELS).index(ss.mm_trend), key="mm_trend_w",
                     format_func=ui.VAR_LABELS.get, on_change=lambda: ss.__setitem__("mm_trend", ss.mm_trend_w))
        c2.radio("Window", list(TREND_WINDOWS), index=list(TREND_WINDOWS).index(ss.mm_window), horizontal=True, key="mm_window_w",
                 on_change=lambda: ss.__setitem__("mm_window", ss.mm_window_w))
        var = ss.mm_trend
        svg = ui.trend_svg(_series(var), i, ui.VAR_LABELS[var].split("(")[-1].rstrip(")"), TREND_WINDOWS[ss.mm_window],
                           ui.levels_for_var(ss.mm_alerts, var), _bands(), lambda k: _met_labels()[k])
        st.markdown(ui.img_html(svg), unsafe_allow_html=True)
    with st.expander("All 19 ASTRA variables + position at this timestamp", expanded=False):
        st.dataframe(pd.DataFrame([{k: rec[k] for k in ASTRA_VARS + ["exercise_type", "pos_x_au", "pos_y_au", "altitude_km", "speed_km_s"]}]),
                     hide_index=True)
    if was and not ss.mm_playing:
        st.rerun()                                                     # refresh the Play/Pause label


def render_console(evaluate_rules):
    """Mission console shown on the Overview page when this mission is the selected data source."""
    init_state()
    ss = st.session_state
    ui.inject_css()
    ensure_alerts(evaluate_rules)
    st.subheader("Earth → Mars mission replay")
    st.caption("**SIMULATED, FICTIONAL DATA.** Toy two-body trajectory and rule-based crew/cabin model, not a validated physiological "
               "or spacecraft simulation. Alerts use ASTRA's unchanged illustrative rules.")
    c1, c2, c3, c4 = st.columns([1, 1, 2, 2])
    c1.button("⏸ Pause" if ss.mm_playing else "▶ Play", on_click=_cb_toggle, type="primary")
    c2.button("⏮ Reset", on_click=_cb_reset)
    # widget keys are discarded by Streamlit when the page is left, so mirror them into persistent keys
    c3.select_slider("Playback speed", options=SPEEDS, value=ss.mm_speed, key="mm_speed_w", format_func=lambda v: f"{v}×",
                     on_change=lambda: ss.__setitem__("mm_speed", ss.mm_speed_w))
    c4.selectbox("Auto-pause on new hazard", PAUSE_OPTIONS, index=PAUSE_OPTIONS.index(ss.mm_pause_on), key="mm_pause_w",
                 on_change=lambda: ss.__setitem__("mm_pause_on", ss.mm_pause_w))
    j = st.columns(5)
    for col, (lab, eid) in zip(j[:3], [("⚡ Solar particle event", "SPE"), ("🫂 Crew anomaly", "CREW"), ("🫁 Cabin anomaly", "CABIN")]):
        col.button(lab, on_click=_cb_jump, args=(EVENTS[eid][2],))
    j[3].button("🚀 Liftoff", on_click=_cb_jump, args=(int(PH_START[1]),))
    j[4].button("🛬 Landing", on_click=_cb_jump, args=(N - 1,))
    frag = st.fragment(run_every=TICK if ss.mm_playing else None)(_live)   # timer only while playing
    frag(evaluate_rules)
    st.download_button("Download the 1,000-row mission telemetry (CSV)", _csv(), "astra_mars_mission_telemetry.csv", "text/csv")
