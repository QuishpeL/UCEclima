/* 6 · hidro · Cuenca  y  10 · hidro · Calibración.
   Cuenca: tres salidas (shape propio · delineación desde el MDT con ríos HydroSHEDS · malla CHIRPS de 5 km por defecto).
   Calibración: registrar QUÉ es la serie de caudal → eventos de ajuste y validación → barrido → la persona acepta. Nada se calibra solo. */
(() => {
  "use strict";
  const pt = () => { const m = /lon\s*(-?[\d.]+)\D+lat\s*(-?[\d.]+)/.exec((S.estado.proyecto || {}).ubicacion || ""); return m ? {lon: +m[1], lat: +m[2]} : {lon: "", lat: ""}; };
  const campo = (et, id, v = "", ancho = "") => `<div ${ancho ? "" : 'class="crece"'}><label for="${id}">${et}</label><input type="text" id="${id}" value="${esc(String(v))}" ${ancho ? `style="width:${ancho}"` : ""}></div>`;
  const val = id => (document.getElementById(id) || {}).value?.trim() ?? "";
  const ETQ_D = {mdt_cuenca: "MDT amplio para delinear", rios: "Ríos HydroSHEDS", delinear: "Delineación desde el MDT", chirps_cuenca: "CHIRPS sobre la cuenca"};

  // tarea en segundo plano (gestor de descargas): lanza y sigue el progreso; una a la vez
  async function tarea(fuente, parametros, box, alTerminar) {
    const j = await api("/api/descargas/iniciar", {fuente, parametros});
    if (j.error) { box.innerHTML = nota(esc(j.error), "err"); return; }
    const seguir = async () => {
      if (!document.body.contains(box)) return;
      const l = ((await api("/api/descargas")).descargas || []).find(d => d.id === j.descarga);
      if (!l) return;
      box.innerHTML = `<div class="tarjeta" style="padding:10px"><b>${esc(ETQ_D[fuente] || fuente)}</b> ${badge(l.estado === "completado" ? "ok" : l.estado === "fallido" ? "error" : "aviso", l.estado)}
        ${l.estado === "en_curso" ? `<div class="barra-prog" style="margin:6px 0"><i style="width:${Math.round((l.progreso || 0) * 100)}%"></i></div><span class="chip">${esc(l.mensaje || "")}</span> <button id="cuCancel">Cancelar</button>` : ""}
        ${l.estado === "fallido" ? nota(esc(l.mensaje || ""), "err") : ""}</div>`;
      const c = document.getElementById("cuCancel"); if (c) c.onclick = () => api("/api/descargas/cancelar", {});
      if (l.estado === "en_curso") setTimeout(seguir, 2000); else if (l.estado === "completado" && alTerminar) alTerminar(l);
    };
    seguir();
  }

  // ================================================================== 6 · CUENCA
  async function vCuenca() {
    const P = $("#principal");
    P.innerHTML = encabezado("hidro · Cuenca", "La unidad de cálculo de hidro. Tres salidas: <b>1)</b> cargar tu polígono, <b>2)</b> delinear desde el MDT (satélite) con la red de ríos HydroSHEDS quemada y contraste de área, o <b>3)</b> por defecto, la <b>malla de celdas CHIRPS de 5 km</b> cuando no hay cuenca ni estaciones. La malla es una malla de cálculo, no una cuenca: no sirve para calibrar contra un aforo.") + '<div id="cuBody"></div>';
    if (!S.estado.proyecto) { $("#cuBody").innerHTML = nota("Primero crea o abre un proyecto en el módulo <b>1 · Proyecto</b>.", "pend"); return; }
    await pintarCuenca();
  }

  async function pintarCuenca() {
    const body = $("#cuBody"); if (!body) return;
    const e = await api("/api/cuenca/estado"); const p = pt();
    const act = e.activa;
    body.innerHTML = `
    <section class="tarjeta"><h2>Cuenca activa</h2>${act ? `<p>${badge(act.origen === "malla" ? "aviso" : /SIN REVISAR/.test(act.etiqueta) ? "aviso" : "ok", act.origen)} <b>${esc(act.etiqueta)}</b> · ${fmt(act.area_km2, 1)} km²</p>
      <img class="mapa" alt="Cuenca activa" style="max-width:640px;border-radius:10px" src="/api/cuenca/mapa.png?t=${Date.now()}">` : nota("Aún no hay cuenca activa. Si no tienes datos, usa la salida 3 (malla CHIRPS).", "pend")}</section>
    <div class="rejilla">
     <section class="tarjeta"><h2>1 · Cargar tu shape</h2>
      <p class="chip">Polígono de la cuenca (shp, gpkg, geojson). Se valida, se une en un solo polígono y se guarda en WGS84 y UTM. Queda activa al cargarla.</p>
      <div class="fila"><div class="crece"><label for="cuShp">Archivo</label><input type="text" id="cuShp" placeholder="C:\\ruta\\cuenca.shp"></div><button id="cuShpEx">Examinar…</button></div>
      <div class="fila">${campo("CRS si el archivo no trae .prj (p. ej. EPSG:32717)", "cuCrs", "")}</div>
      <button class="principal" id="cuShpGo">Cargar cuenca</button><div id="cuShpMsg"></div></section>
     <section class="tarjeta"><h2>2 · Delinear desde el MDT</h2>
      <p class="chip">Para cuencas grandes baja primero un MDT amplio (90 m) y la red de ríos HydroSHEDS. La salida se puede llevar al río HydroSHEDS de mayor área cercano. El resultado queda <b>SIN REVISAR</b> hasta que lo aceptes.</p>
      <div class="fila"><div class="crece"><label for="cuSal">Salida (aforo)</label><select id="cuSal"><option value="">— elige una estación o escribe las coordenadas —</option></select></div></div>
      <div class="fila">${campo("Longitud de la salida (aforo)", "cuLon", "")}${campo("Latitud de la salida (aforo)", "cuLat", "")}</div>
      <div class="fila">${campo("Medio lado del MDT amplio (km)", "cuMed", 60, "90px")}${campo("Resolución (m)", "cuEsc", 90, "80px")}<button id="cuMdt">a) Bajar MDT amplio</button><button id="cuRios">b) Bajar ríos HydroSHEDS</button></div>
      <div class="fila">${campo("Llevar la salida al río (km, 0 = no)", "cuSnapR", 5, "80px")}${campo("Radio de ajuste a la celda (m)", "cuSnap", 300, "80px")}
        <label class="tog" style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="cuQuema" checked> Quemar ríos</label>${campo("Red de ríos propia (GEOGLOWS v2 u otra; vacío = HydroSHEDS)", "cuRiosP", "")}${campo("Profundidad de quema (m)", "cuQm", 5, "70px")}</div>
      <button class="principal" id="cuDel">c) Delinear</button><div id="cuDelMsg"></div></section>
     <section class="tarjeta"><h2>3 · Malla CHIRPS (por defecto)</h2>
      <p class="chip">Celdas de 0,05° (≈ 5,5 km) alineadas a CHIRPS que cubren la cuenca activa, o el recuadro del proyecto si no hay cuenca. Para Ecuador sin estaciones ni aforos es el punto de partida.</p>
      <button class="principal" id="cuMalla">Crear malla CHIRPS</button><div id="cuMallaMsg"></div>
      <h3 style="margin-top:14px">Lluvia sobre la cuenca</h3><p class="chip">Media areal diaria de CHIRPS sobre la cuenca activa (insumo de la calibración).</p>
      <div class="fila">${campo("Desde", "cuIni", "1981-01-01", "110px")}${campo("Hasta", "cuFin", new Date().toISOString().slice(0, 10), "110px")}<button id="cuChirps">Bajar CHIRPS sobre la cuenca</button></div><div id="cuChMsg"></div></section>
    </div>
    <section class="tarjeta"><h2>Historial (nada se borra)</h2>${(e.historial || []).length ? `<table><thead><tr><th>Carpeta</th><th>Origen</th><th>Área km²</th><th>Estado</th><th></th></tr></thead><tbody>${e.historial.map(x => `<tr>
      <td><a href="/api/cuenca/mapa.png?nombre=${encodeURIComponent(x.carpeta)}" target="_blank" rel="noopener">${esc(x.carpeta)}</a></td><td>${esc(x.origen)}</td><td>${fmt(x.area_km2, 1)}${x.dif_hydrosheds_pct != null ? `<br><span class="chip" style="color:${Math.abs(x.dif_hydrosheds_pct) > 50 ? "#ff8a7a" : Math.abs(x.dif_hydrosheds_pct) > 20 ? "#e8b84d" : "#7bd88f"}">${x.dif_hydrosheds_pct > 0 ? "+" : ""}${fmt(x.dif_hydrosheds_pct, 1)} % frente a HydroSHEDS (${fmt(x.area_hydrosheds_km2, 0)} km²)</span>` : ""}</td><td style="font-size:12px">${Math.abs(x.dif_hydrosheds_pct || 0) > 50 ? nota("⚠ <b>No la aceptes todavía:</b> el área difiere más de 50 % de HydroSHEDS. En llanuras, sube la profundidad de quema (p. ej. 15 m) o revisa la salida y vuelve a delinear.", "err") : ""}${x.toca_borde_mdt ? nota("La cuenca toca el borde del MDT amplio: está recortada. Baja un MDT más grande o centrado en la cuenca.", "pend") : ""}${esc(x.etiqueta)}${(x.avisos || []).length ? `<details><summary>avisos</summary><ul>${x.avisos.map(a => `<li>${esc(a)}</li>`).join("")}</ul></details>` : ""}</td>
      <td><button data-act="${esc(x.carpeta)}">${x.origen === "mdt" ? "Revisé y ACEPTO" : "Activar"}</button></td></tr>`).join("")}</tbody></table>` : '<p class="chip">Sin cuencas todavía.</p>'}</section>`;
    api("/api/cuenca/salidas").then(j => { const sel = $("#cuSal"); if (!sel || j.error) return; (j.salidas || []).forEach((x, k) => sel.insertAdjacentHTML("beforeend", `<option value="${k}">${esc(x.nombre)}</option>`));
      sel.onchange = () => { const x = (j.salidas || [])[+sel.value]; if (x) { $("#cuLon").value = x.lon; $("#cuLat").value = x.lat; } }; });
    const msg = (id, j, ok) => { $("#" + id).innerHTML = j.error ? nota(esc(j.error), "err") : nota(ok(j), "ok"); };
    $("#cuShpEx").onclick = async () => { const j = await api("/api/dialogo", {tipo: "vector"}); if (j.ruta) $("#cuShp").value = j.ruta; };
    $("#cuShpGo").onclick = async () => { const j = await api("/api/cuenca/shape", {ruta: val("cuShp"), crs: val("cuCrs")});
      const lejos = !j.error && (j.dist_sitio_a_cuenca_km || 0) > 5;
      msg("cuShpMsg", j, r => `Cuenca cargada: ${fmt(r.area_km2, 2)} km².` + (r.avisos.length ? "<ul>" + r.avisos.map(a => `<li>${esc(a)}</li>`).join("") + "</ul>" : "") + (lejos ? '<button id="cuMover">Mover el sitio del proyecto a la cuenca</button>' : ""));
      if (lejos) $("#cuMover").onclick = async () => { const r = await api("/api/proyecto/sitio", {centrar_cuenca: true}); aviso(r.error || "Sitio movido a la cuenca. Rehaz MDT, suelo, CN/Manning e IDF.", 8000); await cargarEstado(); };
      if (!j.error && !lejos) setTimeout(pintarCuenca, 1500); };
    $("#cuMalla").onclick = async () => { const j = await api("/api/cuenca/malla", {}); msg("cuMallaMsg", j, r => `${r.n_celdas} celdas · ${fmt(r.area_km2, 1)} km² (${esc(r.referencia)}).` + (r.activa ? " Activa." : " Guardada (no reemplaza la cuenca activa).")); if (!j.error) setTimeout(pintarCuenca, 1500); };
    const CLAVE = "uce_cuenca_" + ((S.estado.proyecto || {})._carpeta || "");                 // Eta (puntos 6 y 7): las casillas no se borran entre acciones
    const IDS = ["cuLon", "cuLat", "cuMed", "cuEsc", "cuSnap", "cuSnapR", "cuQm", "cuRiosP"];
    try { const g = JSON.parse(localStorage.getItem(CLAVE) || "{}"); IDS.forEach(i => { const e = $("#" + i); if (e && g[i] !== undefined && g[i] !== "") e.value = g[i]; }); } catch (e) {}
    IDS.forEach(i => { const e = $("#" + i); if (e) e.addEventListener("input", () => { try { const g = JSON.parse(localStorage.getItem(CLAVE) || "{}"); g[i] = e.value; localStorage.setItem(CLAVE, JSON.stringify(g)); } catch (x) {} }); });
    const coords = () => { const lo = String(val("cuLon")).replace(/[−–]/g, "-").replace(",", "."), la = String(val("cuLat")).replace(/[−–]/g, "-").replace(",", ".");
      if (!lo.trim() || !la.trim() || !isFinite(+lo) || !isFinite(+la) || (+lo === 0 && +la === 0)) { $("#cuDelMsg").innerHTML = nota("Escribe primero la <b>longitud</b> y la <b>latitud</b> de la salida (un número en cada casilla, con punto decimal; en Ecuador los dos son negativos, p. ej. -79.69556 y -2.09111). Sin ellas el MDT y la cuenca se buscarían en lon 0 / lat 0, en el mar frente a África.", "err"); return null; }
      return {lon: +lo, lat: +la}; };
    const base = () => { const c = coords(); return c ? {...c, medio_km: +val("cuMed")} : null; };
    $("#cuMdt").onclick = () => { const b = base(); if (b) tarea("mdt_cuenca", {...b, escala_m: +val("cuEsc")}, $("#cuDelMsg")); };
    $("#cuRios").onclick = () => { const b = base(); if (b) tarea("rios", {...b, area_min_km2: 10}, $("#cuDelMsg")); };
    $("#cuDel").onclick = () => coords() && tarea("delinear", {lon: +val("cuLon"), lat: +val("cuLat"), snap_m: +val("cuSnap"), snap_rio_km: +val("cuSnapR"), quemar_rios: $("#cuQuema").checked, quema_m: +val("cuQm"), rios: val("cuRiosP") || null}, $("#cuDelMsg"), () => pintarCuenca());
    $("#cuChirps").onclick = () => tarea("chirps_cuenca", {inicio: val("cuIni"), fin: val("cuFin")}, $("#cuChMsg"));
    document.querySelectorAll("[data-act]").forEach(b => b.onclick = async () => {
      let persona = "";
      if (b.textContent.includes("ACEPTO")) { persona = prompt("Tu nombre (queda registrado como quien revisó y aceptó la delineación):") || ""; if (!persona.trim()) return; }
      const j = await api("/api/cuenca/activar", {nombre: b.dataset.act, persona}); if (j.error) return aviso(j.error, 8000); aviso("Cuenca activa"); pintarCuenca();
    });
  }

  // ================================================================== 10 · CALIBRACIÓN HUMANA
  const CAL = {eventos: null, barrido: null};
  async function vCalibracion() {
    const P = $("#principal");
    P.innerHTML = encabezado("hidro · Calibración", "El programa <b>propone y mide</b>; <b>tú decides</b>. 1) registra el caudal observado y declara qué es; 2) revisa los eventos de <b>ajuste</b> y de <b>validación</b>; 3) barre rangos de CN, lag, PRF y λ; 4) elige y acepta. Las métricas de validación nunca se usan para ordenar. Sin validación favorable, el rótulo sigue siendo «simulación sin calibrar».") + '<div id="caBody"></div>';
    if (!S.estado.proyecto) { $("#caBody").innerHTML = nota("Primero crea o abre un proyecto.", "pend"); return; }
    await pintarCal();
  }

  async function pintarCal() {
    const body = $("#caBody"); if (!body) return;
    const e = await api("/api/calibracion/estado");
    const tipos = Object.entries(e.tipos || {});
    let ULT = {};                                                                                                   // últimos rangos usados (no vuelven a los de fábrica)
    try { ULT = JSON.parse(localStorage.getItem("uceclima_rangos_" + (S.estado.proyecto || {})._carpeta) || "{}"); } catch (x) {}
    if (!ULT.CN && (e.barridos || []).length) { const b = await api("/api/calibracion/barrido?id=" + encodeURIComponent(e.barridos[0]) + "&n=1"); ULT = (b.config || {}).rangos || {}; }
    body.innerHTML = `
    <section class="tarjeta"><h2>Estado</h2><p><b>${esc(e.etiqueta)}</b></p>
      <table><tbody><tr><th>Caudal observado</th><td>${badge(e.observaciones.ok ? "ok" : "aviso", e.observaciones.ok ? "confirmado" : "falta")} ${esc(e.observaciones.mensaje)} ${e.observaciones.periodo ? "· " + esc(e.observaciones.periodo.join(" a ")) : ""}</td></tr>
      <tr><th>Lluvia (forzamiento)</th><td>${badge(e.lluvia.ok ? "ok" : "aviso", e.lluvia.ok ? "lista" : "falta")} ${esc(e.lluvia.mensaje)}
        <div class="fila" style="margin-top:6px"><button id="caUsaCh">Usar CHIRPS sobre la cuenca</button>${e.lluvia.estacion_registrada ? `<button id="caUsaEs">Usar ${e.lluvia.estacion_registrada.tipo_registro === "areal" ? "lluvia areal" : "estación"} ${esc(e.lluvia.estacion_registrada.estacion)}</button>` : ""}</div></td></tr></tbody></table></section>
    <section class="tarjeta"><details><summary><b>Lluvia areal de la cuenca (Thiessen dinámico o IDW)</b> — con las estaciones del proyecto que tienen coordenadas</summary>
      <div class="fila"><div><label for="laMet">Método</label><select id="laMet"><option value="thiessen">Thiessen dinámico</option><option value="idw">IDW (1/d²)</option></select></div>${campo("Radio alrededor de la cuenca (km)", "laRad", 10, "80px")}<button id="laVer">Ver estaciones</button><button class="principal" id="laReg">Calcular y usar</button></div>
      <div id="laMsg"></div></details></section>
    <section class="tarjeta"><details><summary><b>Lluvia de estación (opcional)</b> — si CHIRPS subestima la lluvia (balance imposible), registra la lluvia diaria de una estación</summary>
      <div class="fila"><div class="crece"><label for="clRuta">Archivo (Excel o CSV)</label><input type="text" id="clRuta"></div><button id="clEx">Examinar…</button></div>
      <div class="fila">${campo("Columna de fecha", "clCF", "fecha")}${campo("Columna de lluvia (mm/día)", "clCM", "precipitacion_mm")}${campo("Columna de estación (si el archivo trae varias)", "clCE", "")}</div>
      <div class="fila">${campo("Código de la estación", "clEst", "")}${campo("Fuente (obligatoria)", "clFue", "")}${campo("Tu nombre", "clPer", "")}</div>
      <p class="chip">Es lluvia PUNTUAL: usarla como media de la cuenca es un supuesto que declaras tú.</p>
      <button id="clReg">Registrar y usar esta lluvia</button><div id="clMsg"></div></details></section>
    <section class="tarjeta"><h2>1 · Registrar el caudal observado</h2>
      <div class="fila"><div class="crece"><label for="caRuta">Archivo (Excel o CSV)</label><input type="text" id="caRuta" placeholder="C:\\ruta\\caudales.csv"></div><button id="caEx">Examinar…</button><button id="caVer">Ver columnas</button></div>
      <div id="caPrev"></div>
      <div class="fila">${campo("Columna de fecha", "caCF", "fecha")}${campo("Columna de caudal (m³/s)", "caCQ", "caudal_m3s")}${campo("Marcar sospechoso por encima de (m³/s, opcional)", "caUmb", "")}</div>
      <div class="fila"><div class="crece"><label for="caTipo">¿Qué es esta serie?</label><select id="caTipo">${tipos.map(([k, t]) => `<option value="${k}" ${k === "desconocido" ? "selected" : ""}>${esc(t)}</option>`).join("")}</select></div>${campo("Fuente (institución, código)", "caFue", "")}${campo("Estación o punto", "caEst", "")}</div>
      <div class="fila">${campo("Tu nombre", "caPer", "")}${campo("Nota", "caNota", "")}</div>
      <label class="tog" style="display:flex;gap:8px;align-items:center;margin:6px 0"><input type="checkbox" id="caConf"> Confirmo la identidad de la serie (sé qué mide y dónde). Sin esto queda como candidata y no entra a ninguna métrica.</label>
      <button class="principal" id="caReg">Registrar serie</button><div id="caRegMsg"></div></section>
    <section class="tarjeta"><h2>2 · Eventos de ajuste y validación</h2>
      <div class="fila">${campo("Percentil del pico", "caPct", 90, "70px")}${campo("Días antes", "caDA", 10, "60px")}${campo("Días después", "caDD", 20, "60px")}${campo("Separación (días)", "caSep", 30, "60px")}${campo("1 de cada N a validación", "caCV", 3, "60px")}<button id="caEv">Proponer eventos</button></div>
      <div id="caEvT"></div></section>
    <section class="tarjeta"><h2>3 · Barrido de parámetros</h2><p class="chip">Rangos lineales «mín, máx, n». Los valores los decides tú; aquí no hay valores calibrados por defecto.</p>
      <div class="fila">${campo("CN (mín, máx, n)", "caCN", (ULT.CN || [50, 90, 9]).join(", "))}${campo("Lag h (mín, máx, n)", "caLag", (ULT.lag_h || [6, 120, 12]).join(", "))}${campo("PRF (lista)", "caPRF", (ULT.PRF || [484, 284]).join(", "))}${campo("λ (lista)", "caLam", (ULT.lambda || [0.2, 0.05]).join(", "))}${campo("k recesión, días (vacío = Q base constante; «auto» = estimado)", "caK", (ULT.k_rec_d || []).filter(x => x != null).join(", "))}<button id="caKest">Estimar k</button>
      <div><label for="caHum">Humedad antecedente (opción declarada)</label><select id="caHum"><option value="ninguna">ninguna (CN constante, como Gamma)</option><option value="amc5">AMC I/II/III · lluvia de 5 días</option><option value="api">índice de lluvia antecedente continuo</option><option value="todas">comparar las tres</option></select></div></div><div id="caKmsg"></div>
      <button class="principal" id="caBar">Barrer</button>${(e.barridos || []).length ? ` <select id="caPrevB">${e.barridos.map(b => `<option>${esc(b)}</option>`).join("")}</select> <button id="caAbrB">Abrir barrido anterior</button>` : ""}<div id="caBarT"></div></section>
    ${e.aceptada ? `<section class="tarjeta"><h2>Última aceptación</h2><p>${esc(e.aceptada.etiqueta)}</p><p class="chip">${esc(e.aceptada.persona)} · ${esc(e.aceptada.fecha)} · ${esc(e.aceptada.barrido)} #${esc(e.aceptada.combinacion.id)}</p></section>` : ""}`;
    $("#caUsaCh").onclick = async () => { await api("/api/calibracion/usar_lluvia", {fuente: "chirps"}); pintarCal(); };
    const ue = $("#caUsaEs"); if (ue) ue.onclick = async () => { const j = await api("/api/calibracion/usar_lluvia", {fuente: "estacion"}); if (j.error) return aviso(j.error, 6000); pintarCal(); };
    $("#laVer").onclick = async () => { const j = await api("/api/calibracion/estaciones_areal?radio_km=" + encodeURIComponent(val("laRad"))); $("#laMsg").innerHTML = j.error ? nota(esc(j.error), "err") :
      `<p class="chip">${j.estaciones.length} estaciones dentro de la cuenca o a menos de ${esc(val("laRad"))} km${j.fuera ? " · " + j.fuera + " más lejos" : ""}.</p><table><thead><tr><th>Estación</th><th>Fuente</th><th>Dentro</th><th class="num">Distancia km</th><th class="num">Días</th></tr></thead><tbody>${j.estaciones.map(x => `<tr><td>${esc(x.nombre)}</td><td>${esc(x.fuente)}</td><td>${x.dentro ? "sí" : "no"}</td><td class="num">${x.dist_km}</td><td class="num">${x.dias}</td></tr>`).join("")}</tbody></table>`; };
    $("#laReg").onclick = async () => { $("#laMsg").innerHTML = '<p class="chip">Calculando…</p>'; const j = await api("/api/calibracion/lluvia_areal", {metodo: $("#laMet").value, radio_km: val("laRad"), persona: val("caPer")});
      $("#laMsg").innerHTML = j.error ? nota(esc(j.error), "err") : nota(`${esc(j.estacion)} · ${j.dias} días · ${j.conjuntos_distintos} conjuntos de estaciones · media ${j.media_anual_mm} mm/año. ${esc(j.aviso)}`, "ok") +
        `<table><thead><tr><th>Estación</th><th class="num">Peso (con todas)</th><th>Dentro</th><th class="num">Días con dato</th></tr></thead><tbody>${j.pesos.map(w => `<tr><td>${esc(w.estacion)}</td><td class="num">${fmt(w.peso_con_todas, 3)}</td><td>${w.dentro_de_la_cuenca ? "sí" : "no"}</td><td class="num">${w.dias_con_dato}</td></tr>`).join("")}</tbody></table>`;
      if (!j.error) setTimeout(pintarCal, 4000); };
    $("#caKest").onclick = async () => { const j = await api("/api/calibracion/recesion"); $("#caKmsg").innerHTML = j.error ? nota(esc(j.error), "err") : j.k_dias ? nota(`k estimado ${j.k_dias} días (p25–p75 ${j.p25}–${j.p75}; ${j.n} tramos). ${esc(j.nota)}`, "ok") : nota(esc(j.nota), "pend");
      if (j.k_dias && !val("caK")) $("#caK").value = [Math.round(j.p25), j.k_dias, Math.round(j.p75)].join(", "); };
    $("#clEx").onclick = async () => { const j = await api("/api/dialogo", {tipo: "tabla"}); if (j.ruta) $("#clRuta").value = j.ruta; };
    $("#clReg").onclick = async () => { const j = await api("/api/calibracion/registrar_lluvia", {ruta: val("clRuta"), col_fecha: val("clCF"), col_mm: val("clCM"), col_estacion: val("clCE"), estacion: val("clEst"), fuente: val("clFue"), persona: val("clPer")});
      $("#clMsg").innerHTML = j.error ? nota(esc(j.error), "err") : nota(`Registrada ${esc(j.estacion)}: ${j.n_dias} días (${j.periodo.join(" a ")}). ${esc(j.aviso)}`, "ok"); if (!j.error) setTimeout(pintarCal, 2000); };
    $("#caEx").onclick = async () => { const j = await api("/api/dialogo", {tipo: "tabla"}); if (j.ruta) $("#caRuta").value = j.ruta; };
    $("#caVer").onclick = async () => { const j = await api("/api/calibracion/vista_previa", {ruta: val("caRuta")}); $("#caPrev").innerHTML = j.error ? nota(esc(j.error), "err") :
      (() => { const f = j.columnas.find(c => /fecha|date|time|dia/i.test(c)), q = j.columnas.find(c => /caudal|q_|^q$|flow|discharge|m3/i.test(c)); if (f) $("#caCF").value = f; if (q) $("#caCQ").value = q; return ""; })() +
      `<p class="chip">${j.n} filas · columnas: ${j.columnas.map(c => `<code>${esc(c)}</code>`).join(" ")}</p><table><thead><tr>${j.columnas.map(c => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${j.filas.map(f => `<tr>${f.map(v => `<td>${esc(v)}</td>`).join("")}</tr>`).join("")}</tbody></table>`; };
    $("#caReg").onclick = async () => {
      const j = await api("/api/calibracion/registrar", {ruta: val("caRuta"), col_fecha: val("caCF"), col_caudal: val("caCQ"), tipo: $("#caTipo").value, fuente: val("caFue"), estacion: val("caEst"),
        confirmado: $("#caConf").checked, persona: val("caPer"), nota: val("caNota"), umbral_sospechoso: val("caUmb")});
      $("#caRegMsg").innerHTML = j.error ? nota(esc(j.error), "err") : nota(`Registrada: ${j.n_validos} valores (${j.periodo.join(" a ")}), identidad confirmada: <b>${esc(j.identidad_confirmada)}</b>, sospechosos: ${j.n_sospechosos}.` + (j.avisos.length ? "<ul>" + j.avisos.map(a => `<li>${esc(a)}</li>`).join("") + "</ul>" : ""), j.identidad_confirmada === "si" ? "ok" : "pend");
      if (!j.error) setTimeout(pintarCal, 2500);
    };
    $("#caEv").onclick = async () => {
      const j = await api("/api/calibracion/eventos", {percentil: val("caPct"), dias_antes: val("caDA"), dias_despues: val("caDD"), separacion_dias: val("caSep"), cada_validacion: val("caCV")});
      if (j.error) { $("#caEvT").innerHTML = nota(esc(j.error), "err"); return; }
      const previos = Object.fromEntries((CAL.eventos || []).map(e => [e.pico, e.rol]));
      j.eventos.forEach(e => { if (previos[e.pico] && e.rol !== "excluido") e.rol = previos[e.pico]; });                 // conserva los roles cambiados a mano
      CAL.eventos = j.eventos; tablaEventos(j);
    };
    $("#caBar").onclick = async () => {
      const nums = id => val(id).split(/[,;\s]+/).filter(Boolean).map(Number);
      $("#caBarT").innerHTML = '<p class="chip">Evaluando combinaciones…</p>';
      const rangos = {CN: nums("caCN"), lag_h: nums("caLag"), PRF: nums("caPRF"), lambda: nums("caLam"), k_rec_d: nums("caK")};
      try { localStorage.setItem("uceclima_rangos_" + (S.estado.proyecto || {})._carpeta, JSON.stringify(rangos)); } catch (x) {}
      const kAuto = /auto/i.test(val("caK")), hum = $("#caHum").value;
      const j = await api("/api/calibracion/barrido", {cn: rangos.CN, lag_h: rangos.lag_h, prf: rangos.PRF, lam: rangos.lambda, eventos: CAL.eventos, persona: val("caPer"),
        k_rec: kAuto ? "auto" : (rangos.k_rec_d.length ? [null, ...rangos.k_rec_d] : [null]), humedad: hum === "todas" ? ["ninguna", "amc5", "api"] : [hum]});
      if (j.error) { $("#caBarT").innerHTML = nota(esc(j.error), "err"); return; }
      CAL.barrido = j.barrido; tablaBarrido(j);
    };
    const ab = $("#caAbrB"); if (ab) ab.onclick = async () => { const j = await api("/api/calibracion/barrido?id=" + encodeURIComponent($("#caPrevB").value)); if (j.error) return aviso(j.error, 6000); CAL.barrido = j.barrido; tablaBarrido(j); };
  }

  function tablaEventos(j) {
    $("#caEvT").innerHTML = `<p class="chip">${j.eventos.length} eventos · umbral ${fmt(j.umbral_m3s, 1)} m³/s. ${esc(j.nota)} Cambia el rol con el selector.</p>
      <table><thead><tr><th>Evento</th><th>Inicio</th><th>Pico</th><th>Fin</th><th>Q pico</th><th>Q base</th><th>P total mm</th><th>Días con lluvia</th><th>Cobertura lluvia</th><th>Rol</th></tr></thead><tbody>${j.eventos.map((e, k) => `<tr>
      <td>${esc(e.evento)}</td><td>${esc(e.inicio)}</td><td>${esc(e.pico)}</td><td>${esc(e.fin)}</td><td>${fmt(e.Q_pico_m3s, 1)}</td><td>${fmt(e.Q_base_m3s, 1)}</td><td>${fmt(e.P_total_mm, 1)}</td><td>${e.dias_con_lluvia_pct ?? "—"} %</td><td style="${e.motivo ? "color:#ffb4a2" : ""}">${e.cobertura_lluvia_pct ?? "—"} %${e.motivo ? " · " + esc(e.motivo) : ""}</td>
      <td><select data-rol="${k}"><option value="ajuste" ${e.rol === "ajuste" ? "selected" : ""}>ajuste</option><option value="validacion" ${e.rol === "validacion" ? "selected" : ""}>validación</option><option value="excluido" ${e.rol === "excluido" ? "selected" : ""}>excluir</option></select></td></tr>`).join("")}</tbody></table>`;
    document.querySelectorAll("[data-rol]").forEach(s => s.onchange = () => { CAL.eventos[+s.dataset.rol].rol = s.value; });
  }

  function tablaBarrido(j) {
    const f2 = v => v == null ? "—" : fmt(v, 2);
    const av = (j.avisos || (j.config || {}).avisos || []);
    $("#caBarT").innerHTML = (av.length ? nota(av.map(esc).join("<br>"), "err") : "") + `<p class="chip">Barrido <code>${esc(j.barrido)}</code>: ${j.config.n_combinaciones} combinaciones, ${j.config.n_eventos_usados} eventos. ${esc(j.config.nota)}</p>
      <table><thead><tr><th>#</th><th>CN</th><th>Lag h</th><th>PRF</th><th>λ</th><th>k d</th><th>humedad</th><th>NSE ajuste</th><th>KGE ajuste</th><th>PBIAS % ajuste</th><th style="color:#b5179e">NSE valid.</th><th style="color:#b5179e">KGE valid.</th><th>err. pico % valid.</th><th></th></tr></thead><tbody>${j.mejores.map(r => `<tr>
      <td>${r.id}</td><td>${f2(r.CN)}</td><td>${f2(r.lag_h)}</td><td>${r.PRF}</td><td>${r.lambda}</td><td>${r.k_rec_d == null ? "—" : f2(r.k_rec_d)}</td><td>${esc(r.humedad || "ninguna")}</td><td>${f2(r.NSE_ajuste)}</td><td><b>${f2(r.KGE_ajuste)}</b></td><td>${f2(r.PBIAS_pct_ajuste)}</td><td>${f2(r.NSE_validacion)}</td><td>${f2(r.KGE_validacion)}</td><td>${f2(r.error_pico_medio_abs_pct_validacion)}</td>
      <td><button data-ver="${r.id}">Ver</button></td></tr>`).join("")}</tbody></table>
      <div class="fila"><div><label for="caPet">ETP constante para GR4J (mm/día o «calibrada»)</label><input type="text" id="caPet" style="width:110px" placeholder="declárala"></div><button id="caBench">Benchmark: sin habilidad y GR4J</button></div><div id="caBenchT"></div><div id="caFig"></div>`;
    $("#caBench").onclick = async () => { $("#caBenchT").innerHTML = '<p class="chip">Calculando referencias…</p>';
      const b = await api("/api/calibracion/benchmark", {pet_mm_d: val("caPet"), barrido: CAL.barrido, id: 0, persona: val("caPer")});
      if (b.error) { $("#caBenchT").innerHTML = nota(esc(b.error), "err"); return; }
      $("#caBenchT").innerHTML = nota("Referencia de comparación, no calibrada por la persona. Mismas ventanas de evento, misma lluvia y misma métrica.", "pend") + `<table><thead><tr><th>Modelo</th><th>KGE aj.</th><th>KGE val.</th><th>NSE aj.</th><th>NSE val.</th><th>PBIAS aj.</th><th>PBIAS val.</th></tr></thead><tbody>${b.tabla.map(t => `<tr><td>${esc(t.modelo)}</td><td>${f2(t.KGE_ajuste)}</td><td>${f2(t.KGE_validacion)}</td><td>${f2(t.NSE_ajuste)}</td><td>${f2(t.NSE_validacion)}</td><td>${f2(t.PBIAS_pct_ajuste)}</td><td>${f2(t.PBIAS_pct_validacion)}</td></tr>`).join("")}</tbody></table>`; };
    document.querySelectorAll("[data-ver]").forEach(b => b.onclick = async () => {
      const id = b.dataset.ver;
      $("#caFig").innerHTML = '<p class="chip">Preparando la comparación…</p>';
      const c = await api("/api/calibracion/comparacion?barrido=" + encodeURIComponent(CAL.barrido) + "&id=" + id);
      if (c.error) { $("#caFig").innerHTML = nota(esc(c.error), "err"); return; }
      const g = Object.fromEntries(c.globales.map(x => [x.metrica, x])), fx = v => v == null ? "—" : fmt(v, 3);
      const img = f => `<img class="mapa" alt="${esc(f)}" style="max-width:100%;border-radius:10px;margin:6px 0;background:#fff" src="/api/calibracion/comparacion.png?barrido=${encodeURIComponent(CAL.barrido)}&id=${id}&f=${encodeURIComponent(f)}">`;
      $("#caFig").innerHTML = (c.borde.length ? nota("Óptimo en el borde del rango: " + c.borde.map(esc).join("; ") + ". Amplía el rango y vuelve a barrer.", "err") : "")
        + (c.anios_incoherentes.length ? nota("Balance anual incoherente en: " + c.anios_incoherentes.join(", ") + " (escorrentía ≥ lluvia o coeficiente < 0,05). Revisa la lluvia o el caudal de esos años.", "pend") : "")
        + `<table><thead><tr><th>Global</th><th class="num">Ajuste</th><th class="num">Validación</th></tr></thead><tbody>${["KGE", "NSE", "PBIAS_pct", "error_pico_medio_abs_pct", "error_volumen_directo_medio_pct", "n_eventos"].map(k => `<tr><td>${esc(k)}</td><td class="num">${fx(g[k].ajuste)}</td><td class="num">${fx(g[k].validacion)}</td></tr>`).join("")}</tbody></table>`
        + c.figuras.map(img).join("")
        + `<details><summary>Métricas por evento (${c.por_evento.length})</summary><table><thead><tr><th>Evento</th><th>Rol</th><th class="num">KGE</th><th class="num">NSE</th><th class="num">PBIAS %</th><th class="num">Error pico %</th><th class="num">Error volumen %</th></tr></thead><tbody>${c.por_evento.map(e => `<tr><td>${esc(e.evento)}</td><td>${esc(e.rol)}</td><td class="num">${fx(e.KGE)}</td><td class="num">${fx(e.NSE)}</td><td class="num">${fx(e.PBIAS_pct)}</td><td class="num">${fx(e.error_pico_pct)}</td><td class="num">${fx(e.error_volumen_pct)}</td></tr>`).join("")}</tbody></table></details>`
        + `<p class="chip">${esc(c.nota)} Archivos (PNG + CSV) en <code>${esc(c.carpeta)}</code>.</p>`;
      $("#caFig").insertAdjacentHTML("beforeend", `
        <div class="fila">${campo("Tu nombre", "caAcP", val("caPer"))}${campo("Nota de la decisión", "caAcN", "")}<button class="principal" id="caAcep">Acepto la combinación #${id}</button></div><div id="caAcMsg"></div>`);
      $("#caAcep").onclick = async () => { const r = await api("/api/calibracion/aceptar", {barrido: CAL.barrido, id: +id, persona: val("caAcP"), nota: val("caAcN")});
        $("#caAcMsg").innerHTML = r.error ? nota(esc(r.error), "err") : nota(esc(r.etiqueta), r.favorable ? "ok" : "pend"); };
    });
  }

  VISTAS.cuenca = vCuenca; VISTAS.calibracion = vCalibracion;
})();
