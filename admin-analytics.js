const byId = id => document.getElementById(id);
let userGrowthChart = null;
let transactionActivityChart = null;
let analyticsRequestId = 0;

function localDateString(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function setDateRange(days) {
  const end = new Date();
  const start = new Date(end);
  start.setDate(start.getDate() - days + 1);
  byId("startDate").value = localDateString(start);
  byId("endDate").value = localDateString(end);
  document.querySelectorAll("[data-range-days]").forEach(button => {
    button.setAttribute("aria-pressed", String(Number(button.dataset.rangeDays) === days));
  });
}

function setStatus(message, error = false) {
  const status = byId("analyticsStatus");
  status.textContent = message;
  status.className = `min-h-5 text-sm ${error ? "text-rose-400" : "text-slate-400"}`;
}

function renderCharts(data) {
  if (userGrowthChart) userGrowthChart.destroy();
  if (transactionActivityChart) transactionActivityChart.destroy();
  byId("userGrowthChart").replaceChildren();
  byId("transactionActivityChart").replaceChildren();

  const emptyRegistrations = data.metrics.new_users === 0;
  const emptyTransactions = data.metrics.period_transactions === 0;
  byId("userGrowthEmpty").classList.toggle("hidden", !emptyRegistrations);
  byId("transactionActivityEmpty").classList.toggle("hidden", !emptyTransactions);
  byId("userGrowthChart").classList.toggle("hidden", data.metrics.registered_users === 0);
  byId("transactionActivityChart").classList.toggle("hidden", emptyTransactions);

  if (data.metrics.registered_users > 0) {
    userGrowthChart = new ApexCharts(byId("userGrowthChart"), {
      chart: {type: "line", height: 320, toolbar: {show: false}, animations: {enabled: true}, redrawOnParentResize: true, redrawOnWindowResize: true},
      series: [
        {name: "Cumulative users", type: "line", data: data.series.cumulative_users},
        {name: "New registrations", type: "column", data: data.series.new_users}
      ],
      colors: ["#818cf8", "#38bdf8"],
      dataLabels: {enabled: false},
      stroke: {curve: "smooth", width: [3, 0]},
      plotOptions: {bar: {borderRadius: 3, columnWidth: data.range.interval === "day" ? "55%" : "35%"}},
      xaxis: {categories: data.series.labels, tickAmount: Math.min(data.series.labels.length, 8), labels: {rotate: -35, style: {colors: "#94a3b8"}}},
      yaxis: [
        {min: 0, forceNiceScale: true, title: {text: "Total users", style: {color: "#a5b4fc"}}, labels: {style: {colors: "#94a3b8"}}},
        {opposite: true, min: 0, forceNiceScale: true, title: {text: "New registrations", style: {color: "#7dd3fc"}}, labels: {style: {colors: "#94a3b8"}}}
      ],
      legend: {labels: {colors: "#cbd5e1"}},
      grid: {borderColor: "#1e293b"},
      tooltip: {y: {formatter: value => `${Math.round(value)} users`}},
      noData: {text: "No user records for this range"},
      theme: {mode: "dark"}
    });
    userGrowthChart.render();
  } else {
    byId("userGrowthEmpty").classList.remove("hidden");
  }

  if (!emptyTransactions) {
    transactionActivityChart = new ApexCharts(byId("transactionActivityChart"), {
      chart: {type: "bar", height: 320, toolbar: {show: false}, animations: {enabled: true}, redrawOnParentResize: true, redrawOnWindowResize: true},
      series: [{name: "Transactions", data: data.series.transactions}],
      colors: ["#34d399"],
      plotOptions: {bar: {borderRadius: 4, columnWidth: data.range.interval === "day" ? "58%" : "38%"}},
      dataLabels: {enabled: false},
      xaxis: {categories: data.series.labels, tickAmount: Math.min(data.series.labels.length, 8), labels: {rotate: -35, style: {colors: "#94a3b8"}}},
      yaxis: {min: 0, forceNiceScale: true, labels: {style: {colors: "#94a3b8"}}},
      grid: {borderColor: "#1e293b"},
      tooltip: {y: {formatter: value => `${Math.round(value)} transactions`}},
      theme: {mode: "dark"}
    });
    transactionActivityChart.render();
  }
}

async function loadAnalytics() {
  const requestId = ++analyticsRequestId;
  const startDate = byId("startDate").value;
  const endDate = byId("endDate").value;
  if (!startDate || !endDate || startDate > endDate) {
    setStatus("Choose a valid date range; the start date must not be after the end date.", true);
    byId("applyDateRange").disabled = false;
    byId("analyticsContent").setAttribute("aria-busy", "false");
    return;
  }

  const button = byId("applyDateRange");
  button.disabled = true;
  byId("analyticsContent").setAttribute("aria-busy", "true");
  setStatus("Loading platform analytics…");
  try {
    const query = new URLSearchParams({start_date: startDate, end_date: endDate});
    const response = await fetch(`/admin/api/platform-analytics?${query}`, {
      credentials: "same-origin",
      headers: {"Accept": "application/json"}
    });
    const data = await response.json();
    if (requestId !== analyticsRequestId) return;
    if (!response.ok) {
      const detail = typeof data.detail === "string" ? data.detail : "Could not load platform analytics.";
      throw new Error(response.status === 401 ? "Your admin session has expired. Sign in again to view analytics." : detail);
    }

    byId("registeredUsers").textContent = Number(data.metrics.registered_users).toLocaleString();
    byId("newUsers").textContent = Number(data.metrics.new_users).toLocaleString();
    byId("activeUsers").textContent = Number(data.metrics.active_users).toLocaleString();
    byId("totalTransactions").textContent = Number(data.metrics.total_transactions).toLocaleString();
    byId("periodTransactions").textContent = Number(data.metrics.period_transactions).toLocaleString();
    await renderCharts(data);
    setStatus(`${data.range.start_date} to ${data.range.end_date} · grouped by ${data.range.interval}`);
  } catch (error) {
    if (requestId !== analyticsRequestId) return;
    setStatus(error.message || "Analytics could not be loaded. Please try again.", true);
    console.error("Platform analytics request failed:", error);
  } finally {
    if (requestId === analyticsRequestId) {
      button.disabled = false;
      byId("analyticsContent").setAttribute("aria-busy", "false");
    }
  }
}

byId("dateRangeForm").addEventListener("submit", event => {
  event.preventDefault();
  document.querySelectorAll("[data-range-days]").forEach(button => button.setAttribute("aria-pressed", "false"));
  loadAnalytics();
});

document.querySelectorAll("[data-range-days]").forEach(button => {
  button.addEventListener("click", () => {
    setDateRange(Number(button.dataset.rangeDays));
    loadAnalytics();
  });
});

setDateRange(30);
loadAnalytics();
