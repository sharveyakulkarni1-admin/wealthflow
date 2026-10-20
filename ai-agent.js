const byId = id => document.getElementById(id);
const form = byId("aiChatForm");
const chat = byId("aiChat");
const promptInput = byId("aiPrompt");
const submitButton = byId("aiSubmit");
const status = byId("aiStatus");
const suggestions = byId("aiSuggestions");

let conversationId = null;
let pending = false;
let authenticatedUserId = null;

const suggestedQuestions = [
  "What did I spend most on this month?",
  "How close am I to my budget?",
  "Am I on track with my saving goals?",
  "What changed compared with last month?"
];

function setStatus(message, isError = false) {
  status.textContent = message;
  status.className = `mt-3 text-sm ${isError ? "text-rose-400" : "text-slate-400"}`;
}

function addMessage(role, content) {
  const bubble = document.createElement("div");
  bubble.className = `rounded-2xl border p-3 text-sm ${role === "user"
    ? "ml-auto max-w-[85%] border-indigo-500/30 bg-indigo-500/10 text-indigo-50"
    : "mr-auto max-w-[90%] border-slate-700 bg-slate-900/80 text-slate-200"}`;

  const label = document.createElement("div");
  label.className = "mb-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-400";
  label.textContent = role === "user" ? "You" : "WealthFlow AI";
  const text = document.createElement("div");
  text.className = "whitespace-pre-wrap break-words";
  text.textContent = content;
  bubble.append(label, text);
  chat.appendChild(bubble);
  chat.scrollTop = chat.scrollHeight;
}

function renderSuggestions() {
  for (const question of suggestedQuestions) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "rounded-full border border-slate-700 bg-slate-900/70 px-3 py-1.5 text-xs text-slate-300 transition hover:border-indigo-500/50 hover:text-indigo-100";
    button.textContent = question;
    button.addEventListener("click", () => {
      promptInput.value = question;
      promptInput.focus();
      form.requestSubmit();
    });
    suggestions.appendChild(button);
  }
}

async function requestAnswer(message) {
  const response = await fetch("/api/ai/chat", {
    method: "POST",
    credentials: "include",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      message,
      ...(conversationId ? {conversation_id: conversationId} : {})
    })
  });

  let payload;
  try {
    payload = await response.json();
  } catch {
    throw new Error("The server returned an unreadable response.");
  }
  if (!response.ok) {
    throw new Error(typeof payload.detail === "string" ? payload.detail : "The AI request failed.");
  }
  return payload;
}

form.addEventListener("submit", async event => {
  event.preventDefault();
  const message = promptInput.value.trim();
  if (!message || pending) return;

  pending = true;
  addMessage("user", message);
  promptInput.value = "";
  submitButton.disabled = true;
  submitButton.querySelector("span").textContent = "Thinking";
  setStatus("Thinking...");

  try {
    const result = await requestAnswer(message);
    conversationId = result.conversation_id || conversationId;
    addMessage("assistant", result.answer || "I could not generate an answer for that question.");
    setStatus(result.sections?.length
      ? `Using ${result.sections.length} financial data sections for context.`
      : "Ready for another question.");
  } catch (error) {
    addMessage("assistant", `I couldn’t answer that right now. ${error.message}`);
    setStatus(error.message, true);
  } finally {
    pending = false;
    submitButton.disabled = false;
    submitButton.querySelector("span").textContent = "Ask AI";
  }
});

window.addEventListener("wealthflow:authenticated", event => {
  const nextUserId = event.detail?.userId;
  if (authenticatedUserId !== null && authenticatedUserId !== nextUserId) {
    conversationId = null;
    pending = false;
    chat.replaceChildren();
    addMessage("assistant", "Ask me what changed this month, which category is growing, how close you are to your budget, or whether your goals are on track.");
  }
  authenticatedUserId = nextUserId;
});

renderSuggestions();
