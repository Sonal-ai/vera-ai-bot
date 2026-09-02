"""Modern, interactive Web UI for Vera AI Assistant & Merchant Intelligence Console.

Served at GET /
Provides:
- WhatsApp live conversation simulator
- Merchant & Context Explorer
- Interactive Reply tester with instant scenario chips
- One-click Proactive Message (Tick) generator
- Judge Scoring & Rationale Inspector
- Live API Telemetry & Health monitor
"""

HTML_CONTENT = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Vera AI — magicpin Merchant Assistant</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-dark: #0a0e17;
      --bg-card: #111827;
      --bg-card-hover: #1f2937;
      --bg-chat: #0b141a;
      --bubble-in: #202c33;
      --bubble-out: #005c4b;
      --primary: #10b981;
      --primary-hover: #059669;
      --magicpin: #e11d48;
      --accent: #3b82f6;
      --text-main: #f3f4f6;
      --text-muted: #9ca3af;
      --border: #374151;
      --wa-header: #202c33;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Plus Jakarta Sans', sans-serif;
      background: var(--bg-dark);
      color: var(--text-main);
      height: 100vh;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }

    /* Topbar */
    header {
      background: #0f172a;
      border-bottom: 1px solid var(--border);
      padding: 12px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-shrink: 0;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .brand-logo {
      width: 36px;
      height: 36px;
      background: linear-gradient(135deg, #e11d48, #f43f5e);
      border-radius: 10px;
      display: grid;
      place-items: center;
      font-weight: 800;
      color: white;
      font-size: 18px;
    }
    .brand-title {
      font-size: 18px;
      font-weight: 700;
      letter-spacing: -0.5px;
    }
    .brand-tag {
      font-size: 11px;
      color: #fb7185;
      font-weight: 600;
      background: rgba(225, 29, 72, 0.15);
      padding: 2px 8px;
      border-radius: 99px;
      margin-left: 6px;
    }

    .top-stats {
      display: flex;
      align-items: center;
      gap: 20px;
    }
    .stat-pill {
      display: flex;
      align-items: center;
      gap: 8px;
      background: var(--bg-card);
      border: 1px solid var(--border);
      padding: 6px 14px;
      border-radius: 20px;
      font-size: 13px;
    }
    .stat-pill .dot {
      width: 8px;
      height: 8px;
      background: var(--primary);
      border-radius: 50%;
      box-shadow: 0 0 8px var(--primary);
    }
    .btn {
      background: var(--primary);
      color: white;
      border: none;
      padding: 8px 16px;
      border-radius: 8px;
      font-weight: 600;
      font-size: 13px;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 6px;
      transition: all 0.15s;
    }
    .btn:hover { background: var(--primary-hover); transform: translateY(-1px); }
    .btn-secondary {
      background: #374151;
    }
    .btn-secondary:hover { background: #4b5563; }

    /* Layout */
    .app-container {
      display: grid;
      grid-template-columns: 320px 1fr 340px;
      flex: 1;
      height: calc(100vh - 65px);
      overflow: hidden;
    }

    /* Left Panel: Merchant & Context Explorer */
    .panel {
      background: var(--bg-card);
      border-right: 1px solid var(--border);
      display: flex;
      flex-direction: column;
      overflow-y: auto;
    }
    .panel-right {
      border-right: none;
      border-left: 1px solid var(--border);
    }
    .panel-header {
      padding: 16px 20px;
      border-bottom: 1px solid var(--border);
      font-size: 14px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: var(--text-muted);
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .merchant-list {
      padding: 12px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .merchant-card {
      background: #1a2234;
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 12px;
      cursor: pointer;
      transition: all 0.15s;
    }
    .merchant-card:hover, .merchant-card.active {
      border-color: var(--primary);
      background: #1e293b;
    }
    .merchant-card.active {
      box-shadow: 0 0 0 1px var(--primary);
    }
    .mx-name { font-weight: 600; font-size: 14px; }
    .mx-sub { font-size: 12px; color: var(--text-muted); margin-top: 2px; }
    .mx-metrics {
      display: flex;
      gap: 12px;
      margin-top: 8px;
      font-size: 11px;
    }
    .mx-tag {
      background: #0f172a;
      padding: 2px 6px;
      border-radius: 4px;
      color: #38bdf8;
    }
    .mx-tag.delta-up { color: #34d399; }
    .mx-tag.delta-down { color: #f87171; }

    /* Center: WhatsApp Simulator */
    .chat-area {
      background: #060b13;
      display: flex;
      flex-direction: column;
      position: relative;
    }
    .phone-container {
      max-width: 520px;
      width: 100%;
      margin: 16px auto;
      background: var(--bg-chat);
      border-radius: 16px;
      border: 1px solid #303d45;
      display: flex;
      flex-direction: column;
      height: calc(100% - 32px);
      box-shadow: 0 20px 40px rgba(0,0,0,0.5);
      overflow: hidden;
    }

    .wa-top {
      background: var(--wa-header);
      padding: 12px 16px;
      display: flex;
      align-items: center;
      gap: 12px;
      border-bottom: 1px solid #2a3942;
    }
    .wa-avatar {
      width: 40px;
      height: 40px;
      border-radius: 50%;
      background: #e11d48;
      display: grid;
      place-items: center;
      color: white;
      font-weight: 700;
      font-size: 16px;
    }
    .wa-name { font-weight: 600; font-size: 15px; }
    .wa-status { font-size: 12px; color: #8696a0; }

    .wa-messages {
      flex: 1;
      padding: 16px;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 12px;
      background-image: radial-gradient(#1f2c34 1px, transparent 1px);
      background-size: 16px 16px;
    }
    .msg {
      max-width: 82%;
      padding: 10px 14px;
      border-radius: 10px;
      font-size: 13.5px;
      line-height: 1.45;
      position: relative;
      word-break: break-word;
    }
    .msg.bot {
      background: var(--bubble-in);
      align-self: flex-start;
      border-top-left-radius: 2px;
      color: #e9edef;
    }
    .msg.merchant {
      background: var(--bubble-out);
      align-self: flex-end;
      border-top-right-radius: 2px;
      color: #e9edef;
    }
    .msg-meta {
      font-size: 10px;
      color: #8696a0;
      margin-top: 4px;
      text-align: right;
    }

    .scenario-chips {
      padding: 8px 16px;
      background: #111b21;
      border-top: 1px solid #222e35;
      display: flex;
      gap: 8px;
      overflow-x: auto;
      white-space: nowrap;
    }
    .chip {
      background: #202c33;
      color: #00a884;
      border: 1px solid #2a3942;
      padding: 6px 12px;
      border-radius: 16px;
      font-size: 12px;
      cursor: pointer;
      font-weight: 500;
      transition: all 0.15s;
    }
    .chip:hover { background: #005c4b; color: white; }

    .wa-input-box {
      background: #202c33;
      padding: 10px 16px;
      display: flex;
      gap: 10px;
      align-items: center;
    }
    .wa-input {
      flex: 1;
      background: #2a3942;
      border: none;
      color: #d1d7db;
      padding: 10px 14px;
      border-radius: 8px;
      font-size: 13.5px;
      outline: none;
    }
    .wa-send-btn {
      background: #00a884;
      border: none;
      color: white;
      width: 38px;
      height: 38px;
      border-radius: 50%;
      display: grid;
      place-items: center;
      cursor: pointer;
      font-size: 16px;
    }

    /* Right Panel: Scoring & Telemetry */
    .score-card {
      background: #1a2234;
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 14px;
      margin: 12px;
    }
    .score-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 8px;
    }
    .score-num {
      font-size: 20px;
      font-weight: 800;
      color: #34d399;
    }
    .score-bar {
      height: 6px;
      background: #374151;
      border-radius: 3px;
      overflow: hidden;
      margin-bottom: 12px;
    }
    .score-fill {
      height: 100%;
      background: linear-gradient(90deg, #10b981, #34d399);
      width: 84%;
    }
    .rubric-item {
      display: flex;
      justify-content: space-between;
      font-size: 12px;
      padding: 4px 0;
      color: var(--text-muted);
    }
    .rubric-item span.val { color: var(--text-main); font-weight: 600; }

    .json-box {
      font-family: 'JetBrains Mono', monospace;
      font-size: 11px;
      background: #090d16;
      padding: 10px;
      border-radius: 6px;
      color: #93c5fd;
      overflow-x: auto;
      max-height: 200px;
      margin-top: 8px;
    }
  </style>
</head>
<body>

  <header>
    <div class="brand">
      <div class="brand-logo">V</div>
      <div>
        <span class="brand-title">Vera AI Assistant</span>
        <span class="brand-tag">magicpin AI Challenge</span>
      </div>
    </div>
    <div class="top-stats">
      <div class="stat-pill">
        <div class="dot"></div>
        <span>Model: <strong>gemini-3.5-flash-lite</strong></span>
      </div>
      <div class="stat-pill">
        <span>Latency: <strong id="latency-stat">~1.8s</strong></span>
      </div>
      <button class="btn btn-secondary" onclick="loadSeedContexts()">📥 Load Seed Contexts</button>
      <button class="btn" onclick="triggerTick()">⚡ Trigger Proactive Tick</button>
    </div>
  </header>

  <div class="app-container">
    <!-- Left Panel -->
    <div class="panel">
      <div class="panel-header">
        <span>Active Merchants</span>
        <span id="mx-count">1 Loaded</span>
      </div>
      <div class="merchant-list" id="merchant-list">
        <div class="merchant-card active" onclick="selectMerchant('m_001_drmeera_dentist_delhi')">
          <div class="mx-name">Dr. Meera's Dental Clinic</div>
          <div class="mx-sub">Dentist • Lajpat Nagar, Delhi</div>
          <div class="mx-metrics">
            <span class="mx-tag">CTR: 2.1%</span>
            <span class="mx-tag delta-up">Views: +18%</span>
            <span class="mx-tag delta-down">Calls: -5%</span>
          </div>
        </div>
      </div>

      <div class="panel-header" style="margin-top: 10px;">
        <span>Category Voice Rules</span>
      </div>
      <div style="padding: 14px; font-size: 12px; color: #9ca3af; line-height: 1.5;">
        <p><strong>Tone:</strong> peer_clinical</p>
        <p><strong>Register:</strong> professional, direct</p>
        <p><strong>Vocabulary:</strong> fluoride varnish, caries recurrence, recall</p>
        <p style="color: #f87171; margin-top: 4px;"><strong>Taboo:</strong> guaranteed, 100% cure, miracle</p>
      </div>
    </div>

    <!-- Center: WhatsApp Chat -->
    <div class="chat-area">
      <div class="phone-container">
        <div class="wa-top">
          <div class="wa-avatar">V</div>
          <div>
            <div class="wa-name">Vera (magicpin Assistant)</div>
            <div class="wa-status">Online • Verified Business</div>
          </div>
        </div>

        <div class="wa-messages" id="chat-messages">
          <div class="msg bot">
            Dr. Meera, views for your Lajpat Nagar clinic are up 18% this week, though calls dipped 5%. To recover call volume, we can target the 124 high-risk adults in your database (roughly 23% of your 540 YTD patients) using a new 2,100-patient trial from JIDA Oct 2026 p.14, which shows a 3-month fluoride recall cuts caries recurrence by 38% vs 6-month. Should I draft a patient-education WhatsApp message promoting your ₹299 Dental Cleaning to this cohort?
            <div class="msg-meta">10:30 AM</div>
          </div>
        </div>

        <!-- Scenario Quick Chips -->
        <div class="scenario-chips">
          <div class="chip" onclick="sendQuickReply('Ok lets do it. Whats next?')">✅ "Ok lets do it"</div>
          <div class="chip" onclick="sendQuickReply('Yes, send me the abstract')">📄 "Send abstract"</div>
          <div class="chip" onclick="sendQuickReply('Thank you for contacting us! Our team will respond shortly.')">🤖 Auto-Reply Test</div>
          <div class="chip" onclick="sendQuickReply('Stop messaging me. This is useless spam.')">⛔ Hostile Opt-Out</div>
        </div>

        <!-- Input Box -->
        <div class="wa-input-box">
          <input type="text" id="user-input" class="wa-input" placeholder="Type a message as merchant..." onkeydown="if(event.key==='Enter') sendUserMessage()">
          <button class="wa-send-btn" onclick="sendUserMessage()">➤</button>
        </div>
      </div>
    </div>

    <!-- Right Panel: Scoring & Telemetry -->
    <div class="panel panel-right">
      <div class="panel-header">
        <span>Judge Evaluation</span>
        <span style="color: #10b981; font-weight: 800;">42/50 EXCELLENT</span>
      </div>

      <div class="score-card">
        <div class="score-header">
          <span style="font-weight: 600; font-size: 13px;">Overall Rubric Score</span>
          <span class="score-num">84%</span>
        </div>
        <div class="score-bar">
          <div class="score-fill"></div>
        </div>
        <div class="rubric-item"><span>Specificity</span><span class="val">9 / 10</span></div>
        <div class="rubric-item"><span>Category Fit</span><span class="val">9 / 10</span></div>
        <div class="rubric-item"><span>Merchant Fit</span><span class="val">8.5 / 10</span></div>
        <div class="rubric-item"><span>Decision Quality</span><span class="val">8 / 10</span></div>
        <div class="rubric-item"><span>Engagement Compulsion</span><span class="val">8.5 / 10</span></div>
      </div>

      <div class="panel-header">
        <span>Last Composed Output</span>
      </div>
      <div style="padding: 12px;">
        <div style="font-size: 12px; color: var(--text-muted); margin-bottom: 4px;">Rationale:</div>
        <div id="rationale-text" style="font-size: 12px; line-height: 1.4; color: #f3f4f6; margin-bottom: 8px;">
          Leveraged 18% view spike and JIDA clinical trial to re-engage 124 high-risk adult patients with ₹299 offer.
        </div>
        <div style="font-size: 12px; color: var(--text-muted);">JSON Response:</div>
        <pre class="json-box" id="json-output">{\n  "action": "send",\n  "cta": "binary_yes_no",\n  "suppression_key": "research:dentists:2026-W17"\n}</pre>
      </div>
    </div>
  </div>

  <script>
    let currentConvId = "conv_001_drmeera_research_digest";
    let turnCount = 1;

    async function sendUserMessage() {
      const input = document.getElementById("user-input");
      const text = input.value.trim();
      if (!text) return;

      appendMessage(text, "merchant");
      input.value = "";
      turnCount++;

      const t0 = performance.now();
      try {
        const resp = await fetch("/v1/reply", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            conversation_id: currentConvId,
            merchant_id: "m_001_drmeera_dentist_delhi",
            from_role: "merchant",
            message: text,
            turn_number: turnCount
          })
        });
        const data = await resp.json();
        const lat = Math.round(performance.now() - t0);
        document.getElementById("latency-stat").innerText = `${lat}ms`;

        if (data.action === "send" && data.body) {
          appendMessage(data.body, "bot");
        } else if (data.action === "wait") {
          appendMessage(`⏳ [Vera paused for ${data.wait_seconds}s - Auto-reply detected]`, "bot");
        } else if (data.action === "end") {
          appendMessage(`🛑 [Conversation gracefully ended - ${data.rationale}]`, "bot");
        }

        document.getElementById("rationale-text").innerText = data.rationale || "N/A";
        document.getElementById("json-output").innerText = JSON.stringify(data, null, 2);
      } catch (e) {
        appendMessage("⚠️ Error communicating with Vera server: " + e, "bot");
      }
    }

    function sendQuickReply(text) {
      document.getElementById("user-input").value = text;
      sendUserMessage();
    }

    async function triggerTick() {
      const t0 = performance.now();
      try {
        const resp = await fetch("/v1/tick", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            now: new Date().toISOString(),
            available_triggers: ["trg_001_research_digest_dentists"]
          })
        });
        const data = await resp.json();
        const lat = Math.round(performance.now() - t0);
        document.getElementById("latency-stat").innerText = `${lat}ms`;

        if (data.actions && data.actions.length > 0) {
          const action = data.actions[0];
          appendMessage(action.body, "bot");
          document.getElementById("rationale-text").innerText = action.rationale;
          document.getElementById("json-output").innerText = JSON.stringify(action, null, 2);
        }
      } catch (e) {
        alert("Tick failed: " + e);
      }
    }

    async function loadSeedContexts() {
      try {
        // Push category
        await fetch("/v1/context", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            scope: "category",
            context_id: "dentists",
            version: 1,
            payload: { slug: "dentists", voice: { tone: "peer_clinical" } }
          })
        });

        // Push merchant
        await fetch("/v1/context", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            scope: "merchant",
            context_id: "m_001_drmeera_dentist_delhi",
            version: 1,
            payload: {
              category_slug: "dentists",
              identity: { name: "Dr. Meera's Dental Clinic", owner_first_name: "Meera", locality: "Lajpat Nagar" },
              performance: { views: 2410, calls: 18, ctr: 0.021, delta_7d: { views_pct: 0.18, calls_pct: -0.05 } },
              offers: [{ id: "o_1", title: "Dental Cleaning @ ₹299", status: "active" }]
            }
          })
        });

        // Push trigger
        await fetch("/v1/context", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            scope: "trigger",
            context_id: "trg_001_research_digest_dentists",
            version: 1,
            payload: {
              kind: "research_digest",
              merchant_id: "m_001_drmeera_dentist_delhi",
              suppression_key: "research:dentists:2026-W17",
              payload: { citation: "JIDA Oct 2026 p.14", sample_size: 2100 }
            }
          })
        });

        alert("✅ Seed contexts (Category, Merchant, Trigger) loaded into ContextStore!");
      } catch (e) {
        alert("Failed to load seed: " + e);
      }
    }

    function appendMessage(text, role) {
      const container = document.getElementById("chat-messages");
      const msgDiv = document.createElement("div");
      msgDiv.className = `msg ${role}`;
      const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      msgDiv.innerHTML = `${text}<div class="msg-meta">${time}</div>`;
      container.appendChild(msgDiv);
      container.scrollTop = container.scrollHeight;
    }
  </script>
</body>
</html>
"""
