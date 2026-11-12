"""ASTRA Insights: Crew Resilience and Mission Debrief pages.

Drop this file beside app.py, astra_ui.py and mars_mission.py.
Uses only Streamlit, pandas and Python standard-library modules already used by ASTRA.
All mission replay data are synthetic; this is an educational prototype, not a medical/flight tool.
"""
from __future__ import annotations

import html
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st


STYLE = """
<style>
.ax-hero{padding:30px 32px;border:1px solid rgba(104,220,226,.28);border-radius:22px;margin:4px 0 22px;
background:radial-gradient(ellipse at 86% 8%,rgba(85,213,222,.22),transparent 27%),
radial-gradient(ellipse at 8% 110%,rgba(113,100,255,.20),transparent 34%),
linear-gradient(118deg,#102b43 0%,#101d35 55%,#171a3b 100%);position:relative;overflow:hidden;
box-shadow:0 16px 42px rgba(0,0,0,.18)}
.ax-hero:before{content:"";position:absolute;width:230px;height:230px;border:1px solid rgba(126,225,232,.16);border-radius:50%;right:4%;top:-135px;box-shadow:0 0 0 18px rgba(126,225,232,.035),0 0 0 38px rgba(126,225,232,.025)}
.ax-hero:after{content:"✦     ·       ✧          ·       ✦";position:absolute;right:25px;bottom:22px;color:#9be9e2;opacity:.42;letter-spacing:12px;animation:axfloat 7s ease-in-out infinite}
@keyframes axfloat{50%{transform:translateY(7px);opacity:.7}}
.ax-kicker{color:#72e4dc;font-size:.69rem;font-weight:850;letter-spacing:.2em;text-transform:uppercase}
.ax-title{color:#f2f7ff;font-size:clamp(1.65rem,3vw,2.15rem);font-weight:850;margin:8px 0;letter-spacing:-.035em}
.ax-sub{color:#b8cce0;font-size:.92rem;max-width:850px;line-height:1.55}
.ax-section{color:#82dcd9;font-size:.68rem;font-weight:850;letter-spacing:.18em;margin:22px 0 9px;text-transform:uppercase}
.ax-card{background:linear-gradient(145deg,rgba(17,42,64,.96),rgba(10,24,42,.96));border:1px solid #294d68;
border-radius:16px;padding:15px 17px;margin:8px 0;box-shadow:0 9px 24px rgba(0,0,0,.12)}
.ax-event{border:1px solid rgba(255,180,84,.22);border-left:4px solid #ffb454;background:linear-gradient(100deg,rgba(255,180,84,.10),rgba(17,37,57,.72));border-radius:11px;padding:11px 14px;margin:8px 0}
.ax-event.red{border-color:rgba(255,93,108,.24);border-left-color:#ff5d6c;background:linear-gradient(100deg,rgba(255,93,108,.10),rgba(17,37,57,.72))}
.ax-muted{color:#9db3ca;font-size:.76rem;line-height:1.45}
.ax-chart-shell{background:linear-gradient(155deg,rgba(13,31,51,.98),rgba(8,20,36,.98));border:1px solid #294b65;border-radius:18px;padding:14px 15px 8px;margin:8px 0 12px;box-shadow:0 14px 32px rgba(0,0,0,.16)}
.ax-chart-head{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;padding:3px 7px 5px}
.ax-chart-title{font-size:.92rem;font-weight:800;color:#eaf5ff}.ax-chart-unit{font-size:.7rem;color:#8eaac2;letter-spacing:.08em;text-transform:uppercase}
.ax-chart-svg{width:100%;height:auto;display:block;overflow:visible}
.ax-stat-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:9px;margin:10px 0 16px}
.ax-stat{background:linear-gradient(145deg,#112b43,#0c1d31);border:1px solid #284963;border-radius:14px;padding:12px 14px;min-width:0}
.ax-stat-label{font-size:.64rem;color:#91acc5;letter-spacing:.12em;text-transform:uppercase;font-weight:800}
.ax-stat-value{font-size:1.22rem;color:#f2f7ff;font-weight:850;margin-top:4px;overflow-wrap:anywhere}
.ax-stat-note{font-size:.7rem;color:#6edbd5;margin-top:2px}
.ax-event-legend{display:flex;gap:14px;flex-wrap:wrap;padding:3px 8px 8px;color:#9db3ca;font-size:.68rem}
.ax-dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px}
div[data-testid="stMetric"]{background:linear-gradient(145deg,rgba(17,42,64,.96),rgba(10,24,42,.96));
border:1px solid #294d68;padding:13px 15px;border-radius:15px;box-shadow:0 8px 22px rgba(0,0,0,.12)}
</style>
"""


def _hero(kicker: str, title: str, subtitle: str) -> None:
    st.markdown(STYLE, unsafe_allow_html=True)
    st.markdown(
        f'<div class="ax-hero"><div class="ax-kicker">{html.escape(kicker)}</div>'
        f'<div class="ax-title">{html.escape(title)}</div><div class="ax-sub">{html.escape(subtitle)}</div></div>',
        unsafe_allow_html=True,
    )


def _read_logs(db_path: str | Path, crew: str) -> pd.DataFrame:
    path = Path(db_path)
    if not path.exists():
        return pd.DataFrame()
    try:
        with sqlite3.connect(path, timeout=10) as conn:
            return pd.read_sql_query(
                "SELECT * FROM health_logs WHERE crew=? ORDER BY logged_at, id",
                conn, params=(crew,),
            )
    except (sqlite3.Error, pd.errors.DatabaseError):
        return pd.DataFrame()


def _mission_data(mm) -> pd.DataFrame:
    df = mm.telemetry().copy()
    required = {"sample", "met_label", "phase", "fatigue", "sleep", "mood",
                "heart_rate", "radiation", "co2", "oxygen"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError("Missing telemetry columns: " + ", ".join(sorted(missing)))
    return df



def _render_premium_chart(frame: pd.DataFrame, value_col: str, unit: str, title: str,
                          x_col: str | None = None, event_windows=None, date_axis: bool = False) -> None:
    """Render a dependency-free responsive SVG chart with gradient fill and event bands."""
    data = frame.copy().reset_index(drop=True)
    data[value_col] = pd.to_numeric(data[value_col], errors="coerce")
    data = data.dropna(subset=[value_col]).reset_index(drop=True)
    if data.empty:
        st.info("There are no numeric samples available for this chart yet.")
        return
    values = data[value_col].astype(float).tolist()
    n = len(values)
    width, height = 1160, 350
    left, right, top, bottom = 66, 26, 24, 54
    plot_w, plot_h = width-left-right, height-top-bottom
    lo, hi = min(values), max(values)
    pad = (hi-lo)*0.16 if hi != lo else max(abs(hi)*0.08, 1.0)
    y_min, y_max = lo-pad, hi+pad
    if lo >= 0:
        y_min = max(0.0, y_min)
    if y_max <= y_min:
        y_max = y_min + 1.0
    x = lambda i: left + (plot_w * i / max(n-1, 1))
    y = lambda v: top + plot_h * (1-(v-y_min)/(y_max-y_min))
    pts = [(x(i), y(v)) for i, v in enumerate(values)]
    line = " ".join(f"{px:.1f},{py:.1f}" for px,py in pts)
    area = f"{left},{top+plot_h} " + line + f" {left+plot_w},{top+plot_h}"
    fmt = lambda v: f"{v:,.0f}" if abs(v) >= 100 else f"{v:.2f}".rstrip("0").rstrip(".")
    parts = [f'<div class="ax-chart-shell"><div class="ax-chart-head"><div class="ax-chart-title">{html.escape(title)}</div><div class="ax-chart-unit">{html.escape(unit)}</div></div>',
             f'<svg class="ax-chart-svg" viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(title)} trend chart" xmlns="http://www.w3.org/2000/svg">',
             '<defs><linearGradient id="axArea" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#63e0d7" stop-opacity=".34"/><stop offset="100%" stop-color="#63e0d7" stop-opacity=".015"/></linearGradient><filter id="axGlow" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>',
             f'<rect x="{left}" y="{top}" width="{plot_w}" height="{plot_h}" rx="9" fill="#091a2b" opacity=".72"/>']
    # Scenario event windows are shaded behind the data trace.
    legend = []
    for idx, item in enumerate(event_windows or []):
        label, start, finish, color = item
        a, b = max(0, int(start)), min(n-1, int(finish))
        if b < a:
            continue
        xa, xb = x(a), x(b)
        parts.append(f'<rect x="{xa:.1f}" y="{top}" width="{max(2,xb-xa):.1f}" height="{plot_h}" fill="{color}" opacity=".13"/>')
        if xb-xa > 65:
            parts.append(f'<text x="{xa+5:.1f}" y="{top+15+idx%2*13}" fill="{color}" font-size="10" font-weight="700">{html.escape(label)}</text>')
        legend.append((label,color))
    for tick in range(5):
        fraction = tick/4
        val = y_min + (y_max-y_min)*fraction
        yy = y(val)
        parts.append(f'<line x1="{left}" x2="{left+plot_w}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="#29445c" stroke-dasharray="3 7" opacity=".8"/>')
        parts.append(f'<text x="{left-12}" y="{yy+4:.1f}" fill="#8da9c1" font-size="11" text-anchor="end">{fmt(val)}</text>')
    parts.append(f'<polygon points="{area}" fill="url(#axArea)"/>')
    parts.append(f'<polyline points="{line}" fill="none" stroke="#67e3dc" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" filter="url(#axGlow)"/>')
    # A small number of anchor points keeps long traces crisp rather than cluttered.
    stride = max(1, n//18)
    for i in range(0,n,stride):
        px,py=pts[i]
        parts.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="2.6" fill="#b9fff7" opacity=".8"/>')
    last_x,last_y=pts[-1]
    parts.append(f'<line x1="{last_x:.1f}" x2="{last_x:.1f}" y1="{top}" y2="{top+plot_h}" stroke="#d9fffb" stroke-dasharray="4 5" opacity=".5"/>')
    parts.append(f'<circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="7" fill="#67e3dc" stroke="#eaffff" stroke-width="2"/>')
    parts.append(f'<text x="{max(left+4,min(last_x-10,width-right-10)):.1f}" y="{max(top+14,last_y-13):.1f}" fill="#efffff" font-size="12" font-weight="800" text-anchor="end">{fmt(values[-1])}</text>')
    if date_axis and x_col and x_col in data:
        dates = pd.to_datetime(data[x_col], errors="coerce")
        labels = [d.strftime("%d %b %y") if not pd.isna(d) else "" for d in (dates.iloc[0], dates.iloc[len(dates)//2], dates.iloc[-1])]
    elif x_col and x_col in data:
        raw = data[x_col].astype(str)
        labels = [raw.iloc[0], raw.iloc[len(raw)//2], raw.iloc[-1]]
    else:
        labels = ["START", f"{n//2:,} SAMPLES", "LATEST"]
    for pos, label, anchor_text in [(left,labels[0],"start"),(left+plot_w/2,labels[1],"middle"),(left+plot_w,labels[2],"end")]:
        parts.append(f'<text x="{pos:.1f}" y="{height-18}" fill="#8da9c1" font-size="10" text-anchor="{anchor_text}">{html.escape(str(label))}</text>')
    parts.append('</svg>')
    if legend:
        parts.append('<div class="ax-event-legend">')
        for label,color in legend:
            parts.append(f'<span><i class="ax-dot" style="background:{color}"></i>{html.escape(label)}</span>')
        parts.append('</div>')
    parts.append('</div>')
    st.markdown("".join(parts), unsafe_allow_html=True)


def _stat_cards(items) -> None:
    bits = ['<div class="ax-stat-grid">']
    for label, value, note in items:
        bits.append(f'<div class="ax-stat"><div class="ax-stat-label">{html.escape(str(label))}</div>'
                    f'<div class="ax-stat-value">{html.escape(str(value))}</div>'
                    f'<div class="ax-stat-note">{html.escape(str(note))}</div></div>')
    bits.append('</div>')
    st.markdown("".join(bits), unsafe_allow_html=True)


# ASTRA's seven-day monitor reuses existing illustrative demo rules. These are
# explainable prototype prompts, not validated medical or operational limits.
_SEVEN_DAY_METRICS = {
    "Fatigue": ("fatigue", "score / 10", "latest ≥ 8 / 10", lambda x: x >= 8, "up", 2.0, "rose by at least 2 points"),
    "Sleep": ("sleep_hours", "hours", "latest < 6 h", lambda x: x < 6, "down", 1.5, "fell by at least 1.5 hours"),
    "Mood": ("mood", "score / 10", "latest ≤ 3 / 10", lambda x: x <= 3, "down", 2.0, "fell by at least 2 points"),
    "Heart rate": ("heart_rate", "bpm", "latest < 50 or > 120 bpm", lambda x: x < 50 or x > 120, "either_pct", 20.0, "shifted by at least 20%"),
    "SpO₂": ("spo2", "%", "latest < 90%", lambda x: x < 90, "down", 3.0, "fell by at least 3 percentage points"),
    "Cabin CO₂": ("co2", "ppm", "latest > 5,000 ppm", lambda x: x > 5000, "up_pct", 20.0, "rose by at least 20%"),
    "Radiation": ("radiation", "illustrative units / h", "latest > 2 illustrative units / h", lambda x: x > 2, "up_pct", 20.0, "rose by at least 20%"),
}


def _seven_day_flags(window: pd.DataFrame) -> list[dict]:
    flags=[]
    for label, rule in _SEVEN_DAY_METRICS.items():
        col, unit, limit, threshold, direction, change_limit, change_text = rule
        if col not in window.columns:
            continue
        values=pd.to_numeric(window[col], errors="coerce").dropna()
        if values.empty:
            continue
        latest=float(values.iloc[-1])
        if bool(threshold(latest)):
            flags.append({"metric":label,"kind":"threshold","title":"Latest reading crosses an illustrative review rule",
                          "detail":f"Latest saved value: {latest:.2f} {unit}. Prototype rule: {limit}."})
        # Compare medians of the earlier and later halves; require >=4 records.
        if len(values)>=4:
            mid=len(values)//2
            baseline=float(values.iloc[:mid].median())
            recent=float(values.iloc[mid:].median())
            delta=recent-baseline
            triggered=False
            if direction=="up": triggered=delta>=change_limit
            elif direction=="down": triggered=delta<=-change_limit
            elif direction=="either_pct" and abs(baseline)>1e-9:
                triggered=abs(delta)/abs(baseline)*100>=change_limit
            elif direction=="up_pct" and abs(baseline)>1e-9:
                triggered=delta>0 and delta/abs(baseline)*100>=change_limit
            if triggered:
                flags.append({"metric":label,"kind":"trend","title":"Sustained seven-day trend change",
                              "detail":f"The later-half median ({recent:.2f}) {change_text} versus the earlier-half median ({baseline:.2f})."})
    return flags


def _seven_day_report(crew: str, window: pd.DataFrame, flags: list[dict]) -> str:
    start=window["logged_at"].min().strftime("%Y-%m-%d %H:%M UTC")
    end=window["logged_at"].max().strftime("%Y-%m-%d %H:%M UTC")
    lines=["# ASTRA — Seven-Day Crew Trend Report","",f"**Crew record label:** {crew}",
           f"**Coverage:** {start} to {end}",f"**Saved check-ins:** {len(window)}","",
           "> EDUCATIONAL DEMONSTRATION — user-entered demo records and illustrative rules only. Not a medical assessment or flight warning.",
           "","## Indicator summaries"]
    for label,rule in _SEVEN_DAY_METRICS.items():
        col,unit,*_=rule
        if col in window.columns:
            values=pd.to_numeric(window[col],errors="coerce").dropna()
            if not values.empty:
                lines.append(f"- **{label}:** latest {values.iloc[-1]:.2f} {unit}; median {values.median():.2f}; range {values.min():.2f}–{values.max():.2f}.")
    lines.extend(["","## Prototype notifications"])
    if flags:
        lines.extend([f"- **{f['metric']} — {f['title']}:** {f['detail']}" for f in flags])
    else:
        lines.append("- No seven-day prototype review flags were triggered in the available records.")
    lines.extend(["","## Method and limitations",
        "- Window: saved check-ins from the seven days before report generation (UTC).",
        "- Threshold flags compare the latest saved value with ASTRA's existing illustrative demo rules.",
        "- Trend flags compare earlier-half and later-half medians and require at least four readings.",
        "- Missing days are not interpolated; sparse records may miss short-lived changes.",
        "- These prompts are not diagnoses, validated clinical alerts, or operational flight guidance."])
    return "\n".join(lines)


def _render_seven_day_panel(logs: pd.DataFrame, crew: str, metric: str) -> None:
    st.markdown('<div class="ax-section">◈ SEVEN-DAY TREND WATCH</div>',unsafe_allow_html=True)
    if logs.empty or "logged_at" not in logs.columns:
        st.info("The seven-day monitor is ready, but there are no saved check-ins for this crew record yet.")
        st.caption("Save a demo check-in in Crew Logs & Records. The chart, review flags and downloadable report will populate from records in the rolling seven-day window.")
        return
    cutoff=pd.Timestamp.now(tz="UTC")-pd.Timedelta(days=7)
    window=logs.loc[logs["logged_at"]>=cutoff].copy().sort_values("logged_at")
    if window.empty:
        st.info("No saved check-ins were recorded in the last seven days. New entries in Crew Logs & Records will appear here automatically.")
        st.caption("The rolling window uses UTC timestamps and does not fill in missing days.")
        return
    flags=_seven_day_flags(window)
    days=max(0.0,(window["logged_at"].max()-window["logged_at"].min()).total_seconds()/86400)
    selected=_SEVEN_DAY_METRICS.get(metric)
    latest_text="—"
    if selected and selected[0] in window.columns:
        vals=pd.to_numeric(window[selected[0]],errors="coerce").dropna()
        if not vals.empty: latest_text=f"{vals.iloc[-1]:.1f} {selected[1]}"
    _stat_cards([("Check-ins",len(window),"saved in the last 7 days"),
                 ("Time covered",f"{days:.1f} days","between first and latest entry"),
                 ("Selected latest",latest_text,metric),
                 ("Review flags",len(flags),"illustrative prompts · not diagnoses")])
    if flags:
        st.markdown('<div class="ax-card"><b>✦ EARLY-WARNING NOTIFICATION CENTRE</b><div class="ax-muted">Every flag includes the measurement and rule that triggered it.</div></div>',unsafe_allow_html=True)
        for flag in flags:
            css="red" if flag["kind"]=="threshold" else ""
            st.markdown(f'<div class="ax-event {css}"><b>{html.escape(flag["metric"])} · {html.escape(flag["title"])}</b><div class="ax-muted">{html.escape(flag["detail"])}</div></div>',unsafe_allow_html=True)
    else:
        st.success("No seven-day prototype review flags were triggered in the available check-ins.")
    if selected and selected[0] in window.columns:
        col,unit=selected[0],selected[1]
        chart=window[["logged_at",col]].copy()
        chart[col]=pd.to_numeric(chart[col],errors="coerce")
        chart=chart.dropna().reset_index(drop=True)
        _render_premium_chart(chart,col,unit,f"{metric} · rolling seven-day window",x_col="logged_at",date_axis=True)
    report=_seven_day_report(crew,window,flags)
    stamp=datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    a,b=st.columns(2)
    a.download_button("⬇ DOWNLOAD · 7-DAY REPORT",report.encode("utf-8"),
                      f"ASTRA_7_day_report_{crew.lower().replace(' ','_')}_{stamp}.md","text/markdown",use_container_width=True)
    b.download_button("⬇ DOWNLOAD · 7-DAY DATA (CSV)",window.to_csv(index=False).encode("utf-8"),
                      f"ASTRA_7_day_data_{crew.lower().replace(' ','_')}_{stamp}.csv","text/csv",use_container_width=True)
    st.caption("Seven-day alerts are generated when this page is opened or refreshed; they are in-app demo notifications, not background push alerts.")



def render_seven_day_dashboard_alerts(db_path: str | Path, crew: str) -> None:
    """Show compact seven-day saved-check-in alerts on the Overview dashboard."""
    logs=_read_logs(db_path,crew)
    st.markdown('<div class="ax-section">◈ SEVEN-DAY CREW WATCH · '+html.escape(str(crew))+'</div>',unsafe_allow_html=True)
    if logs.empty or "logged_at" not in logs.columns:
        st.info(f"No saved check-ins are available for {crew} yet. Add a demo record in Crew Logs & Records to activate seven-day trend monitoring and alerts.")
        return
    logs["logged_at"]=pd.to_datetime(logs["logged_at"],errors="coerce",utc=True)
    logs=logs.dropna(subset=["logged_at"])
    if logs.empty:
        return
    cutoff=pd.Timestamp.now(tz="UTC")-pd.Timedelta(days=7)
    window=logs.loc[logs["logged_at"]>=cutoff].sort_values("logged_at")
    if window.empty:
        latest = logs["logged_at"].max()
        st.info(f"No check-ins for {crew} fall within the last seven days. The latest saved record is {latest.strftime('%d %b %Y, %H:%M UTC')}. Add a new demo check-in to start the current monitoring window.")
        return
    flags=_seven_day_flags(window)
    if not flags:
        st.caption(f"Seven-day watch clear · {len(window)} saved check-in(s) reviewed · no illustrative review flags triggered.")
        return
    st.markdown('<div class="ax-card"><b>✦ EARLY-WARNING NOTIFICATIONS</b><div class="ax-muted">Review the flagged demo trends and their explanations below.</div></div>',unsafe_allow_html=True)
    for flag in flags:
        css="red" if flag["kind"]=="threshold" else ""
        st.markdown(f'<div class="ax-event {css}"><b>{html.escape(flag["metric"])} · {html.escape(flag["title"])}</b><div class="ax-muted">{html.escape(flag["detail"])}</div></div>',unsafe_allow_html=True)
    st.caption("Illustrative prototype alerts from saved demo records only — not diagnoses or real-time medical/flight warnings.")

def _render_orbital_satellite() -> None:
    """A lightweight animated SVG accent; no image asset or extra package required."""
    st.markdown("""<div class="ax-card" style="display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;overflow:hidden">
      <div><div class="ax-kicker">ORBITAL SYSTEMS / ONLINE</div><b style="color:#effaff;font-size:1rem">Mission timeline in view</b>
      <div class="ax-muted">A small orbital marker for the debrief console</div></div>
      <svg viewBox="0 0 190 112" role="img" aria-label="Animated satellite orbiting a planet" style="width:180px;max-width:42%;height:auto">
        <defs><radialGradient id="axPlanet"><stop offset="0" stop-color="#70e6df"/><stop offset="1" stop-color="#24628c"/></radialGradient></defs>
        <circle cx="95" cy="56" r="25" fill="none" stroke="#3c6d88" stroke-dasharray="3 5" opacity=".65"/>
        <ellipse cx="95" cy="56" rx="62" ry="25" fill="none" stroke="#5ccfcf" stroke-width="1.3" opacity=".55" transform="rotate(-18 95 56)"/>
        <circle cx="95" cy="56" r="15" fill="url(#axPlanet)"/>
        <path d="M84 56 Q95 44 107 54" fill="none" stroke="#b7fff4" stroke-width="2" opacity=".65"/>
        <g transform="translate(95 56)"><g>
          <animateTransform attributeName="transform" type="rotate" from="0" to="360" dur="12s" repeatCount="indefinite"/>
          <g transform="translate(62 0) rotate(18)">
            <rect x="-5" y="-4" width="10" height="8" rx="2" fill="#f4d58a" stroke="#fff0c2"/>
            <rect x="-18" y="-5" width="10" height="10" fill="#4d91b7" stroke="#9de7f1"/>
            <rect x="8" y="-5" width="10" height="10" fill="#4d91b7" stroke="#9de7f1"/>
            <path d="M0 -4 L0 -11 M-3 -11 L3 -11" stroke="#ffe5a6" stroke-width="1.4"/>
          </g></g></g>
        <circle cx="26" cy="24" r="1.8" fill="#d6fff9"><animate attributeName="opacity" values=".25;1;.25" dur="2.4s" repeatCount="indefinite"/></circle>
        <circle cx="161" cy="83" r="1.5" fill="#d6fff9"><animate attributeName="opacity" values="1;.2;1" dur="3s" repeatCount="indefinite"/></circle>
      </svg></div>""",unsafe_allow_html=True)

def render_crew_resilience(db_path: str | Path, crew_options: list[str], mm) -> None:
    """Render a trend dashboard for either generated Mars telemetry or saved check-ins."""
    _hero(
        "ASTRA / HUMAN SYSTEMS ANALYTICS",
        "Crew Resilience Observatory",
        "Explore how crew-reported wellbeing and mission-environment indicators evolve over time. "
        "Trend visualisation only — not a medical assessment.",
    )
    mode = st.radio("DATA STREAM", ["Mars mission replay", "Saved crew check-ins"],
                    horizontal=True, key="axi_res_mode")

    if mode == "Mars mission replay":
        st.info("The seven-day health trend monitor is based on saved crew check-ins. Switch DATA STREAM to **Saved crew check-ins** below to view its chart, alerts and downloadable report.")
        try:
            df = _mission_data(mm)
        except Exception as exc:
            st.error(f"Could not load mission telemetry: {exc}")
            return
        st.markdown('<div class="ax-card"><b>LIVE SCENARIO STREAM</b><div class="ax-muted">Synthetic Mars-transit telemetry · event windows are scripted for demonstration · no live sensors connected</div></div>', unsafe_allow_html=True)
        _stat_cards([
            ("Telemetry points", f"{len(df):,}", "samples in scenario"),
            ("Mission phases", int(df["phase"].nunique()), "distinct timeline segments"),
            ("Scenario events", len(getattr(mm, "EVENTS", {})), "scripted event windows"),
            ("Latest phase", str(df["phase"].iloc[-1]), "end of generated timeline"),
        ])

        labels = {
            "fatigue": "Fatigue · self-report", "sleep": "Sleep · hours",
            "mood": "Mood · self-report", "heart_rate": "Heart rate · bpm",
            "radiation": "Radiation · illustrative units", "co2": "Cabin CO₂ · ppm",
            "oxygen": "Cabin oxygen · %",
        }
        variable = st.selectbox("Select an indicator", list(labels), format_func=labels.get, key="axi_res_var")
        event_windows = []
        event_colors = {"SPE": "#ffb454", "CREW": "#a78bfa", "CABIN": "#ff647c"}
        for key, event in getattr(mm, "EVENTS", {}).items():
            if len(event) >= 5:
                event_windows.append((str(event[0]), int(event[1]), int(event[4]), event_colors.get(key, "#ffb454")))
        _render_premium_chart(df, variable, labels[variable].split("·")[-1].strip(),
                              f"{labels[variable]} · full mission", x_col="sample", event_windows=event_windows)
        numeric = pd.to_numeric(df[variable], errors="coerce").dropna()
        if not numeric.empty:
            _stat_cards([
                ("Latest reading", f"{numeric.iloc[-1]:,.2f}", "last generated sample"),
                ("Scenario average", f"{numeric.mean():,.2f}", "mean across full timeline"),
                ("Observed range", f"{numeric.min():,.2f} – {numeric.max():,.2f}", "minimum to maximum"),
                ("Data points", f"{len(numeric):,}", "valid numeric samples"),
            ])

        st.markdown('<div class="ax-section">SCENARIO EVENT WINDOWS</div>', unsafe_allow_html=True)
        names = {"SPE": "Solar particle event", "CREW": "Crew wellbeing anomaly",
                 "CABIN": "Cabin environmental anomaly"}
        for key, event in getattr(mm, "EVENTS", {}).items():
            if len(event) >= 5:
                start, finish = max(0, int(event[1])), min(len(df)-1, int(event[4]))
                css = "red" if key == "CABIN" else ""
                st.markdown(
                    f'<div class="ax-event {css}"><b>{html.escape(names.get(key, str(event[0])))}</b>'
                    f'<div class="ax-muted">Samples {start+1:,}–{finish+1:,} · '
                    f'{html.escape(str(df.iloc[start]["phase"]))}</div></div>',
                    unsafe_allow_html=True,
                )
        with st.expander("Inspect mission phase boundaries"):
            phases = df.groupby("phase", sort=False).agg(
                first_sample=("sample", "min"), last_sample=("sample", "max"),
                sample_count=("sample", "count")).reset_index()
            st.dataframe(phases, use_container_width=True, hide_index=True)
        st.caption("These patterns are scripted into synthetic telemetry. They demonstrate trend exploration, not real crew outcomes or causal relationships.")
        return

    crew = st.selectbox("CREW RECORD", crew_options, key="axi_res_crew")
    logs = _read_logs(db_path, crew)
    if logs.empty:
        st.warning(f"No saved check-ins found for {crew} yet. The seven-day monitor is available below, but it needs saved demo records before it can calculate a trend.")
        _render_seven_day_panel(pd.DataFrame(columns=["logged_at"]), crew, "Fatigue")
        st.info("To add records: open **Crew Logs & Records**, choose the same crew member, complete the demo check-in form and select **Save check-in permanently**. Then return here and refresh.")
        return
    logs["logged_at"] = pd.to_datetime(logs["logged_at"], errors="coerce", utc=True)
    logs = logs.dropna(subset=["logged_at"]).sort_values("logged_at")
    if logs.empty:
        st.warning("The saved records do not contain readable timestamps.")
        return

    st.markdown('<div class="ax-section">RECORDED CHECK-IN HISTORY</div>', unsafe_allow_html=True)
    a, b, c = st.columns(3)
    a.metric("Check-ins", len(logs))
    b.metric("First record", logs.logged_at.iloc[0].strftime("%d %b %Y"))
    c.metric("Latest record", logs.logged_at.iloc[-1].strftime("%d %b %Y"))
    options = {
        "Fatigue": ("fatigue", "score / 10"), "Sleep": ("sleep_hours", "hours"),
        "Mood": ("mood", "score / 10"), "Heart rate": ("heart_rate", "bpm"),
        "SpO₂": ("spo2", "%"), "Cabin CO₂": ("co2", "ppm"),
        "Radiation": ("radiation", "illustrative units / h"),
    }
    available = [label for label, (col, _) in options.items() if col in logs.columns]
    if not available:
        st.error("No recognised resilience indicators were found.")
        return
    metric = st.selectbox("Trend indicator", available, key="axi_saved_metric")
    column, unit = options[metric]
    plot = logs[["logged_at", column]].copy()
    plot[column] = pd.to_numeric(plot[column], errors="coerce")
    plot = plot.dropna().reset_index(drop=True)
    _render_premium_chart(plot, column, unit, f"{metric} · saved crew history", x_col="logged_at", date_axis=True)
    if len(plot) >= 2:
        first, latest = float(plot[column].iloc[0]), float(plot[column].iloc[-1])
        change = latest-first
        _stat_cards([
            ("Latest value", f"{latest:.1f} {unit}", "most recent saved check-in"),
            ("Change", f"{change:+.1f} {unit}", "latest minus first record"),
            ("Recorded range", f"{plot[column].min():.1f} – {plot[column].max():.1f}", "minimum to maximum"),
            ("Check-ins", len(plot), "records included in this trend"),
        ])
    else:
        st.caption("Add more check-ins over time to create a meaningful trend.")
    _render_seven_day_panel(logs, crew, metric)
    show = [x for x in ["logged_at", "checkin", "fatigue", "sleep_hours", "mood", "heart_rate", "spo2", "co2", "radiation"] if x in logs]
    st.dataframe(logs[show].sort_values("logged_at", ascending=False), use_container_width=True, hide_index=True)
    st.caption("Saved check-ins are user-entered demonstration records. Trends depend on record frequency and consistent measurement; they are not diagnoses.")


def _make_report(df: pd.DataFrame, mm, mission_name: str, crew: str,
                 scope: str, notes: str) -> str:
    total = len(df)
    if total == 0:
        raise ValueError("The telemetry stream is empty.")
    if scope == "Current replay position":
        last = max(0, min(total - 1, int(st.session_state.get("mm_idx", 0))))
        reviewed = df.iloc[:last+1].copy()
        coverage = f"Replay sample {last+1} of {total}"
    else:
        last = total - 1
        reviewed = df.copy()
        coverage = f"Full scenario · {total} samples"

    phases = reviewed.groupby("phase", sort=False).agg(
        first=("sample", "min"), final=("sample", "max")).reset_index()
    phase_text = "\n".join(
        f"- **{r.phase}** — samples {int(r.first)+1}–{int(r.final)+1}."
        for r in phases.itertuples()
    )
    event_text = []
    for key, event in getattr(mm, "EVENTS", {}).items():
        if len(event) >= 6 and int(event[1]) <= last:
            finish = min(int(event[4]), last)
            state = "resolved in reviewed interval" if int(event[4]) <= last else "not yet resolved in reviewed interval"
            event_text.append(
                f"- **{event[0]}** ({key}) — samples {int(event[1])+1}–{finish+1}; "
                f"peak at sample {int(event[2])+1}; {state}."
            )
    if not event_text:
        event_text = ["- No scripted anomaly window has begun in the reviewed interval."]

    milestone_text = []
    for label, met_s in getattr(mm, "MILESTONES", []):
        try:
            idx = int((df["met_s"] - float(met_s)).abs().idxmin())
            if idx <= last:
                milestone_text.append(f"- {label} — {df.iloc[idx]['met_label']} (sample {idx+1}).")
        except (KeyError, TypeError, ValueError):
            continue
    if not milestone_text:
        milestone_text = ["- No listed milestone reached in the reviewed interval."]

    trend_text = []
    for col in ["fatigue", "sleep", "mood", "heart_rate", "radiation", "co2", "oxygen"]:
        if col in reviewed:
            series = pd.to_numeric(reviewed[col], errors="coerce").dropna()
            if not series.empty:
                trend_text.append(
                    f"- **{col.replace('_', ' ').title()}** — start {series.iloc[0]:.2f}; "
                    f"end {series.iloc[-1]:.2f}; range {series.min():.2f}–{series.max():.2f}."
                )
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    operator_notes = notes.strip() or "No additional operator notes supplied."
    return f"""# ASTRA MISSION DEBRIEF
**Mission:** {mission_name}  
**Crew record label:** {crew}  
**Coverage:** {coverage}  
**Generated:** {now}

> **EDUCATIONAL SIMULATION — FICTIONAL DATA.** This report summarises ASTRA's generated Mars scenario. It is not a real flight, engineering or medical assessment.

## 1. Executive summary
This report reviews {coverage.lower()} of the ASTRA Earth-to-Mars demonstration. It brings together mission progression, scripted scenario events, listed milestones and selected telemetry ranges. It is descriptive and does not infer medical diagnoses, causation or real mission safety.

## 2. Mission progression
{phase_text}

## 3. Milestones reached
{chr(10).join(milestone_text)}

## 4. Scripted events and anomalies
{chr(10).join(event_text)}

## 5. Telemetry review
{chr(10).join(trend_text) if trend_text else "- No numeric telemetry summary available."}

## 6. Operator notes
{operator_notes}

## 7. Data integrity and limitations
- All mission telemetry and event windows are synthetic and fictional.
- Scenario alerts use ASTRA's illustrative prototype rules.
- Thresholds are not validated operational limits.
- Trends describe this generated dataset and do not establish causation.
- This report must not be used for medical decisions, spacecraft operations or engineering certification.

---
**ASTRA // Crew Health & Mission Simulation Console**
"""


def render_mission_debrief(db_path: str | Path, mm, crew_options: list[str], mission_name: str) -> None:
    """Render report builder and downloadable Markdown/TXT mission debrief."""
    _hero(
        "ASTRA / FLIGHT OPERATIONS SUMMARY",
        "Mission Debrief Studio",
        "Transform the mission replay into a structured review of milestones, anomalies, "
        "telemetry trends and operator observations.",
    )
    _render_orbital_satellite()
    try:
        df = _mission_data(mm)
    except Exception as exc:
        st.error(f"Could not load mission telemetry: {exc}")
        return
    _stat_cards([
        ("Telemetry points", f"{len(df):,}", "generated scenario samples"),
        ("Mission phases", int(df.phase.nunique()), "timeline segments"),
        ("Scenario events", len(getattr(mm, "EVENTS", {})), "scripted event windows"),
        ("Milestones", len(getattr(mm, "MILESTONES", [])), "defined mission markers"),
    ])

    with st.form("axi_debrief_form"):
        crew = st.selectbox("Crew record label", crew_options, key="axi_debrief_crew")
        scope = st.radio("Report coverage", ["Full mission scenario", "Current replay position"], horizontal=True)
        notes = st.text_area(
            "Flight director / operator notes",
            placeholder="Record scenario observations, decisions discussed, questions for review, or lessons learned…",
            max_chars=2000,
            help="Use fictional demonstration notes only. Do not enter real sensitive health information.",
        )
        submitted = st.form_submit_button("✦ GENERATE MISSION DEBRIEF", type="primary", use_container_width=True)

    if submitted:
        try:
            st.session_state["axi_debrief_report"] = _make_report(df, mm, mission_name, crew, scope, notes)
            st.session_state["axi_debrief_created"] = datetime.now(timezone.utc).isoformat()
        except Exception as exc:
            st.error(f"Debrief generation failed: {exc}")
            return

    report = st.session_state.get("axi_debrief_report")
    if report:
        st.markdown('<div class="ax-section">GENERATED REPORT · REVIEW BEFORE SHARING</div>', unsafe_allow_html=True)
        st.success("Mission debrief generated successfully.")
        st.markdown(report)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
        plain = report.replace("**", "").replace("## ", "").replace("# ", "").replace("> ", "")
        x, y = st.columns(2)
        x.download_button("⬇ DOWNLOAD · MARKDOWN", report.encode("utf-8"),
                          f"ASTRA_mission_debrief_{stamp}.md", "text/markdown", use_container_width=True)
        y.download_button("⬇ DOWNLOAD · TEXT", plain.encode("utf-8"),
                          f"ASTRA_mission_debrief_{stamp}.txt", "text/plain", use_container_width=True)
        st.caption("Generated from existing synthetic telemetry and scripted event definitions. No source records are modified.")
    else:
        st.markdown(
            '<div class="ax-card"><b>REPORT BUILDER READY</b><p class="ax-muted">'
            'Choose the report scope, add optional operator notes, and generate a downloadable mission summary. '
            'The full-scenario report includes all existing milestones and scripted event windows.</p></div>',
            unsafe_allow_html=True,
        )
