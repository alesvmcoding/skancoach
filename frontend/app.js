const PAGE_SIZE = 12;
// `EM` only means Monk as an uppercase abbreviation. In Portuguese, `em 2026`
// is a common phrase and must not be parsed as a vocation and level.
const ROLE_RE = "MS|EK|ED|RP|Monk|Mage|Sorcerer|Knight|Druid|Paladin";
const ROLE_FIRST_LEVEL_RE = new RegExp(`\\b(${ROLE_RE})\\s*(\\d{2,4})\\b`, "gi");
const LEVEL_FIRST_ROLE_RE = new RegExp(`\\b(\\d{2,4})\\s*(${ROLE_RE})\\b`, "gi");
const EM_FIRST_LEVEL_RE = /\bEM\s*((?!(?:19|20)\d{2}\b)\d{2,4})\b/g;
const LEVEL_FIRST_EM_RE = /\b((?!(?:19|20)\d{2}\b)\d{2,4})\s*EM\b/g;
const ROLE_ORDER = { MS: 0, MAGE: 0, SORCERER: 0, EK: 1, KNIGHT: 1, ED: 2, DRUID: 2, EM: 3, MONK: 3, RP: 4, PALADIN: 4 };
const ROLE_NAMES = { MS: "Master Sorcerer", EK: "Elite Knight", ED: "Elder Druid", RP: "Royal Paladin", EM: "Monk" };
const MODE_NAMES = { "Team Hunt (PT)": "Team Hunt", Duo: "Duo", Trio: "Trio", Solo: "Solo" };
let catalog = [];
let visibleRows = [];
let displayed = PAGE_SIZE;
let feedbackCounts = {};
let selectedFeedbackVideo = null;

const $ = (selector) => document.querySelector(selector);
const cards = $("#cards");

function parseLevels(title, description = "") {
  const source = `${title || ""}\n${description || ""}`;
  const sourceWithoutEmYears = source.replace(/\bEM\s+20\d{2}\b/gi, " ");
  const bestLevel = new Map();
  const add = (rawVocation, rawLevel) => {
    const alias = rawVocation.toUpperCase();
    const vocation = ({ MAGE: "MS", SORCERER: "MS", KNIGHT: "EK", DRUID: "ED", MONK: "EM", PALADIN: "RP" })[alias] || alias;
    const level = Number(rawLevel);
    if (!bestLevel.has(vocation) || level > bestLevel.get(vocation)) bestLevel.set(vocation, level);
  };
  for (const match of sourceWithoutEmYears.matchAll(ROLE_FIRST_LEVEL_RE)) add(match[1], match[2]);
  for (const match of sourceWithoutEmYears.matchAll(EM_FIRST_LEVEL_RE)) add("EM", match[1]);
  for (const match of sourceWithoutEmYears.matchAll(new RegExp(`\\b(${ROLE_RE})\\s+(?:level|lvl|lv\\.?)\\s*(\\d{2,4})\\b`, "gi"))) add(match[1], match[2]);
  for (const match of sourceWithoutEmYears.matchAll(/\bEM\s+(?:level|lvl|lv\.?)\s*((?!(?:19|20)\d{2}\b)\d{2,4})\b/g)) add("EM", match[1]);
  // Some creators write `940 ED`; prefer this actual role-level pair over a
  // later `ED 10+ Raw`, where 10 is the XP rate rather than the character level.
  for (const match of sourceWithoutEmYears.matchAll(LEVEL_FIRST_ROLE_RE)) add(match[2], match[1]);
  for (const match of sourceWithoutEmYears.matchAll(LEVEL_FIRST_EM_RE)) add("EM", match[1]);
  return [...bestLevel.entries()]
    .sort(([a], [b]) => ROLE_ORDER[a] - ROLE_ORDER[b])
    .map(([vocation, level]) => ({ vocation, level }));
}

const NON_SPECIFIC_HUNT_RE = [
  /\bupei\b.*\b(?:xp|profit|\d+\s*(?:kk|k))\b/i,
  /\bfiz\b.*\b(?:xp|profit)\b.*\b(?:pt|duozinho|dominad|hor[aá]rio)\b/i,
  /\bcomo fazer\b.*\bprofit\b/i,
  /\bsuporte\b.*\b(?:profit|xp)\b/i,
  /\bhunted\b.*\b(?:fazendo|double xp|double)\b/i,
  /\b(?:abrindo slot extra|bounty tasks)\b/i,
  /\b(?:testando summon|i peaked)\b/i,
  /\bprofit nessa task\b/i,
];

function cleanHuntName(value) {
  return String(value || "")
    .replace(/#[\p{L}\p{N}_]+/gu, " ")
    .replace(/\b(?:MS|EK|ED|RP|EM|Monk|Mage|Sorcerer|Knight|Druid|Paladin)\s+(?:Lv\.?|Level)\s*\d{2,4}\+?\b/gi, " ")
    .replace(/\b(?:Lv\.?|Level)\s*\d{2,4}\+?\b/gi, " ")
    .replace(/\[\s*\d{1,2}\.\d{1,2}\s*\]/g, " ")
    .replace(/\b(?:\d{2,4}\s*(?:MS|EK|ED|RP|EM|Monk|Mage|Sorcerer|Knight|Druid|Paladin)|(MS|EK|ED|RP|EM|Monk|Mage|Sorcerer|Knight|Druid|Paladin)\s*\d{2,4}\+?)\b/gi, " ")
    .replace(/\b\d+(?:[.,]\d+)?\s*(?:kk|k)\s*(?:\/\s*h|h)?\b/gi, " ")
    .replace(/\b\d+(?:[.,]\d+)?\s*%\b/gi, " ")
    .replace(/\b\d+(?:[.,]\d+)?\+?\s*(?:raw|xp|exp|profit)\b/gi, " ")
    .replace(/\bx[2-5]\b/gi, " ")
    .replace(/\b(?:MS|EK|ED|RP|EM|Monk|Mage|Sorcerer|Knight|Druid|Paladin|Tibia|Hunt|Hunting|Solo|Duo|Trio|Team|Raw|XP|Exp|Profit|Waste|Loot|Peak|Stable|Boosted|Prey|Task|Weekly|Low|Blow|Test|Hour|Hora|Level|Indicado|Explicativa|Explicativo)\b/gi, " ")
    .replace(/\b(?:double|record|recorde|absurdo|do zero ao|em|de|na|no|com|para|and|the|solo|sem|mais|insana|atk|charms?|runes?|proft|waste|full|pt|prey|after|before|global|jogando|farmando|hora|level|lv|s[oó]|falta|um)\b/gi, " ")
    .replace(/\bh\b/gi, " ")
    .replace(/[^\p{L}\p{N}\s.,'-]/gu, " ")
    .replace(/(?<!\s)-|(?<=\s)-(?!\d)|[–—/]+/g, " ")
    .replace(/\s+/g, " ")
    .replace(/^[\s.,]+|[\s.,]+$/g, "")
    .trim();
}

function huntNameFromTitle(title) {
  const text = String(title || "");
  const marker = text.match(/\bhunt(?:ing)?\b\s+(.+)/i);
  if (marker) {
    const segment = marker[1]
      .split(/[([{!?:]/)[0]
      .split(/\s+(?:\||\+)|\s+\d+(?:[.,]\d+)?\s*(?:kk|k)\b|\s+\d+(?:[.,]\d+)?\s*%|\b(?:raw|xp|exp|profit|waste)\b|\bTibia\s+Hunt\b/i)[0];
    const explicitName = cleanHuntName(segment);
    if (explicitName.length >= 3) return explicitName;
  }
  return cleanHuntName(text);
}

function huntNameFromDescription(description) {
  const text = String(description || "");
  const patterns = [
    /\b(?:testei|testando)\s+(?:a\s+)?hunt(?:\s+de)?\s+([^\n.!?…]+)/i,
    /\bhunts?\b[^:\n]{0,90}:\s*(?:a|o|as|os)?\s*([^\n.!?,…]+)/i,
    /\b(?:destruindo|destroying|caçando|hunting)\s+([^\n.!?,…]+)/i,
    /\bbestiary(?:s)?\s+(?:de|do|da|dos|das)\s+([^\n.!?…]+)/i,
    /\bcaçada\s+solo\b[^\n.!?…]{0,60}\b(?:no|na|em)\s+([^,\n.!?…]+)/i,
    /\bhunt(?:zinha)?\s+(?:de|do|da|dos|das|nas|nos|na|no|em)\s+([^,\n.!?…]+)/i,
    /\bhunt(?:zinha)?\b[^\n.!?…]{0,35}\b(?:nas|nos|na|no|em)\s+([^,\n.!?…]+)/i,
  ];
  for (const pattern of patterns) {
   for (const match of text.matchAll(new RegExp(pattern.source, `${pattern.flags.replace("g", "")}g`))) {
    const candidate = match[1]
      .replace(/\s+(?:e olha isso|e olha|para level|com \d.*)$/i, "")
      .split(/\s+(?:—|–|;|mas)\s+/)[0]
      .replace(/[\[\]_*💰🔥⚡🧙🚀]/gu, "")
      .trim();
    if (!candidate || /nome da hunt|\bboas\b/i.test(candidate) || /^(?:pt|party|duo|solo|grupo|live|todo dia|depois|dias?|semanas?|horas?|epis[oó]dio|domingo|canal|prática|favorito|evento|vivo|tibia|dinheiro|money|xp|profit|opções|options|hunt)\b/i.test(candidate)) continue;
    if (/^minha de chocolate$/i.test(candidate)) return "Chocolate Mines";
    return candidate;
   }
  }
  return "";
}

function profitFromDescription(description) {
  const text = String(description || "");
  const prefix = text.match(/\b(profit|waste)\s*:\s*\[?\s*(\d+(?:[.,]\d+)?)\s*(kk|k)\b/i);
  const suffix = text.match(/(\d+(?:[.,]\d+)?)\s*(kk|k)\s*(?:de\s+)?(profit|waste)\b/i);
  if (prefix) return `${prefix[1].toLowerCase() === "waste" ? "-" : ""}${prefix[2].replace(",", ".")}${prefix[3].toLowerCase()}/h`;
  return suffix ? `${suffix[3].toLowerCase() === "waste" ? "-" : ""}${suffix[1].replace(",", ".")}${suffix[2].toLowerCase()}/h` : null;
}

function profitFromTitle(title) {
  const text = String(title || "");
  const suffix = text.match(/(\d+(?:[.,]\d+)?)\s*(kk|k)\s*(?:de\s+)?(profit|waste)\b/i);
  const prefix = text.match(/\b(profit|waste)\s*[:=]\s*(\d+(?:[.,]\d+)?)\s*(kk|k)\b/i);
  if (suffix) return `${suffix[3].toLowerCase() === "waste" ? "-" : ""}${suffix[1].replace(",", ".")}${suffix[2].toLowerCase()}/h`;
  return prefix ? `${prefix[1].toLowerCase() === "waste" ? "-" : ""}${prefix[2].replace(",", ".")}${prefix[3].toLowerCase()}/h` : null;
}

function isSpecificHuntTitle(title, description = "") {
  const text = String(title || "");
  const titleName = huntNameFromTitle(text);
  const titleIsGenericSeries = /\bmongekoth\b/i.test(text) && !/\b(?:nagas?|scarlet|naga tanko)\b/i.test(text);
  if ((titleName.length < 3 || titleIsGenericSeries) && huntNameFromDescription(description)) return true;
  if (NON_SPECIFIC_HUNT_RE.some((pattern) => pattern.test(text))) return false;
  if (titleIsGenericSeries) return false;
  return titleName.length >= 3;
}

function standardizedTitle(row) {
  const titleName = huntNameFromTitle(row.title);
  const titleIsGenericSeries = /\bmongekoth\b/i.test(row.title || "") && !/\b(?:nagas?|scarlet|naga tanko)\b/i.test(row.title || "");
  const huntName = ((titleName.length < 3 || titleIsGenericSeries) && huntNameFromDescription(row.description)) || titleName || "Hunt não identificada";
  const orderedVocations = [...new Set([row.primaryVocation, ...row.levels.map((entry) => entry.vocation)].filter(Boolean))];
  const vocation = orderedVocations.join("/") || vocationFromText(row.title || "") || "Vocação não identificada";
  const xp = row.xp_raw_display || "não informado";
  const profit = row.profit_display || "não informado";
  return `${vocation} · ${huntName} · XP Raw ${xp} · Profit ${profit}`;
}

function vocationFromText(text) {
  const value = String(text || "");
  return vocationsFromText(value)[0] || "";
}

function vocationFromTitle(text) {
  const value = String(text || "").replace(/\bEM\s+20\d{2}\b/gi, " ");
  const namedMatches = [...value.matchAll(/\b(MS|EK|ED|RP|Monk|Master\s+Sorcerer|Elite\s+Knight|Elder\s+Druid|Royal\s+Paladin|Mage|Sorcerer|Knight|Druid|Paladin)\b/gi)];
  const emMatches = [...value.matchAll(/\bEM\b/g)];
  const firstMatch = [...namedMatches, ...emMatches].sort((a, b) => a.index - b.index)[0];
  if (!firstMatch) return "";
  const alias = firstMatch[1].toUpperCase();
  return ({ MAGE: "MS", SORCERER: "MS", KNIGHT: "EK", DRUID: "ED", MONK: "EM", PALADIN: "RP" })[alias] || alias;
}

function vocationsFromText(text) {
  const value = String(text || "");
  const valueWithoutEmYears = value.replace(/\bEM\s+20\d{2}\b/gi, " ");
  const patterns = [
    ["MS", /\b(?:MS|Master Sorcerer|Sorcerer|Sorceress|Mage)\b/i],
    ["EK", /\b(?:EK|Elite Knight|Knight)\b/i],
    ["ED", /\b(?:ED|Elder Druid|Druid)\b/i],
    ["RP", /\b(?:RP|Royal Paladin|Paladin)\b/i],
  ];
  const vocations = patterns.filter(([, pattern]) => pattern.test(value)).map(([vocation]) => vocation);
  if (/\bEM\b/.test(valueWithoutEmYears) || /\bMonk\b/i.test(value)) vocations.push("EM");
  return ["MS", "EK", "ED", "EM", "RP"].filter((vocation) => vocations.includes(vocation));
}

function enrich(row) {
  const levels = parseLevels(row.title || "", row.description || "");
  const playlistVocations = String(row.playlist_vocations || "").split(",").filter(Boolean);
  if (!playlistVocations.length && Number(row.from_channel) === 1) {
    for (const vocation of vocationsFromText(row.title || "")) {
      if (!playlistVocations.includes(vocation)) playlistVocations.push(vocation);
    }
  }
  const profitFromDescriptionValue = profitFromDescription(row.description) || profitFromTitle(row.title);
  const primaryVocation = vocationFromTitle(row.title || "") || playlistVocations[0] || levels[0]?.vocation || "";
  const normalized = { ...row, levels, playlistVocations, primaryVocation };
  if (!normalized.profit_display && profitFromDescriptionValue) {
    normalized.profit_display = profitFromDescriptionValue;
    normalized.profit_source_display = `Descrição: ${profitFromDescriptionValue}`;
  }
  normalized.catalogTitle = standardizedTitle(normalized);
  normalized.concreteHunt = isSpecificHuntTitle(row.title, row.description);
  return normalized;
}

function selectedRadio(name) {
  return document.querySelector(`input[name="${name}"]:checked`)?.value || "ALL";
}

function levelFor(row, vocation) {
  if (vocation !== "ALL") {
    const entry = row.levels.find((item) => item.vocation === vocation);
    if (entry) return entry.level;
  }
  return row.levels[0]?.level ?? null;
}

function difficultyFor(row, playerLevel, vocation) {
  const reference = levelFor(row, vocation);
  if (!reference || !playerLevel) return null;
  if (playerLevel >= reference * 1.1) return "easy";
  if (playerLevel >= reference * 0.9) return "moderate";
  if (playerLevel < 300 && reference > playerLevel * 1.25) return "out_of_range";
  return "advanced";
}

const DIFFICULTY = {
  easy: { label: "Fácil", dot: "easy" },
  moderate: { label: "Moderada", dot: "moderate" },
  advanced: { label: "Avançada", dot: "advanced" },
  out_of_range: { label: "Fora da faixa", dot: "advanced" },
};

function formatLevels(row) {
  if (!row.levels.length) return "Level não identificado";
  return row.levels.map(({ vocation, level }) => `${vocation} ${level}`).join(" · ");
}

function metricMarkup(label, metric, style = "") {
  if (!metric) return `<div class="metric"><span class="metric-label">${label}</span><span class="metric-value unavailable">Não informado no título</span></div>`;
  return `<div class="metric"><span class="metric-label">${label}</span><span class="metric-value ${style}">${metric.text}</span></div>`;
}

function rawXpMarkup(row) {
  if (!row.xp_raw_display) {
    const message = row.xp_raw_status === "not_found" ? "XP/h ausente no título" : "XP Raw indisponível";
    return `<div class="metric"><span class="metric-label">XP/H RAW</span><span class="metric-value unavailable">${message}</span></div>`;
  }
  const source = row.xp_source_display ? `Origem: ${row.xp_source_display}` : row.xp_raw_note;
  return `<div class="metric"><span class="metric-label">XP/H RAW</span><span class="metric-value">${escapeHtml(row.xp_raw_display)}</span><small class="metric-note" title="${escapeHtml(row.xp_raw_note || "")}">${escapeHtml(source || "XP equivalente a 100%")}</small></div>`;
}

function profitMarkup(row) {
  const isWaste = Number(row.profit_per_hour) < 0 || /^\s*-/.test(row.profit_display || "") || /waste/i.test(row.profit_source_display || "");
  const label = isWaste ? "WASTE/H NO TÍTULO" : "PROFIT/H NO TÍTULO";
  if (!row.profit_display) {
    return `<div class="metric"><span class="metric-label">${label}</span><span class="metric-value unavailable">${isWaste ? "Waste não informado" : "Profit não informado"}</span></div>`;
  }
  const note = row.profit_assumption || `${String(row.profit_source_display || "").startsWith("Descrição:") ? "Extraído da descrição" : "Extraído do título"}: ${row.profit_source_display || ""}`;
  return `<div class="metric"><span class="metric-label">${label}</span><span class="metric-value ${isWaste ? "loss" : "profit"}">${escapeHtml(row.profit_display)}</span><small class="metric-note" title="${escapeHtml(note)}">${escapeHtml(isWaste ? "Waste exibido como valor negativo" : row.profit_assumption ? "1 hora de hunt presumida" : `Título: ${row.profit_source_display}`)}</small></div>`;
}

function cardMarkup(row) {
  const vocation = $("#vocation").value;
  const playerLevel = Number($("#player-level").value) || null;
  const difficulty = difficultyFor(row, playerLevel, vocation);
  const mode = MODE_NAMES[row.hunt_type] || row.hunt_type || "Não identificado";
  const level = formatLevels(row);
  const xpMetric = rawXpMarkup(row);
  const profitMetric = profitMarkup(row);
  const diffMarkup = difficulty
    ? `<span class="difficulty-badge"><i class="diff-dot ${DIFFICULTY[difficulty].dot}"></i>${DIFFICULTY[difficulty].label}</span>`
    : `<span class="difficulty-badge">Informe seu level</span>`;
  const playerLabel = Number(row.players_count) === 1 ? "jogador" : "jogadores";
  return `<article class="hunt-card">
    <a class="thumb-wrap" href="${row.video_url}" target="_blank" rel="noopener noreferrer" aria-label="Assistir: ${escapeHtml(row.title)}">
      <img loading="lazy" src="https://i.ytimg.com/vi/${encodeURIComponent(row.video_id)}/hqdefault.jpg" alt="Miniatura do vídeo" />
      <span class="thumb-vocation">${row.primaryVocation || row.levels[0]?.vocation || row.playlistVocations[0] || "HUNT"}</span>
      <span class="thumb-position">#${row.position}</span><span class="play-button">▶</span>
    </a>
    <div class="hunt-card-body">
      <div class="card-badges"><span class="mode-badge ${row.hunt_type === "Solo" ? "solo" : row.hunt_type === "Trio" ? "trio" : ""}">✦ ${escapeHtml(mode)}${row.players_count ? ` · ${row.players_count} ${playerLabel}` : ""}</span><span class="card-badge-right">${row.sponsored ? '<i class="sponsored-badge">Patrocinado</i>' : ""}${diffMarkup}</span></div>
      <a class="card-title-link" href="${row.video_url}" target="_blank" rel="noopener noreferrer"><h3 title="Título original do YouTube">${escapeHtml(row.title)}</h3></a>
      <div class="card-level"><span class="level-symbol">◈</span>${escapeHtml(level)}</div>
      <div class="metric-row">${xpMetric}${profitMetric}</div>
      <div class="feedback-actions"><button class="feedback-action feedback-submit-open" type="button" data-feedback-action="submit" data-video-id="${escapeHtml(row.video_id)}" data-video-title="${escapeHtml(row.title)}">Testei esta hunt</button><button class="feedback-action feedback-view-open" type="button" data-feedback-action="view" data-video-id="${escapeHtml(row.video_id)}" data-video-title="${escapeHtml(row.title)}">Ver feedback <span class="feedback-count">${feedbackCounts[row.video_id] || 0}</span></button></div>
    </div>
  </article>`;
}

function feedbackItemMarkup(item) {
  const date = item.created_at ? new Date(`${item.created_at.replace(" ", "T")}Z`).toLocaleDateString("pt-BR") : "";
  const flags = [item.tested ? "Testou a hunt" : "Relato", item.outdated ? "Vídeo desatualizado" : ""].filter(Boolean).join(" · ");
  const outcome = [item.xp_raw ? `Raw: ${item.xp_raw}` : "", item.profit ? `Profit: ${item.profit}` : "", item.difficulty ? `Dificuldade: ${item.difficulty}/5` : ""].filter(Boolean).join(" · ");
  return `<article class="feedback-entry"><div class="feedback-entry-head"><strong>${escapeHtml(item.nickname || "Caçador da comunidade")}</strong><span>${escapeHtml(item.vocation)} ${escapeHtml(item.player_level)} · ${escapeHtml(date)}</span></div><small>${escapeHtml(flags)}${outcome ? ` · ${escapeHtml(outcome)}` : ""}</small><p>${escapeHtml(item.result)}</p></article>`;
}

async function openFeedbackList(videoId, title, message = "") {
  selectedFeedbackVideo = { videoId, title };
  const dialog = $("#feedback-list-dialog");
  $("#feedback-list-video-title").textContent = title;
  $("#feedback-list-status").textContent = message;
  $("#feedback-list").innerHTML = "<p class=\"feedback-empty\">Carregando relatos…</p>";
  dialog.showModal();
  try {
    const response = await fetch(window.skanApiUrl(`/api/videos/${encodeURIComponent(videoId)}/feedback`), { cache: "no-store" });
    const items = await response.json();
    if (!response.ok) throw new Error(items.error || "Não foi possível carregar os relatos.");
    $("#feedback-list").innerHTML = items.length ? items.map(feedbackItemMarkup).join("") : "<p class=\"feedback-empty\">Ainda sem relatos. Seja a primeira pessoa a contar como foi!</p>";
  } catch (error) {
    $("#feedback-list").innerHTML = `<p class="feedback-empty">${escapeHtml(error.message)}. Abra o site pelo servidor para carregar e enviar feedback.</p>`;
  }
}

function openFeedbackForm(videoId, title) {
  selectedFeedbackVideo = { videoId, title };
  const form = $("#feedback-form");
  form.reset();
  $("#feedback-video-id").value = videoId;
  $("#feedback-form-video-title").textContent = title;
  $("#feedback-form-status").textContent = "Seu relato ficará associado a este vídeo.";
  $("#feedback-form-dialog").showModal();
}

async function submitFeedback(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const videoId = $("#feedback-video-id").value;
  const submit = form.querySelector("button[type=submit]");
  const status = $("#feedback-form-status");
  const payload = Object.fromEntries(new FormData(form).entries());
  payload.tested = form.elements.tested.checked;
  payload.outdated = form.elements.outdated.checked;
  payload.player_level = Number(payload.player_level);
  payload.difficulty = payload.difficulty ? Number(payload.difficulty) : null;
  submit.disabled = true;
  status.textContent = "Enviando seu relato…";
  try {
    const response = await fetch(window.skanApiUrl(`/api/videos/${encodeURIComponent(videoId)}/feedback`), {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Não foi possível enviar.");
    form.elements.result.value = "";
    form.elements.xp_raw.value = "";
    form.elements.profit.value = "";
    const title = selectedFeedbackVideo?.title || "";
    $("#feedback-form-dialog").close();
    feedbackCounts[videoId] = (feedbackCounts[videoId] || 0) + 1;
    renderCards();
    await openFeedbackList(videoId, title, "Feedback publicado. Obrigado por compartilhar sua experiência!");
  } catch (error) {
    status.textContent = error.message;
  } finally {
    submit.disabled = false;
  }
}

async function sendForm(url, form, statusElement, transform = (data) => data) {
  const submit = form.querySelector("button[type=submit]");
  const data = transform(Object.fromEntries(new FormData(form).entries()), form);
  submit.disabled = true;
  try {
    const response = await fetch(window.skanApiUrl(url), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Não foi possível enviar.");
    statusElement.textContent = result.message || "Enviado.";
    form.reset();
    return true;
  } catch (error) {
    statusElement.textContent = error.message;
    return false;
  } finally {
    submit.disabled = false;
  }
}

async function refreshLeaderboard() {
  const list = $("#donation-ranking");
  try {
    const response = await fetch(window.skanApiUrl("/api/donations/leaderboard"), { cache: "no-store" });
    const entries = await response.json();
    if (!response.ok) throw new Error(entries.error || "Falha ao carregar.");
    list.innerHTML = entries.length ? entries.map((entry, index) => `<li><span>${index + 1}. ${escapeHtml(entry.nickname)}</span><b>${Number(entry.total_tc).toLocaleString("pt-BR")} TC</b></li>`).join("") : "<li>O ranking aparecerá após as primeiras contribuições confirmadas.</li>";
  } catch { list.innerHTML = "<li>Ranking disponível quando o site estiver aberto pelo servidor.</li>"; }
}

async function loadFeedbackCounts() {
  try {
    const response = await fetch(window.skanApiUrl("/api/feedback-counts"), { cache: "no-store" });
    if (!response.ok) return;
    feedbackCounts = await response.json();
  } catch { /* Feedback counts require the local site server. */ }
}

function adminHeaders() {
  return { "X-Skan-Admin-Key": sessionStorage.getItem("skan-admin-key") || "" };
}

async function adminGet(path) {
  const response = await fetch(window.skanApiUrl(path), { headers: adminHeaders(), cache: "no-store" });
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || "Falha no portal.");
  return value;
}

async function loadAdminPortal() {
  const [sources, donations, promotions] = await Promise.all([
    adminGet("/api/admin/sources"), adminGet("/api/admin/donations"), adminGet("/api/admin/promotions"),
  ]);
  $("#admin-sources").innerHTML = sources.length ? sources.map((item) => `<div class="admin-entry"><span><b>${escapeHtml(item.name)}</b><small>${escapeHtml(item.source_type)} · ${escapeHtml(item.vocation)} · ${escapeHtml(item.source_url)}</small></span><span class="admin-entry-actions"><button type="button" data-toggle-promotion="${item.id}" data-status="${item.promotion_status === "sponsored" ? "organic" : "sponsored"}">${item.promotion_status === "sponsored" ? "Remover destaque" : "Marcar patrocinado"}</button><button type="button" data-remove-source="${item.id}">Remover</button></span></div>`).join("") : "<p>Nenhuma fonte cadastrada pelo portal.</p>";
  $("#admin-donations").innerHTML = donations.length ? donations.map((item) => `<div class="admin-entry"><span><b>${escapeHtml(item.nickname)} · ${Number(item.amount_tc).toLocaleString("pt-BR")} TC</b><small>Recebimento pendente de conferência manual${item.show_in_ranking ? " · aceitou ranking" : " · não listou nome"}</small></span><button type="button" data-confirm-donation="${item.id}">Confirmar</button></div>`).join("") : "<p>Nenhuma contribuição pendente.</p>";
  $("#admin-promotions").innerHTML = promotions.length ? promotions.map((item) => `<div class="admin-entry"><span><b>${escapeHtml(item.creator_name)} (${escapeHtml(item.vocation)})</b><small><a href="${escapeHtml(item.youtube_url)}" target="_blank" rel="noopener">Abrir link do YouTube</a> · ${escapeHtml(item.note || "Sem observação")}</small></span><button type="button" data-prepare-promo="${escapeHtml(item.youtube_url)}" data-creator="${escapeHtml(item.creator_name)}" data-vocation="${escapeHtml(item.vocation)}">Preparar importação</button></div>`).join("") : "<p>Nenhum pedido pendente.</p>";
}

async function adminRequest(url, method, body = null) {
  const response = await fetch(window.skanApiUrl(url), { method, headers: { ...adminHeaders(), ...(body ? { "Content-Type": "application/json" } : {}) }, ...(body ? { body: JSON.stringify(body) } : {}) });
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || "Ação não concluída.");
  return value;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);
}

function applyFilters() {
  const term = $("#search").value.trim().toLocaleLowerCase("pt-BR");
  const vocation = $("#vocation").value;
  const mode = selectedRadio("mode");
  const difficulty = selectedRadio("difficulty");
  const playerLevel = Number($("#player-level").value) || null;
  const sortBy = $("#sort-by").value;
  visibleRows = catalog.filter((row) => {
    if (!row.concreteHunt) return false;
    if (term && !`${row.catalogTitle} ${row.title} ${row.channel_title || ""}`.toLocaleLowerCase("pt-BR").includes(term)) return false;
    if (vocation !== "ALL" && !row.playlistVocations.includes(vocation) && !row.levels.some((item) => item.vocation === vocation)) return false;
    if (mode !== "ALL" && row.hunt_type !== mode) return false;
    const rowDifficulty = difficultyFor(row, playerLevel, vocation);
    if (difficulty !== "ALL" && rowDifficulty !== difficulty) return false;
    return true;
  });
  visibleRows.sort((a, b) => {
    if (Boolean(a.sponsored) !== Boolean(b.sponsored)) return a.sponsored ? -1 : 1;
    const metricA = sortBy === "profit" ? a.profit_per_hour : sortBy === "level" ? levelFor(a, vocation) : a.xp_raw_per_hour;
    const metricB = sortBy === "profit" ? b.profit_per_hour : sortBy === "level" ? levelFor(b, vocation) : b.xp_raw_per_hour;
    if (metricA == null && metricB == null) return Number(a.position) - Number(b.position);
    if (metricA == null) return 1;
    if (metricB == null) return -1;
    return metricB - metricA;
  });
  displayed = PAGE_SIZE;
  renderCards();
  updateSummary(vocation, difficulty);
}

function updateSummary(vocation, difficulty) {
  $("#result-count").textContent = visibleRows.length;
  const role = vocation === "ALL" ? "todas as vocações" : ROLE_NAMES[vocation];
  const diff = difficulty === "ALL" ? "" : ` · ${DIFFICULTY[difficulty].label.toLowerCase()}`;
  $("#filter-summary").textContent = `Mostrando hunts para ${role}${diff}`;
}

function renderCards() {
  cards.innerHTML = visibleRows.slice(0, displayed).map(cardMarkup).join("");
  $("#empty-state").hidden = visibleRows.length > 0;
  $("#load-more").hidden = displayed >= visibleRows.length;
  cards.querySelectorAll("img").forEach((image) => image.addEventListener("error", () => image.remove(), { once: true }));
}

function clearFilters() {
  $("#search").value = "";
  $("#vocation").value = "ALL";
  $("#player-level").value = "900";
  $("#sort-by").value = "xp";
  document.querySelector('input[name="mode"][value="ALL"]').checked = true;
  document.querySelector('input[name="difficulty"][value="ALL"]').checked = true;
  applyFilters();
}

function applyTheme(theme, save = false) {
  const dark = theme === "dark";
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  const toggle = $("#theme-toggle");
  if (toggle) {
    toggle.setAttribute("aria-pressed", String(dark));
    toggle.setAttribute("aria-label", dark ? "Ativar modo claro" : "Ativar modo escuro");
  }
  if ($("#theme-icon")) $("#theme-icon").textContent = dark ? "☀" : "☾";
  if ($("#theme-label")) $("#theme-label").textContent = dark ? "Modo claro" : "Modo escuro";
  const themeColor = document.querySelector('meta[name="theme-color"]');
  if (themeColor) themeColor.content = dark ? "#0b1411" : "#101b1a";
  if (save) {
    try { localStorage.setItem("skan-theme", dark ? "dark" : "light"); } catch { /* preference storage may be blocked */ }
  }
}

function bindControls() {
  $("#search").addEventListener("input", applyFilters);
  $("#vocation").addEventListener("change", applyFilters);
  $("#player-level").addEventListener("input", applyFilters);
  $("#sort-by").addEventListener("change", applyFilters);
  document.querySelectorAll('input[name="mode"], input[name="difficulty"]').forEach((el) => el.addEventListener("change", applyFilters));
  $("#clear-filters").addEventListener("click", clearFilters);
  $("#empty-clear").addEventListener("click", clearFilters);
  $("#load-more").addEventListener("click", () => { displayed += PAGE_SIZE; renderCards(); });
  $("#theme-toggle").addEventListener("click", () => {
    applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark", true);
  });
  cards.addEventListener("click", (event) => {
    const button = event.target.closest("[data-feedback-action]");
    if (!button) return;
    if (button.dataset.feedbackAction === "view") openFeedbackList(button.dataset.videoId, button.dataset.videoTitle);
    else openFeedbackForm(button.dataset.videoId, button.dataset.videoTitle);
  });
  $("#feedback-form").addEventListener("submit", submitFeedback);
  $("#feedback-list-close").addEventListener("click", () => $("#feedback-list-dialog").close());
  $("#feedback-form-close").addEventListener("click", () => $("#feedback-form-dialog").close());
  $("#write-feedback").addEventListener("click", () => {
    const current = selectedFeedbackVideo;
    $("#feedback-list-dialog").close();
    if (current) openFeedbackForm(current.videoId, current.title);
  });
  $("#donation-form").addEventListener("submit", (event) => {
    event.preventDefault();
    sendForm("/api/donations", event.currentTarget, $("#donation-status"), (data, form) => ({ ...data, amount_tc: Number(data.amount_tc), show_in_ranking: form.elements.show_in_ranking.checked }));
  });
  $("#donation-form").addEventListener("submit", () => setTimeout(refreshLeaderboard, 500));
  refreshLeaderboard();
}

async function start() {
  applyTheme(document.documentElement.dataset.theme || "light");
  bindControls();
  try {
    let payload = !window.SKAN_API_BASE && Array.isArray(window.SKAN_CATALOG) ? window.SKAN_CATALOG : null;
    if (!payload) {
      const response = await fetch(window.skanApiUrl("/api/videos"), { cache: "no-store" });
      if (!response.ok) throw new Error("Não foi possível ler o catálogo local.");
      payload = await response.json();
    }
    if (!Array.isArray(payload)) throw new Error(payload.error || "Resposta inválida do catálogo.");
    catalog = payload.map(enrich).filter((row) => row.concreteHunt);
    await loadFeedbackCounts();
    $("#stat-total").textContent = catalog.length;
    const vocations = new Set(catalog.flatMap((row) => row.playlistVocations));
    $("#stat-vocations").textContent = vocations.size || "—";
    $("#vocation").value = "ALL";
    applyFilters();
  } catch (error) {
    cards.innerHTML = `<div class="load-error"><strong>Não foi possível carregar o catálogo.</strong><p>${escapeHtml(error.message)}</p><span>Confira se o servidor local continua aberto e tente atualizar a página.</span></div>`;
    $("#result-count").textContent = "0";
  }
}

start();
