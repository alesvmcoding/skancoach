const $ = (selector) => document.querySelector(selector);
const status = $("#admin-status");
const importStatus = $("#source-status");

function applyPortalTheme() {
  const dark = document.documentElement.dataset.theme === "dark";
  const button = $("#theme-toggle");
  button.setAttribute("aria-pressed", String(dark));
  button.setAttribute("aria-label", dark ? "Ativar modo claro" : "Ativar modo escuro");
  $("#theme-icon").textContent = dark ? "☀" : "☾";
  $("#theme-label").textContent = dark ? "Modo claro" : "Modo escuro";
  document.querySelector('meta[name="theme-color"]').content = dark ? "#0b1411" : "#101b1a";
}

function syncSourceVocation() {
  const channel = $("#source-form").elements.source_type.value === "channel";
  $("#source-vocation-label").hidden = channel;
  $("#channel-vocation-note").hidden = !channel;
  if (channel) $("#source-form").elements.vocation.value = "CHANNEL";
  else if ($( "#source-form").elements.vocation.value === "CHANNEL") $("#source-form").elements.vocation.value = "MS";
}
$("#source-form").elements.source_type.addEventListener("change", syncSourceVocation);
syncSourceVocation();

$("#theme-toggle").addEventListener("click", () => {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem("skan-theme", next); } catch { /* local preference storage can be disabled */ }
  applyPortalTheme();
});
applyPortalTheme();

function headers(json = false) {
  return { "X-Skan-Admin-Key": sessionStorage.getItem("skan-admin-key") || "", ...(json ? { "Content-Type": "application/json" } : {}) };
}

async function api(path, options = {}) {
  const response = await fetch(window.skanApiUrl(path), { cache: "no-store", ...options, headers: { ...headers(Boolean(options.body)), ...(options.headers || {}) } });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Não foi possível concluir esta ação.");
  return result;
}

async function loadPortal() {
  const [sources, donations, promotions] = await Promise.all([
    api("/api/admin/sources"), api("/api/admin/donations"), api("/api/admin/promotions"),
  ]);
  $("#admin-sources").innerHTML = sources.length ? sources.map((item) => `<div class="admin-entry"><span><b>${esc(item.name)}</b><small>${esc(item.source_type)} · ${item.vocation === "CHANNEL" ? "vocação identificada por vídeo" : esc(item.vocation)} · ${esc(item.source_url)}</small></span><span class="admin-entry-actions"><button type="button" data-sponsor="${item.id}" data-status="${item.promotion_status === "sponsored" ? "organic" : "sponsored"}">${item.promotion_status === "sponsored" ? "Remover destaque" : "Marcar patrocinado"}</button><button type="button" data-remove="${item.id}">Remover</button></span></div>`).join("") : "<p>Nenhuma fonte cadastrada.</p>";
  $("#admin-donations").innerHTML = donations.length ? donations.map((item) => `<div class="admin-entry"><span><b>${esc(item.nickname)} · ${Number(item.amount_tc).toLocaleString("pt-BR")} TC</b><small>Confirme manualmente no jogo${item.show_in_ranking ? " · autorizou ranking" : " · sem ranking público"}</small></span><button type="button" data-confirm-donation="${item.id}">Validar</button></div>`).join("") : "<p>Nenhuma contribuição aguardando validação.</p>";
  $("#admin-promotions").innerHTML = promotions.length ? promotions.map((item) => `<div class="admin-entry"><span><b>${esc(item.creator_name)} · ${esc(item.vocation)}</b><small><a href="${esc(item.youtube_url)}" target="_blank" rel="noopener">Abrir YouTube</a> · ${esc(item.note || "Sem observação")}</small></span><button type="button" data-prepare="${esc(item.youtube_url)}" data-name="${esc(item.creator_name)}" data-vocation="${esc(item.vocation)}">Preparar importação</button></div>`).join("") : "<p>Nenhum pedido aguardando análise.</p>";
}

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
}

$("#admin-login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  sessionStorage.setItem("skan-admin-key", event.currentTarget.elements.admin_key.value);
  status.textContent = "Validando acesso…";
  try {
    await loadPortal();
    $("#admin-tools").hidden = false;
    status.textContent = "Acesso liberado nesta sessão.";
  } catch (error) {
    sessionStorage.removeItem("skan-admin-key");
    status.textContent = error.message;
  }
});

$("#source-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector("button[type=submit]");
  button.disabled = true;
  importStatus.textContent = "Importando do YouTube… Aguarde; canais grandes podem levar alguns minutos.";
  try {
    const payload = Object.fromEntries(new FormData(form).entries());
    if (payload.source_type === "channel") payload.vocation = "CHANNEL";
    const result = await api("/api/admin/sources", { method: "POST", body: JSON.stringify(payload) });
    importStatus.textContent = result.message;
    form.reset();
    await loadPortal();
  } catch (error) { importStatus.textContent = `Importação não concluída: ${error.message}`; }
  finally { button.disabled = false; }
});

$("#refresh-sources").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  const progress = $("#refresh-status");
  button.disabled = true;
  progress.textContent = "Iniciando atualização… mantenha esta página aberta.";
  try {
    let result = await api("/api/admin/sources/refresh", { method: "POST" });
    while (result.status === "running") {
      progress.textContent = `Atualizando fonte ${Math.min(result.completed_sources + 1, result.total_sources)} de ${result.total_sources}: ${result.current_source || "preparando…"}. ${Number(result.videos_processed || 0).toLocaleString("pt-BR")} vídeos processados até agora.`;
      await new Promise((resolve) => setTimeout(resolve, 1800));
      result = await api("/api/admin/sources/refresh/status");
    }
    if (result.status === "failed") throw new Error(result.error || "A atualização foi interrompida.");
    let message = `Concluído: ${result.updated_sources} de ${result.total_sources} fontes atualizadas; ${Number(result.videos_processed || 0).toLocaleString("pt-BR")} vídeos processados. Atualize o catálogo para ver as mudanças.`;
    if (result.errors?.length) message += ` ${result.errors.length} fonte(s) falharam. ${result.errors.slice(0, 2).map((item) => `${item.source}: ${String(item.error).slice(0, 180)}`).join(" | ")}`;
    progress.textContent = message;
    await loadPortal();
  } catch (error) { progress.textContent = `Não foi possível atualizar: ${error.message}`; }
  finally { button.disabled = false; }
});

$("#admin-tools").addEventListener("click", async (event) => {
  const remove = event.target.closest("[data-remove]");
  const confirmDonation = event.target.closest("[data-confirm-donation]");
  const sponsor = event.target.closest("[data-sponsor]");
  const prepare = event.target.closest("[data-prepare]");
  try {
    if (prepare) {
      const url = prepare.dataset.prepare;
      const kind = /[?&]list=/.test(url) ? "playlist" : /youtu\.be|watch\?v=|\/shorts\//.test(url) ? "video" : "channel";
      const form = $("#source-form");
      form.elements.source_type.value = kind;
      form.elements.source_url.value = url;
      form.elements.name.value = prepare.dataset.name;
      form.elements.vocation.value = prepare.dataset.vocation;
      syncSourceVocation();
      form.scrollIntoView({ behavior: "smooth", block: "center" });
      status.textContent = "Revise os dados e clique em Importar para o catálogo.";
      return;
    }
    if (remove && window.confirm("Remover esta fonte? Vídeos que também pertençam a outra fonte serão preservados.")) {
      await api(`/api/admin/sources/${remove.dataset.remove}`, { method: "DELETE" });
      status.textContent = "Fonte removida do catálogo.";
    }
    if (confirmDonation) {
      await api(`/api/admin/donations/${confirmDonation.dataset.confirmDonation}/confirm`, { method: "POST" });
      status.textContent = "Contribuição confirmada e adicionada ao ranking, se a pessoa autorizou.";
    }
    if (sponsor) {
      await api(`/api/admin/sources/${sponsor.dataset.sponsor}/promotion`, { method: "POST", body: JSON.stringify({ status: sponsor.dataset.status }) });
      status.textContent = sponsor.dataset.status === "sponsored" ? "Fonte marcada como patrocinada." : "Destaque patrocinado removido.";
    }
    if (remove || confirmDonation || sponsor) await loadPortal();
  } catch (error) { status.textContent = error.message; }
});
