const form = document.querySelector("#promotion-form");
const status = document.querySelector("#promotion-status");

function applyPromotionTheme() {
  const dark = document.documentElement.dataset.theme === "dark";
  const button = document.querySelector("#theme-toggle");
  button.setAttribute("aria-pressed", String(dark));
  button.setAttribute("aria-label", dark ? "Ativar modo claro" : "Ativar modo escuro");
  document.querySelector("#theme-icon").textContent = dark ? "☀" : "☾";
  document.querySelector("#theme-label").textContent = dark ? "Modo claro" : "Modo escuro";
  document.querySelector('meta[name="theme-color"]').content = dark ? "#0b1411" : "#101b1a";
}

document.querySelector("#theme-toggle").addEventListener("click", () => {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem("skan-theme", next); } catch { /* local preference storage can be disabled */ }
  applyPromotionTheme();
});
applyPromotionTheme();

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const submit = form.querySelector("button[type=submit]");
  submit.disabled = true;
  status.textContent = "Enviando seu pedido…";
  const payload = Object.fromEntries(new FormData(form).entries());
  try {
    const response = await fetch(window.skanApiUrl("/api/promotion-requests"), {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Não foi possível enviar o pedido.");
    status.textContent = result.message;
    form.reset();
  } catch (error) {
    status.textContent = `${error.message} Abra esta página pelo servidor do Skan Coach.`;
  } finally {
    submit.disabled = false;
  }
});
