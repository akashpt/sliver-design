


// ─── Clock ──────────────────────────────────────────────────────────
setInterval(() => {
  document.getElementById("clock").textContent = new Date()
    .toTimeString()
    .slice(0, 8);
}, 1000);

// ─── Global Variables ───────────────────────────────────────────────
let isRunning = false;
let isUIReset = false;
let currentJobId = "";
let currentThreshold = "";
let inspected = 0;
let good = 0;
let bad = 0;
let sessionStart = null;
let uptimeTimer = null;
let demoDefectInterval = null;
let bridge = null;
let currentStream = null;
let frameSignalConnected = false; // FIX: safe guard for frame_signal connection

let defectHistory = [];
let currentModalIndex = -1;

// ─── Bridge & Initialization ────────────────────────────────────────
document.addEventListener("DOMContentLoaded", function () {
  new QWebChannel(qt.webChannelTransport, async function (channel) {
    bridge = channel.objects.bridge;

    // FIX: properly indented inside QWebChannel callback
    // ─── Connect counts_signal ───────────────────────────────────────
    if (bridge.counts_signal) {
      bridge.counts_signal.connect(function (data) {
        if (isUIReset) return; // 🔥 BLOCK backend updates

        console.log("📊 Counts Signal Received:", data);
        const parsed = JSON.parse(data);
        inspected = parsed.inspected || 0;
        good = parsed.good || 0;
        bad = parsed.defective || 0;
        updateCounters();
      });
    }

    // ─── Connect defect_images_signal ────────────────────────────────
    // FIX: was never connected in original — now connected for real-time push
    if (bridge.defect_images_signal) {
      bridge.defect_images_signal.connect(function (data) {
        console.log("🖼️ Defect Images Signal Received:", data);
        const parsed = JSON.parse(data);
        const images = parsed?.images || [];

        defectHistory = [];
        images.forEach((src) => {
          if (!src) return;
          defectHistory.push({
            time: new Date().toLocaleTimeString(),
            src: src,
          });
        });

        renderDefectThumbs();
      });
    }

    if (bridge) {
      showToast("✅ Bridge Connected Successfully", 3000);
    } else {
      showToast("⚠️ No Qt Bridge - Using Laptop Webcam", 4000, "warning");
    }

    // Load dropdowns (jobs + thresholds) from bridge, then restore saved config
    await loadDropdownData();
    await loadDefectImagesFromBridge();
  });

  renderDefectThumbs();
  resetToInitialState();

  const jobIdInput = document.getElementById("jobIdInput");
  const thresholdInput = document.getElementById("thresholdInput");

  jobIdInput.addEventListener("change", checkCanConfirm);
  thresholdInput.addEventListener("input", checkCanConfirm);
});

const USER_CONFIG_KEY = "userConfig";
const USER_CONFIG_DEFAULTS = { jobId: "", threshold: "" };

/**
 * Debounce helper — prevents flooding the bridge on every keystroke.
 */
function debounce(fn, delay) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}

// ─── Fetch Job IDs & Thresholds from Bridge ─────────────────────────
async function loadDropdownData() {
  try {
    let jobs = [];
    let thresholds = [];
    let presetJobId = "";
    let presetThreshold = "";

    if (bridge && typeof bridge.current_job_id === "function") {
      try {
        const raw = await bridge.current_job_id();
        if (raw) {
          const parsed = JSON.parse(raw);
          jobs = parsed?.data?.jobs ?? [];
          thresholds = parsed?.data?.thresholds ?? [];
          // FIX: bridge.py returns "job_id" key (not "jobId") — read correctly
          presetJobId = String(parsed?.job_id ?? "");
          presetThreshold = String(parsed?.threshold ?? "");
        }
      } catch (e) {
        console.warn("[Dropdown] Bridge current_job_id failed:", e);
      }
    }

    // ── Populate Job ID <select> ──────────────────────────────────────
    const jobSelect = document.getElementById("jobIdInput");
    jobSelect.innerHTML =
      '<option value="" disabled selected hidden>Select Job ID</option>';
    jobs.forEach((job) => {
      const option = document.createElement("option");
      option.value = job;
      option.textContent = job;
      jobSelect.appendChild(option);
    });

    // ── Override THRESHOLD_SUGGESTIONS with bridge values ─────────────
    if (thresholds.length > 0) {
      THRESHOLD_SUGGESTIONS.length = 0;
      thresholds.forEach((t) => THRESHOLD_SUGGESTIONS.push(String(t)));
    }

    // ── Auto-fill & disable when bridge provides preset values ─────────
    const thresholdInput = document.getElementById("thresholdInput");

    if (presetJobId) {
      const match = [...jobSelect.options].find((o) => o.value === presetJobId);

      if (match) {
        jobSelect.value = presetJobId;
      }
      if (presetThreshold) {
        thresholdInput.value = presetThreshold;
      }

      if (match && presetThreshold) {
        jobSelect.disabled = true;
        jobSelect.style.opacity = "0.6";
        jobSelect.style.cursor = "not-allowed";

        thresholdInput.disabled = true;
        thresholdInput.style.opacity = "0.6";
        thresholdInput.style.cursor = "not-allowed";

        currentThreshold = presetThreshold;
      }

      currentJobId = presetJobId;
      const label = document.getElementById("jobIdLabel");
      if (label) label.textContent = presetJobId;
    }

    if (presetJobId && presetThreshold) {
      document.getElementById("okBtn").disabled = true;
      document.getElementById("startBtn").disabled = false;
      showToast(
        `🔒 Auto-configured — Job: ${presetJobId} | Threshold: ${presetThreshold}`,
        4000,
      );
      addLog(
        `[Bridge] Auto-config applied → Job: ${presetJobId}, Threshold: ${presetThreshold}`,
      );
    } else {
      checkCanConfirm();
    }
  } catch (error) {
    console.error("[Dropdown] loadDropdownData error:", error);
  }
}

async function loadDefectImagesFromBridge() {
  try {
    if (!bridge || typeof bridge.get_defect_images !== "function") {
      console.warn("Bridge not available");
      return;
    }

    const raw = await bridge.get_defect_images();
    const parsed = JSON.parse(raw);
    const images = parsed?.images || [];

    defectHistory = [];

    images.forEach((src) => {
      if (!src) return;
      defectHistory.push({
        time: new Date().toLocaleTimeString(),
        src: src,
      });
    });

    console.log("✅ Defect images loaded:", images.length);
    renderDefectThumbs();
  } catch (err) {
    console.error("❌ Failed loading defect images:", err);
  }
}

// ─── Load Counts from Bridge ─────────────────────────────────────────
function loadCountsFromBridge() {
  try {
    if (!bridge || typeof bridge.get_counts !== "function") {
      console.warn("Counts API not available");
      return;
    }

    if (!currentJobId) {
      console.warn("❌ No Job ID — skipping get_counts");
      return;
    }

    console.log("📡 Calling get_counts with:", currentJobId);

    bridge.get_counts(currentJobId, function (raw) {
      console.log("🔥 CALLBACK RESPONSE:", raw);

      try {
        const parsed = JSON.parse(raw);

        inspected = parsed.inspected || 0;
        good = parsed.good || 0;
        bad = parsed.defective || 0;

        updateCounters();

        console.log("✅ Counts Loaded", parsed);
      } catch (e) {
        console.error("❌ JSON parse error:", e);
      }
    });

  } catch (err) {
    console.error("❌ Failed to load counts:", err);
  }
}

// ─── Side Menu Control ──────────────────────────────────────────────
function disableSideMenu() {
  const menuItems = [
    document.getElementById("menuDashboard"),
    document.getElementById("menuReport"),
    document.getElementById("menuController"),
    document.getElementById("menuTraining"),
    document.getElementById("menuSettings"),
    document.getElementById("jobIdInput"),
    document.getElementById("thresholdInput"),
  ];

  menuItems.forEach((item) => {
    if (item) {
      item.style.pointerEvents = "none";
      item.style.opacity = "0.5";
      item.style.cursor = "not-allowed";
    }
  });
}

function enableSideMenu() {
  const menuItems = [
    document.getElementById("menuDashboard"),
    document.getElementById("menuReport"),
    document.getElementById("menuController"),
    document.getElementById("menuTraining"),
    document.getElementById("menuSettings"),
    document.getElementById("jobIdInput"),
    document.getElementById("thresholdInput"),
  ];

  menuItems.forEach((item) => {
    if (item) {
      item.style.pointerEvents = "auto";
      item.style.opacity = "1";
      item.style.cursor = "pointer";
    }
  });
}

// ─── Enable OK button ───────────────────────────────────────────────
function checkCanConfirm() {
  const jobId = document.getElementById("jobIdInput").value.trim();
  const threshold = document.getElementById("thresholdInput").value.trim();
  document.getElementById("okBtn").disabled = !(jobId && threshold);
}

// ─── Confirm Configuration ──────────────────────────────────────────
function confirmConfig() {
  const jobId = document.getElementById("jobIdInput").value;
  const threshold = document.getElementById("thresholdInput").value.trim();

  if (!jobId || !threshold) {
    showToast("❌ Please select Job ID and enter Threshold", 3000, "error");
    return;
  }

  currentJobId = jobId;
  currentThreshold = threshold;
  saveUserConfigToBridge(jobId, threshold);
  loadCountsFromBridge();
  document.getElementById("jobIdLabel").textContent = jobId;

  const jobSelect = document.getElementById("jobIdInput");
  const thresholdInput = document.getElementById("thresholdInput");

  jobSelect.disabled = true;
  jobSelect.style.opacity = "0.6";
  jobSelect.style.cursor = "not-allowed";
  thresholdInput.disabled = true;
  thresholdInput.style.opacity = "0.6";
  thresholdInput.style.cursor = "not-allowed";

  showToast(
    `✅ Configuration Confirmed!<br>Job: ${jobId} | Threshold: ${threshold}`,
    4000,
  );
  addLog(`Configuration Confirmed → Job: ${jobId}, Threshold: ${threshold}`);

  document.getElementById("startBtn").disabled = false;
  document.getElementById("okBtn").disabled = true;
}

function resetConfig() {
  const jobSelect = document.getElementById("jobIdInput");
  const thresholdInput = document.getElementById("thresholdInput");

  jobSelect.value = "";
  thresholdInput.value = "";
  currentJobId = "";
  currentThreshold = "";
  document.getElementById("jobIdLabel").textContent = "—";

  // ❌ REMOVE this (important)
  // saveUserConfigToBridge(currentJobId, currentThreshold);

  jobSelect.disabled = false;
  jobSelect.style.opacity = "1";
  jobSelect.style.cursor = "pointer";
  thresholdInput.disabled = false;
  thresholdInput.style.opacity = "1";
  thresholdInput.style.cursor = "pointer";

  enableSideMenu();

  document.getElementById("startBtn").disabled = true;
  document.getElementById("okBtn").disabled = true;

  // 🔥 UI RESET
  isUIReset = true;

  inspected = 0;
  good = 0;
  bad = 0;

  updateCounters();

  // reset uptime
  stopUptime();

  // 🔥 AUTO RESUME (THIS IS THE FIX FOR YOUR ISSUE)
  setTimeout(() => {
    isUIReset = false;

    // reload real counts
    if (currentJobId) {
      loadCountsFromBridge();
    }
  }, 2000);

  showToast("Configuration Reset", 2500);
  addLog("Configuration Reset (UI only)");
}
function resetToInitialState() {
  isRunning = false;
  stopAllCameras();

  document.getElementById("startBtn").disabled = true;
  document.getElementById("stopBtn").disabled = true;
  document.getElementById("okBtn").disabled = true;
  document.getElementById("resetBtn").disabled = false;

  document.getElementById("jobIdInput").disabled = false;
  document.getElementById("thresholdInput").disabled = false;

  enableSideMenu();

  hideCameraFeed();
  document.getElementById("statusLabel").textContent = "STANDBY";
  document.getElementById("jobIdLabel").textContent = "—";

  // 🔥 ALSO APPLY UI RESET MODE HERE
  isUIReset = true;

  inspected = 0;
  good = 0;
  bad = 0;

  updateCounters();

  stopUptime();
}
// ─── Camera Helpers ─────────────────────────────────────────────────
function showCameraFeed() {
  const videoFeed = document.getElementById("videoFeed");
  const noFeed = document.getElementById("noFeed");
  const liveBadge = document.getElementById("liveBadge");
  const cameraWrap = document.querySelector(".camera-wrap");

  if (cameraWrap) cameraWrap.style.display = "block";

  disableSideMenu();

  noFeed.style.display = "none";
  videoFeed.style.display = "block";
  if (liveBadge) liveBadge.style.display = "flex";

  const existingQtImg = document.getElementById("qtFrameImg");
  if (existingQtImg) existingQtImg.remove();
}

// FIX: removed duplicate hideCameraFeed() — keeping only the full version
function hideCameraFeed() {
  const videoFeed = document.getElementById("videoFeed");
  const noFeed = document.getElementById("noFeed");
  const liveBadge = document.getElementById("liveBadge");
  const cameraWrap = document.querySelector(".camera-wrap");

  noFeed.style.display = "flex";
  videoFeed.style.display = "none";
  if (liveBadge) liveBadge.style.display = "none";

  // Remove Qt frame image completely when hiding
  const existingQtImg = document.getElementById("qtFrameImg");
  if (existingQtImg) existingQtImg.remove();
}

function stopAllCameras() {
  if (currentStream) {
    currentStream.getTracks().forEach((track) => track.stop());
    currentStream = null;
  }

  if (bridge && typeof bridge.stopCamera === "function") {
    try {
      bridge.stopCamera();
    } catch (e) {
      console.warn("Bridge stopCamera failed:", e);
    }
  }

  hideCameraFeed();
}

// ─── Start Laptop Webcam (Fallback) ─────────────────────────────────
async function startLaptopWebcam() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment" },
    });
    currentStream = stream;

    const videoElement = document.getElementById("videoFeed");
    videoElement.srcObject = stream;
    await videoElement.play();

    showToast("✅ Laptop Webcam Started", 2500);
  } catch (err) {
    console.error("Webcam error:", err);
    showToast(
      "❌ Could not access laptop camera. Check permissions.",
      4000,
      "error",
    );
  }
}

// ─── Start Detection ────────────────────────────────────────────────
function startDetection() {
  if (isRunning || !currentJobId || !currentThreshold) {
    showToast("❌ Please click OK first", 3000, "error");
    return;
  }

  showCameraFeed();
  loadCountsFromBridge();

  document.getElementById("statusLabel").textContent = "ACTIVE";

  setUIState(true);
  startUptime();

  addLog(`Detection Started - Job ID: ${currentJobId}`);

  // ─── CAMERA START ─────────────────────────────────────
  if (bridge && typeof bridge.startCamera === "function") {
    try {
      bridge.startCamera();
      showToast("✅ Camera Started", 2500);

      if (bridge.frame_signal && !frameSignalConnected) {
        bridge.frame_signal.connect((base64Image) => {
          updateVideoFeedFromBase64(base64Image);
        });
        frameSignalConnected = true;
      }

    } catch (e) {
      console.error(e);
      startLaptopWebcam();
    }
  } else {
    startLaptopWebcam();
  }


  // ─── 🔥 COUNT SIMULATION (ALWAYS RUN) ─────────────────
  // (You can later replace this with real AI detection)

  demoDefectInterval = setInterval(() => {

    const isDefect = Math.random() < 0.3;

    if (bridge && typeof bridge.update_counts === "function") {

      if (isDefect) {
        // DEFECT
        bridge.update_counts(currentJobId, 1, 0, 1);

        defectHistory.unshift({
          time: new Date().toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          }),
          src: "https://placehold.co/640x480/ef233c/white?text=DEFECT",
        });

        if (defectHistory.length > 10) defectHistory.pop();

        addLog('<span style="color:#ef233c">⚠️ DEFECT DETECTED</span>');
        renderDefectThumbs();

      } else {
        // GOOD
        bridge.update_counts(currentJobId, 1, 1, 0);
      }

    } else {
      console.warn("⚠️ update_counts not available");
    }

  }, 3000); // faster for testing (3 sec)

}

// ─── Stop Detection ─────────────────────────────────────────────────
function stopDetection() {
  if (!isRunning) return;

  // FIX: stopAllCameras() already calls bridge.stopCamera() internally
  // removed the redundant explicit bridge.stopCamera() call
  stopAllCameras();

  if (demoDefectInterval) {
    clearInterval(demoDefectInterval);
    demoDefectInterval = null;
  }

  stopUptime();
  setUIState(false);

  document.getElementById("statusLabel").textContent = "STANDBY";

  enableSideMenu();

  showToast("🛑 Detection Stopped", 3000);
  addLog("Detection Stopped");
}

// ─── UI State ───────────────────────────────────────────────────────
function setUIState(running) {
  isRunning = running;
  const startBtn = document.getElementById("startBtn");
  const stopBtn = document.getElementById("stopBtn");
  const jobSelect = document.getElementById("jobIdInput");
  const thresholdInput = document.getElementById("thresholdInput");
  const okBtn = document.getElementById("okBtn");
  const resetBtn = document.getElementById("resetBtn");

  if (running) {
    startBtn.disabled = true;
    stopBtn.disabled = false;
    jobSelect.disabled = true;
    thresholdInput.disabled = true;
    okBtn.disabled = true;
    resetBtn.disabled = true;
  } else {
    startBtn.disabled = false;
    stopBtn.disabled = true;
    jobSelect.disabled = true;
    thresholdInput.disabled = true;
    okBtn.disabled = true;
    resetBtn.disabled = false;
  }
}

// ─── Counters & Uptime ──────────────────────────────────────────────
function updateCounters() {
  document.getElementById("inspectedCount").textContent = inspected;
  document.getElementById("goodCount").textContent = good;
  document.getElementById("badCount").textContent = bad;
}

function startUptime() {
  sessionStart = Date.now();
  uptimeTimer = setInterval(() => {
    const s = Math.floor((Date.now() - sessionStart) / 1000);
    document.getElementById("uptimeVal").textContent =
      `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  }, 1000);
}

function stopUptime() {
  if (uptimeTimer) clearInterval(uptimeTimer);
  document.getElementById("uptimeVal").textContent = "0:00";
}

// ─── Qt Frame Display ───────────────────────────────────────────────
function updateVideoFeedFromBase64(base64Image) {
  let feedImg = document.getElementById("qtFrameImg");
  const videoContainer = document.querySelector(".camera-wrap");
  const videoEl = document.getElementById("videoFeed");

  if (!feedImg) {
    feedImg = document.createElement("img");
    feedImg.id = "qtFrameImg";
    feedImg.style.cssText = `
      width: 100%; 
      height: 100%; 
      object-fit: cover; 
      background: #000;
      border-radius: 6px;
      display: block;
    `;

    if (videoEl) videoEl.style.display = "none";

    videoContainer.appendChild(feedImg);
  }

  feedImg.src = "data:image/jpeg;base64," + base64Image;
}

// ─── Defect Functions ───────────────────────────────────────────────
function renderDefectThumbs() {
  const slider = document.getElementById("defectsSlider");
  if (!slider) return;

  slider.innerHTML = "";

  if (defectHistory.length === 0) {
    const empty = document.createElement("div");
    empty.style.cssText =
      "padding: 30px 20px; color: #888; font-style: italic; text-align: center; width: 100%;";
    empty.textContent = "No defects detected yet";
    slider.appendChild(empty);
    return;
  }

  defectHistory.forEach((defect, index) => {
    const thumbWrapper = document.createElement("div");
    thumbWrapper.className = "defect-thumb";
    thumbWrapper.style.cssText = `
      width: 118px; height: 88px; flex-shrink: 0; border-radius: 8px;
      overflow: hidden; cursor: pointer; border: 2px solid #444;
      position: relative; box-shadow: 0 3px 10px rgba(0,0,0,0.4);
      transition: all 0.25s ease;
    `;

    thumbWrapper.innerHTML = `
      <img src="${defect.src}" style="width:100%;height:100%;object-fit:cover;margin-left:10px;margin-right:10px;display:block;" alt="Defect">
      <div style="position:absolute;bottom:0;left:0;right:0;background:linear-gradient(transparent,rgba(0,0,0,0.85));color:white;font-size:0.78rem;padding:6px 8px 5px;text-align:center;font-weight:500;">
        ${defect.time || "DEFECT"}
      </div>
    `;

    thumbWrapper.onclick = () => openDefectModal(index);
    thumbWrapper.onmouseenter = () =>
      (thumbWrapper.style.borderColor = "#ef233c");
    thumbWrapper.onmouseleave = () => (thumbWrapper.style.borderColor = "#444");

    slider.appendChild(thumbWrapper);
  });
}

function openDefectModal(index) {
  currentModalIndex = index;
  const modal = document.getElementById("defectModal");
  if (!modal) return;
  updateModalImage();
  modal.style.display = "flex";
}

function updateModalImage() {
  if (currentModalIndex < 0 || currentModalIndex >= defectHistory.length)
    return;
  const defect = defectHistory[currentModalIndex];
  const imgElement = document.getElementById("defectModalImage");
  const positionElement = document.getElementById("defectModalPosition");

  if (imgElement) imgElement.src = defect.src;
  if (positionElement) {
    positionElement.textContent = `${currentModalIndex + 1} / ${defectHistory.length} — ${defect.time || "Sample"}`;
  }
}

function changeDefect(direction) {
  currentModalIndex += direction;
  if (currentModalIndex < 0) currentModalIndex = defectHistory.length - 1;
  if (currentModalIndex >= defectHistory.length) currentModalIndex = 0;
  updateModalImage();
}

function closeDefectModal() {
  const modal = document.getElementById("defectModal");
  if (modal) modal.style.display = "none";
}

// ─── Toast & Log ────────────────────────────────────────────────────
function showToast(msg, ms = 3500, type = "success") {
  const toast = document.getElementById("toast");
  const toastMsg = document.getElementById("toastMessage");

  toastMsg.innerHTML = msg;
  if (type === "error") toast.style.background = "#ef233c";
  else if (type === "warning") toast.style.background = "#f59e0b";
  else toast.style.background = "#16a34a";

  toast.style.display = "block";
  requestAnimationFrame(() => toast.classList.add("show"));

  setTimeout(() => {
    toast.classList.remove("show");
    setTimeout(() => {
      toast.style.display = "none";
    }, 300);
  }, ms);
}

function addLog(msg) {
  console.log(`[LOG ${new Date().toLocaleTimeString()}] ${msg}`);
}

// ─── Threshold Suggestions ──────────────────────────────────────────
const THRESHOLD_SUGGESTIONS = [""];

function filterSuggestions() {
  const input = document.getElementById("thresholdInput");
  const container = document.getElementById("thresholdSuggestionsDiv");
  const val = input.value.toLowerCase().trim();

  container.innerHTML = "";
  const filtered = THRESHOLD_SUGGESTIONS.filter(
    (s) => s.includes(val) || val === "",
  );

  filtered.forEach((s) => {
    const div = document.createElement("div");
    div.textContent = s;
    div.onclick = () => {
      input.value = s;
      container.style.display = "none";
      checkCanConfirm();
    };
    container.appendChild(div);
  });

  container.style.display = filtered.length > 0 ? "block" : "none";
}

function toggleSuggestions() {
  const container = document.getElementById("thresholdSuggestionsDiv");
  const input = document.getElementById("thresholdInput");

  if (container.style.display === "block") {
    container.style.display = "none";
  } else {
    filterSuggestions();
    input.focus();
  }
}

// Close suggestions when clicking outside
document.addEventListener("click", function (e) {
  const container = document.getElementById("thresholdSuggestionsDiv");
  const wrapper = document.querySelector(".hybrid-threshold");
  if (wrapper && !wrapper.contains(e.target)) {
    container.style.display = "none";
  }
});

// ─── Settings ───────────────────────────────────────────────────────
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
    .forEach((tab) => tab.classList.remove("active"));
  document
    .querySelectorAll(".tab-content")
    .forEach((content) => content.classList.remove("active"));

  if (tabName === "detection") {
    document.querySelector(".modal-tab:first-child").classList.add("active");
    document.getElementById("detectionTab").classList.add("active");
  } else if (tabName === "threshold") {
    document.querySelector(".modal-tab:last-child").classList.add("active");
    document.getElementById("thresholdTab").classList.add("active");
  }
}

// Modal outside click
document.getElementById("defectModal")?.addEventListener("click", (e) => {
  if (e.target === e.currentTarget) closeDefectModal();
});
document.getElementById("settingsModal")?.addEventListener("click", (e) => {
  if (e.target === e.currentTarget) closeSettings();
});

// ─── Defect Image Zoom ───────────────────────────────────────────────
const image = document.getElementById("defectModalImage");
const viewer = document.getElementById("imageViewer");

const zoomInBtn = document.getElementById("zoomInBtn");
const zoomOutBtn = document.getElementById("zoomOutBtn");
const resetBtn = document.getElementById("resetBtn");

let zoomLevel = 1;
const zoomStep = 0.2;
const maxZoom = 5;
const minZoom = 1;

let posX = 0;
let posY = 0;

let startX = 0;
let startY = 0;
let isDragging = false;

function updateTransform() {
  image.style.transform = `translate3d(${posX}px, ${posY}px, 0) scale(${zoomLevel})`;
}

function resetView() {
  zoomLevel = 1;
  posX = 0;
  posY = 0;
  updateTransform();
}

zoomInBtn.onclick = () => {
  if (zoomLevel < maxZoom) {
    zoomLevel += zoomStep;
    updateTransform();
  }
};

zoomOutBtn.onclick = () => {
  if (zoomLevel > minZoom) {
    zoomLevel -= zoomStep;

    if (zoomLevel <= 1) {
      resetView();
      return;
    }

    updateTransform();
  }
};

resetBtn.onclick = resetView;

viewer.addEventListener("mousedown", (e) => {
  if (zoomLevel <= 1) return;

  isDragging = true;
  viewer.classList.add("dragging");

  startX = e.clientX - posX;
  startY = e.clientY - posY;
});

window.addEventListener("mousemove", (e) => {
  if (!isDragging) return;

  posX = e.clientX - startX;
  posY = e.clientY - startY;

  updateTransform();
});

window.addEventListener("mouseup", () => {
  isDragging = false;
  viewer.classList.remove("dragging");
});

viewer.addEventListener("wheel", (e) => {
  e.preventDefault();

  const rect = viewer.getBoundingClientRect();

  const mouseX = e.clientX - rect.left;
  const mouseY = e.clientY - rect.top;

  const scaleAmount = 0.1;

  let newZoom =
    e.deltaY < 0
      ? zoomLevel + scaleAmount
      : zoomLevel - scaleAmount;

  newZoom = Math.min(maxZoom, Math.max(minZoom, newZoom));

  if (newZoom === zoomLevel) return;

  const zoomRatio = newZoom / zoomLevel;

  posX = mouseX - (mouseX - posX) * zoomRatio;
  posY = mouseY - (mouseY - posY) * zoomRatio;

  zoomLevel = newZoom;

  if (zoomLevel <= 1) {
    resetView();
    return;
  }

  updateTransform();
});

// ─── Save User Config to Bridge ──────────────────────────────────────
function saveUserConfigToBridge(jobId, threshold) {
  if (!bridge || typeof bridge.saveUserConfig !== "function") {
    console.log("Bridge:", bridge);
    console.log("get_counts:", bridge.get_counts);
    console.warn("Bridge saveUserConfig not available");
    return;
  }

  bridge.saveUserConfig(jobId, threshold, function (response) {
    const result = JSON.parse(response);

    if (result.status === "success") {
      // FIX: bridge.py returns { status, jobId } not { status, data: { jobId, threshold } }
      // reading result.jobId directly instead of result.data.jobId
      console.log("🟢 PROCESS CONFIRMED");
      console.log("Job:", result.jobId);

      showToast("✅ Process Confirmed", 3000);
      addLog("PROCESS CONFIRMED ✅");
    } else {
      console.error("❌ Save Failed:", result.message);
      showToast("❌ Save failed", 3000, "error");
    }
  });
}

