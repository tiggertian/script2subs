"use strict";

/* ScriptAlign UI — no framework, no build step. */

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const TOKEN = window.SCRIPTALIGN_TOKEN;

const ui = {
  data: null,
  step: 1,
  filter: "all",
  query: "",
  browse: { kind: "media", target: "audio", folder: false, path: "" },
  jobTimer: null,
  playerKey: null,
  player: null,
  cues: [],
  active: -1,
  wave: null,
  waveDrawn: 0,
  exported: [],
  reflow: null,
};

/* --------------------------------------------------------------- utilities */

async function api(path, { method = "GET", body = null } = {}) {
  const opts = { method, headers: {} };
  if (method !== "GET") {
    opts.headers["Content-Type"] = "application/json";
    opts.headers["X-ScriptAlign-Token"] = TOKEN;
  }
  if (body !== null) opts.body = JSON.stringify(body);
  const res = await fetch(path, opts);
  let data = {};
  try { data = await res.json(); } catch (err) { /* empty body */ }
  if (!res.ok) throw new Error(data.error || `${res.status} ${res.statusText}`);
  return data;
}

let toastTimer = null;
function toast(message, kind = "") {
  const el = $("#toast");
  el.textContent = message;
  el.className = "toast show" + (kind ? " " + kind : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.className = "toast " + kind; }, 3400);
}

function clock(t) {
  if (t === null || t === undefined || !isFinite(t)) return "—";
  const m = Math.floor(t / 60);
  const s = t - m * 60;
  return `${String(m).padStart(2, "0")}:${s.toFixed(2).padStart(5, "0")}`;
}

function humanBytes(n) {
  if (!n && n !== 0) return "";
  const units = ["B", "KB", "MB", "GB"];
  let i = 0, v = n;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(i ? 1 : 0)} ${units[i]}`;
}

function basenameNoExt(path) {
  if (!path) return "";
  const name = path.split(/[\\/]/).pop();
  return name.replace(/\.[^.]+$/, "");
}

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}

/* ------------------------------------------------------------------- steps */

function setStep(n) {
  const num = Math.max(1, Math.min(4, Number(n) || 1));
  ui.step = num;
  $$("#stepper .step").forEach((b) => {
    const s = Number(b.dataset.step);
    b.classList.toggle("active", s === num);
    b.classList.toggle("done", s < num);
  });
  $$("[data-panel]").forEach((p) => {
    p.classList.toggle("active", Number(p.dataset.panel) === num);
  });
  window.scrollTo({ top: 0, behavior: "smooth" });
  if (num === 3) {
    setupPlayer();
    applyCueFilter();
  }
  if (num === 4) renderExport(ui.data);
}

/* ------------------------------------------------------------------ render */

function render(data) {
  if (data) ui.data = data;
  const d = ui.data;
  if (!d) return;
  if (!d.result) ui.exported = [];

  const engine = d.engine || {};
  const badge = $("#engine-badge");
  if (engine.autosubs) {
    badge.textContent = "AutoSubs " + (engine.autosubs.includes("/") ? "found" : "ready");
    badge.className = "badge ok";
    badge.title = engine.autosubs;
  } else {
    badge.textContent = "AutoSubs not on PATH";
    badge.className = "badge warn";
    badge.title = "Install AutoSubs to transcribe inside ScriptAlign";
  }
  $("#version-badge").textContent = "v" + d.version;
  $("#footer-version").textContent = "ScriptAlign " + d.version;

  bindValue("#audio-path", d.paths.audio);
  bindValue("#timings-path", d.paths.timings);
  bindValue("#primary-path", d.paths.primary);
  bindValue("#secondary-path", d.paths.secondary);
  bindValue("#outdir-path", d.outdir);

  const opts = d.options || {};
  bindValue("#opt-offset", opts.offset);
  bindValue("#opt-min-dur", opts.min_dur);
  bindValue("#opt-gap", opts.gap);
  bindValue("#opt-hold", opts.hold);
  bindValue("#opt-linger", opts.linger);
  bindValue("#reflow-max-primary", opts.max_primary);
  bindValue("#reflow-max-secondary", opts.max_secondary);
  bindValue("#reflow-min-len", opts.min_len);

  renderSource(d);
  renderScripts(d);
  renderJob(d.job);
  renderResult(d.result);
  renderExport(d);
  updateTranscribeButton();
}

function bindValue(sel, value) {
  const input = $(sel);
  if (!input) return;
  if (document.activeElement === input) return;
  const text = value === null || value === undefined ? "" : String(value);
  if (input.value !== text) input.value = text;
}

function renderSource(d) {
  const audio = d.files.audio;
  const kind = $("#audio-kind");
  if (audio) {
    kind.textContent = audio.kind === "video" ? "video" : "audio";
    kind.className = "pill ok";
    $("#audio-meta").textContent =
      `${audio.name} · ${humanBytes(audio.size)}` +
      (audio.kind ? "" : " · preview may be unsupported");
  } else {
    kind.textContent = d.paths.audio ? "missing" : "none";
    kind.className = "pill" + (d.paths.audio ? " bad" : "");
    $("#audio-meta").textContent = d.paths.audio
      ? "That audio file is no longer there."
      : "No file selected.";
  }

  const timings = d.files.timings;
  const tstate = $("#timings-state");
  if (timings) {
    tstate.textContent = "ready";
    tstate.className = "pill ok";
    $("#timings-meta").textContent = `${timings.name} · ${humanBytes(timings.bytes)}`;
  } else {
    tstate.textContent = d.paths.timings ? "missing" : "none";
    tstate.className = "pill" + (d.paths.timings ? " bad" : "");
    $("#timings-meta").textContent = d.paths.timings
      ? "Timings file not found. Re-transcribe or choose another file."
      : "No timings yet. Transcribe below, or reuse an existing JSON.";
  }

  const as = $("#autosubs-state");
  if (d.engine.autosubs) {
    as.textContent = "installed";
    as.className = "pill ok";
  } else {
    as.textContent = "not found";
    as.className = "pill warn";
  }

  const foot = $("#source-foot");
  if (d.paths.audio) {
    foot.textContent = "AutoSubs writes the JSON next to the media by default.";
  } else {
    foot.textContent = "Tip: pick the take first, then transcribe — it is the slow step.";
  }
}

function renderScripts(d) {
  const p = d.files.primary;
  const s = d.files.secondary;
  const pPill = $("#primary-lines");
  const sPill = $("#secondary-lines");

  if (p) {
    pPill.textContent = `${p.lines} lines`;
    pPill.className = "pill ok";
    $("#primary-meta").textContent = `${p.name} · ${humanBytes(p.bytes)} · ` +
      (p.cjk ? "CJK (no word spaces)" : "space-delimited words");
  } else {
    pPill.textContent = "—";
    pPill.className = "pill";
    $("#primary-meta").textContent = d.paths.primary
      ? "Script not found." : "No script selected.";
  }
  if (s) {
    sPill.textContent = `${s.lines} lines`;
    sPill.className = "pill ok";
    $("#secondary-meta").textContent = `${s.name} · ${humanBytes(s.bytes)} · ` +
      (s.cjk ? "CJK (no word spaces)" : "space-delimited words");
  } else {
    sPill.textContent = "—";
    sPill.className = "pill";
    $("#secondary-meta").textContent = d.paths.secondary
      ? "Script not found." : "No script selected.";
  }

  const status = $("#pair-status");
  status.className = "pair-status";
  if (!p && !s) {
    status.textContent = "Choose both scripts to check the 1:1 pairing.";
  } else if (!p || !s) {
    status.textContent = "Choose the other script to check the pairing.";
  } else if (p.lines === s.lines) {
    status.classList.add("ok");
    status.textContent = `${p.lines} ↔ ${s.lines} lines · 1:1 pair. ` +
      "Every cue will carry one line from each script.";
  } else {
    status.classList.add("bad");
    status.textContent = `Line counts differ: ${p.lines} vs ${s.lines}. ` +
      "The scripts must be a 1:1 pair before aligning.";
  }
}

function renderJob(job) {
  const log = $("#job-log");
  if (!job || (!job.running && (!job.lines || !job.lines.length))) {
    log.hidden = true;
    return;
  }
  log.hidden = false;
  const state = $("#job-state");
  if (job.running) {
    state.textContent = "running…";
    state.className = "pill";
  } else if (job.exit_code === 0) {
    state.textContent = "done";
    state.className = "pill ok";
  } else {
    state.textContent = "exit " + job.exit_code;
    state.className = "pill bad";
  }
  const pre = $("#job-log-lines");
  const text = (job.lines || []).join("\n");
  pre.textContent = text;
  pre.scrollTop = pre.scrollHeight;
  if (job.json_ready && !$("#timings-path").value) {
    bindValue("#timings-path", job.json_path);
  }
}

function updateTranscribeButton() {
  const d = ui.data;
  const btn = $("#transcribe-btn");
  if (!d) return;
  const running = d.job && d.job.running;
  const ready = Boolean(d.engine.autosubs) && Boolean(d.files.audio);
  btn.disabled = running || !ready;
  btn.textContent = running ? "Transcribing…" : "Transcribe";
}

/* -------------------------------------------------------------- diagnostics */

function renderResult(result) {
  ui.cues = result ? result.cues : [];
  const pill = $("#align-state");
  if (result) {
    pill.textContent = `${result.summary.cues} cues`;
    pill.className = "pill ok";
  } else {
    pill.textContent = "not run";
    pill.className = "pill";
  }
  renderDiagnostics(result);
  renderCues();
  updateStale();
  if (result) setupPlayer();
}

function stat(label, value, kind = "") {
  const box = el("div", "stat" + (kind ? " " + kind : ""));
  box.append(el("div", "v", String(value)), el("div", "k", label));
  return box;
}

function renderDiagnostics(result) {
  const wrap = $("#diagnostics");
  wrap.replaceChildren();
  if (!result) {
    wrap.append(el("p", "meta", "Align to see diagnostics."));
    return;
  }
  const s = result.summary;
  const counts = s.counts || {};
  const grid = el("div", "stat-grid");
  grid.append(
    stat("Cues", s.cues),
    stat("Matched", s.match_pct + "%", s.match_pct >= 85 ? "good" : "warn"),
    stat("Too fast", counts["reading-speed"] || 0,
         counts["reading-speed"] ? "warn" : ""),
    stat("Over limit", counts["over-limit"] || 0,
         counts["over-limit"] ? "warn" : ""),
  );
  wrap.append(grid);

  const meta = el("p", "meta",
    `${s.transcript_kind === "word" ? "Word-level" : "Segment-level"} AutoSubs ` +
    `timings · ${s.script_tokens} script words · ${s.pauses_bridged} pauses bridged`);
  wrap.append(meta);

  if (s.warnings && s.warnings.length) {
    const list = el("div", "warnings");
    s.warnings.forEach((w) => list.append(el("div", "warning-item", w.text)));
    wrap.append(list);
  }
}

function updateStale() {
  const d = ui.data;
  const banner = $("#stale-banner");
  if (!d || !d.result) { banner.hidden = true; return; }
  const used = d.result.options || {};
  const now = d.options || {};
  const keys = ["offset", "min_dur", "gap", "hold", "linger",
                "max_primary", "max_secondary"];
  const dirty = keys.some((k) => Number(used[k]) !== Number(now[k]));
  banner.hidden = !dirty;
}

/* ------------------------------------------------------------------- cues */

function cueMatches(cue) {
  if (ui.filter !== "all") {
    if (ui.filter === "flagged") {
      if (!cue.flags.length) return false;
    } else if (!cue.flags.some((f) => f.code === ui.filter)) {
      return false;
    }
  }
  if (ui.query) {
    const q = ui.query.toLowerCase();
    if (!cue.primary.toLowerCase().includes(q) &&
        !cue.secondary.toLowerCase().includes(q)) return false;
  }
  return true;
}

function renderCues() {
  const body = $("#cue-body");
  body.replaceChildren();
  const list = ui.cues.filter(cueMatches);

  list.forEach((cue) => {
    const tr = document.createElement("tr");
    tr.dataset.n = cue.n;
    if (ui.active === cue.n) tr.classList.add("active");
    if (cue.flags.length) tr.classList.add("has-flags");

    tr.append(
      el("td", "c-num", cue.n),
      el("td", "c-time", clock(cue.start)),
      el("td", "c-time", clock(cue.end)),
      el("td", "c-dur", cue.dur.toFixed(2)),
      el("td", "primary-text", cue.primary),
      el("td", "secondary-text", cue.secondary),
    );

    const flags = el("td", "c-flags");
    cue.flags.forEach((f) => {
      const badge = el("span", "flag " + f.code,
        `${f.track === "secondary" ? "2nd " : ""}${f.label}`);
      badge.title = f.code + (f.track ? " (" + f.track + ")" : "");
      flags.append(badge);
    });
    if (cue.cps != null) {
      tr.title = `${cue.cps} chars/sec (${cue.dur.toFixed(2)}s)`;
    }
    tr.append(flags);
    tr.addEventListener("click", () => seekToCue(cue));
    body.append(tr);
  });

  $("#table-empty").hidden = list.length > 0;
  $("#table-empty").textContent = ui.cues.length
    ? "No cue matches this filter."
    : "Run the alignment to list cues.";
  $("#cue-count").textContent = ui.cues.length
    ? `${list.length} / ${ui.cues.length} cues`
    : "0 cues";
}

function applyCueFilter() {
  ui.query = $("#cue-search").value.trim();
  ui.filter = $("#cue-filter").value;
  renderCues();
}

function seekToCue(cue) {
  const player = $("#player");
  setActiveCue(cue, true);
  if (player) {
    try {
      player.currentTime = Math.max(0, cue.start + 0.01);
      player.play().catch(() => {});
    } catch (err) { /* ignore */ }
  }
}

function setActiveCue(cue, scroll = false) {
  if (ui.active === cue.n) return;
  ui.active = cue.n;
  $$("#cue-body tr").forEach((tr) => {
    tr.classList.toggle("active", Number(tr.dataset.n) === cue.n);
  });
  const overlay = $("#player-cue");
  overlay.classList.remove("empty");
  overlay.replaceChildren(
    el("span", "primary", cue.primary),
    el("span", "second", cue.secondary),
  );
  if (scroll) {
    const row = $(`#cue-body tr[data-n="${cue.n}"]`);
    if (row) row.scrollIntoView({ block: "nearest" });
  }
}

function clearActiveCue() {
  ui.active = -1;
  $$("#cue-body tr.active").forEach((tr) => tr.classList.remove("active"));
  const overlay = $("#player-cue");
  overlay.classList.add("empty");
  overlay.textContent = "No cue at this point in the take.";
}

function updateActiveCue(time) {
  let found = null;
  for (const cue of ui.cues) {
    if (time >= cue.start && time < cue.end) { found = cue; break; }
    if (cue.start > time) break;
  }
  if (found) setActiveCue(found);
  else if (ui.active !== -1) clearActiveCue();
}

/* ----------------------------------------------------------------- player */

function setupPlayer() {
  const d = ui.data;
  const wrap = $("#player-wrap");
  const media = d && d.files.audio;
  if (!media) {
    if (ui.playerKey !== null) {
      ui.playerKey = null;
      ui.player = null;
      wrap.replaceChildren(el("div", "player-empty",
        "Choose the narration in Step 1 to preview it here."));
      $("#wave-wrap").hidden = true;
      clearActiveCue();
    }
    return;
  }
  const key = media.path + ":" + media.mtime;
  if (ui.playerKey === key && $("#player")) return;
  ui.playerKey = key;
  wrap.replaceChildren();
  const tag = media.kind === "video" ? "video" : "audio";
  const player = document.createElement(tag);
  player.id = "player";
  player.controls = true;
  player.preload = "metadata";
  player.src = "/api/media?file=audio&v=" + encodeURIComponent(media.mtime);
  wrap.append(player);
  ui.player = player;
  player.addEventListener("timeupdate", onTime);
  player.addEventListener("loadedmetadata", onTime);
  player.addEventListener("play", onTime);
  setupWave(media, player);
  clearActiveCue();
}

let lastWaveDraw = 0;
function onTime() {
  const player = $("#player");
  if (!player) return;
  if (ui.wave) {
    const now = performance.now();
    if (now - lastWaveDraw > 100) {
      lastWaveDraw = now;
      drawWave(player.currentTime / Math.max(ui.wave.duration, 0.001));
    }
  }
  updateActiveCue(player.currentTime);
}

async function setupWave(media, player) {
  const wrap = $("#wave-wrap");
  const canvas = $("#waveform");
  ui.wave = null;
  canvas.onclick = null;
  if (media.kind !== "audio" || media.size > 90 * 1024 * 1024) {
    wrap.hidden = true;
    return;
  }
  wrap.hidden = false;
  try {
    const res = await fetch("/api/media?file=audio&v=" + encodeURIComponent(media.mtime));
    if (!res.ok) throw new Error("media fetch failed");
    const buf = await res.arrayBuffer();
    const Ctx = window.AudioContext || window.webkitAudioContext;
    const ctx = new Ctx();
    const audio = await ctx.decodeAudioData(buf);
    ctx.close();
    const data = audio.getChannelData(0);
    const buckets = 900;
    const step = Math.max(1, Math.floor(data.length / buckets));
    const peaks = [];
    for (let i = 0; i < buckets; i++) {
      let min = 1, max = -1;
      const off = i * step;
      for (let j = 0; j < step; j += 24) {
        const v = data[off + j] || 0;
        if (v < min) min = v;
        if (v > max) max = v;
      }
      peaks.push([min, max]);
    }
    ui.wave = { peaks, duration: audio.duration };
    drawWave(0);
    canvas.onclick = (ev) => {
      const rect = canvas.getBoundingClientRect();
      const ratio = (ev.clientX - rect.left) / rect.width;
      player.currentTime = Math.max(0, Math.min(audio.duration - 0.05,
        ratio * audio.duration));
      player.play().catch(() => {});
    };
  } catch (err) {
    wrap.hidden = true;
  }
}

function drawWave(progress) {
  const canvas = $("#waveform");
  if (!ui.wave || !canvas) return;
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth, h = canvas.clientHeight;
  if (!w || !h) return;
  if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
  }
  const g = canvas.getContext("2d");
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, w, h);
  const peaks = ui.wave.peaks;
  const bw = w / peaks.length;
  for (let i = 0; i < peaks.length; i++) {
    const [min, max] = peaks[i];
    const y1 = (1 - max) * h / 2;
    const y2 = (1 - min) * h / 2;
    g.fillStyle = (i / peaks.length) <= progress ? "#5eead4" : "#31404f";
    g.fillRect(i * bw, y1, Math.max(1, bw - 0.5), Math.max(1, y2 - y1));
  }
  const x = Math.min(w, Math.max(0, progress * w));
  g.fillStyle = "rgba(255,255,255,0.55)";
  g.fillRect(x, 0, 1, h);
}

/* ------------------------------------------------------------------ reflow */

async function previewReflow() {
  const values = reflowValues();
  try {
    await saveOptions({
      max_primary: values.max_primary,
      max_secondary: values.max_secondary,
      min_len: values.min_len,
    }, true);
    const d = await api("/api/reflow", {
      method: "POST",
      body: { dry_run: true, ...values },
    });
    ui.reflow = d.reflow;
    renderReflow(d.reflow);
    render(d.state);
    toast("Break preview ready");
  } catch (err) {
    toast(err.message, "error");
  }
}

async function applyReflow() {
  if (!confirm("Re-flow both scripts in place? Originals are kept as *.orig.txt.")) {
    return;
  }
  const values = reflowValues();
  const btn = $("#apply-btn");
  btn.disabled = true;
  try {
    await saveOptions({
      max_primary: values.max_primary,
      max_secondary: values.max_secondary,
      min_len: values.min_len,
    }, true);
    const d = await api("/api/reflow", {
      method: "POST",
      body: { dry_run: false, ...values },
    });
    render(d.state);
    renderReflow(d.reflow);
    toast("Scripts re-flowed — wording verified unchanged");
  } catch (err) {
    toast(err.message, "error");
  } finally {
    btn.disabled = false;
  }
}

function reflowValues() {
  const num = (sel, fallback) => {
    const v = Number($(sel).value);
    return Number.isFinite(v) ? v : fallback;
  };
  return {
    max_primary: num("#reflow-max-primary", 42),
    max_secondary: num("#reflow-max-secondary", 20),
    min_len: num("#reflow-min-len", 18),
  };
}

function renderReflow(data) {
  if (!data) return;
  const summary = $("#reflow-summary");
  summary.replaceChildren();
  const b = data.before, a = data.after;
  const sb = data.secondary_before, sa = data.secondary_after;
  const chip = (label, before, after, unit = "") => {
    const box = el("div", "chip");
    box.append(el("span", "", label), el("b", "", `${before}${unit}`));
    if (before !== after) {
      box.append(el("span", "delta", `→ ${after}${unit}`));
    }
    return box;
  };
  summary.append(
    chip("Primary lines", b.lines, a.lines),
    chip("Over max", b.over_max, a.over_max),
    chip("Dangling", b.dangling, a.dangling),
    chip("Second lines", sb.lines, sa.lines),
    chip("Second over max", sb.over_max, sa.over_max),
  );

  const diff = $("#reflow-diff");
  diff.replaceChildren();
  diff.append(
    diffColumn("Before", data.primary.before, 120),
    diffColumn("After", data.primary.after, 120, data.primary.before),
  );
}

function diffColumn(title, lines, limit, compareWith) {
  const col = el("div", "reflow-col");
  col.append(el("h4", "", `${title} · ${lines.length} lines`));
  const body = el("div", "reflow-lines");
  lines.slice(0, limit).forEach((line, i) => {
    const row = el("div", "reflow-line");
    const changed = compareWith && compareWith[i] !== line;
    if (changed) row.classList.add("changed");
    row.append(el("span", "", String(i + 1)), el("span", "", line));
    body.append(row);
  });
  if (lines.length > limit) {
    body.append(el("div", "reflow-line",
      `${lines.length - limit} more line(s) not shown`));
  }
  col.append(body);
  return col;
}

/* ------------------------------------------------------------------- jobs */

function pollJob() {
  clearInterval(ui.jobTimer);
  const tick = async () => {
    try {
      const d = await api("/api/job");
      renderJob(d);
      if (d.state) {
        ui.data.paths = d.state.paths;
        ui.data.files = d.state.files;
        ui.data.job = d.state.job;
        renderSource(ui.data);
        renderScripts(ui.data);
        updateTranscribeButton();
      }
      if (!d.running) {
        clearInterval(ui.jobTimer);
        ui.jobTimer = null;
        const state = await api("/api/state");
        render(state);
        if (d.exit_code === 0) toast("Transcription finished");
        else toast("AutoSubs failed — see the log", "error");
      }
    } catch (err) {
      clearInterval(ui.jobTimer);
      ui.jobTimer = null;
      toast(err.message, "error");
    }
  };
  ui.jobTimer = setInterval(tick, 900);
  tick();
}

async function transcribe() {
  const btn = $("#transcribe-btn");
  btn.disabled = true;
  try {
    const body = {
      model: $("#model").value,
      lang: $("#lang").value.trim(),
      forced_alignment: $("#forced").checked,
    };
    const d = await api("/api/transcribe", { method: "POST", body });
    render(d.state);
    renderJob(d.job);
    pollJob();
  } catch (err) {
    toast(err.message, "error");
  } finally {
    updateTranscribeButton();
  }
}

/* ---------------------------------------------------------------- alignment */

async function runAlign() {
  const btn = $("#align-btn");
  btn.disabled = true;
  btn.textContent = "Aligning…";
  try {
    const d = await api("/api/align", { method: "POST" });
    render(d.state);
    if (d.result) {
      setStep(3);
      toast(`Aligned ${d.result.summary.cues} cues`);
    }
  } catch (err) {
    toast(err.message, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Run alignment";
  }
}

async function saveOptions(patch, silent) {
  try {
    const d = await api("/api/state", { method: "POST", body: { options: patch } });
    ui.data.options = d.options;
    ui.data.result = d.result;
    updateStale();
    if (!silent) toast("Settings saved");
    return d;
  } catch (err) {
    toast(err.message, "error");
    throw err;
  }
}

/* ------------------------------------------------------------------- paths */

async function setPath(key, value) {
  try {
    const d = await api("/api/state", { method: "POST", body: { paths: { [key]: value } } });
    render(d);
    toast("Selected " + basenameNoExt(value) + " for " + key);
  } catch (err) {
    toast(err.message, "error");
    const d = await api("/api/state");
    render(d);
  }
}

async function chooseFolder(path) {
  try {
    const d = await api("/api/state", { method: "POST", body: { outdir: path } });
    render(d);
    $("#browser-dialog").close();
    toast("Output folder set");
  } catch (err) {
    toast(err.message, "error");
  }
}

/* ------------------------------------------------------------------ export */

function renderExport(d) {
  if (!d) return;
  const out = $("#outdir-path");
  if (document.activeElement !== out) out.value = d.outdir || "";

  const list = $("#export-files");
  list.replaceChildren();
  const files = ui.exported.length ? ui.exported : expectedFiles(d);
  files.forEach((item) => {
    const path = typeof item === "string" ? item : item.path;
    const name = typeof item === "string" ? item.split(/[\\/]/).pop() : item.name;
    const li = el("li", ui.exported.length ? "" : "muted");
    li.append(el("span", "", name));
    if (ui.exported.length) {
      const btn = el("button", "btn ghost small reveal", "Reveal");
      btn.addEventListener("click", () => reveal(path));
      li.append(btn);
    } else {
      li.append(el("span", "size", "not written"));
    }
    list.append(li);
  });
  const meta = $("#export-meta");
  if (ui.exported.length) {
    meta.textContent = `Wrote ${ui.exported.length} files to ${d.outdir}`;
  } else if (d.result) {
    meta.textContent = "Ready to export. Bilingual SRT is what you burn in.";
  } else {
    meta.textContent = "Run the alignment first, then export.";
  }
  $("#export-btn").disabled = !d.result;
}

function expectedFiles(d) {
  const names = [];
  if (d.paths.primary) names.push(basenameNoExt(d.paths.primary) + ".srt");
  if (d.paths.secondary) names.push(basenameNoExt(d.paths.secondary) + ".srt");
  names.push("bilingual.srt", "timing_report.csv");
  return names;
}

async function exportFiles() {
  const btn = $("#export-btn");
  btn.disabled = true;
  try {
    const d = await api("/api/export", {
      method: "POST",
      body: { outdir: $("#outdir-path").value.trim() },
    });
    ui.exported = d.files;
    render(d.state);
    toast("Exported " + d.files.length + " files");
  } catch (err) {
    toast(err.message, "error");
  } finally {
    btn.disabled = false;
  }
}

async function reveal(path) {
  try {
    await api("/api/reveal", { method: "POST", body: { path } });
  } catch (err) {
    toast(err.message, "error");
  }
}

/* ----------------------------------------------------------------- browser */

function startPathFor(target) {
  const d = ui.data;
  if (!d) return "";
  if (target === "outdir") return d.outdir || "";
  const path = d.paths[target];
  if (path) return path;
  return d.outdir || "";
}

async function openBrowser(kind, target, folder = false) {
  ui.browse = { kind, target, folder, path: "" };
  const titles = {
    media: "Choose narration audio or video",
    json: "Choose AutoSubs JSON or SRT",
    script: "Choose a script",
  };
  $("#browse-title").textContent = folder ? "Choose a folder" : titles[kind] || "Choose a file";
  $("#browse-pick-folder").hidden = !folder;
  $("#browser-dialog").showModal();
  try {
    await loadBrowse(startPathFor(target));
  } catch (err) {
    toast(err.message, "error");
  }
}

async function loadBrowse(path) {
  const { kind } = ui.browse;
  const d = await api(`/api/browse?path=${encodeURIComponent(path || "")}&kind=${encodeURIComponent(kind)}`);
  ui.browse.path = d.path;
  ui.browse.parent = d.parent;
  $("#browse-path").textContent = d.path;
  const list = $("#browse-list");
  list.replaceChildren();

  const dirs = d.dirs || [];
  const files = d.files || [];
  if (dirs.length) {
    list.append(el("div", "browse-sep", "Folders"));
    dirs.forEach((dir) => {
      const row = el("div", "browse-row dir");
      row.append(el("span", "ico", "▸"), el("span", "name", dir.name));
      row.addEventListener("click", () => loadBrowse(dir.path));
      list.append(row);
    });
  }
  if (!ui.browse.folder && files.length) {
    list.append(el("div", "browse-sep", "Files"));
    files.forEach((file) => {
      const row = el("div", "browse-row");
      row.append(
        el("span", "ico", "•"),
        el("span", "name", file.name),
        el("span", "size", humanBytes(file.size)),
      );
      row.addEventListener("click", async () => {
        await setPath(ui.browse.target, file.path);
        $("#browser-dialog").close();
      });
      list.append(row);
    });
  }
  if (!dirs.length && (ui.browse.folder || !files.length)) {
    list.append(el("div", "browse-sep", "Nothing here"));
  }
}

/* ------------------------------------------------------------------ events */

function bindEvents() {
  $$("#stepper .step").forEach((btn) => {
    btn.addEventListener("click", () => setStep(btn.dataset.step));
  });
  $$("[data-next]").forEach((btn) => {
    btn.addEventListener("click", () => setStep(btn.dataset.next));
  });
  $$("[data-back]").forEach((btn) => {
    btn.addEventListener("click", () => setStep(btn.dataset.back));
  });

  const pathMap = {
    "#audio-path": "audio",
    "#timings-path": "timings",
    "#primary-path": "primary",
    "#secondary-path": "secondary",
  };
  Object.entries(pathMap).forEach(([sel, key]) => {
    const input = $(sel);
    input.addEventListener("change", () => {
      if (input.value.trim()) setPath(key, input.value.trim());
    });
    input.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") input.blur();
    });
  });

  $$("[data-browse]").forEach((btn) => {
    btn.addEventListener("click", () => {
      openBrowser(btn.dataset.browse, btn.dataset.target, false);
    });
  });

  const optionMap = {
    "#opt-offset": "offset",
    "#opt-min-dur": "min_dur",
    "#opt-gap": "gap",
    "#opt-hold": "hold",
    "#opt-linger": "linger",
  };
  Object.entries(optionMap).forEach(([sel, key]) => {
    $(sel).addEventListener("change", () => {
      const value = Number($(sel).value);
      if (!Number.isFinite(value)) return toast("Enter a number", "error");
      saveOptions({ [key]: value }, true);
    });
  });

  const reflowMap = {
    "#reflow-max-primary": "max_primary",
    "#reflow-max-secondary": "max_secondary",
    "#reflow-min-len": "min_len",
  };
  Object.entries(reflowMap).forEach(([sel, key]) => {
    $(sel).addEventListener("change", () => {
      const value = Number($(sel).value);
      if (!Number.isFinite(value)) return toast("Enter a number", "error");
      saveOptions({ [key]: value }, true);
    });
  });

  $("#preview-btn").addEventListener("click", previewReflow);
  $("#apply-btn").addEventListener("click", applyReflow);
  $("#transcribe-btn").addEventListener("click", transcribe);
  $("#align-btn").addEventListener("click", runAlign);
  $("#export-btn").addEventListener("click", exportFiles);
  $("#outdir-browse").addEventListener("click", () => {
    openBrowser("media", "outdir", true);
  });

  $("#cue-search").addEventListener("input", applyCueFilter);
  $("#cue-filter").addEventListener("change", applyCueFilter);

  $("#browse-close").addEventListener("click", () => $("#browser-dialog").close());
  $("#browse-up").addEventListener("click", () => {
    loadBrowse(ui.browse.parent || "/").catch((err) => toast(err.message, "error"));
  });
  $("#browse-home").addEventListener("click", () => {
    loadBrowse("~").catch((err) => toast(err.message, "error"));
  });
  $("#browse-pick-folder").addEventListener("click", () => {
    chooseFolder(ui.browse.path);
  });

  $("#help-btn").addEventListener("click", () => $("#help-dialog").showModal());
  $("#help-close").addEventListener("click", () => $("#help-dialog").close());
  $$("dialog").forEach((dialog) => {
    dialog.addEventListener("click", (ev) => {
      if (ev.target === dialog) dialog.close();
    });
  });

  document.addEventListener("keydown", (ev) => {
    if (ev.target.matches("input, select, textarea")) return;
    if (ui.step !== 3) return;
    const player = $("#player");
    if (!player) return;
    if (ev.code === "Space") {
      ev.preventDefault();
      if (player.paused) player.play().catch(() => {});
      else player.pause();
    } else if (ev.key === "ArrowRight" || ev.key === "ArrowDown") {
      ev.preventDefault();
      jumpCue(1);
    } else if (ev.key === "ArrowLeft" || ev.key === "ArrowUp") {
      ev.preventDefault();
      jumpCue(-1);
    }
  });
}

function jumpCue(direction) {
  const list = ui.cues;
  if (!list.length) return;
  let index = list.findIndex((cue) => cue.n === ui.active);
  if (index === -1) {
    const t = ui.player ? ui.player.currentTime : 0;
    index = list.findIndex((cue) => cue.start > t + 0.02);
    if (index === -1) index = list.length - 1;
  } else {
    index = Math.max(0, Math.min(list.length - 1, index + direction));
  }
  seekToCue(list[index]);
}

/* -------------------------------------------------------------------- init */

async function init() {
  bindEvents();
  setStep(1);
  try {
    const d = await api("/api/state");
    render(d);
    if (d.result) setStep(3);
    if (d.job && d.job.running) pollJob();
  } catch (err) {
    toast("Could not reach ScriptAlign: " + err.message, "error");
  }
}

init();
