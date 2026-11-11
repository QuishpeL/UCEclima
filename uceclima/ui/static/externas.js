// UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
/* Lambda 9.2 · cuencas externas AUTOMÁTICAS (método de Quito dentro del programa) y entradas GEOGLOWS para ríos grandes sin datos.
   Nada entra a la corrida hasta que la persona pulsa «Usar…». Una tarea a la vez (gestor de descargas). */
(function () {
  const ETQ = {mdt_cuenca: "MDT amplio (GLO-30, 90 m)", externas: "Detección de cuencas externas", geoglows_entrada: "Análisis GEOGLOWS"};

  async function seguirTarea(fuente, parametros, box, alTerminar) {
    const j = await api("/api/descargas/iniciar", {fuente, parametros});
    if (j.error) { box.innerHTML = nota(esc(j.error), "err"); return; }
    const paso = async () => {
      if (!document.body.contains(box)) return;
      const l = ((await api("/api/descargas")).descargas || []).find(d => d.id === j.descarga);
      if (!l) { setTimeout(paso, 1500); return; }
      box.innerHTML = `<div class="tarjeta" style="padding:10px"><b>${esc(ETQ[fuente] || fuente)}</b> ${badge(l.estado === "completado" ? "ok" : l.estado === "fallido" ? "error" : "aviso", l.estado)}
        ${l.estado === "en_curso" ? `<div class="barra-prog" style="margin:6px 0"><i style="width:${Math.round((l.progreso || 0) * 100)}%"></i></div><span class="chip">${esc(l.mensaje || "")}</span> <button id="xaCancel">Cancelar</button>` : ""}
        ${l.estado === "fallido" ? nota(esc(l.mensaje || ""), "err") : ""}</div>`;
      const c = document.getElementById("xaCancel"); if (c) c.onclick = () => api("/api/descargas/cancelar", {});
      if (l.estado === "en_curso") setTimeout(paso, 2000); else if (l.estado === "completado" && alTerminar) alTerminar(l);
    };
    paso();
  }

  function tablaDeteccion(d) {
    const filas = (d.cuencas || []).map(c => {
      const chica = c.tipo === "chica", usable = chica ? c.cn != null && c.lag_h != null : true;
      return `<tr><td><input type="checkbox" data-xa-${chica ? "chica" : "grande"}="${c.id}" ${usable ? "checked" : "disabled"} aria-label="Usar E${c.id}"></td>
        <td><b>E${c.id}</b></td><td>${chica ? "chica · SCS-CN" : "<b>grande · GEOGLOWS</b>"}</td><td>${fmt(c.area_km2, 2)}</td>
        <td>${chica ? (c.cn != null ? fmt(c.cn, 1) + ` <span class="chip">${fmt(c.cobertura_cn_pct, 0)} %</span>` : "—") : "—"}</td><td>${chica && c.lag_h != null ? fmt(c.lag_h, 2) : "—"}</td>
        <td>${fmt(c.entrada_xy[0], 0)}; ${fmt(c.entrada_xy[1], 0)} <span class="chip">${fmt(c.desplazamiento_m, 0)} m</span></td>
        <td>${c.en_cauce ? badge("ok", "en cauce") : `<span title="${esc((c.advertencias_entrada || []).join(" · "))}">${badge("aviso", "revisar")}</span>`}${c.cortada_borde_mdt ? " " + badge("error", "cortada por el MDT") : ""}</td></tr>`;
    }).join("");
    return `<table><thead><tr><th></th><th>Cuenca</th><th>Uso</th><th>Área (km²)</th><th>CN (cobertura)</th><th>Lag (h)</th><th>Entrada x; y (ajuste)</th><th>Entrada</th></tr></thead><tbody>${filas}</tbody></table>`;
  }

  async function pintar(box) {
    const x = await api("/api/corrida/externas"); if (x.error) { box.innerHTML = nota(esc(x.error), "err"); return; }
    const det = (x.detecciones || [])[0], ana = (x.analisis_geoglows || [])[0];
    const enUso = (x.cuencas_externas || []).length, geoUso = (x.entradas_geoglows || []).length;
    box.innerHTML = `<h3>Cuencas externas automáticas <span class="chip">9.2</span></h3>
      <p class="chip">Detecta el agua que llega desde FUERA del área 2D: D8 sobre el MDT amplio, cuencas sin solape, CN de las mismas tablas WorldCover × suelo del proyecto y lag NEH-630.
      Las <b>chicas</b> (≤ área máxima) se calculan con SCS-CN y la misma IDF y Tr de la corrida; las <b>grandes</b> (ríos) usan el hidrograma de GEOGLOWS. Nada entra a la corrida hasta que pulses «Usar». No calibrado.</p>
      ${enUso || geoUso ? nota(`En la corrida: ${enUso} cuenca(s) externa(s) SCS-CN · ${geoUso} entrada(s) GEOGLOWS${(x.entradas_geoglows || []).map(e => ` · <b>${esc(e.nombre)}</b> (tramo ${esc(e.river_id)}, Tr100 ${fmt((e.tabla_tr_m3s || {})["100"], 1)} m³/s)`).join("")}${x.exigir_entrada_en_cauce === false ? " · <b>comprobación de cauce desactivada por tu decisión</b>" : ""}`, "ok") : ""}
      <div class="fila"><span class="chip">${x.mdt_amplio ? "MDT amplio: " + esc(x.mdt_amplio) : "<b>Falta el MDT amplio</b> (paso 1)"}</span>
        <div><label for="xaLado">Lado del MDT amplio (km)</label><input id="xaLado" type="number" value="80" min="20" max="200" step="10" style="width:90px"></div>
        <button id="xaMdt" ${x.centro_lonlat ? "" : "disabled title='Registra primero el MDT del proyecto (módulo 5)'"}>1 · ${x.mdt_amplio ? "Volver a descargar" : "Descargar"} MDT amplio</button></div>
      <div class="fila"><div><label for="xaMin">Área mínima por entrada (km²)</label><input id="xaMin" type="number" value="1" min="0.1" step="0.5" style="width:90px"></div>
        <div><label for="xaMax">Área máxima SCS-CN (km²)</label><input id="xaMax" type="number" value="100" min="5" step="10" style="width:90px"></div>
        <button class="principal" id="xaDet" ${x.mdt_amplio ? "" : "disabled"}>2 · Detectar cuencas externas</button></div>
      <div id="xaTarea"></div>
      ${det ? `<h4>Detección ${esc(det.id)} <span class="chip">${esc((det.creado || "").replace("T", " "))} · mín ${fmt(det.area_min_km2, 1)} · máx ${fmt(det.area_max_km2, 0)} km²</span></h4>
        ${(det.avisos || []).map(a => nota(esc(a), "pend")).join("")}${tablaDeteccion(det)}<p class="chip">${esc(det.aportes_laterales || "")}</p>
        <div class="fila"><label style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="xaPermitir"> Permitir entradas que no pasan la comprobación de cauce (bajo mi responsabilidad; queda escrito en el proyecto)</label></div>
        <div class="fila"><button class="principal" id="xaUsar">3 · Usar las chicas marcadas (SCS-CN)</button><button id="xaGeo">3b · Analizar las grandes marcadas con GEOGLOWS</button>${enUso ? '<button id="xaQuitar">Quitar cuencas externas</button>' : ""}</div>` : ""}
      <h4>Entradas GEOGLOWS (río grande sin datos de caudal)</h4>
      <p class="chip">Una fila por río: <b>nombre; x; y</b> (dentro del área 2D, sobre el cauce)<b>; river_id</b> opcional. El pico de cada corrida es el caudal de su Tr (Gumbel de los máximos horarios anuales de GEOGLOWS 1940–hoy) y la forma es la media de las crecidas anuales; el pico coincide con el de la tormenta local (caso desfavorable).</p>
      <textarea id="xaGeoTxt" rows="2" style="width:100%" placeholder="rio_principal; 781500; 9962300"></textarea>
      <div class="fila"><button id="xaGeoMan">Analizar con GEOGLOWS</button>${geoUso ? '<button id="xaGeoQuitar">Quitar entradas GEOGLOWS</button>' : ""}</div>
      ${ana ? `<h4>Análisis GEOGLOWS ${esc(ana.id)}</h4><table><thead><tr><th></th><th>Entrada</th><th>Tramo</th><th>Años</th>${["2", "5", "10", "25", "50", "100"].map(t => `<th>Tr ${t}</th>`).join("")}<th>Q medio</th></tr></thead><tbody>
        ${ana.entradas.map(e => `<tr><td><input type="checkbox" data-xa-geo="${esc(e.nombre)}" checked aria-label="Usar ${esc(e.nombre)}"></td><td><b>${esc(e.nombre)}</b></td>
          <td title="${esc(e.origen_tramo || "")}">${esc(e.river_id)}${(e.candidatos || []).length > 1 ? ` <span class="chip">${e.candidatos.length} candidatos</span>` : ""}</td><td>${e.n_anios}</td>
          ${["2", "5", "10", "25", "50", "100"].map(t => `<td>${fmt((e.tabla_tr_m3s || {})[t], 1)}</td>`).join("")}<td>${fmt(e.caudal_medio_m3s, 2)}</td></tr>`).join("")}</tbody></table>
        <p class="chip">m³/s. Modelo global (GEOGLOWS v2, ECMWF): referencia externa, no observación. Si el tramo elegido no es el río que entra, escribe su river_id en la fila y analiza de nuevo.</p>
        <div class="fila"><button class="principal" id="xaGeoUsar">Usar las marcadas como entradas GEOGLOWS</button></div>` : ""}
      <div id="xaRes"></div>`;
    const res = $("#xaRes"), tareaBox = $("#xaTarea"), rehacer = () => pintar(box);
    $("#xaMdt").onclick = () => { const lado = +$("#xaLado").value || 80; seguirTarea("mdt_cuenca", {lon: x.centro_lonlat[0], lat: x.centro_lonlat[1], medio_km: lado / 2, escala_m: 90}, tareaBox, rehacer); };
    $("#xaDet").onclick = () => seguirTarea("externas", {area_min_km2: +$("#xaMin").value || 1, area_max_km2: +$("#xaMax").value || 100}, tareaBox, rehacer);
    if ($("#xaUsar")) $("#xaUsar").onclick = async () => {
      const ids = [...box.querySelectorAll("[data-xa-chica]:checked")].map(i => +i.dataset.xaChica);
      if (!ids.length) { res.innerHTML = nota("Marca al menos una cuenca chica.", "pend"); return; }
      const permitir = $("#xaPermitir").checked;
      if (permitir && !confirm("Vas a permitir entradas que no pasan la comprobación de cauce. Queda escrito en el proyecto como tu decisión. ¿Seguir?")) return;
      const j = await api("/api/corrida/externas_registrar", {deteccion: det.id, ids, permitir_fuera_de_cauce: permitir});
      res.innerHTML = j.error ? nota(esc(j.error), "err") : nota(`${j.cuencas_externas.length} cuenca(s) externa(s) en la corrida. ${esc(j.nota)}`, "ok");
      if (!j.error) { setTimeout(rehacer, 1500); if (typeof pintarForzamiento === "function") setTimeout(pintarForzamiento, 1600); }
    };
    if ($("#xaQuitar")) $("#xaQuitar").onclick = async () => { const j = await api("/api/corrida/externas_registrar", {quitar: true}); res.innerHTML = nota(esc(j.error || j.nota), j.error ? "err" : "ok"); setTimeout(rehacer, 1200); };
    const analizar = entradas => {
      if (!entradas.length) { res.innerHTML = nota("No hay entradas para analizar.", "pend"); return; }
      if (entradas.length > 6) { res.innerHTML = nota("Como máximo 6 ríos por análisis (cada uno baja ~25 MB de GEOGLOWS).", "pend"); return; }
      seguirTarea("geoglows_entrada", {entradas}, tareaBox, rehacer);
    };
    if ($("#xaGeo")) $("#xaGeo").onclick = () => {
      const ids = new Set([...box.querySelectorAll("[data-xa-grande]:checked")].map(i => +i.dataset.xaGrande));
      analizar(det.cuencas.filter(c => ids.has(c.id)).map(c => ({nombre: "E" + c.id, xy: c.entrada_xy})));
    };
    $("#xaGeoMan").onclick = () => analizar($("#xaGeoTxt").value.split("\n").map(l => l.split(";").map(s => s.trim())).filter(p => p.length >= 3 && p[0])
      .map(p => ({nombre: p[0], xy: [Number(p[1]), Number(p[2])], ...(p[3] ? {river_id: +p[3]} : {})})));
    if ($("#xaGeoUsar")) $("#xaGeoUsar").onclick = async () => {
      const nombres = [...box.querySelectorAll("[data-xa-geo]:checked")].map(i => i.dataset.xaGeo);
      if (!nombres.length) { res.innerHTML = nota("Marca al menos una entrada.", "pend"); return; }
      const j = await api("/api/corrida/entradas_geoglows", {analisis: ana.id, nombres});
      res.innerHTML = j.error ? nota(esc(j.error), "err") : nota(`${j.entradas_geoglows.length} entrada(s) GEOGLOWS en la corrida. ${esc(j.nota)}`, "ok");
      if (!j.error) setTimeout(rehacer, 1500);
    };
    if ($("#xaGeoQuitar")) $("#xaGeoQuitar").onclick = async () => { const j = await api("/api/corrida/entradas_geoglows", {quitar: true}); res.innerHTML = nota(esc(j.error || "Entradas GEOGLOWS quitadas."), j.error ? "err" : "ok"); setTimeout(rehacer, 1200); };
  }
  window.UCE_externas = pintar;
})();
