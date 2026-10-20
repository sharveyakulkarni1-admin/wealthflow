const $ = (id) => document.getElementById(id);
let mode = "login";
let charts = {};
let currentUser = null;
let editingTransactionId = null;
const transactionsById = new Map();
const savingsGoalsById = new Map();
const netWorthItemsById = new Map();
let goalDialogMode = "create";
let activeGoalId = null;
let editingNetWorthId = null;
const navigationGroups = [
  {
    label: "Main",
    items: [
      {label: "Dashboard", icon: "layout-dashboard", target: "dashboard"},
      {label: "Transactions", icon: "arrow-left-right", target: "transactions"},
      {label: "Saving Goals", icon: "target", target: "saving-goals"},
      {label: "Budgets", icon: "wallet", target: "budgets"},
      {label: "Analytics & Reports", icon: "chart-no-axes-combined", target: "analytics-reports"},
      {label: "Import Transactions", icon: "file-up", target: "transaction-import"}
    ]
  },
  {
    label: "Financial tools",
    items: [
      {label: "AI Wealth Agent", icon: "sparkles", target: "ai-wealth-agent"},
      {label: "Recurring Transactions", icon: "repeat-2", target: "recurring"},
      {label: "Smart Insights", icon: "lightbulb", target: "smart-insights"},
      {label: "Export Reports", icon: "file-down", target: "export-reports"}
    ]
  },
  {
    label: "Account",
    items: [
      {label: "Account Information", icon: "circle-user-round", target: "account-information"},
      {label: "Security & Settings", icon: "settings-2", target: "settings"},
      {label: "Help & Support", icon: "circle-help", target: "help-support"},
      {label: "Log Out", icon: "log-out", action: "logout"}
    ]
  },
  {
    label: "Family",
    items: [
      {label: "Family Finances", icon: "users-round", target: "family-finances"}
    ]
  }
];
const pageForTarget = new Map([
  ["dashboard", "page-dashboard"],
  ["transactions", "page-transactions"],
  ["saving-goals", "page-budgets-savings"],
  ["budgets", "page-budgets-savings"],
  ["analytics-reports", "page-analytics-reports"],
  ["transaction-import", "page-transactions"],
  ["ai-wealth-agent", "page-ai-wealth-agent"],
  ["recurring", "page-transactions"],
  ["smart-insights", "page-dashboard"],
  ["export-reports", "page-analytics-reports"],
  ["account-information", "page-account-security"],
  ["settings", "page-account-security"],
  ["help-support", "page-help-support"],
  ["family-finances", "page-family"]
]);
const pageTitleForTarget = new Map([
  ["dashboard", "Dashboard"],
  ["transactions", "Transactions"],
  ["saving-goals", "Budgets & Savings Goals"],
  ["budgets", "Budgets & Savings Goals"],
  ["analytics-reports", "Analytics & Reports"],
  ["transaction-import", "Transactions"],
  ["ai-wealth-agent", "AI Wealth Agent"],
  ["recurring", "Transactions"],
  ["smart-insights", "Dashboard"],
  ["export-reports", "Analytics & Reports"],
  ["account-information", "Account & Security"],
  ["settings", "Account & Security"],
  ["help-support", "Help & Support"],
  ["family-finances", "Family Finances"]
]);
let selectedFamilyId = null;
let latestAnalytics = null;
const netWorthCategories = {
  asset: [
    ["cash", "Cash"],
    ["savings", "Savings"],
    ["investment", "Investment"],
    ["property", "Property"],
    ["vehicle", "Vehicle"],
    ["other", "Other"]
  ],
  liability: [
    ["loan", "Loan"],
    ["debt", "Debt"],
    ["mortgage", "Mortgage"],
    ["credit_card", "Credit card"],
    ["other", "Other"]
  ]
};
const transactionImportFields = [
  {field: "transaction_date", label: "Transaction Date", required: true},
  {field: "kind", label: "Type", required: true},
  {field: "amount", label: "Amount", required: true},
  {field: "currency", label: "Currency", required: false},
  {field: "category", label: "Category", required: true},
  {field: "merchant", label: "Merchant", required: false},
  {field: "note", label: "Note / Description", required: false},
  {field: "tags", label: "Tags", required: false}
];
let selectedImportFile = null;
let transactionImportPreview = null;
let transactionImportRequestId = null;
let transactionImportConfirmationToken = null;
let transactionImportMapping = {};
let transactionImportMappingApplied = false;
let calendarMonth = new Date(new Date().getFullYear(), new Date().getMonth(), 1);
let calendarSelectedDate = localCalendarDate(new Date());
let calendarSelectedEventId = null;
let calendarRecurringItems = [];
let calendarSavingsGoals = [];
let calendarLoadError = "";

const today = new Date().toISOString().slice(0, 10);
$("txDate").value = today;
$("recDue").value = today;

function money(v) {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: currentUser?.base_currency || "USD",
    maximumFractionDigits: 2
  }).format(Number(v || 0));
}

async function api(url, options = {}) {
  const isMultipart = options.body instanceof FormData;
  const res = await fetch(url, {
    credentials: "include",
    headers: {...(isMultipart ? {} : {"Content-Type": "application/json"}), ...(options.headers || {})},
    ...options
  });
  if (!res.ok) {
    let msg = "Request failed";
    try {
      const detail = (await res.json()).detail;
      if (Array.isArray(detail)) {
        msg = detail.map(item => item.msg || JSON.stringify(item)).join("; ");
      } else if (typeof detail === "string") {
        msg = detail;
      }
    } catch {}
    throw new Error(msg);
  }
  return res.json();
}

function renderNavigation() {
  const nav = $("sidebarNav");
  for (const group of navigationGroups) {
    const section = document.createElement("section");
    section.className = "space-y-1";

    const heading = document.createElement("h2");
    heading.className = "sidebar-group-label px-3 pb-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-600";
    heading.textContent = group.label;
    section.appendChild(heading);

    for (const item of group.items) {
      const control = item.target || item.action
        ? document.createElement(item.action ? "button" : "a")
        : document.createElement("button");
      control.className = "sidebar-nav-link flex min-h-11 w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm text-slate-400 focus-visible:outline-none";
      control.title = item.comingSoon ? `${item.label}: Coming Soon` : item.label;
      control.setAttribute("aria-label", item.label);

      if (item.target) {
        control.href = `#${item.target}`;
        control.dataset.navTarget = item.target;
      } else if (item.action) {
        control.type = "button";
        control.dataset.navAction = item.action;
      } else {
        control.type = "button";
        control.disabled = true;
        control.setAttribute("aria-disabled", "true");
        control.classList.add("cursor-not-allowed", "opacity-60");
      }

      const icon = document.createElement("i");
      icon.dataset.lucide = item.icon;
      icon.className = "h-5 w-5 shrink-0";
      const label = document.createElement("span");
      label.className = "sidebar-label min-w-0 flex-1 truncate";
      label.textContent = item.label;
      control.append(icon, label);

      if (item.comingSoon) {
        const badge = document.createElement("span");
        badge.className = "sidebar-coming-soon rounded-md bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-500";
        badge.textContent = "Soon";
        control.appendChild(badge);
      }
      section.appendChild(control);
    }
    nav.appendChild(section);
  }
  lucide.createIcons();
}

function setActiveSection(target, updateHash = false) {
  const section = pageForTarget.has(target) ? target : "dashboard";
  const pageId = pageForTarget.get(section);
  document.querySelectorAll(".wealth-page").forEach(page => {
    page.classList.toggle("hidden", page.id !== pageId);
  });
  $("sidebarNav").querySelectorAll("[data-nav-target]").forEach(link => {
    if (link.dataset.navTarget === section) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  $("pageTitle").textContent = pageTitleForTarget.get(section) || "Dashboard";
  if (updateHash && location.hash !== `#${section}`) {
    history.replaceState(null, "", `#${section}`);
  }
  if ((pageId === "page-dashboard" || pageId === "page-analytics-reports") && latestAnalytics) {
    requestAnimationFrame(() => renderCharts(latestAnalytics));
  }
  if (pageId === "page-family") loadFamilyPage();
}

function closeMobileSidebar() {
  document.body.classList.remove("sidebar-open");
  $("mobileNavToggle").setAttribute("aria-expanded", "false");
  $("mobileNavToggle").setAttribute("aria-label", "Open navigation");
}

function setSidebarCollapsed(collapsed) {
  document.body.classList.toggle("sidebar-collapsed", collapsed);
  for (const button of [$("sidebarCollapse"), $("desktopSidebarToggle")]) {
    button.setAttribute("aria-expanded", String(!collapsed));
    button.setAttribute("aria-label", collapsed ? "Expand sidebar" : "Collapse sidebar");
    button.title = collapsed ? "Expand sidebar" : "Collapse sidebar";
    const icon = button.querySelector("i");
    if (icon) icon.dataset.lucide = collapsed ? "panel-left-open" : "panel-left-close";
  }
  try { localStorage.setItem("wealthflow.sidebar-collapsed", String(collapsed)); } catch {}
  lucide.createIcons();
}

function setupSidebar() {
  renderNavigation();
  let collapsed = false;
  try { collapsed = localStorage.getItem("wealthflow.sidebar-collapsed") === "true"; } catch {}
  setSidebarCollapsed(collapsed);

  $("sidebarCollapse").addEventListener("click", () => {
    setSidebarCollapsed(!document.body.classList.contains("sidebar-collapsed"));
  });
  $("desktopSidebarToggle").addEventListener("click", () => {
    setSidebarCollapsed(!document.body.classList.contains("sidebar-collapsed"));
  });
  $("mobileNavToggle").addEventListener("click", () => {
    const open = document.body.classList.toggle("sidebar-open");
    $("mobileNavToggle").setAttribute("aria-expanded", String(open));
    $("mobileNavToggle").setAttribute("aria-label", open ? "Close navigation" : "Open navigation");
  });
  $("sidebarOverlay").addEventListener("click", closeMobileSidebar);
  $("sidebarNav").addEventListener("click", async event => {
    const actionButton = event.target.closest("[data-nav-action]");
    if (actionButton?.dataset.navAction === "logout") {
      await logout();
      return;
    }

    const link = event.target.closest("[data-nav-target]");
    if (link) {
      event.preventDefault();
      closeMobileSidebar();
      const target = link.dataset.navTarget;
      if (location.hash !== `#${target}`) {
        history.pushState(null, "", `#${target}`);
      }
      setActiveSection(target);
      window.scrollTo({top: 0, behavior: "smooth"});
    }
  });
  window.addEventListener("hashchange", () => {
    const target = location.hash.slice(1) || "dashboard";
    setActiveSection(target, true);
    window.scrollTo({top: 0, behavior: "smooth"});
  });
  document.addEventListener("keydown", event => {
    if (event.key === "Escape") closeMobileSidebar();
  });
  setActiveSection(pageForTarget.has(location.hash.slice(1)) ? location.hash.slice(1) : "dashboard", true);
}

function renderAccountInformation(user) {
  $("accountName").textContent = user.full_name || "Not provided";
  $("accountEmail").textContent = user.email || "Not provided";
  $("accountId").textContent = String(user.id);
  $("accountCurrency").textContent = user.base_currency || "Not set";
  $("profileDisplayName").value = user.full_name || "";
  $("profileEmail").value = user.email || "";
  $("profileCreatedAt").value = user.created_at ? formatProfileDate(user.created_at.slice(0, 10)) : "Not available";
  $("sidebarUserName").textContent = user.full_name || user.email || "Signed in";
  $("settingsTheme").value = user.theme || "system";
  $("settingsCurrency").value = user.base_currency || "USD";
  $("settingsDateFormat").value = user.date_format || "iso";
}

function formatProfileDate(value) {
  if (!value) return "Not available";
  const date = new Date(`${value.slice(0, 10)}T00:00:00`);
  const locale = currentUser?.date_format === "us" ? "en-US" : currentUser?.date_format === "eu" ? "en-GB" : "en-CA";
  return date.toLocaleDateString(locale);
}

function applyTheme(theme) {
  const media = window.matchMedia?.("(prefers-color-scheme: dark)");
  const dark = theme === "dark" || (theme === "system" && (media?.matches ?? true));
  document.documentElement.dataset.colorScheme = dark ? "dark" : "light";
  document.documentElement.classList.toggle("dark", dark);
}

window.matchMedia?.("(prefers-color-scheme: dark)").addEventListener?.("change", () => {
  if (currentUser?.theme === "system") applyTheme("system");
});

function formatTransactionDate(value) {
  if (!value) return "—";
  if (currentUser?.date_format === "iso") return value;
  const date = new Date(`${value.slice(0, 10)}T00:00:00`);
  return date.toLocaleDateString(currentUser?.date_format === "us" ? "en-US" : "en-GB");
}

function setMode(next) {
  mode = next;
  $("loginTab").className = `btn flex-1 ${mode === "login" ? "bg-indigo-500" : "bg-slate-800"}`;
  $("signupTab").className = `btn flex-1 ${mode === "signup" ? "bg-indigo-500" : "bg-slate-800"}`;
  $("nameWrap").classList.toggle("hidden", mode !== "signup");
}

$("loginTab").onclick = () => setMode("login");
$("signupTab").onclick = () => setMode("signup");

$("authForm").onsubmit = async (e) => {
  e.preventDefault();
  $("authError").textContent = "";
  try {
    const body = {
      email: $("email").value,
      password: $("password").value
    };
    if (mode === "signup") {
      body.full_name = $("name").value;
      body.base_currency = $("authCurrency").value;
    }
    currentUser = await api(`/api/auth/${mode === "signup" ? "signup" : "login"}`, {
      method: "POST", body: JSON.stringify(body)
    });
    await startApp();
  } catch (err) {
    $("authError").textContent = err.message;
  }
};

async function logout() {
  try {
    await api("/api/auth/logout", {method: "POST"});
    location.assign("/login");
  } catch (error) {
    console.error("Logout failed:", error);
    $("sidebarUserName").textContent = `Logout failed: ${error.message}`;
  }
}

async function savePreferences(preferences) {
  currentUser = await api("/api/settings/preferences", {
    method: "PATCH",
    body: JSON.stringify(preferences)
  });
  renderAccountInformation(currentUser);
  applyTheme(currentUser.theme);
  await refresh();
}

$("baseCurrency").onchange = async () => {
  $("settingsCurrency").value = $("baseCurrency").value;
  try {
    await savePreferences({
      theme: currentUser.theme || "system",
      date_format: currentUser.date_format || "iso",
      base_currency: $("baseCurrency").value
    });
  } catch (error) {
    $("baseCurrency").value = currentUser.base_currency;
    $("settingsCurrency").value = currentUser.base_currency;
    console.error("Currency preference could not be saved:", error);
  }
};

async function startApp() {
  if (location.pathname !== "/app") {
    history.replaceState(null, "", `/app${location.hash}`);
  }
  $("auth").classList.add("hidden");
  $("app").classList.remove("hidden");
  renderAccountInformation(currentUser);
  $("baseCurrency").value = currentUser.base_currency;
  $("familyBudgetCurrency").value = currentUser.base_currency;
  $("familyGoalCurrency").value = currentUser.base_currency;
  applyTheme(currentUser.theme || "system");
  const target = pageForTarget.has(location.hash.slice(1)) ? location.hash.slice(1) : "dashboard";
  setActiveSection(target, true);
  window.scrollTo({top: 0});
  window.dispatchEvent(new CustomEvent("wealthflow:authenticated", {
    detail: {userId: currentUser.id}
  }));
  lucide.createIcons();
  await refresh();
  await loadSupportTickets();
}

function setSettingsMessage(id, message, success = false) {
  const element = $(id);
  element.textContent = message;
  element.className = `text-sm ${success ? "text-emerald-400" : "text-rose-400"}`;
}

$("profileSettingsForm").addEventListener("submit", async event => {
  event.preventDefault();
  const button = event.currentTarget.querySelector('button[type="submit"]');
  button.disabled = true;
  try {
    currentUser = await api("/api/settings/profile", {
      method: "PATCH",
      body: JSON.stringify({full_name: $("profileDisplayName").value.trim()})
    });
    renderAccountInformation(currentUser);
    setSettingsMessage("profileSettingsMessage", "Profile saved.", true);
  } catch (error) {
    setSettingsMessage("profileSettingsMessage", error.message);
  } finally {
    button.disabled = false;
  }
});

$("preferencesForm").addEventListener("submit", async event => {
  event.preventDefault();
  const button = event.currentTarget.querySelector('button[type="submit"]');
  button.disabled = true;
  try {
    await savePreferences({
      theme: $("settingsTheme").value,
      date_format: $("settingsDateFormat").value,
      base_currency: $("settingsCurrency").value
    });
    $("baseCurrency").value = currentUser.base_currency;
    setSettingsMessage("preferencesMessage", "Preferences saved.", true);
  } catch (error) {
    setSettingsMessage("preferencesMessage", error.message);
  } finally {
    button.disabled = false;
  }
});

$("passwordSettingsForm").addEventListener("submit", async event => {
  event.preventDefault();
  const form = event.currentTarget;
  if ($("newPassword").value !== $("confirmNewPassword").value) {
    setSettingsMessage("passwordSettingsMessage", "The new password confirmation does not match.");
    return;
  }
  const button = form.querySelector('button[type="submit"]');
  button.disabled = true;
  try {
    await api("/api/settings/password", {
      method: "POST",
      body: JSON.stringify({
        current_password: $("currentPassword").value,
        new_password: $("newPassword").value,
        confirm_password: $("confirmNewPassword").value
      })
    });
    form.reset();
    currentUser = null;
    $("app").classList.add("hidden");
    $("auth").classList.remove("hidden");
    setMode("login");
    $("authError").textContent = "Password changed. Sign in again with your new password.";
  } catch (error) {
    setSettingsMessage("passwordSettingsMessage", error.message);
  } finally {
    button.disabled = false;
  }
});

$("settingsLogout").addEventListener("click", logout);

function renderSupportTickets(tickets) {
  const list = $("supportTicketList");
  list.replaceChildren();
  if (!tickets.length) {
    const empty = document.createElement("p");
    empty.className = "text-sm text-slate-400";
    empty.textContent = "No saved support requests yet.";
    list.appendChild(empty);
    return;
  }

  for (const ticket of tickets) {
    const card = document.createElement("article");
    card.className = "rounded-xl border border-slate-700 bg-slate-900/60 p-4";
    const heading = document.createElement("div");
    heading.className = "flex flex-wrap items-center justify-between gap-2";
    const subject = document.createElement("h5");
    subject.className = "font-medium";
    subject.textContent = ticket.subject;
    const status = document.createElement("span");
    status.className = "rounded-full bg-amber-500/10 px-2.5 py-1 text-xs text-amber-300";
    status.textContent = `Saved locally · ${ticket.status}`;
    heading.append(subject, status);
    const meta = document.createElement("p");
    meta.className = "mt-1 text-xs text-slate-500";
    meta.textContent = `${ticket.category} · ${new Date(ticket.created_at).toLocaleString()} · Reference #${ticket.id}`;
    const message = document.createElement("p");
    message.className = "mt-3 whitespace-pre-wrap break-words text-sm text-slate-300";
    message.textContent = ticket.message;
    card.append(heading, meta, message);
    list.appendChild(card);
  }
}

async function loadSupportTickets() {
  try {
    renderSupportTickets(await api("/api/support/tickets"));
  } catch (error) {
    const list = $("supportTicketList");
    list.replaceChildren();
    const message = document.createElement("p");
    message.className = "text-sm text-rose-400";
    message.textContent = `Could not load your saved requests: ${error.message}`;
    list.appendChild(message);
  }
}

$("supportForm").addEventListener("submit", async event => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = $("supportSubmit");
  button.disabled = true;
  try {
    const ticket = await api("/api/support/tickets", {
      method: "POST",
      body: JSON.stringify({
        subject: $("supportSubject").value.trim(),
        category: $("supportCategory").value,
        message: $("supportMessage").value.trim(),
        contact_email: $("supportContactEmail").value.trim() || null
      })
    });
    form.reset();
    setSettingsMessage("supportMessageStatus", `Request #${ticket.id} saved to your account. It was not emailed.`, true);
    await loadSupportTickets();
  } catch (error) {
    setSettingsMessage("supportMessageStatus", error.message);
  } finally {
    button.disabled = false;
  }
});

function localCalendarDate(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function parseCalendarDate(value) {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const [year, month, day] = value.split("-").map(Number);
  const date = new Date(0);
  date.setFullYear(year, month - 1, day);
  date.setHours(0, 0, 0, 0);
  return date.getFullYear() === year && date.getMonth() === month - 1 && date.getDate() === day
    ? date
    : null;
}

function advanceCalendarOccurrence(date, frequency) {
  const next = new Date(date);
  if (frequency === "weekly") {
    next.setDate(next.getDate() + 7);
    return next;
  }
  const targetMonth = next.getMonth() + (frequency === "monthly" ? 1 : 12);
  const targetYear = next.getFullYear() + Math.floor(targetMonth / 12);
  const normalizedMonth = targetMonth % 12;
  const lastDay = new Date(targetYear, normalizedMonth + 1, 0).getDate();
  next.setFullYear(targetYear, normalizedMonth, Math.min(next.getDate(), lastDay));
  return next;
}

function makeCalendarEvents(month, recurringItems, savingsGoals) {
  const start = new Date(month.getFullYear(), month.getMonth(), 1);
  const end = new Date(month.getFullYear(), month.getMonth() + 1, 0);
  const events = [];

  for (const item of recurringItems) {
    if (!item.active) continue;
    let due = parseCalendarDate(item.next_due);
    if (!due || !["weekly", "monthly", "yearly"].includes(item.frequency)) continue;

    if (item.frequency === "weekly" && due < start) {
      const daysUntilMonth = Math.floor((Date.UTC(start.getFullYear(), start.getMonth(), start.getDate()) -
        Date.UTC(due.getFullYear(), due.getMonth(), due.getDate())) / 86400000);
      due.setDate(due.getDate() + Math.ceil(daysUntilMonth / 7) * 7);
    } else {
      let advances = 0;
      while (due < start && advances < 12000) {
        due = advanceCalendarOccurrence(due, item.frequency);
        advances += 1;
      }
      if (advances === 12000 && due < start) continue;
    }

    let occurrences = 0;
    while (due <= end && occurrences < 8) {
      const date = localCalendarDate(due);
      events.push({
        id: `recurring-${item.id}-${date}`,
        date,
        title: item.name,
        type: item.kind === "expense" ? "bill" : "recurring",
        details: item
      });
      due = advanceCalendarOccurrence(due, item.frequency);
      occurrences += 1;
    }
  }

  for (const goal of savingsGoals) {
    if (!goal.deadline || !parseCalendarDate(goal.deadline)) continue;
    const deadline = parseCalendarDate(goal.deadline);
    if (deadline.getFullYear() !== month.getFullYear() || deadline.getMonth() !== month.getMonth()) continue;
    events.push({
      id: `goal-${goal.id}`,
      date: goal.deadline,
      title: goal.name,
      type: "goal",
      details: goal
    });
  }

  return events.sort((left, right) => left.date.localeCompare(right.date) || left.title.localeCompare(right.title));
}

function calendarEventColor(type) {
  if (type === "bill") return "border-amber-400/20 bg-amber-400/10 text-amber-200";
  if (type === "goal") return "border-emerald-400/20 bg-emerald-400/10 text-emerald-200";
  return "border-sky-400/20 bg-sky-400/10 text-sky-200";
}

function renderCalendarEventDetails(event) {
  const details = $("calendarEventDetails");
  details.replaceChildren();

  if (!event) {
    const selectedEvents = makeCalendarEvents(calendarMonth, calendarRecurringItems, calendarSavingsGoals)
      .filter(item => item.date === calendarSelectedDate);
    const message = document.createElement("p");
    message.className = "text-sm text-slate-400";
    const selectedDate = parseCalendarDate(calendarSelectedDate);
    const dateLabel = selectedDate
      ? selectedDate.toLocaleDateString(undefined, {weekday: "long", year: "numeric", month: "long", day: "numeric"})
      : calendarSelectedDate;
    message.textContent = selectedEvents.length
      ? `${selectedEvents.length} event${selectedEvents.length === 1 ? "" : "s"} on ${dateLabel}. Select an event for details.`
      : `No scheduled events on ${dateLabel}.`;
    details.appendChild(message);
    return;
  }

  const title = document.createElement("h4");
  title.className = "font-semibold";
  title.textContent = event.title;

  const summary = document.createElement("p");
  summary.className = "mt-1 text-sm text-slate-400";
  const eventDate = parseCalendarDate(event.date);
  const dateLabel = eventDate
    ? eventDate.toLocaleDateString(undefined, {weekday: "long", year: "numeric", month: "long", day: "numeric"})
    : event.date;
  summary.textContent = `${event.type === "goal" ? "Savings goal deadline" : event.type === "bill" ? "Scheduled recurring bill" : "Scheduled recurring income"} · ${dateLabel}`;
  details.append(title, summary);

  const extra = document.createElement("p");
  extra.className = "mt-2 text-sm text-slate-300";
  if (event.type === "goal") {
    extra.textContent = `${goalMoney(event.details.saved_amount, event.details.currency)} saved of ${goalMoney(event.details.target_amount, event.details.currency)}.`;
  } else {
    extra.textContent = `${goalMoney(event.details.amount, event.details.currency)} · ${event.details.category} · ${event.details.frequency}.`;
  }
  details.appendChild(extra);

  if (event.type === "bill") {
    const note = document.createElement("p");
    note.className = "mt-2 text-xs text-amber-200/80";
    note.textContent = "Scheduled from a recurring rule; this is not a payment confirmation. WealthFlow records the transaction when the recurring schedule is processed.";
    details.appendChild(note);
  }
}

function renderCalendar() {
  const status = $("calendarStatus");
  const content = $("calendarContent");
  if (calendarLoadError) {
    status.textContent = calendarLoadError;
    status.className = "mb-3 text-sm text-rose-400";
    status.classList.remove("hidden");
    content.classList.add("hidden");
    return;
  }
  status.classList.add("hidden");
  content.classList.remove("hidden");

  $("calendarMonthLabel").textContent = calendarMonth.toLocaleDateString(undefined, {month: "long", year: "numeric"});
  const events = makeCalendarEvents(calendarMonth, calendarRecurringItems, calendarSavingsGoals);
  const eventsByDate = new Map();
  for (const event of events) {
    if (!eventsByDate.has(event.date)) eventsByDate.set(event.date, []);
    eventsByDate.get(event.date).push(event);
  }

  const days = $("calendarDays");
  days.replaceChildren();
  const firstWeekday = (new Date(calendarMonth.getFullYear(), calendarMonth.getMonth(), 1).getDay() + 6) % 7;
  const monthDays = new Date(calendarMonth.getFullYear(), calendarMonth.getMonth() + 1, 0).getDate();
  const cellCount = Math.ceil((firstWeekday + monthDays) / 7) * 7;
  const todayDate = localCalendarDate(new Date());

  for (let cell = 0; cell < cellCount; cell += 1) {
    const dayNumber = cell - firstWeekday + 1;
    const cellElement = document.createElement("div");
    cellElement.className = "calendar-day flex flex-col gap-1 border-b border-r border-slate-700 p-2";
    cellElement.setAttribute("role", "gridcell");
    if (dayNumber < 1 || dayNumber > monthDays) {
      cellElement.setAttribute("aria-label", "Outside this month");
      days.appendChild(cellElement);
      continue;
    }

    const date = `${calendarMonth.getFullYear()}-${String(calendarMonth.getMonth() + 1).padStart(2, "0")}-${String(dayNumber).padStart(2, "0")}`;
    const dateButton = document.createElement("button");
    dateButton.type = "button";
    dateButton.className = `self-start rounded-md px-1.5 py-0.5 text-xs ${date === todayDate ? "bg-indigo-500 text-white" : date === calendarSelectedDate ? "bg-slate-700 text-white" : "text-slate-300 hover:bg-slate-800"}`;
    dateButton.textContent = String(dayNumber);
    dateButton.setAttribute("aria-label", `Select ${new Date(calendarMonth.getFullYear(), calendarMonth.getMonth(), dayNumber).toLocaleDateString(undefined, {dateStyle: "full"})}`);
    dateButton.setAttribute("aria-pressed", String(date === calendarSelectedDate));
    dateButton.addEventListener("click", () => {
      calendarSelectedDate = date;
      calendarSelectedEventId = null;
      renderCalendar();
    });
    cellElement.appendChild(dateButton);
    cellElement.setAttribute("aria-label", `${date}, ${(eventsByDate.get(date) || []).length} events`);

    const dateEvents = eventsByDate.get(date) || [];
    for (const event of dateEvents) {
      const eventButton = document.createElement("button");
      eventButton.type = "button";
      eventButton.className = `calendar-event flex items-center gap-1 rounded-md border px-1.5 py-1 text-left text-[10px] leading-tight hover:brightness-125 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-300 ${calendarEventColor(event.type)}`;
      eventButton.setAttribute("aria-label", `${event.type === "goal" ? "Savings goal deadline" : event.type === "bill" ? "Scheduled bill" : "Recurring income"}: ${event.title}`);
      eventButton.setAttribute("aria-pressed", String(calendarSelectedEventId === event.id));
      const dot = document.createElement("span");
      dot.className = "h-1.5 w-1.5 shrink-0 rounded-full bg-current";
      dot.setAttribute("aria-hidden", "true");
      const label = document.createElement("span");
      label.className = "calendar-event-label";
      label.textContent = event.title;
      eventButton.append(dot, label);
      eventButton.addEventListener("click", () => {
        calendarSelectedDate = event.date;
        calendarSelectedEventId = event.id;
        renderCalendar();
      });
      cellElement.appendChild(eventButton);
    }
    days.appendChild(cellElement);
  }

  const upcoming = $("calendarUpcomingEvents");
  upcoming.replaceChildren();
  $("upcomingEventsRange").textContent = `Remaining in ${calendarMonth.toLocaleDateString(undefined, {month: "long"})}`;
  const upcomingEvents = events.filter(event => event.date >= todayDate).slice(0, 8);
  if (!upcomingEvents.length) {
    const empty = document.createElement("p");
    empty.className = "text-sm text-slate-400";
    empty.textContent = events.length ? "No more events this month." : "No scheduled events this month.";
    upcoming.appendChild(empty);
  } else {
    for (const event of upcomingEvents) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `flex w-full items-start gap-2 rounded-lg border p-2 text-left hover:bg-slate-800/70 ${calendarEventColor(event.type)}`;
      button.setAttribute("aria-label", `View ${event.title} on ${event.date}`);
      const date = document.createElement("span");
      date.className = "shrink-0 text-xs font-semibold";
      date.textContent = parseCalendarDate(event.date).toLocaleDateString(undefined, {month: "short", day: "numeric"});
      const copy = document.createElement("span");
      copy.className = "min-w-0";
      const name = document.createElement("span");
      name.className = "block truncate text-xs font-medium";
      name.textContent = event.title;
      const type = document.createElement("span");
      type.className = "block text-[10px] opacity-75";
      type.textContent = event.type === "goal" ? "Goal deadline" : event.type === "bill" ? "Scheduled bill" : "Recurring income";
      copy.append(name, type);
      button.append(date, copy);
      button.addEventListener("click", () => {
        calendarSelectedDate = event.date;
        calendarSelectedEventId = event.id;
        renderCalendar();
      });
      upcoming.appendChild(button);
    }
  }

  renderCalendarEventDetails(events.find(event => event.id === calendarSelectedEventId) || null);
}

function moveCalendarMonth(offset) {
  calendarMonth = new Date(calendarMonth.getFullYear(), calendarMonth.getMonth() + offset, 1);
  calendarSelectedDate = localCalendarDate(calendarMonth);
  calendarSelectedEventId = null;
  renderCalendar();
}

$("calendarPrevious").addEventListener("click", () => moveCalendarMonth(-1));
$("calendarNext").addEventListener("click", () => moveCalendarMonth(1));
$("calendarToday").addEventListener("click", () => {
  const now = new Date();
  calendarMonth = new Date(now.getFullYear(), now.getMonth(), 1);
  calendarSelectedDate = localCalendarDate(now);
  calendarSelectedEventId = null;
  renderCalendar();
});

async function loadFinancialCalendar(goals) {
  const status = $("calendarStatus");
  const content = $("calendarContent");
  calendarLoadError = "";
  status.textContent = "Loading financial calendar…";
  status.className = "mb-3 text-sm text-slate-400";
  status.classList.remove("hidden");
  content.classList.add("hidden");

  if (!Array.isArray(goals)) {
    calendarLoadError = "Could not load financial calendar because savings goals could not be loaded. Refresh the page to try again.";
    renderCalendar();
    return;
  }

  try {
    calendarRecurringItems = await api("/api/recurring");
    calendarSavingsGoals = goals;
    renderCalendar();
  } catch (error) {
    calendarLoadError = `Could not load financial calendar: ${error.message}. Refresh the page to try again.`;
    renderCalendar();
    console.error("Financial calendar refresh failed:", error);
  }
}

function setNetWorthStatus(message, error = false) {
  const status = $("netWorthStatus");
  status.textContent = message;
  status.className = `mb-3 text-sm ${error ? "text-rose-400" : "text-slate-400"}`;
  status.classList.toggle("hidden", !message);
}

function renderNetWorthItemList(items, kind, currency) {
  const container = $(kind === "asset" ? "netWorthAssetsList" : "netWorthLiabilitiesList");
  const count = $(kind === "asset" ? "netWorthAssetsCount" : "netWorthLiabilitiesCount");
  count.textContent = `${items.length} recorded`;
  container.replaceChildren();

  if (!items.length) {
    const empty = document.createElement("p");
    empty.className = "rounded-lg border border-dashed border-slate-700 p-4 text-sm text-slate-400";
    empty.textContent = kind === "asset"
      ? "No assets recorded. Add a cash, savings, or investment estimate."
      : "No liabilities recorded. Add a loan or debt balance estimate.";
    container.appendChild(empty);
    return;
  }

  for (const item of items) {
    const row = document.createElement("article");
    row.className = "flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-700 bg-slate-900/60 p-3";
    const copy = document.createElement("div");
    copy.className = "min-w-0";
    const name = document.createElement("p");
    name.className = "break-words text-sm font-medium";
    name.textContent = item.name;
    const category = document.createElement("p");
    category.className = "mt-1 text-xs capitalize text-slate-400";
    category.textContent = item.category.replaceAll("_", " ");
    copy.append(name, category);

    const amountWrap = document.createElement("div");
    amountWrap.className = "ml-auto text-right";
    const amount = document.createElement("p");
    amount.className = `text-sm font-semibold ${kind === "asset" ? "text-emerald-300" : "text-amber-300"}`;
    amount.textContent = goalMoney(item.amount, item.currency);
    const converted = document.createElement("p");
    converted.className = "text-xs text-slate-500";
    converted.textContent = `${goalMoney(item.amount_base, currency)} in ${currency}`;
    amountWrap.append(amount, converted);

    const actions = document.createElement("div");
    actions.className = "flex gap-1";
    const edit = document.createElement("button");
    edit.type = "button";
    edit.className = "btn bg-slate-800 px-2 py-1 text-xs";
    edit.dataset.netWorthAction = "edit";
    edit.dataset.netWorthId = String(item.id);
    edit.setAttribute("aria-label", `Edit ${kind}: ${item.name}`);
    edit.textContent = "Edit";
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "btn bg-slate-800 px-2 py-1 text-xs text-rose-300";
    remove.dataset.netWorthAction = "delete";
    remove.dataset.netWorthId = String(item.id);
    remove.setAttribute("aria-label", `Delete ${kind}: ${item.name}`);
    remove.textContent = "Delete";
    actions.append(edit, remove);

    row.append(copy, amountWrap, actions);
    container.appendChild(row);
  }
}

function renderNetWorthChart(history, currency) {
  const container = $("netWorthHistoryChart");
  if (charts.netWorth) {
    charts.netWorth.destroy();
    charts.netWorth = null;
  }
  container.replaceChildren();
  if (!history.length) {
    const empty = document.createElement("p");
    empty.className = "py-12 text-center text-sm text-slate-400";
    empty.textContent = "No historical snapshots yet. A point is recorded when you add, update, or delete a balance.";
    container.appendChild(empty);
    return;
  }

  const lightTheme = document.documentElement.dataset.colorScheme === "light";
  const mutedText = lightTheme ? "#475569" : "#94a3b8";
  charts.netWorth = new ApexCharts(container, {
    chart: {type: "line", height: 300, toolbar: {show: false}, animations: {enabled: true}},
    series: [
      {name: "Assets", data: history.map(point => Number(point.total_assets))},
      {name: "Liabilities", data: history.map(point => Number(point.total_liabilities))},
      {name: "Net worth", data: history.map(point => Number(point.net_worth))}
    ],
    colors: ["#34d399", "#fbbf24", "#818cf8"],
    xaxis: {categories: history.map(point => point.snapshot_date), labels: {style: {colors: mutedText}}},
    yaxis: {labels: {formatter: value => goalMoney(value, currency), style: {colors: mutedText}}},
    stroke: {curve: "smooth", width: 2},
    markers: {size: history.length === 1 ? 4 : 2},
    dataLabels: {enabled: false},
    legend: {labels: {colors: lightTheme ? "#334155" : "#cbd5e1"}},
    grid: {borderColor: lightTheme ? "#cbd5e1" : "#1e293b"},
    theme: {mode: lightTheme ? "light" : "dark"},
    tooltip: {y: {formatter: value => goalMoney(value, currency)}}
  });
  charts.netWorth.render();
}

function renderNetWorth(data) {
  $("netWorthAssetsTotal").textContent = goalMoney(data.total_assets, data.base_currency);
  $("netWorthLiabilitiesTotal").textContent = goalMoney(data.total_liabilities, data.base_currency);
  $("netWorthTotal").textContent = goalMoney(data.net_worth, data.base_currency);
  $("netWorthCurrency").value = currentUser.base_currency;
  netWorthItemsById.clear();
  [...data.assets, ...data.liabilities].forEach(item => netWorthItemsById.set(item.id, item));
  renderNetWorthItemList(data.assets, "asset", data.base_currency);
  renderNetWorthItemList(data.liabilities, "liability", data.base_currency);
  renderNetWorthChart(data.history, data.base_currency);
}

async function loadNetWorth() {
  const content = $("netWorthContent");
  content.classList.add("hidden");
  setNetWorthStatus("Loading your recorded balances…");
  try {
    const data = await api("/api/net-worth");
    renderNetWorth(data);
    setNetWorthStatus("");
    content.classList.remove("hidden");
    return data;
  } catch (error) {
    setNetWorthStatus(`Could not load net worth: ${error.message}. Try refreshing the page.`, true);
    console.error("Net worth refresh failed:", error);
    return null;
  }
}

function setNetWorthCategories(kind, selected = "") {
  const select = $("netWorthCategory");
  select.replaceChildren();
  for (const [value, label] of netWorthCategories[kind]) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    select.appendChild(option);
  }
  if (netWorthCategories[kind].some(([value]) => value === selected)) {
    select.value = selected;
  }
}

function resetNetWorthForm() {
  editingNetWorthId = null;
  $("netWorthForm").reset();
  $("netWorthKind").disabled = false;
  $("netWorthCurrency").value = currentUser?.base_currency || "USD";
  $("netWorthFormTitle").textContent = "Add balance";
  $("netWorthSubmit").textContent = "Add balance";
  $("netWorthCancel").classList.add("hidden");
  $("netWorthKind").value = "asset";
  setNetWorthCategories("asset");
}

$("netWorthKind").addEventListener("change", () => {
  setNetWorthCategories($("netWorthKind").value);
});
$("netWorthCancel").addEventListener("click", resetNetWorthForm);
$("netWorthForm").addEventListener("submit", async event => {
  event.preventDefault();
  const submit = $("netWorthSubmit");
  const wasEditing = editingNetWorthId !== null;
  const itemId = editingNetWorthId;
  const payload = {
    kind: $("netWorthKind").value,
    name: $("netWorthName").value.trim(),
    category: $("netWorthCategory").value,
    amount: Number($("netWorthAmount").value),
    currency: $("netWorthCurrency").value
  };
  submit.disabled = true;
  setNetWorthStatus(wasEditing ? "Updating recorded balance…" : "Saving recorded balance…");
  try {
    await api(wasEditing ? `/api/net-worth/items/${itemId}` : "/api/net-worth/items", {
      method: wasEditing ? "PUT" : "POST",
      body: JSON.stringify(payload)
    });
    resetNetWorthForm();
    const data = await loadNetWorth();
    if (data) setNetWorthStatus(wasEditing ? "Balance updated and history snapshot recorded." : "Balance saved and history snapshot recorded.");
  } catch (error) {
    setNetWorthStatus(`Could not save balance: ${error.message}`, true);
    console.error("Net worth save failed:", error);
  } finally {
    submit.disabled = false;
  }
});

document.querySelectorAll("#netWorthAssetsList, #netWorthLiabilitiesList").forEach(container => {
  container.addEventListener("click", async event => {
    const button = event.target.closest("[data-net-worth-action]");
    if (!button) return;
    const item = netWorthItemsById.get(Number(button.dataset.netWorthId));
    if (!item) return;

    if (button.dataset.netWorthAction === "edit") {
      editingNetWorthId = item.id;
      $("netWorthKind").value = item.kind;
      $("netWorthKind").disabled = true;
      setNetWorthCategories(item.kind, item.category);
      $("netWorthName").value = item.name;
      $("netWorthAmount").value = item.amount;
      $("netWorthCurrency").value = item.currency;
      $("netWorthFormTitle").textContent = "Update balance";
      $("netWorthSubmit").textContent = "Save changes";
      $("netWorthCancel").classList.remove("hidden");
      $("netWorthName").focus();
      return;
    }

    if (!window.confirm(`Delete "${item.name}" from your ${item.kind} list? This will update today's net-worth snapshot.`)) return;
    button.disabled = true;
    setNetWorthStatus(`Deleting ${item.name}…`);
    try {
      await api(`/api/net-worth/items/${item.id}`, {method: "DELETE"});
      if (editingNetWorthId === item.id) resetNetWorthForm();
      const data = await loadNetWorth();
      if (data) setNetWorthStatus("Balance deleted and history snapshot updated.");
    } catch (error) {
      setNetWorthStatus(`Could not delete balance: ${error.message}`, true);
      console.error("Net worth delete failed:", error);
    } finally {
      button.disabled = false;
    }
  });
});

async function refresh() {
  const [analytics, txs] = await Promise.all([
    api("/api/analytics"),
    loadTransactions()
  ]);
  latestAnalytics = analytics;
  renderMetrics(analytics);
  renderBudgetAlerts(analytics);
  renderSpendingInsights(analytics);
  renderReports(analytics);
  renderCharts(analytics);
  renderLedger(txs);
  const [goals] = await Promise.all([loadSavingsGoals(), loadBudgets(), loadNetWorth()]);
  await loadFinancialCalendar(goals);
  lucide.createIcons();
}

function setFamilyStatus(message, isError = false) {
  const status = $("familyStatus");
  status.textContent = message;
  status.className = `mt-3 text-sm ${isError ? "text-rose-400" : "text-slate-400"}`;
}

function setFamilySettingsStatus(message, success = false) {
  const status = $("familySettingsStatus");
  status.textContent = message;
  status.className = `mt-3 text-sm ${success ? "text-emerald-400" : "text-rose-400"}`;
}

function renderFamilyInvitations(invitations) {
  const list = $("familyInvitationList");
  list.replaceChildren();
  if (!invitations.length) {
    const empty = document.createElement("p");
    empty.className = "text-sm text-slate-400";
    empty.textContent = "You have no pending family invitations.";
    list.appendChild(empty);
    return;
  }
  for (const invitation of invitations) {
    const card = document.createElement("div");
    card.className = "flex flex-col gap-3 rounded-xl border border-slate-700 bg-slate-900/60 p-3 sm:flex-row sm:items-center sm:justify-between";
    card.innerHTML = `
      <p class="text-sm">Invitation to join <strong>${escapeHtml(invitation.family_name)}</strong></p>
      <div class="flex gap-2">
        <button type="button" class="btn bg-indigo-600 px-3 py-2 text-sm" data-family-invitation-action="accept" data-invitation-id="${invitation.id}">Accept</button>
        <button type="button" class="btn bg-slate-800 px-3 py-2 text-sm" data-family-invitation-action="decline" data-invitation-id="${invitation.id}">Decline</button>
      </div>`;
    list.appendChild(card);
  }
}

async function loadFamilyPage() {
  setFamilyStatus("Loading family finances…");
  $("familyWorkspace").classList.add("hidden");
  try {
    const [families, invitations] = await Promise.all([
      api("/api/families"),
      api("/api/family-invitations")
    ]);
    renderFamilyInvitations(invitations);
    const selector = $("familySelect");
    selector.replaceChildren();
    if (!families.length) {
      selectedFamilyId = null;
      selector.add(new Option("No family groups", ""));
      selector.disabled = true;
      $("familyWorkspace").classList.add("hidden");
      setFamilyStatus("Create a family group or accept an invitation to get started.");
      return;
    }
    selector.disabled = false;
    for (const family of families) {
      selector.add(new Option(`${family.name} (${family.member_count})`, String(family.id)));
    }
    const selected = families.find(item => item.id === Number(selectedFamilyId)) || families[0];
    selectedFamilyId = selected.id;
    selector.value = String(selected.id);
    const [detail, dashboard, familyInvitations, notifications] = await Promise.all([
      api(`/api/families/${selected.id}`),
      api(`/api/families/${selected.id}/dashboard`),
      selected.role === "owner"
        ? api(`/api/families/${selected.id}/invitations`)
        : Promise.resolve([]),
      api(`/api/families/${selected.id}/notifications`)
    ]);
    renderFamilyWorkspace(detail, dashboard, familyInvitations, notifications);
    $("familyWorkspace").classList.remove("hidden");
    setFamilyStatus(`${detail.name} · ${detail.members.length} ${detail.members.length === 1 ? "member" : "members"} · Your role: ${detail.role}.`);
  } catch (error) {
    setFamilyStatus(`Could not load family information: ${error.message}`, true);
  }
}

function renderFamilyWorkspace(detail, dashboard, invitations, notifications) {
  const family = detail;
  const current = family;
  const canManageResources = family.role === "owner" || family.members_can_manage_resources;
  $("familyIncome").textContent = goalMoney(dashboard.shared_summary.income, "USD");
  $("familyExpenses").textContent = goalMoney(dashboard.shared_summary.expenses, "USD");
  $("familyNet").textContent = goalMoney(dashboard.shared_summary.net, "USD");
  $("familyPrivacyNote").textContent =
    `Household totals are based on explicit sharing by ${dashboard.shared_summary.sharing_member_count} ${dashboard.shared_summary.sharing_member_count === 1 ? "member" : "members"}. Personal transaction details are never shown.`;
  $("familyShareSummary").checked = current.share_financial_summary;
  $("familyNotifications").checked = current.notifications_enabled;
  $("familyManagePermission").checked = current.members_can_manage_resources;
  $("familyManagePermissionWrap").classList.toggle("hidden", current.role !== "owner");
  $("familyManagePermissionWrap").classList.toggle("flex", current.role === "owner");
  $("familyInviteForm").classList.toggle("hidden", current.role !== "owner");
  $("familyInviteForm").classList.toggle("flex", current.role === "owner");
  $("familyBudgetForm").classList.toggle("hidden", !canManageResources);
  $("familyGoalForm").classList.toggle("hidden", !canManageResources);
  $("familyLeaveWrap").classList.toggle("hidden", current.role !== "owner" || family.members.length < 2);
  $("familyLeaveButton").dataset.familyOwner = String(current.role === "owner");
  $("familyLeaveButton").dataset.familyMemberCount = String(family.members.length);
  const successor = $("familySuccessor");
  successor.replaceChildren(new Option("Choose a member (required for an owner)", ""));
  for (const member of family.members) {
    if (member.user_id !== currentUser.id) {
      successor.add(new Option(member.full_name, String(member.user_id)));
    }
  }

  const members = $("familyMembers");
  members.replaceChildren();
  for (const member of family.members) {
    const row = document.createElement("div");
    row.className = "flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-800 bg-slate-900/60 p-3";
    const identity = document.createElement("div");
    identity.innerHTML = `<p class="font-medium">${escapeHtml(member.full_name)}${member.user_id === currentUser.id ? " (you)" : ""}</p><p class="text-xs text-slate-500">${escapeHtml(member.email)} · ${escapeHtml(member.role)}</p>`;
    row.appendChild(identity);
    if (family.role === "owner" && member.user_id !== currentUser.id) {
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "btn bg-rose-500/10 px-3 py-2 text-sm text-rose-200";
      remove.textContent = "Remove";
      remove.dataset.familyRemoveMember = String(member.user_id);
      remove.dataset.familyMemberName = member.full_name;
      row.appendChild(remove);
    }
    members.appendChild(row);
  }

  const inviteList = $("familyInvitations");
  inviteList.replaceChildren();
  if (invitations.length) {
    const title = document.createElement("h4");
    title.className = "text-sm font-medium";
    title.textContent = "Invitations";
    inviteList.appendChild(title);
    for (const invitation of invitations) {
      const row = document.createElement("div");
      row.className = "flex flex-wrap items-center justify-between gap-2 text-sm text-slate-400";
      row.innerHTML = `<span>${escapeHtml(invitation.email)} · ${escapeHtml(invitation.status)}</span>`;
      if (invitation.status === "pending") {
        const cancel = document.createElement("button");
        cancel.type = "button";
        cancel.className = "text-rose-300 hover:text-rose-200";
        cancel.textContent = "Cancel invitation";
        cancel.dataset.familyCancelInvitation = String(invitation.id);
        row.appendChild(cancel);
      }
      inviteList.appendChild(row);
    }
  }

  renderFamilyBudgets(dashboard.budgets, canManageResources);
  renderFamilyGoals(dashboard.goals);
  renderFamilyNotifications(notifications);
  $("familySettingsStatus").textContent = "";
}

function renderFamilyBudgets(budgets, canManageResources) {
  const list = $("familyBudgets");
  list.replaceChildren();
  if (!budgets.length) {
    const empty = document.createElement("p");
    empty.className = "text-sm text-slate-400";
    empty.textContent = "No shared budgets yet.";
    list.appendChild(empty);
    return;
  }
  for (const budget of budgets) {
    const progress = Number(budget.progress_percentage);
    const card = document.createElement("article");
    card.className = "rounded-xl border border-slate-700 bg-slate-900/60 p-4";
    card.innerHTML = `
      <div class="flex flex-wrap items-start justify-between gap-2">
        <div><h4 class="font-semibold">${escapeHtml(budget.category)}</h4><p class="text-xs text-slate-500">${budget.month}/${budget.year}</p></div>
        <p class="text-right text-sm">${goalMoney(budget.spent_amount, budget.currency)} spent <span class="text-slate-500">of</span> ${goalMoney(budget.amount, budget.currency)}</p>
      </div>
      <div class="mt-3 h-2 overflow-hidden rounded-full bg-slate-800" role="progressbar" aria-label="${escapeHtml(budget.category)} budget progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${progress}">
        <div class="h-full rounded-full bg-indigo-500" style="width:${Math.max(0, Math.min(100, progress))}%"></div>
      </div>
      <p class="mt-2 text-xs text-slate-400">${progress.toFixed(1)}% used · ${goalMoney(budget.remaining_amount, budget.currency)} remaining</p>
      <form class="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3" data-family-expense="${budget.id}" data-family-month="${budget.month}" data-family-year="${budget.year}" ${canManageResources ? "" : ""}>
        <input class="input sm:col-span-1" type="date" name="transaction_date" value="${budget.year}-${String(budget.month).padStart(2, "0")}-01" required aria-label="Shared expense date">
        <input class="input" type="number" name="amount" min="0.01" step="0.01" placeholder="Amount (${escapeHtml(budget.currency)})" required>
        <input class="input sm:col-span-3" type="text" name="description" maxlength="200" placeholder="Shared expense description (optional)">
        <button class="btn bg-slate-800 sm:col-span-3" type="submit">Add shared expense</button>
      </form>`;
    list.appendChild(card);
  }
}

function renderFamilyGoals(goals) {
  const list = $("familyGoals");
  list.replaceChildren();
  if (!goals.length) {
    const empty = document.createElement("p");
    empty.className = "text-sm text-slate-400";
    empty.textContent = "No shared savings goals yet.";
    list.appendChild(empty);
    return;
  }
  for (const goal of goals) {
    const progress = Number(goal.progress_percentage);
    const card = document.createElement("article");
    card.className = "rounded-xl border border-slate-700 bg-slate-900/60 p-4";
    card.innerHTML = `
      <div class="flex items-start justify-between gap-2"><div><h4 class="font-semibold">${escapeHtml(goal.name)}</h4><p class="mt-1 text-xs text-slate-500">${goal.deadline ? `Target ${escapeHtml(goal.deadline)}` : "No target date"}</p></div>
        <p class="text-right text-sm">${goalMoney(goal.saved_amount, goal.currency)} <span class="text-slate-500">of</span> ${goalMoney(goal.target_amount, goal.currency)}</p>
      </div>
      ${goal.description ? `<p class="mt-2 text-sm text-slate-400">${escapeHtml(goal.description)}</p>` : ""}
      <div class="mt-3 h-2 overflow-hidden rounded-full bg-slate-800" role="progressbar" aria-label="${escapeHtml(goal.name)} progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${progress}">
        <div class="h-full rounded-full bg-emerald-500" style="width:${Math.max(0, Math.min(100, progress))}%"></div>
      </div>
      <p class="mt-2 text-xs text-slate-400">${progress.toFixed(1)}% complete · ${goalMoney(goal.remaining_amount, goal.currency)} remaining</p>
      <form class="mt-3 flex flex-col gap-2 sm:flex-row" data-family-contribution="${goal.id}">
        <input class="input flex-1" type="number" name="amount" min="0.01" step="0.01" max="${goal.remaining_amount}" placeholder="Your voluntary contribution (${escapeHtml(goal.currency)})" required ${Number(goal.remaining_amount) <= 0 ? "disabled" : ""}>
        <button class="btn bg-slate-800" type="submit" ${Number(goal.remaining_amount) <= 0 ? "disabled" : ""}>Contribute</button>
      </form>`;
    list.appendChild(card);
  }
}

function renderFamilyNotifications(notifications) {
  const list = $("familyNotificationsList");
  list.replaceChildren();
  if (!notifications.length) {
    const empty = document.createElement("p");
    empty.className = "text-sm text-slate-400";
    empty.textContent = "No recent family activity.";
    list.appendChild(empty);
    return;
  }
  for (const notification of notifications) {
    const row = document.createElement("div");
    row.className = `flex items-start justify-between gap-2 rounded-lg p-2 text-sm ${notification.read ? "text-slate-500" : "bg-slate-900 text-slate-300"}`;
    row.innerHTML = `<span>${escapeHtml(notification.message)}</span>`;
    if (!notification.read) {
      const read = document.createElement("button");
      read.type = "button";
      read.className = "shrink-0 text-xs text-indigo-300 hover:text-indigo-200";
      read.textContent = "Mark read";
      read.dataset.familyNotificationRead = String(notification.id);
      row.appendChild(read);
    }
    list.appendChild(row);
  }
}

async function saveFamilySetting(name, value, input) {
  if (!selectedFamilyId) return;
  input.disabled = true;
  setFamilySettingsStatus("Saving setting…");
  try {
    await api(`/api/families/${selectedFamilyId}/settings`, {
      method: "PATCH",
      body: JSON.stringify({[name]: value})
    });
    await loadFamilyPage();
    setFamilySettingsStatus("Family setting saved.", true);
  } catch (error) {
    input.checked = !value;
    setFamilySettingsStatus(`Could not save setting: ${error.message}`);
  } finally {
    input.disabled = false;
  }
}

$("familySelect").addEventListener("change", async event => {
  selectedFamilyId = Number(event.target.value) || null;
  await loadFamilyPage();
});

$("familyCreateForm").addEventListener("submit", async event => {
  event.preventDefault();
  const button = $("familyCreateSubmit");
  button.disabled = true;
  setFamilyStatus("Creating your family group…");
  try {
    const family = await api("/api/families", {
      method: "POST",
      body: JSON.stringify({name: $("familyName").value})
    });
    selectedFamilyId = family.id;
    $("familyName").value = "";
    await loadFamilyPage();
  } catch (error) {
    setFamilyStatus(`Could not create family: ${error.message}`, true);
  } finally {
    button.disabled = false;
  }
});

$("familyInvitationList").addEventListener("click", async event => {
  const button = event.target.closest("[data-family-invitation-action]");
  if (!button) return;
  button.disabled = true;
  try {
    await api(`/api/family-invitations/${button.dataset.invitationId}/respond`, {
      method: "POST",
      body: JSON.stringify({action: button.dataset.familyInvitationAction})
    });
    await loadFamilyPage();
  } catch (error) {
    setFamilyStatus(`Could not respond to invitation: ${error.message}`, true);
    button.disabled = false;
  }
});

$("familyInviteForm").addEventListener("submit", async event => {
  event.preventDefault();
  const button = $("familyInviteSubmit");
  button.disabled = true;
  try {
    await api(`/api/families/${selectedFamilyId}/invitations`, {
      method: "POST",
      body: JSON.stringify({email: $("familyInviteEmail").value})
    });
    $("familyInviteEmail").value = "";
    setFamilyStatus("Invitation created. It will appear in WealthFlow when that person signs in with this email.");
    await loadFamilyPage();
  } catch (error) {
    setFamilyStatus(`Could not create invitation: ${error.message}`, true);
  } finally {
    button.disabled = false;
  }
});

$("familyBudgetMonth").value = String(new Date().getMonth() + 1);
$("familyBudgetYear").value = String(new Date().getFullYear());
$("familyBudgetCurrency").value = currentUser?.base_currency || "USD";
$("familyGoalCurrency").value = currentUser?.base_currency || "USD";

$("familyBudgetForm").addEventListener("submit", async event => {
  event.preventDefault();
  const button = $("familyBudgetSubmit");
  button.disabled = true;
  try {
    await api(`/api/families/${selectedFamilyId}/budgets`, {
      method: "POST",
      body: JSON.stringify({
        category: $("familyBudgetCategory").value,
        amount: Number($("familyBudgetAmount").value),
        currency: $("familyBudgetCurrency").value,
        month: Number($("familyBudgetMonth").value),
        year: Number($("familyBudgetYear").value)
      })
    });
    $("familyBudgetForm").reset();
    $("familyBudgetMonth").value = String(new Date().getMonth() + 1);
    $("familyBudgetYear").value = String(new Date().getFullYear());
    $("familyBudgetCurrency").value = currentUser.base_currency;
    setFamilyStatus("Shared budget created.");
    await loadFamilyPage();
  } catch (error) {
    setFamilyStatus(`Could not create shared budget: ${error.message}`, true);
  } finally {
    button.disabled = false;
  }
});

$("familyGoalForm").addEventListener("submit", async event => {
  event.preventDefault();
  const button = $("familyGoalSubmit");
  button.disabled = true;
  try {
    await api(`/api/families/${selectedFamilyId}/goals`, {
      method: "POST",
      body: JSON.stringify({
        name: $("familyGoalName").value,
        target_amount: Number($("familyGoalTarget").value),
        currency: $("familyGoalCurrency").value,
        deadline: $("familyGoalDeadline").value || null,
        description: $("familyGoalDescription").value
      })
    });
    event.target.reset();
    $("familyGoalCurrency").value = currentUser.base_currency;
    setFamilyStatus("Shared savings goal created.");
    await loadFamilyPage();
  } catch (error) {
    setFamilyStatus(`Could not create shared goal: ${error.message}`, true);
  } finally {
    button.disabled = false;
  }
});

$("familyBudgets").addEventListener("submit", async event => {
  const form = event.target.closest("[data-family-expense]");
  if (!form) return;
  event.preventDefault();
  const button = form.querySelector("button[type=submit]");
  button.disabled = true;
  try {
    await api(`/api/families/${selectedFamilyId}/budgets/${form.dataset.familyExpense}/expenses`, {
      method: "POST",
      body: JSON.stringify({
        transaction_date: form.elements.transaction_date.value,
        amount: Number(form.elements.amount.value),
        description: form.elements.description.value
      })
    });
    setFamilyStatus("Shared household expense recorded. Your personal ledger was not changed.");
    await loadFamilyPage();
  } catch (error) {
    setFamilyStatus(`Could not record shared expense: ${error.message}`, true);
    button.disabled = false;
  }
});

$("familyGoals").addEventListener("submit", async event => {
  const form = event.target.closest("[data-family-contribution]");
  if (!form) return;
  event.preventDefault();
  const button = form.querySelector("button[type=submit]");
  button.disabled = true;
  try {
    await api(`/api/families/${selectedFamilyId}/goals/${form.dataset.familyContribution}/contributions`, {
      method: "POST",
      body: JSON.stringify({amount: Number(form.elements.amount.value)})
    });
    setFamilyStatus("Your voluntary contribution was added to the shared goal.");
    await loadFamilyPage();
  } catch (error) {
    setFamilyStatus(`Could not contribute to shared goal: ${error.message}`, true);
    button.disabled = false;
  }
});

$("familyMembers").addEventListener("click", async event => {
  const button = event.target.closest("[data-family-remove-member]");
  if (!button) return;
  const name = button.dataset.familyMemberName;
  if (!window.confirm(`Remove ${name} from this family? Their personal finance data remains private and unchanged.`)) return;
  button.disabled = true;
  try {
    await api(`/api/families/${selectedFamilyId}/members/${button.dataset.familyRemoveMember}`, {method: "DELETE"});
    await loadFamilyPage();
  } catch (error) {
    setFamilyStatus(`Could not remove family member: ${error.message}`, true);
    button.disabled = false;
  }
});

$("familyInvitations").addEventListener("click", async event => {
  const button = event.target.closest("[data-family-cancel-invitation]");
  if (!button) return;
  button.disabled = true;
  try {
    await api(`/api/families/${selectedFamilyId}/invitations/${button.dataset.familyCancelInvitation}`, {method: "DELETE"});
    await loadFamilyPage();
  } catch (error) {
    setFamilyStatus(`Could not cancel invitation: ${error.message}`, true);
    button.disabled = false;
  }
});

$("familyShareSummary").addEventListener("change", event => {
  saveFamilySetting("share_financial_summary", event.target.checked, event.target);
});
$("familyNotifications").addEventListener("change", event => {
  saveFamilySetting("notifications_enabled", event.target.checked, event.target);
});
$("familyManagePermission").addEventListener("change", event => {
  saveFamilySetting("members_can_manage_resources", event.target.checked, event.target);
});

$("familyNotificationsList").addEventListener("click", async event => {
  const button = event.target.closest("[data-family-notification-read]");
  if (!button) return;
  button.disabled = true;
  try {
    await api(`/api/families/${selectedFamilyId}/notifications/${button.dataset.familyNotificationRead}/read`, {method: "POST"});
    await loadFamilyPage();
  } catch (error) {
    setFamilyStatus(`Could not update notification: ${error.message}`, true);
    button.disabled = false;
  }
});

$("familyLeaveButton").addEventListener("click", async event => {
  if (!selectedFamilyId) return;
  const successorId = $("familySuccessor").value;
  if (
    event.target.dataset.familyOwner === "true" &&
    Number(event.target.dataset.familyMemberCount) > 1 &&
    !successorId
  ) {
    setFamilyStatus("Choose a family member to become the new owner before leaving.", true);
    return;
  }
  const willDelete =
    event.target.dataset.familyOwner === "true" &&
    event.target.dataset.familyMemberCount === "1";
  const confirmation = willDelete
    ? "You are the only member. Leaving will permanently remove this family group and its shared records. Continue?"
    : "Leave this family? Your personal financial data remains unchanged.";
  if (!window.confirm(confirmation)) return;
  event.target.disabled = true;
  try {
    await api(`/api/families/${selectedFamilyId}/leave`, {
      method: "POST",
      body: JSON.stringify(successorId ? {transfer_to_user_id: Number(successorId)} : {})
    });
    selectedFamilyId = null;
    await loadFamilyPage();
  } catch (error) {
    setFamilyStatus(`Could not leave family: ${error.message}`, true);
  } finally {
    event.target.disabled = false;
  }
});

function renderMetrics(a) {
  $("totalIncome").textContent = money(a.total_income);
  $("totalExpenses").textContent = money(a.total_expenses);
  $("projected").textContent = money(a.projected_month_end_spend);
  $("burn").textContent =
    `${Number(a.budget_burn_percent).toFixed(1)}%`;
}

function renderBudgetAlerts(analytics) {
  const container = $("budgetAlerts");
  if (!container) return;
  container.replaceChildren();
  const thresholds = analytics.threshold_dates || [];
  if (!Number(analytics.budget_total) || !thresholds.length) {
    const message = document.createElement("p");
    message.className = "text-sm text-slate-400";
    message.textContent = "Add a current-month budget to see projected budget alerts.";
    container.appendChild(message);
    return;
  }

  for (const item of thresholds) {
    const alert = document.createElement("p");
    alert.className = "rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-sm text-amber-200";
    alert.textContent = `${item.threshold}% of your combined monthly budget is projected for ${formatTransactionDate(item.date)}.`;
    container.appendChild(alert);
  }
}


function renderSpendingInsights(a) {
  const container = $("spendingInsights");
  const insights = a.spending_insights || [];

  if (insights.length === 0) {
    container.textContent = "Add some expenses to see your insights.";
    return;
  }

  container.innerHTML = insights.map(insight => `
    <div class="rounded-xl border border-slate-700 bg-slate-900/60 p-4">
      <h3 class="font-medium text-indigo-300">
        ${escapeHtml(insight.title)}
      </h3>
      <p class="mt-1 text-sm text-slate-300">
        ${escapeHtml(insight.detail)}
      </p>
    </div>
  `).join("");
}

function renderReports(analytics) {
  const categoryBody = $("reportCategories");
  const timelineBody = $("reportTimeline");
  if (!categoryBody || !timelineBody) return;

  const categories = analytics.category_breakdown || [];
  const categoryTotal = categories.reduce((sum, item) => sum + Number(item.amount || 0), 0);
  categoryBody.replaceChildren();
  if (!categories.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.className = "p-3 text-slate-400";
    cell.colSpan = 3;
    cell.textContent = "No spending recorded this month.";
    row.appendChild(cell);
    categoryBody.appendChild(row);
  } else {
    for (const item of categories) {
      const row = document.createElement("tr");
      row.className = "border-b border-slate-900";
      const category = document.createElement("td");
      category.className = "p-3";
      category.textContent = item.category;
      const amount = document.createElement("td");
      amount.className = "p-3 text-right";
      amount.textContent = money(item.amount);
      const share = document.createElement("td");
      share.className = "p-3 text-right text-slate-400";
      share.textContent = categoryTotal ? `${(Number(item.amount) / categoryTotal * 100).toFixed(1)}%` : "0.0%";
      row.append(category, amount, share);
      categoryBody.appendChild(row);
    }
  }

  timelineBody.replaceChildren();
  const timeline = (analytics.timeline || []).slice(-90).reverse();
  if (!timeline.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.className = "p-3 text-slate-400";
    cell.colSpan = 4;
    cell.textContent = "No cashflow activity recorded yet.";
    row.appendChild(cell);
    timelineBody.appendChild(row);
    return;
  }

  for (const item of timeline) {
    const row = document.createElement("tr");
    row.className = "border-b border-slate-900";
    for (const [value, className] of [
      [formatTransactionDate(item.date), "p-3 text-slate-400"],
      [money(item.income), "p-3 text-right text-emerald-400"],
      [money(item.expense), "p-3 text-right text-rose-400"],
      [money(Number(item.income) - Number(item.expense)), "p-3 text-right"]
    ]) {
      const cell = document.createElement("td");
      cell.className = className;
      cell.textContent = value;
      row.appendChild(cell);
    }
    timelineBody.appendChild(row);
  }
}

function renderCharts(a) {
  if (!a) return;
  const timeline = a.timeline || [];
  const categories = a.category_breakdown || [];
  const lightTheme = document.documentElement.dataset.colorScheme === "light";
  const mutedText = lightTheme ? "#475569" : "#94a3b8";
  const legendText = lightTheme ? "#334155" : "#cbd5e1";

  if (!$("page-dashboard").classList.contains("hidden")) {
    if (charts.timeline) charts.timeline.destroy();
    charts.timeline = new ApexCharts($("timelineChart"), {
      chart: {type:"area", height:330, toolbar:{show:false}, animations:{enabled:true}},
      series: [
        {name:"Income", data:timeline.map(x=>[new Date(x.date).getTime(), x.income])},
        {name:"Expenses", data:timeline.map(x=>[new Date(x.date).getTime(), x.expense])}
      ],
      xaxis:{type:"datetime", labels:{style:{colors:mutedText}}},
      yaxis:{labels:{formatter:v=>money(v), style:{colors:mutedText}}},
      stroke:{curve:"smooth", width:2},
      fill:{type:"gradient", gradient:{opacityFrom:.35, opacityTo:.03}},
      legend:{labels:{colors:legendText}},
      grid:{borderColor:lightTheme ? "#cbd5e1" : "#1e293b"},
      theme:{mode:lightTheme ? "light" : "dark"},
      tooltip:{shared:true, x:{format:"dd MMM"}}
    });
    charts.timeline.render();

    if (charts.donut) charts.donut.destroy();
    charts.donut = new ApexCharts($("donutChart"), {
      chart:{type:"donut", height:330, events:{
        dataPointSelection:(event, chartContext, config)=>{
          const c = categories[config.dataPointIndex]?.category;
          if (c) {
            $("search").value = c;
            location.hash = "transactions";
            loadTransactions().then(renderLedger);
          }
        }
      }},
      labels:categories.map(x=>x.category),
      series:categories.map(x=>Number(x.amount)),
      legend:{position:"bottom", labels:{colors:legendText}},
      theme:{mode:lightTheme ? "light" : "dark"},
      dataLabels:{enabled:false},
      tooltip:{y:{formatter:v=>money(v)}}
    });
    charts.donut.render();
  }

  if (!$("page-analytics-reports").classList.contains("hidden")) {
    if (charts.reportTrend) charts.reportTrend.destroy();
    charts.reportTrend = new ApexCharts($("reportTrendChart"), {
      chart:{type:"area", height:320, toolbar:{show:false}, animations:{enabled:true}},
      series:[
        {name:"Income", data:timeline.map(item=>[new Date(item.date).getTime(), item.income])},
        {name:"Expenses", data:timeline.map(item=>[new Date(item.date).getTime(), item.expense])}
      ],
      xaxis:{type:"datetime", labels:{style:{colors:mutedText}}},
      yaxis:{labels:{formatter:value=>money(value), style:{colors:mutedText}}},
      stroke:{curve:"smooth", width:2},
      fill:{type:"gradient", gradient:{opacityFrom:.35, opacityTo:.03}},
      legend:{labels:{colors:legendText}},
      grid:{borderColor:lightTheme ? "#cbd5e1" : "#1e293b"},
      theme:{mode:lightTheme ? "light" : "dark"},
      tooltip:{shared:true, x:{format:"dd MMM"}}
    });
    charts.reportTrend.render();
  }
}

async function loadTransactions() {
  const p = new URLSearchParams();
  if ($("search").value) p.set("q", $("search").value);
  if ($("kindFilter").value) p.set("kind", $("kindFilter").value);
  if ($("minAmount").value) p.set("min_amount", $("minAmount").value);
  if ($("maxAmount").value) p.set("max_amount", $("maxAmount").value);
  return api(`/api/transactions?${p}`);
}

function renderLedger(txs) {
  transactionsById.clear();
  txs.forEach(t => transactionsById.set(t.id, t));
  $("ledger").innerHTML = txs.map(t => `
    <tr class="border-b border-slate-900 hover:bg-slate-800/40 transition">
      <td class="p-3 text-slate-400">${escapeHtml(formatTransactionDate(t.transaction_date))}</td>
      <td class="p-3"><div class="font-medium">${escapeHtml(t.merchant || "—")}</div><div class="text-xs text-slate-500">${escapeHtml(t.note || "")}</div></td>
      <td class="p-3"><span class="rounded-full bg-slate-800 px-2 py-1 text-xs">${escapeHtml(t.category)}</span></td>
      <td class="p-3 text-right ${t.kind === "income" ? "text-emerald-400" : "text-rose-400"}">${t.kind === "income" ? "+" : "-"}${money(t.amount_base)}</td>
      <td class="p-3 text-right whitespace-nowrap">
        <button type="button" onclick="editTx(${t.id})" aria-label="Edit transaction" title="Edit transaction" class="text-slate-500 hover:text-indigo-400 mr-2"><i data-lucide="pencil" class="w-4"></i></button>
        <button type="button" onclick="removeTx(${t.id})" aria-label="Delete transaction" title="Delete transaction" class="text-slate-500 hover:text-rose-400"><i data-lucide="trash-2" class="w-4"></i></button>
      </td>
    </tr>
  `).join("");
  lucide.createIcons();
}

function clearImportState() {
  selectedImportFile = null;
  transactionImportPreview = null;
  transactionImportRequestId = null;
  transactionImportConfirmationToken = null;
  transactionImportMapping = {};
  transactionImportMappingApplied = false;
  $("importFile").value = "";
  $("importSelectedFile").classList.add("hidden");
  $("importSelectedFile").classList.remove("flex");
  $("importPreview").classList.add("hidden");
  $("importResult").classList.add("hidden");
  $("importMappingPanel").classList.add("hidden");
  $("importMessage").textContent = "";
  $("previewImport").disabled = true;
}

function setImportMessage(message, kind = "error") {
  const element = $("importMessage");
  element.textContent = message;
  element.className = `text-sm ${kind === "success" ? "text-emerald-400" : kind === "info" ? "text-slate-400" : "text-rose-400"}`;
}

function showSelectedImportFile(file) {
  clearImportState();
  selectedImportFile = file;
  $("importFileName").textContent = file.name;
  $("importFileSize").textContent = `${(file.size / 1024).toFixed(file.size < 1024 * 1024 ? 1 : 0)} KB`;
  $("importSelectedFile").classList.remove("hidden");
  $("importSelectedFile").classList.add("flex");
  const extension = file.name.split(".").pop().toLowerCase();
  if (!new Set(["xlsx", "csv"]).has(extension)) {
    setImportMessage("Choose an .xlsx or .csv file.");
  } else if (file.size === 0) {
    setImportMessage("The selected file is empty.");
  } else if (file.size > 5 * 1024 * 1024) {
    setImportMessage("Files must be 5 MB or smaller.");
  } else {
    $("previewImport").disabled = false;
    setImportMessage("Ready to preview. No transactions are saved yet.", "info");
  }
}

function importCellValue(row, field, label) {
  return row.values[field] ?? row.values[label] ?? "";
}

function renderImportMapping(preview) {
  const panel = $("importMappingPanel");
  const mappingFields = $("importMappingFields");
  mappingFields.replaceChildren();
  if (!preview.unmapped_fields.length || (transactionImportMappingApplied && !preview.unmapped_required.length)) {
    panel.classList.add("hidden");
    return;
  }

  for (const item of transactionImportFields) {
    const wrapper = document.createElement("label");
    wrapper.className = "block text-sm text-slate-300";
    wrapper.textContent = `${item.label}${item.required ? " *" : " (optional)"}`;
    const select = document.createElement("select");
    select.className = "input mt-1";
    select.dataset.mappingField = item.field;
    const none = document.createElement("option");
    none.value = "";
    none.textContent = item.required ? "Choose a column" : "Not mapped";
    select.appendChild(none);
    for (const header of preview.headers) {
      const option = document.createElement("option");
      option.value = header;
      option.textContent = header || "(blank header)";
      select.appendChild(option);
    }
    select.value = transactionImportMapping[item.field] || preview.mapped_columns[item.field] || "";
    wrapper.appendChild(select);
    mappingFields.appendChild(wrapper);
  }
  panel.classList.remove("hidden");
}

function updateImportConfirmation() {
  if (!transactionImportPreview) return;
  const summary = transactionImportPreview.summary;
  const importValidOnly = $("importValidOnly").checked;
  const includeDuplicates = $("importIncludeDuplicates").checked;
  const hasInvalidRows = summary.invalid_rows > 0;
  const expectedDuplicates = includeDuplicates ? 0 : summary.possible_duplicates;
  const eligible = Math.max(0, summary.valid_rows - expectedDuplicates);
  const remainingSkipped = summary.invalid_rows + expectedDuplicates;
  $("importConfirmationSummary").textContent = `${eligible} will be imported; ${remainingSkipped} will be skipped.`;
  $("confirmImport").disabled = eligible === 0 || (hasInvalidRows && !importValidOnly);
}

function renderImportPreview(preview) {
  transactionImportPreview = preview;
  transactionImportRequestId = preview.request_id;
  transactionImportConfirmationToken = preview.confirmation_token;
  $("importTotalRows").textContent = preview.summary.total_rows;
  $("importValidRows").textContent = preview.summary.valid_rows;
  $("importInvalidRows").textContent = preview.summary.invalid_rows;
  $("importDuplicateRows").textContent = preview.summary.possible_duplicates;
  $("importValidOnlyWrap").classList.toggle("hidden", preview.summary.invalid_rows === 0);
  $("importValidOnlyWrap").classList.toggle("flex", preview.summary.invalid_rows > 0);
  $("importDuplicateWrap").classList.toggle("hidden", preview.summary.possible_duplicates === 0);
  $("importDuplicateWrap").classList.toggle("flex", preview.summary.possible_duplicates > 0);
  $("importValidOnly").checked = false;
  $("importIncludeDuplicates").checked = false;

  $("importPreviewRows").innerHTML = preview.rows.map(row => {
    const duplicate = row.possible_duplicate;
    const valid = row.valid;
    const statusClass = duplicate ? "text-amber-300" : valid ? "text-emerald-300" : "text-rose-300";
    const statusText = duplicate
      ? `Possible duplicate: ${row.duplicate_reason}`
      : valid ? "Valid" : row.errors.join("; ");
    const amount = importCellValue(row, "amount", "Amount");
    const currency = importCellValue(row, "currency", "Currency") || "USD";
    return `<tr class="${valid ? "" : "bg-rose-950/10"}">
      <td class="p-3 text-slate-400">${row.row_number}</td>
      <td class="p-3">${escapeHtml(importCellValue(row, "transaction_date", "Transaction Date"))}</td>
      <td class="p-3 capitalize">${escapeHtml(importCellValue(row, "kind", "Type"))}</td>
      <td class="p-3 whitespace-nowrap">${escapeHtml(amount)} ${escapeHtml(currency)}</td>
      <td class="p-3">${escapeHtml(importCellValue(row, "category", "Category"))}</td>
      <td class="p-3">${escapeHtml(importCellValue(row, "merchant", "Merchant"))}</td>
      <td class="p-3 ${statusClass} whitespace-normal">${escapeHtml(statusText)}</td>
    </tr>`;
  }).join("") || '<tr><td colspan="7" class="p-6 text-center text-slate-400">No transaction rows found under the headers.</td></tr>';

  renderImportMapping(preview);
  $("importPreview").classList.remove("hidden");
  updateImportConfirmation();
  $("importPreview").scrollIntoView({behavior: "smooth", block: "nearest"});
}

function createImportFormData() {
  const form = new FormData();
  form.append("upload", selectedImportFile);
  form.append("mapping_json", JSON.stringify(transactionImportMapping));
  return form;
}

async function previewImport(mapping = transactionImportMapping) {
  if (!selectedImportFile) return;
  transactionImportMapping = {...mapping};
  transactionImportPreview = null;
  transactionImportRequestId = null;
  transactionImportConfirmationToken = null;
  const button = $("previewImport");
  button.disabled = true;
  $("remapImport").disabled = true;
  $("confirmImport").disabled = true;
  $("importPreview").classList.add("hidden");
  $("importProgress").classList.remove("hidden");
  $("importProgress").classList.add("inline-flex");
  setImportMessage("Uploading for validation. Nothing will be saved yet.", "info");
  try {
    const response = await api("/api/transactions/import/preview", {
      method: "POST",
      body: createImportFormData()
    });
    renderImportPreview(response);
    const requiredMappingMissing = response.unmapped_required.length > 0;
    const hasUnmappedFields = response.unmapped_fields.length > 0;
    setImportMessage(
      requiredMappingMissing
        ? "Map the required columns and preview again."
        : hasUnmappedFields
          ? "Optional columns can be mapped, or left unused, before confirmation."
          : "Review every row before confirming the import.",
      "info"
    );
  } catch (error) {
    $("importPreview").classList.add("hidden");
    setImportMessage(error.message);
  } finally {
    $("importProgress").classList.add("hidden");
    $("importProgress").classList.remove("inline-flex");
    $("remapImport").disabled = false;
    button.disabled = !selectedImportFile || selectedImportFile.size === 0 || selectedImportFile.size > 5 * 1024 * 1024;
  }
}

$("importFile").addEventListener("change", event => {
  const file = event.target.files?.[0];
  if (file) showSelectedImportFile(file);
});
$("removeImportFile").addEventListener("click", clearImportState);
$("importDropZone").addEventListener("dragover", event => {
  event.preventDefault();
  $("importDropZone").classList.add("border-indigo-400", "bg-indigo-500/5");
});
$("importDropZone").addEventListener("dragleave", () => {
  $("importDropZone").classList.remove("border-indigo-400", "bg-indigo-500/5");
});
$("importDropZone").addEventListener("drop", event => {
  event.preventDefault();
  $("importDropZone").classList.remove("border-indigo-400", "bg-indigo-500/5");
  const file = event.dataTransfer.files?.[0];
  if (file) showSelectedImportFile(file);
});
$("previewImport").addEventListener("click", () => previewImport());
$("remapImport").addEventListener("click", () => {
  const mapping = {};
  $("importMappingFields").querySelectorAll("[data-mapping-field]").forEach(select => {
    if (select.value) mapping[select.dataset.mappingField] = select.value;
  });
  transactionImportMappingApplied = true;
  previewImport(mapping);
});
$("importValidOnly").addEventListener("change", updateImportConfirmation);
$("importIncludeDuplicates").addEventListener("change", updateImportConfirmation);
$("cancelImport").addEventListener("click", clearImportState);
$("confirmImport").addEventListener("click", async () => {
  if (!selectedImportFile || !transactionImportRequestId || !transactionImportPreview) return;
  const button = $("confirmImport");
  button.disabled = true;
  button.textContent = "Importing...";
  try {
    const form = createImportFormData();
    form.append("request_id", transactionImportRequestId);
    form.append("confirmation_token", transactionImportConfirmationToken);
    form.append("import_valid_only", String($("importValidOnly").checked));
    form.append("include_duplicates", String($("importIncludeDuplicates").checked));
    const result = await api("/api/transactions/import/confirm", {method: "POST", body: form});
    $("importPreview").classList.add("hidden");
    const skipped = result.invalid_skipped + result.duplicate_skipped;
    const reportLink = skipped
      ? `<a class="ml-2 font-medium text-indigo-300 underline" href="/api/transactions/import/${encodeURIComponent(result.request_id)}/errors">Download skipped-row report</a>`
      : "";
    $("importResult").innerHTML = `<p class="font-semibold text-emerald-300">Import complete</p><p class="mt-2 text-sm text-slate-300">${result.imported} imported · ${result.invalid_skipped} invalid skipped · ${result.duplicate_skipped} possible duplicates skipped · ${result.duplicates_included} duplicates included.${reportLink}</p>`;
    $("importResult").classList.remove("hidden");
    setImportMessage("Transactions were saved to your account.", "success");
    clearImportAfterSuccess();
    if (result.imported > 0) {
      try { await refresh(); }
      catch (error) { setImportMessage(`Imported, but dashboard refresh failed: ${error.message}`, "error"); }
    }
  } catch (error) {
    setImportMessage(error.message);
  } finally {
    button.textContent = "Import transactions";
    button.disabled = false;
  }
});

function clearImportAfterSuccess() {
  selectedImportFile = null;
  transactionImportPreview = null;
  transactionImportRequestId = null;
  transactionImportConfirmationToken = null;
  transactionImportMapping = {};
  transactionImportMappingApplied = false;
  $("importFile").value = "";
  $("importSelectedFile").classList.add("hidden");
  $("importSelectedFile").classList.remove("flex");
}

window.removeTx = async (id) => {
  await api(`/api/transactions/${id}`, {method:"DELETE"});
  if (editingTransactionId === id) resetTransactionForm();
  await refresh();
};

window.editTx = (id) => {
  const transaction = transactionsById.get(id);
  if (!transaction) return;

  editingTransactionId = id;
  $("txDate").value = transaction.transaction_date;
  $("txKind").value = transaction.kind;
  $("txAmount").value = transaction.amount;
  $("txCurrency").value = transaction.currency;
  $("txCategory").value = transaction.category;
  $("txMerchant").value = transaction.merchant || "";
  $("txTags").value = (transaction.tags || []).join(", ");
  $("txNote").value = transaction.note || "";
  $("txFormTitle").textContent = "Edit transaction";
  $("txSubmit").textContent = "Save changes";
  $("txCancel").classList.remove("hidden");
  $("txForm").scrollIntoView({behavior: "smooth", block: "center"});
};

function resetTransactionForm() {
  editingTransactionId = null;
  $("txForm").reset();
  $("txDate").value = today;
  $("txFormTitle").textContent = "Add transaction";
  $("txSubmit").textContent = "Add transaction";
  $("txCancel").classList.add("hidden");
}

$("txCancel").onclick = resetTransactionForm;


$("txForm").onsubmit = async e => {
  e.preventDefault();

  const button = $("txSubmit");
  if (button) button.disabled = true;

  try {
    const isEditing = editingTransactionId !== null;
    await api(isEditing ? `/api/transactions/${editingTransactionId}` : "/api/transactions", {
      method: isEditing ? "PUT" : "POST",
      body: JSON.stringify({
        transaction_date: $("txDate").value,
        kind: $("txKind").value,
        amount: Number($("txAmount").value),
        currency: $("txCurrency").value,
        category: $("txCategory").value,
        merchant: $("txMerchant").value,
        note: $("txNote").value,
        tags: $("txTags").value
          .split(",")
          .map(x => x.trim())
          .filter(Boolean)
      })
    });
    
    resetTransactionForm();

    // Reload the ledger independently so analytics errors
    // cannot prevent the transaction list from updating.
    const txs = await loadTransactions();
    renderLedger(txs);

    // Update dashboard metrics and charts separately.
    try {
      const analytics = await api("/api/analytics");
      latestAnalytics = analytics;
      renderMetrics(analytics);
      renderBudgetAlerts(analytics);
      renderSpendingInsights(analytics);
      renderReports(analytics);
      renderCharts(analytics);
      lucide.createIcons();
    } catch (error) {
      console.error("Analytics refresh failed:", error);
    }
  } catch (error) {
    alert("Could not save or refresh transaction: " + error.message);
  } finally {
    if (button) button.disabled = false;
  }
};
const budgetMonth = $("budgetMonth");
const budgetYear = $("budgetYear");

if (budgetMonth) {
  budgetMonth.value = String(new Date().getMonth() + 1);
}

if (budgetYear) {
  budgetYear.value = String(new Date().getFullYear());
}

async function loadBudgets() {
  const budgets = await api("/api/budgets");
  const list = $("budgetsList");

  if (!list) return;

  list.replaceChildren();

  if (!budgets.length) {
    const message = document.createElement("p");
    message.className = "text-sm text-slate-400";
    message.textContent = "No budgets yet. Add your first budget above.";
    list.appendChild(message);
    return;
  }

  for (const budget of budgets) {
    const card = document.createElement("div");
    card.className = "rounded-xl border border-slate-700 bg-slate-900/60 p-4";

    const category = document.createElement("h3");
    category.className = "font-semibold text-white";
    category.textContent = budget.category;

    const period = document.createElement("p");
    period.className = "text-sm text-slate-400 mt-1";
    period.textContent = `${budget.month}/${budget.year}`;

    const amount = document.createElement("p");
    amount.className = "text-lg font-semibold text-indigo-300 mt-3";
    amount.textContent = `${budget.amount} ${budget.currency || ""}`.trim();

    card.append(category, period, amount);
    list.appendChild(card);
  }
}


function goalMoney(amount, currency) {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency,
    maximumFractionDigits: 2
  }).format(Number(amount || 0));
}

function setSavingsGoalsMessage(message, success = false) {
  const element = $("savingsGoalsMessage");
  element.textContent = message;
  element.className = `text-sm mb-3 ${success ? "text-emerald-400" : "text-rose-400"}`;
}

async function loadSavingsGoals() {
  const list = $("savingsGoalsList");
  try {
    const goals = await api("/api/savings-goals");
    savingsGoalsById.clear();
    goals.forEach(goal => savingsGoalsById.set(goal.id, goal));

    if (!goals.length) {
      list.innerHTML = '<div class="col-span-full rounded-xl border border-dashed border-slate-700 p-6 text-center"><p class="font-medium">No saving goals yet</p><p class="mt-1 text-sm text-slate-400">Create a goal to start tracking progress.</p></div>';
      return goals;
    }

    list.innerHTML = goals.map(goal => {
      const progress = Math.max(0, Math.min(100, Number(goal.progress_percentage)));
      const statusClass = {
        active: "bg-indigo-400/10 text-indigo-300",
        overdue: "bg-amber-400/10 text-amber-300",
        completed: "bg-emerald-400/10 text-emerald-300"
      }[goal.status] || "bg-slate-700 text-slate-300";
      const dateLabel = goal.deadline
        ? `Target ${formatTransactionDate(goal.deadline)}`
        : "No target date";
      const description = goal.description
        ? `<p class="mt-3 text-sm text-slate-400 whitespace-pre-wrap">${escapeHtml(goal.description)}</p>`
        : "";

      return `
        <article class="rounded-xl border border-slate-700 bg-slate-900/60 p-4 sm:p-5" data-goal-card="${goal.id}">
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <h3 class="font-semibold text-white break-words">${escapeHtml(goal.name)}</h3>
              <p class="mt-1 text-xs text-slate-400">${escapeHtml(dateLabel)}</p>
            </div>
            <span class="shrink-0 rounded-full px-2.5 py-1 text-xs capitalize ${statusClass}">${escapeHtml(goal.status)}</span>
          </div>
          ${description}
          <div class="mt-4 flex items-end justify-between gap-2 text-sm">
            <div><p class="text-xs text-slate-500">Saved</p><p class="font-semibold">${goalMoney(goal.saved_amount, goal.currency)}</p></div>
            <div class="text-right"><p class="text-xs text-slate-500">Target</p><p class="font-semibold">${goalMoney(goal.target_amount, goal.currency)}</p></div>
          </div>
          <div class="mt-3 h-2 overflow-hidden rounded-full bg-slate-800" role="progressbar" aria-label="${escapeHtml(goal.name)} progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${progress}">
            <div class="h-full rounded-full bg-indigo-500 transition-[width] duration-500" style="width:${progress}%"></div>
          </div>
          <div class="mt-2 flex justify-between gap-2 text-xs text-slate-400">
            <span>${progress.toFixed(1)}% complete</span>
            <span>${goalMoney(goal.remaining_amount, goal.currency)} remaining</span>
          </div>
          <div class="mt-4 flex flex-wrap gap-2">
            <button type="button" class="btn bg-indigo-600 px-3 py-2 text-sm" data-goal-action="contribute" data-goal-id="${goal.id}" ${Number(goal.remaining_amount) <= 0 ? "disabled" : ""}>Add Money</button>
            <button type="button" class="btn bg-slate-800 px-3 py-2 text-sm" data-goal-action="withdraw" data-goal-id="${goal.id}" ${Number(goal.saved_amount) <= 0 ? "disabled" : ""}>Withdraw</button>
            <button type="button" class="btn bg-slate-800 px-3 py-2 text-sm" data-goal-action="edit" data-goal-id="${goal.id}" aria-label="Edit ${escapeHtml(goal.name)}" title="Edit goal"><i data-lucide="pencil" class="w-4"></i></button>
            <button type="button" class="btn bg-slate-800 px-3 py-2 text-sm text-rose-300" data-goal-action="delete" data-goal-id="${goal.id}" aria-label="Delete ${escapeHtml(goal.name)}" title="Delete goal"><i data-lucide="trash-2" class="w-4"></i></button>
          </div>
        </article>`;
    }).join("");
    lucide.createIcons();
    return goals;
  } catch (error) {
    list.innerHTML = '<p class="col-span-full text-sm text-rose-400">Could not load saving goals. Try refreshing the dashboard.</p>';
    console.error("Saving goals refresh failed:", error);
    return null;
  }
}

function openGoalEditor(mode, goal = null) {
  goalDialogMode = mode;
  activeGoalId = goal?.id ?? null;
  $("goalDialogTitle").textContent = mode === "edit" ? "Edit saving goal" : "Create saving goal";
  $("goalFormSubmit").textContent = mode === "edit" ? "Save changes" : "Create goal";
  $("goalForm").classList.remove("hidden");
  $("goalMoneyForm").classList.add("hidden");
  $("goalSavedWrap").classList.toggle("hidden", mode === "edit");
  $("goalName").value = goal?.name || "";
  $("goalTargetAmount").value = goal?.target_amount ?? "";
  $("goalSavedAmount").value = goal?.saved_amount ?? "0";
  $("goalCurrency").value = goal?.currency || currentUser?.base_currency || "USD";
  $("goalCurrency").disabled = mode === "edit" && Number(goal?.saved_amount || 0) > 0;
  $("goalCurrencyHelp").classList.toggle("hidden", !$("goalCurrency").disabled);
  $("goalDeadline").value = goal?.deadline || "";
  $("goalDescription").value = goal?.description || "";
  $("goalDialogMessage").textContent = "";
  $("goalDialog").showModal();
}

function openGoalMoneyDialog(mode, goal) {
  goalDialogMode = mode;
  activeGoalId = goal.id;
  const action = mode === "withdraw" ? "Withdraw from" : "Add money to";
  $("goalDialogTitle").textContent = `${action} ${goal.name}`;
  $("goalMoneyDescription").textContent = `${goalMoney(goal.saved_amount, goal.currency)} saved of ${goalMoney(goal.target_amount, goal.currency)}.`;
  $("goalMoneySubmit").textContent = mode === "withdraw" ? "Withdraw" : "Add money";
  $("goalMoneySubmit").className = `btn ${mode === "withdraw" ? "bg-amber-600 hover:bg-amber-500" : "bg-indigo-600 hover:bg-indigo-500"}`;
  $("goalMoneyAmount").value = "";
  $("goalMoneyAmount").max = String(mode === "withdraw" ? goal.saved_amount : goal.remaining_amount);
  $("goalDialogMessage").textContent = "";
  $("goalForm").classList.add("hidden");
  $("goalMoneyForm").classList.remove("hidden");
  $("goalDialog").showModal();
  $("goalMoneyAmount").focus();
}

$("createGoalButton").onclick = () => openGoalEditor("create");
$("goalDialogClose").onclick = () => $("goalDialog").close();
$("goalFormCancel").onclick = () => $("goalDialog").close();
$("goalMoneyCancel").onclick = () => $("goalDialog").close();

$("goalForm").onsubmit = async event => {
  event.preventDefault();
  const editing = goalDialogMode === "edit";
  const payload = {
    name: $("goalName").value.trim(),
    target_amount: Number($("goalTargetAmount").value),
    currency: $("goalCurrency").value,
    deadline: $("goalDeadline").value || null,
    description: $("goalDescription").value.trim()
  };
  if (!editing) payload.saved_amount = Number($("goalSavedAmount").value || 0);

  try {
    await api(editing ? `/api/savings-goals/${activeGoalId}` : "/api/savings-goals", {
      method: editing ? "PUT" : "POST",
      body: JSON.stringify(payload)
    });
    $("goalDialog").close();
    setSavingsGoalsMessage(editing ? "Saving goal updated." : "Saving goal created.", true);
    const goals = await loadSavingsGoals();
    await loadFinancialCalendar(goals);
  } catch (error) {
    $("goalDialogMessage").textContent = error.message;
    $("goalDialogMessage").className = "text-sm mb-3 text-rose-400";
  }
};

$("goalMoneyForm").onsubmit = async event => {
  event.preventDefault();
  try {
    await api(`/api/savings-goals/${activeGoalId}/${goalDialogMode}`, {
      method: "POST",
      body: JSON.stringify({amount: Number($("goalMoneyAmount").value)})
    });
    $("goalDialog").close();
    setSavingsGoalsMessage(goalDialogMode === "withdraw" ? "Withdrawal recorded." : "Money added to goal.", true);
    const goals = await loadSavingsGoals();
    await loadFinancialCalendar(goals);
  } catch (error) {
    $("goalDialogMessage").textContent = error.message;
    $("goalDialogMessage").className = "text-sm mb-3 text-rose-400";
  }
};

$("savingsGoalsList").addEventListener("click", async event => {
  const button = event.target.closest("[data-goal-action]");
  if (!button) return;
  const goal = savingsGoalsById.get(Number(button.dataset.goalId));
  if (!goal) return;

  const action = button.dataset.goalAction;
  if (action === "edit") {
    openGoalEditor("edit", goal);
  } else if (action === "contribute" || action === "withdraw") {
    openGoalMoneyDialog(action, goal);
  } else if (action === "delete" && window.confirm(`Delete the saving goal "${goal.name}"?`)) {
    try {
      await api(`/api/savings-goals/${goal.id}`, {method: "DELETE"});
      setSavingsGoalsMessage("Saving goal deleted.", true);
      const goals = await loadSavingsGoals();
      await loadFinancialCalendar(goals);
    } catch (error) {
      setSavingsGoalsMessage("Could not delete saving goal: " + error.message);
    }
  }
});

$("budgetForm").onsubmit = async (e) => {
  e.preventDefault();

  const button = e.target.querySelector('button[type="submit"]');
  const message = $("budgetMessage");

  if (button) button.disabled = true;
  message.textContent = "Saving budget...";
  message.className = "text-sm mb-3 text-slate-400";

  try {
    await api("/api/budgets", {
      method: "POST",
      body: JSON.stringify({
        category: $("budgetCategory").value.trim(),
        amount: Number($("budgetAmount").value),
        month: Number($("budgetMonth").value),
        year: Number($("budgetYear").value)
      })
    });

    message.textContent = "Budget saved successfully!";
    message.className = "text-sm mb-3 text-emerald-400";

    $("budgetCategory").value = "";
    $("budgetAmount").value = "";

    await refresh();
  } catch (error) {
    message.textContent = "Could not save budget: " + error.message;
    message.className = "text-sm mb-3 text-red-400";
  } finally {
    if (button) button.disabled = false;
  }
};


$("recForm").onsubmit = async e => {
  e.preventDefault();
  const message = $("recurringMessage");
  message.textContent = "Scheduling recurring transaction…";
  message.className = "mt-3 text-sm text-slate-400";
  try {
    await api("/api/recurring", {
      method:"POST",
      body:JSON.stringify({
        name:$("recName").value,
        kind:"expense",
        amount:Number($("recAmount").value),
        currency:currentUser.base_currency,
        category:$("recCategory").value,
        frequency:$("recFrequency").value,
        next_due:$("recDue").value,
        active:true
      })
    });
    e.target.reset();
    $("recDue").value = today;
    message.textContent = "Recurring transaction scheduled. Its future dates now appear in your financial calendar.";
    message.className = "mt-3 text-sm text-emerald-400";
    const goals = await loadSavingsGoals();
    await loadFinancialCalendar(goals);
  } catch (error) {
    message.textContent = `Could not schedule recurring transaction: ${error.message}`;
    message.className = "mt-3 text-sm text-rose-400";
  }
};

["search","kindFilter","minAmount","maxAmount"].forEach(id => {
  $(id).addEventListener("input", async () => renderLedger(await loadTransactions()));
  $(id).addEventListener("change", async () => renderLedger(await loadTransactions()));
});

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, c => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"
  }[c]));
}

setMode($("auth").dataset.authMode === "signup" ? "signup" : "login");
setupSidebar();

(async () => {
  try {
    currentUser = await api("/api/auth/me");
    await startApp();
  } catch {
    $("auth").classList.remove("hidden");
    $("app").classList.add("hidden");
    lucide.createIcons();
  }
})();
