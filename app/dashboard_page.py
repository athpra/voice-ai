DASHBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>DemoTel Voice AI &mdash; Live Call Monitor</title>
<style>
  :root {
    --bg: #0A0E14;
    --surface: #10151E;
    --surface-2: #161D29;
    --line: #232C3B;
    --ink: #E9EDF2;
    --muted: #7C8797;
    --signal: #F2B84B;
    --signal-glow: rgba(242, 184, 75, 0.45);
    --wave: #59CFC9;
    --wave-glow: rgba(89, 207, 201, 0.4);
    --good: #4FCF8A;
    --good-soft: rgba(79, 207, 138, 0.12);
  }
  * { box-sizing: border-box; }
  html, body { height: 100%; }
  body {
    margin: 0;
    background:
      radial-gradient(1200px 600px at 15% -10%, rgba(242,184,75,0.06), transparent 60%),
      radial-gradient(1000px 500px at 100% 10%, rgba(89,207,201,0.05), transparent 60%),
      var(--bg);
    color: var(--ink);
    font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    -webkit-font-smoothing: antialiased;
    display: flex;
    flex-direction: column;
  }
  .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }

  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1.3rem 2rem;
    border-bottom: 1px solid var(--line);
  }
  header .brand { display: flex; flex-direction: column; gap: 0.15rem; }
  header .brand .eyebrow {
    font-family: ui-monospace, monospace;
    font-size: 0.68rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--muted);
  }
  header .brand h1 { font-size: 1.15rem; font-weight: 600; margin: 0; }
  .conn { display: flex; align-items: center; gap: 0.5rem; font-size: 0.8rem; color: var(--muted); }
  .conn .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--muted); }
  .conn.online .dot { background: var(--good); box-shadow: 0 0 8px var(--good); }
  .conn.online { color: var(--good); }

  main {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 2rem;
    gap: 2rem;
    position: relative;
  }

  /* -------- idle -------- */
  #idle {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1.4rem;
    text-align: center;
  }
  .pulse-ring {
    width: 84px; height: 84px; border-radius: 50%;
    border: 2px solid var(--signal);
    display: flex; align-items: center; justify-content: center;
    position: relative;
  }
  .pulse-ring::before {
    content: ""; position: absolute; inset: -12px; border-radius: 50%;
    border: 1px solid var(--signal-glow);
    animation: ring 2.2s ease-out infinite;
  }
  .pulse-ring .core { width: 14px; height: 14px; border-radius: 50%; background: var(--signal); box-shadow: 0 0 16px var(--signal-glow); }
  @keyframes ring {
    0% { transform: scale(0.85); opacity: 0.9; }
    100% { transform: scale(1.6); opacity: 0; }
  }
  #idle h2 { font-size: 1.3rem; font-weight: 600; margin: 0; }
  #idle p { color: var(--muted); margin: 0; max-width: 40ch; }
  #idle .number {
    font-family: ui-monospace, monospace;
    font-size: 1.6rem;
    letter-spacing: 0.02em;
    color: var(--signal);
    padding: 0.5rem 1.1rem;
    border: 1px solid var(--line);
    border-radius: 10px;
    background: var(--surface);
  }
  @media (prefers-reduced-motion: reduce) {
    .pulse-ring::before { animation: none; }
  }

  /* -------- live view -------- */
  #live { display: none; width: 100%; max-width: 1080px; flex-direction: column; gap: 1.8rem; }
  #live.show { display: flex; }
  #idle.hide { display: none; }

  .call-banner {
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 12px;
    padding: 0.9rem 1.3rem;
  }
  .call-banner .label { font-size: 0.72rem; letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted); }
  .call-banner .value { font-size: 0.95rem; font-weight: 600; }
  .status-badge {
    font-family: ui-monospace, monospace;
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    padding: 0.28rem 0.7rem;
    border-radius: 999px;
    background: var(--good-soft);
    color: var(--good);
  }
  .status-badge.ended { background: var(--surface-2); color: var(--muted); }

  /* -------- pipeline -------- */
  .pipeline {
    display: flex;
    align-items: center;
    justify-content: center;
    flex-wrap: wrap;
    gap: 0.4rem;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 16px;
    padding: 1.6rem 1.2rem;
  }
  .node {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.5rem;
    padding: 0.9rem 1rem;
    border-radius: 12px;
    min-width: 108px;
    border: 1px solid transparent;
    transition: border-color 0.25s ease, background 0.25s ease;
  }
  .node .ring {
    width: 34px; height: 34px; border-radius: 50%;
    border: 2px solid var(--line);
    display: flex; align-items: center; justify-content: center;
    transition: border-color 0.25s ease, box-shadow 0.25s ease;
  }
  .node .ring .core { width: 8px; height: 8px; border-radius: 50%; background: var(--muted); transition: background 0.25s ease; }
  .node .label { font-size: 0.78rem; font-weight: 600; text-align: center; }
  .node .sub { font-size: 0.66rem; color: var(--muted); text-align: center; }
  .arrow { color: var(--line); font-size: 1rem; padding: 0 0.1rem; }

  .node[data-state="active"] .ring { border-color: var(--signal); box-shadow: 0 0 14px var(--signal-glow); animation: nodepulse 1.1s ease-in-out infinite; }
  .node[data-state="active"] .ring .core { background: var(--signal); }
  .node[data-state="active"] .label { color: var(--signal); }
  .node[data-state="done"] .ring { border-color: var(--good); }
  .node[data-state="done"] .ring .core { background: var(--good); }
  @keyframes nodepulse {
    0%, 100% { box-shadow: 0 0 8px var(--signal-glow); }
    50% { box-shadow: 0 0 20px var(--signal-glow); }
  }
  @media (prefers-reduced-motion: reduce) {
    .node[data-state="active"] .ring { animation: none; }
  }

  /* -------- caller card -------- */
  .caller-card {
    display: none;
    background: var(--surface);
    border: 1px solid var(--line);
    border-left: 3px solid var(--wave);
    border-radius: 12px;
    padding: 1.1rem 1.4rem;
    gap: 0.3rem;
    flex-direction: column;
  }
  .caller-card.show { display: flex; }
  .caller-card .tag { font-family: ui-monospace, monospace; font-size: 0.66rem; text-transform: uppercase; letter-spacing: 0.08em; color: var(--wave); }
  .caller-card .name { font-size: 1.15rem; font-weight: 700; }
  .caller-card .details { color: var(--muted); font-size: 0.85rem; }

  /* -------- transcript -------- */
  .transcript {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 14px;
    padding: 1.1rem 1.3rem;
    display: flex;
    flex-direction: column;
    gap: 0.7rem;
    max-height: 300px;
    overflow-y: auto;
  }
  .turn { display: grid; grid-template-columns: 70px 1fr; gap: 0.8rem; animation: rise 0.25s ease; }
  @keyframes rise { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }
  .turn .who { font-family: ui-monospace, monospace; font-size: 0.68rem; text-transform: uppercase; color: var(--muted); padding-top: 0.15rem; }
  .turn.agent .who { color: var(--signal); }
  .turn.caller .who { color: var(--wave); }
  .turn p { margin: 0; font-size: 0.92rem; }
  .transcript:empty::before { content: "Transcript will appear here once the call connects."; color: var(--muted); font-size: 0.85rem; }

  footer { padding: 1rem 2rem; text-align: center; color: var(--muted); font-size: 0.75rem; border-top: 1px solid var(--line); }
</style>
</head>
<body>

  <header>
    <div class="brand">
      <span class="eyebrow">DemoTel &middot; Voice AI Agent</span>
      <h1>Live Call Monitor</h1>
    </div>
    <div class="conn" id="conn"><span class="dot"></span><span id="connLabel">Connecting&hellip;</span></div>
  </header>

  <main>
    <div id="idle">
      <div class="pulse-ring"><div class="core"></div></div>
      <h2>Waiting for a call</h2>
      <p>This screen updates live the moment a call comes in &mdash; watch it light up as the call moves through the system.</p>
      <div class="number" id="demoNumber"></div>
    </div>

    <div id="live">
      <div class="call-banner">
        <div><div class="label">Caller</div><div class="value" id="callerNumber">&mdash;</div></div>
        <div class="status-badge" id="callStatus">In call</div>
      </div>

      <div class="pipeline" id="pipeline">
        <div class="node" data-node="caller" data-state="active"><div class="ring"><div class="core"></div></div><div class="label">Caller</div><div class="sub">Phone</div></div>
        <div class="arrow">&rarr;</div>
        <div class="node" data-node="twilio" data-state="active"><div class="ring"><div class="core"></div></div><div class="label">Twilio</div><div class="sub">Telephony</div></div>
        <div class="arrow">&rarr;</div>
        <div class="node" data-node="app" data-state="active"><div class="ring"><div class="core"></div></div><div class="label">App</div><div class="sub">Cloudera AI</div></div>
        <div class="arrow">&rarr;</div>
        <div class="node" data-node="cdp" data-state="idle"><div class="ring"><div class="core"></div></div><div class="label">CDP</div><div class="sub">Customer data</div></div>
        <div class="arrow">&rarr;</div>
        <div class="node" data-node="stt" data-state="idle"><div class="ring"><div class="core"></div></div><div class="label">STT</div><div class="sub">Cartesia</div></div>
        <div class="arrow">&rarr;</div>
        <div class="node" data-node="llm" data-state="idle"><div class="ring"><div class="core"></div></div><div class="label">LLM</div><div class="sub">Cloudera AI</div></div>
        <div class="arrow">&rarr;</div>
        <div class="node" data-node="tts" data-state="idle"><div class="ring"><div class="core"></div></div><div class="label">TTS</div><div class="sub">Cartesia</div></div>
      </div>

      <div class="caller-card" id="callerCard">
        <span class="tag" id="callerTag">Recognized caller</span>
        <span class="name" id="callerName"></span>
        <span class="details" id="callerDetails"></span>
      </div>

      <div class="transcript" id="transcript"></div>
    </div>
  </main>

  <footer>Twilio &middot; Cartesia &middot; Cloudera AI Inference Service</footer>

<script>
(function () {
  var demoNumber = "__DEMO_PHONE_NUMBER__";
  var demoNumberEl = document.getElementById("demoNumber");
  if (demoNumber) {
    demoNumberEl.textContent = demoNumber;
  } else {
    demoNumberEl.style.display = "none";
  }

  var idleEl = document.getElementById("idle");
  var liveEl = document.getElementById("live");
  var connEl = document.getElementById("conn");
  var connLabel = document.getElementById("connLabel");
  var callerNumberEl = document.getElementById("callerNumber");
  var callStatusEl = document.getElementById("callStatus");
  var callerCardEl = document.getElementById("callerCard");
  var callerTagEl = document.getElementById("callerTag");
  var callerNameEl = document.getElementById("callerName");
  var callerDetailsEl = document.getElementById("callerDetails");
  var transcriptEl = document.getElementById("transcript");
  var resetTimer = null;

  function node(key) { return document.querySelector('.node[data-node="' + key + '"]'); }
  function setNode(key, state) { var el = node(key); if (el) el.setAttribute("data-state", state); }

  function resetPipeline() {
    setNode("caller", "idle");
    setNode("twilio", "idle");
    setNode("app", "idle");
    setNode("cdp", "idle");
    setNode("stt", "idle");
    setNode("llm", "idle");
    setNode("tts", "idle");
  }

  function showIdle() {
    idleEl.classList.remove("hide");
    liveEl.classList.remove("show");
    transcriptEl.innerHTML = "";
    callerCardEl.classList.remove("show");
    resetPipeline();
  }

  function showLive() {
    idleEl.classList.add("hide");
    liveEl.classList.add("show");
  }

  function addTurn(who, text) {
    var row = document.createElement("div");
    row.className = "turn " + who;
    var label = document.createElement("div");
    label.className = "who";
    label.textContent = who === "agent" ? "Agent" : "Caller";
    var p = document.createElement("p");
    p.textContent = text;
    row.appendChild(label);
    row.appendChild(p);
    transcriptEl.appendChild(row);
    transcriptEl.scrollTop = transcriptEl.scrollHeight;
  }

  function yearsSince(isoDate) {
    if (!isoDate) return null;
    var start = new Date(isoDate);
    if (isNaN(start.getTime())) return null;
    var years = (Date.now() - start.getTime()) / (1000 * 60 * 60 * 24 * 365);
    return Math.max(Math.floor(years), 0);
  }

  function handleEvent(evt) {
    switch (evt.type) {
      case "call_received":
        break;
      case "call_started":
        if (resetTimer) { clearTimeout(resetTimer); resetTimer = null; }
        showLive();
        transcriptEl.innerHTML = "";
        callerCardEl.classList.remove("show");
        callStatusEl.textContent = "In call";
        callStatusEl.classList.remove("ended");
        callerNumberEl.textContent = evt.caller_number || "Unknown";
        setNode("caller", "active");
        setNode("twilio", "active");
        setNode("app", "active");
        setNode("cdp", "active");
        setNode("stt", "active");
        setNode("llm", "idle");
        setNode("tts", "idle");
        break;
      case "customer_identified":
        setNode("cdp", "done");
        callerCardEl.classList.add("show");
        if (evt.known) {
          callerTagEl.textContent = "Recognized caller";
          callerNameEl.textContent = evt.name || "Customer";
          var years = yearsSince(evt.customer_since_date);
          var bits = [];
          if (evt.plan) bits.push(evt.plan);
          if (evt.loyalty_tier) bits.push(evt.loyalty_tier + " tier");
          if (years !== null) bits.push("customer for " + years + " years");
          callerDetailsEl.textContent = bits.join(" · ");
        } else {
          callerTagEl.textContent = "New caller";
          callerNameEl.textContent = "Unrecognized number";
          callerDetailsEl.textContent = "No account on file — treated as a new customer.";
        }
        break;
      case "routing_to_llm":
        setNode("llm", "active");
        break;
      case "greeting_sent":
      case "agent_reply":
        setNode("llm", "done");
        addTurn("agent", evt.text);
        break;
      case "speaking":
        setNode("tts", "active");
        break;
      case "speaking_done":
        setNode("tts", "done");
        break;
      case "caller_said":
        addTurn("caller", evt.text);
        setNode("stt", "active");
        break;
      case "call_ended":
        callStatusEl.textContent = "Call ended";
        callStatusEl.classList.add("ended");
        resetPipeline();
        resetTimer = setTimeout(showIdle, 6000);
        break;
    }
  }

  function connect() {
    var proto = location.protocol === "https:" ? "wss://" : "ws://";
    var ws = new WebSocket(proto + location.host + "/dashboard-events");

    ws.onopen = function () {
      connEl.classList.add("online");
      connLabel.textContent = "Live";
    };
    ws.onclose = function () {
      connEl.classList.remove("online");
      connLabel.textContent = "Reconnecting…";
      setTimeout(connect, 1500);
    };
    ws.onerror = function () { ws.close(); };
    ws.onmessage = function (msg) {
      try { handleEvent(JSON.parse(msg.data)); } catch (e) { /* ignore malformed events */ }
    };
  }

  connect();
})();
</script>
</body>
</html>
"""
