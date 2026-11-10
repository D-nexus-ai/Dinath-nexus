"""astra_ui.py - shared, mission-independent ASTRA dashboard pieces.

Used by app.py (manual mode) and by every mission plug-in (e.g. mars_mission.py):
    status bar, compact vital tiles with sparklines, hazard notification centre, toasts, trend charts.
All visuals are plain HTML / data-URI SVG, so no extra dependencies are needed.

MISSION PLUG-IN INTERFACE (what app.py expects from a module registered in MISSION_SOURCES)
    LABEL: str                               text shown in the sidebar "Data source" dropdown
    sync_session(active, visible)            called on every run; when `active` it must write the current replay
                                             sample into the ASTRA session variables, otherwise pause playback
    render_console(evaluate_rules)           draws the mission console on the Overview page
"""
from __future__ import annotations

import base64
import html

import streamlit as st

LEVEL_RANK = {"": 0, "REVIEW": 1, "HIGH": 2}
LEVEL_COLOR = {"": "#61d9d0", "REVIEW": "#ffb454", "HIGH": "#ff5d6c"}

# (group, [(variable, label, unit, decimals)])  - "bp" is the combined systolic/diastolic tile
TILES = [
    ("VITALS", [("heart_rate", "Heart rate", "bpm", 0), ("spo2", "SpO₂", "%", 0), ("respiration", "Respiration", "br/min", 0),
                ("skin_temp", "Skin temp", "°C", 1), ("bp", "Blood pressure", "mmHg", 0)]),
    ("CREW WELLBEING", [("fatigue", "Fatigue", "/10", 0), ("mood", "Mood", "/10", 0), ("sleep", "Sleep", "h", 1),
                        ("water", "Water", "L", 2), ("exercise", "Exercise", "min", 0), ("calories", "Calories", "kcal", 0)]),
    ("CABIN & RADIATION", [("co2", "CO₂", "ppm", 0), ("oxygen", "Oxygen", "%", 1), ("cabin_pressure", "Pressure", "kPa", 1),
                           ("temperature", "Cabin temp", "°C", 1), ("humidity", "Humidity", "%", 0),
                           ("particles", "Particles", "units", 1), ("radiation", "Radiation", "u/h", 2)]),
]
# which tile(s) each alert key from evaluate_rules() belongs to
ALERT_VARS = {
    "SpO₂": ("spo2",), "Heart rate": ("heart_rate",), "Respiration": ("respiration",), "Skin temperature": ("skin_temp",),
    "Blood pressure": ("bp", "systolic", "diastolic"), "Blood pressure data quality": ("bp", "systolic", "diastolic"),
    "Fatigue": ("fatigue",), "Sleep": ("sleep",), "Mood": ("mood",), "CO₂": ("co2",), "Oxygen concentration": ("oxygen",),
    "Cabin pressure": ("cabin_pressure",), "Cabin temperature": ("temperature",), "Relative humidity": ("humidity",),
    "Particles": ("particles",), "Radiation": ("radiation",)}
VAR_LABELS = {"heart_rate": "Heart rate (bpm)", "spo2": "SpO₂ (%)", "respiration": "Respiration (breaths/min)",
              "skin_temp": "Skin temperature (°C)", "systolic": "Systolic BP (mmHg)", "diastolic": "Diastolic BP (mmHg)",
              "fatigue": "Fatigue (1-10)", "sleep": "Sleep (h)", "mood": "Mood (1-10)", "water": "Water (L)",
              "exercise": "Exercise (min)", "calories": "Calories (kcal)", "co2": "CO₂ (ppm)", "oxygen": "Oxygen (%)",
              "cabin_pressure": "Cabin pressure (kPa)", "temperature": "Cabin temperature (°C)", "humidity": "Humidity (%)",
              "particles": "Particles (demo units)", "radiation": "Radiation (units/h)"}

CSS = """<style>
.ax-h{color:#9db3ca;font-size:.68rem;letter-spacing:.16em;font-weight:700;margin:8px 0 4px}
.ax-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(132px,1fr));gap:7px;margin-bottom:4px}
.ax-t{background:#0c1b2d;border:1px solid #23425c;border-left:4px solid #2f8f88;border-radius:10px;padding:5px 9px 3px}
.ax-t.review{border-left-color:#ffb454;background:#2a2212}.ax-t.high{border-left-color:#ff5d6c;background:#2b1219}
.ax-l{display:flex;justify-content:space-between;align-items:center;font-size:.66rem;color:#9db3ca;text-transform:uppercase;letter-spacing:.05em}
.ax-b{font-size:.58rem;font-weight:800;padding:0 5px;border-radius:6px;color:#07111f;background:#ffb454}
.ax-t.high .ax-b{background:#ff5d6c}
.ax-v{font-size:1.2rem;font-weight:700;color:#edf4ff;line-height:1.25}.ax-u{font-size:.68rem;color:#9db3ca;font-weight:400}
.ax-t img{width:100%;height:26px;display:block}
.ax-bar{display:flex;align-items:center;gap:12px;flex-wrap:wrap;background:#0c1b2d;border:1px solid #23425c;border-radius:12px;padding:8px 12px;margin:6px 0 4px}
.ax-pill{font-weight:800;font-size:.78rem;letter-spacing:.08em;padding:3px 12px;border-radius:999px;color:#07111f;background:#61d9d0}
.ax-pill.review{background:#ffb454}.ax-pill.high{background:#ff5d6c}
.ax-cnt{color:#cfe3ff;font-size:.8rem}.ax-sub{color:#9db3ca;font-size:.78rem;margin-left:auto}
.ax-nc{background:#0c1b2d;border:1px solid #23425c;border-radius:12px;padding:8px 10px;max-height:330px;overflow-y:auto}
.ax-nt{color:#9db3ca;font-size:.68rem;letter-spacing:.14em;font-weight:700;margin-bottom:6px}
.ax-n{border-left:4px solid #ffb454;background:#2a2212;border-radius:8px;padding:5px 8px;margin-bottom:6px}
.ax-n.high{border-left-color:#ff5d6c;background:#2b1219}.ax-n.done{opacity:.55;background:#10263b;border-left-color:#2f8f88}
.ax-n.ack{opacity:.7}
.ax-nh{display:flex;justify-content:space-between;gap:8px;font-size:.76rem;color:#edf4ff}.ax-nh span{color:#9db3ca;font-size:.68rem;white-space:nowrap}
.ax-nm{font-size:.7rem;color:#b9c9dc;margin-top:2px}.ax-ok{color:#61d9d0;font-size:.8rem;padding:6px 2px}
</style>"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def img_html(svg: str, style: str = "width:100%") -> str:
    return f'<img style="{style}" src="data:image/svg+xml;base64,{base64.b64encode(svg.encode()).decode()}">'


# ----------------------------------------------------------------------------- status / tiles
def var_levels(alerts) -> dict:
    """{tile or variable name: highest alert level} for a list of (level, key, msg) from evaluate_rules()."""
    out: dict = {}
    for level, key, _ in alerts:
        for v in ALERT_VARS.get(key, ()):
            if LEVEL_RANK[level] > LEVEL_RANK.get(out.get(v, ""), 0):
                out[v] = level
    return out


def overall_level(alerts) -> str:
    return "HIGH" if any(a[0] == "HIGH" for a in alerts) else "REVIEW" if alerts else ""


def sparkline(series, level="", w=120, h=26) -> str:
    flat = [v for s in series for v in s]
    if len(flat) < 4:
        return ""
    lo, hi = min(flat), max(flat)
    span = (hi - lo) or 1.0
    col = LEVEL_COLOR[level]
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">']
    for k, s in enumerate(series):
        n = len(s)
        pts = [(2 + (w - 4) * j / (n - 1), h - 3 - (h - 6) * (v - lo) / span) for j, v in enumerate(s)]
        parts.append(f'<polyline fill="none" stroke="{col}" stroke-width="{1.8 if k == 0 else 1.1}" opacity="{1 if k == 0 else .45}" '
                     f'stroke-linejoin="round" points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in pts)}"/>')
        if k == 0:
            parts.append(f'<circle cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" r="2.4" fill="{col}"/>')
    return img_html("".join(parts) + "</svg>", "")


def status_bar_html(alerts, sub="") -> str:
    lvl = overall_level(alerts)
    nh, nr = sum(a[0] == "HIGH" for a in alerts), sum(a[0] == "REVIEW" for a in alerts)
    text = {"HIGH": "ATTENTION REQUIRED", "REVIEW": "REVIEW INPUTS", "": "ALL NOMINAL"}[lvl]
    return (f'<div class="ax-bar"><span class="ax-pill {lvl.lower()}">{text}</span>'
            f'<span class="ax-cnt">{nh} HIGH · {nr} REVIEW</span><span class="ax-sub">{html.escape(sub)}</span></div>')


def tiles_html(vals, levels, hist=None) -> str:
    """Compact tile grid. `hist` = {variable: [recent values]} adds a sparkline trend to each tile."""
    out = []
    for group, items in TILES:
        out.append(f'<div class="ax-h">{group}</div><div class="ax-grid">')
        for var, label, unit, dec in items:
            lvl = levels.get(var, "")
            if var == "bp":
                val = f"{vals['systolic']:.0f}/{vals['diastolic']:.0f}"
                series = [hist["systolic"], hist["diastolic"]] if hist else []
            else:
                val = f"{vals[var]:,.{dec}f}"
                series = [hist[var]] if hist else []
            badge = f'<span class="ax-b">{lvl}</span>' if lvl else ""
            out.append(f'<div class="ax-t {lvl.lower()}"><div class="ax-l"><span>{label}</span>{badge}</div>'
                       f'<div class="ax-v">{val}<span class="ax-u"> {unit}</span></div>{sparkline(series, lvl)}</div>')
        out.append("</div>")
    return "".join(out)


# ----------------------------------------------------------------------------- hazard episodes / notifications
def build_episodes(alerts_by_sample) -> list:
    """Collapse per-sample alert lists into episodes: one per continuous run of the same alert key."""
    open_, eps = {}, []
    for i, al in enumerate(alerts_by_sample):
        now = {k: (lvl, msg) for lvl, k, msg in al}
        for k, (lvl, msg) in now.items():
            if k not in open_:
                open_[k] = {"id": f"{k}@{i}", "key": k, "level": lvl, "msg": msg, "start": i, "end": i}
            open_[k]["end"] = i
        for k in [k for k in open_ if k not in now]:
            eps.append(open_.pop(k))
    eps.extend(open_.values())
    return sorted(eps, key=lambda e: (e["start"], e["key"]))


def active_at(eps, i):
    return [e for e in eps if e["start"] <= i <= e["end"]]


def new_since(eps, prev, i):
    """Episodes that began after sample `prev` up to and including `i` (forward movement only)."""
    return [e for e in eps if prev < e["start"] <= i] if i > prev else []


def levels_for_var(alerts_by_sample, var):
    return [max((a[0] for a in al if var in ALERT_VARS.get(a[1], ())), key=lambda l: LEVEL_RANK[l], default="")
            for al in alerts_by_sample]


def notifications_html(eps, i, ack, label_fn, max_done=4) -> str:
    act = sorted(active_at(eps, i), key=lambda e: (-LEVEL_RANK[e["level"]], e["start"]))
    done = sorted([e for e in eps if e["end"] < i], key=lambda e: -e["end"])[:max_done]
    rows = [f'<div class="ax-nt">🔔 HAZARD NOTIFICATIONS · {len(act)} ACTIVE</div>']
    if not act:
        rows.append('<div class="ax-ok">✔ No active hazards</div>')
    for e in act:
        a = e["id"] in ack
        rows.append(f'<div class="ax-n {e["level"].lower()} {"ack" if a else ""}"><div class="ax-nh"><b>{"🚨" if e["level"] == "HIGH" else "⚠️"} '
                    f'{e["level"]} · {html.escape(e["key"])}</b><span>{"✓ ack · " if a else ""}since {label_fn(e["start"])}</span></div>'
                    f'<div class="ax-nm">{html.escape(e["msg"])}</div></div>')
    for e in done:
        rows.append(f'<div class="ax-n done"><div class="ax-nh"><b>✔ {html.escape(e["key"])} recovered</b>'
                    f'<span>{label_fn(e["start"])} → {label_fn(e["end"])}</span></div></div>')
    return f'<div class="ax-nc">{"".join(rows)}</div>'


def notification_center(eps, i, ack, label_fn, on_ack):
    st.markdown(notifications_html(eps, i, ack, label_fn), unsafe_allow_html=True)
    pending = [e for e in active_at(eps, i) if e["id"] not in ack]
    st.button("✓ Acknowledge all active", on_click=on_ack, disabled=not pending, key="ax_ack_btn")


def toast_episodes(new, label_fn, limit=3):
    for e in sorted(new, key=lambda e: -LEVEL_RANK[e["level"]])[:limit]:
        st.toast(f"{e['level']} · {e['key']} at {label_fn(e['start'])}", icon="🚨" if e["level"] == "HIGH" else "⚠️")
    if len(new) > limit:
        st.toast(f"+{len(new) - limit} more hazard(s): see the notification centre", icon="🔔")


def manual_toasts(alerts, state, key="_ax_prev_alerts"):
    """Toast whenever a hazard newly appears in manual mode (not on the first run, not while it persists)."""
    now, prev = {a[1] for a in alerts}, state.get(key)
    if prev is not None:
        for level, k, _ in alerts:
            if k not in prev:
                st.toast(f"{level} · {k}", icon="🚨" if level == "HIGH" else "⚠️")
    state[key] = now


def render_overview(vals, alerts):
    """Compact manual-mode dashboard: status bar + tiles + active hazards."""
    st.markdown(status_bar_html(alerts, "manual inputs · edit them in Sensor Lab"), unsafe_allow_html=True)
    left, right = st.columns([5, 3])
    left.markdown(tiles_html(vals, var_levels(alerts)), unsafe_allow_html=True)
    right.markdown(notifications_html([{"id": k, "key": k, "level": l, "msg": m, "start": 0, "end": 0} for l, k, m in alerts],
                                      0, set(), lambda _: "now"), unsafe_allow_html=True)


# ----------------------------------------------------------------------------- trend chart
def trend_svg(values, i, unit, window, flags=None, bands=(), x_label=None, w=1100, h=210) -> str:
    """Line chart of `values` with playhead at sample i. window=None -> whole timeline, else last `window` samples."""
    n = len(values)
    lo_i, hi_i = (0, n - 1) if window is None else (max(0, i - window), max(i, 1))
    seg = values[lo_i:hi_i + 1]
    vmin, vmax = min(seg), max(seg)
    pad = (vmax - vmin) * .15 or max(abs(vmax) * .05, 1.0)
    nonneg = vmin >= 0
    vmin, vmax = vmin - pad, vmax + pad
    if nonneg:
        vmin = max(vmin, 0.0)                              # never draw a negative axis for a non-negative quantity
    fmt = lambda v: f"{v:,.0f}" if abs(v) >= 100 else f"{v:,.2f}"
    ml, mr, mt, mb = 54, 16, 16, 26
    X = lambda k: ml + (w - ml - mr) * (k - lo_i) / (hi_i - lo_i)
    Y = lambda v: mt + (h - mt - mb) * (1 - (v - vmin) / (vmax - vmin))
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" font-family="Segoe UI,Helvetica,Arial,sans-serif">',
         f'<rect width="{w}" height="{h}" rx="12" fill="#0c1b2d" stroke="#23425c"/>']
    for g in (0, .5, 1):
        v = vmin + (vmax - vmin) * g
        o.append(f'<line x1="{ml}" x2="{w - mr}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="#23425c" stroke-dasharray="3 5"/>'
                 f'<text x="{ml - 6}" y="{Y(v) + 4:.1f}" font-size="11" fill="#9db3ca" text-anchor="end">{fmt(v)}</text>')
    for name, s, e, col in bands:
        a, b = max(s, lo_i), min(e, hi_i)
        if b > a:
            o.append(f'<rect x="{X(a):.1f}" y="{mt}" width="{X(b) - X(a):.1f}" height="{h - mt - mb}" fill="{col}" opacity=".16"/>'
                     f'<text x="{X(a) + 4:.1f}" y="{mt + 11}" font-size="10" font-weight="700" fill="{col}">{html.escape(name)}</text>')
    k_end = min(i, hi_i)
    if k_end > lo_i:
        o.append('<polyline fill="none" stroke="#61d9d0" stroke-width="2" stroke-linejoin="round" points="'
                 + " ".join(f"{X(k):.1f},{Y(values[k]):.1f}" for k in range(lo_i, k_end + 1)) + '"/>')
    if hi_i > k_end:
        o.append('<polyline fill="none" stroke="#4d6a85" stroke-width="1.3" stroke-dasharray="2 3" points="'
                 + " ".join(f"{X(k):.1f},{Y(values[k]):.1f}" for k in range(k_end, hi_i + 1)) + '"/>')
    for k in range(lo_i, k_end + 1):
        if flags and flags[k]:
            o.append(f'<circle cx="{X(k):.1f}" cy="{Y(values[k]):.1f}" r="3" fill="{LEVEL_COLOR[flags[k]]}"/>')
    cx = X(min(max(i, lo_i), hi_i))
    o.append(f'<line x1="{cx:.1f}" x2="{cx:.1f}" y1="{mt}" y2="{h - mb}" stroke="#fff" stroke-width="1.5"/>'
             f'<circle cx="{cx:.1f}" cy="{Y(values[i]):.1f}" r="4.5" fill="#fff"/>'
             f'<text x="{min(cx + 8, w - 120):.1f}" y="{max(Y(values[i]) - 8, mt + 22):.1f}" font-size="12" font-weight="700" fill="#fff">{fmt(values[i])} {html.escape(unit)}</text>')
    if x_label:
        o.append(f'<text x="{ml}" y="{h - 8}" font-size="10" fill="#9db3ca">{x_label(lo_i)}</text>'
                 f'<text x="{w - mr}" y="{h - 8}" font-size="10" fill="#9db3ca" text-anchor="end">{x_label(hi_i)}</text>')
    return "".join(o) + "</svg>"
