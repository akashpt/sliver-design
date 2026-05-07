/* ── Bridge init ── */
let _br = null;
function initBridge() {
  if (_br) return _br;
  _br = new Promise((res, rej) => {
    let n = 0;
    (function try_() {
      if (window.qt && qt.webChannelTransport) {
        window.__qtWebChannelConnecting = true;

        new QWebChannel(qt.webChannelTransport, (ch) => {
          window.__qtWebChannelConnecting = false;
          window.bridge = ch.objects.bridge;
          res(window.bridge);
        });
        return;
      }
      // if (++n > 50) return rej(new Error("Qt bridge unavailable"));
      if (++n > 200) return rej(new Error("Qt bridge unavailable"));
      setTimeout(try_, 100);
    })();
  });
  return _br;
}
const callNoReturn = (fn, ...a) => initBridge().then((b) => b[fn](...a));
const callWithResult = (fn, ...a) =>
  initBridge().then(
    (b) =>
      new Promise((res, rej) => {
        try {
          b[fn](...a, res);
        } catch (e) {
          rej(e);
        }
      }),
  );
window.addEventListener("load", () => initBridge().catch(console.warn));

/* ── Clock ── */
function pad2(n) {
  return String(n).padStart(2, "0");
}
function tick() {
  const d = new Date();
  const t = `${pad2(d.getHours() % 12 || 12)}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`;
  const dt = `${pad2(d.getDate())}/${pad2(d.getMonth() + 1)}/${d.getFullYear()}`;
  document.querySelectorAll("#timeValue").forEach((e) => (e.textContent = t));
  document.querySelectorAll("#dateValue").forEach((e) => (e.textContent = dt));
}
tick();
setInterval(tick, 1000);

/* ── Toast ── */
function showToast(msg, type = "ok") {
  const t = document.getElementById("toast");
  clearTimeout(t._t);
  t.className = `toast ${type}`;
  t.textContent = msg;
  t.style.display = "block";
  t._t = setTimeout(() => {
    t.style.display = "none";
  }, 2400);
}

/* ── Error overlay ── */
function showError(msg) {
  document.getElementById("errMsg").textContent = msg;
  const ov = document.getElementById("errOverlay");
  ov.style.display = "flex";
  requestAnimationFrame(() =>
    requestAnimationFrame(() => ov.classList.add("open")),
  );
}
function closeError() {
  const ov = document.getElementById("errOverlay");
  ov.classList.remove("open");
  setTimeout(() => (ov.style.display = "none"), 260);
}

/* ── Section reveal ── */
function revealSection(id) {
  const el = document.getElementById(id);
  el.classList.add("revealing");
  requestAnimationFrame(() =>
    requestAnimationFrame(() => {
      el.classList.remove("hidden-section", "revealing");
      el.classList.add("visible-section");
    }),
  );
}
function hideSection(id) {
  const el = document.getElementById(id);
  el.classList.remove("visible-section");
  el.classList.add("hidden-section");
}

/* ── Global status badge ── */
function setGlobalStatus(state, text) {
  const badge = document.getElementById("globalStatus");
  badge.querySelector(".ctrl-status-dot").className =
    "ctrl-status-dot " + state;
  badge.querySelector(".ctrl-status-text").textContent = text;
}

let _connected = false;
let _mode = null;

/* ════════════════════════════════════════════
       ① EXPOSURE
   ════════════════════════════════════════════ */
async function applyExposure() {
  const inp = document.getElementById("exposureInput");
  const rawVal = inp.value.trim();

  /* ── Empty input guard ── */
  if (rawVal === "") {
    showError("Exposure value cannot be empty. Please enter a value.");
    return;
  }

  const v = parseInt(rawVal, 10);
  const min = Math.round(parseFloat(inp.min));
  const max = Math.round(parseFloat(inp.max));

  /* ── Min/max must be loaded and > 0 ── */
  if (!min || min <= 0 || !max || max <= 0) {
    showError(
      "Camera exposure range is not available or invalid. " +
        "Min and Max must both be greater than 0.",
    );
    return;
  }

  /* ── Value must be > 0 and within [min, max] ── */
  if (isNaN(v) || v <= 0 || v < min || v > max) {
    showError(
      "Enter a valid exposure value between " +
        min +
        " and " +
        max +
        " µs (must be greater than 0).",
    );
    return;
  }

  try {
    const raw = await callWithResult("cameraControl", "setExposure", String(v));
    let p = {};
    try {
      p = JSON.parse(raw);
    } catch (_) {}
    if (p.ok === false) {
      showError("Exposure error: " + (p.message || "Unknown"));
      return;
    }

    /* ── Confirm running value from backend ── */
    try {
      const expRaw = await callWithResult("cameraControl", "getExposure", "");
      let val = null;
      try {
        const ep = JSON.parse(expRaw);
        val = ep.value ?? ep.exposure ?? null;
      } catch (_) {
        val = parseFloat(expRaw);
      }
      if (val !== null && !isNaN(val)) {
        document.getElementById("exposureInput").value = Math.round(val);
      }
    } catch (_) {
      /* getExposure confirmation is optional */
    }
  } catch (e) {
    showError("Exposure failed: " + (e.message || e));
  }
}

/* ════════════════════════════════════════════
       ② CONNECTION (auto-runs on page load)
   ════════════════════════════════════════════ */
async function checkConnection() {
  const dot = document.getElementById("connDot");
  const text = document.getElementById("connText");
  const sub = document.getElementById("connSub");
  const wrap = document.getElementById("connBanner");
  const btn = document.getElementById("connRefreshBtn");

  /* Checking state */
  dot.className = "conn-dot-large pulse";
  text.textContent = "Checking connection…";
  sub.textContent = "Please wait";
  wrap.className = "conn-status-wrap";
  setGlobalStatus("pulse", "Connecting…");
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-rotate-right fa-spin"></i>Checking…';
  }

  hideSection("modeSection");
  hideSection("manualSection");
  _connected = false;
  _mode = null;
  resetMode();

  try {
    const raw = await callWithResult("checkPlcConnection");

    let ok = false,
      statusMsg = "";
    try {
      const p = JSON.parse(raw);
      ok = p.ok === true;
      statusMsg = p.message || (ok ? "PLC Connected" : "PLC Not Connected");
    } catch (_) {
      ok = raw === "ok";
      statusMsg = ok ? "PLC Connected" : raw || "PLC Not Connected";
    }

    _connected = ok;
    if (ok) {
      dot.className = "conn-dot-large ok";
      text.textContent = statusMsg;
      sub.textContent = "Link established — ready";
      wrap.className = "conn-status-wrap ok-state";
      setGlobalStatus("ok", "PLC Connected");
      revealSection("modeSection");
      fetchCurrentState();
    } else {
      dot.className = "conn-dot-large err";
      text.textContent = statusMsg;
      sub.textContent = "Check cable or PLC power";
      wrap.className = "conn-status-wrap err-state";
      setGlobalStatus("err", "Connection Failed");
    }
  } catch (e) {
    _connected = false;
    dot.className = "conn-dot-large err";
    text.textContent = "Bridge Unavailable";
    sub.textContent = "Qt bridge could not be reached";
    wrap.className = "conn-status-wrap err-state";
    setGlobalStatus("err", "Bridge Unavailable");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '<i class="fa-solid fa-rotate-right"></i>Refresh';
    }
  }
}

/* ════════════════════════════════════════════
       ③ MODE — display driven by backend
   ════════════════════════════════════════════ */
function resetMode() {
  document.getElementById("btnAuto").dataset.active = "false";
  document.getElementById("btnManual").dataset.active = "false";
  document.getElementById("modeStatusPill").textContent = "IDLE";
  document.getElementById("modeStatusPill").className = "mode-status-pill";
  document.getElementById("modeSeg").dataset.mode = "none";
}

function updateModeDisplay(mode) {
  _mode = mode;
  const isAuto = mode === "auto";
  document.getElementById("modeSeg").dataset.mode = mode;
  document.getElementById("btnAuto").dataset.active = isAuto ? "true" : "false";
  document.getElementById("btnManual").dataset.active = !isAuto ? "true" : "false";
  const pill = document.getElementById("modeStatusPill");
  pill.textContent = isAuto ? "AUTO" : "MANUAL";
  pill.className = "mode-status-pill " + (isAuto ? "pill-auto" : "pill-manual");
  /* Always show IO section; in AUTO just disable interaction */
  revealSection("manualSection");
  const grid = document.querySelector(".io-grid");
  if (grid) grid.classList.toggle("io-grid--disabled", isAuto);
  if (isAuto) {
    Object.keys(IO_CFG).forEach((dev) => setIO(dev, false));
  }
}

/* ════════════════════════════════════════════
       ④ I/O TOGGLES — visual state management
   ════════════════════════════════════════════ */
const IO_CFG = {
  gripper:  { toggleId: "gripperToggle",  labelId: "gripperLabel",  cardId: "gripperCard"  },
  uv:       { toggleId: "uvToggle",       labelId: "uvLabel",       cardId: "uvCard"       },
  relay1:   { toggleId: "relay1Toggle",   labelId: "relay1Label",   cardId: "relay1Card"   },
  relay2:   { toggleId: "relay2Toggle",   labelId: "relay2Label",   cardId: "relay2Card"   },
  conveyor: { toggleId: "conveyorToggle", labelId: "conveyorLabel", cardId: "conveyorCard" },
  sensor:   { toggleId: "sensorToggle",   labelId: "sensorLabel",   cardId: "sensorCard"   },
};

function setIO(device, on) {
  const cfg = IO_CFG[device];
  if (!cfg) return;
  const toggle = document.getElementById(cfg.toggleId);
  const card = document.getElementById(cfg.cardId);
  const sw = toggle ? toggle.closest(".sw") : null;
  if (toggle) toggle.checked = on;
  if (sw) {
    on ? sw.classList.add("on") : sw.classList.remove("on");
  }
  if (card) {
    card.dataset.on = on ? "true" : "false";
    const stateOff = card.querySelector(".io-state-off");
    const stateOn = card.querySelector(".io-state-on");
    if (stateOff) stateOff.classList.toggle("d-none", on);
    if (stateOn) stateOn.classList.toggle("d-none", !on);
  }
}

/* ════════════════════════════════════════════
       ⑤ LOAD EXPOSURE RANGE FROM settings.json
   ════════════════════════════════════════════ */
async function loadExposureRange() {
  try {
    const raw = await callWithResult("cameraControl", "getCameraDetails", "");
    let p = {};
    try {
      p = JSON.parse(raw);
    } catch (_) {}
    if (p.ok === false) return;

    const minVal = parseFloat(p.min);
    const maxVal = parseFloat(p.max);

    const inp = document.getElementById("exposureInput");
    inp.min = Math.round(minVal);
    inp.max = Math.round(maxVal);
    inp.step = 1;

    const hint = document.querySelector(".ctrl-hint");
    if (hint) {
      hint.innerHTML =
        '<i class="fa-solid fa-circle-info"></i>' +
        " Range: " +
        Math.round(minVal) +
        " – " +
        Math.round(maxVal) +
        " µs";
    }
  } catch (e) {
    console.warn("loadExposureRange failed", e);
  }
}

/* ════════════════════════════════════════════
       ⑥ FETCH LIVE STATE FROM BACKEND
   ════════════════════════════════════════════ */
async function fetchCurrentState() {
  await loadExposureRange();

  /* ── Current exposure value ── */
  try {
    const raw = await callWithResult("cameraControl", "getExposure", "");
    let val = null;
    try {
      const p = JSON.parse(raw);
      val = p.value ?? p.exposure ?? null;
    } catch (_) {
      val = parseFloat(raw);
    }
    if (val !== null && !isNaN(val))
      document.getElementById("exposureInput").value = Math.round(val);
  } catch (e) {
    console.warn("getExposure failed", e);
  }

  /* ── Controller mode ── */
  try {
    const raw = await callWithResult("cameraControl", "getControllerMode", "");
    let mode = null;
    try {
      const p = JSON.parse(raw);
      mode = p.mode || p.value || null;
    } catch (_) {
      mode = raw;
    }
    if (mode) updateModeDisplay(mode.toString().toLowerCase());
  } catch (e) {
    console.warn("getControllerMode failed", e);
  }

  /* ── I/O states (manual mode only) ── */
  if (_mode === "manual") {
    try {
      const raw = await callWithResult("cameraControl", "getIOStates", "");
      let io = {};
      try {
        io = JSON.parse(raw);
      } catch (_) {}
      Object.keys(IO_CFG).forEach((dev) => {
        if (io[dev] !== undefined) setIO(dev, !!io[dev]);
      });
    } catch (e) {
      console.warn("getIOStates failed", e);
    }
  }
}

/* ════════════════════════════════════════════
       ⑦ SIGNAL STATUS — left card
          Read-only. Updated ONLY by
          signal_status_signal from Python.
          JS has zero signal logic — pure display.
   ════════════════════════════════════════════ */

/* Left card badge + card element IDs */
const STATUS_CFG = {
  signal1: { badgeId: "signal1Badge", cardId: "signal1Card" },
  signal2: { badgeId: "signal2Badge", cardId: "signal2Card" },
  signal3: { badgeId: "signal3Badge", cardId: "signal3Card" },
  signal4: { badgeId: "signal4Badge", cardId: "signal4Card" },
  signal5: { badgeId: "signal5Badge", cardId: "signal5Card" },
  signal6: { badgeId: "signal6Badge", cardId: "signal6Card" },
  signal7: { badgeId: "signal7Badge", cardId: "signal7Card" },
};

/*
 * setSignalStatus — updates LEFT card badge only.
 * Never touches the right-card (Signal Controls) toggles.
 */
function setSignalStatus(signal, on) {
  const cfg = STATUS_CFG[signal];
  if (!cfg) return;
  const badge = document.getElementById(cfg.badgeId);
  const card  = document.getElementById(cfg.cardId);
  if (badge) {
    badge.textContent = on ? "ON" : "OFF";
    badge.className   = "signal-badge " + (on ? "on" : "off");
  }
  if (card) card.dataset.on = on ? "true" : "false";
}

function applySignalStatus(data) {
  setSignalStatus("signal1", !!data.signal1);
  setSignalStatus("signal2", !!data.signal2);
  setSignalStatus("signal3", !!data.signal3);
  setSignalStatus("signal4", !!data.signal4);
  setSignalStatus("signal5", !!data.signal5);
  setSignalStatus("signal6", !!data.signal6);
  setSignalStatus("signal7", !!data.signal7);
}

async function loadSignalStatus() {
  try {
    const raw = await callWithResult("cameraControl", "getSignalStatus", "");
    let data = {};
    try { data = JSON.parse(raw); } catch (_) {}
    applySignalStatus(data);
  } catch (e) {
    console.warn("getSignalStatus failed", e);
  }
}

/* ════════════════════════════════════════════
       ⑧ SIGNAL CONTROLS — right card
          Write-only toggles.
          User toggles → cameraControl → hardware.
          Left-card Signal Status is NEVER touched.
   ════════════════════════════════════════════ */

/* Right card toggle IDs — for page-load reset only */
const SIGNAL_CFG = {
  whitelight:   { toggleId: "whitelightToggle"  },
  uvlight:      { toggleId: "uvlightToggle"      },
  machinebreak: { toggleId: "machinebreakToggle" },
  greenlight:   { toggleId: "greenlightToggle"   },
  yellowlight:  { toggleId: "yellowlightToggle"  },
  redlight:     { toggleId: "redlightToggle"     },
  empty:        { toggleId: "emptyToggle"        },
};

/* Reset a right-card toggle visually — never affects left card */
function setSignal(signal, on) {
  const cfg = SIGNAL_CFG[signal];
  if (!cfg) return;
  const toggle = document.getElementById(cfg.toggleId);
  const sw     = toggle ? toggle.closest(".sw") : null;
  if (toggle) toggle.checked = on;
  if (sw) on ? sw.classList.add("on") : sw.classList.remove("on");
}

/* ════════════════════════════════════════════
       ⑨ BRIDGE → SIGNAL STATUS (left card)
          Listens ONLY to signal_status_signal.
          Python owns all signal ON/OFF logic.
          JS receives flat true/false per signal
          and renders it — nothing more.
   ════════════════════════════════════════════ */
function connectSignalStatusToBridge(bridge) {

  /*
   * signal_status_signal — dedicated pyqtSignal from bridge.py.
   *
   * Payload (JSON string):
   * {
   *   "signal1": true | false,
   *   "signal2": true | false,
   *   "signal3": true | false,
   *   "signal4": true | false,
   *   "signal5": true | false,
   *   "signal6": true | false,
   *   "signal7": true | false
   * }
   *
   * Python decides when each signal is ON or OFF
   * (based on counts, defects, resets, timing, etc.).
   * JS just receives and displays.
   */
  bridge.signal_status_signal.connect(function (jsonStr) {
    var data = {};
    try { data = JSON.parse(jsonStr); } catch (_) {}
    applySignalStatus(data);
  });

  console.log("✅ Signal Status card connected to signal_status_signal");
}

/* ════════════════════════════════════════════
       DOMContentLoaded — wire up all UI events
   ════════════════════════════════════════════ */
document.addEventListener("DOMContentLoaded", function () {

  /* ── Apply exposure button ── */
  document
    .getElementById("ctrlApplyBtn")
    .addEventListener("click", applyExposure);

  /* ── Exposure input: integers only, block special chars ── */
  var expInp = document.getElementById("exposureInput");
  expInp.addEventListener("keydown", function (e) {
    var allowed = [
      "Backspace", "Delete", "Tab", "Escape", "Enter",
      "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown",
      "Home", "End",
    ];
    if (allowed.indexOf(e.key) !== -1) return;
    if (
      (e.ctrlKey || e.metaKey) &&
      ["a", "c", "v", "x", "z"].indexOf(e.key.toLowerCase()) !== -1
    )
      return;
    if (!/^[0-9]$/.test(e.key)) e.preventDefault();
  });
  expInp.addEventListener("input", function () {
    var clean = this.value.replace(/[^0-9]/g, "");
    if (clean !== this.value) this.value = clean;
  });

  /* ── Error modal ── */
  document.getElementById("errDismiss").addEventListener("click", closeError);
  document.getElementById("errOverlay").addEventListener("click", function (e) {
    if (e.target === this) closeError();
  });

  /* ── Mode buttons → cameraControl slot ── */
  document.getElementById("btnAuto").addEventListener("click", function () {
    if (_mode === "auto") return;
    callWithResult("cameraControl", "setMode", "auto")
      .then(function (raw) {
        let p = {};
        try { p = JSON.parse(raw); } catch (_) {}
        if (p.ok === false) {
          showError("Mode error: " + (p.message || "Unknown"));
          return;
        }
        updateModeDisplay("auto");
        showToast("Mode → AUTO saved ✓", "ok");
      })
      .catch(function (e) {
        showError("setMode failed: " + e.message);
      });
  });

  document.getElementById("btnManual").addEventListener("click", function () {
    if (_mode === "manual") return;
    callWithResult("cameraControl", "setMode", "manual")
      .then(function (raw) {
        let p = {};
        try { p = JSON.parse(raw); } catch (_) {}
        if (p.ok === false) {
          showError("Mode error: " + (p.message || "Unknown"));
          return;
        }
        updateModeDisplay("manual");
        showToast("Mode → MANUAL saved ✓", "ok");
      })
      .catch(function (e) {
        showError("setMode failed: " + e.message);
      });
  });

  /* ── IO toggles → cameraControl slot ──
       data-fn: setGripper | setUVLight | setRelay1 | setRelay2 | setConveyor | setSensorLight
  ── */
  document
    .querySelectorAll(".io-grid input[type='checkbox'][data-fn]")
    .forEach(function (chk) {
      chk.addEventListener("change", function () {
        var param = chk.dataset.fn;     // e.g. "setGripper"
        var dev   = chk.dataset.device; // e.g. "gripper"
        var on    = chk.checked;
        setIO(dev, on); // instant visual feedback
        callWithResult("cameraControl", param, String(on))
          .then(function (raw) {
            var p = {};
            try { p = JSON.parse(raw); } catch (_) {}
            if (p.ok === false) {
              setIO(dev, !on); // revert on error
              showError(param + " failed: " + (p.message || "Unknown"));
            }
          })
          .catch(function (e) {
            setIO(dev, !on);
            showError(param + " error: " + e.message);
          });
      });
    });

  /* ── Click anywhere on io-box to toggle ── */
  document.querySelectorAll(".io-box").forEach(function (box) {
    box.addEventListener("click", function (e) {
      if (e.target.closest(".sw")) return;
      var chk = box.querySelector("input[type='checkbox']");
      if (!chk) return;
      chk.checked = !chk.checked;
      chk.dispatchEvent(new Event("change"));
    });
  });

  /* ── Hard-reset all IO to OFF on page load ── */
  Object.keys(IO_CFG).forEach(function (dev) {
    setIO(dev, false);
  });

  /* ── Hard-reset right-card (Signal Controls) toggles to OFF on page load ── */
  Object.keys(SIGNAL_CFG).forEach(function (sig) {
    setSignal(sig, false);
  });

  /* ── Signal Controls (right card) → bridge write ──
       User toggles → cameraControl → hardware.
       On error: revert only that toggle.
       Left-card Signal Status is NEVER touched here.
  ── */
  document
    .querySelectorAll("#signalControlCard input[type='checkbox'][data-fn]")
    .forEach(function (chk) {
      chk.addEventListener("change", function () {
        var param = chk.dataset.fn; // e.g. "setWhiteLight"
        var on    = chk.checked;
        var sw    = chk.closest(".sw");

        /* Instant visual feedback */
        if (sw) on ? sw.classList.add("on") : sw.classList.remove("on");

        callWithResult("cameraControl", param, String(on))
          .then(function (raw) {
            var p = {};
            try { p = JSON.parse(raw); } catch (_) {}
            if (p.ok === false) {
              /* Revert toggle only — left card untouched */
              chk.checked = !on;
              if (sw) on ? sw.classList.remove("on") : sw.classList.add("on");
              showError(param + " failed: " + (p.message || "Unknown"));
            }
          })
          .catch(function (e) {
            /* Revert toggle on bridge error — left card untouched */
            chk.checked = !on;
            if (sw) on ? sw.classList.remove("on") : sw.classList.add("on");
            showError(param + " error: " + e.message);
          });
      });
    });

  /* ── Load exposure range + current value ── */
  loadExposureRange();
  callWithResult("cameraControl", "getExposure", "")
    .then(function (raw) {
      let val = null;
      try {
        const p = JSON.parse(raw);
        val = p.value ?? p.exposure ?? null;
      } catch (_) {
        val = parseFloat(raw);
      }
      if (val !== null && !isNaN(val)) {
        document.getElementById("exposureInput").value = Math.round(val);
      }
    })
    .catch(function (e) {
      console.warn("Initial getExposure failed", e);
    });

  /* ── Auto-check connection on page load ── */
  checkConnection();

  /* ── Subscribe Signal Status left card to bridge signal_status_signal ── */
  initBridge()
    .then(function (bridge) {
      connectSignalStatusToBridge(bridge);
      loadSignalStatus();
    })
    .catch(function (e) {
      console.warn("Bridge signal subscription failed:", e);
    });
});
