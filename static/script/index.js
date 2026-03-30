// =====================================================
// FULL FIXED INDEX.JS - Sliver Strip Detection System
// Fixed: Sidebar now re-enables properly when Stop is clicked
// =====================================================

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

let defectHistory = [];
let currentModalIndex = -1;

const FIXED_DEFECT_IMAGES = [
  "https://placehold.co/640x480/ff4d6d/white?text=EDGE+SLIVER",
  "https://placehold.co/640x480/ef233c/fff?text=DENT+DEFECT",
  "https://picsum.photos/seed/metaldefect1/640/480",
  "https://placehold.co/640x480/c1121f/white?text=SCRATCH+DEFECT",
  "https://picsum.photos/seed/industrialdefect/640/480",
  "https://placehold.co/640x480/d00000/fff?text=CRACK+DETECTED",
];

// Initialize sample defects
FIXED_DEFECT_IMAGES.forEach((src) => {
  defectHistory.push({ time: "Sample", src: src });
});

// ─── User Config Persistence ─────────────────────────────────────────
// Manages reading and writing userConfig.json via the Qt bridge.
// Falls back to localStorage when no bridge is present (browser testing).
//
// Expected Qt bridge methods (expose these from your Python/C++ backend):
//   bridge.readUserConfig()           → returns JSON string (or empty string)
//   bridge.writeUserConfig(jsonStr)   → writes the string to userConfig.json
//
// JSON structure:
//   { "jobId": "102", "threshold": "82", "lastSaved": "ISO-timestamp" }
// ─────────────────────────────────────────────────────────────────────

const USER_CONFIG_KEY = "userConfig"; // localStorage key (fallback)
const USER_CONFIG_DEFAULTS = { jobId: "", threshold: "" };

/**
 * Read userConfig.json.
 * Priority: Qt bridge → localStorage → built-in defaults.
 * @returns {Promise<{jobId:string, threshold:string}>}
 */
async function readUserConfig() {
  // 1. Try Qt bridge
  if (bridge && typeof bridge.readUserConfig === "function") {
    try {
      const raw = await bridge.readUserConfig();
      if (raw && raw.trim()) {
        const parsed = JSON.parse(raw);
        // Guard against empty / malformed data
        if (parsed && typeof parsed === "object") {
          return {
            jobId: String(parsed.jobId ?? ""),
            threshold: String(parsed.threshold ?? ""),
          };
        }
      }
    } catch (e) {
      console.warn("[UserConfig] Bridge read failed, using localStorage:", e);
    }
  }

  // 2. Fallback: localStorage
  try {
    const raw = localStorage.getItem(USER_CONFIG_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === "object") {
        return {
          jobId: String(parsed.jobId ?? ""),
          threshold: String(parsed.threshold ?? ""),
        };
      }
    }
  } catch (e) {
    console.warn("[UserConfig] localStorage read failed:", e);
  }

  // 3. First-time launch — return defaults
  console.info("[UserConfig] No saved config found. Using defaults.");
  return { ...USER_CONFIG_DEFAULTS };
}

/**
 * Write values to userConfig.json.
 * Writes to Qt bridge AND localStorage (belt-and-suspenders).
 * @param {string} jobId
 * @param {string} threshold
 */
async function writeUserConfig(jobId, threshold) {
  const payload = {
    jobId: String(jobId ?? ""),
    threshold: String(threshold ?? ""),
    lastSaved: new Date().toISOString(),
  };
  const jsonStr = JSON.stringify(payload, null, 2);

  // 1. Qt bridge (primary — true file persistence)
  if (bridge && typeof bridge.writeUserConfig === "function") {
    try {
      await bridge.writeUserConfig(jsonStr);
    } catch (e) {
      console.warn("[UserConfig] Bridge write failed:", e);
    }
  }

  // 2. localStorage (secondary — survives page reloads in browser mode)
  try {
    localStorage.setItem(USER_CONFIG_KEY, jsonStr);
  } catch (e) {
    console.warn("[UserConfig] localStorage write failed:", e);
  }

  addLog(
    `[UserConfig] Saved → jobId="${payload.jobId}", threshold="${payload.threshold}"`,
  );
}

/**
 * Populate the two input fields from saved config.
 * Called once on DOMContentLoaded (after bridge is ready).
 */
async function populateInputsFromConfig() {
  const cfg = await readUserConfig();

  const jobInput = document.getElementById("jobIdInput");
  const thresholdInput = document.getElementById("thresholdInput");

  if (!jobInput || !thresholdInput) return;

  // jobIdInput is a <select> — only set if the option exists
  if (cfg.jobId) {
    const matchingOption = [...jobInput.options].find(
      (o) => o.value === cfg.jobId,
    );
    if (matchingOption) {
      jobInput.value = cfg.jobId;
    } else {
      // Option not loaded yet (async job list). Store for deferred assignment.
      jobInput.dataset.pendingValue = cfg.jobId;
    }
  }

  // thresholdInput is a plain text/number input
  if (cfg.threshold) {
    thresholdInput.value = cfg.threshold;
  }

  checkCanConfirm();

  if (cfg.jobId || cfg.threshold) {
    showToast(
      `📂 Config loaded — Job: ${cfg.jobId || "—"} | Threshold: ${cfg.threshold || "—"}`,
      3000,
    );
  }
}

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

const autoSaveConfig = debounce(async () => {
  const jobId = document.getElementById("jobIdInput")?.value ?? "";
  const threshold = document.getElementById("thresholdInput")?.value ?? "";
  await writeUserConfig(jobId, threshold);
}, 500);

// ─── Fetch Job IDs ──────────────────────────────────────────────────
async function loadConfigFromJSON() {
  try {
    const response = await fetch("/config.json");
    if (!response.ok) throw new Error("Config load failed");
    const data = await response.json();
    const jobSelect = document.getElementById("jobIdInput");
    jobSelect.innerHTML =
      '<option value="" disabled selected hidden>Select Job ID</option>';
    if (data.jobs && Array.isArray(data.jobs)) {
      data.jobs.forEach((job) => {
        const option = document.createElement("option");
        option.value = job.id;
        option.textContent = `${job.id} - ${job.name || "Product"}`;
        jobSelect.appendChild(option);
      });
    }

    // Resolve a pending saved value that arrived before options were ready
    if (jobSelect.dataset.pendingValue) {
      const matchingOption = [...jobSelect.options].find(
        (o) => o.value === jobSelect.dataset.pendingValue,
      );
      if (matchingOption) {
        jobSelect.value = jobSelect.dataset.pendingValue;
        checkCanConfirm();
      }
      delete jobSelect.dataset.pendingValue;
    }
  } catch (error) {
    console.error("JSON fetch error:", error);
  }
}

// ─── Bridge & Initialization ────────────────────────────────────────
document.addEventListener("DOMContentLoaded", function () {
  loadConfigFromJSON();

  new QWebChannel(qt.webChannelTransport, async function (channel) {
    bridge = channel.objects.bridge;
    if (bridge) {
      showToast("✅ Bridge Connected Successfully", 3000);
    } else {
      showToast("⚠️ No Qt Bridge - Using Laptop Webcam", 4000, "warning");
    }

    // Load saved config now that the bridge is available
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

  // Persist confirmed values immediately (no debounce)
  writeUserConfig(jobId, threshold);

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
  document.getElementById("jobIdInput").value = "";
  document.getElementById("thresholdInput").value = "";
  currentJobId = "";
  currentThreshold = "";
  document.getElementById("jobIdLabel").textContent = "—";

  enableSideMenu(); // Re-enable menu on reset

  document.getElementById("startBtn").disabled = true;
  document.getElementById("okBtn").disabled = true;

  // Persist the cleared state so next launch starts blank
  writeUserConfig("", "");

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

  showCameraFeed();
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
      bad++;
      const randomSrc =
        FIXED_DEFECT_IMAGES[
          Math.floor(Math.random() * FIXED_DEFECT_IMAGES.length)
        ];

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
    jobSelect.disabled = false;
    thresholdInput.disabled = false;
    okBtn.disabled = false; // Allow re-config if needed
    resetBtn.disabled = false;
  }
}

// ─── Counters & Uptime ──────────────────────────────────────────────
function updateCounters() {
  document.getElementById("inspectedCount").textContent = inspected;
  document.getElementById("goodCount").textContent = good;
  document.getElementById("badCount").textContent = bad;
  document.getElementById("hdrDefects").textContent = bad;
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

function downloadDefectImage() {
  if (currentModalIndex < 0 || currentModalIndex >= defectHistory.length)
    return;
  const defect = defectHistory[currentModalIndex];
  const link = document.createElement("a");
  link.href = defect.src;
  link.download = `sliver_defect_${currentModalIndex + 1}_${Date.now()}.jpg`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  showToast("✅ Defect image downloaded", 2500);
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
const THRESHOLD_SUGGESTIONS = ["50", "60", "75", "80", "85", "90", "95", "100"];

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

// Expose to HTML
window.startDetection = startDetection;
window.stopDetection = stopDetection;
window.confirmConfig = confirmConfig;
window.resetConfig = resetConfig;
window.checkCanConfirm = checkCanConfirm;
window.openSettings = openSettings;
window.closeSettings = closeSettings;
window.saveSettings = saveSettings;
window.changeDefect = changeDefect;
window.closeDefectModal = closeDefectModal;
window.downloadDefectImage = downloadDefectImage;
window.filterSuggestions = filterSuggestions;
window.toggleSuggestions = toggleSuggestions;
