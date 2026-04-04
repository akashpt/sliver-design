// ─── Clock ──────────────────────────────────────────────────────────
setInterval(() => {
  document.getElementById("clock").textContent = new Date()
    .toTimeString()
    .slice(0, 8);
}, 1000);

// ─── Global Variables ───────────────────────────────────────────────
let isRunning = false;
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
let defectPollingInterval = null;
let defectHistory = [];
let defectImageSet = new Set(); // ⭐ ADD THIS LINE
let currentModalIndex = -1;

// ─── Bridge & Initialization ────────────────────────────────────────
document.addEventListener("DOMContentLoaded", function () {
  new QWebChannel(qt.webChannelTransport, async function (channel) {
    bridge = channel.objects.bridge;
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

  // Enable OK button check
  jobIdInput.addEventListener("change", checkCanConfirm);
  thresholdInput.addEventListener("input", checkCanConfirm);
});

// document.addEventListener("DOMContentLoaded", () => {
//   loadDefectImagesFromBridge();
// });

const USER_CONFIG_KEY = "userConfig"; // localStorage key (fallback)
const USER_CONFIG_DEFAULTS = { jobId: "", threshold: "" };

/**
 * Populate the two input fields from saved config.
 * Called once on DOMContentLoaded (after bridge is ready).
 */
// async function populateInputsFromConfig() {

//   // const cfg = await readUserConfig();

//   const jobInput = document.getElementById("jobIdInput");
//   const thresholdInput = document.getElementById("thresholdInput");

//   if (!jobInput || !thresholdInput) return;

//   // jobIdInput is a <select> — only set if the option exists
//   if (cfg.jobId) {
//     const matchingOption = [...jobInput.options].find(
//       (o) => o.value === cfg.jobId,
//     );
//     if (matchingOption) {
//       jobInput.value = cfg.jobId;
//     } else {
//       // Option not loaded yet (async job list). Store for deferred assignment.
//       jobInput.dataset.pendingValue = cfg.jobId;
//     }
//   }

//   // thresholdInput is a plain text/number input
//   if (cfg.threshold) {
//     thresholdInput.value = cfg.threshold;
//   }

//   checkCanConfirm();

//   if (cfg.jobId || cfg.threshold) {
//     showToast(
//       `📂 Config loaded — Job: ${cfg.jobId || "—"} | Threshold: ${cfg.threshold || "—"}`,
//       3000,
//     );
//   }
// }

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

    // Primary: Qt bridge → bridge.current_job_id()
    if (bridge && typeof bridge.current_job_id === "function") {
      try {
        const raw = await bridge.current_job_id();
        if (raw) {
          const parsed = JSON.parse(raw);
          // alert(parsed.data.jobs);
          jobs = parsed?.data?.jobs ?? [];
          thresholds = parsed?.data?.thresholds ?? [];
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
      // Select the matching option in the dropdown
      const match = [...jobSelect.options].find((o) => o.value === presetJobId);

      if (match) {
        jobSelect.value = presetJobId;
      }
      if (presetThreshold) {
        thresholdInput.value = presetThreshold;
      }

      if (match && presetThreshold) {
        // Lock the dropdown — value is set by the system
        jobSelect.disabled = true;
        jobSelect.style.opacity = "0.6";
        jobSelect.style.cursor = "not-allowed";

        thresholdInput.disabled = true;
        thresholdInput.style.opacity = "0.6";
        thresholdInput.style.cursor = "not-allowed";

        currentThreshold = presetThreshold;
      }

      // Mirror into currentJobId so confirmConfig works immediately
      currentJobId = presetJobId;
      const label = document.getElementById("jobIdLabel");
      if (label) label.textContent = presetJobId;
    }

    // If both preset values are present, treat config as already confirmed
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

    images.forEach((src) => {
      if (!src || typeof src !== "string" || src.trim() === "") return;

      // ✅ MATCH CHECK
      if (!defectImageSet.has(src)) {
        defectImageSet.add(src);

        defectHistory.unshift({
          time: new Date().toLocaleTimeString(),
          src: src,
        });

        console.log("🔥 DEFECT ADDED:", src);

        bad++; // increase defective counter
      }
    });

    renderDefectThumbs();
    updateCounters();
  } catch (err) {
    console.error("❌ Failed loading defect images:", err);
  }
}
// count add ------------------------------------------
async function loadCountsFromBridge() {
  try {
    if (!bridge || typeof bridge.get_counts !== "function") {
      console.warn("Counts API not available");
      return;
    }

    const raw = await bridge.get_counts(currentJobId);
    const parsed = JSON.parse(raw);

    // ✅ SET GLOBAL VARIABLES
    inspected = parsed.inspected || 0;
    good = parsed.good || 0;
    bad = parsed.defective || 0;

    // ✅ UPDATE UI
    updateCounters();

    console.log("✅ Counts Loaded", parsed);
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
  document.getElementById("jobIdLabel").textContent = jobId;

  // Lock both inputs after confirmation
  const jobSelect = document.getElementById("jobIdInput");
  const thresholdInput = document.getElementById("thresholdInput");

  jobSelect.disabled = true;
  jobSelect.style.opacity = "0.6";
  jobSelect.style.cursor = "not-allowed";
  thresholdInput.disabled = true;
  thresholdInput.style.opacity = "0.6";
  thresholdInput.style.cursor = "not-allowed";

  // Persist confirmed values immediately (no debounce)
  // writeUserConfig(jobId, threshold);

  showToast(
    `✅ Configuration Confirmed!<br>Job: ${jobId} | Threshold: ${threshold}`,
    4000,
  );
  addLog(`Configuration Confirmed → Job: ${jobId}, Threshold: ${threshold}`);

  document.getElementById("startBtn").disabled = false;
  document.getElementById("okBtn").disabled = true;
}

// ─── Reset Configuration ────────────────────────────────────────────
function resetConfig() {
  const jobSelect = document.getElementById("jobIdInput");
  const thresholdInput = document.getElementById("thresholdInput");

  jobSelect.value = "";
  thresholdInput.value = "";
  currentJobId = "";
  currentThreshold = "";
  document.getElementById("jobIdLabel").textContent = "—";

  // Re-enable fields that may have been locked by bridge preset
  jobSelect.disabled = false;
  jobSelect.style.opacity = "1";
  jobSelect.style.cursor = "pointer";
  thresholdInput.disabled = false;
  thresholdInput.style.opacity = "1";
  thresholdInput.style.cursor = "pointer";

  enableSideMenu(); // Re-enable menu on reset

  document.getElementById("startBtn").disabled = true;
  document.getElementById("okBtn").disabled = true;

  // Persist the cleared state so next launch starts blank
  // writeUserConfig("", "");

  showToast("Configuration Reset", 2500);
  addLog("Configuration Reset");
}

// ─── Reset to Initial State ─────────────────────────────────────────
function resetToInitialState() {
  isRunning = false;
  stopAllCameras();

  document.getElementById("startBtn").disabled = true;
  document.getElementById("stopBtn").disabled = true;
  document.getElementById("okBtn").disabled = true;
  document.getElementById("resetBtn").disabled = false;

  document.getElementById("jobIdInput").disabled = false;
  document.getElementById("thresholdInput").disabled = false;

  enableSideMenu(); // Ensure menu is enabled initially

  hideCameraFeed();
  document.getElementById("statusLabel").textContent = "STANDBY";
  document.getElementById("jobIdLabel").textContent = "—";
  inspected = 0;
  good = 0;
  bad = 0;
  updateCounters();
}

// ─── Camera Helpers ─────────────────────────────────────────────────
function showCameraFeed() {
  const videoFeed = document.getElementById("videoFeed");
  const noFeed = document.getElementById("noFeed");
  const liveBadge = document.getElementById("liveBadge");
  const cameraWrap = document.querySelector(".camera-wrap");

  // Make sure container is visible
  if (cameraWrap) cameraWrap.style.display = "block";

  disableSideMenu(); // Disable menu after start

  noFeed.style.display = "none";
  videoFeed.style.display = "block"; // Show video element initially
  if (liveBadge) liveBadge.style.display = "flex";

  // Remove any previous qtFrameImg so we start clean
  const existingQtImg = document.getElementById("qtFrameImg");
  if (existingQtImg) existingQtImg.remove();
}

function hideCameraFeed() {
  const videoFeed = document.getElementById("videoFeed");
  const noFeed = document.getElementById("noFeed");
  const liveBadge = document.getElementById("liveBadge");
  const cameraWrap = document.querySelector(".camera-wrap");

  // Stop any stream
  stopAllCameras();

  noFeed.style.display = "flex";
  videoFeed.style.display = "none";
  if (liveBadge) liveBadge.style.display = "none";

  // Remove Qt frame image completely when hiding
  const existingQtImg = document.getElementById("qtFrameImg");
  if (existingQtImg) existingQtImg.remove();
}

function hideCameraFeed() {
  const videoFeed = document.getElementById("videoFeed");
  const noFeed = document.getElementById("noFeed");
  const liveBadge = document.getElementById("liveBadge");

  videoFeed.style.display = "none";
  noFeed.style.display = "flex";
  if (liveBadge) liveBadge.style.display = "none";
}

function stopAllCameras() {
  if (currentStream) {
    currentStream.getTracks().forEach((track) => track.stop());
    currentStream = null;
  }

  // Also stop Qt bridge camera if available
  if (bridge && typeof bridge.stopCamera === "function") {
    try {
      bridge.stopCamera();
    } catch (e) {
      console.warn("Bridge stopCamera failed:", e);
    }
  }

  hideCameraFeed(); // This will now properly clean up
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

  if (!defectPollingInterval) {
    defectPollingInterval = setInterval(loadDefectImagesFromBridge, 2000);
  }

  showCameraFeed();
  loadCountsFromBridge();
  document.getElementById("statusLabel").textContent = "ACTIVE";

  setUIState(true);
  startUptime();

  addLog(`Detection Started - Job ID: ${currentJobId}`);

  if (bridge && typeof bridge.startCamera === "function") {
    try {
      bridge.startCamera();
      showToast("✅ Industrial Camera Started via Bridge", 2500);

      // Connect frame signal (only once)
      if (bridge.frame_signal && !bridge.frame_signal._connected) {
        bridge.frame_signal.connect((base64Image) => {
          updateVideoFeedFromBase64(base64Image);
        });
        bridge.frame_signal._connected = true;
      }
    } catch (e) {
      console.error(e);
      startLaptopWebcam();
    }
  } else {
    startLaptopWebcam();
  }

  // Demo defect simulation
  demoDefectInterval = setInterval(() => {
    inspected++;
    const isDefect = Math.random() < 0.3;

    if (isDefect) {
      const randomSrc = [Math.floor(Math.random())];

      defectHistory.unshift({
        time: new Date().toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
        }),
        src: randomSrc,
      });

      if (defectHistory.length > 10) defectHistory.pop();

      addLog('<span style="color:#ef233c">⚠️ DEFECT DETECTED</span>');
      renderDefectThumbs();
    } else {
      good++;
    }
    updateCounters();
  }, 5000);
}

// ─── Stop Detection ─────────────────────────────────────────────────
function stopDetection() {
  if (!isRunning) return;

  // Stop everything
  stopAllCameras();

  if (bridge && typeof bridge.stopCamera === "function") {
    try {
      bridge.stopCamera();
    } catch (e) {
      console.error("Error stopping camera via bridge:", e);
    }
  }

  if (demoDefectInterval) {
    clearInterval(demoDefectInterval);
    demoDefectInterval = null;
  }
  if (defectPollingInterval) {
    clearInterval(defectPollingInterval);
    defectPollingInterval = null;
  }
  stopUptime();
  setUIState(false);

  document.getElementById("statusLabel").textContent = "STANDBY";

  // IMPORTANT: Re-enable side menu when stopping
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
    startBtn.disabled = false; // ← Fixed: Allow starting again
    stopBtn.disabled = true;
    jobSelect.disabled = true;
    thresholdInput.disabled = true;
    okBtn.disabled = true; // Allow re-config if needed
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
    // Create Qt image only when first frame arrives
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

    // Hide the <video> element when using Qt frames
    if (videoEl) videoEl.style.display = "none";

    videoContainer.appendChild(feedImg);
  }

  // Update the source
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
    // ✅ SKIP INVALID IMAGE FIRST
    if (!defect.src || typeof defect.src !== "string") {
      console.warn("Skipping invalid defect:", defect);
      return;
    }

    const thumbWrapper = document.createElement("div");
    thumbWrapper.className = "defect-thumb";

    thumbWrapper.innerHTML = `
      <img src="${defect.src}" alt="Defect">
  <div class="defect-time">${defect.time}</div>
  `;

    thumbWrapper.onclick = () => openDefectModal(index);

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

// function downloadDefectImage() {
//   if (currentModalIndex < 0 || currentModalIndex >= defectHistory.length)
//     return;
//   const defect = defectHistory[currentModalIndex];
//   const link = document.createElement("a");
//   link.href = defect.src;
//   link.download = `sliver_defect_${currentModalIndex + 1}_${Date.now()}.jpg`;
//   document.body.appendChild(link);
//   link.click();
//   document.body.removeChild(link);
//   showToast("✅ Defect image downloaded", 2500);
// }

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

// defect image zoom
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

// ===================
// APPLY TRANSFORM
// ===================
function updateTransform() {
  image.style.transform = `translate3d(${posX}px, ${posY}px, 0) scale(${zoomLevel})`;
}

// ===================
// RESET FUNCTION
// ===================
function resetView() {
  zoomLevel = 1;
  posX = 0;
  posY = 0;
  updateTransform();
}

// ===================
// ZOOM IN
// ===================
zoomInBtn.onclick = () => {
  if (zoomLevel < maxZoom) {
    zoomLevel += zoomStep;
    updateTransform();
  }
};

// ===================
// ZOOM OUT
// ===================
zoomOutBtn.onclick = () => {
  if (zoomLevel > minZoom) {
    zoomLevel -= zoomStep;

    if (zoomLevel <= 1) {
      resetView(); // ⭐ FIX
      return;
    }

    updateTransform();
  }
};

// ===================
// RESET BUTTON
// ===================
resetBtn.onclick = resetView;

// ===================
// DRAG START
// ===================
viewer.addEventListener("mousedown", (e) => {
  if (zoomLevel <= 1) return;

  isDragging = true;
  viewer.classList.add("dragging");

  startX = e.clientX - posX;
  startY = e.clientY - posY;
});

// ===================
// DRAG MOVE
// ===================
window.addEventListener("mousemove", (e) => {
  if (!isDragging) return;

  posX = e.clientX - startX;
  posY = e.clientY - startY;

  updateTransform();
});

// ===================
// DRAG END
// ===================
window.addEventListener("mouseup", () => {
  isDragging = false;
  viewer.classList.remove("dragging");
});
// mouse wheel scrool
viewer.addEventListener("wheel", (e) => {
  e.preventDefault();

  const rect = viewer.getBoundingClientRect();

  // mouse position inside viewer
  const mouseX = e.clientX - rect.left;
  const mouseY = e.clientY - rect.top;

  const scaleAmount = 0.1;

  let newZoom =
    e.deltaY < 0
      ? zoomLevel + scaleAmount // scroll up
      : zoomLevel - scaleAmount; // scroll down

  // limit zoom
  newZoom = Math.min(maxZoom, Math.max(minZoom, newZoom));

  // stop if same zoom
  if (newZoom === zoomLevel) return;

  // 🔥 zoom towards mouse position
  const zoomRatio = newZoom / zoomLevel;

  posX = mouseX - (mouseX - posX) * zoomRatio;
  posY = mouseY - (mouseY - posY) * zoomRatio;

  zoomLevel = newZoom;

  // auto reset when normal size
  if (zoomLevel <= 1) {
    resetView();
    return;
  }

  updateTransform();
});
