import { useEffect, useState, useRef } from "react";
import "./App.css";

interface Vitals {
  respiration_rate: number;
  spo2: number;
  systolic_bp: number;
  heart_rate: number;
  consciousness: string;
  temperature: number;
}

interface Patient {
  incident_id: string;
  news2: number;
  news2_risk_band: string;
  care_tag: string;
  emergency_description?: string;
  custom_requirements?: string[];
  paramedic_notes?: string;
  vitals: Vitals;
}

interface Handshake {
  id: string;
  ambulance_id: string;
  hospital_id: string;
  eta_min: number;
  status: string;
  created_ts: number;
  anticipated_esi?: number;
  constraint_detail?: string;
  patient: Patient;
}

interface Hospital {
  id: string;
  name: string;
  beds_available: number;
  icu_beds_available: number;
  active_boarders: number;
  specialist_status: string;
  ct_operational: boolean;
  freshness: number;
  staleness_minutes: number;
  confidence_adjusted_beds: number;
  stale?: boolean;
  capacity_probability?: number;
  icu_probability?: number;
  forecast_mode?: string;
  forecast_confidence_band?: string;
  forecast_disclaimer?: string;
}

export default function App() {
  const [serverUrl, setServerUrl] = useState("http://localhost:8000");
  const [hospitalId, setHospitalId] = useState("H1");
  const [hospitals, setHospitals] = useState<Hospital[]>([]);
  const [currentHospital, setCurrentHospital] = useState<Hospital | null>(null);
  const [handshakes, setHandshakes] = useState<Handshake[]>([]);
  const [selectedHs, setSelectedHs] = useState<Handshake | null>(null);

  // Live Clock
  const [clock, setClock] = useState({ local: "", utc: "" });

  // Form State for capacity
  const [beds, setBeds] = useState(4);
  const [icuBeds, setIcuBeds] = useState(1);
  const [boarders, setBoarders] = useState(2);
  const [specialist, setSpecialist] = useState("ACTIVE");
  const [ctOp, setCtOp] = useState(true);

  // Triage Action State
  const [chosenEsi, setChosenEsi] = useState<number>(2);
  const [wsConnected, setWsConnected] = useState(false);
  const [audioEnabled, setAudioEnabled] = useState(true);

  // Modals
  const [showDivertModal, setShowDivertModal] = useState(false);
  const [divertReason, setDivertReason] = useState("ED at critical resuscitation surge");
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [showAboutModal, setShowAboutModal] = useState(false);
  const [tempServerUrl, setTempServerUrl] = useState("http://localhost:8000");

  const wsRef = useRef<WebSocket | null>(null);

  // Live clock interval
  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      setClock({
        local: now.toLocaleTimeString([], { hour12: false }),
        utc: now.toISOString().slice(11, 19) + " UTC",
      });
    };
    updateTime();
    const timer = setInterval(updateTime, 1000);
    return () => clearInterval(timer);
  }, []);

  // Keyboard shortcut listener
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setShowDivertModal(false);
        setShowSettingsModal(false);
        setShowAboutModal(false);
      } else if (e.key === "Enter" && !showDivertModal && !showSettingsModal && !showAboutModal) {
        if (selectedHs && selectedHs.status === "PENDING_RESPONSE") {
          handleConfirmHandshake();
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [selectedHs, chosenEsi, showDivertModal, showSettingsModal, showAboutModal]);

  // Clinical alert chime
  const playAlertSound = () => {
    if (!audioEnabled) return;
    try {
      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
      if (!AudioCtx) return;
      const ctx = new AudioCtx();
      
      const playTone = (freq: number, start: number, dur: number) => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = "sine";
        osc.frequency.setValueAtTime(freq, ctx.currentTime + start);
        gain.gain.setValueAtTime(0.18, ctx.currentTime + start);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + start + dur);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(ctx.currentTime + start);
        osc.stop(ctx.currentTime + start + dur);
      };

      playTone(880, 0, 0.14);
      playTone(1175, 0.15, 0.22);
    } catch (e) {
      console.warn("Audio chime error:", e);
    }
  };

  // Fetch Hospitals list
  const loadHospitals = async () => {
    try {
      const res = await fetch(`${serverUrl}/api/hospitals`);
      if (res.ok) {
        const data = await res.json();
        setHospitals(data);
      }
    } catch (e) {
      // Backend not running
    }
  };

  // Fetch Current Hospital detail
  const loadHospitalData = async (hId: string) => {
    try {
      const res = await fetch(`${serverUrl}/api/hospitals/${hId}`);
      if (res.ok) {
        const h: Hospital = await res.json();
        setCurrentHospital(h);
        setBeds(h.beds_available);
        setIcuBeds(h.icu_beds_available);
        setBoarders(h.active_boarders);
        setSpecialist(h.specialist_status);
        setCtOp(h.ct_operational);
      }
    } catch (e) {
      // Backend not running
    }
  };

  // Fetch Handshakes for this hospital
  const loadHandshakes = async (hId: string) => {
    try {
      const res = await fetch(`${serverUrl}/api/handshakes/hospital/${hId}`);
      if (res.ok) {
        const list: Handshake[] = await res.json();
        setHandshakes(list);
        if (list.length > 0 && !selectedHs) {
          setSelectedHs(list[0]);
          setChosenEsi(list[0].anticipated_esi || 2);
        }
      }
    } catch (e) {
      // Backend not running
    }
  };

  // Setup WebSocket
  const setupWebSocket = (hId: string) => {
    if (wsRef.current) {
      wsRef.current.close();
    }

    const host = serverUrl.replace(/^http:\/\//, "").replace(/^https:\/\//, "");
    const wsProto = serverUrl.startsWith("https") ? "wss:" : "ws:";
    const url = `${wsProto}//${host}/ws/hospital:${hId}`;

    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => setWsConnected(true);
      ws.onclose = () => {
        setWsConnected(false);
        setTimeout(() => setupWebSocket(hId), 4000);
      };
      ws.onerror = () => setWsConnected(false);

      ws.onmessage = (evt) => {
        try {
          const msg = JSON.parse(evt.data);
          if (msg.type === "handshake_request") {
            playAlertSound();
            loadHandshakes(hId);
          } else if (msg.type === "hospital_update") {
            if (msg.hospital?.id === hId) {
              setCurrentHospital(msg.hospital);
            }
          } else if (msg.type === "handshake_ack" || msg.type === "handshake_timeout") {
            loadHandshakes(hId);
          }
        } catch (err) {
          console.error("WS message error:", err);
        }
      };
    } catch (err) {
      setWsConnected(false);
    }
  };

  useEffect(() => {
    loadHospitals();
    loadHospitalData(hospitalId);
    loadHandshakes(hospitalId);
    setupWebSocket(hospitalId);

    const interval = setInterval(() => {
      loadHospitalData(hospitalId);
      loadHandshakes(hospitalId);
    }, 5000);

    return () => {
      clearInterval(interval);
      if (wsRef.current) wsRef.current.close();
    };
  }, [serverUrl, hospitalId]);

  // Update capacity action
  const handleUpdateCapacity = async () => {
    try {
      const payload = {
        hospital_id: hospitalId,
        beds_available: beds,
        icu_beds_available: icuBeds,
        active_boarders: boarders,
        specialist_status: specialist,
        ct_operational: ctOp,
        refresh_timestamp: true,
      };
      const res = await fetch(`${serverUrl}/api/hospitals/event`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        const data = await res.json();
        setCurrentHospital(data);
      }
    } catch (e) {
      // Local fallback for offline simulation
      if (currentHospital) {
        setCurrentHospital({
          ...currentHospital,
          beds_available: beds,
          icu_beds_available: icuBeds,
          active_boarders: boarders,
          specialist_status: specialist,
          ct_operational: ctOp,
        });
      }
    }
  };

  // Confirm Handshake
  const handleConfirmHandshake = async () => {
    if (!selectedHs) return;
    try {
      const res = await fetch(
        `${serverUrl}/api/handshake/${selectedHs.id}/ack?confirm=true&anticipated_esi=${chosenEsi}`,
        { method: "POST" }
      );
      if (res.ok) {
        loadHandshakes(hospitalId);
        return;
      }
    } catch (e) {
      // Fallback
    }

    // Local state update if offline
    setHandshakes((prev) =>
      prev.map((h) =>
        h.id === selectedHs.id ? { ...h, status: "CONFIRMED", anticipated_esi: chosenEsi } : h
      )
    );
    setSelectedHs((prev) => (prev ? { ...prev, status: "CONFIRMED", anticipated_esi: chosenEsi } : null));
  };

  // Divert Handshake
  const handleDivertHandshake = async () => {
    if (!selectedHs) return;
    try {
      const res = await fetch(
        `${serverUrl}/api/handshake/${selectedHs.id}/ack?confirm=false&constraint=${encodeURIComponent(divertReason)}`,
        { method: "POST" }
      );
      if (res.ok) {
        setShowDivertModal(false);
        loadHandshakes(hospitalId);
        return;
      }
    } catch (e) {
      // Fallback
    }

    // Local state update if offline
    setHandshakes((prev) =>
      prev.map((h) =>
        h.id === selectedHs.id
          ? { ...h, status: "CONSTRAINED_REROUTE_REQUESTED", constraint_detail: divertReason }
          : h
      )
    );
    setSelectedHs((prev) =>
      prev ? { ...prev, status: "CONSTRAINED_REROUTE_REQUESTED", constraint_detail: divertReason } : null
    );
    setShowDivertModal(false);
  };

  // Simulate Inbound Case (works online or offline)
  const handleSimulateCase = async (type: "STEMI" | "TRAUMA") => {
    const isStemi = type === "STEMI";
    const simPayload = {
      ambulance_id: isStemi ? "AMB-204" : "AMB-108",
      latitude: 28.618,
      longitude: 77.215,
      vitals: isStemi
        ? { respiration_rate: 22, spo2: 95, systolic_bp: 145, heart_rate: 110, consciousness: "A", temperature: 37.1 }
        : { respiration_rate: 26, spo2: 91, systolic_bp: 92, heart_rate: 124, consciousness: "V", temperature: 36.4 },
      care_tag: isStemi ? "STEMI" : "TRAUMA",
      emergency_description: isStemi
        ? "62M acute substernal chest crushing pressure radiating to jaw, diaphoretic, 12-lead ECG confirms ST elevation."
        : "29M high-velocity motorcycle collision; open right femur fracture, paradoxical right flail chest, pale and cool.",
      custom_requirements: isStemi ? ["Cath Lab"] : ["Trauma", "ICU"],
      paramedic_notes: isStemi
        ? "Aspirin 325mg PO, sublingual nitroglycerin x1, 2L O2 NC"
        : "C-collar secured, bilateral large-bore IVs placed, 15L O2 NRB, pelvic binder applied",
    };

    if (wsConnected) {
      try {
        await fetch(`${serverUrl}/api/handshake?hospital_id=${hospitalId}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(simPayload),
        });
        loadHandshakes(hospitalId);
        playAlertSound();
        return;
      } catch (e) {
        // Fallback to local simulation
      }
    }

    // Local simulation
    const localHs: Handshake = {
      id: "SIM-" + Math.floor(1000 + Math.random() * 9000),
      ambulance_id: simPayload.ambulance_id,
      hospital_id: hospitalId,
      eta_min: Math.floor(6 + Math.random() * 8),
      status: "PENDING_RESPONSE",
      created_ts: Math.floor(Date.now() / 1000),
      patient: {
        incident_id: "INC-" + Math.floor(100000 + Math.random() * 900000),
        news2: isStemi ? 5 : 9,
        news2_risk_band: isStemi ? "MEDIUM" : "HIGH",
        care_tag: simPayload.care_tag,
        emergency_description: simPayload.emergency_description,
        custom_requirements: simPayload.custom_requirements,
        paramedic_notes: simPayload.paramedic_notes,
        vitals: simPayload.vitals,
      },
    };
    setHandshakes((prev) => [localHs, ...prev]);
    setSelectedHs(localHs);
    setChosenEsi(isStemi ? 2 : 1);
    playAlertSound();
  };

  // Export CSV
  const handleExportCSV = () => {
    if (handshakes.length === 0) {
      alert("No handshakes to export.");
      return;
    }
    const headers = [
      "ID",
      "Timestamp",
      "Ambulance",
      "Status",
      "ETA_Min",
      "Category",
      "Description",
      "NEWS2",
      "ESI",
      "Constraint",
    ];
    const rows = handshakes.map((h) => [
      h.id,
      new Date(h.created_ts * 1000).toISOString(),
      h.ambulance_id,
      h.status,
      h.eta_min,
      h.patient.care_tag,
      `"${(h.patient.emergency_description || "").replace(/"/g, '""')}"`,
      h.patient.news2,
      h.anticipated_esi || "",
      `"${(h.constraint_detail || "").replace(/"/g, '""')}"`,
    ]);

    const csvContent =
      "data:text/csv;charset=utf-8," +
      [headers.join(","), ...rows.map((e) => e.join(","))].join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `VitalRoute_Handshakes_${hospitalId}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // Freshness calculation percentage
  const isTelemetryLive = wsConnected && currentHospital !== null;
  const freshnessPct = isTelemetryLive
    ? Math.max(0, Math.min(100, Math.round((currentHospital?.freshness ?? 0.8) * 100)))
    : 0;
  const freshnessColor = freshnessPct >= 65 ? "#10b981" : freshnessPct >= 35 ? "#f59e0b" : "#ef4444";

  // Uncertainty badge text & color (strictly NEVER "LIVE" if disconnected)
  const uncertaintyBadge = !isTelemetryLive
    ? "OFFLINE"
    : currentHospital?.forecast_confidence_band ?? "LIVE";
  const uncertaintyClass = !isTelemetryLive ? "offline" : uncertaintyBadge.toLowerCase();

  return (
    <div className="app-wrapper">
      {/* ====================================================================
          1. Redesigned Two-Tier Application Shell
          ==================================================================== */}
      <header className="app-shell-header">
        {/* Tier 1: Primary Brand, Facility, Connection Pill, Clock */}
        <div className="shell-primary-bar">
          <div className="shell-brand">
            <span className="shell-brand-icon">🏥</span>
            <div className="shell-brand-titles">
              <span className="shell-brand-name">VitalRoute</span>
              <span className="shell-brand-role">Receiving Triage HUD</span>
            </div>
          </div>

          <div className="shell-facility-wrap">
            <span>Facility:</span>
            <select
              className="shell-facility-select"
              value={hospitalId}
              onChange={(e) => {
                setHospitalId(e.target.value);
                setSelectedHs(null);
              }}
            >
              {hospitals.length > 0 ? (
                hospitals.map((h) => (
                  <option key={h.id} value={h.id}>
                    {h.id} — {h.name}
                  </option>
                ))
              ) : (
                <option value="H1">H1 — All India Institute of Medical Sciences (AIIMS)</option>
              )}
            </select>
          </div>

          <div className="shell-status-area">
            <div className={`shell-conn-pill ${wsConnected ? "connected" : "disconnected"}`}>
              <span className="dot"></span>
              <span>{wsConnected ? "LIVE TELEMETRY (PORT 8000)" : "OFFLINE CACHE"}</span>
              {!wsConnected && (
                <button
                  type="button"
                  className="btn-reconnect"
                  onClick={() => {
                    loadHospitalData(hospitalId);
                    setupWebSocket(hospitalId);
                  }}
                >
                  Retry
                </button>
              )}
            </div>

            <div className="shell-clock">
              <span className="clock-primary">{clock.local}</span>
              <span>{clock.utc}</span>
            </div>
          </div>
        </div>

        {/* Tier 2: Secondary Action Toolbar & Ward Quick Stats */}
        <div className="shell-action-toolbar">
          <div className="toolbar-stats">
            <span className="toolbar-stat-item">
              Acute Beds: <strong>{beds}</strong>
            </span>
            <span className="toolbar-stat-item">
              ICU: <strong>{icuBeds}</strong>
            </span>
            <span className="toolbar-stat-item">
              Boarding Queue: <strong>{boarders}</strong>
            </span>
            <span className="toolbar-stat-item">
              Inbound Cases: <strong>{handshakes.length}</strong>
            </span>
          </div>

          <div className="toolbar-actions">
            <button
              className="btn-tool btn-tool-primary"
              onClick={() => handleSimulateCase("STEMI")}
              title="Simulate an incoming ambulance case for demonstration"
            >
              ⚡ Demo Inbound Case
            </button>
            <button className="btn-tool" onClick={() => loadHandshakes(hospitalId)}>
              🔄 Refresh
            </button>
            <button className="btn-tool" onClick={handleExportCSV}>
              📁 Export CSV
            </button>
            <button className="btn-tool" onClick={() => setShowSettingsModal(true)}>
              ⚙ Settings
            </button>
            <button className="btn-tool" onClick={() => setShowAboutModal(true)}>
              ℹ About
            </button>
            <label style={{ display: "flex", alignItems: "center", gap: "5px", color: "var(--text-muted)", fontSize: "0.75rem", cursor: "pointer", marginLeft: "4px" }}>
              <input
                type="checkbox"
                checked={audioEnabled}
                onChange={(e) => setAudioEnabled(e.target.checked)}
              />
              <span>🔔 Chime</span>
            </label>
          </div>
        </div>
      </header>

      {/* ====================================================================
          2. Main Workspace Layout
          ==================================================================== */}
      <div className="main-content-layout">
        {/* Left Column: Department Capacity & Coherent Forecasting Box */}
        <aside className="left-controls-col">
          {/* Card 1: Verified Department Capacity */}
          <section className="hud-section">
            <div className="hud-section-header">
              <span>Department Capacity</span>
              <span className="tag">VERIFIED INPUT</span>
            </div>

            <div className="control-field">
              <label className="control-label">
                <span>Acute Resuscitation Beds:</span>
                <span className="note">Available</span>
              </label>
              <input
                type="number"
                className="control-input"
                min={0}
                max={100}
                value={beds}
                onChange={(e) => setBeds(parseInt(e.target.value) || 0)}
              />
            </div>

            <div className="control-field">
              <label className="control-label">
                <span>Critical / ICU Beds:</span>
                <span className="note">Available</span>
              </label>
              <input
                type="number"
                className="control-input"
                min={0}
                max={50}
                value={icuBeds}
                onChange={(e) => setIcuBeds(parseInt(e.target.value) || 0)}
              />
            </div>

            <div className="control-field">
              <label className="control-label">
                <span>Active ED Boarders:</span>
                <span className="note">Queue</span>
              </label>
              <input
                type="number"
                className="control-input"
                min={0}
                max={100}
                value={boarders}
                onChange={(e) => setBoarders(parseInt(e.target.value) || 0)}
              />
            </div>

            <div className="control-field">
              <label className="control-label">
                <span>Specialist Team:</span>
              </label>
              <select
                className="control-input"
                value={specialist}
                onChange={(e) => setSpecialist(e.target.value)}
              >
                <option value="ACTIVE">ACTIVE (In-House Immediate)</option>
                <option value="ON_CALL">ON_CALL (15-20 Min Response)</option>
                <option value="UNAVAILABLE">UNAVAILABLE (Diverting)</option>
              </select>
            </div>

            <label className="control-checkbox-row">
              <input
                type="checkbox"
                checked={ctOp}
                onChange={(e) => setCtOp(e.target.checked)}
              />
              <span>CT Scanner Operational</span>
            </label>

            <button className="btn-commit-capacity" onClick={handleUpdateCapacity}>
              💾 Commit Capacity Update
            </button>
          </section>

          {/* Card 2: Coherent Telemetry & Forecasting Section */}
          <section className="hud-section">
            <div className="hud-section-header">
              <span>Telemetry & Forecasting</span>
              <span className="tag">PILLAR 1</span>
            </div>

            <div className="telemetry-metrics-stack">
              <div className="telemetry-metric-row">
                <span>Telemetry Freshness:</span>
                <strong style={{ color: freshnessColor }}>
                  {isTelemetryLive ? `${(currentHospital?.freshness ?? 0.8).toFixed(2)} (${freshnessPct}%)` : "0.00 (Offline)"}
                </strong>
              </div>
              <div className="progress-track-sm">
                <div
                  className="progress-fill-sm"
                  style={{ width: `${freshnessPct}%`, backgroundColor: freshnessColor }}
                ></div>
              </div>

              <div className="telemetry-metric-row">
                <span>Telemetry Age:</span>
                <strong>
                  {isTelemetryLive && currentHospital?.staleness_minutes !== undefined
                    ? `${currentHospital.staleness_minutes.toFixed(1)} min ago`
                    : "Link Inactive"}
                </strong>
              </div>

              <div className="telemetry-metric-row">
                <span>Confidence-Adjusted Beds:</span>
                <strong>
                  {isTelemetryLive && currentHospital?.confidence_adjusted_beds !== undefined
                    ? currentHospital.confidence_adjusted_beds.toFixed(1)
                    : "--"}
                </strong>
              </div>

              <div className="telemetry-metric-row">
                <span>Predicted Arrival Capacity (P≥1):</span>
                <strong
                  style={{
                    color:
                      isTelemetryLive && (currentHospital?.capacity_probability ?? 0.8) >= 0.7
                        ? "#38bdf8"
                        : "#f59e0b",
                  }}
                >
                  {isTelemetryLive && currentHospital?.capacity_probability !== undefined
                    ? `${Math.round(currentHospital.capacity_probability * 100)}%`
                    : "-- (Engine Offline)"}
                </strong>
              </div>

              <div className="telemetry-metric-row">
                <span>Predicted ICU Capacity:</span>
                <strong
                  style={{
                    color:
                      isTelemetryLive && (currentHospital?.icu_probability ?? 0.5) >= 0.6
                        ? "#38bdf8"
                        : "#f59e0b",
                  }}
                >
                  {isTelemetryLive && currentHospital?.icu_probability !== undefined
                    ? `${Math.round(currentHospital.icu_probability * 100)}%`
                    : "--"}
                </strong>
              </div>

              <div className="telemetry-metric-row">
                <span>Uncertainty Rating:</span>
                <span className={`badge-uncertainty ${uncertaintyClass}`}>
                  {uncertaintyBadge}
                </span>
              </div>

              {!isTelemetryLive ? (
                <div className="callout-box info">
                  <strong>ℹ Local Offline Shell:</strong> Decision core sidecar not connected. Run via <code>launch_vitalroute_system.bat</code> to enable live mathematical TTDC optimization and real-time fleet synchronization.
                </div>
              ) : currentHospital?.stale || currentHospital?.forecast_mode === "OFFLINE_PROBABILISTIC" ? (
                <div className="callout-box">
                  <strong>⚠️ Telemetry Stale:</strong> Inbound routing derived from local diurnal predictive model. Unconfirmed estimate — voice radio confirmation required.
                </div>
              ) : null}
            </div>
          </section>
        </aside>

        {/* Right Column: Inbound Queue Table & Expanded Patient Dossier */}
        <main className="right-workspace-col">
          {/* Section: Queue Table */}
          <section className="hud-section" style={{ flex: selectedHs ? "0 0 auto" : "1" }}>
            <div className="hud-section-header">
              <span>Inbound Pre-Arrival Emergency Queue ({handshakes.length})</span>
              <span className="tag">PRIORITY SORT</span>
            </div>

            {handshakes.length > 0 ? (
              <div className="triage-table-wrap">
                <table className="triage-table">
                  <thead>
                    <tr>
                      <th>Status</th>
                      <th>ETA</th>
                      <th>Category</th>
                      <th>NEWS2 Risk</th>
                      <th>Ambulance</th>
                      <th>Incident ID</th>
                      <th>Received</th>
                    </tr>
                  </thead>
                  <tbody>
                    {handshakes.map((hs) => {
                      const isSelected = selectedHs?.id === hs.id;
                      const statusClass =
                        hs.status === "CONFIRMED"
                          ? "confirmed"
                          : hs.status === "CONSTRAINED_REROUTE_REQUESTED"
                          ? "diverted"
                          : hs.status === "TIMED_OUT"
                          ? "timeout"
                          : "pending";

                      const urgencyClass =
                        hs.patient.news2 >= 7
                          ? "urgency-high"
                          : hs.patient.news2 >= 5
                          ? "urgency-med"
                          : hs.patient.news2 >= 1
                          ? "urgency-low"
                          : "urgency-stable";

                      return (
                        <tr
                          key={hs.id}
                          className={`${isSelected ? "selected" : ""} ${urgencyClass}`}
                          onClick={() => {
                            setSelectedHs(hs);
                            setChosenEsi(hs.anticipated_esi || 2);
                          }}
                        >
                          <td>
                            <span className={`badge-status ${statusClass}`}>{hs.status}</span>
                          </td>
                          <td>
                            <span className="eta-pill">{hs.eta_min} min</span>
                          </td>
                          <td>
                            <strong style={{ color: "#ffffff" }}>{hs.patient.care_tag}</strong>
                          </td>
                          <td>
                            <span
                              className="num-tabular"
                              style={{
                                color:
                                  hs.patient.news2 >= 7
                                    ? "#f87171"
                                    : hs.patient.news2 >= 5
                                    ? "#fbbf24"
                                    : "#34d399",
                                fontWeight: 800,
                              }}
                            >
                              {hs.patient.news2} [{hs.patient.news2_risk_band}]
                            </span>
                          </td>
                          <td style={{ fontFamily: "var(--font-mono)", fontWeight: 600 }}>
                            {hs.ambulance_id}
                          </td>
                          <td style={{ fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>
                            {hs.id}
                          </td>
                          <td className="num-tabular">
                            {new Date(hs.created_ts * 1000).toLocaleTimeString()}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              /* Rebuilt Empty State: Welcoming Emergency Department Standby Station */
              <div className="standby-station-card">
                <div className="standby-header">
                  <span className="standby-icon">📡</span>
                  <div>
                    <h3 className="standby-title">Emergency Department Standing By — No Inbound Pre-Arrivals</h3>
                    <p className="standby-subtitle">
                      Monitoring regional CAD and field paramedic transmissions. Inbound emergency handshakes will chime and prioritize automatically by physiological urgency.
                    </p>
                  </div>
                </div>

                <div className="standby-demo-box">
                  <span className="standby-demo-title">Interactive Operational Test Station:</span>
                  <p className="standby-demo-desc">
                    Click either simulated scenario below to verify two-way telemetry, vital sign presentation, and receiving nurse ESI bay reservation:
                  </p>
                  <div className="standby-actions-row">
                    <button
                      type="button"
                      className="btn-demo-sim"
                      onClick={() => handleSimulateCase("STEMI")}
                    >
                      ⚡ Simulate Inbound STEMI Pre-Alert (AMB-204)
                    </button>
                    <button
                      type="button"
                      className="btn-demo-sim"
                      onClick={() => handleSimulateCase("TRAUMA")}
                    >
                      ⚡ Simulate Polytrauma Bay Request (AMB-108)
                    </button>
                  </div>
                </div>
              </div>
            )}
          </section>

          {/* Section: Expanded Patient Case Dossier (Appears only when a case is active/selected) */}
          {selectedHs && (
            <section className="patient-dossier-card">
              <div className="dossier-top-bar">
                <div className="dossier-headline">
                  <span>🚨 Case Dossier:</span>
                  <span className="incident-badge">{selectedHs.id}</span>
                  <span style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>
                    Unit: <strong style={{ color: "#ffffff" }}>{selectedHs.ambulance_id}</strong>
                  </span>
                  <span className="eta-pill">ETA: {selectedHs.eta_min} min</span>
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <span
                    className={`badge-status ${
                      selectedHs.status === "CONFIRMED"
                        ? "confirmed"
                        : selectedHs.status === "CONSTRAINED_REROUTE_REQUESTED"
                        ? "diverted"
                        : "pending"
                    }`}
                  >
                    {selectedHs.status}
                  </span>
                  <button
                    type="button"
                    className="btn-close-dossier"
                    onClick={() => setSelectedHs(null)}
                    title="Close dossier view"
                  >
                    ✕ Close Dossier
                  </button>
                </div>
              </div>

              {/* Paramedic Emergency Narrative Callout */}
              <div className="paramedic-narrative-box">
                <div className="paramedic-narrative-title">
                  📋 Field Paramedic Emergency Narrative & Scene Observations:
                </div>
                <div className="paramedic-narrative-content">
                  {selectedHs.patient.emergency_description ||
                    `No custom narrative documented. Predefined clinical tag: ${selectedHs.patient.care_tag}`}
                </div>
              </div>

              {/* Clinical Resources & Field Interventions */}
              <div className="clinical-context-grid">
                <div className="context-box">
                  <span className="context-box-lbl">Requested Department Resources:</span>
                  <strong>
                    {selectedHs.patient.custom_requirements?.length
                      ? selectedHs.patient.custom_requirements.join(", ")
                      : "Standard Emergency Department Protocol"}
                  </strong>
                </div>
                <div className="context-box">
                  <span className="context-box-lbl">Paramedic Field Interventions:</span>
                  <strong>{selectedHs.patient.paramedic_notes || "None documented in transit"}</strong>
                </div>
              </div>

              {/* Vitals Matrix with Normal Reference Ranges */}
              <div className="vitals-grid-six">
                <div
                  className={`vital-pod ${
                    selectedHs.patient.vitals.respiration_rate < 12 || selectedHs.patient.vitals.respiration_rate > 24
                      ? "abnormal"
                      : ""
                  }`}
                >
                  <span className="v-name">Resp Rate</span>
                  <span className="v-number">{selectedHs.patient.vitals.respiration_rate}</span>
                  <span className="v-ref">Normal: 12–20</span>
                </div>

                <div
                  className={`vital-pod ${
                    selectedHs.patient.vitals.spo2 < 95 ? "abnormal" : ""
                  }`}
                >
                  <span className="v-name">SpO2</span>
                  <span className="v-number">{selectedHs.patient.vitals.spo2}%</span>
                  <span className="v-ref">Normal: ≥96%</span>
                </div>

                <div
                  className={`vital-pod ${
                    selectedHs.patient.vitals.systolic_bp < 90 || selectedHs.patient.vitals.systolic_bp > 140
                      ? "abnormal"
                      : ""
                  }`}
                >
                  <span className="v-name">Systolic BP</span>
                  <span className="v-number">{selectedHs.patient.vitals.systolic_bp}</span>
                  <span className="v-ref">Normal: 90–120</span>
                </div>

                <div
                  className={`vital-pod ${
                    selectedHs.patient.vitals.heart_rate < 50 || selectedHs.patient.vitals.heart_rate > 100
                      ? "abnormal"
                      : ""
                  }`}
                >
                  <span className="v-name">Heart Rate</span>
                  <span className="v-number">{selectedHs.patient.vitals.heart_rate}</span>
                  <span className="v-ref">Normal: 60–100</span>
                </div>

                <div
                  className={`vital-pod ${
                    selectedHs.patient.vitals.temperature < 36.0 || selectedHs.patient.vitals.temperature > 38.0
                      ? "abnormal"
                      : ""
                  }`}
                >
                  <span className="v-name">Temp (°C)</span>
                  <span className="v-number">{selectedHs.patient.vitals.temperature.toFixed(1)}</span>
                  <span className="v-ref">Normal: 36.5–37.5</span>
                </div>

                <div
                  className={`vital-pod ${
                    selectedHs.patient.vitals.consciousness !== "A" ? "abnormal" : ""
                  }`}
                >
                  <span className="v-name">AVPU</span>
                  <span className="v-number">{selectedHs.patient.vitals.consciousness}</span>
                  <span className="v-ref">Normal: Alert (A)</span>
                </div>
              </div>

              {/* Triage Actions Console Bar */}
              <div className="triage-console-bar">
                <div className="esi-selector-wrap">
                  <span className="lbl">Receiving ESI:</span>
                  <select
                    className="control-input"
                    style={{ width: "auto" }}
                    value={chosenEsi}
                    onChange={(e) => setChosenEsi(parseInt(e.target.value))}
                    disabled={selectedHs.status !== "PENDING_RESPONSE"}
                  >
                    <option value={1}>ESI 1 — Resuscitation (Immediate Life Threat)</option>
                    <option value={2}>ESI 2 — Emergent (High Risk / Time Critical)</option>
                    <option value={3}>ESI 3 — Urgent (Two or More Resources)</option>
                    <option value={4}>ESI 4 — Less Urgent (One Resource)</option>
                    <option value={5}>ESI 5 — Non-Urgent (Zero Resources)</option>
                  </select>
                </div>

                <div style={{ display: "flex", gap: "10px" }}>
                  <button
                    className="btn-ack-bay"
                    disabled={selectedHs.status !== "PENDING_RESPONSE"}
                    onClick={handleConfirmHandshake}
                    title="Acknowledge readiness and reserve receiving bay [Enter]"
                  >
                    <span>✅ Acknowledge & Reserve Bay</span>
                    <span style={{ opacity: 0.7, fontSize: "0.72rem" }}>[Enter]</span>
                  </button>

                  <button
                    className="btn-report-surge"
                    disabled={selectedHs.status !== "PENDING_RESPONSE"}
                    onClick={() => setShowDivertModal(true)}
                    title="Report capacity constraint and divert ambulance"
                  >
                    <span>⚠️ Report Surge / Divert</span>
                  </button>
                </div>
              </div>
            </section>
          )}
        </main>
      </div>

      {/* Diversion Modal */}
      {showDivertModal && (
        <div className="modal-backdrop">
          <div className="modal-box">
            <h3>Report Department Constraint & Request Reroute</h3>
            <p style={{ fontSize: "0.82rem", color: "var(--text-muted)", marginBottom: "12px", lineHeight: "1.4" }}>
              Provide the clinical or capacity reason to transmit to the ambulance crew. The VitalRoute optimizer will immediately evaluate secondary receiving facilities:
            </p>
            <input
              type="text"
              className="control-input"
              value={divertReason}
              onChange={(e) => setDivertReason(e.target.value)}
              placeholder="e.g. ED Resuscitation Bays at Critical Surge"
              autoFocus
            />
            <div className="modal-actions-row">
              <button className="btn-tool" onClick={() => setShowDivertModal(false)}>
                Cancel [Esc]
              </button>
              <button
                className="btn-report-surge"
                style={{ backgroundColor: "#dc2626", color: "#ffffff" }}
                onClick={handleDivertHandshake}
              >
                Confirm Diversion
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Settings Modal */}
      {showSettingsModal && (
        <div className="modal-backdrop">
          <div className="modal-box">
            <h3>Core Server Endpoint Settings</h3>
            <div className="control-field" style={{ marginTop: "12px" }}>
              <label className="control-label">VitalRoute Decision Core URL:</label>
              <input
                type="text"
                className="control-input"
                value={tempServerUrl}
                onChange={(e) => setTempServerUrl(e.target.value)}
              />
            </div>
            <div className="modal-actions-row">
              <button className="btn-tool" onClick={() => setShowSettingsModal(false)}>
                Cancel
              </button>
              <button
                className="btn-commit-capacity"
                onClick={() => {
                  setServerUrl(tempServerUrl.trim());
                  setShowSettingsModal(false);
                }}
              >
                Save & Connect
              </button>
            </div>
          </div>
        </div>
      )}

      {/* About Modal */}
      {showAboutModal && (
        <div className="modal-backdrop">
          <div className="modal-box">
            <h3>VitalRoute Emergency Destination Orchestration</h3>
            <p style={{ fontSize: "0.82rem", lineHeight: "1.5", color: "var(--text-muted)", marginTop: "8px" }}>
              <strong>Receiving Hospital Triage HUD</strong>
              <br />
              <strong>Architecture:</strong> Tauri 2 + React + TypeScript + Python Decision Core
              <br />
              <strong>Pillars:</strong> Telemetry Freshness Decay, Time-to-Definitive-Care (TTDC), Two-Way Readiness Handshake, Offline Diurnal Predictive Capacity.
              <br />
              <strong>SDG 3 Target 3.6 & 3.8:</strong> Mitigating emergency offload delays and emergency department crowding through confidence-aware prehospital coordination.
            </p>
            <div className="modal-actions-row">
              <button className="btn-tool" onClick={() => setShowAboutModal(false)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
