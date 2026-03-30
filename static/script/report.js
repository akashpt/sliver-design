// Date
document.getElementById("reportDate").textContent =
  new Date().toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

// Chart global defaults
Chart.defaults.font.family = "Inter, sans-serif";
Chart.defaults.font.size = 11;
Chart.defaults.color = "#9ca3af";

const C_RED = "#c0202e";
const C_GREEN = "#16a34a";
const gridCol = "#f3f4f6";

// ── Line Chart ──
new Chart(document.getElementById("chartLine"), {
  type: "line",
  data: {
    labels: [
      "00",
      "02",
      "04",
      "06",
      "08",
      "10",
      "12",
      "14",
      "16",
      "18",
      "20",
      "22",
    ],
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

// ── Doughnut ──
new Chart(document.getElementById("chartDonut"), {
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
    labels: [
      "Sliver Mark",
      "Surface Scratch",
      "Edge Dent",
      "Oil Stain",
      "Crack",
    ],
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

// ── Table ──
const rows = [
  ["0248", "22:41:03", "Camera 1", "Sliver Mark", "96.2%", "bad"],
  ["0247", "22:38:51", "Camera 0", "—", "98.8%", "good"],
  ["0246", "22:35:22", "Camera 0", "—", "99.1%", "good"],
  ["0245", "22:31:14", "Camera 1", "Surface Scratch", "91.4%", "bad"],
  ["0244", "22:28:09", "Camera 0", "—", "97.7%", "good"],
  ["0243", "22:22:50", "Camera 1", "Edge Dent", "88.9%", "bad"],
  ["0242", "22:19:33", "Camera 0", "—", "99.3%", "good"],
  ["0241", "22:14:07", "Camera 0", "—", "98.0%", "good"],
  ["0240", "22:11:42", "Camera 1", "Oil Stain", "93.5%", "bad"],
  ["0239", "22:07:18", "Camera 0", "—", "97.2%", "good"],
];
const tbody = document.getElementById("tBody");
rows.forEach((r) => {
  const isGood = r[5] === "good";
  tbody.innerHTML += `
      <tr>
        <td class="mono" style="color:var(--gray-400)">#${r[0]}</td>
        <td class="mono">${r[1]}</td>
        <td>${r[2]}</td>
        <td>${r[3]}</td>
        <td class="mono">${r[4]}</td>
        <td>
          <span class="pill ${r[5]}">
            <i class="fas fa-${isGood ? "check" : "xmark"}" style="font-size:.6rem;"></i>
            ${isGood ? "Good" : "Defective"}
          </span>
        </td>
      </tr>`;
});
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
