const chatScroll = document.getElementById("chat-scroll");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const sendBtn = document.getElementById("send-btn");
const serverPills = document.getElementById("server-pills");
const headerTitle = document.getElementById("header-title");
const headerSubtitle = document.getElementById("header-subtitle");
const iconDev = document.getElementById("icon-dev");
const iconPharmacy = document.getElementById("icon-pharmacy");

const THEME_COPY = {
  dev: {
    title: "MCP Assistant",
    subtitle: "Host de consola con acceso a herramientas MCP",
  },
  pharmacy: {
    title: "Farmacia MCP · inspirado en Meykos",
    subtitle: "Asistente virtual de triage y pedidos",
  },
};

let currentTheme = "dev";

function setTheme(mode) {
  if (mode === currentTheme) return;
  currentTheme = mode;
  document.body.dataset.theme = mode;
  headerTitle.textContent = THEME_COPY[mode].title;
  headerSubtitle.textContent = THEME_COPY[mode].subtitle;
  iconDev.style.display = mode === "dev" ? "" : "none";
  iconPharmacy.style.display = mode === "pharmacy" ? "" : "none";
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

// A small, safe subset of Markdown for assistant replies: headings, bold,
// inline code and bullet lists. Escapes HTML first, so raw tags in the
// model's output are shown as text rather than executed.
function renderMarkdown(text) {
  const lines = escapeHtml(text).split("\n");
  const htmlParts = [];
  let listBuffer = [];

  const flushList = () => {
    if (listBuffer.length) {
      htmlParts.push(`<ul>${listBuffer.join("")}</ul>`);
      listBuffer = [];
    }
  };

  const inline = (line) =>
    line
      .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
      .replace(/`(.+?)`/g, "<code>$1</code>");

  for (const rawLine of lines) {
    const line = rawLine.trim();
    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    const bullet = line.match(/^[-*]\s+(.*)$/);
    if (heading) {
      flushList();
      const level = Math.min(heading[1].length + 2, 6);
      htmlParts.push(`<h${level}>${inline(heading[2])}</h${level}>`);
    } else if (bullet) {
      listBuffer.push(`<li>${inline(bullet[1])}</li>`);
    } else if (line === "") {
      flushList();
      htmlParts.push("<br>");
    } else {
      flushList();
      htmlParts.push(`<p>${inline(line)}</p>`);
    }
  }
  flushList();
  return htmlParts.join("");
}

function timeNow() {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function scrollToBottom() {
  chatScroll.parentElement.scrollTop = chatScroll.parentElement.scrollHeight;
}

function addMessage(role, text) {
  const row = document.createElement("div");
  row.className = `msg-row ${role}`;
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  if (role === "assistant") {
    bubble.innerHTML = renderMarkdown(text);
  } else {
    bubble.textContent = text;
  }
  const time = document.createElement("span");
  time.className = "msg-time";
  time.textContent = `${role === "user" ? "tú" : "asistente"} · ${timeNow()}`;
  row.appendChild(bubble);
  row.appendChild(time);
  chatScroll.appendChild(row);
  scrollToBottom();
  return row;
}

function addToolBadge(server, tool) {
  let row = chatScroll.lastElementChild;
  if (!row || !row.classList.contains("tool-row")) {
    row = document.createElement("div");
    row.className = "tool-row";
    chatScroll.appendChild(row);
  }
  const badge = document.createElement("span");
  badge.className = "tool-badge";
  badge.textContent = `${server}__${tool}`;
  row.appendChild(badge);
  scrollToBottom();
}

function addTyping() {
  const el = document.createElement("div");
  el.className = "typing";
  el.id = "typing-indicator";
  el.textContent = "escribiendo…";
  chatScroll.appendChild(el);
  scrollToBottom();
}

function removeTyping() {
  const el = document.getElementById("typing-indicator");
  if (el) el.remove();
}

function renderServerPills(servers, errors) {
  serverPills.innerHTML = "";
  for (const s of servers) {
    const pill = document.createElement("span");
    pill.className = "server-pill";
    pill.innerHTML = `<span class="dot"></span>${s.name} (${s.tools})`;
    serverPills.appendChild(pill);
  }
  for (const name of Object.keys(errors || {})) {
    const pill = document.createElement("span");
    pill.className = "server-pill down";
    pill.innerHTML = `<span class="dot"></span>${name} (falló)`;
    serverPills.appendChild(pill);
  }
}

const protocol = location.protocol === "https:" ? "wss:" : "ws:";
const ws = new WebSocket(`${protocol}//${location.host}/ws`);

ws.onmessage = (evt) => {
  const msg = JSON.parse(evt.data);
  if (msg.type === "ready") {
    renderServerPills(msg.servers, msg.errors);
  } else if (msg.type === "tool_call") {
    setTheme(msg.mode);
    addToolBadge(msg.server, msg.tool);
  } else if (msg.type === "assistant_message") {
    removeTyping();
    addMessage("assistant", msg.text);
    sendBtn.disabled = false;
  } else if (msg.type === "error") {
    removeTyping();
    addMessage("assistant", `Error: ${msg.message}`);
    sendBtn.disabled = false;
  }
};

ws.onclose = () => {
  addMessage("assistant", "Se perdió la conexión con el servidor. Recarga la página.");
  sendBtn.disabled = true;
};

chatInput.addEventListener("keydown", (evt) => {
  if (evt.key === "Enter" && !evt.shiftKey) {
    evt.preventDefault();
    chatForm.requestSubmit();
  }
});

chatForm.addEventListener("submit", (evt) => {
  evt.preventDefault();
  const text = chatInput.value.trim();
  if (!text || ws.readyState !== WebSocket.OPEN) return;
  addMessage("user", text);
  chatInput.value = "";
  sendBtn.disabled = true;
  addTyping();
  ws.send(JSON.stringify({ text }));
});
