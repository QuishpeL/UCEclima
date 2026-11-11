/* Módulos 1 · Proyecto, 2 · Datos/GEE y 3 · CHIRPS.
   1) Crear la carpeta del proyecto (con las series del premódulo) o abrir una existente.
   2) Tu proyecto de Google Cloud → autorizar con tu cuenta en el navegador → inicializar y VERIFICAR la conexión; descargas del proyecto.
   3) CHIRPS: descargar la serie del sitio, graficarla y guardar todo en la carpeta del proyecto. */
(() => {
  "use strict";
  const hoy = () => new Date().toISOString().slice(0, 10);
  const punto = () => { const m = /lon\s*(-?[\d.]+)\D+lat\s*(-?[\d.]+)/.exec((S.estado.proyecto || {}).ubicacion || ""); return m ? {lon: +m[1], lat: +m[2]} : null; };
  const PASO_TXT = {mdt: "MDT (Copernicus 30 m)", suelo: "Uso de suelo y suelo (WorldCover + OpenLandMap)", otras: "Otras descargas opcionales (Earth Engine)", cn_manning: "CN y Manning (calculados con las capas)", chirps: "CHIRPS (lluvia por satélite)", geoglows: "GEOGLOWS (caudal reanalizado)", celec: "CELEC Mazar (cota y caudal)"};
  const campoL = (et, id, v = "", ph = "") => `<div class="crece"><label for="${id}">${et}</label><input type="text" id="${id}" value="${esc(v)}" placeholder="${esc(ph)}"></div>`;

  // ------------------------------------------------------------------ descargas en curso (se reutiliza en GEE y CHIRPS)
  async function seguirDescargas(box, filtro, alTerminar) {
    if (!box || !document.body.contains(box)) return;
    const r = await api("/api/descargas"); const l = (r.descargas || []).filter(d => !filtro || d.fuente === filtro || (d.fuente === "sitio" && !filtro));
    box.innerHTML = l.length ? "<h3>Historial de descargas</h3>" + l.slice(0, 6).map(d => `<div class="tarjeta" style="margin:8px 0;padding:12px"><b>${esc(PASO_TXT[d.fuente] || d.fuente)}</b> <span class="chip">${esc(d.id)}</span> ${badge(d.estado === "completado" ? "ok" : d.estado === "fallido" ? "error" : "aviso", d.estado)}
       ${d.estado === "en_curso" ? `<div class="barra-prog" style="margin:6px 0"><i style="width:${Math.round((d.progreso || 0) * 100)}%"></i></div><span class="chip">${esc(d.mensaje || "")}</span> <button data-cancel-d="1" style="margin-left:8px">Cancelar descarga</button>` : ""}
       ${d.resumen && d.resumen.pasos ? `<table><tbody>${Object.entries(d.resumen.pasos).map(([k, p]) => `<tr><th>${esc(PASO_TXT[k] || k)}</th><td>${p.estado === "ok" ? badge("ok", "listo") : badge("error", "falló")}</td><td>${esc(p.estado === "ok" ? (p.n_dias ? fmt(p.n_dias, 0) + " días" : "") : p.error || "")}</td></tr>`).join("")}</tbody></table>` : ""}
       ${d.fuente === "otras" && d.resumen && d.resumen.items ? `<table><tbody>${Object.entries(d.resumen.items).map(([k, it]) => `<tr><th>${esc(it.nombre || k)}</th><td>${it.estado === "ok" ? badge("ok", "listo") : badge("error", "falló")}</td><td style="font-size:12px">${esc(it.estado === "ok" ? (it.archivos || []).filter(a => !/\.(shp|dbf|shx|prj|cpg)$/.test(a)).join(", ") : it.error || "")}${it.estado === "ok" && (it.archivos || []).some(a => /_(vista|serie)\.png$/.test(a)) ? ` · <a href="/api/proyecto/archivo?ruta=${encodeURIComponent("datos_descargados/" + d.id + "/" + k + "/" + (it.archivos.find(a => /_vista\.png$/.test(a)) || it.archivos.find(a => /_serie\.png$/.test(a))))}" target="_blank" rel="noopener">ver vista previa</a>` : ""}</td></tr>`).join("")}</tbody></table>` : ""}
       ${d.fuente === "suelo" && d.estado === "completado" ? `<img class="mapa" style="max-width:420px;border-radius:10px;margin-top:8px" alt="Uso de suelo" src="/api/proyecto/archivo?ruta=${encodeURIComponent("datos_descargados/" + d.id + "/uso_suelo_vista.png")}">` : ""}
       ${d.estado === "fallido" ? nota(esc(d.mensaje || ""), "err") : ""}${d.estado === "interrumpida" ? `<div class="fila">${nota("Se interrumpió (programa o sesión cerrados). Lo ya bajado se conserva.", "pend")}<button class="principal" data-reanudar="${esc(d.id)}">Reanudar</button></div>` : ""}</div>`).join("") : "";
    box.querySelectorAll("[data-cancel-d]").forEach(b => b.onclick = async () => { b.disabled = true; await api("/api/descargas/cancelar", {}); });
    box.querySelectorAll("[data-reanudar]").forEach(b => b.onclick = async () => { b.disabled = true; const j = await api("/api/descargas/reanudar", {id: b.dataset.reanudar}); if (j.error) aviso(j.error, 6000); seguirDescargas(box, filtro, alTerminar); });
    const activa = l.some(d => d.estado === "en_curso");
    clearTimeout(seguirDescargas.t);
    if (activa) { seguirDescargas.t = setTimeout(() => seguirDescargas(box, filtro, alTerminar), 2500); seguirDescargas.vista = true; }
    else if (seguirDescargas.vista) { seguirDescargas.vista = false; await cargarEstado(); if (alTerminar) alTerminar(l[0]); }
  }

  // ================================================================== 1 · PROYECTO
  async function vProyecto() {
    const p = S.estado.proyecto, demos = await api("/api/proyectos_demo"), mem = await api("/api/prep/memoria");
    $("#principal").innerHTML = encabezado("1 · Proyecto", "Aquí se <b>crea la carpeta del proyecto</b> (con las series que cargaste en el premódulo) o se <b>abre uno existente</b>. Todo lo que descargues y calcules después queda dentro de esa carpeta. Nada se sobrescribe.") + `
    <div class="rejilla">
     <section class="tarjeta"><h2>Crear un proyecto nuevo</h2>
      <div class="fila">${campoL("Nombre del proyecto", "prNom", "", "mi_proyecto")}</div>
      <div class="fila">${campoL("Longitud (grados decimales)", "prLon", "", "escribe, p. ej. -78.645")}${campoL("Latitud (grados decimales)", "prLat", "", "escribe, p. ej. -2.585")}</div>
      <p class="chip"><b>Un solo número en cada casilla</b>, con punto decimal y sin letras (N, S, E, O). En Ecuador los dos son negativos: longitud <code>-79.69556</code>, latitud <code>-2.09111</code>.</p>
      <p class="chip">El sitio es el punto de interés (presa, estación o centro del estudio), en Ecuador o en cualquier lugar con CHIRPS (latitud −50…50); de él se derivan el CRS (UTM) y las descargas de Earth Engine.</p>
      <h3>…o desde el shape de la zona de estudio (Zeta)</h3>
      <div class="fila"><div class="crece"><label for="prShp">Shape / GeoPackage / GeoJSON de la zona de estudio (opcional)</label><input type="text" id="prShp" placeholder="C:\\ruta\\zona_estudio.shp"></div><button id="prShpExa">Examinar…</button></div>
      <div class="fila">${campoL("CRS del shape solo si no trae .prj", "prShpCrs", "", "p. ej. EPSG:32630")}</div>
      <p class="chip">Con shape no hace falta escribir longitud y latitud: se toma un punto interior del polígono. El shape se copia a <code>zona_estudio\\</code>, queda como cuenca activa y define el área 2D.</p>
      <div class="fila"><div class="crece"><label for="prBase">Crear dentro de la carpeta</label><input type="text" id="prBase" value="${esc(S.estado.carpeta_proyectos || "")}"></div><button id="prExa">Examinar…</button></div>
      <label class="tog" style="display:flex;gap:8px;align-items:center;margin:6px 0"><input type="checkbox" id="prMem" ${mem.n ? "checked" : "disabled"}> Guardar en el proyecto las series del premódulo <b>a menos de 100 km del sitio</b> (tienes ${mem.n} en memoria; las lejanas no se copian)</label>
      ${mem.n ? "" : '<p class="chip">Aún no cargaste datos en el módulo 0; puedes hacerlo después.</p>'}
      <div class="fila"><button class="principal" id="prCrear">Crear carpeta del proyecto</button></div><div id="prMsg"></div>
     </section>
     <section class="tarjeta"><h2>Abrir un proyecto existente</h2>
      <label for="rutaProy">Carpeta del proyecto (o su archivo proyecto_uceclima.json)</label>
      <div class="fila"><div class="crece"><input type="text" id="rutaProy" placeholder="C:\\ruta\\al\\proyecto"></div><button id="btnExaC">Carpeta…</button><button id="btnExa">Archivo…</button><button class="principal" id="btnAbrir">Abrir</button></div>
      <h3>Proyectos en la carpeta de proyectos</h3><div id="prLista"><p class="chip">…</p></div>
      ${(S.estado.recientes || []).length ? "<h3>Recientes</h3>" + S.estado.recientes.map(r => `<div><a href="#" data-rec="${esc(r)}">${esc(r)}</a></div>`).join("") : ""}
     </section>
    </div>
    ${p ? '<section class="tarjeta" id="loHecho"><h2>Lo que llevas hecho</h2><p class="chip">Leyendo la carpeta del proyecto…</p></section>' : ""}
    <section class="tarjeta"><h2>Proyecto actual</h2>${p ? `<table><tbody>
      <tr><th>Nombre</th><td>${esc(p.nombre)}</td></tr><tr><th>Tipo</th><td>${p.tipo === "sintetico" ? "Sintético (prueba)" : "Datos reales"}</td></tr><tr><th>Ubicación</th><td>${esc(p.ubicacion || "—")}</td></tr>
      <tr><th>CRS horizontal</th><td>${esc(p.crs)}</td></tr><tr><th>Datum vertical</th><td>${esc(p.datum_vertical)}</td></tr><tr><th>Tipo de terreno</th><td>${esc(p.tipo_terreno || "desconocido")}</td></tr>
      <tr><th>Carpeta</th><td>${esc(p._carpeta)}</td></tr></tbody></table>
      <div id="prDes"></div>
      <h3>Sitio del proyecto</h3><div class="fila">${campoL("Longitud", "prSLon", (punto() || {}).lon ?? "")}${campoL("Latitud", "prSLat", (punto() || {}).lat ?? "")}<button id="prSitio">Guardar sitio</button><button id="prCentrar">Centrar en la cuenca activa</button></div>
      <h3>Nombre</h3><div class="fila">${campoL("Nuevo nombre", "prRen", p.nombre)}<button id="prRenB">Renombrar</button></div>
      <h3>Estaciones INAMHI más cercanas</h3><div id="prEst"><p class="chip">…</p></div>
      <details><summary>Procedencia y notas</summary><p>Origen: ${esc((p.procedencia || {}).origen)} · creado ${esc((p.procedencia || {}).creado)}</p><ul>${((p.procedencia || {}).notas || []).map(n => `<li>${esc(n)}</li>`).join("")}</ul></details>
      <h3>Guardar copia como…</h3><div class="fila"><div class="crece"><input type="text" id="rutaCopia" placeholder="C:\\ruta\\nueva\\carpeta"></div><button id="btnCopia">Guardar copia</button></div><p class="chip">Si la carpeta ya contiene un proyecto, se rechaza.</p>` : nota("No hay proyecto abierto.", "pend")}</section>`;
    if (p) api("/api/bitacora?n=200").then(b => { const el = $("#loHecho"); if (!el || b.error) return;          // Eta: se arma con los archivos, no con la memoria del navegador
      const fil = (b.hecho || []).map(x => `<tr><td>${x.hecho ? "✅" : "⬜"}</td><td><a href="#/${esc(x.modulo)}">${esc(x.paso)}</a></td><td>${esc(x.cuando || "")}</td><td style="font-size:12px">${esc(x.detalle || "")}</td></tr>`).join("");
      const ev = (b.eventos || []).slice().reverse().slice(0, 80).map(e => `<tr><td style="white-space:nowrap">${esc((e.fecha || "").slice(5))} ${esc(e.t || "")}</td><td>${esc(e.titulo)}</td><td style="font-size:12px;color:#93a4b8">${esc(e.detalle || "")}</td></tr>`).join("");
      el.innerHTML = `<h2>Lo que llevas hecho</h2><table><thead><tr><th></th><th>Paso</th><th>Cuándo</th><th>Detalle</th></tr></thead><tbody>${fil}</tbody></table>
        <details ${ev ? "" : "hidden"}><summary>Bitácora del proyecto (${(b.eventos || []).length} registros · <code>registro/bitacora.jsonl</code>)</summary><div class="tabla-ancha" style="max-height:360px;overflow:auto"><table><tbody>${ev}</tbody></table></div></details>
        <p class="chip">Todo esto sale de los archivos del proyecto: aunque se cierre el programa, se vaya la luz o recargues la página, al volver se ve igual.</p>`; });
    api("/api/proyectos/lista").then(j => { const el = $("#prLista"); if (el) el.innerHTML = (j.proyectos || []).length ? j.proyectos.map(x => `<div><a href="#" data-rec="${esc(x.carpeta)}">${esc(x.nombre)}</a> <span class="chip">${esc(x.carpeta.split(/[\\/]/).pop())}${x.ucec ? "" : " · sin sufijo ucec"}</span></div>`).join("") : '<p class="chip">Sin proyectos.</p>';
      el && el.querySelectorAll("[data-rec]").forEach(a => a.onclick = ev => { ev.preventDefault(); abrir(a.dataset.rec); }); });
    if (p) api("/api/proyecto/desactualizadas").then(j => { const x = j.desactualizadas, el = $("#prDes"); if (!x || !el) return;
      el.innerHTML = nota(`El sitio cambió el ${esc(x.fecha)}: ${x.descargas_desactualizadas.length} descarga(s) quedaron desactualizadas (MDT, suelo, CN/Manning, GEOGLOWS) y la IDF debe fijarse de nuevo.${x.crs_cambio ? " La zona UTM cambió." : ""} Rehazlas: <a href="#/terreno">5 · Terreno</a> · <a href="#/gee">2 · Datos / GEE</a> · <a href="#/idf">4 · IDF</a>.`, "pend"); });
    const sitio = async c => { const j = await api("/api/proyecto/sitio", c); if (j.error) return aviso(j.error, 7000); aviso("Sitio actualizado"); await cargarEstado(); navegar(); };
    if ($("#prSitio")) $("#prSitio").onclick = () => sitio({lon: $("#prSLon").value.trim(), lat: $("#prSLat").value.trim()});
    if ($("#prCentrar")) $("#prCentrar").onclick = () => sitio({centrar_cuenca: true});
    if ($("#prRenB")) $("#prRenB").onclick = async () => { const j = await api("/api/proyecto/renombrar", {nombre: $("#prRen").value.trim()}); if (j.error) return aviso(j.error, 7000); aviso("Proyecto renombrado: " + j.carpeta, 6000); await cargarEstado(); navegar(); };
    if (p && $("#prEst")) api("/api/estaciones/referencia").then(r => { const el = $("#prEst"); if (!el) return; if (r.error) { el.innerHTML = nota(esc(r.error), "pend"); return; }
      const t = (l) => `<table><thead><tr><th>Código</th><th>Nombre</th><th>Tipo</th><th class="num">Distancia km</th><th class="num">Altitud m</th></tr></thead><tbody>${l.map(e => `<tr><td><b>${esc(e.codigo)}</b></td><td>${esc(e.nombre)}</td><td>${esc(e.tipo)}</td><td class="num">${fmt(e.dist_km, 1)}</td><td class="num">${e.z_msnm == null ? "—" : fmt(e.z_msnm, 0)}</td></tr>`).join("")}</tbody></table>`;
      el.innerHTML = `<div class="rejilla"><div><h3>Hidrométricas</h3>${t(r.hidrometricas)}</div><div><h3>Meteorológicas</h3>${t(r.meteorologicas)}</div></div>`; });
    const abrir = async ruta => { const j = await api("/api/proyecto/abrir", {ruta}); if (j.error) return aviso(j.error, 8000); aviso("Proyecto abierto"); S.verif = null; await cargarEstado(); navegar(); };
    $("#prExa").onclick = async () => { const j = await api("/api/dialogo", {tipo: "carpeta"}); if (j.ruta) $("#prBase").value = j.ruta; };
    $("#prCrear").onclick = async () => {
      const g = id => $("#" + id).value.trim();
      if (!g("prNom") || (!g("prShp") && (!g("prLon") || !g("prLat")))) { $("#prMsg").innerHTML = nota("Escribe el nombre y la longitud y latitud del sitio, o elige el shape de la zona de estudio.", "err"); return; }
      $("#prMsg").innerHTML = '<p class="chip">Creando…</p>';
      const j = await api("/api/proyecto/crear", {nombre: g("prNom"), lon: g("prLon"), lat: g("prLat"), shape: g("prShp"), crs_shape: g("prShpCrs"), carpeta_base: g("prBase"), incluir_memoria: $("#prMem").checked});
      if (j.error) { $("#prMsg").innerHTML = nota(esc(j.error), "err"); return; }
      aviso("Proyecto creado"); S.verif = null; await cargarEstado(); navegar();
      const z = j.zona_estudio;
      $("#principal").insertAdjacentHTML("afterbegin", nota(`Proyecto creado en <code>${esc(j.carpeta)}</code>${j.series_guardadas ? ` con ${j.series_guardadas} serie(s) del premódulo` : ""}.` +
        (j.series_lejanas ? ` No se copiaron ${j.series_lejanas} serie(s) a más de ${j.radio_km} km del sitio.` : "") +
        (j.series_sin_coordenadas ? ` ${j.series_sin_coordenadas} serie(s) sin coordenadas sí se copiaron: revisa en el módulo 3 que sean de esta zona.` : "") +
        (z ? ` Zona de estudio: ${fmt(z.area_km2, 2)} km², punto interior ${fmt(z.lon, 4)}, ${fmt(z.lat, 4)}${z.carpeta ? " · cuenca activa registrada" : (z.error_cuenca ? " · no se pudo registrar como cuenca: " + esc(z.error_cuenca) : "")}.` : "") +
        ` Siguiente: módulo <b>2 · Datos / GEE</b>. Los productos ordenados se van guardando en <code>productos\\</code>.`, "ok"));
    };
    if ($("#prShpExa")) $("#prShpExa").onclick = async () => { const j = await api("/api/dialogo", {tipo: "archivo"}); if (j.ruta) $("#prShp").value = j.ruta; };
    $("#btnAbrir").onclick = () => abrir($("#rutaProy").value.trim());
    $("#btnExa").onclick = async () => { const j = await api("/api/dialogo", {tipo: "archivo"}); if (j.ruta) $("#rutaProy").value = j.ruta; };
    $("#btnExaC").onclick = async () => { const j = await api("/api/dialogo", {tipo: "carpeta"}); if (j.ruta) $("#rutaProy").value = j.ruta; };
    document.querySelectorAll("[data-demo]").forEach(b => b.onclick = async () => { const j = await api("/api/proyecto/demo", {id: b.dataset.demo}); if (j.error) return aviso(j.error, 8000); S.verif = null; await cargarEstado(); navegar(); });
    document.querySelectorAll("[data-rec]").forEach(a => a.onclick = e => { e.preventDefault(); abrir(a.dataset.rec); });
    if ($("#btnCopia")) $("#btnCopia").onclick = async () => { const j = await api("/api/proyecto/guardar_como", {carpeta: $("#rutaCopia").value.trim()}); aviso(j.error || "Copia guardada en " + j.guardado, 8000); };
  }

  // ================================================================== 2 · DATOS / GEE
  // Requisito del programa: cada persona usa SU cuenta de Google y SU proyecto de Google Cloud con Earth Engine. Un solo botón lleva a la página de Google (eliges tu correo y pulsas «Permitir»),
  // vuelve solo, prueba tu proyecto, inicializa y verifica. UCEclima nunca ve ni guarda tu contraseña ni tu token.
  const GEE = {auto: false, conectando: false};
  async function vGee() {
    $("#principal").innerHTML = encabezado("2 · Datos / Google Earth Engine", "Para usar UCEclima necesitas <b>tu propia cuenta de Google con Earth Engine y un proyecto de Google Cloud</b> (gratis para investigación y educación). Pulsa <b>Conectar</b>: se abre Google, eliges tu correo, pulsas «Permitir» y UCEclima se conecta, inicializa y verifica por ti.") + '<div id="gBody"></div><div id="gDesc"></div>';
    const e = await api("/api/gee/estado");
    if (e.credenciales && e.proyecto && !e.conectado && !GEE.auto) { GEE.auto = true; await pintarGee(); await conectarAuto(true); return; }      // ya autorizaste antes: se intenta conectar sola, sin pedirte nada
    await pintarGee();
  }
  async function conectarAuto(silencioso) {
    const msg = $("#gMsgC"); if (msg) msg.innerHTML = '<p class="chip">Probando tu proyecto de Google Cloud con Earth Engine…</p>';
    const t0 = Date.now(), e = await api("/api/gee/conectar", {}); await pintarGee();
    if (e.conectado) aviso("Earth Engine conectado: " + e.proyecto + " (" + ((Date.now() - t0) / 1000).toFixed(1) + " s)", 6000);
  }
  async function conectar() {
    if (GEE.conectando) return; GEE.conectando = true;
    try {
      const pid = (($("#gProy") || {}).value || "").trim();                                      // 1) el ID que escribió la persona manda (llave directa: solo se prueba ese)
      if (!pid) { $("#gMsgC").innerHTML = nota("Escribe primero el <b>ID de tu proyecto</b> de Google Cloud con Earth Engine (paso 1).", "err"); return; }
      const g = await api("/api/gee/proyecto", {proyecto: pid}); if (g.error) { $("#gMsgC").innerHTML = nota(esc(g.error), "err"); return; }
      let e = await api("/api/gee/estado");
      if (!e.credenciales) {                                                                      // 1) autorizar con la cuenta de Google en el navegador
        const a = await api("/api/gee/autorizar", {modo: "localhost"}); await pintarGee();
        for (let i = 0; i < 150; i++) {                                                           // hasta ~5 min esperando que elijas tu cuenta y pulses «Permitir»
          await new Promise(r => setTimeout(r, 2000)); if (!$("#gBody")) return;
          e = await api("/api/gee/estado"); const f = (e.auth || {}).fase;
          if (i === 22 && $("#gSugerencia")) $("#gSugerencia").innerHTML = '<p class="chip" style="color:#ffd166">¿No avanza? Si el navegador no vuelve a esta pantalla, pulsa «Conectar con código».</p>';
          if (f === "esperando_codigo") return;
          if (f === "completado") break; if (f === "error" || f === "cancelado") { await pintarGee(); return; }
        }
      }
      await conectarAuto(false);                                                                  // 2) probar proyectos, inicializar y verificar
    } finally { GEE.conectando = false; }
  }
  async function pintarGee() {
    const body = $("#gBody"); if (!body) return;
    const e = await api("/api/gee/estado"), a = e.auth || {}, v = e.verificacion || {};
    const espera = a.fase === "esperando_aprobacion" || a.fase === "esperando_codigo" || a.fase === "iniciando";
    const chip = (ok, txt) => badge(ok ? "ok" : "aviso", txt);
    body.innerHTML = `
    ${e.conectado ? nota(`<b>Conectado a Earth Engine ✓</b> · proyecto <b>${esc(e.proyecto)}</b><br><span class="chip">${esc(v.detalle || "")} · ${esc(v.fecha_utc || "")}</span>`, "ok") : nota("Aún no estás conectado a Earth Engine.", "pend")}
    <section class="tarjeta"><h2>Conectar con Google Earth Engine</h2>
      <div class="fila">${campoL("1 · ID de TU proyecto de Google Cloud con Earth Engine", "gProy", e.proyecto || e.proyecto_sugerido || "", "mi-proyecto-123 (minúsculas y guiones)")}</div>
      <p class="chip">Cada persona usa su propio proyecto. Es el <b>ID</b> (no el nombre visible): lo ves en <a href="https://console.cloud.google.com/" target="_blank" rel="noopener">console.cloud.google.com</a>, arriba a la izquierda, o en <a href="https://code.earthengine.google.com/" target="_blank" rel="noopener">code.earthengine.google.com</a>.</p>
      <div class="fila"><button class="principal" id="gConectar" ${espera || GEE.conectando ? "disabled" : ""}>${e.conectado ? "Volver a verificar la conexión" : "Conectar con Google Earth Engine"}</button><button id="gAuthCod2" ${espera && a.fase !== "esperando_codigo" ? "" : ""} title="Si el navegador no vuelve solo a esta pantalla, copia el código que muestra Google y pégalo aquí">Conectar con código</button>${espera ? '<button id="gCancel">Cancelar</button>' : ""}</div>
      <p class="chip">Dos formas, ambas válidas: <b>Conectar</b> (el navegador vuelve solo) o <b>Conectar con código</b> (copias un código de Google y lo pegas aquí).</p>
      <div id="gMsgC">${a.fase === "esperando_codigo" ? nota("<b>Se abrió tu navegador.</b> Elige tu cuenta de Google, pulsa «Permitir», <b>copia el código</b> que aparece y pégalo aquí:" + (a.url ? `<br><span class="chip">Si no se abrió: <a href="${esc(a.url)}" target="_blank" rel="noopener">abrir la página de Google</a></span>` : "") + `<div class="fila">${campoL("Código de Google", "gCodigo", "", "pega aquí el código")}<button class="principal" id="gEnviar">Enviar código</button></div>`, "pend") : espera ? nota("<b>Se abrió tu navegador.</b> Elige tu cuenta de Google y pulsa «Permitir». Cuando termines, vuelve aquí: esta pantalla se actualiza sola." + (a.url ? `<br><span class="chip">Si no se abrió: <a href="${esc(a.url)}" target="_blank" rel="noopener">abrir la página de Google</a></span>` : "") + '<div id="gSugerencia"></div>', "pend") : ""}
        ${a.fase === "error" ? nota("<b>No se completó la autorización automática.</b> " + esc(a.error || "") + "<br>Prueba el modo manual (abajo, «Usar código»).", "err") : ""}
        ${!e.conectado && v.ok === false && v.error && !espera ? nota("<b>No se pudo conectar.</b> " + esc(v.ayuda || "") + ((v.probados || []).length ? "<br><span class=\"chip\">Proyectos probados: " + v.probados.map(x => esc(x.proyecto) + " (" + (x.ok ? "ok" : "no funcionó") + ")").join(", ") + "</span>" : "") + (v.error ? `<details><summary>Detalle técnico</summary><p>${esc(v.error)}</p></details>` : ""), "err") : ""}</div>
      <ol class="chip" style="line-height:1.9;margin-top:8px"><li>${chip(e.credenciales, e.credenciales ? "autorizado" : "pendiente")} Autorización con tu cuenta de Google</li>
        <li>${chip(!!e.proyecto || e.conectado, e.proyecto ? esc(e.proyecto) : "pendiente")} Tu proyecto de Google Cloud ${e.candidatos && e.candidatos.length && !e.proyecto ? "(encontrado: " + esc(e.candidatos.join(", ")) + ")" : ""}</li>
        <li>${chip(e.conectado, e.conectado ? "verificado" : "pendiente")} Inicialización y verificación (consulta real a CHIRPS)</li></ol>
      <p class="chip">Requisito: una cuenta de Google con Earth Engine y un proyecto de Google Cloud registrado (<a href="https://code.earthengine.google.com/register" target="_blank" rel="noopener">crear / registrar aquí</a>, gratis para investigación). El programa nunca ve ni guarda tu contraseña ni tu token.</p>
      <details><summary>Opciones manuales (si el navegador no vuelve solo)</summary>
        <div class="fila"><button id="gAuthCod" title="Si el navegador no puede volver a esta pantalla, copia el código a mano">Autorizar con código (modo manual)</button></div>
        <div id="gMsgM"></div></details></section>
    <section class="tarjeta"><h2>Descargas del proyecto</h2>${S.estado.proyecto ? `<p class="chip">Una descarga a la vez; si una tarda demasiado puedes cancelarla. Todo se guarda dentro de la carpeta del proyecto abierto (<b>${esc(S.estado.proyecto.nombre)}</b>). La lluvia CHIRPS está en el módulo 3.</p>
      ${e.conectado ? "" : nota("Conéctate a Earth Engine (arriba) para habilitar las descargas de Earth Engine. El cálculo de CN y Manning (paso 2) no necesita conexión, pero sí las capas del paso 1.", "pend")}
      <div class="fila"><button data-d="mdt" ${e.conectado ? "" : "disabled"}>MDT 30 m (Copernicus)</button><button data-d="suelo" ${e.conectado ? "" : "disabled"} title="Baja el uso de suelo (WorldCover 10 m) y la textura del suelo a la carpeta del proyecto">1 · Uso de suelo y suelo</button><button data-d="cn_manning" title="Calcula CN y Manning con las capas del paso 1 (sin conexión); necesita el MDT registrado">2 · Calcular CN y Manning</button><button data-d="geoglows" ${e.conectado ? "" : "disabled"}>Caudal GEOGLOWS</button></div>
      <div class="fila"><div><label for="ggAmb">GEOGLOWS: buscar el tramo en</label><select id="ggAmb"><option value="sitio">el sitio</option><option value="cuenca">la salida de la cuenca activa</option></select></div>
        <div class="crece"><label for="ggRios">Capa de ríos GEOGLOWS v2 (opcional, para comparar DSContArea)</label><input type="text" id="ggRios" placeholder="C:\\ruta\\streams_605.gpkg"></div></div>
      <details style="margin:6px 0"><summary>¿Ya tienes tu MDT o tus propios CN y Manning en la PC?</summary>
        <p class="chip">MDT propio: regístralo en <a href="#/terreno">5 · Terreno</a> (GeoTIFF en metros, mismo CRS del proyecto). CN y Manning propios (GeoTIFF): tienen prioridad sobre los de Earth Engine.</p>
        <div class="fila"><div class="crece"><label for="ppCn">CN (GeoTIFF)</label><input type="text" id="ppCn"></div><button id="ppCnEx">Examinar…</button></div>
        <div class="fila"><div class="crece"><label for="ppMn">Manning (GeoTIFF)</label><input type="text" id="ppMn"></div><button id="ppMnEx">Examinar…</button></div>
        <div class="fila"><div class="crece"><label for="ppFu">Fuente (estudio, institución)</label><input type="text" id="ppFu"></div><button id="ppGo">Usar mis CN y Manning</button></div><div id="ppMsg"></div>
      </details>` : nota("Abre o crea un proyecto en el módulo 1 para descargar datos dentro de su carpeta.", "pend")}<div id="gDMsg"></div>
      ${S.estado.proyecto ? `<details id="gOtras" style="margin-top:12px"><summary><b>Otras descargas (opcional)</b> · pendiente, RUSLE, hidrografía, población, clima, emisiones…</summary><div id="gOtrasCuerpo"><p class="chip">Cargando el catálogo…</p></div></details>` : ""}</section>`;
    if ($("#gOtras")) $("#gOtras").addEventListener("toggle", function () { if (this.open && !this.dataset.listo) { this.dataset.listo = "1"; catalogoOtras(e.conectado); } });
    $("#gConectar").onclick = () => conectar();
    if ($("#gCancel")) $("#gCancel").onclick = async () => { await api("/api/gee/cancelar", {}); GEE.conectando = false; pintarGee(); };
    const porCodigo = async () => { await api("/api/gee/cancelar", {}); GEE.conectando = false; const j = await api("/api/gee/autorizar", {modo: "codigo"}); if (j.error && $("#gMsgM")) $("#gMsgM").innerHTML = nota(esc(j.error), "err"); pintarGee(); };
    $("#gAuthCod").onclick = porCodigo; $("#gAuthCod2").onclick = porCodigo;
    if ($("#gEnviar")) $("#gEnviar").onclick = async () => { const j = await api("/api/gee/codigo", {codigo: $("#gCodigo").value}); if (j.error) $("#gMsgM").innerHTML = nota(esc(j.error), "err"); else { await conectarAuto(false); } };
    document.querySelectorAll("[data-d]").forEach(b => b.onclick = async () => {
      const pt = punto() || {lon: -78.645, lat: -2.585}, f = b.dataset.d;
      const par = f === "mdt" ? {lon: pt.lon, lat: pt.lat, medio_km: 20} : f === "suelo" ? {lon: pt.lon, lat: pt.lat} : f === "geoglows" ? {lon: pt.lon, lat: pt.lat, ambito: ($("#ggAmb") || {}).value || "sitio", rios_geoglows: (($("#ggRios") || {}).value || "").trim()} : f === "celec" ? {inicio: "2010-01-01", fin: hoy()} : {};
      const j = await api("/api/descargas/iniciar", {fuente: f, parametros: par}); $("#gDMsg").innerHTML = j.error ? nota(esc(j.error), "err") : nota("Descarga lanzada…", "ok"); seguirDescargas($("#gDesc"));
    });
    if ($("#ppGo")) {
      const exa = (id) => async () => { const j = await api("/api/dialogo", {tipo: "raster"}); if (j.ruta) $("#" + id).value = j.ruta; };
      $("#ppCnEx").onclick = exa("ppCn"); $("#ppMnEx").onclick = exa("ppMn");
      $("#ppGo").onclick = async () => { const j = await api("/api/parametros/propios", {cn: $("#ppCn").value.trim(), manning: $("#ppMn").value.trim(), fuente: $("#ppFu").value.trim()});
        $("#ppMsg").innerHTML = j.error ? nota(esc(j.error), "err") : nota(esc(j.texto) + (j.avisos && j.avisos.length ? "<ul>" + j.avisos.map(a => `<li>${esc(a)}</li>`).join("") + "</ul>" : ""), "ok"); };
    }
    seguirDescargas($("#gDesc"));
  }

  async function catalogoOtras(conectado) {
    const cont = $("#gOtrasCuerpo"); const c = await api("/api/gee/catalogo");
    const porCat = {}; c.items.forEach(i => (porCat[i.categoria] = porCat[i.categoria] || []).push(i));
    cont.innerHTML = `<p class="chip">${esc(c.nota)} Son opcionales: lo imprescindible para hidro y land (terreno, uso de suelo, CN y Manning, lluvia) está arriba. Una descarga a la vez; puedes elegir varias capas.</p>
      ${Object.entries(porCat).map(([cat, its]) => `<h3>${esc(cat)}</h3>${its.map(i => `<label class="tog" style="display:flex;gap:8px;align-items:flex-start;margin:4px 0"><input type="checkbox" data-o="${esc(i.id)}" style="margin-top:4px"><span><b>${esc(i.nombre)}</b> <span class="chip">${esc(i.resolucion)} · ${esc(i.periodo)} · ${i.tipo === "imagen" ? "mapa (GeoTIFF)" : i.tipo === "serie" ? "serie mensual (CSV y Excel)" : i.tipo === "serie_imagen" ? "mapa + serie mensual" : "tabla / capa vectorial"}</span><br><span class="chip">${esc(i.descripcion)}${i.aviso ? " · <i>" + esc(i.aviso) + "</i>" : ""}</span></span></label>`).join("")}`).join("")}
      <div class="fila" style="margin-top:10px"><button class="principal" id="gOtrasGo" ${conectado ? "" : "disabled"}>Descargar las seleccionadas</button><button id="gOtrasNinguna">Quitar selección</button></div>${conectado ? "" : nota("Conéctate a Earth Engine (arriba) para habilitar estas descargas. Vías y poblados de OpenStreetMap no la necesita.", "pend")}<div id="gOtrasMsg"></div>`;
    $("#gOtrasNinguna").onclick = () => cont.querySelectorAll("[data-o]").forEach(x => x.checked = false);
    $("#gOtrasGo").onclick = async () => {
      const items = [...cont.querySelectorAll("[data-o]:checked")].map(x => x.dataset.o); if (!items.length) { $("#gOtrasMsg").innerHTML = nota("Elige al menos una capa.", "pend"); return; }
      const j = await api("/api/descargas/iniciar", {fuente: "otras", parametros: {items}}); $("#gOtrasMsg").innerHTML = j.error ? nota(esc(j.error), "err") : nota(`Descargando ${items.length} capa(s) en la carpeta del proyecto…`, "ok"); seguirDescargas($("#gDesc"));
    };
  }
  // ================================================================== 3 · CHIRPS
  async function vChirps() {
    $("#principal").innerHTML = encabezado("3 · CHIRPS", "Descarga la <b>serie diaria de CHIRPS</b> del sitio (desde 1981), genera los gráficos y tendencias y <b>guarda todo dentro de la carpeta del proyecto</b>. CHIRPS es un producto de satélite: sirve para contexto y para corregir sesgo del cambio climático, no es una medición de campo.") + '<div id="chBody"></div><div id="chDesc"></div><div id="chRes"></div>';
    await pintarChirps();
  }
  async function pintarChirps() {
    const body = $("#chBody"); if (!body) return;
    if (!S.estado.proyecto) { body.innerHTML = nota("Primero crea o abre un proyecto en el módulo <b>1 · Proyecto</b>: aquí se guardan los datos y los gráficos.", "pend"); return; }
    const g = await api("/api/gee/estado"), pt = punto() || {lon: "", lat: ""};
    body.innerHTML = `<section class="tarjeta"><h2>Descargar serie CHIRPS</h2>
      <div class="fila">${campoL("Longitud", "chLon", pt.lon)}${campoL("Latitud", "chLat", pt.lat)}${campoL("Desde", "chIni", "1981-01-01")}${campoL("Hasta", "chFin", hoy())}</div>
      <div class="fila">${g.conectado ? "" : '<button id="chCon">Conectar Earth Engine</button>'}<button class="principal" id="chGo" ${g.conectado ? "" : "disabled"}>Descargar CHIRPS y generar gráficos</button></div><div id="chMsg"></div>
      <p class="chip">Se guarda en <code>${esc(S.estado.proyecto._carpeta)}\\datos_descargados\\chirps_…</code>: serie diaria (CSV), gráficos (PNG), resumen anual (CSV) y tendencia (JSON).</p></section>`;
    if ($("#chCon")) $("#chCon").onclick = async () => { $("#chMsg").innerHTML = '<p class="chip">Conectando…</p>'; const j = await api("/api/gee/conectar", {}); if (j.conectado) vChirps(); else $("#chMsg").innerHTML = nota(esc(j.error || "No se pudo conectar: autoriza tu cuenta en 2 · Datos / GEE."), "err"); };
    if ($("#chGo")) $("#chGo").onclick = async () => {
      const v = id => $("#" + id).value.trim();
      const j = await api("/api/descargas/iniciar", {fuente: "chirps", parametros: {lon: v("chLon"), lat: v("chLat"), inicio: v("chIni"), fin: v("chFin")}});
      $("#chMsg").innerHTML = j.error ? nota(esc(j.error), "err") : nota("Descargando CHIRPS año por año…", "ok"); seguirDescargas($("#chDesc"), "chirps", () => resultados());
    };
    seguirDescargas($("#chDesc"), "chirps", () => resultados()); resultados();
  }
  async function resultados() {
    const el = $("#chRes"); if (!el) return;
    const r = await api("/api/chirps/graficos");
    if (r.error || !r.descarga) { el.innerHTML = r.error ? nota(esc(r.error), "err") : nota(esc(r.nota || "Aún no hay descargas CHIRPS."), "pend"); return; }
    const url = n => `/api/proyecto/archivo?ruta=${encodeURIComponent(r.carpeta + "/graficos/" + n)}&t=${Date.now()}`, rs = r.resumen || {}, t = rs.tendencia_total || {};
    el.innerHTML = `<section class="tarjeta"><h2>Resultados guardados en el proyecto</h2>
      <p class="chip">Carpeta: <code>${esc(r.carpeta)}</code> · periodo ${esc((rs.periodo || []).join(" → "))} · ${esc(rs.descripcion || "")}</p>
      <div class="metricas" style="margin-bottom:10px"><div class="metrica"><div class="v">${fmt(rs.media_anual_mm, 0)}</div><div class="k">mm/año (media)</div></div><div class="metrica"><div class="v">${rs.anios_completos ?? "—"}</div><div class="k">años completos</div></div>
       <div class="metrica"><div class="v">${t.sen_por_anio == null ? "—" : (t.sen_por_anio >= 0 ? "+" : "") + fmt(t.sen_por_anio, 1)}</div><div class="k">mm/año (Sen) · p=${t.p == null ? "—" : fmt(t.p, 2)}</div></div></div>
      ${t.p != null && t.p >= 0.05 ? nota("La tendencia <b>no es estadísticamente significativa</b> (p ≥ 0,05): descriptiva, no concluyente.", "pend") : ""}
      <div class="rejilla">${r.graficos.map(n => `<div><img class="mapa" style="width:100%;border-radius:10px" alt="${esc(n)}" src="${url(n)}"></div>`).join("")}</div>
      <p class="chip">Archivos: ${[...r.graficos, ...r.tablas, "chirps_resumen.json"].map(esc).join(", ")}</p></section>
      <section class="tarjeta"><h2>Series y tendencias (interactivo)</h2><div id="serBody"></div></section>`;
    const cat = await api("/api/series/catalogo"); const sub = {series: (cat.series || []).filter(s => /^chirps:/.test(s.id))};
    window.SERIES.montar(el.querySelector("#serBody"), sub, window.SERIES.EP_PROYECTO);
  }

  VISTAS.proyecto = vProyecto; VISTAS.gee = vGee; VISTAS.chirps = vChirps;
})();
