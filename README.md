# Dinath-nexus
 COSMIC-NEXUS · Astronaut Health & Cabin Simulation

A lightweight, zero-dependency, standalone **HTML, CSS & JavaScript** application.

> **Zero Complex Folders & Zero Build Steps:** Everything is simplified into **4 clean root files**.
> You can run the application **directly by double-clicking `index.html` in your file explorer** or by running `python server.py`.

---

## 🚀 How to Run the App

### Method 1: Just Double-Click `index.html` (No Server Needed!)
Open your file manager, navigate to this folder, and double-click `index.html` (or drag it into Chrome, Edge, Safari, or Firefox).
- Works 100% out-of-the-box via `file:///`.
- No Node.js, no npm, no Vite, and no web server required!

### Method 2: Run with Python (Optional)
If you prefer running a local HTTP server:
```bash
python server.py
```
This automatically launches at `http://127.0.0.1:8000/` and opens your browser.

---

## 📁 Super Clean 4-File Structure

```text
├── index.html   # Main HTML5 shell (links style.css and app.js)
├── style.css    # All styling: design tokens, layout, tiles, gauges, charts, drawer
├── app.js       # Complete simulation, alert rules, health scoring & UI controller
├── server.py    # Optional zero-dependency Python local server
└── README.md    # Documentation & guide
```

---

## 🛠 Easy Guide: How to Add New Things in `app.js`

`app.js` is clearly organized into 15 numbered sections with a Table of Contents at the top:

### 1. Adding a New Sensor Metric
Go to **Section 1 (`METRICS` array)** near line 38 of `app.js` and add a new sensor definition:
```javascript
health({
  id: 'core_temp',
  label: 'Core body temperature',
  unit: '°C',
  section: 'skin',
  plausible: { min: 32, max: 43 },
  nominal: 37.0,
  noise: 0.1,
  decimals: 2,
  step: 0.01,
  circadian: { amplitude: 0.3, peakHour: 18 }
}),
```

### 2. Adding a New Alert Threshold
Go to **Section 2 (`THRESHOLDS` array)** near line 118 of `app.js` and add a rule:
```javascript
rule('core_temp', 'above', 38.5, 'warning', 3),
rule('core_temp', 'above', 39.5, 'critical', 1, { urgent: true }),
```

### 3. Adding a New Logged Symptom
Go to **Section 3 (`SYMPTOMS` array)** near line 215 of `app.js` and add a symptom:
```javascript
{ id: 'muscle_cramps', label: 'Muscle cramps', serious: false },
```

### 4. Adding a New Chart
Go to **Section 14 (`HEALTH_CHARTS` or `ENV_CHARTS` array)** near line 785 of `app.js` and add:
```javascript
['Core Body Temperature', ['core_temp']],
```

---

## 🌟 Full Feature Breakdown (100% Preserved)

- **32 Simulated Metrics:** 18 astronaut physiological health metrics (Heart rate, PPG pulse, ECG RR/PR/QRS/QTc, SpO2, HRV RMSSD, Respiratory rate, Tidal volume, Skin temps, BP, Signal quality) and 14 cabin environment metrics (O2, CO2, Pressure, Temp, Humidity, Radiation count/dose/cumulative, PM2.5/PM10, CO, NH3, HCHO).
- **Simulation Clock:** Speeds 1×, 60×, 300×, 900×, 3600×, pause/resume, step, jump to time/timezone (UTC, Houston, Florida, Cologne, Tsukuba, Colombo).
- **Orbital Health Score Gauge:** Transparent weighted 0–100 score with circular animated ring and full breakdown table.
- **Sensor Fault Injection:** Stuck values, out-of-range, missing data, stale data, and manual test values in the Simulation Controls Drawer.
- **Alert Engine:** Multi-tier thresholds (Caution, Warning, Critical), emergency procedures, Acknowledge, Action Taken, and Sensor Checked re-check countdown.
- **Astronaut Logs & Reminders:** Scheduled 07:00 and 19:00 mission reminders, self-reporting form, snooze, and browser notifications.
- **Data Export:** Instant download of State JSON, Logs CSV, and 7-day Multi-Sensor CSV.

---

## 🛡 Disclaimer
COSMIC-NEXUS is a hackathon simulation prototype. It is not medical software, uses no real sensors, and provides no diagnoses. All threshold rules are placeholders requiring expert review.

