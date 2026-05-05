// =====================================
// COMMON SETTINGS MODAL + SHIFT TIMING
// Used by index.html, training.html, controller.html
// =====================================

(function () {
  if (window.__settingsCommonLoaded) return;
  window.__settingsCommonLoaded = true;

  function getBridge() {
    return window.bridge || (typeof bridge !== "undefined" ? bridge : null);
  }

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
      alert(message);
    }
  }

  window.openSettings = function () {
    const modal = document.getElementById("settingsModal");

    if (!modal) {
      console.error("settingsModal not found in this page");
      toastMsg("Settings modal not found");
      return;
    }

    modal.style.display = "flex";

    // Always open Shift Timing tab first
    window.switchTab("shift");

    setTimeout(() => {
      window.loadShifts();
    }, 200);
  };

  window.closeSettings = function () {
    const modal = document.getElementById("settingsModal");
    if (modal) {
      modal.style.display = "none";
    }
  };

  window.switchTab = function (tabName) {
    document.querySelectorAll(".modal-tab").forEach((btn) => {
      btn.classList.remove("active");
    });

    document.querySelectorAll(".tab-content").forEach((tab) => {
      tab.classList.remove("active");
    });

    const selectedTab = document.getElementById(tabName + "Tab");
    if (selectedTab) {
      selectedTab.classList.add("active");
    }

    document.querySelectorAll(".modal-tab").forEach((btn) => {
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

    const b = getBridge();

    if (!b || typeof b.getShifts !== "function") {
      tbody.innerHTML = `
        <tr>
          <td colspan="4">Bridge not ready</td>
        </tr>
      `;
      return;
    }

    b.getShifts(function (res) {
      try {
        const data = typeof res === "string" ? JSON.parse(res) : res;
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
  };

  window.saveShiftTiming = function () {
    const shiftName = document.getElementById("shiftName")?.value.trim();
    const startTime = document.getElementById("shiftStart")?.value.trim();
    const endTime = document.getElementById("shiftEnd")?.value.trim();

    if (!shiftName || !startTime || !endTime) {
      toastMsg("Please enter shift name, start time and end time");
      return;
    }

    const b = getBridge();

    if (!b || typeof b.saveShift !== "function") {
      toastMsg("Bridge saveShift not ready");
      return;
    }

    b.saveShift(shiftName, startTime, endTime, function (res) {
      try {
        const data = typeof res === "string" ? JSON.parse(res) : res;

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
  };

  window.saveSettings = window.saveSettings || function () {
    window.closeSettings();
  };
})();