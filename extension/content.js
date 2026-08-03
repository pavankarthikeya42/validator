/**
 * content.js — Floating Pen Button + Validation Panel
 *
 * Injects a gorgeous floating action button (pen in circle) into every page.
 * Clicking it opens a control panel with Start / Stop / Resume buttons.
 * Real-time progress is polled from the local server every 2 seconds.
 */

(() => {
  // ── Guard: only inject once ─────────────────────────────────────────────────
  if (document.getElementById("__dv_fab__")) return;

  // ── Inject styles ───────────────────────────────────────────────────────────
  const STYLE = `
    /* ── Reset & Fonts ──────────────────────────────────────────────────────── */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    #__dv_root__ * {
      box-sizing: border-box;
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      margin: 0; padding: 0;
    }

    /* ── FAB Button ─────────────────────────────────────────────────────────── */
    #__dv_fab__ {
      position: fixed;
      bottom: 28px;
      right: 28px;
      width: 56px;
      height: 56px;
      border-radius: 50%;
      background: linear-gradient(135deg, #7c3aed, #2563eb);
      border: none;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 4px 20px rgba(124, 58, 237, 0.5), 0 2px 8px rgba(0,0,0,0.3);
      z-index: 2147483647;
      transition: transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1),
                  box-shadow 0.2s ease;
      outline: none;
      -webkit-tap-highlight-color: transparent;
    }

    #__dv_fab__:hover {
      transform: scale(1.1);
      box-shadow: 0 6px 28px rgba(124, 58, 237, 0.7), 0 3px 12px rgba(0,0,0,0.4);
    }

    #__dv_fab__:active {
      transform: scale(0.96);
    }

    #__dv_fab__.running {
      animation: __dv_pulse__ 2s ease-in-out infinite;
    }

    @keyframes __dv_pulse__ {
      0%, 100% { box-shadow: 0 4px 20px rgba(124,58,237,0.5), 0 0 0 0 rgba(124,58,237,0.4); }
      50%       { box-shadow: 0 4px 20px rgba(124,58,237,0.5), 0 0 0 12px rgba(124,58,237,0); }
    }

    /* ── Panel ──────────────────────────────────────────────────────────────── */
    #__dv_panel__ {
      position: fixed;
      bottom: 96px;
      right: 28px;
      width: 320px;
      background: rgba(15, 23, 42, 0.92);
      backdrop-filter: blur(20px);
      -webkit-backdrop-filter: blur(20px);
      border: 1px solid rgba(255,255,255,0.1);
      border-radius: 18px;
      padding: 20px;
      z-index: 2147483646;
      box-shadow: 0 24px 64px rgba(0,0,0,0.6), 0 0 0 1px rgba(124,58,237,0.2);
      color: #e2e8f0;
      display: none;
      transform-origin: bottom right;
      animation: __dv_panel_in__ 0.22s cubic-bezier(0.34, 1.56, 0.64, 1);
    }

    #__dv_panel__.visible {
      display: block;
    }

    @keyframes __dv_panel_in__ {
      from { opacity: 0; transform: scale(0.85) translateY(12px); }
      to   { opacity: 1; transform: scale(1)    translateY(0); }
    }

    /* ── Header ─────────────────────────────────────────────────────────────── */
    .__dv_header__ {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 16px;
    }

    .__dv_logo__ {
      width: 32px;
      height: 32px;
      border-radius: 8px;
      background: linear-gradient(135deg, #7c3aed, #2563eb);
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
    }

    .__dv_title__ {
      font-size: 14px;
      font-weight: 700;
      color: #f1f5f9;
      letter-spacing: -0.01em;
    }

    .__dv_subtitle__ {
      font-size: 11px;
      color: #64748b;
      margin-top: 1px;
    }

    /* ── Status Badge ───────────────────────────────────────────────────────── */
    .__dv_badge__ {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      padding: 3px 10px;
      border-radius: 9999px;
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      margin-left: auto;
      flex-shrink: 0;
    }

    .__dv_badge__.IDLE     { background: rgba(100,116,139,0.2); color: #94a3b8; }
    .__dv_badge__.RUNNING  { background: rgba(16,185,129,0.15); color: #34d399; }
    .__dv_badge__.STOPPED  { background: rgba(245,158,11,0.15); color: #fbbf24; }
    .__dv_badge__.COMPLETE { background: rgba(59,130,246,0.15); color: #60a5fa; }
    .__dv_badge__.ERROR    { background: rgba(239,68,68,0.15);  color: #f87171; }

    .__dv_dot__ {
      width: 6px; height: 6px; border-radius: 50%; background: currentColor;
    }

    .__dv_dot__.RUNNING { animation: __dv_blink__ 1s ease-in-out infinite; }

    @keyframes __dv_blink__ {
      0%, 100% { opacity: 1; } 50% { opacity: 0.3; }
    }

    /* ── Divider ─────────────────────────────────────────────────────────────  */
    .__dv_divider__ {
      height: 1px;
      background: rgba(255,255,255,0.07);
      margin: 14px 0;
    }

    /* ── Progress ────────────────────────────────────────────────────────────  */
    .__dv_progress_section__ {
      margin-bottom: 14px;
    }

    .__dv_progress_label__ {
      display: flex;
      justify-content: space-between;
      font-size: 11px;
      color: #64748b;
      margin-bottom: 6px;
    }

    .__dv_progress_track__ {
      height: 6px;
      background: rgba(255,255,255,0.08);
      border-radius: 9999px;
      overflow: hidden;
    }

    .__dv_progress_fill__ {
      height: 100%;
      border-radius: 9999px;
      background: linear-gradient(90deg, #7c3aed, #2563eb);
      transition: width 0.5s ease;
      min-width: 0%;
    }

    .__dv_progress_fill__.running {
      background: linear-gradient(90deg, #7c3aed, #06b6d4);
      animation: __dv_shimmer__ 1.5s linear infinite;
      background-size: 200% 100%;
    }

    @keyframes __dv_shimmer__ {
      0%   { background-position: 200% center; }
      100% { background-position: -200% center; }
    }

    /* ── Stats Grid ──────────────────────────────────────────────────────────  */
    .__dv_stats__ {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      margin-bottom: 14px;
    }

    .__dv_stat__ {
      background: rgba(255,255,255,0.04);
      border: 1px solid rgba(255,255,255,0.07);
      border-radius: 10px;
      padding: 10px 12px;
    }

    .__dv_stat_val__ {
      font-size: 20px;
      font-weight: 700;
      line-height: 1;
      color: #f1f5f9;
    }

    .__dv_stat_lbl__ {
      font-size: 10px;
      color: #475569;
      margin-top: 3px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }

    .__dv_stat_val__.green  { color: #34d399; }
    .__dv_stat_val__.red    { color: #f87171; }
    .__dv_stat_val__.yellow { color: #fbbf24; }
    .__dv_stat_val__.blue   { color: #60a5fa; }

    /* ── Buttons ─────────────────────────────────────────────────────────────  */
    .__dv_actions__ {
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      gap: 8px;
    }

    .__dv_btn__ {
      padding: 10px 4px;
      border: none;
      border-radius: 10px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 4px;
      transition: transform 0.15s ease, opacity 0.15s ease, filter 0.15s ease;
      letter-spacing: 0.01em;
    }

    .__dv_btn__:hover:not(:disabled) { transform: translateY(-1px); filter: brightness(1.1); }
    .__dv_btn__:active:not(:disabled) { transform: translateY(0); filter: brightness(0.95); }
    .__dv_btn__:disabled { opacity: 0.35; cursor: not-allowed; }

    .__dv_btn_icon__ { font-size: 18px; line-height: 1; }

    #__dv_btn_start__  { background: linear-gradient(135deg, #059669, #10b981); color: white; }
    #__dv_btn_stop__   { background: linear-gradient(135deg, #dc2626, #ef4444); color: white; }
    #__dv_btn_resume__ { background: linear-gradient(135deg, #d97706, #f59e0b); color: white; }

    /* ── Toast ───────────────────────────────────────────────────────────────  */
    .__dv_toast__ {
      position: fixed;
      bottom: 96px;
      right: 28px;
      background: rgba(15,23,42,0.95);
      color: #e2e8f0;
      border: 1px solid rgba(255,255,255,0.1);
      border-radius: 10px;
      padding: 10px 16px;
      font-size: 12px;
      font-weight: 500;
      z-index: 2147483648;
      animation: __dv_toast_in__ 0.2s ease, __dv_toast_out__ 0.3s ease 2.7s forwards;
      pointer-events: none;
      max-width: 280px;
    }

    @keyframes __dv_toast_in__  { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
    @keyframes __dv_toast_out__ { from { opacity: 1; } to { opacity: 0; } }

    /* ── Log line ────────────────────────────────────────────────────────────── */
    .__dv_log__ {
      margin-top: 10px;
      padding: 8px 10px;
      background: rgba(0,0,0,0.3);
      border: 1px solid rgba(255,255,255,0.06);
      border-radius: 8px;
      font-size: 10px;
      color: #64748b;
      word-break: break-all;
      line-height: 1.4;
      min-height: 28px;
      max-height: 60px;
      overflow: hidden;
      display: -webkit-box;
      -webkit-line-clamp: 3;
      -webkit-box-orient: vertical;
    }
    .__dv_log__.error  { color: #f87171; border-color: rgba(239,68,68,0.25); }
    .__dv_log__.warn   { color: #fbbf24; border-color: rgba(245,158,11,0.25); }
    .__dv_log__.ok     { color: #34d399; border-color: rgba(52,211,153,0.25); }

    /* ── Diagnose panel ───────────────────────────────────────────────── */
    .__dv_diag_btn__ {
      margin-top: 8px;
      width: 100%;
      background: rgba(255,255,255,0.05);
      border: 1px solid rgba(255,255,255,0.1);
      border-radius: 8px;
      color: #94a3b8;
      font-size: 11px;
      font-weight: 600;
      padding: 7px;
      cursor: pointer;
      transition: background 0.15s, color 0.15s;
      font-family: inherit;
      letter-spacing: 0.03em;
    }
    .__dv_diag_btn__:hover { background: rgba(255,255,255,0.09); color: #e2e8f0; }

    .__dv_diag_results__ {
      display: none;
      margin-top: 8px;
      background: rgba(0,0,0,0.35);
      border: 1px solid rgba(255,255,255,0.07);
      border-radius: 8px;
      padding: 10px;
      max-height: 180px;
      overflow-y: auto;
      font-size: 10px;
      line-height: 1.6;
    }
    .__dv_diag_results__.open { display: block; }

    .__dv_diag_item__ {
      display: flex;
      gap: 6px;
      padding: 2px 0;
      border-bottom: 1px solid rgba(255,255,255,0.04);
      word-break: break-all;
    }
    .__dv_diag_item__:last-child { border-bottom: none; }
    .__dv_diag_item__.err  { color: #f87171; }
    .__dv_diag_item__.ok   { color: #34d399; }
    .__dv_diag_item__.log  { color: #64748b; font-family: monospace; }
    .__dv_diag_item__.head { color: #94a3b8; font-weight: 700; padding-top: 6px; }

    /* ── Download Reports ────────────────────────────────────────────────── */
    .__dv_reports_section__ {
      margin-top: 10px;
    }
    .__dv_reports_label__ {
      font-size: 10px;
      font-weight: 700;
      color: #94a3b8;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 6px;
    }
    .__dv_reports_grid__ {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 6px;
    }
    .__dv_report_btn__ {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 4px;
      padding: 6px 8px;
      background: rgba(255,255,255,0.06);
      border: 1px solid rgba(255,255,255,0.1);
      border-radius: 8px;
      color: #38bdf8;
      font-size: 11px;
      font-weight: 600;
      cursor: pointer;
      text-decoration: none;
      transition: all 0.15s;
    }
    .__dv_report_btn__:hover {
      background: rgba(56,189,248,0.15);
      border-color: rgba(56,189,248,0.3);
      color: #7dd3fc;
    }
  `;

  const styleEl = document.createElement("style");
  styleEl.textContent = STYLE;
  document.head.appendChild(styleEl);

  // ── Utilities ────────────────────────────────────────────────────────────────
  function _truncateUrl(url) {
    try {
      const u = new URL(url);
      const path = u.pathname.length > 20 ? u.pathname.slice(0, 20) + "…" : u.pathname;
      return u.hostname + path;
    } catch {
      return url.slice(0, 35) + (url.length > 35 ? "…" : "");
    }
  }

  // ── Create root container ───────────────────────────────────────────────────
  const root = document.createElement("div");
  root.id = "__dv_root__";
  document.body.appendChild(root);


  // ── FAB Button ───────────────────────────────────────────────────────────────
  const fab = document.createElement("button");
  fab.id = "__dv_fab__";
  fab.title = "Document Validator (Click to open control panel)";
  fab.innerHTML = `
    <svg width="22" height="22" viewBox="0 0 24 24" fill="white">
      <path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zm17.71-10.21a1 1 0 000-1.41l-2.34-2.34a1 1 0 00-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/>
    </svg>
  `;
  root.appendChild(fab);

  // ── Panel ─────────────────────────────────────────────────────────────────────
  const panel = document.createElement("div");
  panel.id = "__dv_panel__";
  panel.innerHTML = `
    <div class="__dv_header__">
      <div class="__dv_logo__">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="white">
          <path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zm17.71-10.21a1 1 0 000-1.41l-2.34-2.34a1 1 0 00-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/>
        </svg>
      </div>
      <div>
        <div class="__dv_title__">Document Validator</div>
        <div class="__dv_subtitle__" id="__dv_page_url__" title="${window.location.href}">
          ${_truncateUrl(window.location.href)}
        </div>
      </div>
      <span id="__dv_badge__" class="__dv_badge__ IDLE">
        <span class="__dv_dot__ IDLE"></span>IDLE
      </span>
    </div>

    <div class="__dv_divider__"></div>

    <div class="__dv_progress_section__">
      <div class="__dv_progress_label__">
        <span id="__dv_prog_text__">Ready to validate</span>
        <span id="__dv_prog_pct__">0%</span>
      </div>
      <div class="__dv_progress_track__">
        <div id="__dv_prog_fill__" class="__dv_progress_fill__" style="width:0%"></div>
      </div>
    </div>

    <div class="__dv_stats__">
      <div class="__dv_stat__">
        <div id="__dv_s_docs__" class="__dv_stat_val__ blue">—</div>
        <div class="__dv_stat_lbl__">Docs Done</div>
      </div>
      <div class="__dv_stat__">
        <div id="__dv_s_fields__" class="__dv_stat_val__">—</div>
        <div class="__dv_stat_lbl__">Fields</div>
      </div>
      <div class="__dv_stat__">
        <div id="__dv_s_match__" class="__dv_stat_val__ green">—</div>
        <div class="__dv_stat_lbl__">Matches</div>
      </div>
      <div class="__dv_stat__">
        <div id="__dv_s_mismatch__" class="__dv_stat_val__ red">—</div>
        <div class="__dv_stat_lbl__">Mismatches</div>
      </div>
    </div>

    <div class="__dv_divider__"></div>

    <div class="__dv_actions__">
      <button id="__dv_btn_start__"  class="__dv_btn__">
        <span class="__dv_btn_icon__">▶</span>Start
      </button>
      <button id="__dv_btn_stop__"   class="__dv_btn__" disabled>
        <span class="__dv_btn_icon__">⏹</span>Stop
      </button>
      <button id="__dv_btn_resume__" class="__dv_btn__" disabled>
        <span class="__dv_btn_icon__">⏩</span>Resume
      </button>
    </div>

    <div id="__dv_log__" class="__dv_log__">Click ▶ Start to begin validation</div>

    <div class="__dv_reports_section__">
      <div class="__dv_reports_label__">📎 Manual PDF (Optional)</div>
      <div style="background:rgba(255,255,255,0.04); border:1px dashed rgba(255,255,255,0.15); border-radius:8px; padding:6px 8px;">
        <input type="file" id="__dv_manual_file__" accept=".pdf" style="font-size:10px; color:#cbd5e1; width:100%; cursor:pointer;">
      </div>
    </div>

    <div class="__dv_reports_section__">
      <div class="__dv_reports_label__">📥 Download Results Data</div>
      <div class="__dv_reports_grid__">
        <a href="http://localhost:8765/download/csv" target="_blank" class="__dv_report_btn__" id="__dv_dl_csv__">📊 CSV Data</a>
        <a href="http://localhost:8765/download/excel" target="_blank" class="__dv_report_btn__" id="__dv_dl_excel__">📗 Excel (.xlsx)</a>
        <a href="http://localhost:8765/download/json" target="_blank" class="__dv_report_btn__" id="__dv_dl_json__">📄 JSON Data</a>
        <a href="http://localhost:8765/download/html" target="_blank" class="__dv_report_btn__" id="__dv_dl_html__">🌐 HTML Report</a>
      </div>
    </div>

    <button id="__dv_diag_btn__" class="__dv_diag_btn__">⚙ Diagnose — show config &amp; log details</button>
    <div id="__dv_diag_results__" class="__dv_diag_results__"></div>
  `;
  root.appendChild(panel);

  // ── Helpers ───────────────────────────────────────────────────────────────────
  const $ = (id) => document.getElementById(id);

  // ── Diagnose ──────────────────────────────────────────────────────────────────
  let _diagOpen = false;

  async function runDiagnose() {
    const resultsEl = $("__dv_diag_results__");
    const btnEl     = $("__dv_diag_btn__");
    if (!resultsEl) return;

    // Toggle
    _diagOpen = !_diagOpen;
    if (!_diagOpen) {
      resultsEl.classList.remove("open");
      btnEl.textContent = "⚙ Diagnose — show config & log details";
      return;
    }

    resultsEl.classList.add("open");
    btnEl.textContent = "✕ Hide diagnostics";
    resultsEl.innerHTML = `<div class="__dv_diag_item__ log">Running checks…</div>`;

    const items = [];

    // 1. Config check
    try {
      const cfg = await api("GET", "/config-check");
      items.push({ cls: "head", icon: "📝", text: "config.yaml" });
      if (cfg.warnings && cfg.warnings.length) {
        cfg.warnings.forEach(w => items.push({ cls: "err", icon: "•", text: w }));
      } else {
        items.push({ cls: "ok", icon: "✓", text: "All selectors look configured" });
      }
    } catch (e) {
      items.push({ cls: "err", icon: "⚠", text: "Cannot reach server — is run_server.bat running?" });
    }

    // 2. Last logs
    try {
      const logsData = await api("GET", "/logs");
      const lines = (logsData.lines || []).slice(-8);
      if (lines.length) {
        items.push({ cls: "head", icon: "📜", text: "Last log output" });
        lines.forEach(l => items.push({ cls: "log", icon: "", text: l || " " }));
      }
    } catch (_) {}

    resultsEl.innerHTML = items.map(it =>
      `<div class="__dv_diag_item__ ${it.cls}">
        <span style="flex-shrink:0">${it.icon}</span>
        <span>${it.text}</span>
       </div>`
    ).join("");
  }

  function showToast(msg, isError = false) {
    const existing = document.querySelector(".__dv_toast__");
    if (existing) existing.remove();
    const toast = document.createElement("div");
    toast.className = "__dv_toast__";
    toast.style.borderColor = isError ? "rgba(239,68,68,0.3)" : "rgba(255,255,255,0.1)";
    toast.style.color = isError ? "#f87171" : "#e2e8f0";
    toast.textContent = msg;
    root.appendChild(toast);
    setTimeout(() => toast.remove(), 3100);
  }

  function api(method, endpoint, body) {
    return new Promise((resolve, reject) => {
      chrome.runtime.sendMessage(
        { type: "API_CALL", method, endpoint, body },
        (resp) => {
          if (chrome.runtime.lastError) return reject(new Error(chrome.runtime.lastError.message));
          if (!resp) return reject(new Error("No response from extension"));
          if (!resp.ok) return reject(new Error(resp.error || "Request failed"));
          resolve(resp.data);
        }
      );
    });
  }

  // ── State update ──────────────────────────────────────────────────────────────
  let _pollTimer = null;

  function updateUI(data) {
    const status = data.status || "IDLE";

    // Badge
    const badge = $("__dv_badge__");
    badge.className = `__dv_badge__ ${status}`;
    const dot = badge.querySelector(".__dv_dot__");
    dot.className = `__dv_dot__ ${status === "RUNNING" ? "RUNNING" : ""}`;
    badge.textContent = "";
    badge.appendChild(dot);
    badge.append(status);

    // FAB pulse
    if (status === "RUNNING") fab.classList.add("running");
    else fab.classList.remove("running");

    // Progress
    const pct = data.progress_pct || 0;
    $("__dv_prog_fill__").style.width = `${pct}%`;
    $("__dv_prog_fill__").className = `__dv_progress_fill__ ${status === "RUNNING" ? "running" : ""}`;
    $("__dv_prog_pct__").textContent = `${pct}%`;

    if (data.total > 0) {
      $("__dv_prog_text__").textContent =
        status === "COMPLETE"
          ? "Validation complete ✓"
          : `Document ${data.completed} of ${data.total}`;
    } else {
      $("__dv_prog_text__").textContent =
        status === "IDLE" ? "Ready to validate" : "Initialising…";
    }

    // Stats
    $("__dv_s_docs__").textContent    = data.completed ?? "—";
    $("__dv_s_fields__").textContent  = data.fields_validated ?? "—";
    $("__dv_s_match__").textContent   = data.matches ?? "—";
    $("__dv_s_mismatch__").textContent= data.mismatches ?? "—";

    // Buttons
    const running  = status === "RUNNING";
    const stopped  = status === "STOPPED";
    const errored  = status === "ERROR";

    $("__dv_btn_start__").disabled  = running;
    $("__dv_btn_stop__").disabled   = !running;
    $("__dv_btn_resume__").disabled = !stopped;

    // Log / diagnostic line
    const logEl = $("__dv_log__");
    if (logEl) {
      const lastLog = data.last_log || "";
      if (errored) {
        logEl.className = "__dv_log__ error";
        logEl.textContent = lastLog || `Process exited with code ${data.exit_code}. Check config.yaml selectors.`;
      } else if (status === "COMPLETE") {
        logEl.className = "__dv_log__ ok";
        logEl.textContent = "✓ All documents validated — see reports/ for results";
      } else if (lastLog) {
        logEl.className = `__dv_log__ ${status === "RUNNING" ? "" : ""}`;
        logEl.textContent = lastLog;
      }
      if (status === "IDLE") {
        logEl.className = "__dv_log__";
        logEl.textContent = "Click ▶ Start to begin validation";
      }
    }

    // Auto-open diagnose panel when an error occurs
    if (errored && !_diagOpen) {
      runDiagnose();
    }
  }

  async function pollStatus() {
    try {
      const data = await api("GET", "/status");
      updateUI(data);
      if (data.status === "RUNNING") {
        _pollTimer = setTimeout(pollStatus, 1500);  // poll every 1.5s while running
      } else if (data.status === "ERROR") {
        _pollTimer = setTimeout(pollStatus, 3000);  // keep checking on error
      } else {
        _pollTimer = null;
      }
    } catch (err) {
      // Server offline
      const logEl = $("__dv_log__");
      if (logEl) {
        logEl.className = "__dv_log__ warn";
        logEl.textContent = "⚠ Server offline — double-click run_server.bat";
      }
      updateUI({ status: "IDLE" });
    }
  }

  function startPolling() {
    if (_pollTimer) return;
    pollStatus();
  }

  async function extractLiveDOMSections() {
    const sections = {};
    const clean = (t) => t ? t.replace(/\s+/g, ' ').trim() : '';

    const cmpTables = document.querySelectorAll("table.cmp-table");
    if (cmpTables.length > 0) {
      for (const table of cmpTables) {
        const tbodies = table.querySelectorAll("tbody");
        for (const tbody of tbodies) {
          if (tbody.classList.contains("cmp-section-group")) {
            const secRow = tbody.querySelector(".cmp-sec-row");
            const secTextEl = tbody.querySelector(".cmp-sec-text");
            const secName = secTextEl ? clean(secTextEl.innerText) : "";
            
            if (secRow && !secRow.classList.contains("cmp-sec-open")) {
              secRow.click();
              await new Promise(r => setTimeout(r, 400)); // wait for angular to render
            }
            
            const contentEl = tbody.querySelector(".cmp-content-inner, .cmp-content-cell");
            if (contentEl && secName) {
                const innerTables = contentEl.querySelectorAll("table");
                let hasTable = innerTables.length > 0;
                if (hasTable) {
                    let cIdx = 1;
                    innerTables.forEach(tbl => {
                        tbl.querySelectorAll("td, th, .cmp-td, .cmp-th").forEach(cell => {
                            let cVal = clean(cell.innerText);
                            if (cVal) sections[`${secName} > Table Cell ${cIdx++}`] = cVal;
                        });
                    });
                }
                
                const inputs = contentEl.querySelectorAll("input, select, textarea, mat-select, .mat-select-value");
                let iIdx = 1;
                inputs.forEach(inp => {
                    let val = "";
                    if (inp.tagName === "SELECT") {
                        if (inp.selectedIndex >= 0) val = inp.options[inp.selectedIndex].text;
                    } else if (inp.tagName === "INPUT" || inp.tagName === "TEXTAREA") {
                        val = inp.value;
                    } else {
                        val = inp.innerText;
                    }
                    val = clean(val);
                    if (val) sections[`${secName} > Dropdown/Input ${iIdx++}`] = val;
                });
                
                if (!hasTable) {
                    const textContent = clean(contentEl.innerText);
                    if (textContent) sections[`${secName} > Content`] = textContent;
                }
            }
          } else {
             tbody.querySelectorAll("tr").forEach(row => {
                 const labelEl = row.querySelector(".cmp-td-label");
                 const valEl = row.querySelector(".cmp-td-value");
                 if (labelEl && valEl) {
                     const k = clean(labelEl.innerText);
                     const v = clean(valEl.innerText);
                     if (k && v) sections[`Overview > ${k}`] = v;
                 }
             });
          }
        }
      }
      if (Object.keys(sections).length > 0) return sections;
    }

    function extractPairsFromNode(rootNode) {
      const rows = rootNode.querySelectorAll("tr, [class*='row'], [class*='grid'], [class*='item'], [class*='flex']");
      rows.forEach(row => {
        if (row.querySelector("tr, [class*='row'], [class*='grid'], [class*='item'], [class*='flex']")) return;
        const walker = document.createTreeWalker(row, NodeFilter.SHOW_TEXT, null, false);
        const texts = [];
        let node;
        while(node = walker.nextNode()) {
          const t = node.nodeValue.trim();
          if(t) texts.push(t);
        }
        if(texts.length >= 2) {
          const k = clean(texts[0]).replace(/:\s*$/, '');
          const v = clean(texts.slice(1).join(" "));
          if(k && v && k.length <= 150 && k.toLowerCase() !== v.toLowerCase()) {
            sections[`UI Field > ${k}`] = v;
          }
        }
      });
    }

    const appComp = document.querySelector("app-comparison");
    if (appComp) {
      extractPairsFromNode(appComp.shadowRoot || appComp);
    } else {
      extractPairsFromNode(document.body);
    }

    document.querySelectorAll("table").forEach(tbl => {
      tbl.querySelectorAll("tr").forEach(row => {
        const cells = row.querySelectorAll("td, th");
        if (cells.length >= 2) {
          const k = clean(cells[0].innerText);
          const v = clean(cells[1].innerText);
          if (k && v && k.length <= 150) {
            sections[`Table > ${k}`] = v;
          }
        }
      });
    });

    return sections;
  }

  // ── Button handlers ────────────────────────────────────────────────────────────
  $('__dv_btn_start__').addEventListener('click', async () => {
    try {
      $('__dv_btn_start__').disabled = true;
      const logEl = $("__dv_log__");
      if (logEl) { logEl.className = "__dv_log__"; logEl.textContent = "Extracting page content…"; }

      // 1. Extract live DOM sections directly from active tab
      const uiData = await extractLiveDOMSections();

      let manualPdfPath = "";
      const fileInput = $("__dv_manual_file__");
      if (fileInput && fileInput.files && fileInput.files[0]) {
        if (logEl) { logEl.textContent = "Uploading manual PDF…"; }
        const formData = new FormData();
        formData.append("file", fileInput.files[0]);
        const uploadRes = await fetch("http://localhost:8765/upload-pdf", {
          method: "POST",
          body: formData,
        });
        const uploadData = await uploadRes.json();
        if (uploadData.ok) {
          manualPdfPath = uploadData.path;
        }
      }

      if (logEl) { logEl.textContent = "Comparing UI ↔ PDF data…"; }

      // 2. Validate extracted DOM sections directly against PDF
      const res = await api('POST', '/validate-dom', {
        url: window.location.href,
        ui_data: uiData,
        manual_pdf: manualPdfPath
      });

      updateUI(res);
      showToast('✅ Validation complete — reports ready for download!');
    } catch (err) {
      const msg = err.message || "";
      const logEl = $("__dv_log__");
      if (logEl) {
        logEl.className = "__dv_log__ error";
        logEl.textContent = msg;
      }
      showToast(`❌ ${msg.split('\n')[0]}`, true);
      $('__dv_btn_start__').disabled = false;
    }
  });

  $('__dv_btn_stop__').addEventListener('click', async () => {
    try {
      $('__dv_btn_stop__').disabled = true;
      await api('POST', '/stop');
      showToast('⏹ Validation stopped');
      clearTimeout(_pollTimer);
      _pollTimer = null;
      await pollStatus();
    } catch (err) {
      showToast(`❌ ${err.message}`, true);
      $('__dv_btn_stop__').disabled = false;
    }
  });

  $('__dv_btn_resume__').addEventListener('click', async () => {
    try {
      $('__dv_btn_resume__').disabled = true;
      const res = await api('POST', '/resume', { url: window.location.href });
      showToast('⏩ Validation resumed on this page');
      startPolling();
    } catch (err) {
      showToast(`❌ ${err.message}`, true);
      await pollStatus();
    }
  });

  // ── FAB toggle ────────────────────────────────────────────────────────────────
  fab.addEventListener("click", () => {
    const isOpen = panel.classList.toggle("visible");
    if (isOpen) {
      // Reset diagnostic state on open
      if (_diagOpen) {
        _diagOpen = false;
        $("__dv_diag_results__").classList.remove("open");
        $("__dv_diag_btn__").textContent = "⚙ Diagnose — show config & log details";
      }
      // Refresh status every time panel opens
      pollStatus();
    }
  });

  // Diagnose button
  document.addEventListener("click", (e) => {
    if (e.target && e.target.id === "__dv_diag_btn__") {
      runDiagnose();
    }
  });

  // Close panel when clicking outside
  document.addEventListener("click", (e) => {
    if (!root.contains(e.target)) {
      panel.classList.remove("visible");
    }
  });

  // ── Initial status check ──────────────────────────────────────────────────────
  // Silent check on page load — if validation was running, resume polling
  api("GET", "/status")
    .then((data) => {
      if (data.status === "RUNNING") {
        fab.classList.add("running");
        startPolling();
      }
    })
    .catch(() => {}); // server not running yet — that's fine

})();
