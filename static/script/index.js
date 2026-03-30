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
const USER_CONFIG_KEY = "userConfig";
const USER_CONFIG_DEFAULTS = { jobId: "", threshold: "" };

async function readUserConfig() {
  if (bridge && typeof bridge.readUserConfig === "function") {
    try {
      const raw = await bridge.readUserConfig();
      if (raw && raw.trim()) {
        const parsed = JSON.parse(raw);
        if (parsed && typeof parsed === "object") {
          return {
            jobId: String(parsed.jobId ?? ""),
            threshold: String(parsed.threshold ?? ""),
          };
        }
      }
    } catch (e) {
      console.warn("[UserConfig] Bridge read failed:", e);
    }
  }

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

  return { ...USER_CONFIG_DEFAULTS };
}

async function writeUserConfig(jobId, threshold) {
  const payload = {
    jobId: String(jobId ?? ""),
    threshold: String(threshold ?? ""),
    lastSaved: new Date().toISOString(),
  };
  const jsonStr = JSON.stringify(payload, null, 2);

  if (bridge && typeof bridge.writeUserConfig === "function") {
    try {
      await bridge.writeUserConfig(jsonStr);
    } catch (e) {}
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

// ─── Populate Inputs ────────────────────────────────────────────────
async function populateInputsFromConfig() {
  const cfg = await readUserConfig();
  const jobInput = document.getElementById("jobIdInput");
  const thresholdInput = document.getElementById("thresholdInput");

  if (cfg.jobId && jobInput) {
    const matching = [...jobInput.options].find((o) => o.value === cfg.jobId);
    if (matching) jobInput.value = cfg.jobId;
  }
  if (cfg.threshold && thresholdInput) {
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
    if (!response.ok) throw new Error();
    const data = await response.json();
    const jobSelect = document.getElementById("jobIdInput");
    jobSelect.innerHTML =
      '<option value="" disabled selected hidden>Select Job ID</option>';

    if (data.jobs) {
      data.jobs.forEach((job) => {
        const opt = document.createElement("option");
        opt.value = job.id;
        opt.textContent = `${job.id} - ${job.name || "Product"}`;
        jobSelect.appendChild(opt);
      });
    }
  } catch (e) {
    console.error("Failed to load config.json");
  }
}

// ─── Initialization ─────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", function () {
  loadConfigFromJSON();

  new QWebChannel(qt.webChannelTransport, async function (channel) {
    bridge = channel.objects.bridge;
    if (bridge) showToast("✅ Bridge Connected", 2000);
    else showToast("⚠️ No Bridge - Using Webcam", 3000, "warning");

    await populateInputsFromConfig();
  });

  renderDefectThumbs();
  resetToInitialState();

  const jobIdInput = document.getElementById("jobIdInput");
  const thresholdInput = document.getElementById("thresholdInput");

  jobIdInput.addEventListener("change", checkCanConfirm);
  thresholdInput.addEventListener("input", checkCanConfirm);
  jobIdInput.addEventListener("change", autoSaveConfig);
  thresholdInput.addEventListener("input", autoSaveConfig);
});

// ─── Side Menu Control ──────────────────────────────────────────────
function disableSideMenu() {
  const items = [
    "menuDashboard",
    "menuReport",
    "menuController",
    "menuTraining",
    "menuSettings",
  ];
  items.forEach((id) => {
    const el = document.getElementById(id);
    if (el) {
      el.style.pointerEvents = "none";
      el.style.opacity = "0.5";
      el.style.cursor = "not-allowed";
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
// ─── Confirm Configuration ──────────────────────────────────────────
// ─── Confirm Configuration ──────────────────────────────────────────
function confirmConfig() {
  const jobIdInput = document.getElementById("jobIdInput");
  const thresholdInput = document.getElementById("thresholdInput");

  const jobId = jobIdInput ? jobIdInput.value.trim() : "";
  const threshold = thresholdInput ? thresholdInput.value.trim() : "";

  if (!jobId || !threshold) {
    showToast("❌ Please select Job ID and enter Threshold", 3000, "error");
    return;
  }

  currentJobId = jobId;
  currentThreshold = threshold;
  document.getElementById("jobIdLabel").textContent = jobId;

  writeUserConfig(jobId, threshold);

  showToast(
    `✅ Config Confirmed - Job: ${jobId} | Threshold: ${threshold}`,
    4000,
  );
  addLog(`Configuration Confirmed → Job: ${jobId}, Threshold: ${threshold}`);

  // Disable inputs after OK is clicked
  document.getElementById("jobIdInput").disabled = true;
  document.getElementById("thresholdInput").disabled = true;

  document.getElementById("startBtn").disabled = false;
  document.getElementById("okBtn").disabled = true;
}

// Make Job ID and Threshold inputs non-editable with visual feedback
function makeInputsNonEditable() {
  const jobIdInput = document.getElementById("jobIdInput");
  const thresholdInput = document.getElementById("thresholdInput");

  if (jobIdInput) {
    jobIdInput.disabled = true;
    jobIdInput.style.opacity = "0.6";
    jobIdInput.style.backgroundColor = "#1f1f1f";
    jobIdInput.style.cursor = "not-allowed";
    jobIdInput.style.pointerEvents = "none";
  }

  if (thresholdInput) {
    thresholdInput.disabled = true;
    thresholdInput.style.opacity = "0.6";
    thresholdInput.style.backgroundColor = "#1f1f1f";
    thresholdInput.style.cursor = "not-allowed";
    thresholdInput.style.pointerEvents = "none";
  }
}

// Re-enable inputs (used in Reset and when stopping detection)
function makeInputsEditable() {
  const jobIdInput = document.getElementById("jobIdInput");
  const thresholdInput = document.getElementById("thresholdInput");

  if (jobIdInput) {
    jobIdInput.disabled = false;
    jobIdInput.style.opacity = "1";
    jobIdInput.style.backgroundColor = "";
    jobIdInput.style.cursor = "pointer";
    jobIdInput.style.pointerEvents = "auto";
  }

  if (thresholdInput) {
    thresholdInput.disabled = false;
    thresholdInput.style.opacity = "1";
    thresholdInput.style.backgroundColor = "";
    thresholdInput.style.cursor = "text";
    thresholdInput.style.pointerEvents = "auto";
  }
}

// ─── Reset Configuration ────────────────────────────────────────────
function resetConfig() {
  const jobIdInput = document.getElementById("jobIdInput");
  const thresholdInput = document.getElementById("thresholdInput");

  if (jobIdInput) jobIdInput.value = "";
  if (thresholdInput) thresholdInput.value = "";

  currentJobId = "";
  currentThreshold = "";
  document.getElementById("jobIdLabel").textContent = "—";

  makeInputsEditable();     // Make editable again
  enableSideMenu();

  document.getElementById("startBtn").disabled = true;
  document.getElementById("okBtn").disabled = true;

  writeUserConfig("", "");

  showToast("Configuration Reset", 2500);
  addLog("Configuration Reset");
}

// Function to completely hide the inputs
function hideConfigInputs() {
  const jobIdInput = document.getElementById("jobIdInput");
  const thresholdInput = document.getElementById("thresholdInput");

  if (jobIdInput) {
    jobIdInput.style.display = "none";
  }
  if (thresholdInput) {
    thresholdInput.style.display = "none";
  }
}

// Function to show the inputs again (used in Reset and Stop)
function showConfigInputs() {
  const jobIdInput = document.getElementById("jobIdInput");
  const thresholdInput = document.getElementById("thresholdInput");

  if (jobIdInput) {
    jobIdInput.style.display = "block";   // or "inline-block" / "flex" depending on your layout
  }
  if (thresholdInput) {
    thresholdInput.style.display = "block";
  }
}

// ─── Reset Configuration ────────────────────────────────────────────
function resetConfig() {
  document.getElementById("jobIdInput").value = "";
  document.getElementById("thresholdInput").value = "";
  currentJobId = "";
  currentThreshold = "";
  document.getElementById("jobIdLabel").textContent = "—";

  // Enable inputs
  document.getElementById("jobIdInput").disabled = false;
  document.getElementById("thresholdInput").disabled = false;

  enableSideMenu();

  document.getElementById("startBtn").disabled = true;
  document.getElementById("okBtn").disabled = true;

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

  // Enable inputs by default
  document.getElementById("jobIdInput").disabled = false;
  document.getElementById("thresholdInput").disabled = false;

  enableSideMenu();

  hideCameraFeed();
  document.getElementById("statusLabel").textContent = "STANDBY";
  document.getElementById("jobIdLabel").textContent = "—";
}

// ─── Camera & Detection Functions (unchanged logic) ─────────────────
function showCameraFeed() {
  const noFeed = document.getElementById("noFeed");
  const videoFeed = document.getElementById("videoFeed");
  const liveBadge = document.getElementById("liveBadge");

  noFeed.style.display = "none";
  videoFeed.style.display = "block";
  if (liveBadge) liveBadge.style.display = "flex";
}

function hideCameraFeed() {
  const noFeed = document.getElementById("noFeed");
  const videoFeed = document.getElementById("videoFeed");
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
  if (bridge && typeof bridge.stopCamera === "function") {
    try {
      bridge.stopCamera();
    } catch (e) {}
  }
  hideCameraFeed();
}

async function startLaptopWebcam() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment" },
    });
    currentStream = stream;
    document.getElementById("videoFeed").srcObject = stream;
    await document.getElementById("videoFeed").play();
  } catch (err) {
    console.error(err);
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
      if (bridge.frame_signal && !bridge.frame_signal._connected) {
        bridge.frame_signal.connect((base64) =>
          updateVideoFeedFromBase64(base64),
        );
        bridge.frame_signal._connected = true;
      }
    } catch (e) {
      startLaptopWebcam();
    }
  } else {
    startLaptopWebcam();
  }

  demoDefectInterval = setInterval(() => {
    inspected++;
    if (Math.random() < 0.3) {
      bad++;
      const src =
        FIXED_DEFECT_IMAGES[
          Math.floor(Math.random() * FIXED_DEFECT_IMAGES.length)
        ];
      defectHistory.unshift({
        time: new Date().toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
        }),
        src,
      });
      if (defectHistory.length > 10) defectHistory.pop();
      renderDefectThumbs();
      addLog('<span style="color:#ef233c">⚠️ DEFECT DETECTED</span>');
    } else {
      good++;
    }
    updateCounters();
  }, 5000);
}

// ─── Stop Detection ─────────────────────────────────────────────────
function stopDetection() {
  if (!isRunning) return;

  stopAllCameras();
  if (bridge && typeof bridge.stopCamera === "function")
    try {
      bridge.stopCamera();
    } catch (e) {}

  if (demoDefectInterval) {
    clearInterval(demoDefectInterval);
    demoDefectInterval = null;
  }

  stopUptime();
  setUIState(false);

  document.getElementById("statusLabel").textContent = "STANDBY";

  showToast("🛑 Detection Stopped", 3000);
  addLog("Detection Stopped");
}

// ─── UI State ───────────────────────────────────────────────────────
function setUIState(running) {
  isRunning = running;

  const startBtn = document.getElementById("startBtn");
  const stopBtn = document.getElementById("stopBtn");
  const resetBtn = document.getElementById("resetBtn");

  if (running) {
    startBtn.disabled = true;
    stopBtn.disabled = false;
    resetBtn.disabled = true;
  } else {
    startBtn.disabled = false;
    stopBtn.disabled = true;
    resetBtn.disabled = false;

    // Enable Job ID and Threshold when stopped
    document.getElementById("jobIdInput").disabled = false;
    document.getElementById("thresholdInput").disabled = false;
    enableSideMenu();
  }
}

// ─── Counters ───────────────────────────────────────────────────────
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

// ─── Qt Frame Update ────────────────────────────────────────────────
function updateVideoFeedFromBase64(base64Image) {
  let img = document.getElementById("qtFrameImg");
  if (!img) {
    img = document.createElement("img");
    img.id = "qtFrameImg";
    img.style.cssText =
      "width:100%; height:100%; object-fit:cover; border-radius:6px;";
    document.querySelector(".camera-wrap").appendChild(img);
    document.getElementById("videoFeed").style.display = "none";
  }
  img.src = "data:image/jpeg;base64," + base64Image;
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
