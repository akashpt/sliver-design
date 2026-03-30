// ─── Clock ──────────────────────────────────────────────────────────
(function tick() {
  document.getElementById("clock").textContent = new Date()
    .toTimeString()
    .slice(0, 8);
})();
setInterval(() => {
  document.getElementById("clock").textContent = new Date()
    .toTimeString()
    .slice(0, 8);
}, 1000);
// ─── Uptime ─────────────────────────────────────────────────────────
let sessionStart = null;
let uptimeTimer = null;
function startUptime() {
  sessionStart = Date.now();
  uptimeTimer = setInterval(() => {
    const s = Math.floor((Date.now() - sessionStart) / 1000);
    document.getElementById("uptimeVal").textContent =
      `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  }, 1000);
}
function stopUptime() {
  if (uptimeTimer) {
    clearInterval(uptimeTimer);
    uptimeTimer = null;
  }
}
// ─── Log ────────────────────────────────────────────────────────────
function addLog(msg) {
  const box = document.getElementById("logBox");
  if (!box) return;
  const time = new Date().toTimeString().slice(0, 8);
  box.innerHTML += `<div><span style="color:var(--primary);font-weight:600">${time}</span> ${msg}</div>`;
  box.scrollTop = box.scrollHeight;
}
// ─── SINGLE FIXED SET OF DEFECT IMAGES ──────────────────────────────
const FIXED_DEFECT_IMAGES = [
  "https://placehold.co/640x480/ff4d6d/white?text=EDGE+SLIVER",
  "https://placehold.co/640x480/ef233c/fff?text=DENT+DEFECT",
  "https://picsum.photos/seed/metaldefect1/640/480",
  "https://placehold.co/640x480/c1121f/white?text=SCRATCH+DEFECT",
  "https://picsum.photos/seed/industrialdefect/640/480",
  "https://placehold.co/640x480/d00000/fff?text=CRACK+DETECTED",
];
let defectHistory = [];
let currentModalIndex = -1;
// Initialize with the fixed set (shown on page load)
FIXED_DEFECT_IMAGES.forEach((src) => {
  defectHistory.push({ time: "Sample", src: src, isSample: true });
});
function addDefectImage(imgSrc) {
  const time = new Date().toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
  defectHistory.unshift({ time, src: imgSrc, isSample: false });
  if (defectHistory.length > 10) defectHistory.pop();
  renderDefectThumbs();
}
function renderDefectThumbs() {
  const container = document.getElementById("defectsSlider");
  if (!container) return;
  container.innerHTML = "";
  if (defectHistory.length === 0) {
    container.innerHTML = `<div class="defect-empty">Waiting for detection to start...</div>`;
    return;
  }
  defectHistory.forEach((def, idx) => {
    const thumb = document.createElement("div");
    thumb.className = "defect-thumb";
    if (def.isSample) {
      thumb.style.opacity = "0.78";
      thumb.style.border = "1px dashed #9ca3af";
      thumb.innerHTML = `
            <img src="${def.src}" alt="Sample defect" loading="lazy">
            `;
    } else {
      thumb.innerHTML = `<img src="${def.src}" alt="Defect ${idx + 1}" loading="lazy">`;
    }
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
// ─── Detection / Demo Logic ─────────────────────────────────────────
let inspected = 0;
let good = 0;
let bad = 0;
let demoDefectInterval = null;
function startDetection() {
  const cam = document.getElementById("cameraSelect")?.value || "0";
  fetch("/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ camera: cam }),
  })
    .then(() => {
      _activate();
      addLog(`Detection started — Camera ${cam}`);
    })
    .catch(() => {
      _activate();
      addLog("Detection started (demo mode)");
    });
}
function _activate() {
  const feed = document.getElementById("videoFeed");
  if (feed) {
    feed.src = "/video?t=" + Date.now();
    feed.style.display = "block";
  }
  document.getElementById("noFeed")?.style.setProperty("display", "none");
  document
    .getElementById("liveBadge")
    ?.style.setProperty("display", "inline-flex");
  document.getElementById("statusLabel").textContent = "ACTIVE";
  document.getElementById("confVal").textContent = "84%";
  document.getElementById("confBar").style.width = "84%";

  startUptime();

  // Demo: only update counters — NO NEW IMAGES added to slider
  demoDefectInterval = setInterval(
    () => {
      inspected++;

      if (Math.random() < 0.28) {
        bad++;
        addLog(
          '<span style="color:var(--accent)">⚠ DEFECT DETECTED (demo)</span>',
        );
        // If you want to cycle through the same fixed images instead of staying static, uncomment next 2 lines:
        // const src = FIXED_DEFECT_IMAGES[bad % FIXED_DEFECT_IMAGES.length];
        // addDefectImage(src);
      } else {
        good++;
      }

      document.getElementById("inspectedCount").textContent = inspected;
      document.getElementById("goodCount").textContent = good;
      document.getElementById("badCount").textContent = bad;
      document.getElementById("hdrDefects").textContent = bad;

      const rate = inspected > 0 ? ((bad / inspected) * 100).toFixed(1) : "0.0";
      document.getElementById("defectRateVal").textContent = rate + "%";
      document.getElementById("defectBar").style.width =
        Math.min(parseFloat(rate) * 5, 100) + "%";
    },
    6000 + Math.random() * 9000,
  );
}

function stopDetection() {
  fetch("/stop", { method: "POST" }).finally(_deactivate);
}

function _deactivate() {
  const feed = document.getElementById("videoFeed");
  if (feed) {
    feed.style.display = "none";
    feed.src = "";
  }
  document.getElementById("noFeed")?.style.setProperty("display", "flex");
  document.getElementById("liveBadge")?.style.setProperty("display", "none");
  document.getElementById("statusLabel").textContent = "STANDBY";
  document.getElementById("confVal").textContent = "—";
  document.getElementById("confBar").style.width = "0%";

  stopUptime();
  addLog("Detection stopped.");

  if (demoDefectInterval) {
    clearInterval(demoDefectInterval);
    demoDefectInterval = null;
  }
}
// ─── Toast ──────────────────────────────────────────────────────────
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
// ─── Training ───────────────────────────────────────────────────────
function startTraining() {
  showToast("Training in progress — please wait ~20 seconds", 7000);
  addLog("Training started...");
  setTimeout(() => {
    document.getElementById("trainingModal").style.display = "flex";
    addLog("Training complete.");
  }, 20000);
}
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
document.getElementById("defectModal")?.addEventListener("click", (e) => {
  if (e.target === e.currentTarget) closeDefectModal();
});
document.getElementById("settingsModal")?.addEventListener("click", (e) => {
  if (e.target === e.currentTarget) closeSettings();
});
// ─── Initial render ─────────────────────────────────────────────────
renderDefectThumbs();
// Make range sliders show dynamic fill color
document.querySelectorAll('input[type="range"]').forEach((slider) => {
  // Initial update
  updateRangeFill(slider);
  // Update on every change
  slider.addEventListener("input", () => {
    updateRangeFill(slider);
  });
  // Optional: also update when number input changes (if you have linked number field)
  const numberInput = document.getElementById(
    slider.id.replace("Slider", "Value"),
  );
  if (numberInput) {
    numberInput.addEventListener("input", () => {
      slider.value = numberInput.value;
      updateRangeFill(slider);
    });
  }
});
function updateRangeFill(slider) {
  const percentage =
    ((slider.value - slider.min) / (slider.max - slider.min)) * 100;
  slider.style.setProperty("--value", percentage + "%");
}
// ─── Real Camera Switching (Laptop vs USB) ──────────────────────────────────
let currentStream = null;

// Map your dropdown values to camera preferences
// 0 = prefer built-in (laptop), 1 = prefer external/USB
const cameraPreference = {
  0: "user", // facingMode: "user" → built-in laptop camera
  1: "environment", // facingMode: "environment" → external/USB camera (most common)
};
async function startDetection() {
  const selectedValue = document.getElementById("cameraSelect").value;
  // Stop any previous stream cleanly
  if (currentStream) {
    currentStream.getTracks().forEach((track) => track.stop());
    currentStream = null;
  }
  try {
    // Choose facingMode based on selection
    const facingMode = cameraPreference[selectedValue] || "user";
    const constraints = {
      video: {
        facingMode: facingMode,
        width: { ideal: 1280 },
        height: { ideal: 720 },
      },
      audio: false,
    };
    // Request camera access
    currentStream = await navigator.mediaDevices.getUserMedia(constraints);
    const videoEl = document.getElementById("videoFeed");
    videoEl.srcObject = currentStream;
    videoEl.play().catch((e) => console.warn("Video play failed:", e));
    videoEl.style.display = "block";
    document.getElementById("noFeed").style.display = "none";
    document.getElementById("liveBadge").style.display = "inline-flex";
    document.getElementById("statusLabel").textContent = "ACTIVE";
    startUptime();
    addLog(
      `Detection started — ${selectedValue === "1" ? "USB Camera" : "Laptop Camera"}`,
    );
    // Keep your demo counters running (optional)
    // demoDefectInterval = setInterval(.... your existing demo code ....);
  } catch (err) {
    console.error("Camera error:", err);
    addLog("Failed to open camera: " + err.message);
    showToast(
      "Cannot access camera. Please check permissions or connection.",
      5000,
    );
  }
}
function _deactivate() {
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
  addLog("Detection stopped.");
  if (demoDefectInterval) {
    clearInterval(demoDefectInterval);
    demoDefectInterval = null;
  }
}
// ─── Make sure stop button calls the right deactivate ───────────────────────
function stopDetection() {
  // Remove the old fetch if you don't need backend stop anymore
  // fetch('/stop', { method: 'POST' }).finally(_deactivate);
  _deactivate();
}
