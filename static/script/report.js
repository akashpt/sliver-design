// ─────────────────────────────────────────────
//  Signal / Slot  (lightweight event bus)
// ─────────────────────────────────────────────
class Signal {
  constructor() {
    this._slots = [];
  }
  /** Connect a slot function to this signal */
  connect(slot) {
    this._slots.push(slot);
  }
  /** Emit the signal — every connected slot is called with data */
  emit(data) {
    this._slots.forEach((slot) => slot(data));
  }
}
// Initialize QWebChannel, then trigger the first fetch
document.addEventListener("DOMContentLoaded", () => {
  new QWebChannel(qt.webChannelTransport, function (channel) {
    window.bridge = channel.objects.bridge;   // expose globally
    filterSignal.emit({ period: "day" });     // now safe to fire
  });
});
// ─────────────────────────────────────────────
//  Signals
// ─────────────────────────────────────────────

/** Fired whenever the user clicks a Day / Week / Month button.
 *  Payload: { period: 'day' | 'week' | 'month' } */
const filterSignal = new Signal();

/** Fired after the bridge returns fresh counts.
 *  Payload: { inspected, good, defective, rate, period } */
const metricsSignal = new Signal();

// ─────────────────────────────────────────────
//  Period → human-readable label map
// ─────────────────────────────────────────────
const PERIOD_LABELS = {
  day:   "Last 24 hours",
  week:  "Last 7 days",
  month: "This month",
};

const PERIOD_SUB = {
  day:   "units today",
  week:  "units this week",
  month: "units this month",
};

// ─────────────────────────────────────────────
//  Slot: call bridge → emit metricsSignal
// ─────────────────────────────────────────────
function slotFetchMetrics({ period }) {
  if (!window.bridge) {
    console.warn("Bridge not ready");
    return;
  }

  bridge.get_counts_by_range(period, function (raw) {   // ← callback
    try {
      const data = JSON.parse(raw);
      if (!data.ok) {
        console.warn("Bridge returned error:", data.message);
        return;
      }
      metricsSignal.emit(data);
    } catch (e) {
      console.error("slotFetchMetrics parse error:", e);
    }
  });
}

// ─────────────────────────────────────────────
//  Slot: update DOM from metricsSignal payload
// ─────────────────────────────────────────────
function slotUpdateMetricCards({ period, inspected, good, defective, rate }) {
  const fmt = (n) => n.toLocaleString("en-IN");

  document.getElementById("mcInspected").textContent    = fmt(inspected);
  document.getElementById("mcGood").textContent         = fmt(good);
  document.getElementById("mcDefective").textContent    = fmt(defective);
  document.getElementById("mcRate").textContent         = rate.toFixed(1) + "%";
  document.getElementById("mcInspectedSub").textContent = PERIOD_SUB[period] ?? "units";
  document.getElementById("activePeriodLabel").textContent = PERIOD_LABELS[period] ?? period;

  // Keep donut chart in sync
  if (window._donutChart) {
    window._donutChart.data.datasets[0].data = [good, defective];
    window._donutChart.update();
  }
}

// ─────────────────────────────────────────────
//  Wire signals → slots
// ─────────────────────────────────────────────
filterSignal.connect(slotFetchMetrics);     // button click → bridge call
metricsSignal.connect(slotUpdateMetricCards); // bridge result → DOM update
 
// ─────────────────────────────────────────────
//  Filter button wiring (DOM → Signal)
// ─────────────────────────────────────────────
document.getElementById("filterGroup")
  .addEventListener("click", (e) => {
    const btn = e.target.closest(".filter-btn");
    if (!btn) return;

    const period = btn.dataset.period;

    // Toggle active state
    document.querySelectorAll(".filter-btn").forEach((b) =>
      b.classList.toggle("active", b === btn)
    );

    // Fire the signal
    filterSignal.emit({ period });
  });

// ─────────────────────────────────────────────
//  Date label
// ─────────────────────────────────────────────
document.getElementById("reportDate").textContent =
  new Date().toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

// ─────────────────────────────────────────────
//  Chart global defaults
// ─────────────────────────────────────────────
Chart.defaults.font.family = "Inter, sans-serif";
Chart.defaults.font.size = 11;
Chart.defaults.color = "#9ca3af";

const C_RED   = "#c0202e";
const C_GREEN = "#16a34a";
const gridCol = "#f3f4f6";

// ── Line Chart ──
new Chart(document.getElementById("chartLine"), {
  type: "line",
  data: {
    labels: ["00","02","04","06","08","10","12","14","16","18","20","22"],
    datasets: [
      {
        label: "Defects",
        data: [1, 3, 7, 12, 8, 4, 2, 5, 11, 9, 3, 1],
        borderColor: C_RED,
        backgroundColor: "rgba(192,32,46,0.07)",
        tension: 0.4,
        fill: true,
        pointRadius: 3,
        pointBackgroundColor: C_RED,
        pointBorderColor: "#fff",
        pointBorderWidth: 1.5,
        borderWidth: 2,
      },
    ],
  },
  options: {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: { mode: "index", intersect: false },
    },
    scales: {
      x: { grid: { color: gridCol }, ticks: { font: { size: 10 } } },
      y: {
        beginAtZero: true,
        grid: { color: gridCol },
        ticks: { stepSize: 3, font: { size: 10 } },
      },
    },
  },
});

// ── Doughnut  (kept in window so metricsSignal can update it) ──
window._donutChart = new Chart(document.getElementById("chartDonut"), {
  type: "doughnut",
  data: {
    labels: ["Good", "Defective"],
    datasets: [
      {
        data: [1187, 61],
        backgroundColor: [C_GREEN, C_RED],
        borderColor: ["#fff", "#fff"],
        borderWidth: 3,
        hoverOffset: 4,
      },
    ],
  },
  options: {
    responsive: true,
    maintainAspectRatio: false,
    cutout: "70%",
    plugins: {
      legend: {
        position: "bottom",
        labels: {
          padding: 14,
          font: { size: 11 },
          usePointStyle: true,
          pointStyleWidth: 7,
        },
      },
    },
  },
});

// ── Bar Chart ──
new Chart(document.getElementById("chartBar"), {
  type: "bar",
  data: {
    labels: ["Sliver Mark","Surface Scratch","Edge Dent","Oil Stain","Crack"],
    datasets: [
      {
        label: "Occurrences",
        data: [28, 15, 9, 6, 3],
        backgroundColor: [
          "rgba(192,32,46,0.85)",
          "rgba(192,32,46,0.68)",
          "rgba(192,32,46,0.52)",
          "rgba(192,32,46,0.38)",
          "rgba(192,32,46,0.24)",
        ],
        borderRadius: 5,
        borderSkipped: false,
        maxBarThickness: 44,
      },
    ],
  },
  options: {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      x: { grid: { display: false }, ticks: { font: { size: 10 } } },
      y: {
        beginAtZero: true,
        grid: { color: gridCol },
        ticks: { stepSize: 5, font: { size: 10 } },
      },
    },
  },
});

// ─────────────────────────────────────────────
//  Toast
// ─────────────────────────────────────────────
function showToast(msg, ms = 3000) {
  const t = document.getElementById("toast");
  document.getElementById("toastMsg").textContent = msg;
  t.style.display = "block";
  requestAnimationFrame(() => t.classList.add("show"));
  setTimeout(() => {
    t.classList.remove("show");
    setTimeout(() => (t.style.display = "none"), 300);
  }, ms);
}

// ─────────────────────────────────────────────
//  On load: trigger default filter (Day)
// ─────────────────────────────────────────────
// window.addEventListener("DOMContentLoaded", () => {
//   filterSignal.emit({ period: "day" });
// });