// =====================================
// COMMON SETTINGS + SHIFT TIMING
// Used by index.html, training.html, controller.html, settings.html
// =====================================

(function () {
  if (window.__settingsCommonLoaded) return;
  window.__settingsCommonLoaded = true;

  function toastMsg(message, time = 2500) {
    if (typeof showToast === "function") {
      showToast(message, time);
      return;
    }

    const toast = document.getElementById("toast");
    const toastMessage =
      document.getElementById("toastMessage") ||
      document.getElementById("toastMsg");

    if (toastMessage) {
      toastMessage.textContent = message;
    }

    if (toast) {
      if (!toastMessage) toast.textContent = message;
      toast.style.display = "block";
      toast.classList.add("show");

      setTimeout(() => {
        toast.classList.remove("show");
        toast.style.display = "none";
      }, time);
    } else {
      console.log(message);
    }
  }

  function getBridge() {
    return window.bridge || (typeof bridge !== "undefined" ? bridge : null);
  }

  function connectBridge(callback) {
    const existingBridge = getBridge();

    if (existingBridge) {
      window.bridge = existingBridge;
      if (typeof callback === "function") callback(existingBridge);
      return;
    }

    if (window.__qtWebChannelConnecting) {
      let attempts = 0;
      const waitForBridge = setInterval(function () {
        attempts += 1;

        const readyBridge = getBridge();
        if (readyBridge || attempts >= 20) {
          clearInterval(waitForBridge);

          if (readyBridge) {
            window.bridge = readyBridge;
          }

          if (typeof callback === "function") callback(readyBridge);
        }
      }, 100);

      return;
    }

    if (
      typeof QWebChannel === "undefined" ||
      typeof qt === "undefined" ||
      !qt.webChannelTransport
    ) {
      if (typeof callback === "function") callback(null);
      return;
    }

    window.__qtWebChannelConnecting = true;

    new QWebChannel(qt.webChannelTransport, function (channel) {
      window.__qtWebChannelConnecting = false;
      window.bridge = channel.objects.bridge || null;

      if (window.bridge) {
        toastMsg("Bridge Connected Successfully", 2500);
      }

      if (typeof callback === "function") callback(window.bridge);
    });
  }

  function parseBridgeResponse(res) {
    return typeof res === "string" ? JSON.parse(res) : res;
  }

  function callBridgeResult(methodName, args, onDone) {
    const b = getBridge();

    if (!b || typeof b[methodName] !== "function") {
      onDone(null);
      return;
    }

    try {
      b[methodName](...args, onDone);
    } catch (err) {
      console.error(`${methodName} bridge call failed:`, err);
      onDone(null);
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    connectBridge();
  });

  window.openSettings = function () {
    const modal = document.getElementById("settingsModal");

    connectBridge();

    if (!modal) {
      window.switchTab("detection");
      return;
    }

    modal.style.display = "flex";
    window.switchTab("shift");
  };

  window.closeSettings = function () {
    const modal = document.getElementById("settingsModal");

    if (modal) {
      modal.style.display = "none";
    }
  };

  window.switchTab = function (tabName) {
    document.querySelectorAll(".modal-tab, .settings-tab-btn").forEach((btn) => {
      btn.classList.remove("active");
    });

    document.querySelectorAll(".tab-content, .settings-pane").forEach((tab) => {
      tab.classList.remove("active");
    });

    const selectedTab = document.getElementById(tabName + "Tab");
    if (selectedTab) {
      selectedTab.classList.add("active");
    }

    document.querySelectorAll(".modal-tab, .settings-tab-btn").forEach((btn) => {
      const text = btn.textContent.toLowerCase();

      if (
        (tabName === "detection" && text.includes("detection")) ||
        (tabName === "threshold" && text.includes("threshold")) ||
        (tabName === "shift" && text.includes("shift"))
      ) {
        btn.classList.add("active");
      }
    });

    if (tabName === "shift") {
      window.loadShifts();
    }
  };

  window.toggleManual = function () {
    const manualRadio = document.getElementById("modeManual");
    const manualControls = document.getElementById("manualControls");

    if (!manualRadio || !manualControls) return;

    manualControls.style.display = manualRadio.checked ? "block" : "none";
  };

  window.loadShifts = function () {
    const tbody = document.getElementById("shiftTableBody");
    if (!tbody) return;

    connectBridge(function (b) {
      if (!b || typeof b.getShifts !== "function") {
        tbody.innerHTML = `
          <tr>
            <td colspan="4">Bridge not ready</td>
          </tr>
        `;
        return;
      }

      callBridgeResult("getShifts", [], function (res) {
        try {
          if (!res) throw new Error("Empty bridge response");

          const data = parseBridgeResponse(res);
          const shifts = Array.isArray(data) ? data : data.shifts || [];

          if (!shifts.length) {
            tbody.innerHTML = `
              <tr>
                <td colspan="4">No shifts found</td>
              </tr>
            `;
            return;
          }

          tbody.innerHTML = shifts
            .map((s) => {
              const status =
                Number(s.active) === 1 || s.active === true
                  ? "Active"
                  : "Inactive";

              return `
                <tr>
                  <td>${s.shift_name || ""}</td>
                  <td>${s.start_time || ""}</td>
                  <td>${s.end_time || ""}</td>
                  <td>${status}</td>
                </tr>
              `;
            })
            .join("");
        } catch (err) {
          console.error("loadShifts error:", err, res);
          tbody.innerHTML = `
            <tr>
              <td colspan="4">Shift load error</td>
            </tr>
          `;
        }
      });
    });
  };

  window.saveShiftTiming = function () {
    const shiftName = document.getElementById("shiftName")?.value.trim();
    const startTime = document.getElementById("shiftStart")?.value.trim();
    const endTime = document.getElementById("shiftEnd")?.value.trim();

    if (!shiftName || !startTime || !endTime) {
      toastMsg("Please enter shift name, start time and end time");
      return;
    }

    connectBridge(function (b) {
      if (!b || typeof b.saveShift !== "function") {
        toastMsg("Bridge saveShift not ready");
        return;
      }

      callBridgeResult("saveShift", [shiftName, startTime, endTime], function (res) {
        try {
          if (!res) throw new Error("Empty bridge response");

          const data = parseBridgeResponse(res);

          toastMsg(data.message || "Shift saved");

          if (data.ok) {
            document.getElementById("shiftName").value = "";
            document.getElementById("shiftStart").value = "";
            document.getElementById("shiftEnd").value = "";

            window.loadShifts();
          }
        } catch (err) {
          console.error("saveShiftTiming error:", err, res);
          toastMsg("Shift save response error");
        }
      });
    });
  };

  window.saveSettings = window.saveSettings || function () {
    window.closeSettings();
  };
})();
