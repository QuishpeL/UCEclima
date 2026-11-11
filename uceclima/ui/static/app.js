"use strict";
const $ = (s, r = document) => r.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const fmtS = (v, d = 3) => { if (v === null || v === undefined || Number.isNaN(v)) return "—"; const a = Math.abs(v); return (a !== 0 && a < 1e-3) ? Number(v).toExponential(1).replace(".", ",") : fmt(v, d); };
const fmt = (v, d = 2) => (v === null || v === undefined || Number.isNaN(v)) ? "—" : Number(v).toLocaleString("es-EC", {maximumFractionDigits: d, minimumFractionDigits: 0});
let S = {estado: null, ruta: "proyecto", verif: null, temporizador: null, corridaSel: null};

async function api(ruta, cuerpo) {
  const op = cuerpo === undefined ? {} : {method: "POST", headers: {"Content-Type": "application/json", "X-UCECLIMA-TOKEN": window.TOKEN}, body: JSON.stringify(cuerpo)};
  const r = await fetch(ruta, op);
  const j = await r.json().catch(() => ({error: "Respuesta no válida del servidor"}));
  if (!r.ok && !j.error) j.error = "Error " + r.status;
  return j;
}
function aviso(t, ms = 4500) { const a = $("#aviso"); a.textContent = t; a.style.display = "block"; clearTimeout(aviso.t); aviso.t = setTimeout(() => a.style.display = "none", ms); }
const badge = (estado, txt) => `<span class="badge b-${esc(estado)}">${esc(txt ?? estado)}</span>`;
const nota = (t, tipo = "") => `<div class="nota ${tipo}">${t}</div>`;
const pendiente = (que) => `<button disabled title="${esc(que)}">${esc(que.split(":")[0])}</button><span class="chip"> · pendiente: ${esc(que.split(":").slice(1).join(":").trim() || "no implementado")}</span>`;
const ESTADOS_TXT = {ok: "correcto", aviso: "aviso", error: "error", pendiente: "pendiente"};

async function cargarEstado() {
  S.estado = await api("/api/estado"); pintarCabecera(); pintarNav();
  const c = S.estado.proyecto ? S.estado.proyecto._carpeta : null;               // Zeta: al cambiar de proyecto, sus propios campos guardados
  if (c !== S.uiCarpeta) { S.uiCarpeta = c; S.ui = c ? await api("/api/proyecto/estado_ui") : null; if ($("#guardado-info")) $("#guardado-info").textContent = S.ui?.ultimo_guardado ? "último guardado " + S.ui.ultimo_guardado.slice(0, 16).replace("T", " ") : ""; }
}
function pintarCabecera() {
  const p = S.estado.proyecto;
  $("#titulo-proyecto").textContent = p ? p.nombre : "Sin proyecto abierto";
  $("#badge-tipo").innerHTML = p ? (p.tipo === "sintetico" ? badge("aviso", "SINTÉTICO · no es un lugar real").replace("b-aviso", "b-sint") : badge("ok", "Datos reales").replace("b-ok", "b-real")) : "";
  const ult = (S.estado.corridas || [])[0];
  $("#estado-corrida").innerHTML = ult ? `Última corrida: ${badge(ult.estado)}` : "";
}
function pintarNav() {
  $("#nav").innerHTML = S.estado.modulos.map((m, i) => {
    const id = m.id; const actual = id === S.ruta ? ' aria-current="page"' : "";
    return `<a href="#/${id}"${actual} title="${esc(m.resumen)}"><span class="pt ${m.estado}" aria-hidden="true"></span><span>${esc(m.nombre)}</span><span class="sr" style="position:absolute;left:-999px"> (${m.estado})</span></a>`;
  }).join("");
}
function ruta() { return (location.hash.replace(/^#\//, "") || "proyecto"); }
async function navegar() {
  S.ruta = ruta(); if (!S.estado) await cargarEstado(); pintarNav(); $("#lateral").classList.remove("abierto");
  clearInterval(S.temporizador); S.temporizador = null;
  const v = VISTAS[S.ruta] || VISTAS.proyecto; $("#principal").innerHTML = ""; await v(); $("#principal").focus({preventScroll: true});
  actualizarRun();
  if (S.estado?.proyecto) { api("/api/proyecto/estado_ui", {ruta: S.ruta}); restaurarCampos(); setTimeout(restaurarCampos, 1500); }   // Zeta «modo Word»
}

// ================================================================== Zeta «modo Word»: guardar y continuar donde te quedaste
const CAMPOS_SEL = "#principal input[id]:not([type=password]):not([type=file]):not([type=button]), #principal select[id], #principal textarea[id]";
function leerCampos() {
  const c = {}; document.querySelectorAll(CAMPOS_SEL).forEach(e => { c[e.id] = e.type === "checkbox" ? String(e.checked) : e.value; }); return c;
}
function restaurarCampos() {
  const guard = ((S.ui || {}).campos || {})[S.ruta]; if (!guard) return;
  document.querySelectorAll(CAMPOS_SEL).forEach(e => {
    if (!(e.id in guard) || e.dataset.restaurado) return;
    if (e.type === "checkbox") e.checked = guard[e.id] === "true";
    else if (e.tagName === "SELECT") { if ([...e.options].some(o => o.value === guard[e.id])) e.value = guard[e.id]; }
    else if (!e.value) e.value = guard[e.id];
    e.dataset.restaurado = "1";
  });
}
function autoguardar() {
  if (!S.estado?.proyecto) return; clearTimeout(autoguardar.t);
  autoguardar.t = setTimeout(async () => { const campos = leerCampos(); S.ui = S.ui || {}; (S.ui.campos = S.ui.campos || {})[S.ruta] = campos;
    await api("/api/proyecto/estado_ui", {ruta: S.ruta, campos}); $("#guardado-info").textContent = "autoguardado " + new Date().toLocaleTimeString("es-EC", {hour: "2-digit", minute: "2-digit"}); }, 1500);
}
async function guardarAvance() {
  if (!S.estado?.proyecto) { aviso("Abre o crea un proyecto para guardar.", 5000); return; }
  $("#guardado-info").textContent = "guardando…";
  const j = await api("/api/proyecto/guardar_avance", {ruta: S.ruta, campos: leerCampos()});
  if (j.error) { aviso(j.error, 7000); $("#guardado-info").textContent = ""; return; }
  $("#guardado-info").textContent = "guardado " + (j.guardado || "").slice(11, 16); aviso(`Avance guardado en ${j.carpeta}. Al volver a abrir UCEclima continúas aquí.`, 5000);
}
document.addEventListener("input", e => { if (e.target.closest("#principal")) autoguardar(); });
document.addEventListener("change", e => { if (e.target.closest("#principal")) autoguardar(); });
document.addEventListener("keydown", e => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); guardarAvance(); } });
$("#btnguardar").addEventListener("click", guardarAvance);
async function continuarDondeQuede() {
  if (!S.estado?.proyecto) return;
  S.ui = await api("/api/proyecto/estado_ui");
  if (S.ui.ultimo_guardado) $("#guardado-info").textContent = "último guardado " + S.ui.ultimo_guardado.slice(0, 16).replace("T", " ");
  if (!location.hash && S.ui.ruta && S.ui.ruta !== "proyecto" && VISTAS[S.ui.ruta]) { aviso(`Continúas donde te quedaste: ${S.ui.ruta}.`, 4000); location.hash = "#/" + S.ui.ruta; }
}
window.addEventListener("hashchange", navegar);
document.addEventListener("keydown", e => { if (e.altKey && /^[0-9]$/.test(e.key)) { const i = e.key === "0" ? 9 : +e.key - 1; const m = S.estado?.modulos[i]; if (m) location.hash = "#/" + m.id; } });
$("#btnmenu").addEventListener("click", () => { const a = $("#lateral").classList.toggle("abierto"); $("#btnmenu").setAttribute("aria-expanded", a); });

// ⚙ Configuración de un módulo (parámetros matemáticos y de paso); guarda con respaldo .bak
async function panelConfig(modulo, el) {
  if (!el) return;
  const c = await api("/api/config?modulo=" + modulo);
  if (c.error) { el.innerHTML = ""; return; }
  const campo = f => f.tipo === "bool" ? `<label class="tog" style="display:flex;gap:6px;align-items:center"><input type="checkbox" data-cf="${f.clave}" ${f.valor ? "checked" : ""}> ${esc(f.nombre)}</label>`
    : f.tipo === "opcion" ? `<div><label>${esc(f.nombre)}</label><select data-cf="${f.clave}">${f.opciones.map(o => `<option ${String(o) === String(f.valor) ? "selected" : ""}>${esc(o)}</option>`).join("")}</select></div>`
    : `<div><label>${esc(f.nombre)}${f.unidad ? " (" + esc(f.unidad) + ")" : ""}</label><input type="text" data-cf="${f.clave}" value="${esc(f.valor)}" style="width:110px" title="${f.min} a ${f.max}"></div>`;
  el.innerHTML = `<details class="tarjeta" style="padding:12px 16px"><summary><b>⚙ Configuración</b></summary><div class="fila" style="flex-wrap:wrap;gap:14px;margin-top:10px">${c.campos.map(campo).join("")}</div>
    <div class="fila"><button class="principal" data-cfg-guardar>Guardar configuración</button></div><div data-cfg-msg></div></details>`;
  el.querySelector("[data-cfg-guardar]").onclick = async () => {
    const valores = {}; el.querySelectorAll("[data-cf]").forEach(i => valores[i.dataset.cf] = i.type === "checkbox" ? i.checked : i.value);
    const j = await api("/api/config", {modulo, valores}); const m = el.querySelector("[data-cfg-msg]");
    m.innerHTML = j.error ? nota(esc(j.error), "err") : nota(Object.keys(j.cambios).length ? "Guardado: " + Object.entries(j.cambios).map(([k, v]) => `${esc(k)} ${esc(v.antes)} → <b>${esc(v.ahora)}</b>`).join(" · ") : "Sin cambios.", "ok") + (j.avisos || []).map(a => nota(esc(a), "pend")).join("");
  };
}
const encabezado = (t, s) => `<h1>${esc(t)}</h1><p class="sub">${s}</p>`;
const requiereProyecto = () => S.estado.proyecto ? "" : nota("Abre un proyecto en la etapa 1 para continuar.", "pend");

const campo = (et, id, v = "", ph = "", tipo = "text") => `<div class="crece"><label for="${id}">${et}</label><input type="${tipo}" id="${id}" value="${esc(v)}" placeholder="${esc(ph)}"></div>`;
/* ---------------------------------------------------------------- 5 Terreno */
async function vTerreno() {
  $("#principal").innerHTML = encabezado("Terreno", "Se verifica CRS, resolución, cobertura de datos y tipo de modelo (MDT de suelo desnudo o DSM de superficie). No se rellenan huecos ni se afirma exactitud vertical.") + requiereProyecto();
  if (!S.estado.proyecto) return;
  $("#principal").insertAdjacentHTML("beforeend", `<section class="tarjeta"><h2>Calidad del terreno</h2><div id="chkT"><p class="chip">Verificando…</p></div>
    <div class="fila" style="margin-top:8px"><div><label for="demAmb">Área</label><select id="demAmb"><option value="sitio">alrededor del sitio</option><option value="cuenca">cuenca activa + margen</option></select></div><div><label for="demProd">Producto</label><select id="demProd"><option value="glo30">Copernicus GLO-30 (DSM, con techos y árboles)</option><option value="fabdem">FABDEM (suelo desnudo estimado · no comercial)</option></select></div><button class="principal" id="demGee">Usar MDT de Earth Engine (30 m)</button><span class="chip">GLO-30 por defecto. FABDEM quita bosques y edificios (Hawker et al. 2022) pero también suaviza cauces pequeños; licencia CC BY-NC-SA.</span></div><div id="demGeeMsg"></div>
    <h3>Filtro declarado de picos</h3><p class="chip">Para un DSM: las celdas que sobresalen más que el umbral sobre la mediana de su ventana se reemplazan por esa mediana. Crea un MDT nuevo (el original no se toca) y lo registra; queda en el historial con el número de celdas corregidas.</p>
    <div class="fila">${campo("Umbral (m)", "picU", "3", "3", "number")}${campo("Ventana (celdas, impar)", "picV", "5", "5", "number")}<button id="picOk">Aplicar filtro de picos</button></div><div id="picMsg"></div>
    <h3>Quemar ríos en el terreno</h3><p class="chip">FABDEM y los MDT de suelo desnudo suavizan los cauces: graba la red HydroSHEDS del proyecto con una profundidad que declaras (z = mínimo 3×3 − profundidad). Crea un MDT nuevo y lo registra.</p>
    <div class="fila">${campo("Profundidad (m)", "qrP", "2", "2", "number")}${campo("Ancho (celdas)", "qrA", "1", "1", "number")}<button id="qrOk">Quemar ríos</button></div><div id="qrMsg"></div></section>
   <section class="tarjeta"><h2>Importar MDT / DSM de dron (GeoTIFF)</h2>
    <p class="chip">El ráster no se copia ni se modifica: el proyecto lo referencia por ruta y hash. Debe estar en metros y en el mismo CRS del proyecto (${esc(S.estado.proyecto.crs)}). El tipo y el datum los declaras tú.</p>
    <div class="fila"><div class="crece"><label for="demArch">Archivo .tif</label><input type="text" id="demArch" placeholder="C:\\ruta\\DEM_dron.tif"></div><button id="demExa">Examinar…</button><button id="demIns">Inspeccionar</button></div><div id="demRes"></div></section>
   <section class="tarjeta"><h2>Vista previa del terreno de estudio</h2><img class="mapa mapa-grande" id="imgT" alt="Sombreado del terreno del área de estudio" src="/api/terreno/preview.png?t=${Date.now()}"></section>
   <section class="tarjeta"><h2>Modelo digital de elevación</h2><div id="tLam"></div><p class="chip">El terreno en 3D está en <a href="#/visor">★ Visor 3D</a>.</p></section>
   <div id="cfgT"></div><section class="tarjeta"><details><summary>Historial de registros del terreno</summary><div id="tHist"></div></details></section>`);
  api("/api/terreno/historial").then(j => { const el = $("#tHist"); if (el) el.innerHTML = (j.historial || []).length ? `<table><thead><tr><th>Fecha</th><th>Resultado</th><th>Archivo</th><th>Detalle</th></tr></thead><tbody>${j.historial.map(x => `<tr><td>${esc(x.fecha)}</td><td>${x.resultado === "error" ? badge("error", "error") : badge("ok", "registrado")}</td><td style="font-size:12px">${esc(x.archivo || "")}</td><td style="font-size:12px">${esc(x.mensaje || (x.aoi ? "área " + x.aoi.map(v => Math.round(v)).join(", ") + " · " + x.res_m + " m" : ""))}</td></tr>`).join("")}</tbody></table>` : '<p class="chip">Sin registros.</p>'; });
  panelConfig("terreno", $("#cfgT"));
  const lam = new Image(); lam.className = "mapa mapa-grande"; lam.alt = "Lámina del MDT"; lam.style.width = "100%"; lam.style.borderRadius = "10px";
  lam.onerror = () => { const el = $("#tLam"); if (el) el.innerHTML = nota("Aún no hay MDT registrado: usa «Usar MDT de Earth Engine» o carga tu GeoTIFF.", "pend"); };
  lam.onload = () => { const el = $("#tLam"); if (el) { el.innerHTML = ""; el.appendChild(lam); } };
  if ($("#tLam")) $("#tLam").innerHTML = '<p class="chip">Preparando la lámina…</p>';
  lam.src = "/api/terreno/lamina.png?t=" + Date.now();
  $("#qrOk").onclick = async () => {                                          // Omega O7
    const j = await api("/api/terreno/quemar_rios", {profundidad_m: +$("#qrP").value, ancho_celdas: +$("#qrA").value});
    $("#qrMsg").innerHTML = j.error ? nota(esc(j.error), "err") : nota(`Ríos grabados: ${fmt(j.quema.tramos, 0)} tramos, ${fmt(j.quema.celdas_quemadas, 0)} celdas (~${fmt(j.quema.longitud_aprox_km, 1)} km) a ${fmt(j.quema.profundidad_m, 1)} m. Nuevo terreno registrado.`, "ok");
    if (!j.error) setTimeout(vTerreno, 1500);
  };
  $("#picOk").onclick = async () => {                                         // Omega O2
    const j = await api("/api/terreno/filtrar_picos", {umbral_m: +$("#picU").value, ventana: +$("#picV").value});
    $("#picMsg").innerHTML = j.error ? nota(esc(j.error), "err") : nota(`Filtro aplicado: ${fmt(j.filtro.celdas_corregidas, 0)} celdas corregidas (${fmt(j.filtro.pct_celdas, 2)} %), descenso medio ${fmt(j.filtro.descenso_medio_m, 2)} m, máximo ${fmt(j.filtro.descenso_max_m, 2)} m. Nuevo terreno registrado.`, "ok");
    if (!j.error) setTimeout(vTerreno, 1500);
  };
  $("#demExa").onclick = async () => { const j = await api("/api/dialogo", {tipo: "raster"}); if (j.ruta) $("#demArch").value = j.ruta; };
  $("#demGee").onclick = async () => {
    const b = $("#demGee"); b.disabled = true; const m = $("#demGeeMsg");
    const j = await api("/api/terreno/gee", {ambito: $("#demAmb").value, producto: $("#demProd").value});
    if (j.error) { m.innerHTML = nota(esc(j.error), "err"); b.disabled = false; return; }
    if (!j.descarga) { m.innerHTML = nota(esc(j.mensaje), "ok"); aviso("Terreno listo"); await cargarEstado(); setTimeout(vTerreno, 800); return; }
    const seguir = async () => {
      if (!document.body.contains(m)) return;
      const d = ((await api("/api/descargas")).descargas || []).find(x => x.id === j.descarga);
      if (!d || d.estado === "en_curso") { m.innerHTML = nota(`Descargando el MDT… ${Math.round(((d || {}).progreso || 0) * 100)} % · ${esc((d || {}).mensaje || "")}`, "pend"); return setTimeout(seguir, 2000); }
      if (d.estado === "fallido") { m.innerHTML = nota(esc(d.mensaje || "Falló la descarga"), "err"); b.disabled = false; return; }
      m.innerHTML = nota("MDT descargado y registrado como terreno del proyecto.", "ok"); aviso("Terreno listo"); await cargarEstado(); setTimeout(vTerreno, 800);
    };
    seguir();
  };
  $("#demIns").onclick = async () => {
    const r = await api("/api/terreno/inspeccionar", {archivo: $("#demArch").value.trim()});
    if (r.error) { $("#demRes").innerHTML = nota(esc(r.error), "err"); return; }
    $("#demRes").innerHTML = `<div class="tabla-ancha"><table><tbody>
      <tr><th>CRS</th><td>${esc(r.crs)}</td><th>Resolución</th><td>${fmt(r.res_m, 3)} m</td><th>Tamaño</th><td>${fmt(r.ancho_px, 0)} × ${fmt(r.alto_px, 0)} px · ${fmt(r.tamano_mb, 1)} MB</td></tr>
      <tr><th>Extensión</th><td>${fmt(r.ancho_m, 0)} × ${fmt(r.alto_m, 0)} m</td><th>Cota (p0,5–p99,5)</th><td>${fmt(r.z_p05_p995[0], 1)} – ${fmt(r.z_p05_p995[1], 1)} m</td><th>Celdas válidas</th><td>${fmt(r.validas_pct, 1)} %</td></tr></tbody></table></div>
     ${coincidenciaMDT(r.coincidencia)}
     ${r.sugerencia ? `<h3>Cómo usar este MDT (${fmt(r.sugerencia.res_nativa_m, 2)} m)</h3><table><thead><tr><th>Celda del modelo</th><th>Área máxima por corrida</th><th>Lado máximo</th></tr></thead><tbody>${r.sugerencia.opciones.map(o => `<tr><td>${fmt(o.celda_m, 1)} m</td><td>${fmt(o.area_max_km2, 2)} km²</td><td>${fmt(o.lado_max_m, 0)} m</td></tr>`).join("")}</tbody></table>
       ${r.sugerencia.recomendaciones.map(t => nota(esc(t), "ok")).join("")}${r.sugerencia.avisos.map(t => nota(esc(t), "pend")).join("")}` : ""}
     ${(r.avisos || []).map(t => nota(esc(t))).join("")}
     <div class="fila"><div><label for="demTipo">Tipo de modelo</label><select id="demTipo"><option value="DSM">DSM (superficie con edificios/vegetación)</option><option value="MDT">MDT (suelo desnudo)</option><option value="desconocido">desconocido</option></select></div>
      ${campo("Datum vertical", "demDatum", "no verificado")}${campo("Resolución del modelo (m)", "demRes", String(Math.max(10, r.res_m)))}</div>
     <div class="fila">${campo("Área de estudio [x0,x1,y0,y1] (opcional: por defecto 600 m centrados)", "demAoi", "", "p. ej. 659100,659700,9766500,9767100")}</div>
     <p class="chip">Se respaldan la configuración y el proyecto actuales (.bak). El área se limita a 250 000 celdas del modelo.</p>
     <div class="fila"><button class="principal" id="demReg" ${r.apto ? "" : "disabled"}>Registrar como terreno del proyecto</button></div><div id="demOk"></div>`;
    if (r.apto) $("#demReg").onclick = async () => {
      const aoi = $("#demAoi").value.trim() ? $("#demAoi").value.split(",").map(Number) : null;
      const j = await api("/api/terreno/registrar", {archivo: $("#demArch").value.trim(), tipo_terreno: $("#demTipo").value, datum: $("#demDatum").value.trim(), res: +$("#demRes").value, aoi});
      if (j.error) { $("#demOk").innerHTML = nota(esc(j.error), "err"); return; }
      aviso("Terreno registrado"); await cargarEstado(); await vTerreno();
      $("#principal").insertAdjacentHTML("afterbegin", nota(`Terreno registrado: ${esc(j.nota)}. Área ${j.aoi.join(", ")} · ${fmt(j.celdas_modelo, 0)} celdas a ${j.res_modelo_m} m.`, "ok"));
    };
  };
  const v = await api("/api/verificar", {}); S.verif = v;
  $("#chkT").innerHTML = v.chequeos.filter(c => /terreno|aoi|datum/.test(c.id)).map(chequeo).join("");
  if (String((S.estado.proyecto || {}).tipo_terreno || "").toUpperCase() === "DSM") {           // 8.0.1: un novato no sabe que GLO-30 es superficie
    $("#chkT").insertAdjacentHTML("afterbegin", nota("Tu terreno es un <b>DSM</b> (Copernicus GLO-30): mide la altura de techos, árboles y cultivos, no la del suelo. En llanuras con caña, banano o ciudad el agua choca con ellos como si fueran muros. Recomendado: elige <b>FABDEM</b> abajo y pulsa «Usar MDT de Earth Engine» (o aplica el filtro de picos).", "pend"));
    if ($("#demProd")) $("#demProd").value = "fabdem";
  }
}
/* ¿El MDT subido cae en la zona de trabajo y se superpone al terreno regional de Earth Engine? Esquema en el CRS del proyecto (metros). */
function coincidenciaMDT(c) {
  if (!c) return "";
  const tipo = {coincide: "ok", parcial: "aviso", no_coincide: "err", sin_sitio: "aviso", error: "err"}[c.veredicto] || "aviso";
  let svg = "";
  if (c.mdt) {
    const R = [["gee", c.gee, "#6b7f99", "Terreno regional GEE (GLO-30)"], ["mdt", c.mdt, "#6cc4ec", "MDT subido"], ["aoi", c.aoi, "#ffd166", "Área de estudio actual"]].filter(z => z[1]);
    const xs = R.flatMap(z => [z[1][0], z[1][1]]).concat(c.sitio ? [c.sitio[0]] : []), ys = R.flatMap(z => [z[1][2], z[1][3]]).concat(c.sitio ? [c.sitio[1]] : []);
    const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys), W = 640, H = 300, m = 14, k = Math.min((W - 2 * m) / ((x1 - x0) || 1), (H - 2 * m) / ((y1 - y0) || 1));
    const X = v => m + (v - x0) * k, Y = v => H - m - (v - y0) * k;
    svg = `<svg viewBox="0 0 ${W} ${H}" style="width:100%;max-width:640px;background:#0f1b2d;border:1px solid #25364f;border-radius:10px" role="img" aria-label="Esquema de superposición del MDT con la zona de trabajo">` +
      R.map(z => `<rect x="${X(z[1][0])}" y="${Y(z[1][3])}" width="${Math.max(2, (z[1][1] - z[1][0]) * k)}" height="${Math.max(2, (z[1][3] - z[1][2]) * k)}" fill="${z[2]}" fill-opacity="${z[0] === "gee" ? .16 : .22}" stroke="${z[2]}" stroke-width="2" ${z[0] === "gee" ? 'stroke-dasharray="6 4"' : ""}/>`).join("") +
      (c.sitio ? `<circle cx="${X(c.sitio[0])}" cy="${Y(c.sitio[1])}" r="6" fill="#ff4da6" stroke="#fff" stroke-width="1.5"/><text x="${X(c.sitio[0]) + 10}" y="${Y(c.sitio[1]) + 4}" font-size="12" fill="#e6edf5">sitio del proyecto</text>` : "") + "</svg>" +
      `<div style="display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:#9fb0c6;margin:4px 0">${R.map(z => `<span><i style="display:inline-block;width:14px;height:10px;background:${z[2]};opacity:.6;margin-right:4px"></i>${esc(z[3])}</span>`).join("")}<span><i style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#ff4da6;margin-right:4px"></i>sitio</span></div>`;
  }
  return `<div style="margin:10px 0"><h3>¿Coincide con la zona de trabajo?</h3>${nota(`<b>${esc(c.mensaje || "")}</b>${c.base_gee ? "<br>" + esc(c.base_gee) : ""}${c.distancia_al_sitio_km != null && c.veredicto === "no_coincide" ? "" : ""}`, tipo)}${(c.pistas || []).map(p => nota(esc(p), "pend")).join("")}${svg}</div>`;
}
const chequeo = c => `<div class="chequeo"><div class="ic">${badge(c.estado, ESTADOS_TXT[c.estado])}</div><div>${esc(c.mensaje)}</div></div>`;

/* ---------------------------------------------------------------- 6 Cuencas */
async function vCuencas() {
  const c = await api("/api/cuencas/resumen");
  $("#principal").innerHTML = encabezado("Cuencas y canales", "Capas ya diagnosticadas (28 subcuencas, 4 ríos). Los cruces río–dominio son <b>candidatos</b>: sin sección, cota de fondo ni sentido de flujo confirmados no se usan como entradas.") + (c.error ? nota(esc(c.error), "pend") : `
  <div class="rejilla"><section class="tarjeta"><h2>Correspondencia con hidro (modelo de referencia externo)</h2><p>${Object.entries(c.correspondencia).map(([k, v]) => `${badge(k === "exacta" ? "ok" : "aviso", k.replace(/_/g, " "))} ${v}`).join(" · ")}</p>
    <h3>Áreas que no concuerdan (>1 %)</h3><table><thead><tr><th>Cuenca</th><th class="num">Polígono km²</th><th class="num">hidro km²</th><th class="num">Dif. %</th></tr></thead><tbody>${c.areas_no_concuerdan.map(a => `<tr><td>${esc(a.nombre_shp)}</td><td class="num">${fmt(a.area_shp_km2)}</td><td class="num">${fmt(a.area_hms_km2)}</td><td class="num">${fmt(a.dif_area_pct, 1)}</td></tr>`).join("")}</tbody></table></section>
   <section class="tarjeta"><h2>Entradas candidatas (cruce río–dominio)</h2><table><thead><tr><th>Río</th><th>Borde</th><th class="num">X</th><th class="num">Y</th><th>Estado</th></tr></thead><tbody>${c.candidatos_entrada.map(e => `<tr><td>${esc(e.rio)}</td><td>${esc(e.borde)}</td><td class="num">${fmt(e.x, 0)}</td><td class="num">${fmt(e.y, 0)}</td><td>${`<span class="badge b-aviso" title="Sin sección, cota de fondo ni sentido de flujo confirmados">candidata</span>`}</td></tr>`).join("")}</tbody></table></section></div>
  <section class="tarjeta"><details open><summary>Datos faltantes antes de simular con cuencas y ríos</summary><pre class="log">${esc(c.datos_faltantes)}</pre></details>
   <div class="fila" style="margin-top:12px">${pendiente("Editar entradas, perfiles y breaklines: capas QGIS/GeoPackage")}</div><div class="fila" style="margin-top:8px">${pendiente("Estructuras candidatas/confirmadas: biblioteca VOTEX")}</div></section>`);
}

/* ---------------------------------------------------------------- 7 Corrida */
async function vCorrida() {
  $("#principal").innerHTML = encabezado("Corrida", "Comprobación previa → ejecución (una tarea por vez) → seguimiento. «Completada» significa que el proceso terminó, no que el modelo esté validado.") + requiereProyecto();
  if (!S.estado.proyecto) return;
  $("#principal").insertAdjacentHTML("beforeend", `<div id="cfgC"></div>`); panelConfig("corrida", $("#cfgC"));
  $("#principal").insertAdjacentHTML("beforeend", `<section class="tarjeta" id="forz"><h2>0 · Forzamiento: evento observado e hidrogramas de entrada</h2><div id="forzRes"><p class="chip">Leyendo…</p></div></section>`); pintarForzamiento();
  $("#principal").insertAdjacentHTML("beforeend", `<div class="rejilla"><section class="tarjeta"><h2>1 · Verificar entradas</h2><button id="btnVer">Comprobar</button><div id="resVer" style="margin-top:10px"></div></section>
   <section class="tarjeta"><h2>2 · Ejecutar</h2>
    <div class="fila"><div><label for="runTr">Período de retorno Tr (años)</label><select id="runTr">${[2, 5, 10, 25, 50, 100].map(t => `<option ${t === 100 ? "selected" : ""}>${t}</option>`).join("")}</select></div>
     <p class="chip" style="flex:1">Tormenta de diseño de la IDF del proyecto (módulo 4). Una corrida por Tr; 100 años por defecto. Si declaraste un evento observado, el Tr no se usa.</p></div>
    <div class="fila"><button class="principal" id="btnRun">Ejecutar caso pequeño</button><button class="peligro" id="btnCan" disabled>Cancelar</button></div>
    <div id="estRun" style="margin-top:12px"></div></section></div>
   <section class="tarjeta"><h2>Registro de la corrida</h2><pre class="log" id="logRun">Sin corrida seleccionada.</pre></section>
   <section class="tarjeta"><h2>Historial</h2><div id="histo"></div></section>`);
  $("#btnVer").onclick = verificar; $("#btnRun").onclick = ejecutar; $("#btnCan").onclick = cancelar;
  if (S.verif) pintarVerif(S.verif);
  await refrescarCorrida(); S.temporizador = setInterval(refrescarCorrida, 1200);
}
/* G17/G18 (caso real Milagro): el evento se escribe en HORA LOCAL de la estación; los hidrogramas de entrada (t_s, Q_m3s) entran por su celda */
async function pintarForzamiento() {
  const f = await api("/api/corrida/forzamiento"); if (f.error) { $("#forzRes").innerHTML = nota(esc(f.error), "err"); return; }
  const ev = f.evento_observado, ent = f.entradas_hidrograma || [];
  const sinEst = !(f.estaciones || []).length;
  $("#forzRes").innerHTML = `<h3>Evento observado (opcional)</h3>` + (sinEst && !ev ? nota("<b>Sin datos propios de lluvia:</b> la corrida usa la tormenta de diseño (IDF del módulo 4) con el Tr que elijas abajo. No hace falta llenar nada aquí.", "ok") : "") + (ev ? nota(`En uso: ${ev.forzamiento_externo ? `<b>${ev.forzamiento_externo.tipo === "pronostico" ? "PRONÓSTICO" : "ESTIMACIÓN SATELITAL"}</b> (${esc(ev.forzamiento_externo.nombre || "")}; no es una observación) · ` : ""}<b>${esc(ev.id)}</b>${ev.estacion ? " · estación " + esc(ev.estacion) : ""}${ev.real_largo ? " · evento real largo (tope 96 h si se estima ≤ 30 min)" : ""} · ${fmt(f.sim_horas, 1)} h simuladas`, "ok") : nota("Sin evento observado: la corrida usa la tormenta de diseño (IDF).", "pend")) +
    `<div ${sinEst ? "hidden" : ""}><div class="fila"><div class="crece"><label for="fzEst">Estación del proyecto</label><select id="fzEst">${(f.estaciones || []).map(e => `<option value="${esc(e.id)}">${esc(e.id)} · ${esc(e.nombre || "")}</option>`).join("")}</select></div>
     ${campo("Inicio (hora local de la estación)", "fzIni", "", "ej.: AAAA-MM-DD hh:mm")}${campo("Fin (hora local)", "fzFin", "", "ej.: AAAA-MM-DD hh:mm")}</div>
     <div class="fila"><button id="fzUsar">Usar este evento</button>${ev ? '<button id="fzQuitar">Quitar evento</button>' : ""}</div></div><div id="fzEvRes"></div>
     <h3>Hidrogramas de entrada (agua que llega desde aguas arriba)</h3>
     <p class="chip">Una fila por entrada: <b>nombre; ruta del CSV (columnas t_s y Q_m3s, empieza en 0 y termina en Q = 0); x; y</b> en el CRS del proyecto, dentro del área de cálculo${f.aoi ? ` (${fmt(f.aoi[0], 0)}–${fmt(f.aoi[1], 0)} E, ${fmt(f.aoi[2], 0)}–${fmt(f.aoi[3], 0)} N)` : ""}. Cada una entra por su celda; la corrida dura hasta el final del hidrograma más largo.</p>
     <textarea id="fzEnt" rows="4" style="width:100%">${esc(ent.map(e => `${e.nombre}; ${e.csv}; ${e.xy[0]}; ${e.xy[1]}`).join("\n"))}</textarea>
     <div class="fila"><button id="fzEntOk">Declarar hidrogramas</button><button id="fzEntNo">Quitar todos</button></div><div id="fzEntRes"></div>
     <h3>Cuencas externas (solo tormentas de diseño Tr)</h3>
     <p class="chip">El núcleo calcula el hidrograma de cada cuenca con la MISMA IDF y Tr de la 2D (SCS-CN + HU SCS), usando solo su área fuera del dominio. Una fila por cuenca: <b>nombre; carpeta de la cuenca; CN; lag (h); x; y</b>. Cuencas del proyecto: ${(f.cuencas || []).map(esc).join(", ") || "—"}.</p>
     <textarea id="fzCue" rows="3" style="width:100%">${esc((f.cuencas_externas || []).map(c => `${c.nombre}; ${(c.shp.split(/[\\/]/).slice(-2, -1)[0] || c.shp)}; ${c.cn}; ${c.lag_h}; ${c.entrada_xy[0]}; ${c.entrada_xy[1]}`).join("\n"))}</textarea>
     <div class="fila"><button id="fzCueOk">Declarar cuencas externas</button></div><div id="fzCueRes"></div>`;
  $("#fzUsar").onclick = async () => {
    const j = await api("/api/proyecto/evento", {estacion: $("#fzEst").value, inicio: $("#fzIni").value, fin: $("#fzFin").value, zona: "local"});
    $("#fzEvRes").innerHTML = j.error ? nota(esc(j.error), "err") : nota(`Evento declarado: ${fmt(j.P_total_mm, 1)} mm · hora local ${esc(j.inicio_local || "")} → ${esc(j.fin_local || "")} (${esc(j.zona_local || "")}) · UTC ${esc(j.inicio_utc)} → ${esc(j.fin_utc)} · ${fmt(j.sim_horas, 1)} h simuladas.<br>${(j.advertencias || []).map(esc).join("<br>")}`, "ok");
    if (!j.error) setTimeout(pintarForzamiento, 2500);
  };
  if ($("#fzQuitar")) $("#fzQuitar").onclick = async () => { const j = await api("/api/proyecto/evento_quitar", {}); aviso(j.error || "Evento quitado: vuelve la tormenta de diseño"); pintarForzamiento(); };
  const declarar = async (lineas) => {
    const entradas = lineas.map(l => l.split(";").map(x => x.trim())).filter(p => p.length >= 4 && p[0]).map(p => ({nombre: p[0], csv: p[1], xy: [Number(p[2]), Number(p[3])]}));
    const j = await api("/api/corrida/entradas", {entradas});
    $("#fzEntRes").innerHTML = j.error ? nota(esc(j.error), "err") : nota(j.entradas.length ? `Declaradas: ${j.entradas.map(e => `<b>${esc(e.nombre)}</b> pico ${fmt(e.pico_m3s, 1)} m³/s · ${fmt(e.duracion_h, 1)} h · ${fmt(e.volumen_m3 / 1e6, 2)} hm³`).join(" · ")}. ${esc(j.nota)}` : "Sin hidrogramas de entrada.", "ok");
  };
  $("#fzEntOk").onclick = () => declarar($("#fzEnt").value.split("\n")); $("#fzEntNo").onclick = () => { $("#fzEnt").value = ""; declarar([]); };
  $("#fzCueOk").onclick = async () => {                                                     // G23
    const cuencas = $("#fzCue").value.split("\n").map(l => l.split(";").map(x => x.trim())).filter(p => p.length >= 6 && p[0]).map(p => ({nombre: p[0], cuenca: p[1], cn: +p[2], lag_h: +p[3], entrada_xy: [+p[4], +p[5]]}));
    const j = await api("/api/corrida/cuencas_externas", {cuencas});
    $("#fzCueRes").innerHTML = j.error ? nota(esc(j.error), "err") : nota(`${j.cuencas_externas.length} cuenca(s) externa(s) declaradas. ${esc(j.nota)}`, "ok");
  };
}
async function verificar() { $("#resVer").innerHTML = '<p class="chip">Verificando (puede tardar al calcular hashes grandes)…</p>'; S.verif = await api("/api/verificar", {}); pintarVerif(S.verif); }
function pintarVerif(v) {
  $("#resVer").innerHTML = (v.puede_ejecutar ? nota("Las entradas permiten ejecutar el caso.", "ok") : nota("Hay errores: corrígelos antes de ejecutar.", "err")) + v.chequeos.map(chequeo).join("") +
    (v.estimacion ? `<p class="chip">Estimación: ${fmt(v.estimacion.celdas, 0)} celdas · ~${fmt(v.estimacion.pasos_aprox, 0)} pasos · ≈ ${fmt(v.estimacion.tiempo_estimado_s, 0)} s · ${fmt(v.estimacion.memoria_estimada_mb, 0)} MB. ${esc(v.estimacion.base)}</p>` : "");
}
async function ejecutar() {
  const j = await api("/api/corrida/iniciar", {tr: +($("#runTr") || {}).value || 100}); if (j.error) { aviso(j.error, 8000); if (j.chequeos) { S.verif = await api("/api/verificar", {}); pintarVerif(S.verif); } return; }
  S.corridaSel = j.id; aviso("Corrida iniciada: " + j.id); refrescarCorrida();
}
async function cancelar() { const j = await api("/api/corrida/cancelar", {}); aviso(j.cancelada ? "Corrida cancelada" : "No había corrida activa"); refrescarCorrida(); }
async function refrescarCorrida() {
  if (S.ruta !== "corrida") return;
  await cargarEstado(); const lista = S.estado.corridas; const id = S.corridaSel || (lista[0] && lista[0].id);
  const activa = S.estado.corrida_activa; $("#btnCan").disabled = !activa; $("#btnRun").disabled = activa;
  $("#histo").innerHTML = lista.length ? `<table><thead><tr><th>Corrida</th><th>Estado</th><th>Inicio</th><th>Mensaje</th></tr></thead><tbody>${lista.map(e => `<tr><td><a href="#" data-r="${esc(e.id)}">${esc(e.id)}</a></td><td>${badge(e.estado)}</td><td>${esc((e.inicio || "").replace("T", " "))}</td><td>${esc(e.mensaje || "")}</td></tr>`).join("")}</tbody></table>` : "<p class='chip'>Todavía no hay corridas.</p>";
  document.querySelectorAll("[data-r]").forEach(a => a.onclick = e => { e.preventDefault(); S.corridaSel = a.dataset.r; refrescarCorrida(); });
  if (!id) return; const e = await api("/api/corrida/estado?id=" + encodeURIComponent(id));
  const reanudar = e.estado === "interrumpido" && e.reanudable ? `<div class="fila"><button class="principal" id="btnReanudar" data-id="${esc(id)}">▶ Reanudar desde el ${Math.round(((e.punto_control || {}).progreso || 0) * 100)} %</button><span class="chip">No se repite lo ya calculado. El resultado es el mismo que sin el corte.</span></div>` : (e.estado === "interrumpido" ? nota("Esta corrida se cortó antes de su primer punto de control (se guarda cada 10 minutos): hay que lanzarla de nuevo.", "pend") : "");
  $("#estRun").innerHTML = reanudar + `<p>${badge(e.estado)} <b>${esc(id)}</b></p><div class="barra-prog" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round((e.progreso || 0) * 100)}"><i style="width:${Math.round((e.progreso || 0) * 100)}%"></i></div><p class="chip">${esc(e.mensaje || "")}${e.pasos ? " · " + fmt(e.pasos, 0) + " pasos" : ""}</p>` +
    (e.estado === "completado" ? `<p><a href="#/evaluacion" data-eval="${esc(id)}">Ver métricas y mapa →</a> · <a href="#/campo" data-campo="${esc(id)}">Validar con la comunidad (módulo 12) →</a></p>` : "");
  const eva = $("[data-eval]"); if (eva) eva.onclick = () => { S.corridaSel = eva.dataset.eval; };
  const cam = $("[data-campo]"); if (cam) cam.onclick = () => { S.campoSel = cam.dataset.campo; };
  const lg = $("#logRun"); lg.textContent = e.log || "(sin registro)"; lg.scrollTop = lg.scrollHeight;
  const br = $("#btnReanudar"); if (br) br.onclick = async () => { br.disabled = true; const j = await api("/api/corrida/reanudar", {id: br.dataset.id}); aviso(j.error || "Corrida reanudada desde su último punto de control.", 6000); refrescarCorrida(); };
}

/* ---------------------------------------------------------------- 8 Evaluación */
async function vEvaluacion() {
  $("#principal").innerHTML = encabezado("Evaluación", "Qué tan bien se conservan los volúmenes y qué tan estable fue el cálculo. Es evaluación numérica del modelo, <b>no</b> evidencia de exactitud física ni de capacidad de canales.") + requiereProyecto();
  if (!S.estado.proyecto) return;
  const comp = (S.estado.corridas || []).filter(c => c.estado === "completado"); const id = S.corridaSel && comp.find(c => c.id === S.corridaSel) ? S.corridaSel : (comp[0] && comp[0].id);
  if (!id) return $("#principal").insertAdjacentHTML("beforeend", nota("No hay corridas completadas. Ejecuta un caso en la etapa 7.", "pend"));
  const r = await api("/api/corrida/resultado?id=" + encodeURIComponent(id)); const ev = r.evaluacion || {}, rs = r.resumen || {}, mp = r.mapa || {};
  const M = (k, v, u = "", d = 2) => `<div class="metrica"><div class="v">${fmt(v, d)}${u ? ` <small>${u}</small>` : ""}</div><div class="k">${esc(k)}</div></div>`;
  const MS = (k, v, u = "") => `<div class="metrica"><div class="v">${fmtS(v)}${u ? ` <small>${u}</small>` : ""}</div><div class="k">${esc(k)}</div></div>`;
  const NE = k => `<div class="metrica noeval"><div class="v">no evaluada</div><div class="k">${esc(k)}</div></div>`;
  $("#principal").insertAdjacentHTML("beforeend", `
   <div class="fila" style="margin-bottom:10px"><label for="selRun" style="margin:0">Corrida</label><select id="selRun">${comp.map(c => `<option ${c.id === id ? "selected" : ""}>${esc(c.id)}</option>`).join("")}</select><a class="btn" href="#/campo" id="evCampo" data-campo="${esc(id)}">Validar con la comunidad →</a></div>
   ${(r.escenario && r.escenario.tipo === "cmip6") ? nota("<b>Escenario Y · CMIP6</b> (" + esc(r.escenario.nombre) + "): la lluvia de diseño de entrada se multiplicó por " + fmt(r.escenario.factor, 3) + " (" + (r.escenario.tasa_cambio_pct >= 0 ? "+" : "") + fmt(r.escenario.tasa_cambio_pct, 0) + " %). Es una <b>proyección bajo supuesto</b>: la línea base fue asumida por decisión del usuario y no está calibrada ni validada. Compara siempre contra X (condiciones existentes).", "") : rs.tipo_forzamiento === "pronostico" ? nota("<b>PRONÓSTICO</b> «" + esc((rs.idf_info || {}).id || "") + "» (" + esc((rs.forzamiento_externo || {}).nombre || "") + "): " + fmt(rs.P_total_mm, 1) + " mm. Modelo <b>no calibrado, no validado</b>: no es una observación, no es una huella de inundación y no es una alerta oficial (INAMHI / SNGR).", "pend") : rs.tipo_forzamiento === "estimacion_satelital" ? nota("<b>Lluvia ESTIMADA POR SATÉLITE</b> «" + esc((rs.idf_info || {}).id || "") + "» (" + esc((rs.forzamiento_externo || {}).nombre || "") + "): " + fmt(rs.P_total_mm, 1) + " mm. El satélite no mide en tierra y en islas subestima mucho. Modelo <b>no calibrado, no validado</b>.", "pend") : rs.tipo_forzamiento === "evento_observado" ? nota("Evento de lluvia <b>observado</b> «" + esc((rs.idf_info || {}).id || "") + "» (histórico): " + fmt(rs.P_total_mm, 1) + " mm. Modelo <b>no calibrado, no validado</b>: no es una validación ni una huella de inundación observada.", "") : nota("Diseño IDF histórica (" + esc(rs.escenario || "") + ", Tr " + esc(rs.Tr || "") + "), no es un evento observado. <b>No calibrado, no validado.</b>", "")}
   ${(r.alertas || []).map(a => nota("⚠ " + esc(a), "err")).join("")}
   <section class="tarjeta"><h2>Balance de volumen</h2><div class="metricas">
    ${M("Volumen disponible", ev.volumen_disponible_m3, "m³", 0)}${MS("Diferencia del balance físico", ev.diferencia_balance_fisico_m3, "m³")}${MS("Diferencia del balance físico", ev.diferencia_balance_fisico_pct, "%")}
    ${MS("Residual tras el ajuste numérico", ev.residual_tras_ajuste_m3, "m³")}${M("Volumen que queda almacenado", ev.porcentaje_volumen_almacenado, "%", 1)}${M("Lluvia total del diseño", rs.P_total_mm, "mm", 1)}</div></section>
   <section class="tarjeta"><h2>Estabilidad del cálculo</h2><div class="metricas">
    ${M("Courant máximo", ev.Courant_max, "", 3)}${M("Courant objetivo", ev.Courant_objetivo, "", 2)}${M("Pasos de cálculo", ev.pasos_calculo, "", 0)}${M("Pasos con limitador", ev.porcentaje_pasos_con_limitador, "%", 1)}${M("Celdas limitadas (máx. en un paso)", (ev.fraccion_celdas_limitadas_max || 0) * 100, "%", 1)}</div>
    <details><summary>Qué significan</summary><p>${esc(ev.definicion_Courant || "")}. ${esc(ev.motivo_iteraciones || "")}</p></details></section>
   <section class="tarjeta"><h2>Resultado hidráulico</h2><div class="metricas">${M("Calado máximo de celda", rs.calado_max_m, "m", 2)}${M("Área con calado ≥ 0,3 m", rs["area_ge_0.3_km2"], "km²", 4)}${M("Área con calado ≥ 0,05 m", rs["area_ge_0.05_km2"], "km²", 4)}${M("Celdas del modelo", rs.celdas, "", 0)}${M("Resolución", rs.res_m, "m", 0)}
    ${NE("Capacidad de canales")}${NE("Pérdidas de carga en estructuras")}${rs.hidrograma_salida ? M("Caudal pico 2D en la salida", rs.hidrograma_salida.pico_2d_m3s, "m³/s", 2) : NE("Caudal y nivel por sección")}</div>
    <p class="chip">El calado máximo puntual no converge con la malla (ver CONVERGENCIA.md): usar áreas, no el máximo de una celda.</p></section>
   ${rs.hidrograma_salida ? `<section class="tarjeta"><h2>Hidrograma en la salida: 2D frente a hidro</h2><div class="metricas">
    ${M("Pico 2D", rs.hidrograma_salida.pico_2d_m3s, "m³/s", 2)}${M("Hora del pico 2D", rs.hidrograma_salida.t_pico_2d_h, "h", 2)}${M("Volumen 2D por la sección", rs.hidrograma_salida.volumen_2d_m3, "m³", 0)}
    ${rs.hidrograma_salida.hidro_pico_m3s != null ? M("Pico hidro (parámetros aceptados)", rs.hidrograma_salida.hidro_pico_m3s, "m³/s", 2) + M("Hora del pico hidro", rs.hidrograma_salida.hidro_t_pico_h, "h", 2) + M("Volumen hidro", rs.hidrograma_salida.hidro_volumen_m3, "m³", 0) : ""}</div>
    <img class="mapa" alt="Hidrograma en la salida" style="max-width:100%;background:#fff;border-radius:8px" src="/api/corrida/hidrograma.png?id=${encodeURIComponent(id)}&t=${Date.now()}" onerror="this.style.display='none'">
    <p class="chip">${esc(rs.hidrograma_salida.nota || "")}</p>
    <p class="chip">Un caudal <b>negativo</b> significa que el agua cruza la sección en sentido contrario (aguas arriba), por ejemplo cuando se embalsa y se devuelve.${rs.hidrograma_salida.volumen_2d_m3 < 0 ? " <b>Aquí el volumen neto por la sección es negativo:</b> la sección no está sobre el cauce que lleva el agua o el agua sale por otro borde; no uses este hidrograma como caudal del río." : ""}</p></section>` : ""}
   ${rs.velocidad_anomala ? `<section class="tarjeta"><h2>Velocidades anómalas (diagnóstico)</h2><div class="metricas">${M("Celdas por encima del umbral", rs.velocidad_anomala.celdas_anomalas, "", 0)}${M("Umbral", rs.velocidad_anomala.umbral_ms, "m/s", 1)}${M("Velocidad máxima", rs.velocidad_anomala.velocidad_max_ms, "m/s", 1)}${M("Velocidad máxima sin celdas anómalas", rs.velocidad_anomala.velocidad_max_robusta_ms, "m/s", 1)}${M("Percentil 99 (celdas mojadas)", rs.velocidad_anomala.p99_mojadas_ms, "m/s", 1)}</div>
    ${rs.velocidad_anomala.celda_max ? `<p class="chip">Máxima en x ${fmt(rs.velocidad_anomala.celda_max.x, 0)}, y ${fmt(rs.velocidad_anomala.celda_max.y, 0)} (calado máximo ${fmt(rs.velocidad_anomala.celda_max.calado_max_m, 2)} m). Ráster: v_anomala.tif.</p>` : ""}<p class="chip">${esc(rs.velocidad_anomala.nota || "")}</p></section>` : ""}
   ${rs.relleno_depresiones ? `<section class="tarjeta"><h2>Relleno de depresiones (opción declarada)</h2><div class="metricas">${M("Depresiones rellenadas", rs.relleno_depresiones.depresiones_encontradas - rs.relleno_depresiones.depresiones_conservadas, "", 0)}${M("Conservadas (más profundas que el umbral)", rs.relleno_depresiones.depresiones_conservadas, "", 0)}${M("Almacenamiento quitado", rs.relleno_depresiones.volumen_almacenamiento_quitado_m3, "m³", 0)}${M("Relleno máximo", rs.relleno_depresiones.profundidad_max_rellenada_m, "m", 2)}</div>${nota(esc(rs.relleno_depresiones.aviso), "pend")}</section>` : ""}
   <section class="tarjeta"><h2>Mapa del calado máximo (rásteres del núcleo)</h2>${r.mapa_png ? `<img class="mapa mapa-grande" alt="Mapa estático del calado máximo del área de estudio" src="/api/corrida/mapa.png?id=${encodeURIComponent(id)}&t=${Date.now()}">` : nota("Esta corrida no generó mapa.", "pend")}
    <p class="chip">Mapa estático del máximo; no es una evolución temporal. Sin imagen satelital. Cotas con datum vertical no verificado.</p></section>`);
  $("#principal").insertAdjacentHTML("beforeend", `<section class="tarjeta"><h2>Mapa con referencias (imagen satelital + OpenStreetMap)</h2>
    <p class="chip">Calado sobre imagen satelital con calles, edificios (expuestos en rojo), salud, educación, seguridad y gobierno de OSM; calcula la exposición. Descarga OSM una vez (datos públicos).</p>
    <div class="fila"><button id="mrGo">Generar mapa con referencias</button></div><div id="mrRes"></div></section>`);
  $("#mrGo").onclick = async () => { $("#mrRes").innerHTML = '<p class="chip">Descargando OSM e imagen y dibujando…</p>'; const j = await api("/api/mapa/referencias", {id});
    $("#mrRes").innerHTML = j.error ? nota(esc(j.error), "err") : nota(`Edificios OSM: ${fmt(j.exposicion.edificios_osm, 0)} · con ≥ 0,5 m: ${fmt(j.exposicion["edificios_calado_ge_0.5m"] || 0, 0)} · con ≥ 1 m: ${fmt(j.exposicion.edificios_calado_ge_1m || 0, 0)}` + (j.exposicion.instalaciones_osm != null ? ` · instalaciones: ${j.exposicion.instalaciones_osm} (con ≥ 0,3 m: ${j.exposicion["instalaciones_calado_ge_0.3m"]})` : "") + `. Base: ${esc(j.base)}. ${esc(j.aviso)}`, "ok") +
      `<img class="mapa" style="max-width:100%;background:#fff;border-radius:8px" src="/api/proyecto/archivo.png?f=${encodeURIComponent(j.figura)}&t=${Date.now()}">`; };
  $("#principal").insertAdjacentHTML("beforeend", window.peligroTarjeta ? window.peligroTarjeta() : ""); if (window.peligroEventos) window.peligroEventos(id);   // Lambda: botón calado · velocidad · peligro
  $("#principal").insertAdjacentHTML("beforeend", `<details class="tarjeta" id="valCard"><summary><h2 style="display:inline">Validación con observaciones (opcional)</h2></summary>
    ${nota("<b>Opcional.</b> Si no tienes caudal medido, imágenes de una inundación ni marcas de agua, sáltala: la validación con la comunidad está en el módulo 12. «Buscar eventos con Sentinel-1» necesita eventos sacados de un caudal medido (hidro › Calibración); sin caudal, escribe tú las fechas del evento (por ejemplo, el «evento más fuerte» que contó la comunidad en el módulo 12).", "")}
    <p class="chip">Contrasta ESTA corrida con lo observado. Por defecto: (1) caudal medido en la salida y (2) mancha de agua Sentinel-1 (Earth Engine). Abiertas: (3) manchas de otras fuentes y (4) evidencia de campo. No convierte la corrida en predicción.</p>
    <h3>Preparar una corrida con un evento real</h3>
    <div class="fila"><button id="valCand">Buscar eventos con Sentinel-1 cerca del pico</button></div><div id="valCandRes"></div>
    <div class="fila">${campo("Inicio", "valIni", "", "AAAA-MM-DD")}${campo("Fin", "valFin", "", "AAAA-MM-DD")}${campo("Celda (m, opcional)", "valRes", "60")}<button id="valPrep">Preparar corrida del evento</button><button id="valRest">Volver a la configuración anterior</button></div><div id="valPrepRes"></div>
    <h3>Contrastar</h3>
    <div class="fila"><button id="valQ">1 · Comparar con caudal observado</button>${campo("Fecha del pico", "valPico", "", "AAAA-MM-DD")}<button id="valS1">2 · Mancha Sentinel-1</button></div>
    <div class="fila">${campo("3 · Mancha externa (.gpkg/.shp/.geojson/.tif)", "valMan", "", "C:\\ruta\\mancha.gpkg")}${campo("Fuente", "valManF", "", "Global Flood Database, Copernicus EMS, SNGR…")}${campo("Fecha", "valManD", "", "AAAA-MM-DD")}<button id="valManB">Cargar</button></div>
    <div class="fila">${campo("4 · Evidencia de campo (CSV: x,y o lon,lat; calado_obs_m y/o mojado)", "valPto", "", "C:\\ruta\\marcas.csv")}${campo("Fuente", "valPtoF", "", "marcas de agua, fotos, testimonios…")}<button id="valPtoB">Cargar</button></div>
    <div class="fila"><button id="valTodo">Contrastar las fuentes que cargaste</button></div><div id="valRes"></div></details>`);
  const VR = (t, c) => { $("#valRes").innerHTML = nota(t, c); };
  const vpost = async (r, b, el, ok) => { el.innerHTML = '<p class="chip">Procesando…</p>'; const j = await api(r, b); el.innerHTML = j.error ? nota(esc(j.error), "err") : ok(j); return j; };
  $("#valCand").onclick = () => vpost("/api/validacion/candidatos", {con_s1: true}, $("#valCandRes"), j => `<table><thead><tr><th>Evento</th><th>Inicio</th><th>Pico</th><th>Fin</th><th class="num">Q pico</th><th>Sentinel-1</th><th></th></tr></thead><tbody>${j.eventos.map(e => `<tr><td>${esc(e.evento)}</td><td>${e.inicio}</td><td>${e.pico}</td><td>${e.fin}</td><td class="num">${fmt(e.q_pico_m3s, 2)}</td><td>${(e.s1 || []).join(", ") || "—"}</td><td><button data-ev='${JSON.stringify(e)}'>Usar</button></td></tr>`).join("")}</tbody></table><p class="chip">${esc(j.nota)}</p>`).then(() => document.querySelectorAll("#valCandRes button[data-ev]").forEach(b => b.onclick = () => { const e = JSON.parse(b.dataset.ev); $("#valIni").value = e.inicio; $("#valFin").value = e.fin; $("#valPico").value = e.pico; }));
  $("#valPrep").onclick = () => vpost("/api/validacion/preparar", {inicio: $("#valIni").value, fin: $("#valFin").value, res_m: +$("#valRes").value || null}, $("#valPrepRes"), j => nota(`Listo: ${j.dias} días, ${fmt(j.lluvia_total_mm, 1)} mm, ${fmt(j.sim_horas, 0)} h simuladas, celda ${j.res_m} m. Ve a 7 · Corrida 2D y ejecuta. ${esc(j.nota)}`, "ok"));
  $("#valRest").onclick = () => vpost("/api/validacion/restaurar", {}, $("#valPrepRes"), j => nota(j.restaurado ? "Configuración anterior restaurada." : "No había una corrida de validación preparada.", "ok"));
  $("#valQ").onclick = () => vpost("/api/validacion/caudal", {id}, $("#valRes"), j => nota(`Caudal: KGE ${fmt(j.KGE, 2)} · NSE ${fmt(j.NSE, 2)} · PBIAS ${fmt(j.PBIAS_pct, 1)} % · pico obs ${fmt(j.pico_obs_m3s, 2)} vs 2D ${fmt(j.pico_2d_m3s, 2)} m³/s. ${esc(j.nota)}`, "ok") + `<img class="mapa" style="max-width:100%;background:#fff" src="/api/validacion/caudal.png?id=${encodeURIComponent(id)}&t=${Date.now()}">`);
  $("#valS1").onclick = () => vpost("/api/validacion/sentinel1", {id, fecha_pico: $("#valPico").value}, $("#valRes"), j => nota(`Sentinel-1 del ${j.fecha_imagen} (+${j.dias_despues_del_pico} d): ${fmt(j.celdas_agua_s1, 0)} celdas con agua. CSI ${j.contraste["h_ge_0.05m"].CSI ?? "—"} (calado ≥ 0,05 m). ${esc(j.limites)}`, "ok"));
  $("#valManB").onclick = () => vpost("/api/validacion/mancha", {ruta: $("#valMan").value.trim(), fuente: $("#valManF").value.trim(), fecha: $("#valManD").value.trim()}, $("#valRes"), j => nota("Mancha registrada: " + esc(j.archivo), "ok"));
  $("#valPtoB").onclick = () => vpost("/api/validacion/puntos", {ruta: $("#valPto").value.trim(), fuente: $("#valPtoF").value.trim()}, $("#valRes"), j => nota(`Evidencia registrada: ${j.n_puntos} puntos.`, "ok"));
  $("#valTodo").onclick = () => vpost("/api/validacion/contrastar", {id}, $("#valRes"), j => `<table><thead><tr><th>#</th><th>Fuente</th><th>Tipo</th><th>Resultado</th></tr></thead><tbody>${j.tabla.map(f => `<tr><td>${f.n}</td><td>${esc(f.fuente)}</td><td>${esc(f.tipo)}</td><td>${esc(f.metrica)}</td></tr>`).join("")}</tbody></table><p class="chip">${esc(j.nota)}</p>`);
  $("#selRun").onchange = e => { S.corridaSel = e.target.value; navegar(); };
  { const ec = $("#evCampo"); if (ec) ec.onclick = () => { S.campoSel = ec.dataset.campo; }; }
}

/* ---------------------------------------------------------------- 9 CMIP6 */
async function vCmip6() {
  const c = await api("/api/cmip6/compuerta");
  $("#principal").innerHTML = encabezado("Cambio climático (CMIP6)", "Módulo penúltimo, <b>bloqueado</b> hasta calibrar y validar las condiciones existentes. Los factores climáticos modificarán la lluvia y se volverá a resolver hidrología e hidráulica; no se multiplican profundidades.") + `
  <section class="tarjeta">${nota("Bloqueado. " + esc(c.nota), "err")}<h3>Por qué sigue bloqueado</h3><ul>${(c.razones || []).map(r => `<li>${esc(r)}</li>`).join("")}</ul></section>
  <section class="tarjeta"><h2>Especificación (sin botones que simulen resultados)</h2><ul><li>NASA NEX-GDDP-CMIP6: verificar catálogo, miembros y licencias antes de descargar.</li><li>Evaluación de modelos con criterios definidos antes de mirar futuros; ensamble, sin «mejor modelo» universal.</li><li>Corrección local de sesgo solo si se justifica y preserva la señal de cambio.</li><li>Escenarios SSP y horizontes sobre la misma infraestructura de la línea base.</li></ul>
  <div class="fila">${pendiente("Descargar NEX-GDDP-CMIP6: bloqueado hasta línea base validada")}</div></section>`;
}

/* ---------------------------------------------------------------- 10 VOTEX */
async function vVotex() {
  $("#principal").innerHTML = encabezado("VOTEX 4D / exportación", "El visor 3D + tiempo solo puede mostrar <b>estados temporales realmente calculados</b>. Hoy el solver entrega el máximo (hmax): se ofrece mapa estático, no una película.") + `
  <div class="rejilla"><section class="tarjeta"><h2>Mapa estático real</h2><p>Disponible en la etapa 8 para cada corrida completada.</p><a class="btn" href="#/evaluacion">Ir a Evaluación</a></section>
   <section class="tarjeta"><h2>Visor 3D + tiempo</h2>${badge("aviso", "MAQUETA SINTÉTICA").replace("b-aviso", "b-sint")}<p>Maqueta de la interfaz del visor con datos inventados. No representa Milagro ni resultados del solver.</p><a class="btn" href="/visual/index.html" target="_blank" rel="noopener">Abrir maqueta sintética</a>
    <div class="fila" style="margin-top:12px">${pendiente("Exportar estados temporales: el solver aún no exporta h(t), velocidades ni secciones")}</div><div class="fila" style="margin-top:8px">${pendiente("Textura satelital y estilo carboncillo: requiere el visor georreferenciado con datos reales")}</div></section></div>`;
}

async function vVisor() {
  $("#principal").innerHTML = encabezado("★ Visor 3D de resultados", "Terreno y capas <b>reales</b> de una corrida en una maqueta isométrica: calado máximo, velocidad máxima y duración. Control de capas, exageración vertical y barrido por calado (no es evolución temporal: el solver aún no exporta h(t)).") + requiereProyecto() + (S.estado.proyecto ? `
  <section class="tarjeta"><iframe id="marcoVisor" title="Visor 3D de resultados" src="/visor" style="width:100%;height:78vh;min-height:560px;border:1px solid var(--linea);border-radius:12px;background:#07090c" allow="fullscreen"></iframe>
   <p class="chip"><a href="/visor" target="_blank" rel="noopener">Abrir a pantalla completa en una pestaña</a></p></section>` : "");
}
async function vContaminantes() {                                       // Omega O4: entrada propia en el menú
  $("#principal").innerHTML = encabezado("Contaminantes", "Dispersión de un derrame en un tramo de río: vista isométrica (venas → mancha) y planta sobre la imagen satelital siguiendo el cauce del MDT. Base pedagógica, sin calibrar ni validar.") +
    `<section class="tarjeta"><iframe title="Dispersión de contaminantes" src="/contaminantes" style="width:100%;height:1150px;border:0;border-radius:10px;background:#fff"></iframe>
     <p class="chip"><a href="/contaminantes" target="_blank" rel="noopener">Abrir en una pestaña</a></p></section>`;
}
const VISTAS = {terreno: vTerreno, visor: vVisor, cuencas: vCuencas, corrida: vCorrida, evaluacion: vEvaluacion, cmip6: vCmip6, contaminantes: vContaminantes};
// Eta (Mejora 1 · A): pantalla de arranque, nunca en blanco; si el servidor no responde en 20 s se dice con palabras simples
(function arrancar() {
  const t0 = Date.now(), bar = $("#arrBar"), txt = $("#arrTxt"), re = $("#arrRe"); let k = 8;
  const avance = setInterval(() => { k = Math.min(90, k + 6); if (bar) bar.style.width = k + "%"; if (Date.now() - t0 > 20000) { clearInterval(avance); if (txt) txt.textContent = "El programa no responde todavía. Puede estar terminando de arrancar o se cerró. Tus datos están guardados."; if (re) re.hidden = false; } }, 700);
  if (re) re.onclick = () => location.reload();
  cargarEstado().then(async () => {
    const p = S.estado.proyecto, ult = (S.estado.corridas || [])[0];
    if (txt && p) txt.textContent = `Recuperando ${p.nombre}` + (ult ? ` (última corrida: ${ult.estado}${ult.fin ? " " + ult.fin.slice(11, 16) : ""})` : "") + "…";
    const antes = location.hash; await continuarDondeQuede(); if (location.hash === antes) await navegar();   // si cambió el hash, navega hashchange
    clearInterval(avance); if (bar) bar.style.width = "100%"; setTimeout(() => { const a = $("#arranque"); if (a) a.remove(); }, 250);
  }).catch(() => { if (txt) txt.textContent = "No se pudo leer el estado del programa. Pulsa «Reintentar»."; if (re) re.hidden = false; });
})();

// latido: permite que la versión empaquetada se cierre sola cuando se cierra la ventana.
// Lambda: la franja roja «UCEclima se desconectó» solo aparece cuando la conexión de verdad se cortó. En Eta saltaba con 2 latidos fallidos (20 s),
// y bastaba que el servidor estuviera ocupado con una descarga o que el navegador congelara la pestaña. Ahora: (1) cada latido tiene un tiempo máximo
// de 8 s; (2) no cuentan los fallos mientras la pestaña está oculta (el navegador congela los temporizadores); (3) hacen falta 6 fallos seguidos y
// más de 60 s sin ninguna respuesta; (4) antes de avisar se confirma con una segunda sonda distinta (/api/estado).
let FALLOS_LATIDO = 0, ULTIMA_RESPUESTA = Date.now(), DESC_CERRADA = false;
const FALLOS_PARA_AVISAR = 6, SEGUNDOS_SIN_RESPUESTA = 60;
async function sonda(url) {
  const ctl = new AbortController(), t = setTimeout(() => ctl.abort(), 8000);
  try { const r = await fetch(url, {cache: "no-store", signal: ctl.signal}); return r.ok; } catch (e) { return false; } finally { clearTimeout(t); }
}
async function latido() {
  if (document.hidden) return;                                  // pestaña dormida: no es una desconexión
  if (await sonda("/api/latido")) {
    FALLOS_LATIDO = 0; ULTIMA_RESPUESTA = Date.now(); DESC_CERRADA = false; const d = $("#desconexion");
    if (d && !d.hidden) { d.hidden = true; aviso("Conexión recuperada: todo sigue guardado.", 5000); cargarEstado(); }
    return;
  }
  FALLOS_LATIDO++;
  if (FALLOS_LATIDO >= FALLOS_PARA_AVISAR && (Date.now() - ULTIMA_RESPUESTA) / 1000 > SEGUNDOS_SIN_RESPUESTA && !(await sonda("/api/estado")) && !DESC_CERRADA) { const d = $("#desconexion"); if (d) d.hidden = false; }
}
document.addEventListener("visibilitychange", () => { if (!document.hidden) { FALLOS_LATIDO = 0; ULTIMA_RESPUESTA = Date.now(); latido(); } });   // al volver a la pestaña se empieza de cero
setInterval(latido, 10000); latido();
document.addEventListener("click", e => { if (e.target.closest("#descCerrar")) { DESC_CERRADA = true; const d = $("#desconexion"); if (d) d.hidden = true; } });   // el aviso se puede cerrar: no vuelve hasta que la conexión se recupere y se corte otra vez
document.addEventListener("click", e => { if (e.target.closest("#descRe")) { $("#descTxt").textContent = "Reconectando…"; latido().then(() => { if (FALLOS_LATIDO === 0) location.reload(); else $("#descTxt").textContent = "Sigue sin responder. Abre UCEclima otra vez desde el acceso directo: tus datos y la corrida están guardados y continúas donde te quedaste."; }); } });

// tema noche / claro (preferencia solo en este navegador)
$("#btntema").addEventListener("click", () => {
  const r = document.documentElement, claro = r.hasAttribute("data-tema");
  if (claro) r.removeAttribute("data-tema"); else r.setAttribute("data-tema", "oscuro");
  try { localStorage.setItem("uceclima_tema", claro ? "claro" : "oscuro"); } catch (e) {}
});

// ▶ RUN · cada módulo se puede operar SIN IA: el botón ejecuta la acción principal del módulo abierto (con confirmación; una corrida o descarga por vez).
const RUN = {
  preparacion: ["#pLeer", "Leer el archivo o la carpeta indicada y cargarla en memoria", false], proyecto: ["#prCrear", "Crear la carpeta del proyecto con los datos indicados", false],
  gee: ["#gConectar", "Conectar con Google Earth Engine (autoriza en el navegador, prueba tu proyecto, inicializa y verifica)", false], chirps: ["#chGo", "Descargar la serie CHIRPS del sitio y generar los gráficos (puede tardar unos minutos)", true],
  idf: ["#idfFijar", "Fijar la IDF del INAMHI elegida como X del proyecto", false], terreno: ["#demReg", "Registrar el MDT inspeccionado como terreno del proyecto", false], corrida: ["#btnRun", "Ejecutar UNA corrida pequeña (puede tardar varios minutos)", true],
  entregas: ["#enGo", "Armar la carpeta de entrega: resultados, BCA FEMA y El Niño / La Niña", false], hidrologia: ["#hiExp", "Exportar gráficas y tablas del panel a una carpeta nueva", false], cmip6: ["#cmE", "Evaluar y ordenar los modelos CMIP6 (solo cálculo, sin descargas)", false],
  evaluacion: [null, "Actualizar la evaluación de la última corrida", false],
};
function actualizarRun() {
  const b = document.querySelector("#btnrun"); if (!b) return; const r = RUN[S.ruta];
  const el = r && r[0] ? document.querySelector("#principal " + r[0]) : null;
  const ok = !!r && (r[0] === null || (el && !el.disabled));
  b.disabled = !ok; b.title = r ? (ok ? r[1] : "Esta acción no está disponible todavía en este módulo (faltan entradas o hay un proceso en curso).") : "Este módulo no tiene una acción ejecutable (es informativo)";
}
document.addEventListener("click", async e => {
  const b = e.target.closest("#btnrun"); if (!b) return; const r = RUN[S.ruta]; if (!r) return;
  if (!confirm("▶ RUN · " + r[1] + "\n\n" + (r[2] ? "Es un proceso largo: se ejecuta UNO a la vez. " : "") + "¿Ejecutar ahora?")) return;
  if (r[0] === null) { navegar(); return; }
  const el = document.querySelector("#principal " + r[0]); if (el && !el.disabled) el.click();
});

// Agentes: VS Code (Copilot) y VS Code + Claude Code. Al abrir un proyecto ambos quedan configurados en su carpeta.
async function estadoAgente() {
  const b = document.getElementById("btnagente"); if (!b) return;
  const e = await api("/api/agente/vscode"); S.agente = e;
  b.textContent = (e.conectado_copilot || e.conectado_claude ? "● " : "○ ") + "Agente";
  b.classList.toggle("conectado", !!(e.conectado_copilot || e.conectado_claude));
}
document.addEventListener("click", async ev => {
  const m = document.getElementById("menuAgente");
  if (ev.target.closest("#btnagente")) {
    if (m) { m.remove(); return; }
    const e = S.agente || await api("/api/agente/vscode");
    const fila = (id, t, con, inst) => `<button data-ag="${id}" style="display:block;width:100%;text-align:left;margin:4px 0">${con ? "●" : "○"} ${t}${inst ? "" : " <span style='color:#ffb4a2'>(extensión no instalada)</span>"}</button>`;
    document.body.insertAdjacentHTML("beforeend", `<div id="menuAgente" class="tarjeta" style="position:fixed;top:58px;right:120px;z-index:50;padding:10px;min-width:300px">
      ${!e.proyecto ? '<p class="chip">Abre o crea un proyecto: el agente trabaja en su carpeta.</p>' : ""}
      ${fila("claude", "VS Code + Claude Code", e.conectado_claude, e.claude_code_instalado)}${fila("copilot", "VS Code + Copilot", e.conectado_copilot, e.copilot_instalado)}
      ${!e.vscode ? '<p class="chip">VS Code no está instalado en este equipo.</p>' : ""}</div>`);
    return;
  }
  const op = ev.target.closest("[data-ag]");
  if (op) {
    document.getElementById("menuAgente")?.remove();
    if (!S.estado || !S.estado.proyecto) { aviso("Abre o crea un proyecto: el agente trabaja en su carpeta.", 6000); return; }
    const j = await api("/api/agente/vscode", {agente: op.dataset.ag});
    aviso(j.error || (j.mensaje + (j.avisos && j.avisos.length ? " " + j.avisos.join(" ") : "")), 9000); estadoAgente(); return;
  }
  if (m && !ev.target.closest("#menuAgente")) m.remove();
});
setInterval(estadoAgente, 20000); setTimeout(estadoAgente, 1500);
