# 🚑 VitalRoute — Smart Emergency Ambulance Destination Routing

> **Confidence-aware emergency routing that finds the fastest hospital with open beds and ready specialists—not just the physically closest one.**

Developed by **TEAM RAPS** · Aligned with **UN SDG 3 (Good Health and Well-Being)**  
Includes full presentation slide deck in [`docs/VitalRoute_AI_FORGE_EXPO.pptx`](docs/VitalRoute_AI_FORGE_EXPO.pptx).

---

## 💡 The Big Idea

When someone suffers a heart attack, stroke, or severe injury, every minute counts. 

Today, ambulances usually rush to the **closest hospital**. But too often:
- The emergency room is overcrowded with long queues.
- The hospital's CT scanner is broken or the cath lab doctors are off-duty.
- The ambulance gets stuck waiting outside for an open bed (**ambulance ramping**), losing crucial time.

**VitalRoute solves this.** Instead of just measuring driving distance, it calculates the **Total Time to Definitive Care (TTDC)**:

$$\text{Total Time} = \text{Driving Time} + \text{Emergency Room Wait Time} + \text{Specialist Preparation Time}$$

It directs the ambulance to the hospital where the patient will **actually receive treatment fastest**, and reserves a resuscitation bay before the ambulance arrives.

---

## ⚡ How It Works (3 Connected Roles)

```
       [ 🩺 PARAMEDIC ]                   [ 🧭 AMBULANCE DRIVER ]                  [ 🏥 HOSPITAL ER ]
   Enters vitals & injury               Receives live turn-by-turn             Audible alert rings on PC,
  in rapid mobile interface            GPS navigation with Leaflet map         nurse confirms and reserves bed
             │                                     ▲                                       ▲
             ▼                                     │                                       │
     ─────────────────────────────── VITALROUTE CORE ENGINE ─────────────────────────────────
                            • Freshness Decay & Offline Forecaster
                            • Total Time to Definitive Care (TTDC)
                            • Two-Way Live Digital Handshake
```

### 1. 🩺 Paramedic Field App (`/?role=paramedic`)
* Rapid physiological vitals entry (Respiration, SpO2, Blood Pressure, Heart Rate, AVPU, Temperature).
* Automatic calculation of clinical risk (NEWS2 score).
* Selects injury category (Trauma, Stroke, Heart Attack, Burns, etc.) or free-text clinical notes.
* One-click dispatch calculation that instantly finds the optimal hospital.

### 2. 🧭 Ambulance Driver App (`/?role=driver`)
* Automatically activates the moment the paramedic calculates the route.
* Live vehicle GPS location and high-contrast Leaflet route map.
* Cardinal compass directions (e.g. *“Proceed North to Apollo Trauma Centre Emergency Bay”*).
* One-tap button to launch live turn-by-turn navigation in **Google Maps**.

### 3. 🏥 Hospital ER Triage Software (`VitalRoute_Hospital_Triage.exe`)
* Standalone desktop application for emergency department charge nurses and triage staff.
* Plays an audible chime when an incoming ambulance transmits a pre-alert.
* Displays patient vitals, clinical summary, and suggested emergency acuity (ESI).
* **One-click Bay Reservation**: The nurse clicks `[✅ Acknowledge & Reserve Bay]`, which immediately alerts the ambulance crew that a bed is ready.

---

## 🔬 Novelty & Competitive Benchmark (First-of-its-Kind Solution)

While **ambulance offload delays (ramping)** and **emergency department overcrowding** are well-documented healthcare crises worldwide, existing systems (traditional Computer-Aided Dispatch, regional divert portals like EMResource, and generic mapping apps) only treat surface symptoms or route ambulances purely by physical road distance.

**VitalRoute is the first platform to systematically unify telemetry freshness decay, multi-factor clinical readiness, offline Bayesian forecasting, and two-way pre-arrival bay reservations into a single cohesive architecture:**

| Dimension | Standard GPS / Google Maps | Regional Divert Portals (EMResource, ReddiNet) | **VitalRoute (TEAM RAPS)** |
| :--- | :--- | :--- | :--- |
| **Optimization Target** | Driving time ($T_{\text{drive}}$) only | Coarse manual open/divert flags | **Total Time to Definitive Care ($\text{TTDC} = T_{\text{drive}} + T_{\text{offload}} + T_{\text{readiness}}$)** |
| **"Phantom Bed" Elimination** | ❌ Completely ignored | ⚠️ Manual toggles often stale by 30–90+ minutes | **✅ Mathematical Freshness Decay $F(t) = e^{-\lambda \Delta t}$ with uncertainty penalties** |
| **Clinical Resource Readiness** | ❌ Unchecked | ⚠️ Static phone registry | **✅ Live specialist tracking (Cath Lab, CT Scanner, on-call vs scrubbed-in)** |
| **Offline Reliability (Loss of Signal)** | ❌ Stops working | ❌ Cloud-dependent website | **✅ Local Bayesian model forecasting arrival capacity from diurnal rhythms** |
| **Hospital Pre-Arrival Handshake** | ❌ None (crew arrives unannounced) | ⚠️ Clunky radio/phone calls | **✅ 2-way closed-loop digital handshake reserving ED bays before arrival** |
| **Clinical Role Separation** | ❌ None | ❌ One-size-fits-all forms | **✅ Paramedic (rapid NEWS2 vitals) vs Hospital Nurse (Anticipated ESI scoring)** |

---

## 🌟 Key Innovations

1. **No "Phantom Beds" (Freshness Decay)**: Hospital bed reports decay exponentially over time ($F(t) = e^{-\lambda \Delta t}$). Outdated numbers are mathematically penalized so ambulances are never routed to hospitals based on stale capacity claims.
2. **Offline-Ready Probability Forecasting**: If cell towers fail, VitalRoute uses an embedded local mathematical model based on 24-hour diurnal hospital admission rhythms to estimate arrival bed probability.
3. **Closed-Loop Digital Handshake**: Replaces chaotic phone calls and radio tag with instant digital confirmations. If a hospital suddenly fills up, it triggers an instant diversion *before* the ambulance gets stuck.
4. **Transparent "Why Inspector"**: Clearly tells the medical crew why a hospital was chosen (e.g. *"Apollo preferred over Max: although 3 min farther by road, Max has a 30-min offload delay; net clinical saving of 27 minutes"*).

---

## 📁 Repository Structure

```
vitalroute/
├── backend/                  # FastAPI decision engine, mathematical models, SQLite storage
│   ├── app/
│   │   ├── main.py           # REST endpoints and real-time WebSockets
│   │   ├── database.py       # Persistent SQLite database & audit logs
│   │   ├── models.py         # Clinical data structures and schemas
│   │   ├── services/
│   │   │   ├── clinical.py   # NEWS2 scoring and ESI anticipation
│   │   │   ├── confidence.py # Freshness decay and offline probability forecaster
│   │   │   ├── ttdc.py       # Total Time to Definitive Care optimizer
│   │   │   └── simulation.py # Background multi-hospital surge simulator
│   │   └── ws.py             # Concurrent-safe WebSocket manager
│   └── tests/                # 35 automated unit and integration tests
├── software/                 # Hospital Emergency Department desktop application
│   └── windows_app/
│       ├── main_window.py    # PySide6 / Qt desktop interface
│       ├── api_client.py     # Asynchronous API and WebSocket client
│       └── styles.py         # Dark medical theme stylesheet
├── mobile/                   # Paramedic and Ambulance Driver field application
│   ├── index.html            # Role-segregated field interface
│   ├── mobile.js             # Vitals engine, Leaflet mapping, and sync logic
│   ├── mobile.css            # High-contrast emergency UI styling
│   ├── leaflet.js            # Offline-ready interactive map library
│   └── leaflet.css           # Map styling
├── docs/
│   └── VitalRoute_AI_FORGE_EXPO.pptx # Official Presentation Slide Deck
├── LICENSE.md                # Strict proprietary intellectual property license (TEAM RAPS)
├── run_server.bat            # One-click backend server launcher
├── run_ambulance_mobile_app.bat # One-click browser field app launcher
└── README.md
```

---

## 🚀 Quick Start Guide

### Prerequisites
- Python 3.10+ (Python 3.12 or 3.14 recommended)
- A modern web browser (Chrome, Edge, Firefox)

### 1. Install Dependencies
```bash
pip install -r backend/requirements.txt
# Or directly:
pip install fastapi uvicorn pydantic pytest PySide6
```

### 2. Start the Decision Engine Backend
```bash
python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
```
*(Or double-click `run_server.bat` on Windows)*

### 3. Open the Mobile Field Apps
Open your browser to:
- **Paramedic Console**: `http://localhost:8000/?role=paramedic`
- **Ambulance Driver Console**: `http://localhost:8000/?role=driver`

### 4. Run the Hospital Desktop Software
```bash
python software/windows_app/main_window.py
```
*(Or launch the compiled standalone `VitalRoute_Hospital_Triage.exe`)*

### 5. Run the Automated Tests
```bash
python -m pytest backend/tests/ -v
```
All **35/35 tests** will execute and pass cleanly.

---

## 📊 Presentation Slide Deck

The full project presentation is included directly in this repository:
👉 [**`docs/VitalRoute_AI_FORGE_EXPO.pptx`**](docs/VitalRoute_AI_FORGE_EXPO.pptx)

---

## 🔒 Proprietary License

Copyright (C) 2026 **TEAM RAPS**. All Rights Reserved.

The VitalRoute concept, algorithms (TTDC optimization, Capacity-Confidence Engine, Two-Way Handshake), source code, designs, and documentation are the **exclusive proprietary intellectual property of the team members of TEAM RAPS**. 

Unauthorized copying, distribution, modification, reverse engineering, commercialization, or public reuse of this work is strictly prohibited. See [`LICENSE.md`](LICENSE.md) for full terms.
