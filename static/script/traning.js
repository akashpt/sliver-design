// ═══════════════════════════════════════════════════════════════════
//  traning.js — Sliver Strip Detection · Training Page
//  Modules: Clock · Log · Toast · Defect Viewer · Settings ·
//           Camera Control · Bridge Communication · Range Sliders
// ═══════════════════════════════════════════════════════════════════


document.addEventListener("DOMContentLoaded", function () {

  new QWebChannel(qt.webChannelTransport, async function (channel) {

    window.bridge = channel.objects.bridge;

    if (!bridge) {
      showToast("⚠️ No Qt Bridge - Using Laptop Webcam", 4000);
      return;
    }

    showToast("✅ Bridge Connected Successfully", 3000);

    // ✅ CONNECT FRAME SIGNAL ONLY HERE
    if (bridge.frame_signal) {

      bridge.frame_signal.connect(function (frame) {

        const img = document.getElementById("bridgeFeed");
        const noFeed = document.getElementById("noFeed");

        if (!img) return;

        img.src = "data:image/jpeg;base64," + frame;

        img.style.display = "block";
        if (noFeed) noFeed.style.display = "none";
      });

      console.log("✅ frame_signal connected");
    }

    await loadDropdownData();
    await populateInputsFromConfig();

  });



  renderDefectThumbs();
  resetToInitialState();

  const jobIdInput = document.getElementById("jobIdInput");
  const thresholdInput = document.getElementById("thresholdInput");

  // Enable OK button check
  jobIdInput.addEventListener("change", checkCanConfirm);
  thresholdInput.addEventListener("input", checkCanConfirm);

  // Auto-save to userConfig.json on every change (debounced 500 ms)
  jobIdInput.addEventListener("change", autoSaveConfig);
  thresholdInput.addEventListener("input", autoSaveConfig);
});
 


// ── Module: Clock ───────────────────────────────────────────────────
(function initClock() {
  const update = () => {
    const el = document.getElementById("clock");
    if (el) el.textContent = new Date().toTimeString().slice(0, 8);
  };
  update();
  setInterval(update, 1000);
})();

// ── Module: Log ─────────────────────────────────────────────────────
function addLog(msg) {
  const box = document.getElementById("logBox");
  if (!box) return;
  const time = new Date().toTimeString().slice(0, 8);
  box.innerHTML += `<div><span style="color:var(--primary);font-weight:600">${time}</span> ${msg}</div>`;
  box.scrollTop = box.scrollHeight;
}

// ── Module: Toast ────────────────────────────────────────────────────
function showToast(msg, ms = 3500) {
  const t = document.getElementById("toast");
  if (!t) return;
  document.getElementById("toastMessage").textContent = msg;
  t.style.display = "block";
  requestAnimationFrame(() => t.classList.add("show"));
  setTimeout(() => {
    t.classList.remove("show");
    setTimeout(() => (t.style.display = "none"), 300);
  }, ms);
}

// ── Module: Defect Viewer ────────────────────────────────────────────
let defectHistory = [];
let currentModalIndex = -1;

function addDefectImage(imgSrc) {
  const time = new Date().toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
  defectHistory.unshift({ time, src: imgSrc });
  if (defectHistory.length > 10) defectHistory.pop();
  renderDefectThumbs();
}

function renderDefectThumbs() {
  const container = document.getElementById("defectsSlider");
  if (!container) return;
  container.innerHTML = "";
  if (defectHistory.length === 0) {
    container.innerHTML = `<div class="defect-empty">No defects captured yet.</div>`;
    return;
  }
  defectHistory.forEach((def, idx) => {
    const thumb = document.createElement("div");
    thumb.className = "defect-thumb";
    thumb.innerHTML = `<img src="${def.src}" alt="Defect ${idx + 1}" loading="lazy">`;
    thumb.onclick = () => openDefectModal(idx);
    container.appendChild(thumb);
  });
}

function openDefectModal(index) {
  currentModalIndex = index;
  updateModalImage();
  document.getElementById("defectModal").style.display = "flex";
}

function updateModalImage() {
  if (currentModalIndex < 0 || currentModalIndex >= defectHistory.length) {
    closeDefectModal();
    return;
  }
  const def = defectHistory[currentModalIndex];
  document.getElementById("defectModalImage").src = def.src;
  document.getElementById("defectModalPosition").textContent =
    `${currentModalIndex + 1} / ${defectHistory.length} — ${def.time}`;
  document.getElementById("prevDefect").disabled = currentModalIndex === 0;
  document.getElementById("nextDefect").disabled =
    currentModalIndex === defectHistory.length - 1;
}

function changeDefect(direction) {
  currentModalIndex += direction;
  updateModalImage();
}

function closeDefectModal() {
  document.getElementById("defectModal").style.display = "none";
  currentModalIndex = -1;
}

function downloadDefectImage() {
  if (currentModalIndex < 0 || currentModalIndex >= defectHistory.length)
    return;
  const img = document.getElementById("defectModalImage");
  const a = document.createElement("a");
  a.href = img.src;
  a.download = `defect_${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.jpg`;
  a.click();
}

// ── Module: Settings ─────────────────────────────────────────────────
function openSettings() {
  document.getElementById("settingsModal").style.display = "flex";
  document.getElementById("modeDefault").checked = true;
  toggleManual();
}

function closeSettings() {
  document.getElementById("settingsModal").style.display = "none";
}

function toggleManual() {
  const isManual =
    document.querySelector('input[name="mode"]:checked')?.value === "manual";
  document.getElementById("manualControls").style.display = isManual
    ? "block"
    : "none";
  document.getElementById("defaultInfo").style.display = isManual
    ? "none"
    : "block";
}

function saveSettings() {
  closeSettings();
  showToast("Settings saved successfully");
  addLog("Settings updated.");
}

function switchTab(tabName) {
  document
    .querySelectorAll(".modal-tab")
    .forEach((t) => t.classList.remove("active"));
  document
    .querySelectorAll(".tab-content")
    .forEach((c) => c.classList.remove("active"));
  if (tabName === "detection") {
    document.querySelector(".modal-tab:first-child").classList.add("active");
    document.getElementById("detectionTab").classList.add("active");
  } else if (tabName === "threshold") {
    document.querySelector(".modal-tab:last-child").classList.add("active");
    document.getElementById("thresholdTab").classList.add("active");
  }
}

// ── Module: Bridge Communication ─────────────────────────────────────
const Bridge = (() => {
  const available = () =>
    typeof window.bridge !== "undefined" && window.bridge !== null;

  function sendTrainingSession(data) {
    try {
      if (
        available() &&
        typeof window.bridge.saveTrainingSession === "function"
      ) {
        window.bridge.saveTrainingSession(JSON.stringify(data));
        addLog("✅ Session data sent to bridge.");
      } else {
        console.warn("Bridge not available — session data:", data);
        addLog("⚠ Bridge unavailable. Data logged to console.");
      }
    } catch (err) {
      console.error("Bridge communication error:", err);
      addLog("❌ Bridge error: " + err.message);
    }
  }

  // ── FIX: QWebChannel slots with return values are ASYNC.
  //    Calling window.bridge.startCamera() synchronously always returns
  //    undefined, so result === "OK" was always false — the bridge path
  //    was silently skipped every time.
  //    Solution: wrap in a Promise and use the callback overload.
  function startCamera() {
    return new Promise((resolve) => {
      if (available() && typeof window.bridge.startCamera === "function") {
        window.bridge.startCamera(function (result) {
          resolve(result === "OK");
        });
      } else {
        resolve(false);
      }
    });
  }

  function stopCamera() {
    if (available() && typeof window.bridge.stopCamera === "function") {
      window.bridge.stopCamera();
    }
  }

  return { available, sendTrainingSession, startCamera, stopCamera };
})();

// ── Module: Camera Control ────────────────────────────────────────────
const CameraControl = (() => {
  // ── State ──────────────────────────────────────────────────────────
  let activeMode = null; // null | 'live' | 'training'
  let currentStream = null; // MediaStream — only used in browser fallback
  let usingBridge = false; // true when PyQt5 bridge is driving the camera

  // ── DOM Helper ─────────────────────────────────────────────────────
  const $ = (id) => document.getElementById(id);

  // ── UI State Rules ──────────────────────────────────────────────────
  //
  //  Mode      | LiveStart | LiveStop | TrainStart | TrainStop | SideMenu
  //  null      |    ON     |   OFF    |    ON      |   OFF     |   ON
  //  live      |    OFF    |   ON     |    OFF     |   OFF     |   OFF
  //  training  |    OFF    |   OFF    |    OFF     |   ON      |   OFF
  //
  function applyUIState(mode) {
    const idle = mode === null;
    const isLive = mode === "live";
    const isTrain = mode === "training";

    setBtn($("btnLiveStart"), !idle);
    setBtn($("btnLiveStop"), !isLive);
    setBtn($("btnTrainStart"), !idle);
    setBtn($("btnTrainStop"), !isTrain);
    setSideMenu(!idle);
  }

  function setBtn(el, disabled) {
    if (!el) return;
    el.disabled = disabled;
    el.style.opacity = disabled ? "0.38" : "1";
    el.style.pointerEvents = disabled ? "none" : "";
    el.style.cursor = disabled ? "not-allowed" : "pointer";
  }

  function setSideMenu(disabled) {
    const el = $("sideMenu");
    if (!el) return;
    el.style.pointerEvents = disabled ? "none" : "";
    el.style.opacity = disabled ? "0.38" : "";
  }

  // ── Show / hide feed elements ───────────────────────────────────────
  function showFeed() {
    $("noFeed").style.display = "none";
    $("liveBadge").style.display = "inline-flex";
  }

  function hideFeed() {
    // Hide both feed elements
    const video = $("videoFeed");
    const img = $("bridgeFeed");
    if (video) {
      video.srcObject = null;
      video.style.display = "none";
    }
    if (img) {
      img.src = "";
      img.style.display = "none";
    }

    $("noFeed").style.display = "flex";
    $("liveBadge").style.display = "none";
  }

  // ── Camera open (bridge-first, getUserMedia fallback) ───────────────
  // ── FIX: Bridge.startCamera() now returns a Promise, so we await it.
  //    Previously it returned a synchronous boolean (always false),
  //    which meant openCamera() always fell through to getUserMedia —
  //    which also fails in PyQt5's file:// context — and returned false.
  //    That caused startLive/confirmTraining to bail out early, leaving
  //    the stop button permanently disabled.
  async function openCamera() {
    hideFeed(); // reset state

    // ── Path 1: PyQt5 bridge (OpenCV) ──────────────────────────────
    const bridgeOk = await Bridge.startCamera(); // ← was: Bridge.startCamera() (sync, always false)
    if (bridgeOk) {
      usingBridge = true;
      // Frames will arrive via window.receiveFrame() below.
      // Show the <img id="bridgeFeed"> placeholder until first frame arrives.
      const img = $("bridgeFeed");
      if (img) img.style.display = "block";
      showFeed();
      addLog("📷 Camera started via bridge (OpenCV).");
      return true;
    }

    // ── Path 2: Browser getUserMedia fallback ───────────────────────
    usingBridge = false;

    // getUserMedia requires a secure context (HTTPS or localhost).
    // Opening the file directly via file:// will silently fail in most browsers.
    if (!window.isSecureContext) {
      addLog(
        "❌ Camera requires a secure context (HTTPS or localhost). Cannot use file:// protocol.",
      );
      showToast("Camera blocked: serve the page via localhost or HTTPS.", 6000);
      return false;
    }

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      addLog("❌ getUserMedia not supported in this environment.");
      showToast(
        "Camera API not available. Running in PyQt5 desktop mode?",
        5000,
      );
      return false;
    }

    try {
      // Use 'user' facingMode (ideal) to target the built-in laptop webcam.
      // 'ideal' means the browser won't throw OverconstrainedError if the
      // device doesn't report a facing mode (common on laptops).
      currentStream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: "user" },
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
        audio: false,
      });

      const v = $("videoFeed");
      v.srcObject = currentStream;
      v.style.display = "block";
      await v.play().catch((e) => console.warn("Video play:", e));
      showFeed();
      addLog("📷 Camera started via getUserMedia (browser).");
      return true;
    } catch (err) {
      const friendly =
        {
          NotAllowedError:
            "Camera permission denied. Please allow camera access.",
          NotFoundError: "No camera found on this device.",
          NotReadableError: "Camera is already in use by another application.",
          OverconstrainedError:
            "Camera does not support the requested settings.",
        }[err.name] || `Camera error: ${err.message}`;

      console.error("getUserMedia error:", err);
      addLog("❌ " + friendly);
      showToast(friendly, 5000);
      return false;
    }
  }

  // ── Camera stop ─────────────────────────────────────────────────────
  function stopCamera() {
    if (usingBridge) {
      Bridge.stopCamera();
      usingBridge = false;
    } else if (currentStream) {
      currentStream.getTracks().forEach((t) => t.stop());
      currentStream = null;
    }
    hideFeed();
  }

  // ── Live Camera ─────────────────────────────────────────────────────
  async function startLive() {
    if (activeMode !== null) return;

    const ok = await openCamera();
    if (!ok) return;

    activeMode = "live";
    $("statusLabel").textContent = "LIVE";
    applyUIState("live");
    addLog("🎥 Live camera started.");
  }

  function stopLive() {
    if (activeMode !== "live") return;
    stopCamera();
    activeMode = null;
    $("statusLabel").textContent = "STANDBY";
    applyUIState(null);
    addLog("⏹ Live camera stopped.");
  }

  // ── Training Camera ─────────────────────────────────────────────────
  function startTraining() {
    if (activeMode !== null) return;

    // Clear + reset modal fields
    ["tsJobId", "tsCount", "tsYarn", "tsColor"].forEach((id) => {
      const el = $(id);
      if (el) {
        el.value = "";
        el.classList.remove("input-error");
      }
    });

    $("trainingSessionModal").style.display = "flex";
    // Auto-focus first field
    setTimeout(() => $("tsJobId")?.focus(), 80);
  }

  function cancelTrainingModal() {
    $("trainingSessionModal").style.display = "none";
    // Camera does NOT start — state unchanged
  }

  async function confirmTraining() {
    // ── Validate ALL four fields (all mandatory) ──────────────────────
    const fields = [
      { id: "tsJobId", label: "Job ID" },
      { id: "tsCount", label: "Count" },
      { id: "tsYarn", label: "Yarn" },
      { id: "tsColor", label: "Color" },
    ];

    let firstError = null;
    fields.forEach((f) => {
      const el = $(f.id);
      const val = (el?.value || "").trim();
      if (!val) {
        el.classList.add("input-error");
        if (!firstError) firstError = f.label;
      } else {
        el.classList.remove("input-error");
      }
    });

    if (firstError) {
      showToast(
        `"${firstError}" is required. Please fill in all fields.`,
        3500,
      );
      $(
        fields.find((f) => $(f.id).classList.contains("input-error")).id,
      )?.focus();
      return; // stay on modal
    }

    const jobId = $("tsJobId").value.trim();
    const count = $("tsCount").value.trim();
    const yarn = $("tsYarn").value.trim();
    const color = $("tsColor").value.trim();

    // Close modal
    $("trainingSessionModal").style.display = "none";

    // Send values to bridge.py → saveTrainingSession()
    Bridge.sendTrainingSession({ jobId, count, yarn, color });

    // Update header Job ID pill
    $("jobIdLabel").textContent = jobId;

    // Start camera
    const ok = await openCamera();
    if (!ok) return;

    activeMode = "training";
    $("statusLabel").textContent = "TRAINING";
    applyUIState("training");
    addLog(
      `🎓 Training — Job: <strong>${jobId}</strong>` +
        ` · Count: ${count} · Yarn: ${yarn} · Color: ${color}`,
    );
  }

  function stopTraining() {
    if (activeMode !== "training") return;
    stopCamera();
    activeMode = null;
    $("statusLabel").textContent = "STANDBY";
    applyUIState(null);
    addLog("⏹ Training camera stopped.");
  }

  // ── Init ─────────────────────────────────────────────────────────────
  function init() {
    applyUIState(null);
    renderDefectThumbs();

    // Backdrop-click closes modals
    $("trainingSessionModal")?.addEventListener("click", (e) => {
      if (e.target === e.currentTarget) cancelTrainingModal();
    });
    $("defectModal")?.addEventListener("click", (e) => {
      if (e.target === e.currentTarget) closeDefectModal();
    });
    $("settingsModal")?.addEventListener("click", (e) => {
      if (e.target === e.currentTarget) closeSettings();
    });

    // Remove input-error highlight as user types
    ["tsJobId", "tsCount", "tsYarn", "tsColor"].forEach((id) => {
      $(id)?.addEventListener("input", () =>
        $(id).classList.remove("input-error"),
      );
    });

    // Range slider fill
    document.querySelectorAll('input[type="range"]').forEach((slider) => {
      updateRangeFill(slider);
      slider.addEventListener("input", () => updateRangeFill(slider));
      const linked = document.getElementById(
        slider.id.replace("Slider", "Value"),
      );
      if (linked) {
        linked.addEventListener("input", () => {
          slider.value = linked.value;
          updateRangeFill(slider);
        });
      }
    });

    // Color picker
    const picker = $("colorPicker");
    const preview = $("colorPreview");
    const hexDisp = $("hexValue");
    const rgbDisp = $("rgbValue");
    if (picker) {
      const updateColor = () => {
        const c = picker.value;
        if (preview) preview.style.backgroundColor = c;
        if (hexDisp) hexDisp.textContent = c.toUpperCase();
        if (rgbDisp) {
          const r = parseInt(c.substr(1, 2), 16);
          const g = parseInt(c.substr(3, 2), 16);
          const b = parseInt(c.substr(5, 2), 16);
          rgbDisp.textContent = `rgb(${r}, ${g}, ${b})`;
        }
      };
      picker.addEventListener("input", updateColor);
      updateColor();
    }
  }

  return {
    startLive,
    stopLive,
    startTraining,
    cancelTrainingModal,
    confirmTraining,
    stopTraining,
    init,
  };
})();

// ── Global: updateVideoFeedFromBase64 ────────────────────────────────
// Called by the PyQt5 main app when bridge.frame_signal fires, e.g.:
//   self.bridge.frame_signal.connect(
//     lambda b64: self.view.page().runJavaScript(
//       f"updateVideoFeedFromBase64('{b64}')"
//     )
//   )
// NOTE: "receiveFrame" is kept as an alias so either name works.
window.updateVideoFeedFromBase64 = function (base64) {
  const img = document.getElementById("bridgeFeed");
  if (!img) {
    console.error("bridgeFeed element not found!");
    return;
  }

  // Make visible if hidden
  if (img.style.display === "none" || img.style.display === "") {
    img.style.display = "block";
    console.log("bridgeFeed made visible on first frame.");
  }

  // Set the frame
  img.src = "data:image/jpeg;base64," + base64;
};

window.receiveFrame = window.updateVideoFeedFromBase64;

// ── Range Slider Fill ────────────────────────────────────────────────
function updateRangeFill(slider) {
  const pct = ((slider.value - slider.min) / (slider.max - slider.min)) * 100;
  slider.style.setProperty("--value", pct + "%");
}

// ── Bootstrap ─────────────────────────────────────────────────────────
// Script is at the very bottom of <body> — DOM is already parsed.
CameraControl.init();
let currentStream = null;

async function startDetection() {
  // Stop any previous stream
  if (currentStream) {
    currentStream.getTracks().forEach((track) => track.stop());
    currentStream = null;
  }

  try {
    const constraints = {
      video: {
        width: { ideal: 1280 },
        height: { ideal: 720 },
        facingMode: "environment", // or "user" for front camera
      },
      audio: false,
    };

    currentStream = await navigator.mediaDevices.getUserMedia(constraints);

    const videoEl = document.getElementById("videoFeed");
    videoEl.srcObject = currentStream;
    videoEl.play().catch((err) => console.warn("Video play error:", err));

    videoEl.style.display = "block";
    document.getElementById("noFeed").style.display = "none";
    document.getElementById("liveBadge").style.display = "inline-flex";
    document.getElementById("statusLabel").textContent = "ACTIVE";

    startUptime();
    addLog("Live camera feed started using browser camera");

    // Optional: keep your demo counters if you want fake defects
    // demoDefectInterval = setInterval(...);
  } catch (err) {
    console.error("Camera access error:", err);
    addLog("Failed to access camera: " + err.message);
    showToast(
      "Cannot access camera. Check permissions and that no other app is using it.",
      5000,
    );
  }
}

function stopDetection() {
  if (currentStream) {
    currentStream.getTracks().forEach((track) => track.stop());
    currentStream = null;
  }

  const videoEl = document.getElementById("videoFeed");
  if (videoEl) {
    videoEl.srcObject = null;
    videoEl.style.display = "none";
  }

  document.getElementById("noFeed").style.display = "flex";
  document.getElementById("liveBadge").style.display = "none";
  document.getElementById("statusLabel").textContent = "STANDBY";

  stopUptime();
  addLog("Live camera feed stopped.");

  // Clear demo interval if used
  if (demoDefectInterval) {
    clearInterval(demoDefectInterval);
    demoDefectInterval = null;
  }
}
