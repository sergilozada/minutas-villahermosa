const state = {
  user: null,
  csrfToken: null,
  schema: null,
  minutes: [],
  stats: { total: 0, borradores: 0, generadas: 0 },
  route: "dashboard",
  editingId: null,
  payload: {},
  wizardStep: 0,
  formErrors: {},
  dirty: false,
  search: "",
  statusFilter: "all",
  buyerStash: [],
  paymentStash: [],
  regularAmountManual: false,
};

const FIREBASE_CONFIG = Object.freeze({
  projectId: "minutas-villa-hermosa",
  appId: "1:860555340487:web:711f3de6b4430b6a626ce2",
  storageBucket: "minutas-villa-hermosa.firebasestorage.app",
  apiKey: "AIzaSyDY1h2VCJyCxZICnlKRpXxbLEVpG23THHw",
  authDomain: "minutas-villa-hermosa.firebaseapp.com",
  messagingSenderId: "860555340487",
});
const FIREBASE_HOSTS = new Set([
  "minutas-villa-hermosa.web.app",
  "minutas-villa-hermosa.firebaseapp.com",
]);
const USE_FIREBASE_BACKEND = FIREBASE_HOSTS.has(window.location.hostname);
const DOCUMENT_SERVICE_URL = "https://minutas-villahermosa.onrender.com/api/firebase/generate";
const AUTHORIZED_EMAILS = new Set([
  "inmobiliariaathouse@gmail.com",
  "asesor@villahermosa.com",
]);
let firebaseRuntime = null;

document.documentElement.classList.toggle("is-embedded", window.self !== window.top);

const elements = {
  loginView: document.querySelector("#login-view"),
  appView: document.querySelector("#app-view"),
  loginForm: document.querySelector("#login-form"),
  loginEmail: document.querySelector("#login-email"),
  loginPassword: document.querySelector("#login-password"),
  loginAlert: document.querySelector("#login-alert"),
  loginSubmit: document.querySelector("#login-submit"),
  togglePassword: document.querySelector("#toggle-password"),
  main: document.querySelector("#main-content"),
  title: document.querySelector("#topbar-title"),
  kicker: document.querySelector("#topbar-kicker"),
  profileName: document.querySelector("#profile-name"),
  profileButton: document.querySelector("#profile-button"),
  modalRoot: document.querySelector("#modal-root"),
  toastRegion: document.querySelector("#toast-region"),
};

const icons = {
  plus: '<svg aria-hidden="true" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>',
  arrow: '<svg aria-hidden="true" viewBox="0 0 24 24"><path d="M5 12h14M14 7l5 5-5 5"/></svg>',
  arrowLeft: '<svg aria-hidden="true" viewBox="0 0 24 24"><path d="m15 18-6-6 6-6"/></svg>',
  file: '<svg aria-hidden="true" viewBox="0 0 24 24"><path d="M6 2h9l4 4v16H6z"/><path d="M14 2v5h5M9 12h7M9 16h7"/></svg>',
  draft: '<svg aria-hidden="true" viewBox="0 0 24 24"><path d="M5 4h14v16H5z"/><path d="M8 8h8M8 12h5"/></svg>',
  checkFile: '<svg aria-hidden="true" viewBox="0 0 24 24"><path d="M6 2h9l4 4v16H6z"/><path d="M14 2v5h5m-9 9 2 2 4-4"/></svg>',
  search: '<svg aria-hidden="true" viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg>',
  edit: '<svg aria-hidden="true" viewBox="0 0 24 24"><path d="m4 16-.8 4.8L8 20l11-11-4-4L4 16Z"/><path d="m13.5 6.5 4 4"/></svg>',
  download: '<svg aria-hidden="true" viewBox="0 0 24 24"><path d="M12 3v12m0 0 4-4m-4 4-4-4M5 20h14"/></svg>',
  trash: '<svg aria-hidden="true" viewBox="0 0 24 24"><path d="M4 7h16M9 7V4h6v3m3 0-1 14H7L6 7"/><path d="M10 11v6M14 11v6"/></svg>',
  info: '<svg aria-hidden="true" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7h.01"/></svg>',
  warning: '<svg aria-hidden="true" viewBox="0 0 24 24"><path d="M12 3 2.5 20h19L12 3Z"/><path d="M12 9v5M12 17h.01"/></svg>',
  shield: '<svg aria-hidden="true" viewBox="0 0 24 24"><path d="M12 3 5 6v5c0 4.5 2.7 8.1 7 10 4.3-1.9 7-5.5 7-10V6l-7-3Z"/><path d="m9.5 12 1.7 1.7 3.5-3.7"/></svg>',
  logout: '<svg aria-hidden="true" viewBox="0 0 24 24"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5M21 12H9"/></svg>',
};

const routeMeta = {
  dashboard: { title: "Inicio", kicker: "Panel de gestión" },
  minutes: { title: "Minutas", kicker: "Expedientes y documentos" },
  "new-minute": { title: "Nueva minuta", kicker: "Plantilla financiada" },
};

document.addEventListener("DOMContentLoaded", initialize);

async function initialize() {
  bindStaticEvents();
  try {
    if (USE_FIREBASE_BACKEND) {
      await initializeFirebaseRuntime();
      const firebaseUser = firebaseRuntime.auth.currentUser;
      if (!firebaseUser || !AUTHORIZED_EMAILS.has(firebaseUser.email?.toLowerCase())) {
        if (firebaseUser) await firebaseRuntime.signOut(firebaseRuntime.auth);
        showLogin();
        return;
      }
      state.user = firebaseUserProfile(firebaseUser);
      await enterApplication();
      return;
    }
    const session = await api("/api/session", { suppressAuthRedirect: true });
    state.user = session.user;
    state.csrfToken = session.csrfToken;
    await enterApplication();
  } catch (error) {
    showLogin();
  }
}

function bindStaticEvents() {
  elements.loginForm.addEventListener("submit", handleLogin);
  elements.togglePassword.addEventListener("click", togglePasswordVisibility);
  elements.profileButton.addEventListener("click", openAccountModal);

  document.querySelectorAll("[data-route]").forEach((button) => {
    if (button.closest("#main-content")) return;
    button.addEventListener("click", () => requestNavigation(button.dataset.route));
  });

  document.querySelectorAll('[data-action="profile-menu"]').forEach((button) => {
    button.addEventListener("click", openAccountModal);
  });

  elements.main.addEventListener("click", handleMainClick);
  elements.main.addEventListener("input", handleFormInput);
  elements.main.addEventListener("change", handleFormInput);
  window.addEventListener("beforeunload", (event) => {
    if (!state.dirty) return;
    event.preventDefault();
    event.returnValue = "";
  });
}

async function handleLogin(event) {
  event.preventDefault();
  clearLoginErrors();
  const email = elements.loginEmail.value.trim().toLowerCase();
  const password = elements.loginPassword.value;
  let valid = true;

  if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/i.test(email)) {
    setLoginFieldError("email", "Ingresa un correo electrónico válido.");
    valid = false;
  }
  if (!password) {
    setLoginFieldError("password", "Ingresa tu contraseña.");
    valid = false;
  }
  if (!valid) {
    document.querySelector('#login-form [aria-invalid="true"]')?.focus();
    return;
  }

  setButtonBusy(elements.loginSubmit, true, "Ingresando…");
  try {
    const response = await api("/api/login", {
      method: "POST",
      body: { email, password },
      suppressAuthRedirect: true,
    });
    state.user = response.user;
    state.csrfToken = response.csrfToken;
    elements.loginPassword.value = "";
    await enterApplication();
  } catch (error) {
    elements.loginAlert.textContent = error.message;
    elements.loginAlert.hidden = false;
  } finally {
    setButtonBusy(elements.loginSubmit, false);
  }
}

function togglePasswordVisibility() {
  const show = elements.loginPassword.type === "password";
  elements.loginPassword.type = show ? "text" : "password";
  elements.togglePassword.setAttribute("aria-pressed", String(show));
  elements.togglePassword.setAttribute("aria-label", show ? "Ocultar contraseña" : "Mostrar contraseña");
}

function clearLoginErrors() {
  elements.loginAlert.hidden = true;
  elements.loginAlert.textContent = "";
  ["email", "password"].forEach((name) => {
    const input = document.querySelector(`#login-${name}`);
    const error = document.querySelector(`#login-${name}-error`);
    input.closest(".input-shell").classList.remove("is-invalid");
    input.removeAttribute("aria-invalid");
    error.textContent = "";
  });
}

function setLoginFieldError(name, message) {
  const input = document.querySelector(`#login-${name}`);
  input.closest(".input-shell").classList.add("is-invalid");
  input.setAttribute("aria-invalid", "true");
  document.querySelector(`#login-${name}-error`).textContent = message;
}

async function enterApplication() {
  elements.loginView.hidden = true;
  elements.appView.hidden = false;
  document.body.classList.add("is-authenticated");
  hydrateProfile();
  renderLoading();
  try {
    const [schema, minutesResponse, stats] = await Promise.all([
      api("/api/schema"),
      api("/api/minutes"),
      api("/api/stats"),
    ]);
    state.schema = schema;
    state.minutes = minutesResponse.items || [];
    state.stats = stats;
    navigate("dashboard");
  } catch (error) {
    renderFatalError(error.message);
  }
}

function showLogin() {
  resetSessionState();
  elements.appView.inert = false;
  elements.modalRoot.innerHTML = "";
  elements.appView.hidden = true;
  elements.loginView.hidden = false;
  document.body.classList.remove("is-authenticated");
  elements.loginEmail.value = "";
  elements.loginPassword.value = "";
  window.setTimeout(() => elements.loginEmail.focus(), 40);
}

function resetSessionState() {
  Object.assign(state, {
    user: null,
    csrfToken: null,
    schema: null,
    minutes: [],
    stats: { total: 0, borradores: 0, generadas: 0 },
    route: "dashboard",
    editingId: null,
    payload: {},
    wizardStep: 0,
    formErrors: {},
    dirty: false,
    search: "",
    statusFilter: "all",
    buyerStash: [],
    paymentStash: [],
    regularAmountManual: false,
  });
}

function hydrateProfile() {
  const roleLabel = state.user.role === "admin" ? "Admin" : "Asesor";
  elements.profileName.textContent = roleLabel;
  elements.profileButton.setAttribute("aria-label", `Abrir cuenta de ${roleLabel}`);
}

async function performLogout() {
  try {
    await api("/api/logout", { method: "POST" });
  } catch (error) {
    // Clear the local state even when the session already expired.
  }
  showLogin();
}

function requestLogout() {
  if (!state.dirty) {
    performLogout();
    return;
  }
  confirmDiscardChanges(performLogout, "Se descartarán los datos de la minuta y se cerrará la sesión.");
}

function openAccountModal() {
  const discarding = state.dirty;
  showModal({
    title: state.user.display_name,
    message: `${state.user.email} · ${state.user.role === "admin" ? "Administrador" : "Asesor"}${discarding ? ". Hay cambios sin guardar que se descartarán al cerrar la sesión." : ""}`,
    icon: icons.shield,
    confirmLabel: discarding ? "Descartar y cerrar sesión" : "Cerrar sesión",
    confirmClass: "button--secondary",
    onConfirm: async () => {
      state.dirty = false;
      await performLogout();
    },
  });
}

function confirmDiscardChanges(action, message = "Se perderán los cambios que todavía no guardaste.") {
  showModal({
    title: "¿Descartar cambios?",
    message,
    icon: icons.warning,
    confirmLabel: "Descartar cambios",
    confirmClass: "button--danger",
    onConfirm: async () => {
      state.dirty = false;
      await action();
    },
  });
}

function requestNavigation(route) {
  if (route === state.route) return;
  if (state.dirty) confirmDiscardChanges(() => navigate(route));
  else navigate(route);
}

function navigate(route, options = {}) {
  state.route = route;
  const meta = routeMeta[route] || routeMeta.dashboard;
  elements.title.textContent = meta.title;
  elements.kicker.textContent = meta.kicker;
  document.title = `${meta.title} · Minutas Villa Hermosa`;
  updateNavigation(route);

  if (route === "dashboard") renderDashboard();
  if (route === "minutes") renderMinutes();
  if (route === "new-minute") renderWizard();
  if (options.focus !== false) {
    const target = route === "new-minute" ? document.querySelector("#wizard-title") : elements.main;
    target?.focus({ preventScroll: true });
  }
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  window.scrollTo({ top: 0, behavior: reduceMotion ? "auto" : "smooth" });
}

function updateNavigation(route) {
  document.querySelectorAll("[data-route]").forEach((button) => {
    const active = button.dataset.route === route;
    button.classList.toggle("is-active", active);
    if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
}

function renderLoading() {
  elements.main.innerHTML = '<div class="loading-state" role="status" aria-live="polite"><span class="spinner" aria-hidden="true"></span><span class="sr-only">Cargando el sistema…</span></div>';
}

function renderFatalError(message) {
  elements.main.innerHTML = `
    <section class="section-card empty-state" role="alert">
      <div class="empty-state__inner">
        <span class="empty-state__icon">${icons.warning}</span>
        <h3>No pudimos cargar el sistema</h3>
        <p>${escapeHtml(message)}</p>
        <button class="button button--primary" type="button" data-action="reload">Reintentar</button>
      </div>
    </section>`;
}

function renderDashboard() {
  const recent = state.minutes.slice(0, 5);
  elements.main.innerHTML = `
    <div class="page-stack">
      <section class="hero-card" aria-labelledby="hero-title">
        <div class="hero-card__copy">
          <span class="eyebrow eyebrow--light">Condominio Villa Hermosa</span>
          <h2 id="hero-title">Convierte los datos del cliente en una minuta lista.</h2>
          <p>La plantilla legal queda protegida. Tú completas el formulario, el sistema valida los importes y genera el documento.</p>
          <button class="button button--primary" type="button" data-action="new-minute">${icons.plus}<span>Crear nueva minuta</span></button>
        </div>
        <div class="hero-card__aside" aria-hidden="true">
          <img class="hero-card__wordmark" src="/assets/villa-hermosa-wordmark.png" alt="" />
        </div>
      </section>

      <section class="metrics-grid" aria-label="Resumen de minutas">
        ${metricCard("Minutas totales", state.stats.total, "Expedientes registrados", icons.file, "")}
        ${metricCard("Borradores", state.stats.borradores, "Pendientes de revisión", icons.draft, "gold")}
        ${metricCard("Generadas", state.stats.generadas, "Documentos descargados", icons.checkFile, "green")}
      </section>

      <section class="section-card" aria-labelledby="recent-title">
        <header class="section-card__header">
          <div><h2 id="recent-title">Actividad reciente</h2><p>Últimas minutas creadas o actualizadas.</p></div>
          <button class="text-link" type="button" data-action="view-all">Ver todas ${icons.arrow}</button>
        </header>
        ${recent.length ? recordsTable(recent) : emptyRecords("Todavía no hay minutas", "Crea el primer expediente para comenzar.")}
      </section>
    </div>`;
}

function metricCard(label, value, hint, icon, modifier) {
  return `
    <article class="metric-card">
      <div class="metric-card__copy">
        <span class="metric-card__label">${escapeHtml(label)}</span>
        <strong class="metric-card__value">${Number(value || 0).toLocaleString("es-PE")}</strong>
        <span class="metric-card__hint">${escapeHtml(hint)}</span>
      </div>
      <span class="metric-card__icon ${modifier ? `metric-card__icon--${modifier}` : ""}">${icon}</span>
    </article>`;
}

function renderMinutes() {
  const query = state.search.trim().toLocaleLowerCase("es");
  const items = state.minutes.filter((item) => {
    const matchesStatus = state.statusFilter === "all" || item.status === state.statusFilter;
    const haystack = [
      item.reference,
      item.client_name,
      item.document_number,
      item.payload?.lote,
      item.payload?.manzana,
      item.owner_name,
      ...(Array.isArray(item.payload?.compradores)
        ? item.payload.compradores.flatMap((buyer) => Object.values(buyer || {}))
        : []),
    ]
      .join(" ")
      .toLocaleLowerCase("es");
    return matchesStatus && (!query || haystack.includes(query));
  });

  elements.main.innerHTML = `
    <div class="page-stack">
      <section class="toolbar" aria-label="Buscar y filtrar minutas">
        <label class="search-box">
          ${icons.search}
          <span class="sr-only">Buscar minutas</span>
          <input id="minute-search" type="search" value="${escapeAttribute(state.search)}" placeholder="Buscar por cliente, DNI, lote o referencia" autocomplete="off" />
        </label>
        <div class="filter-tabs" role="group" aria-label="Filtrar por estado">
          ${filterButton("all", "Todas")}
          ${filterButton("borrador", "Borradores")}
          ${filterButton("generada", "Generadas")}
        </div>
      </section>

      <section class="section-card" aria-label="Listado de minutas">
        <header class="section-card__header">
          <div><h2>${items.length} ${items.length === 1 ? "minuta" : "minutas"}</h2><p>Accede, corrige o descarga el documento.</p></div>
          <button class="button button--primary" type="button" data-action="new-minute">${icons.plus}<span>Nueva minuta</span></button>
        </header>
        ${items.length ? recordsTable(items, true) : emptyRecords("No hay resultados", "Prueba con otra búsqueda o crea una minuta nueva.")}
      </section>
    </div>`;
}

function filterButton(value, label) {
  const active = state.statusFilter === value;
  return `<button class="filter-tab ${active ? "is-active" : ""}" type="button" data-action="filter" data-filter="${value}" aria-pressed="${active}">${label}</button>`;
}

function recordsTable(items, showOwner = false) {
  return `
    <div class="records-table-wrap">
      <table class="records-table">
        <thead><tr>
          <th>Compradores</th><th>Inmueble</th><th>Referencia</th>${showOwner && state.user.role === "admin" ? "<th>Responsable</th>" : ""}<th>Estado</th><th>Actualizada</th><th><span class="sr-only">Acciones</span></th>
        </tr></thead>
        <tbody>${items.map((item) => recordRow(item, showOwner)).join("")}</tbody>
      </table>
    </div>
    <div class="records-mobile">${items.map(recordCard).join("")}</div>`;
}

function recordRow(item, showOwner) {
  const property = `Mz. ${item.payload?.manzana || "—"} · Lt. ${item.payload?.lote || "—"}`;
  const buyerName = buyerSummary(item);
  const buyerDocument = buyerDocumentSummary(item);
  return `<tr>
    <td><div class="record-person"><span class="record-avatar">${initials(buyerName || "VH")}</span><span><strong>${escapeHtml(buyerName || "Sin nombre")}</strong><small>${escapeHtml(buyerDocument)}</small></span></div></td>
    <td><span class="record-primary">${escapeHtml(property)}</span><span class="record-secondary">${formatArea(item.payload?.area_m2)}</span></td>
    <td><span class="record-primary">${escapeHtml(item.reference)}</span></td>
    ${showOwner && state.user.role === "admin" ? `<td><span class="record-secondary">${escapeHtml(item.owner_name)}</span></td>` : ""}
    <td>${statusPill(item.status)}</td>
    <td><span class="record-secondary">${formatDateTime(item.updated_at)}</span></td>
    <td>${rowActions(item)}</td>
  </tr>`;
}

function recordCard(item) {
  const buyerName = buyerSummary(item);
  return `<article class="record-card">
    <div class="record-card__top">
      <div class="record-person"><span class="record-avatar">${initials(buyerName || "VH")}</span><span><strong>${escapeHtml(buyerName || "Sin nombre")}</strong><small>${escapeHtml(item.reference)}</small></span></div>
      ${statusPill(item.status)}
    </div>
    <div class="record-card__meta">
      <div><span>Documentos</span><strong>${escapeHtml(buyerDocumentSummary(item))}</strong></div>
      <div><span>Inmueble</span><strong>Mz. ${escapeHtml(item.payload?.manzana || "—")} · Lt. ${escapeHtml(item.payload?.lote || "—")}</strong></div>
      <div><span>Actualizada</span><strong>${formatShortDate(item.updated_at)}</strong></div>
      ${state.user.role === "admin" ? `<div><span>Responsable</span><strong>${escapeHtml(item.owner_name || "—")}</strong></div>` : ""}
    </div>
    <div class="record-card__actions">
      <button class="button button--secondary" type="button" data-action="edit" data-id="${item.id}">${icons.edit}<span>Editar</span></button>
      <button class="button button--primary" type="button" data-action="generate" data-id="${item.id}">${icons.download}<span>Descargar</span></button>
      ${state.user.role === "admin" ? `<button class="button button--danger" type="button" data-action="delete" data-id="${item.id}">${icons.trash}<span>Eliminar</span></button>` : ""}
    </div>
  </article>`;
}

function buyerSummary(item) {
  const names = Array.isArray(item.payload?.compradores)
    ? item.payload.compradores.map((buyer) => String(buyer?.nombre_completo || "").trim()).filter(Boolean)
    : [];
  if (!names.length) return item.client_name || "";
  return names.length === 1 ? names[0] : `${names[0]} y ${names.length - 1} más`;
}

function buyerDocumentSummary(item) {
  const documents = Array.isArray(item.payload?.compradores)
    ? item.payload.compradores.map((buyer) => String(buyer?.documento || "").trim()).filter(Boolean)
    : [];
  if (!documents.length) return item.document_number ? `DNI ${item.document_number}` : "DNI pendiente";
  return documents.length === 1 ? `DNI ${documents[0]}` : `${documents.length} DNI registrados`;
}

function rowActions(item) {
  return `<div class="row-actions">
    <button class="icon-button" type="button" data-action="edit" data-id="${item.id}" aria-label="Editar ${escapeAttribute(item.client_name)}" title="Editar">${icons.edit}</button>
    <button class="icon-button" type="button" data-action="generate" data-id="${item.id}" aria-label="Generar minuta de ${escapeAttribute(item.client_name)}" title="Generar y descargar">${icons.download}</button>
    ${state.user.role === "admin" ? `<button class="icon-button" type="button" data-action="delete" data-id="${item.id}" aria-label="Eliminar minuta de ${escapeAttribute(item.client_name)}" title="Eliminar">${icons.trash}</button>` : ""}
  </div>`;
}

function statusPill(status) {
  const generated = status === "generada";
  return `<span class="status-pill ${generated ? "status-pill--generated" : ""}">${generated ? "Generada" : "Borrador"}</span>`;
}

function emptyRecords(title, message) {
  return `<div class="empty-state"><div class="empty-state__inner">
    <span class="empty-state__icon">${icons.file}</span><h3>${escapeHtml(title)}</h3><p>${escapeHtml(message)}</p>
    <button class="button button--primary" type="button" data-action="new-minute">${icons.plus}<span>Nueva minuta</span></button>
  </div></div>`;
}

function startNewMinute() {
  if (!state.schema) return;
  state.editingId = null;
  state.payload = defaultPayload();
  state.payload.fecha_firma = todayIso();
  state.wizardStep = 0;
  state.formErrors = {};
  state.buyerStash = [];
  state.paymentStash = [];
  state.regularAmountManual = false;
  state.dirty = false;
  navigate("new-minute");
}

function requestStartNewMinute() {
  if (state.dirty) confirmDiscardChanges(startNewMinute);
  else startNewMinute();
}

function editMinute(id) {
  const item = state.minutes.find((minute) => minute.id === id);
  if (!item) return;
  state.editingId = id;
  state.payload = normalizeEditorPayload(item.payload);
  state.regularAmountManual = hasValue(state.payload.monto_cuota_regular);
  state.wizardStep = 0;
  state.formErrors = {};
  state.buyerStash = [];
  state.paymentStash = [];
  state.dirty = false;
  navigate("new-minute");
}

function requestEditMinute(id) {
  if (state.dirty) confirmDiscardChanges(() => editMinute(id));
  else editMinute(id);
}

function defaultPayload() {
  const payload = {};
  state.schema.sections.forEach((section) => {
    if (section.repeatable) {
      payload[section.payloadKey || section.id] = [defaultRepeatableItem(section)];
      return;
    }
    section.fields.forEach((field) => {
      if (Object.prototype.hasOwnProperty.call(field, "default")) payload[field.id] = field.default;
      else payload[field.id] = field.type === "checkbox" ? false : "";
    });
    (section.groups || []).filter((group) => group.repeatable).forEach((group) => {
      payload[group.payloadKey || group.id] = [defaultRepeatableItem(group)];
    });
  });
  return computePayload(payload);
}

function defaultRepeatableItem(section) {
  return Object.fromEntries(section.fields.map((field) => [
    field.id,
    Object.prototype.hasOwnProperty.call(field, "default")
      ? field.default
      : field.type === "checkbox" ? false : "",
  ]));
}

function repeatableSection() {
  return state.schema.sections.find((section) => section.repeatable);
}

function paymentGroup() {
  return state.schema.sections
    .flatMap((section) => section.groups || [])
    .find((group) => group.payloadKey === "pagos_iniciales" || group.id === "initial_payments");
}

function normalizeEditorPayload(rawPayload = {}) {
  const defaults = defaultPayload();
  const incoming = rawPayload && typeof rawPayload === "object" ? rawPayload : {};
  const result = { ...defaults, ...incoming };
  const section = repeatableSection();
  if (section) {
    const payloadKey = section.payloadKey || section.id;
    let items = Array.isArray(incoming[payloadKey]) ? incoming[payloadKey] : null;
    if (!items) {
      const legacy = {};
      let foundLegacy = false;
      section.fields.forEach((field) => {
        const legacyKey = `comprador_${field.id}`;
        if (Object.prototype.hasOwnProperty.call(incoming, legacyKey)) {
          legacy[field.id] = incoming[legacyKey];
          foundLegacy = true;
        }
      });
      items = foundLegacy ? [legacy] : [];
    }
    result[payloadKey] = (items.length ? items : [{}]).map((item) => ({
      ...defaultRepeatableItem(section),
      ...(item && typeof item === "object" ? item : {}),
    }));
  }
  const group = paymentGroup();
  if (group) {
    const payloadKey = group.payloadKey || group.id;
    let items = Array.isArray(incoming[payloadKey]) ? incoming[payloadKey] : null;
    if (!items) {
      const hasLegacyPayment = hasValue(incoming.numero_operacion) || hasValue(incoming.fecha_pago_inicial);
      items = hasLegacyPayment ? [{
        metodo: "transferencia_bancaria",
        monto: incoming.cuota_inicial,
        numero_operacion: incoming.numero_operacion,
        fecha_pago: incoming.fecha_pago_inicial,
      }] : [];
    }
    result[payloadKey] = (items.length ? items : [{}]).map((item) => ({
      ...defaultRepeatableItem(group),
      ...(item && typeof item === "object" ? item : {}),
    }));
    delete result.numero_operacion;
    delete result.fecha_pago_inicial;
  }
  if (!hasValue(result.numero_cuotas_total) && hasValue(incoming.numero_cuotas_regulares)) {
    const legacyRegular = numeric(incoming.numero_cuotas_regulares);
    if (legacyRegular !== null && Number.isInteger(legacyRegular)) {
      result.numero_cuotas_total = legacyRegular + 1;
    }
  }
  return computePayload(result);
}

function computePayload(payload, options = {}) {
  const result = { ...payload };
  const price = numeric(result.precio_total);
  const initial = numeric(result.cuota_inicial);
  const total = numeric(result.numero_cuotas_total);
  result.saldo_financiado = price !== null && initial !== null ? roundMoney(price - initial) : "";
  const validTotal = total !== null && Number.isInteger(total) && total >= 1;
  result.numero_cuotas_regulares = validTotal ? total - 1 : "";
  if (options.autoRegular) {
    result.monto_cuota_regular = result.saldo_financiado !== ""
      && Number(result.saldo_financiado) > 0
      && validTotal
      ? roundMoney(Number(result.saldo_financiado) / total)
      : "";
  }
  const regular = numeric(result.monto_cuota_regular);
  result.monto_cuota_final = result.saldo_financiado !== "" && validTotal && regular !== null
    ? roundMoney(Number(result.saldo_financiado) - (total - 1) * regular)
    : "";
  const payments = Array.isArray(result.pagos_iniciales) ? result.pagos_iniciales : [];
  const paymentAmounts = payments
    .map((payment) => numeric(payment?.monto))
    .filter((amount) => amount !== null);
  result.total_pagos_iniciales = paymentAmounts.length
    ? paymentAmounts.reduce((sum, amount) => sum + moneyCents(amount), 0) / 100
    : "";
  return result;
}

function renderWizard() {
  if (!state.schema) return renderLoading();
  if (!Object.keys(state.payload).length) state.payload = defaultPayload();
  state.payload = computePayload(state.payload);
  const section = state.schema.sections[state.wizardStep];
  const progress = completionProgress();
  const record = state.editingId ? state.minutes.find((item) => item.id === state.editingId) : null;

  elements.main.innerHTML = `
    <div class="wizard-layout page-stack">
      <section class="wizard-card" aria-labelledby="wizard-title">
        <nav class="wizard-progress" aria-label="Pasos del formulario">
          ${state.schema.sections.map((item, index) => wizardStepButton(item, index)).join("")}
        </nav>
        <form id="minute-form" class="wizard-content" novalidate>
          <header class="wizard-heading">
            <p class="wizard-heading__step">Paso ${state.wizardStep + 1} de ${state.schema.sections.length}${record ? ` · ${escapeHtml(record.reference)}` : ""}</p>
            <h2 id="wizard-title" tabindex="-1">${escapeHtml(section.title)}</h2>
            <p>${escapeHtml(section.description)}</p>
          </header>
          ${section.repeatable
            ? renderRepeatableSection(section)
            : renderStandardSection(section)}
          ${state.wizardStep === state.schema.sections.length - 1 ? `<div id="review-summary">${reviewSummary()}</div>` : ""}
          <div class="wizard-actions">
            <button class="button button--ghost" type="button" data-action="previous-step" ${state.wizardStep === 0 ? "disabled" : ""}>${icons.arrowLeft}<span>Anterior</span></button>
            <div class="wizard-actions__end">
              <button class="button button--secondary" type="button" data-action="save-draft">Guardar borrador</button>
              ${state.wizardStep < state.schema.sections.length - 1
                ? `<button class="button button--primary" type="button" data-action="next-step"><span>Continuar</span>${icons.arrow}</button>`
                : `<button class="button button--primary" type="button" data-action="generate-current">${icons.download}<span>Generar minuta</span></button>`}
            </div>
          </div>
        </form>
      </section>

      <aside class="wizard-aside" aria-label="Estado del documento">
        <section class="aside-card">
          <h3>Avance del expediente</h3>
          <div class="aside-progress" aria-hidden="true"><span id="aside-progress-bar" style="width:${progress.percent}%"></span></div>
          <div class="aside-progress-label"><span id="aside-progress-copy">${progress.completed} de ${progress.total} datos listos</span><strong id="aside-progress-percent">${progress.percent}%</strong></div>
        </section>
        <section class="aside-card">
          <h3>Cobertura automática</h3>
          <ul class="coverage-list">
            <li><span class="coverage-list__check">✓</span>Compradores múltiples</li>
            <li><span class="coverage-list__check">✓</span>Montos en letras y centavos</li>
            <li><span class="coverage-list__check">✓</span>Saldo, cuotas y cronograma</li>
            <li><span class="coverage-list__check">✓</span>Fechas en formato contractual</li>
          </ul>
        </section>
      </aside>
    </div>`;
  applyRenderedErrors();
}

function wizardStepButton(section, index) {
  const complete = sectionComplete(section);
  const current = index === state.wizardStep;
  const accessibleLabel = `${section.shortTitle}: ${complete ? "completo" : "pendiente"}${current ? ", paso actual" : ""}`;
  return `<button class="wizard-step ${current ? "is-active" : ""} ${complete ? "is-complete" : ""}" type="button" data-action="wizard-step" data-step="${index}" aria-label="${escapeAttribute(accessibleLabel)}" ${current ? 'aria-current="step"' : ""}>
    <span class="wizard-step__number">${complete && index !== state.wizardStep ? "✓" : index + 1}</span>
    <span class="wizard-step__label">${escapeHtml(section.shortTitle)}<small>${complete ? "Completo" : "Pendiente"}</small></span>
  </button>`;
}

function renderRepeatableSection(section) {
  const payloadKey = section.payloadKey || section.id;
  const buyers = Array.isArray(state.payload[payloadKey]) && state.payload[payloadKey].length
    ? state.payload[payloadKey]
    : [defaultRepeatableItem(section)];
  const minimum = Number(section.minItems || 1);
  const maximum = Number(section.maxItems || 10);
  const options = Array.from({ length: maximum - minimum + 1 }, (_, index) => minimum + index)
    .map((count) => `<option value="${count}" ${count === buyers.length ? "selected" : ""}>${count}</option>`)
    .join("");
  return `<div class="buyers-editor">
    <div class="buyers-toolbar">
      <div class="field-group buyer-count-field">
        <label for="buyer-count">${escapeHtml(section.countLabel || "Cantidad de compradores")}</label>
        <div class="input-shell">
          <select id="buyer-count" data-buyer-count aria-controls="buyers-list" aria-describedby="buyer-count-help buyer-count-status">${options}</select>
        </div>
        <p class="field-help" id="buyer-count-help">${escapeHtml(section.countHelp || "")}</p>
      </div>
      <p id="buyer-count-status" class="buyer-count-status" aria-live="polite">${buyers.length} ${buyers.length === 1 ? "comprador registrado" : "compradores registrados"}</p>
    </div>
    <div id="buyers-list" class="buyers-list">
      ${buyers.map((buyer, index) => `<fieldset class="buyer-card">
        <legend><span>Comprador ${index + 1}</span><small>${escapeHtml(buyer.nombre_completo || "Datos pendientes")}</small></legend>
        <div class="form-grid buyer-card__grid">
          ${section.fields.map((field) => renderBuyerField(field, buyer, index, payloadKey)).join("")}
        </div>
      </fieldset>`).join("")}
    </div>
  </div>`;
}

function renderBuyerField(field, buyer, index, payloadKey) {
  const domId = `buyer-${index}-${field.id}`;
  const errorKey = `${payloadKey}.${index}.${field.id}`;
  const autocomplete = field.autocomplete
    ? `section-buyer-${index + 1} ${field.autocomplete}`
    : "off";
  return renderField(
    { ...field, id: domId, autocomplete },
    {
      value: buyer[field.id] ?? "",
      errorKey,
      dataAttributes: `data-buyer-index="${index}" data-buyer-field="${escapeAttribute(field.id)}"`,
    },
  );
}

function renderStandardSection(section) {
  const groups = (section.groups || []).filter((group) => group.repeatable);
  const rendered = [];
  section.fields.forEach((field) => {
    rendered.push(renderField(field));
    groups
      .filter((group) => group.afterField === field.id)
      .forEach((group) => rendered.push(renderPaymentGroup(group)));
  });
  groups
    .filter((group) => !section.fields.some((field) => field.id === group.afterField))
    .forEach((group) => rendered.push(renderPaymentGroup(group)));
  return `<div class="form-grid">${rendered.join("")}</div>`;
}

function renderPaymentGroup(group) {
  const payloadKey = group.payloadKey || group.id;
  const payments = Array.isArray(state.payload[payloadKey]) && state.payload[payloadKey].length
    ? state.payload[payloadKey]
    : [defaultRepeatableItem(group)];
  const minimum = Number(group.minItems || 1);
  const maximum = Number(group.maxItems || 20);
  const options = Array.from({ length: maximum - minimum + 1 }, (_, index) => minimum + index)
    .map((count) => `<option value="${count}" ${count === payments.length ? "selected" : ""}>${count}</option>`)
    .join("");
  const registered = numeric(state.payload.total_pagos_iniciales);
  const expected = numeric(state.payload.cuota_inicial);
  const reconciled = registered !== null && expected !== null && moneyCents(registered) === moneyCents(expected);
  const statusClass = registered === null || expected === null
    ? ""
    : reconciled ? "is-reconciled" : "is-pending";
  const groupError = state.formErrors[payloadKey] || "";
  return `<section class="payments-editor form-field--full" aria-labelledby="payments-title">
    <div class="buyers-toolbar payments-toolbar">
      <div class="field-group payment-count-field">
        <label id="payments-title" for="payment-count">${escapeHtml(group.countLabel || "Cantidad de pagos")}</label>
        <div class="input-shell">
          <select id="payment-count" data-payment-count aria-controls="payments-list" aria-describedby="payment-count-help payment-count-status">${options}</select>
        </div>
        <p class="field-help" id="payment-count-help">${escapeHtml(group.countHelp || "")}</p>
      </div>
      <p id="payment-count-status" class="payment-count-status ${statusClass}" aria-live="polite">
        <strong>${payments.length} ${payments.length === 1 ? "pago" : "pagos"}</strong>
        <span>${formatCurrency(state.payload.total_pagos_iniciales)} de ${formatCurrency(state.payload.cuota_inicial)}</span>
      </p>
    </div>
    <div id="payments-list" class="buyers-list payments-list">
      ${payments.map((payment, index) => `<fieldset class="buyer-card payment-card">
        <legend><span>${escapeHtml(group.itemLabel || "Pago")} ${index + 1}</span><small>${escapeHtml(paymentMethodLabel(payment.metodo) || "Datos pendientes")}</small></legend>
        <div class="form-grid payment-card__grid">
          ${group.fields.map((field) => renderPaymentField(field, payment, index, payloadKey)).join("")}
        </div>
      </fieldset>`).join("")}
    </div>
    <p class="field-error payment-group-error" id="${payloadKey}-error">${escapeHtml(groupError)}</p>
  </section>`;
}

function renderPaymentField(field, payment, index, payloadKey) {
  const domId = `payment-${index}-${field.id}`;
  const errorKey = `${payloadKey}.${index}.${field.id}`;
  return renderField(
    { ...field, id: domId },
    {
      value: payment[field.id] ?? "",
      errorKey,
      dataAttributes: `data-payment-index="${index}" data-payment-field="${escapeAttribute(field.id)}"`,
    },
  );
}

function paymentMethodLabel(value) {
  const group = paymentGroup();
  const field = group?.fields.find((item) => item.id === "metodo");
  return field?.options?.find((option) => option.value === value)?.label || "";
}

function renderField(field, options = {}) {
  const value = Object.prototype.hasOwnProperty.call(options, "value") ? options.value : state.payload[field.id] ?? "";
  const errorKey = options.errorKey || field.id;
  const dataAttributes = options.dataAttributes || `data-field="${escapeAttribute(field.id)}"`;
  const classes = `field-group form-field ${field.fullWidth ? "form-field--full" : ""}`;
  const error = state.formErrors[errorKey] || "";
  const describedBy = [field.help ? `${field.id}-help` : "", `${field.id}-error`].filter(Boolean).join(" ");

  if (field.type === "checkbox") {
    return `<div class="${classes}">
      <label class="checkbox-field ${error ? "is-invalid" : ""}" for="${field.id}">
        <input id="${field.id}" name="${field.id}" type="checkbox" ${dataAttributes} ${value ? "checked" : ""} aria-describedby="${describedBy}" ${field.required ? 'required aria-required="true"' : ""} ${error ? 'aria-invalid="true"' : ""} />
        <span class="checkbox-field__copy"><strong>${escapeHtml(field.label)}${field.required ? " *" : ""}</strong>${field.help ? `<small id="${field.id}-help">${escapeHtml(field.help)}</small>` : ""}</span>
      </label>
      <p class="field-error" id="${field.id}-error">${escapeHtml(error)}</p>
    </div>`;
  }

  const input = field.type === "select"
    ? renderSelect(field, value, describedBy, error, dataAttributes)
    : renderInput(field, value, describedBy, error, dataAttributes);
  return `<div class="${classes}">
    <label for="${field.id}">${escapeHtml(field.label)}${field.required ? " *" : ""}</label>
    <div class="input-shell ${field.computed ? "is-computed" : ""} ${error ? "is-invalid" : ""}">
      ${field.prefix ? `<span class="input-prefix">${escapeHtml(field.prefix)}</span>` : ""}
      ${input}
      ${field.suffix ? `<span class="input-suffix">${escapeHtml(field.suffix)}</span>` : ""}
    </div>
    ${field.help ? `<p class="field-help" id="${field.id}-help">${escapeHtml(field.help)}</p>` : ""}
    <p class="field-error" id="${field.id}-error">${escapeHtml(error)}</p>
  </div>`;
}

function renderInput(field, value, describedBy, error, dataAttributes) {
  const type = ["email", "tel", "date", "number"].includes(field.type) ? field.type : "text";
  const attributes = [
    `id="${field.id}"`,
    `name="${field.id}"`,
    `type="${type}"`,
    dataAttributes,
    `value="${escapeAttribute(value)}"`,
    field.placeholder ? `placeholder="${escapeAttribute(field.placeholder)}"` : "",
    field.autocomplete ? `autocomplete="${escapeAttribute(field.autocomplete)}"` : "autocomplete=\"off\"",
    field.inputmode ? `inputmode="${escapeAttribute(field.inputmode)}"` : "",
    field.maxlength ? `maxlength="${Number(field.maxlength)}"` : "",
    field.min !== undefined ? `min="${Number(field.min)}"` : "",
    field.max !== undefined ? `max="${Number(field.max)}"` : "",
    field.step ? `step="${escapeAttribute(field.step)}"` : "",
    field.required ? 'required aria-required="true"' : "",
    field.computed ? "readonly aria-readonly=\"true\"" : "",
    describedBy ? `aria-describedby="${describedBy}"` : "",
    error ? 'aria-invalid="true"' : "",
  ].filter(Boolean).join(" ");
  return `<input ${attributes} />`;
}

function renderSelect(field, value, describedBy, error, dataAttributes) {
  return `<select id="${field.id}" name="${field.id}" ${dataAttributes} ${field.required ? 'required aria-required="true"' : ""} ${describedBy ? `aria-describedby="${describedBy}"` : ""} ${error ? 'aria-invalid="true"' : ""}>
    <option value="">Selecciona una opción</option>
    ${(field.options || []).map((option) => `<option value="${escapeAttribute(option.value)}" ${String(value) === String(option.value) ? "selected" : ""}>${escapeHtml(option.label)}</option>`).join("")}
  </select>`;
}

function handleFormInput(event) {
  const paymentCountControl = event.target.closest("[data-payment-count]");
  if (paymentCountControl) {
    if (event.type === "change") resizePaymentList(Number(paymentCountControl.value));
    return;
  }
  const countControl = event.target.closest("[data-buyer-count]");
  if (countControl) {
    if (event.type === "change") resizeBuyerList(Number(countControl.value));
    return;
  }
  const paymentInput = event.target.closest("[data-payment-field]");
  const buyerInput = event.target.closest("[data-buyer-field]");
  const input = event.target.closest("[data-field]");
  if ((!input && !buyerInput && !paymentInput) || state.route !== "new-minute") return;

  let field;
  let errorKey;
  let value;
  let changedFieldId = "";
  if (paymentInput) {
    const group = paymentGroup();
    const payloadKey = group.payloadKey || group.id;
    const index = Number(paymentInput.dataset.paymentIndex);
    const fieldId = paymentInput.dataset.paymentField;
    const payments = Array.isArray(state.payload[payloadKey]) ? state.payload[payloadKey] : [];
    if (!payments[index]) payments[index] = defaultRepeatableItem(group);
    value = paymentInput.type === "checkbox" ? paymentInput.checked : paymentInput.value;
    payments[index][fieldId] = value;
    state.payload[payloadKey] = payments;
    field = group.fields.find((item) => item.id === fieldId);
    errorKey = `${payloadKey}.${index}.${fieldId}`;
  } else if (buyerInput) {
    const section = repeatableSection();
    const payloadKey = section.payloadKey || section.id;
    const index = Number(buyerInput.dataset.buyerIndex);
    const fieldId = buyerInput.dataset.buyerField;
    const buyers = Array.isArray(state.payload[payloadKey]) ? state.payload[payloadKey] : [];
    if (!buyers[index]) buyers[index] = defaultRepeatableItem(section);
    value = buyerInput.type === "checkbox" ? buyerInput.checked : buyerInput.value;
    buyers[index][fieldId] = value;
    state.payload[payloadKey] = buyers;
    field = section.fields.find((item) => item.id === fieldId);
    errorKey = `${payloadKey}.${index}.${fieldId}`;
  } else {
    const id = input.dataset.field;
    changedFieldId = id;
    value = input.type === "checkbox" ? input.checked : input.value;
    state.payload[id] = value;
    field = state.schema.sections.flatMap((section) => section.fields).find((item) => item.id === id);
    errorKey = id;
  }
  if (changedFieldId === "monto_cuota_regular") {
    state.regularAmountManual = !(event.type === "change" && !hasValue(value));
  }
  state.payload = computePayload(state.payload, {
    autoRegular: !state.regularAmountManual,
  });
  state.dirty = true;
  const error = field ? validateField(field, value) : "";
  if (error) {
    state.formErrors[errorKey] = error;
    setRenderedFieldError(errorKey, error);
  } else {
    delete state.formErrors[errorKey];
    clearRenderedFieldError(errorKey);
  }
  if (!state.regularAmountManual && hasValue(state.payload.monto_cuota_regular)) {
    delete state.formErrors.monto_cuota_regular;
    clearRenderedFieldError("monto_cuota_regular");
  }
  const crossErrors = crossFieldErrors();
  const crossMessages = new Set([
    "La cuota inicial no puede superar el precio total.",
    "La cuota final debe ser mayor a cero; ajusta el total o el monto regular.",
  ]);
  ["cuota_inicial", "monto_cuota_regular"].forEach((crossId) => {
    if (crossErrors[crossId]) {
      state.formErrors[crossId] = crossErrors[crossId];
      setRenderedFieldError(crossId, crossErrors[crossId]);
    } else if (crossMessages.has(state.formErrors[crossId])) {
      delete state.formErrors[crossId];
      clearRenderedFieldError(crossId);
    }
  });
  const group = paymentGroup();
  const paymentKey = group?.payloadKey || group?.id;
  const mismatchMessage = "La suma de los pagos iniciales debe coincidir exactamente con la cuota inicial.";
  if (paymentKey) {
    if (crossErrors[paymentKey]) {
      state.formErrors[paymentKey] = crossErrors[paymentKey];
      setRenderedFieldError(paymentKey, crossErrors[paymentKey]);
    } else if (state.formErrors[paymentKey] === mismatchMessage) {
      delete state.formErrors[paymentKey];
      clearRenderedFieldError(paymentKey);
    }
  }
  updateComputedFields();
  updatePaymentStatus();
  updateProgressAside();
  if (state.wizardStep === state.schema.sections.length - 1) {
    const review = document.querySelector("#review-summary");
    if (review) review.innerHTML = reviewSummary();
  }
}

function resizeBuyerList(requestedCount) {
  const section = repeatableSection();
  if (!section) return;
  const minimum = Number(section.minItems || 1);
  const maximum = Number(section.maxItems || 10);
  const count = Math.min(maximum, Math.max(minimum, Math.trunc(requestedCount || minimum)));
  const payloadKey = section.payloadKey || section.id;
  const buyers = Array.isArray(state.payload[payloadKey]) ? [...state.payload[payloadKey]] : [];
  const previousCount = buyers.length;
  if (count < previousCount) {
    state.buyerStash = [...buyers.splice(count), ...state.buyerStash];
    Object.keys(state.formErrors)
      .filter((key) => key.startsWith(`${payloadKey}.`) && Number(key.split(".")[1]) >= count)
      .forEach((key) => delete state.formErrors[key]);
  } else {
    while (buyers.length < count) {
      buyers.push(state.buyerStash.shift() || defaultRepeatableItem(section));
    }
  }
  state.payload[payloadKey] = buyers;
  state.dirty = true;
  renderWizard();
  window.setTimeout(() => {
    if (count > previousCount) document.querySelector(`#buyer-${previousCount}-nombre_completo`)?.focus();
    else document.querySelector("#buyer-count")?.focus();
  }, 30);
}

function resizePaymentList(requestedCount) {
  const group = paymentGroup();
  if (!group) return;
  const minimum = Number(group.minItems || 1);
  const maximum = Number(group.maxItems || 20);
  const count = Math.min(maximum, Math.max(minimum, Math.trunc(requestedCount || minimum)));
  const payloadKey = group.payloadKey || group.id;
  const payments = Array.isArray(state.payload[payloadKey]) ? [...state.payload[payloadKey]] : [];
  const previousCount = payments.length;
  if (count < previousCount) {
    state.paymentStash = [...payments.splice(count), ...state.paymentStash];
    Object.keys(state.formErrors)
      .filter((key) => key.startsWith(`${payloadKey}.`) && Number(key.split(".")[1]) >= count)
      .forEach((key) => delete state.formErrors[key]);
  } else {
    while (payments.length < count) {
      payments.push(state.paymentStash.shift() || defaultRepeatableItem(group));
    }
  }
  state.payload[payloadKey] = payments;
  state.payload = computePayload(state.payload, { autoRegular: !state.regularAmountManual });
  if (state.formErrors[payloadKey] === "La suma de los pagos iniciales debe coincidir exactamente con la cuota inicial.") {
    delete state.formErrors[payloadKey];
  }
  state.dirty = true;
  renderWizard();
  window.setTimeout(() => {
    if (count > previousCount) document.querySelector(`#payment-${previousCount}-metodo`)?.focus();
    else document.querySelector("#payment-count")?.focus();
  }, 30);
}

function updateComputedFields() {
  ["saldo_financiado", "total_pagos_iniciales", "numero_cuotas_regulares", "monto_cuota_regular", "monto_cuota_final"].forEach((id) => {
    const input = document.querySelector(`#${id}`);
    if (input) input.value = state.payload[id] ?? "";
  });
}

function updatePaymentStatus() {
  const status = document.querySelector("#payment-count-status");
  if (!status) return;
  const payments = Array.isArray(state.payload.pagos_iniciales) ? state.payload.pagos_iniciales : [];
  const registered = numeric(state.payload.total_pagos_iniciales);
  const expected = numeric(state.payload.cuota_inicial);
  const reconciled = registered !== null && expected !== null && moneyCents(registered) === moneyCents(expected);
  status.classList.toggle("is-reconciled", reconciled);
  status.classList.toggle("is-pending", registered !== null && expected !== null && !reconciled);
  const count = status.querySelector("strong");
  const amount = status.querySelector("span");
  if (count) count.textContent = `${payments.length} ${payments.length === 1 ? "pago" : "pagos"}`;
  if (amount) amount.textContent = `${formatCurrency(state.payload.total_pagos_iniciales)} de ${formatCurrency(state.payload.cuota_inicial)}`;
}

function updateProgressAside() {
  const progress = completionProgress();
  const bar = document.querySelector("#aside-progress-bar");
  const copy = document.querySelector("#aside-progress-copy");
  const percent = document.querySelector("#aside-progress-percent");
  if (bar) bar.style.width = `${progress.percent}%`;
  if (copy) copy.textContent = `${progress.completed} de ${progress.total} datos listos`;
  if (percent) percent.textContent = `${progress.percent}%`;
}

function reviewSummary() {
  const p = state.payload;
  const section = repeatableSection();
  const payloadKey = section?.payloadKey || section?.id || "compradores";
  const buyers = Array.isArray(p[payloadKey]) ? p[payloadKey] : [];
  const payments = Array.isArray(p.pagos_iniciales) ? p.pagos_iniciales : [];
  return `<div class="review-grid" aria-label="Resumen de la minuta">
    ${buyers.map((buyer, index) => reviewCard(`Comprador ${index + 1}`, [
      ["Nombre", buyer.nombre_completo], ["DNI", buyer.documento], ["Estado civil", buyer.estado_civil], ["Correo", buyer.email],
    ])).join("")}
    ${reviewCard("Inmueble", [
      ["Manzana y lote", `Mz. ${p.manzana || "—"} · Lt. ${p.lote || "—"}`], ["Área", formatArea(p.area_m2)],
    ])}
    ${reviewCard("Operación", [
      ["Precio total", formatCurrency(p.precio_total)], ["Cuota inicial", formatCurrency(p.cuota_inicial)], ["Pagos registrados", formatCurrency(p.total_pagos_iniciales)], ["Estado", p.pago_inicial_confirmado ? "Confirmados" : "Pendientes"],
    ])}
    ${reviewCard("Pagos iniciales", payments.map((payment, index) => [
      `Pago ${index + 1}`,
      `${paymentMethodLabel(payment.metodo) || "—"} · ${formatCurrency(payment.monto)} · Op. ${payment.numero_operacion || "—"} · ${payment.fecha_pago || "—"}`,
    ]))}
    ${reviewCard("Financiamiento", [
      ["Saldo", formatCurrency(p.saldo_financiado)], ["Cuotas", `${p.numero_cuotas_regulares ?? "—"} regulares + 1 final (${p.numero_cuotas_total || "—"} en total)`], ["Cuota regular", formatCurrency(p.monto_cuota_regular)], ["Cuota final", formatCurrency(p.monto_cuota_final)],
    ])}
  </div>`;
}

function reviewCard(title, rows) {
  return `<section class="review-card"><h3>${escapeHtml(title)}</h3><dl class="review-list">${rows.map(([label, value]) => `<div class="review-row"><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value || "—")}</dd></div>`).join("")}</dl></section>`;
}

function completionProgress() {
  const required = state.schema.sections.flatMap((section) => fieldInstances(section).filter((instance) => instance.field.required && !instance.field.computed));
  const crossErrors = crossFieldErrors();
  const completed = required.filter((instance) => !validateField(instance.field, instance.value) && !crossErrors[instance.key]).length;
  return { completed, total: required.length, percent: required.length ? Math.round((completed / required.length) * 100) : 0 };
}

function sectionComplete(section) {
  const required = fieldInstances(section).filter((instance) => instance.field.required && !instance.field.computed);
  const crossErrors = crossFieldErrors();
  const enoughItems = (!section.repeatable || required.length > 0)
    && (section.groups || []).filter((group) => group.repeatable).every((group) => {
      const items = state.payload[group.payloadKey || group.id];
      return Array.isArray(items) && items.length >= Number(group.minItems || 1);
    });
  const groupError = (section.groups || []).some((group) => crossErrors[group.payloadKey || group.id]);
  return enoughItems
    && required.length > 0
    && !groupError
    && required.every((instance) => !validateField(instance.field, instance.value) && !crossErrors[instance.key]);
}

function fieldInstances(section) {
  const instances = [];
  if (!section.repeatable) {
    instances.push(...section.fields.map((field) => ({ field, key: field.id, value: state.payload[field.id] })));
  } else {
    const payloadKey = section.payloadKey || section.id;
    const items = Array.isArray(state.payload[payloadKey]) ? state.payload[payloadKey] : [];
    instances.push(...items.flatMap((item, index) => section.fields.map((field) => ({
      field,
      key: `${payloadKey}.${index}.${field.id}`,
      value: item?.[field.id],
    }))));
  }
  (section.groups || []).filter((group) => group.repeatable).forEach((group) => {
    const payloadKey = group.payloadKey || group.id;
    const items = Array.isArray(state.payload[payloadKey]) ? state.payload[payloadKey] : [];
    instances.push(...items.flatMap((item, index) => group.fields.map((field) => ({
      field,
      key: `${payloadKey}.${index}.${field.id}`,
      value: item?.[field.id],
    }))));
  });
  return instances;
}

function sectionOwnsError(section, key) {
  if (section.fields.some((field) => field.id === key)) return true;
  const payloadKeys = [];
  if (section.repeatable) payloadKeys.push(section.payloadKey || section.id);
  (section.groups || []).filter((group) => group.repeatable)
    .forEach((group) => payloadKeys.push(group.payloadKey || group.id));
  return payloadKeys.some((payloadKey) => key === payloadKey || key.startsWith(`${payloadKey}.`));
}

function validateField(field, value) {
  if (field.required && !hasValue(value)) return "Este campo es obligatorio.";
  if (!hasValue(value)) return "";
  const text = String(value);
  const maxLength = Number(field.maxlength || 240);
  if (["text", "email", "tel", "select"].includes(field.type) && text.length > maxLength) {
    return `Usa como máximo ${maxLength} caracteres.`;
  }
  if (field.validation === "dni" && !/^\d{8}$/.test(text.replace(/\D/g, ""))) {
    return "El DNI debe tener 8 dígitos.";
  }
  if (field.type === "email" && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(text)) {
    return "Ingresa un correo válido.";
  }
  if (field.type === "select") {
    const allowed = (field.options || []).some((option) => String(option.value) === text);
    if (!allowed) return "Selecciona una opción válida.";
  }
  if (field.type === "date" && !validIsoDate(text)) return "Ingresa una fecha válida.";
  if (field.type === "number") {
    const number = numeric(value);
    if (number === null) return "Ingresa un número válido.";
    if (field.integer && !Number.isInteger(number)) return "Ingresa un número entero.";
    if (field.min !== undefined && number < Number(field.min)) return `El valor mínimo es ${field.min}.`;
    if (field.max !== undefined && number > Number(field.max)) return `El valor máximo es ${field.max}.`;
  }
  return "";
}

function validIsoDate(value) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return false;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  return parsed.getUTCFullYear() === year && parsed.getUTCMonth() === month - 1 && parsed.getUTCDate() === day;
}

function crossFieldErrors() {
  const errors = {};
  const price = numeric(state.payload.precio_total);
  const initial = numeric(state.payload.cuota_inicial);
  const final = numeric(state.payload.monto_cuota_final);
  if (price !== null && initial !== null && initial > price) {
    errors.cuota_inicial = "La cuota inicial no puede superar el precio total.";
  }
  if (final !== null && final <= 0) {
    errors.monto_cuota_regular = "La cuota final debe ser mayor a cero; ajusta el total o el monto regular.";
  }
  const group = paymentGroup();
  const paymentKey = group?.payloadKey || group?.id;
  const payments = paymentKey && Array.isArray(state.payload[paymentKey])
    ? state.payload[paymentKey]
    : [];
  const amounts = payments.map((payment) => numeric(payment?.monto));
  if (
    paymentKey
    && initial !== null
    && payments.length > 0
    && amounts.every((amount) => amount !== null)
    && amounts.reduce((sum, amount) => sum + moneyCents(amount), 0) !== moneyCents(initial)
  ) {
    errors[paymentKey] = "La suma de los pagos iniciales debe coincidir exactamente con la cuota inicial.";
  }
  return errors;
}

function validateSection(sectionIndex) {
  const section = state.schema.sections[sectionIndex];
  const errors = {};
  Object.keys(state.formErrors)
    .filter((key) => sectionOwnsError(section, key))
    .forEach((key) => delete state.formErrors[key]);
  const instances = fieldInstances(section);
  if (section.repeatable && instances.length === 0) {
    const payloadKey = section.payloadKey || section.id;
    errors[payloadKey] = "Registra al menos un comprador.";
  }
  (section.groups || []).filter((group) => group.repeatable).forEach((group) => {
    const payloadKey = group.payloadKey || group.id;
    const items = state.payload[payloadKey];
    if (!Array.isArray(items) || items.length < Number(group.minItems || 1)) {
      errors[payloadKey] = "Registra al menos un pago inicial.";
    }
  });
  instances.forEach((instance) => {
    const error = validateField(instance.field, instance.value);
    if (error) errors[instance.key] = error;
  });
  const crossErrors = crossFieldErrors();
  instances.forEach((instance) => {
    if (crossErrors[instance.key]) errors[instance.key] = crossErrors[instance.key];
  });
  Object.entries(crossErrors).forEach(([key, message]) => {
    if (sectionOwnsError(section, key)) errors[key] = message;
  });
  Object.assign(state.formErrors, errors);
  return Object.keys(errors).length === 0;
}

function validateAll() {
  state.formErrors = {};
  state.schema.sections.forEach((_, index) => validateSection(index));
  Object.assign(state.formErrors, crossFieldErrors());
  return Object.keys(state.formErrors).length === 0;
}

function firstErrorStep() {
  return state.schema.sections.findIndex((section) => (
    Object.keys(state.formErrors).some((key) => sectionOwnsError(section, key))
  ));
}

function applyRenderedErrors() {
  Object.entries(state.formErrors).forEach(([id, message]) => setRenderedFieldError(id, message));
}

function setRenderedFieldError(id, message) {
  const domId = errorKeyToDomId(id);
  const input = document.querySelector(`#${CSS.escape(domId)}`);
  const error = document.querySelector(`#${CSS.escape(domId)}-error`);
  if (!input) {
    if (error) error.textContent = message;
    return;
  }
  input.setAttribute("aria-invalid", "true");
  const shell = input.closest(".input-shell, .checkbox-field");
  shell?.classList.add("is-invalid");
  if (error) error.textContent = message;
}

function clearRenderedFieldError(id) {
  const domId = errorKeyToDomId(id);
  const input = document.querySelector(`#${CSS.escape(domId)}`);
  const error = document.querySelector(`#${CSS.escape(domId)}-error`);
  input?.removeAttribute("aria-invalid");
  input?.closest(".input-shell, .checkbox-field")?.classList.remove("is-invalid");
  if (error) error.textContent = "";
}

function errorKeyToDomId(key) {
  const buyerMatch = /^compradores\.(\d+)\.([^.]+)$/.exec(key);
  if (buyerMatch) return `buyer-${buyerMatch[1]}-${buyerMatch[2]}`;
  const paymentMatch = /^pagos_iniciales\.(\d+)\.([^.]+)$/.exec(key);
  return paymentMatch ? `payment-${paymentMatch[1]}-${paymentMatch[2]}` : key;
}

async function saveDraft(options = {}) {
  const button = options.button;
  if (button) setButtonBusy(button, true, "Guardando…");
  try {
    const path = state.editingId ? `/api/minutes/${state.editingId}` : "/api/minutes";
    const method = state.editingId ? "PUT" : "POST";
    const item = await api(path, { method, body: { payload: state.payload } });
    state.editingId = item.id;
    state.payload = normalizeEditorPayload(item.payload);
    state.buyerStash = [];
    state.paymentStash = [];
    upsertMinute(item);
    state.dirty = false;
    await refreshStats();
    if (!options.quiet) toast("Borrador guardado", `${item.reference} está disponible en el historial.`);
    return item;
  } catch (error) {
    applyApiValidation(error);
    if (!options.quiet) toast("No se pudo guardar", error.message, "error");
    throw error;
  } finally {
    if (button) setButtonBusy(button, false);
  }
}

async function generateCurrent(button) {
  if (!validateAll()) {
    const step = firstErrorStep();
    if (step >= 0) state.wizardStep = step;
    renderWizard();
    focusFirstError();
    toast("Faltan datos", "Revisa los campos marcados antes de generar.", "error");
    return;
  }
  setButtonBusy(button, true, "Generando…");
  try {
    const item = await saveDraft({ quiet: true });
    await downloadMinute(item.id);
    await refreshData();
    navigate("minutes");
    toast("Minuta generada", "El documento Word se descargó con todos los campos completados.");
  } catch (error) {
    if (!error.fieldErrors) toast("No se pudo generar", error.message, "error");
  } finally {
    setButtonBusy(button, false);
  }
}

async function generateFromList(id, button) {
  if (button) setButtonBusy(button, true, "Generando…");
  try {
    await downloadMinute(id);
    await refreshData();
    if (state.route === "dashboard") renderDashboard();
    else renderMinutes();
    toast("Minuta generada", "El documento se descargó correctamente.");
  } catch (error) {
    if (error.fieldErrors) {
      const item = state.minutes.find((minute) => minute.id === id);
      state.editingId = id;
      state.payload = normalizeEditorPayload(item.payload);
      state.regularAmountManual = hasValue(state.payload.monto_cuota_regular);
      state.buyerStash = [];
      state.paymentStash = [];
      state.formErrors = error.fieldErrors;
      state.wizardStep = Math.max(0, firstErrorStep());
      navigate("new-minute");
      focusFirstError();
      toast("Faltan datos", "Completa los campos marcados para generar la minuta.", "error");
    } else {
      toast("No se pudo generar", error.message, "error");
    }
  } finally {
    if (button?.isConnected) setButtonBusy(button, false);
  }
}

async function downloadMinute(id) {
  const result = await api(`/api/minutes/${id}/generate`, { method: "POST", download: true });
  const url = URL.createObjectURL(result.blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = result.filename || "minuta-villa-hermosa.docx";
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function applyApiValidation(error) {
  if (!error.fieldErrors) return;
  state.formErrors = error.fieldErrors;
  const step = firstErrorStep();
  if (step >= 0) state.wizardStep = step;
  if (state.route === "new-minute") {
    renderWizard();
    focusFirstError();
  }
}

function focusFirstError() {
  window.setTimeout(() => document.querySelector('[aria-invalid="true"]')?.focus(), 30);
}

function focusWizardTitle() {
  window.setTimeout(() => document.querySelector("#wizard-title")?.focus({ preventScroll: true }), 30);
}

function upsertMinute(item) {
  const index = state.minutes.findIndex((minute) => minute.id === item.id);
  if (index >= 0) state.minutes[index] = item;
  else state.minutes.unshift(item);
  state.minutes.sort((a, b) => String(b.updated_at).localeCompare(String(a.updated_at)));
}

async function refreshStats() {
  state.stats = await api("/api/stats");
}

async function refreshData() {
  const [minutes, stats] = await Promise.all([api("/api/minutes"), api("/api/stats")]);
  state.minutes = minutes.items || [];
  state.stats = stats;
}

function confirmDelete(id) {
  const item = state.minutes.find((minute) => minute.id === id);
  if (!item) return;
  showModal({
    title: "Eliminar minuta",
    message: `Se eliminará ${item.reference} de ${item.client_name || "este cliente"}. Esta acción no se puede deshacer.`,
    icon: icons.trash,
    confirmLabel: "Eliminar definitivamente",
    confirmClass: "button--danger",
    onConfirm: async () => {
      await api(`/api/minutes/${id}`, { method: "DELETE" });
      state.minutes = state.minutes.filter((minute) => minute.id !== id);
      await refreshStats();
      renderMinutes();
      toast("Minuta eliminada", "El expediente fue retirado del sistema.");
    },
  });
}

async function handleMainClick(event) {
  const button = event.target.closest("[data-action]");
  if (!button) return;
  const action = button.dataset.action;
  if (action === "new-minute") requestStartNewMinute();
  if (action === "view-all") requestNavigation("minutes");
  if (action === "reload") window.location.reload();
  if (action === "edit") requestEditMinute(button.dataset.id);
  if (action === "generate") await generateFromList(button.dataset.id, button);
  if (action === "delete") confirmDelete(button.dataset.id);
  if (action === "filter") {
    state.statusFilter = button.dataset.filter;
    renderMinutes();
    document.querySelector(`[data-action="filter"][data-filter="${CSS.escape(state.statusFilter)}"]`)?.focus();
  }
  if (action === "previous-step") {
    state.wizardStep = Math.max(0, state.wizardStep - 1);
    renderWizard();
    focusWizardTitle();
  }
  if (action === "next-step") {
    if (!validateSection(state.wizardStep)) {
      renderWizard();
      focusFirstError();
      return;
    }
    state.wizardStep = Math.min(state.schema.sections.length - 1, state.wizardStep + 1);
    renderWizard();
    focusWizardTitle();
  }
  if (action === "wizard-step") {
    const targetStep = Number(button.dataset.step);
    if (targetStep > state.wizardStep && !validateSection(state.wizardStep)) {
      renderWizard();
      focusFirstError();
      return;
    }
    state.wizardStep = targetStep;
    renderWizard();
    focusWizardTitle();
  }
  if (action === "save-draft") {
    try { await saveDraft({ button }); } catch (error) { /* toast handled */ }
  }
  if (action === "generate-current") await generateCurrent(button);
}

elements.main.addEventListener("input", (event) => {
  if (event.target.id === "minute-search") {
    state.search = event.target.value;
    const position = event.target.selectionStart;
    renderMinutes();
    const next = document.querySelector("#minute-search");
    next?.focus({ preventScroll: true });
    next?.setSelectionRange(position, position);
  }
});

function showModal({ title, message, icon, confirmLabel, confirmClass = "button--primary", onConfirm }) {
  const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  elements.modalRoot.innerHTML = `<div class="modal-backdrop" role="presentation">
    <section class="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title" aria-describedby="modal-description">
      <div class="modal__body"><span class="modal__icon">${icon}</span><h2 id="modal-title">${escapeHtml(title)}</h2><p id="modal-description">${escapeHtml(message)}</p></div>
      <div class="modal__actions"><button class="button button--secondary" type="button" data-modal-cancel>Cancelar</button><button class="button ${confirmClass}" type="button" data-modal-confirm>${escapeHtml(confirmLabel)}</button></div>
    </section>
  </div>`;
  const backdrop = elements.modalRoot.querySelector(".modal-backdrop");
  const cancel = elements.modalRoot.querySelector("[data-modal-cancel]");
  const confirm = elements.modalRoot.querySelector("[data-modal-confirm]");
  const focusable = [cancel, confirm];
  let closed = false;
  elements.appView.inert = true;
  const close = () => {
    if (closed) return;
    closed = true;
    document.removeEventListener("keydown", keyHandler);
    elements.appView.inert = false;
    elements.modalRoot.innerHTML = "";
    previousFocus?.focus({ preventScroll: true });
  };
  const keyHandler = (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      close();
      return;
    }
    if (event.key !== "Tab") return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };
  cancel.addEventListener("click", close);
  backdrop.addEventListener("click", (event) => { if (event.target === backdrop) close(); });
  confirm.addEventListener("click", async () => {
    setButtonBusy(confirm, true, "Procesando…");
    try { await onConfirm(); close(); } catch (error) { toast("No se pudo completar", error.message, "error"); setButtonBusy(confirm, false); }
  });
  document.addEventListener("keydown", keyHandler);
  cancel.focus();
}

function toast(title, message, type = "success") {
  const item = document.createElement("div");
  item.className = `toast ${type === "error" ? "toast--error" : ""}`;
  item.setAttribute("role", type === "error" ? "alert" : "status");
  item.innerHTML = `<span class="toast__icon">${type === "error" ? "!" : "✓"}</span><span class="toast__copy"><strong>${escapeHtml(title)}</strong><span>${escapeHtml(message)}</span></span><button class="toast__close" type="button" aria-label="Cerrar aviso">×</button>`;
  elements.toastRegion.append(item);
  let timeoutId;
  const remove = () => item.remove();
  const pause = () => window.clearTimeout(timeoutId);
  const schedule = () => {
    pause();
    timeoutId = window.setTimeout(remove, 8000);
  };
  item.querySelector(".toast__close").addEventListener("click", remove);
  item.addEventListener("mouseenter", pause);
  item.addEventListener("mouseleave", schedule);
  item.addEventListener("focusin", pause);
  item.addEventListener("focusout", schedule);
  schedule();
}

async function api(path, options = {}) {
  if (USE_FIREBASE_BACKEND) return firebaseApi(path, options);

  const method = options.method || "GET";
  const headers = { Accept: options.download ? "application/vnd.openxmlformats-officedocument.wordprocessingml.document" : "application/json" };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET" && path !== "/api/login" && state.csrfToken) headers["X-CSRF-Token"] = state.csrfToken;

  let response;
  try {
    response = await fetch(path, {
      method,
      credentials: "same-origin",
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    });
  } catch (error) {
    throw new Error("No hay conexión con el servidor.");
  }

  if (options.download && response.ok) {
    const disposition = response.headers.get("Content-Disposition") || "";
    const match = disposition.match(/filename="([^"]+)"/i);
    return { blob: await response.blob(), filename: match?.[1] };
  }

  let payload = {};
  if (response.status !== 204) {
    try { payload = await response.json(); } catch (error) { payload = {}; }
  }
  if (!response.ok) {
    const apiError = new Error(payload.error || "Ocurrió un error inesperado.");
    apiError.status = response.status;
    apiError.fieldErrors = payload.fieldErrors;
    if (response.status === 401 && !options.suppressAuthRedirect && path !== "/api/login") {
      showLogin();
      toast("Sesión finalizada", "Ingresa nuevamente para continuar.", "error");
    }
    throw apiError;
  }
  return payload;
}

async function initializeFirebaseRuntime() {
  if (firebaseRuntime) return firebaseRuntime;
  const [appModule, authModule, firestoreModule] = await Promise.all([
    import("https://www.gstatic.com/firebasejs/12.4.0/firebase-app.js"),
    import("https://www.gstatic.com/firebasejs/12.4.0/firebase-auth.js"),
    import("https://www.gstatic.com/firebasejs/12.4.0/firebase-firestore.js"),
  ]);
  const firebaseApp = appModule.initializeApp(FIREBASE_CONFIG);
  const auth = authModule.getAuth(firebaseApp);
  await authModule.setPersistence(auth, authModule.browserLocalPersistence);
  const db = firestoreModule.getFirestore(firebaseApp);
  firebaseRuntime = { auth, db, ...authModule, ...firestoreModule };
  await new Promise((resolve, reject) => {
    const unsubscribe = authModule.onAuthStateChanged(
      auth,
      () => {
        unsubscribe();
        resolve();
      },
      reject,
    );
  });
  return firebaseRuntime;
}

function firebaseUserProfile(user) {
  const email = String(user.email || "").toLowerCase();
  const admin = email === "inmobiliariaathouse@gmail.com";
  return {
    id: user.uid,
    email,
    display_name: user.displayName || (admin ? "Administrador Villa Hermosa" : "Asesor Villa Hermosa"),
    role: admin ? "admin" : "asesor",
  };
}

function firebaseApiError(message, status = 500, fieldErrors) {
  const error = new Error(message);
  error.status = status;
  error.fieldErrors = fieldErrors;
  return error;
}

function firebaseAuthError(error) {
  const code = String(error?.code || "");
  if (["auth/invalid-credential", "auth/user-not-found", "auth/wrong-password"].includes(code)) {
    return firebaseApiError("Correo o contraseña incorrectos.", 401);
  }
  if (code === "auth/too-many-requests") {
    return firebaseApiError("Demasiados intentos. Espera unos minutos e inténtalo otra vez.", 429);
  }
  if (code === "auth/network-request-failed") {
    return firebaseApiError("No hay conexión con Firebase.", 503);
  }
  return firebaseApiError("No pudimos iniciar sesión. Inténtalo nuevamente.", 500);
}

function requireFirebaseUser(options = {}) {
  const user = firebaseRuntime?.auth?.currentUser;
  if (!user || !AUTHORIZED_EMAILS.has(user.email?.toLowerCase())) {
    if (!options.suppressAuthRedirect) {
      showLogin();
      toast("Sesión finalizada", "Ingresa nuevamente para continuar.", "error");
    }
    throw firebaseApiError("Tu sesión no está activa.", 401);
  }
  return user;
}

function firebaseMinuteData(payload, existing = {}) {
  const normalizedPayload = normalizeEditorPayload(payload);
  const buyers = Array.isArray(normalizedPayload.compradores) ? normalizedPayload.compradores : [];
  const names = buyers.map((buyer) => String(buyer?.nombre_completo || "").trim()).filter(Boolean);
  const documents = buyers.map((buyer) => String(buyer?.documento || "").trim()).filter(Boolean);
  const now = new Date().toISOString();
  return {
    ...existing,
    client_name: names.join(" · "),
    document_number: documents.join(" · "),
    payload: normalizedPayload,
    status: existing.status || "borrador",
    updated_at: now,
  };
}

function nextFirebaseReference(items) {
  const prefix = new Date().toISOString().slice(0, 7).replace("-", "");
  const pattern = new RegExp(`^VH-${prefix}-(\\d+)$`);
  const last = items.reduce((maximum, item) => {
    const match = pattern.exec(String(item.reference || ""));
    return match ? Math.max(maximum, Number(match[1])) : maximum;
  }, 0);
  return `VH-${prefix}-${String(last + 1).padStart(4, "0")}`;
}

async function firebaseListMinutes() {
  const user = requireFirebaseUser();
  const { collection, getDocs, query, where } = firebaseRuntime;
  const snapshot = await getDocs(query(
    collection(firebaseRuntime.db, "minutes"),
    where("owner_uid", "==", user.uid),
  ));
  return snapshot.docs
    .map((item) => ({ id: item.id, ...item.data() }))
    .sort((left, right) => String(right.updated_at || "").localeCompare(String(left.updated_at || "")));
}

async function firebaseStats() {
  const items = await firebaseListMinutes();
  return {
    total: items.length,
    borradores: items.filter((item) => item.status === "borrador").length,
    generadas: items.filter((item) => item.status === "generada").length,
  };
}

async function firebaseGenerateMinute(id) {
  const user = requireFirebaseUser();
  const { doc, getDoc, updateDoc } = firebaseRuntime;
  const reference = doc(firebaseRuntime.db, "minutes", id);
  const snapshot = await getDoc(reference);
  if (!snapshot.exists()) throw firebaseApiError("No encontramos esa minuta.", 404);
  const item = { id: snapshot.id, ...snapshot.data() };
  let response;
  try {
    response = await fetch(DOCUMENT_SERVICE_URL, {
      method: "POST",
      mode: "cors",
      headers: {
        Accept: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        Authorization: `Bearer ${await user.getIdToken()}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ payload: item.payload, reference: item.reference }),
    });
  } catch (error) {
    throw firebaseApiError("No pudimos conectar con el generador de documentos.", 503);
  }
  if (!response.ok) {
    let payload = {};
    try { payload = await response.json(); } catch (error) { payload = {}; }
    throw firebaseApiError(
      payload.error || "No pudimos generar el documento.",
      response.status,
      payload.fieldErrors,
    );
  }
  const now = new Date().toISOString();
  await updateDoc(reference, { status: "generada", generated_at: now, updated_at: now });
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="([^"]+)"/i);
  return { blob: await response.blob(), filename: match?.[1] };
}

async function firebaseApi(path, options = {}) {
  await initializeFirebaseRuntime();
  const method = options.method || "GET";
  if (path === "/api/login" && method === "POST") {
    try {
      const credential = await firebaseRuntime.signInWithEmailAndPassword(
        firebaseRuntime.auth,
        String(options.body?.email || "").toLowerCase(),
        String(options.body?.password || ""),
      );
      if (!AUTHORIZED_EMAILS.has(credential.user.email?.toLowerCase())) {
        await firebaseRuntime.signOut(firebaseRuntime.auth);
        throw firebaseApiError("Esta cuenta no tiene acceso a Minutas.", 403);
      }
      return { user: firebaseUserProfile(credential.user), csrfToken: null };
    } catch (error) {
      if (error?.status) throw error;
      throw firebaseAuthError(error);
    }
  }
  if (path === "/api/logout" && method === "POST") {
    await firebaseRuntime.signOut(firebaseRuntime.auth);
    return { ok: true };
  }
  if (path === "/api/session" && method === "GET") {
    const user = requireFirebaseUser(options);
    return { user: firebaseUserProfile(user), csrfToken: null };
  }
  if (path === "/api/schema" && method === "GET") {
    const response = await fetch("/minute_schema.json", { cache: "no-store" });
    if (!response.ok) throw firebaseApiError("No pudimos cargar el formulario.", 503);
    return response.json();
  }
  if (path === "/api/minutes" && method === "GET") {
    return { items: await firebaseListMinutes() };
  }
  if (path === "/api/stats" && method === "GET") return firebaseStats();
  if (path === "/api/minutes" && method === "POST") {
    const user = requireFirebaseUser();
    const items = await firebaseListMinutes();
    if (items.length >= 5000) throw firebaseApiError("Alcanzaste el límite de expedientes.", 409);
    const id = crypto.randomUUID();
    const now = new Date().toISOString();
    const item = firebaseMinuteData(options.body?.payload || {}, {
      id,
      reference: nextFirebaseReference(items),
      owner_uid: user.uid,
      owner_email: user.email,
      owner_name: firebaseUserProfile(user).display_name,
      created_by: user.uid,
      created_at: now,
      status: "borrador",
    });
    await firebaseRuntime.setDoc(firebaseRuntime.doc(firebaseRuntime.db, "minutes", id), item);
    return item;
  }
  const match = /^\/api\/minutes\/([0-9a-f-]{36})(?:\/(generate))?$/.exec(path);
  if (!match) throw firebaseApiError("Ruta no encontrada.", 404);
  const [, id, action] = match;
  if (method === "POST" && action === "generate" && options.download) {
    return firebaseGenerateMinute(id);
  }
  const reference = firebaseRuntime.doc(firebaseRuntime.db, "minutes", id);
  if (method === "PUT" && !action) {
    const snapshot = await firebaseRuntime.getDoc(reference);
    if (!snapshot.exists()) throw firebaseApiError("No encontramos esa minuta.", 404);
    const existing = { id: snapshot.id, ...snapshot.data(), status: "borrador" };
    const item = firebaseMinuteData(options.body?.payload || {}, existing);
    await firebaseRuntime.setDoc(reference, item);
    return item;
  }
  if (method === "DELETE" && !action) {
    await firebaseRuntime.deleteDoc(reference);
    return {};
  }
  throw firebaseApiError("Acción no permitida.", 405);
}

function setButtonBusy(button, busy, label = "Procesando…") {
  if (!button) return;
  if (busy) {
    if (!button.dataset.originalHtml) button.dataset.originalHtml = button.innerHTML;
    button.disabled = true;
    button.innerHTML = `<span class="spinner" style="width:18px;height:18px;border-width:2px"></span><span>${escapeHtml(label)}</span>`;
  } else {
    button.disabled = false;
    if (button.dataset.originalHtml) {
      button.innerHTML = button.dataset.originalHtml;
      delete button.dataset.originalHtml;
    }
  }
}

function hasValue(value) {
  return value !== undefined && value !== null && value !== "" && value !== false;
}

function numeric(value) {
  if (value === "" || value === null || value === undefined) return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function roundMoney(value) {
  return Math.round((value + Number.EPSILON) * 100) / 100;
}

function moneyCents(value) {
  return Math.round((Number(value) + Number.EPSILON) * 100);
}

function formatCurrency(value) {
  const number = numeric(value);
  return number === null ? "—" : new Intl.NumberFormat("es-PE", { style: "currency", currency: "PEN" }).format(number);
}

function formatArea(value) {
  const number = numeric(value);
  return number === null ? "Área pendiente" : `${number.toLocaleString("es-PE", { maximumFractionDigits: 2 })} m²`;
}

function formatDateTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return "—";
  return new Intl.DateTimeFormat("es-PE", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }).format(date);
}

function formatShortDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return "—";
  return new Intl.DateTimeFormat("es-PE", { day: "2-digit", month: "short" }).format(date);
}

function todayIso() {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 10);
}

function initials(value) {
  return String(value || "VH").trim().split(/\s+/).slice(0, 2).map((part) => part[0]?.toUpperCase() || "").join("") || "VH";
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[character]));
}

function escapeAttribute(value) {
  return escapeHtml(value).replace(/`/g, "&#96;");
}
