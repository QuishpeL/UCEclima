// Encuesta de campo «¿Se inunda?» generada por UCEclima (módulo Validación de campo). Base: mapa comunitario del Taller 3 de Milagro (milagro-comunidad-1.3).
// DATA = {titulo, zona, slug, endpoint, form, idioma, area (GeoJSON), capas: [{titulo, tipo, png, b}], aviso, pie}
// Dos modos: archivo autocontenido (window.DATA incrustado) o página genérica del sitio (?z=<zona>&s=<id del Apps Script>), que lee DATA de la hoja.
// Las respuestas se guardan con los valores en español (los mismos de Milagro) aunque la persona vea la encuesta en inglés.
(function () {
"use strict";
const APP = "uceclima-validacion-campo-2.0";
const $ = id => document.getElementById(id);
const store = {get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }, set(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }};

// ---------- textos (es / en)
const T = {
 es: {ayuda: "? Ayuda", cancelar: "Cancelar", terminar_zona: "Terminar zona", b_si: "≈ SE INUNDA<small>aquí llega el agua</small>", b_no: "✓ NO SE INUNDA<small>aquí nunca llega</small>",
  m_punto: "● Punto", m_zona: "⬠ Zona", m_aqui: "◎ Aquí estoy", m_deshacer: "↶ Deshacer", m_enviar: "⇪ Enviar",
  h_tit: "Cómo marcar su barrio", h_intro: "Este mapa es suyo: marque lo que usted conoce del territorio. No hay respuestas buenas ni malas.",
  h_1: 'Toque <b style="color:#C0392B">SE INUNDA</b> o <b style="color:#1E8E6E">NO SE INUNDA</b>.',
  h_2: "Toque el mapa para poner un <b>punto</b>. Para un sector más grande use <b>Zona</b>: toque las esquinas y luego «Terminar zona». Para marcar donde está parado, use <b>Aquí estoy</b>.",
  h_3: "Responda rápido: <b>cada cuánto</b> ocurre, <b>qué tan alta</b> llega el agua, <b>cuánto perdieron</b>, la <b>fecha y duración</b> de la peor inundación y las <b>medidas</b> que ayudarían.",
  h_4: "Cada marca se envía sola cuando hay internet. En <b>Enviar</b> también puede mandarla por WhatsApp o guardar el archivo.",
  h_pie: "Sus marcas se guardan en este teléfono aunque cierre la página. No pedimos nombres ni datos personales. El mapa del modelo está en ☰ Capas: mírelo al final, para comparar.",
  entendido: "Entendido", q_frec: "¿Cada cuánto se inunda?", q_alt: "¿Qué tan alta llega el agua?", q_cm: "Si la recuerda: altura en centímetros (marca en la pared)",
  q_afec: "¿Qué se ve afectado?", q_perd: "¿Cuánto han perdido en total (en dólares)?", q_ev: "¿Qué fecha recuerda del evento de inundación más fuerte?",
  q_dur: "¿Durante cuánto tiempo estuvo inundado?", q_med: "¿Qué medidas cree que ayudarían a evitar la inundación aquí?", max3: "(máximo 3)",
  med_fuente: "Lista basada en la clasificación de medidas estructurales y no estructurales de UNDRR, en medidas de gestión de inundaciones usadas en Ecuador y en soluciones basadas en la naturaleza.",
  q_nota: "Comentario (opcional)", borrar: "Borrar", guardar: "Guardar", l_tit: "Capas del mapa", l_fondo: "Fondo", l_claro: "Mapa claro (recomendado)", l_calles: "Calles", l_sat: "Satélite",
  l_sobre: "Sobre el mapa", l_zona: "Zona de estudio", l_modelo: "Mapas del modelo", l_modelo2: "(mírelos al final, para comparar)", listo: "Listo",
  s_tit: "Guardar y enviar", s_grupo: "Nombre del grupo o barrio", s_web: "☁ Enviar a la base ahora", s_wa: "Enviar por WhatsApp", s_share: "Compartir archivo", s_dl: "Descargar archivo",
  s_clear: "Borrar todo", cerrar: "Cerrar", ph_ev: "Ej.: marzo 2023, febrero 2017, El Niño 1998", ph_nota: "Ej.: se tapa la alcantarilla, el estero se desborda…", ph_grupo: "Ej.: Grupo San Miguel – mesa 2",
  elija: "— elija —", k: "Validación de campo · ", hint1: "1) Elija qué va a marcar", hint_p: "2) Toque el mapa donde ", hint_z: "2) Toque las esquinas de la zona", zona_n: "Zona: {n} esquinas · mínimo 3",
  t_si: "≈ Aquí SE INUNDA", t_no: "✓ Aquí NO SE INUNDA", t_zona: " (zona)", sub_nuevo: "Guardado. Puede completar estos datos (opcional).", sub_ed: "Puede cambiar los datos o borrar la marca.",
  primero: "Primero elija: SE INUNDA o NO SE INUNDA", esquinas3: "Ponga al menos 3 esquinas", elija_zona: "Elija SE INUNDA o NO SE INUNDA y toque las esquinas",
  sin_gps: "Este teléfono no permite ubicación", buscando: "Buscando su ubicación…", gps_err: "No se pudo obtener la ubicación. Active el GPS y dé permiso.",
  guardada: "Marca guardada", max3_t: "Elija máximo 3 medidas: las más importantes", sin_marcas: "No hay marcas", descargado: "Se descargó el archivo",
  resumen: "Tiene {n} marca(s): {s} donde SE INUNDA y {no} donde NO SE INUNDA.", pend: " {p} por enviar a la base.", al_dia: " Todas enviadas a la base.",
  vacio: "Aún no hay marcas. Vuelva al mapa y marque su barrio.", nada_nuevo: "No hay marcas nuevas por enviar.", sin_red: "Sin conexión: las marcas quedan guardadas en el teléfono y se envían solas cuando haya señal.",
  enviando: "Enviando {n} marca(s)…", ok_env: "✓ {n} marca(s) en la base. ¡Gracias!", parcial: "{ok} de {n} enviadas; se reintenta solo con mejor señal.",
  borrar_todo: "¿Borrar TODAS las marcas de este teléfono?", hay_senal: "Hay señal: enviando sus marcas pendientes…", sin_capas: "Sin mapas del modelo.",
  pie: "El archivo (.geojson) se abre en QGIS o Google Earth y se importa en UCEclima (módulo Validación de campo).",
  sin_registro: "El envío a la base no está configurado: use WhatsApp o «Compartir archivo».", grupo_wa: "Grupo: ", marcas_wa: " marca(s)", mas_wa: "(+{n} más: use «Compartir archivo»)",
  cargando: "Cargando la encuesta…", no_encuesta: "No se encontró esta encuesta. Revise el enlace o pida uno nuevo a quien se lo envió."},
 en: {ayuda: "? Help", cancelar: "Cancel", terminar_zona: "Finish area", b_si: "≈ IT FLOODS<small>water reaches here</small>", b_no: "✓ DOES NOT FLOOD<small>water never reaches here</small>",
  m_punto: "● Point", m_zona: "⬠ Area", m_aqui: "◎ I'm here", m_deshacer: "↶ Undo", m_enviar: "⇪ Send",
  h_tit: "How to map your neighbourhood", h_intro: "This map is yours: mark what you know about the area. There are no right or wrong answers.",
  h_1: 'Tap <b style="color:#C0392B">IT FLOODS</b> or <b style="color:#1E8E6E">DOES NOT FLOOD</b>.',
  h_2: "Tap the map to place a <b>point</b>. For a larger area use <b>Area</b>: tap the corners and then «Finish area». To mark where you are standing, use <b>I'm here</b>.",
  h_3: "Answer quickly: <b>how often</b> it happens, <b>how high</b> the water gets, <b>how much was lost</b>, the <b>date and duration</b> of the worst flood and the <b>measures</b> that would help.",
  h_4: "Each mark is sent automatically when there is internet. Under <b>Send</b> you can also share it by WhatsApp or save the file.",
  h_pie: "Your marks stay on this phone even if you close the page. We do not ask for names or personal data. The model map is under ☰ Layers: look at it at the end, to compare.",
  entendido: "Got it", q_frec: "How often does it flood?", q_alt: "How high does the water get?", q_cm: "If you remember: height in centimetres (mark on the wall)",
  q_afec: "What is affected?", q_perd: "How much has been lost in total (in US dollars)?", q_ev: "What date do you remember of the worst flood?",
  q_dur: "How long did the flooding last?", q_med: "Which measures would help prevent flooding here?", max3: "(up to 3)",
  med_fuente: "List based on the UNDRR classification of structural and non-structural measures, on flood management measures used in Ecuador and on nature-based solutions.",
  q_nota: "Comment (optional)", borrar: "Delete", guardar: "Save", l_tit: "Map layers", l_fondo: "Background", l_claro: "Light map (recommended)", l_calles: "Streets", l_sat: "Satellite",
  l_sobre: "On the map", l_zona: "Study area", l_modelo: "Model maps", l_modelo2: "(look at them at the end, to compare)", listo: "Done",
  s_tit: "Save and send", s_grupo: "Group or neighbourhood name", s_web: "☁ Send to the database now", s_wa: "Send by WhatsApp", s_share: "Share file", s_dl: "Download file",
  s_clear: "Delete all", cerrar: "Close", ph_ev: "E.g.: March 2023, February 2017", ph_nota: "E.g.: the drain gets blocked, the stream overflows…", ph_grupo: "E.g.: Riverside group – table 2",
  elija: "— choose —", k: "Field validation · ", hint1: "1) Choose what you will mark", hint_p: "2) Tap the map where ", hint_z: "2) Tap the corners of the area", zona_n: "Area: {n} corners · at least 3",
  t_si: "≈ IT FLOODS here", t_no: "✓ DOES NOT FLOOD here", t_zona: " (area)", sub_nuevo: "Saved. You can complete these details (optional).", sub_ed: "You can change the details or delete the mark.",
  primero: "First choose: IT FLOODS or DOES NOT FLOOD", esquinas3: "Place at least 3 corners", elija_zona: "Choose IT FLOODS or DOES NOT FLOOD and tap the corners",
  sin_gps: "This phone does not allow location", buscando: "Finding your location…", gps_err: "Could not get your location. Turn on GPS and allow access.",
  guardada: "Mark saved", max3_t: "Choose up to 3 measures: the most important ones", sin_marcas: "No marks yet", descargado: "The file was downloaded",
  resumen: "You have {n} mark(s): {s} where IT FLOODS and {no} where it DOES NOT FLOOD.", pend: " {p} waiting to be sent.", al_dia: " All sent to the database.",
  vacio: "No marks yet. Go back to the map and mark your neighbourhood.", nada_nuevo: "No new marks to send.", sin_red: "No connection: your marks stay on the phone and are sent automatically when there is signal.",
  enviando: "Sending {n} mark(s)…", ok_env: "✓ {n} mark(s) in the database. Thank you!", parcial: "{ok} of {n} sent; it will retry automatically with better signal.",
  borrar_todo: "Delete ALL the marks on this phone?", hay_senal: "Signal is back: sending your pending marks…", sin_capas: "No model maps.",
  pie: "The file (.geojson) opens in QGIS or Google Earth and can be imported into UCEclima (Field validation module).",
  sin_registro: "Sending to the database is not set up: use WhatsApp or «Share file».", grupo_wa: "Group: ", marcas_wa: " mark(s)", mas_wa: "(+{n} more: use «Share file»)",
  cargando: "Loading the survey…", no_encuesta: "This survey was not found. Check the link or ask whoever sent it for a new one."}
};
// opciones: [valor guardado (español, igual que Milagro), texto en inglés]
const OPC = {
 fFrec: [["Todos los años", "Every year"], ["Cada 2 a 5 años", "Every 2 to 5 years"], ["Solo con El Niño o lluvias extremas", "Only with El Niño or extreme rain"], ["Solo pasó una vez", "It happened only once"]],
 fAlt: [["Charco (menos de 10 cm)", "Puddle (less than 10 cm)"], ["Tobillo a rodilla (10–50 cm)", "Ankle to knee (10–50 cm)"], ["Cintura (50 cm–1 m)", "Waist (50 cm–1 m)"], ["Más de 1 metro", "More than 1 metre"]],
 fAfec: [["Casas", "Houses"], ["Calle o vía", "Street or road"], ["Escuela o colegio", "School"], ["Negocios", "Shops or businesses"], ["Cultivos", "Crops"], ["Otro", "Other"]],
 fPerd: [["Nada / no sé", "Nothing / I don't know"], ["Menos de USD 100", "Less than USD 100"], ["USD 100 a 500", "USD 100 to 500"], ["USD 500 a 2.000", "USD 500 to 2,000"], ["USD 2.000 o más", "USD 2,000 or more"]],
 fDur: [["Menos de 1 hora", "Less than 1 hour"], ["Unas horas (1 a 6 horas)", "A few hours (1 to 6 hours)"], ["Un día", "One day"], ["2 a 3 días", "2 to 3 days"], ["Una semana", "One week"], ["Más de una semana", "More than a week"], ["No recuerdo", "I don't remember"]]
};
const MEDIDAS = [
 [["Limpieza y mantenimiento", "Cleaning and maintenance"], [["Limpieza de cunetas, sumideros y alcantarillas", "Clean gutters, drains and culverts"], ["Limpieza y desazolve de ríos y esteros (sedimentos, maleza, basura)", "Clear rivers and streams (sediment, weeds, rubbish)"], ["Dragado de ríos o esteros", "Dredge rivers or streams"], ["Mingas comunitarias y no botar basura a los cauces", "Community clean-ups and no dumping in channels"]]],
 [["Obras de protección y drenaje", "Protection works and drainage"], [["Muros de gaviones o protección de las orillas", "Gabion walls or riverbank protection"], ["Diques o muros de contención", "Levees or flood walls"], ["Ampliar o construir colectores, canales y alcantarillado pluvial", "Build or enlarge storm drains and channels"], ["Compuertas o estación de bombeo", "Flood gates or pumping station"], ["Elevar calles o viviendas", "Raise streets or houses"]]],
 [["Con la naturaleza", "Working with nature"], [["Reforestar las riberas y sembrar vegetación nativa", "Reforest riverbanks with native plants"], ["Parques o lagunas que retengan el agua de lluvia", "Parks or ponds that hold rainwater"]]],
 [["Organización y prevención", "Organisation and prevention"], [["Sistema de alerta temprana y plan de evacuación", "Early warning system and evacuation plan"], ["No construir ni rellenar en zonas de riesgo (control municipal)", "No building or filling in risk areas (land-use control)"], ["Otra medida (escríbala en el comentario)", "Other measure (write it in the comment)"]]]
];

const Q = new URLSearchParams(location.search);
let L_ = (Q.get("lang") || store.get("uce_campo_idioma") || "").slice(0, 2);
const t = (k, v) => { let s = (T[L_] || T.es)[k] || T.es[k] || k; if (v) Object.keys(v).forEach(x => s = s.split("{" + x + "}").join(v[x])); return s; };
function idioma(l) {
  L_ = l === "en" ? "en" : "es"; store.set("uce_campo_idioma", L_); document.documentElement.lang = L_;
  document.querySelectorAll("[data-t]").forEach(e => e.innerHTML = t(e.dataset.t));
  document.querySelectorAll("[data-ph]").forEach(e => e.placeholder = t(e.dataset.ph));
  Object.keys(OPC).forEach(id => { const s = $(id), v = s.value; s.innerHTML = '<option value="">' + t("elija") + "</option>" + OPC[id].map(o => '<option value="' + o[0].replace(/"/g, "&quot;") + '">' + (L_ === "en" ? o[1] : o[0]) + "</option>").join(""); s.value = v; });
  document.querySelectorAll("#fMed .mg").forEach((h, i) => h.textContent = MEDIDAS[i][0][L_ === "en" ? 1 : 0]);
  document.querySelectorAll("#fMed .chk").forEach(r => r.querySelector("span").textContent = r.dataset[L_ === "en" ? "en" : "v"]);
  $("bLang").textContent = L_ === "en" ? "ES" : "EN";
  if (iniciar.ui) iniciar.ui();
}
// medidas (máximo 3)
(function () { const box = $("fMed"); MEDIDAS.forEach(g => { const h = document.createElement("div"); h.className = "mg"; box.appendChild(h);
  g[1].forEach(o => { const r = document.createElement("div"); r.className = "chk"; r.dataset.v = o[0]; r.dataset.en = o[1]; r.innerHTML = "<input type=\"checkbox\"><span></span>";
    r.addEventListener("click", e => { const cb = r.querySelector("input"); if (e.target !== cb) cb.checked = !cb.checked;
      if (cb.checked && document.querySelectorAll("#fMed input:checked").length > 3) { cb.checked = false; toast(t("max3_t")); }
      r.classList.toggle("on", cb.checked); });
    box.appendChild(r); }); }); })();
function toast(s) { const x = $("toast"); x.textContent = s; x.style.display = "block"; clearTimeout(toast.h); toast.h = setTimeout(() => x.style.display = "none", 2400); }
$("bLang").onclick = () => idioma(L_ === "en" ? "es" : "en");

function iniciar(DATA) {
const LS = "uce_campo_" + DATA.slug + "_marcas", LG = "uce_campo_" + DATA.slug + "_grupo", LH = "uce_campo_" + DATA.slug + "_ayuda", LB = "uce_campo_" + DATA.slug + "_borradas", LD = "uce_campo_dispositivo";
const disp = store.get(LD) || ("d" + Math.random().toString(36).slice(2, 9)); store.set(LD, disp);
document.title = DATA.titulo; $("hT").textContent = DATA.titulo;
const map = L.map("map", {zoomControl: false, attributionControl: true, minZoom: 3, maxZoom: 19, tap: true});
map.attributionControl.setPrefix(false);
const ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services/";
const bases = {
  claro: L.tileLayer(ESRI + "Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}", {maxNativeZoom: 16, maxZoom: 19, attribution: "Esri · © OpenStreetMap"}),
  calles: L.tileLayer(ESRI + "World_Street_Map/MapServer/tile/{z}/{y}/{x}", {maxNativeZoom: 19, maxZoom: 19, attribution: "Esri · HERE · Garmin · OpenStreetMap"}),
  sat: L.tileLayer(ESRI + "World_Imagery/MapServer/tile/{z}/{y}/{x}", {maxNativeZoom: 19, maxZoom: 19, attribution: "Esri · Maxar · Earthstar Geographics"})
};
bases.claro.addTo(map);
const area = L.geoJSON(DATA.area, {style: {color: "#0B4F8A", weight: 2.2, dashArray: "6 4", fill: false}, interactive: false}).addTo(map);
map.fitBounds(area.getBounds(), {padding: [16, 16]});
// mapas del modelo (apagados al inicio: se comparan al final, para no inducir respuestas)
map.createPane("modelo"); map.getPane("modelo").style.zIndex = 350;
const capas = (DATA.capas || []).map(c => L.imageOverlay("data:image/png;base64," + c.png, c.b, {pane: "modelo", opacity: .8, interactive: false}));
$("lCapas").innerHTML = (DATA.capas || []).map((c, i) => `<div class="capa"><input type="checkbox" id="cM${i}"><label for="cM${i}" style="margin:0;text-transform:none;font-size:15px;color:inherit"></label></div>`).join("") || "<p>" + t("sin_capas") + "</p>";
(DATA.capas || []).forEach((c, i) => { $("cM" + i).nextElementSibling.textContent = c.titulo; $("cM" + i).onchange = e => { e.target.checked ? capas[i].addTo(map) : map.removeLayer(capas[i]); $("legMod").style.display = capas.some(x => map.hasLayer(x)) ? "flex" : "none"; }; });
$("avisoMod").textContent = DATA.aviso || "";
if (!DATA.endpoint) { $("filaWeb").style.display = "none"; }

// ---------- marcas
let marks = []; let tipo = null, forma = "punto", drawing = null, editing = null;
let borradas = []; try { borradas = JSON.parse(store.get(LB) || "[]"); } catch (e) { borradas = []; }
const layer = L.layerGroup().addTo(map); const objs = {};
function save() { store.set(LS, JSON.stringify(marks)); store.set(LB, JSON.stringify(borradas)); ui(); }
function load() { try { marks = JSON.parse(store.get(LS) || "[]"); } catch (e) { marks = []; } }
function pinIcon(k) { return L.divIcon({className: "", html: '<div class="pin ' + (k === "si" ? "si" : "no") + '">' + (k === "si" ? "≈" : "✓") + "</div>", iconSize: [30, 30], iconAnchor: [15, 15]}); }
function draw(m) {
  if (objs[m.id]) layer.removeLayer(objs[m.id]);
  const col = m.tipo === "si" ? "#C0392B" : "#1E8E6E"; let o;
  if (m.forma === "punto") o = L.marker(m.coords, {icon: pinIcon(m.tipo), keyboard: false});
  else o = L.polygon(m.coords, {color: col, weight: 3, fillColor: col, fillOpacity: .32});
  o.on("click", e => { if (drawing) return; L.DomEvent.stopPropagation(e); openForm(m.id); });
  objs[m.id] = o; layer.addLayer(o);
}
// cada marca recuerda a qué dirección se envió: si la encuesta cambia de dirección, se vuelve a enviar
function pendientes() { return marks.filter(m => m.enviado !== DATA.endpoint).length + borradas.length; }
function ui() {
  $("hK").textContent = t("k") + DATA.zona;
  $("fCnt").textContent = marks.length; $("mUndo").disabled = marks.length === 0;
  $("tSi").classList.toggle("on", tipo === "si"); $("tNo").classList.toggle("on", tipo === "no");
  $("mPt").classList.toggle("on", forma === "punto"); $("mZone").classList.toggle("on", forma === "zona");
  let h = t("hint1");
  if (tipo) h = forma === "punto" ? t("hint_p") + (tipo === "si" ? t("t_si").replace(/^≈ /, "") : t("t_no").replace(/^✓ /, "")) : t("hint_z");
  if (drawing) h = t("zona_n", {n: drawing.pts.length});
  $("hint").textContent = h; $("sPie").textContent = DATA.pie && L_ !== "en" ? DATA.pie : t("pie");
}
iniciar.ui = ui;
function addMark(m) { m.id = "m" + Date.now() + Math.floor(Math.random() * 999); m.t = new Date().toISOString(); m.v = 0; marks.push(m); draw(m); save(); openForm(m.id, true); }
map.on("click", e => {
  if (!tipo) { toast(t("primero")); return; }
  if (forma === "punto") addMark({tipo, forma: "punto", coords: [e.latlng.lat, e.latlng.lng]});
  else { if (!drawing) startZone(); drawing.pts.push([e.latlng.lat, e.latlng.lng]); refreshZone(); ui(); }
});
function startZone() { drawing = {pts: [], line: L.polyline([], {color: tipo === "si" ? "#C0392B" : "#1E8E6E", weight: 3, dashArray: "6 6"}).addTo(map), vt: L.layerGroup().addTo(map)}; $("drawbar").style.display = "flex"; }
function refreshZone() { drawing.line.setLatLngs(drawing.pts.length > 2 ? drawing.pts.concat([drawing.pts[0]]) : drawing.pts); drawing.vt.clearLayers(); drawing.pts.forEach(p => L.marker(p, {icon: L.divIcon({className: "", html: '<div class="vtx"></div>', iconSize: [14, 14], iconAnchor: [7, 7]}), interactive: false}).addTo(drawing.vt)); }
function endZone(ok) {
  if (!drawing) return; const d = drawing; map.removeLayer(d.line); map.removeLayer(d.vt); drawing = null; $("drawbar").style.display = "none";
  if (ok) { if (d.pts.length < 3) toast(t("esquinas3")); else addMark({tipo, forma: "zona", coords: d.pts}); }
  ui();
}
$("dDone").onclick = () => { if (drawing && drawing.pts.length < 3) { toast(t("esquinas3")); return; } endZone(true); };
$("dCancel").onclick = () => endZone(false);
$("tSi").onclick = () => { if (drawing) endZone(false); tipo = tipo === "si" ? null : "si"; ui(); };
$("tNo").onclick = () => { if (drawing) endZone(false); tipo = tipo === "no" ? null : "no"; ui(); };
$("mPt").onclick = () => { if (drawing) endZone(false); forma = "punto"; ui(); };
$("mZone").onclick = () => { forma = "zona"; ui(); if (!tipo) toast(t("elija_zona")); };
$("mUndo").onclick = () => { if (drawing && drawing.pts.length) { drawing.pts.pop(); refreshZone(); ui(); return; } const m = marks.pop(); if (m) quitar(m); save(); };

// GPS
let meMarker = null, meCircle = null;
function locate(cb) {
  if (!navigator.geolocation) { toast(t("sin_gps")); return; }
  toast(t("buscando"));
  navigator.geolocation.getCurrentPosition(p => {
    const ll = [p.coords.latitude, p.coords.longitude];
    if (!meMarker) { meMarker = L.circleMarker(ll, {radius: 8, color: "#fff", weight: 3, fillColor: "#1F6FB2", fillOpacity: 1}).addTo(map); meCircle = L.circle(ll, {radius: p.coords.accuracy, color: "#1F6FB2", weight: 1, fillOpacity: .08}).addTo(map); }
    else { meMarker.setLatLng(ll); meCircle.setLatLng(ll).setRadius(p.coords.accuracy); }
    map.setView(ll, Math.max(map.getZoom(), 17)); if (cb) cb(ll, p.coords.accuracy);
  }, () => toast(t("gps_err")), {enableHighAccuracy: true, timeout: 15000, maximumAge: 5000});
}
$("fGps").onclick = () => locate();
$("mHere").onclick = () => { if (!tipo) { toast(t("primero")); return; } locate((ll, acc) => addMark({tipo, forma: "punto", coords: ll, gps_m: Math.round(acc)})); };

// formulario
const CAMPOS = [["fFrec", "frec"], ["fAlt", "alt"], ["fCm", "cm"], ["fAfec", "afec"], ["fPerd", "perd"], ["fEv", "ev"], ["fDur", "dur"], ["fNota", "nota"]];
function openForm(id, isNew) {
  const m = marks.find(x => x.id === id); if (!m) return; editing = id;
  $("fTitle").textContent = (m.tipo === "si" ? t("t_si") : t("t_no")) + (m.forma === "zona" ? t("t_zona") : "");
  $("fSub").textContent = isNew ? t("sub_nuevo") : t("sub_ed");
  $("fSiOnly").style.display = m.tipo === "si" ? "block" : "none";
  CAMPOS.forEach(([e, k]) => $(e).value = m[k] || "");
  document.querySelectorAll("#fMed .chk").forEach(r => { const on = (m.med || []).includes(r.dataset.v); r.querySelector("input").checked = on; r.classList.toggle("on", on); });
  $("sForm").classList.add("open"); $("sForm").querySelector(".card").scrollTop = 0;
}
$("fOk").onclick = () => { const m = marks.find(x => x.id === editing); if (m) { CAMPOS.forEach(([e, k]) => m[k] = String($(e).value || "").trim());
  m.med = [].map.call(document.querySelectorAll("#fMed .chk"), r => r.querySelector("input").checked ? r.dataset.v : null).filter(Boolean);
  m.v = (m.v || 0) + 1; m.enviado = false; save(); registrar(true); }
  $("sForm").classList.remove("open"); editing = null; toast(t("guardada")); };
function quitar(m) { if (objs[m.id]) { layer.removeLayer(objs[m.id]); delete objs[m.id]; } if (m.enviado) borradas.push(Object.assign({}, m, {v: (m.v || 0) + 1})); }
$("fDel").onclick = () => { const i = marks.findIndex(x => x.id === editing); if (i >= 0) { quitar(marks[i]); marks.splice(i, 1); save(); registrar(true); } $("sForm").classList.remove("open"); editing = null; };

// capas
function setBase(k) { Object.values(bases).forEach(b => map.removeLayer(b)); bases[k].addTo(map); bases[k].bringToBack(); $("map").classList.toggle("sat", k === "sat"); }
$("fLay").onclick = () => $("sLay").classList.add("open"); $("lOk").onclick = () => $("sLay").classList.remove("open");
$("bClaro").onchange = () => setBase("claro"); $("bCalles").onchange = () => setBase("calles"); $("bSat").onchange = () => setBase("sat");
$("cArea").onchange = e => e.target.checked ? area.addTo(map) : map.removeLayer(area);

// enviar (columnas iguales a la encuesta de Milagro, milagro-comunidad-1.3)
function geom(m) { return m.forma === "punto" ? {type: "Point", coordinates: [m.coords[1], m.coords[0]]} : {type: "Polygon", coordinates: [m.coords.concat([m.coords[0]]).map(c => [c[1], c[0]])]}; }
function centroid(m) { if (m.forma === "punto") return m.coords; let a = 0, b = 0; m.coords.forEach(c => { a += c[0]; b += c[1]; }); return [a / m.coords.length, b / m.coords.length]; }
function props(m, g, estado) {
  const c = centroid(m);
  return {id_marca: m.id, version_marca: m.v || 1, estado: estado || "ACTIVA", zona: DATA.zona, grupo: g, resultado: m.tipo === "si" ? "SE INUNDA" : "NO SE INUNDA", forma: m.forma,
          lat: +c[0].toFixed(6), lon: +c[1].toFixed(6), frecuencia: m.frec || "", altura_agua: m.alt || "", altura_cm: m.cm || "", afectado: m.afec || "", perdida_usd: m.perd || "",
          evento_mas_fuerte: m.ev || "", duracion_inundacion: m.dur || "", medidas: (m.med || []).join(" | "), comentario: m.nota || "",
          gps_precision_m: m.gps_m || "", fecha_marca: m.t, dispositivo: disp, idioma: L_, app: APP};
}
function geojson() { const g = $("grp").value.trim(); return {type: "FeatureCollection", name: "marcas_" + DATA.slug, properties: {zona: DATA.zona, grupo: g, generado: new Date().toISOString(), app: APP}, features: marks.map(m => ({type: "Feature", properties: props(m, g), geometry: geom(m)}))}; }
function summary() { const s = marks.filter(m => m.tipo === "si").length, n = marks.length - s, p = pendientes();
  return marks.length ? (t("resumen", {n: marks.length, s, no: n}) + (DATA.endpoint ? (p ? t("pend", {p}) : t("al_dia")) : " " + t("sin_registro"))) : t("vacio"); }
$("fCnt").onclick = $("mSend").onclick = () => { $("grp").value = store.get(LG) || ""; $("sSum").textContent = summary(); $("estadoWeb").textContent = ""; $("sSend").classList.add("open"); };
$("sClose").onclick = () => { store.set(LG, $("grp").value); $("sSend").classList.remove("open"); };
$("grp").oninput = () => store.set(LG, $("grp").value);
// registro en la hoja (Apps Script; una fila por versión de cada marca; si no hay señal, quedan pendientes y se reintenta solo)
let enviandoYa = false;
async function registrar(silencio) {
  if (!DATA.endpoint || enviandoYa) return; const g = (store.get(LG) || $("grp").value || "").trim();
  const pend = marks.filter(m => m.enviado !== DATA.endpoint).map(m => [m, "ACTIVA"]).concat(borradas.map(m => [m, "BORRADA"]));
  const msg = s => { if (!silencio) $("estadoWeb").textContent = s; };
  if (!pend.length) { msg(t("nada_nuevo")); return; }
  if (!navigator.onLine) { msg(t("sin_red")); return; }
  enviandoYa = true; msg(t("enviando", {n: pend.length})); let ok = 0;
  for (const [m, est] of pend) {
    const d = props(m, g, est); d.geometria_geojson = JSON.stringify(geom(m)); d.enviado_en_dispositivo = new Date().toISOString();
    try { await fetch(DATA.endpoint + (DATA.endpoint.includes("?") ? "&" : "?") + "form=" + encodeURIComponent(DATA.form), {method: "POST", mode: "no-cors", headers: {"Content-Type": "text/plain;charset=utf-8"}, body: JSON.stringify(d)});
      if (est === "BORRADA") borradas = borradas.filter(x => x !== m); else m.enviado = DATA.endpoint; ok++; }
    catch (e) { break; }
  }
  enviandoYa = false; save(); msg(ok === pend.length ? t("ok_env", {n: ok}) : t("parcial", {ok, n: pend.length})); $("sSum").textContent = summary();
}
$("sWeb").onclick = () => { if (!marks.length && !borradas.length) { toast(t("sin_marcas")); return; } store.set(LG, $("grp").value); registrar(false); };
function fileObj() { const blob = new Blob([JSON.stringify(geojson(), null, 1)], {type: "application/geo+json"}); const nm = "marcas_" + DATA.slug + "_" + (($("grp").value.trim() || "grupo").replace(/[^\w]+/g, "_")) + "_" + new Date().toISOString().slice(0, 10) + ".geojson"; return {blob, nm}; }
$("sDl").onclick = () => { if (!marks.length) { toast(t("sin_marcas")); return; } const f = fileObj(); const a = document.createElement("a"); a.href = URL.createObjectURL(f.blob); a.download = f.nm; document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1500); };
$("sShare").onclick = async () => { if (!marks.length) { toast(t("sin_marcas")); return; } const f = fileObj(); const file = new File([f.blob], f.nm, {type: "application/geo+json"});
  try { if (navigator.canShare && navigator.canShare({files: [file]})) await navigator.share({files: [file], title: DATA.titulo}); else { $("sDl").click(); toast(t("descargado")); } } catch (e) {} };
$("sWa").onclick = () => { if (!marks.length) { toast(t("sin_marcas")); return; }
  const g = $("grp").value.trim(); let s = "*" + DATA.titulo + "*\n" + (g ? t("grupo_wa") + g + "\n" : "") + marks.length + t("marcas_wa") + "\n\n";
  marks.slice(0, 20).forEach((m, i) => { const c = centroid(m); s += (i + 1) + ". " + (m.tipo === "si" ? "SE INUNDA" : "NO SE INUNDA") + (m.forma === "zona" ? t("t_zona") : "") + (m.alt ? " · " + m.alt : "") + (m.cm ? " · " + m.cm + " cm" : "") + (m.frec ? " · " + m.frec : "") + (m.nota ? " · «" + m.nota + "»" : "") + "\nhttps://maps.google.com/?q=" + c[0].toFixed(6) + "," + c[1].toFixed(6) + "\n"; });
  if (marks.length > 20) s += "\n" + t("mas_wa", {n: marks.length - 20});
  window.open("https://wa.me/?text=" + encodeURIComponent(s), "_blank"); };
$("sClear").onclick = () => { if (!marks.length) return; if (confirm(t("borrar_todo"))) { marks.forEach(quitar); marks = []; save(); registrar(true); $("sSum").textContent = summary(); } };
window.addEventListener("online", () => { if (DATA.endpoint && pendientes()) { toast(t("hay_senal")); registrar(true); } });

// ayuda
$("bHelp").onclick = () => $("sHelp").classList.add("open"); $("hOk").onclick = () => { $("sHelp").classList.remove("open"); store.set(LH, "1"); };
[$("sHelp"), $("sLay"), $("sSend"), $("sForm")].forEach(s => s.addEventListener("click", e => { if (e.target === s && s.id !== "sForm") s.classList.remove("open"); }));
load(); marks.forEach(draw); idioma(L_ || DATA.idioma || "es");
if (!store.get(LH)) $("sHelp").classList.add("open");
if (pendientes()) registrar(true);
}

// ---------- arranque: archivo autocontenido o página genérica del sitio
if (window.DATA) { iniciar(window.DATA); return; }
idioma(L_ || "es");
const z = (Q.get("z") || "").replace(/[^a-z0-9-]/g, ""), sid = (Q.get("s") || "").replace(/[^\w-]/g, "");
const ep = sid ? "https://script.google.com/macros/s/" + sid + "/exec" : (window.ENDPOINT_DEF || "");
const cg = $("cargando"); cg.style.display = "flex"; cg.textContent = t("cargando");
if (!z || !ep) { cg.textContent = t("no_encuesta"); return; }
fetch(ep + "?accion=encuesta&z=" + encodeURIComponent(z)).then(r => r.json()).then(j => {
  if (!j || !j.ok || !j.datos) throw new Error("sin datos");
  const D = j.datos; D.endpoint = ep; cg.style.display = "none"; iniciar(D);
}).catch(() => { cg.textContent = t("no_encuesta"); });
})();
