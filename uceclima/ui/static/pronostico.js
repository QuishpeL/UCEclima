/* Lambda · 7b Pronóstico de lluvia (GFS · ECMWF · NASA IMERG) y caudal GEOGLOWS Forecast.
   Un pronóstico no es una observación: al usarlo como forzamiento el resultado sale rotulado PRONÓSTICO. Investigación, no alerta oficial (INAMHI / SNGR). */
(() => {
  "use strict";
  const COL = {gfs: "#6cc4ec", ecmwf: "#ffb454", imerg: "#8ee58f"}, NOM = {gfs: "NOAA GFS (EE. UU.)", ecmwf: "ECMWF IFS (Europa)", imerg: "NASA IMERG (satélite)"};
  let ULT = {};                                                                  // consultas hechas en esta pantalla: id → resumen
  function grafico(series) {
    const W = 760, H = 210, m = {l: 44, r: 10, t: 10, b: 28}; const todos = series.flatMap(s => s.datos); if (!todos.length) return "";
    const t0 = Date.parse(todos[0][0]), t1 = Math.max(...todos.map(d => Date.parse(d[0]))), ymax = Math.max(1, ...todos.map(d => d[1])) * 1.1;
    const X = t => m.l + (t - t0) / Math.max(1, t1 - t0) * (W - m.l - m.r), Y = v => H - m.b - v / ymax * (H - m.t - m.b);
    const ejes = [0, .25, .5, .75, 1].map(f => `<line x1="${m.l}" x2="${W - m.r}" y1="${Y(f * ymax)}" y2="${Y(f * ymax)}" stroke="#2d4058" stroke-width=".6"/><text x="${m.l - 5}" y="${Y(f * ymax) + 4}" text-anchor="end" font-size="10" fill="#93a4b8">${fmt(f * ymax, 0)}</text>`).join("");
    const dias = []; for (let t = Math.ceil(t0 / 864e5) * 864e5; t <= t1; t += 864e5) dias.push(t);
    const marcas = dias.map(t => `<line x1="${X(t)}" x2="${X(t)}" y1="${m.t}" y2="${H - m.b}" stroke="#2d4058" stroke-width=".6" stroke-dasharray="3 3"/><text x="${X(t)}" y="${H - 10}" text-anchor="middle" font-size="10" fill="#93a4b8">${new Date(t).toISOString().slice(5, 10)}</text>`).join("");
    const lin = series.map(s => `<polyline fill="none" stroke="${s.color}" stroke-width="1.6" points="${s.datos.map(d => `${X(Date.parse(d[0])).toFixed(1)},${Y(d[1]).toFixed(1)}`).join(" ")}"/>`).join("");
    return `<svg viewBox="0 0 ${W} ${H}" style="width:100%;max-width:${W}px;background:#0e1a2b;border-radius:8px" role="img" aria-label="Lluvia horaria pronosticada (mm por hora, UTC)">${ejes}${marcas}${lin}<text x="${m.l}" y="${m.t + 8}" font-size="10" fill="#93a4b8">mm por hora (UTC)</text></svg>
      <div class="fila" style="gap:14px">${series.map(s => `<span class="chip"><span style="color:${s.color}">━</span> ${esc(NOM[s.id] || s.id)}</span>`).join("")}</div>`;
  }
  function tabla(r) {
    const ms = Object.keys(r.modelos);
    return `<table><thead><tr><th>Día (${esc(r.zona_local)})</th>${ms.map(m => `<th class="num">${esc(NOM[m])} (mm)</th>`).join("")}</tr></thead><tbody>
      ${r.tabla.map(f => `<tr><td>${esc(f.dia)}</td>${ms.map(m => `<td class="num" style="${f[m] != null && f[m] >= 50 ? "background:rgba(255,77,166,.25)" : ""}">${f[m] != null ? fmt(f[m], 1) : "—"}</td>`).join("")}</tr>`).join("")}
      <tr><th>Total</th>${ms.map(m => `<th class="num">${fmt(r.modelos[m].total_mm, 1)}</th>`).join("")}</tr></tbody></table>
      <p class="chip">Rosado: 50 mm o más en el día. Máximos: ${ms.map(m => `${esc(NOM[m])}: 1 h ${fmt(r.modelos[m].max_1h_mm, 1)} mm · 3 h ${fmt(r.modelos[m].max_3h_mm, 1)} mm · 24 h ${fmt(r.modelos[m].max_24h_mm, 1)} mm`).join(" — ")}.</p>`;
  }
  async function vPronostico() {
    const P = $("#principal");
    P.innerHTML = encabezado("7b · Pronóstico de lluvia", "Consulta la lluvia pronosticada por <b>GFS (NOAA, EE. UU.)</b> y <b>ECMWF (Europa)</b> y la lluvia ya caída estimada por <b>NASA IMERG</b> (satélite), y úsala como forzamiento de la corrida 2D. Un pronóstico a ~25 km falla a menudo en la ubicación y la intensidad de los aguaceros: es <b>investigación, no alerta oficial</b> (INAMHI / SNGR). Sin calibrar ni validar.") + requiereProyecto();
    if (!S.estado.proyecto) return;
    const L = await api("/api/pronostico/lista"); if (L.error) { P.insertAdjacentHTML("beforeend", nota(esc(L.error), "err")); return; }
    P.insertAdjacentHTML("beforeend", `
     <section class="tarjeta"><h2>1 · Consultar pronósticos</h2>
      <div class="fila" style="flex-wrap:wrap;gap:16px"><label class="tog"><input type="checkbox" class="pnMod" value="gfs" checked> NOAA GFS (EE. UU.)</label><label class="tog"><input type="checkbox" class="pnMod" value="ecmwf" checked> ECMWF IFS (Europa)</label><label class="tog" title="Lluvia ya caída de los últimos días, con ~1 día de retraso; necesita Earth Engine autorizado"><input type="checkbox" class="pnMod" value="imerg"> NASA IMERG (satélite, lluvia ya caída)</label></div>
      <div class="fila">${campo("Días", "pnDias", "5", "1 a 10")}${campo("Longitud (vacío = el sitio del proyecto)", "pnLon", "", "-90.30")}${campo("Latitud", "pnLat", "", "-0.74")}
       <div><label for="pnMue">Lluvia sobre</label><select id="pnMue"><option value="area" selected>Promedio del área 2D</option><option value="punto">Un solo punto</option></select></div>
       <div><label for="pnZona">Hora de la tabla</label><select id="pnZona"><option value="" selected>Automática por el sitio</option><option>UTC</option><option>America/Guayaquil</option><option>Pacific/Galapagos</option></select></div></div>
      <div class="fila"><button class="principal" id="pnGo">Consultar pronósticos</button></div><div id="pnRes"></div>
      <p class="chip">${esc(L.atribucion)}</p></section>
     <section class="tarjeta"><h2>2 · Usar como forzamiento de la corrida 2D</h2>
      <p class="chip">Importa la serie como una estación «PRON_…» y declara el evento; la corrida y sus mapas saldrán rotulados <b>PRONÓSTICO</b> (o ESTIMACIÓN SATELITAL), nunca «evento observado». Corre <b>una</b> corrida por vez en el módulo 7.</p>
      <div class="fila"><div class="crece"><label for="pnId">Consulta</label><select id="pnId">${L.consultas.map(c => `<option value="${esc(c.id)}">${esc(c.nombre)} · emitido ${esc((c.emitido_utc || "").slice(0, 16).replace("T", " "))} UTC · ${fmt(c.total_mm, 1)} mm</option>`).join("") || '<option value="">(todavía no hay consultas)</option>'}</select></div>
       ${campo("Horas a modelar (6 a 95)", "pnHoras", "72", "72")}<label class="tog"><input type="checkbox" id="pnPoca"> permitir poca lluvia</label></div>
      <div class="fila"><button class="principal" id="pnUsar">Declarar como forzamiento</button><button id="pnQuitar">Volver a la tormenta de diseño (IDF)</button><a class="btn" href="#/corrida">Ir a la corrida (módulo 7) →</a></div><div id="pnUsoRes"></div></section>
     <section class="tarjeta"><h2>3 · Caudal de la sierra (GEOGLOWS v2 Forecast)</h2>
      <p class="chip">Caudal pronosticado (mediana y banda alta del ensamble, cada 3 h) de un tramo GEOGLOWS. Deja dos CSV t_s;Q_m3s para declarar como <b>hidrograma de entrada</b> en el módulo 7. Es un modelo global: sirve para el orden de magnitud, no para ubicar el cauce.</p>
      <div class="fila">${campo("Número del tramo (river_id)", "pnRio", "", "ej.: 670065959")}${campo("Horas", "pnRioH", "96", "96")}<button id="pnRioGo">Consultar caudal</button></div><div id="pnRioRes"></div></section>
     <section class="tarjeta"><h2>Consultas anteriores</h2>${L.consultas.length ? `<table><thead><tr><th>Modelo</th><th>Emitido (UTC)</th><th class="num">Horas</th><th class="num">Total (mm)</th><th class="num">Máx. 1 h (mm)</th></tr></thead><tbody>${L.consultas.map(c => `<tr><td>${esc(c.nombre)}</td><td>${esc((c.emitido_utc || "").slice(0, 16).replace("T", " "))}</td><td class="num">${c.horas}</td><td class="num">${fmt(c.total_mm, 1)}</td><td class="num">${fmt(c.max_1h_mm, 1)}</td></tr>`).join("")}</tbody></table>` : '<p class="chip">Todavía no hay consultas en este proyecto.</p>'}</section>`);
    $("#pnGo").onclick = async () => {
      const modelos = [...document.querySelectorAll(".pnMod")].filter(x => x.checked).map(x => x.value); if (!modelos.length) { $("#pnRes").innerHTML = nota("Elige al menos un modelo.", "err"); return; }
      const num = id => { const v = ($(id).value || "").trim().replace(",", ".").replace(/[−–]/g, "-"); return v === "" ? null : parseFloat(v); };
      $("#pnGo").disabled = true; $("#pnRes").innerHTML = '<p class="chip">Consultando (unos segundos)…</p>';
      const j = await api("/api/pronostico/comparar", {modelos, dias: parseInt($("#pnDias").value, 10) || 5, lon: num("#pnLon"), lat: num("#pnLat"), muestreo: $("#pnMue").value, zona: $("#pnZona").value || null}); $("#pnGo").disabled = false;
      if (j.error) { $("#pnRes").innerHTML = nota(esc(j.error), "err"); return; }
      Object.entries(j.modelos).forEach(([m, r]) => { ULT[r.id] = r; });
      const sel = $("#pnId"); if (sel) { Object.values(j.modelos).forEach(r => { if (![...sel.options].some(o => o.value === r.id)) sel.add(new Option(`${r.nombre} · emitido ${r.emitido_utc.slice(0, 16).replace("T", " ")} UTC · ${fmt(r.total_mm, 1)} mm`, r.id)); }); const o0 = [...sel.options].find(o => o.value === "") ; if (o0) o0.remove(); sel.value = Object.values(j.modelos)[0].id; }
      $("#pnRes").innerHTML = (Object.keys(j.errores).length ? nota(Object.entries(j.errores).map(([m, e]) => `<b>${esc(NOM[m] || m)}</b>: ${esc(e)}`).join("<br>"), "err") : "") + tabla(j) + grafico(Object.entries(j.hietogramas).map(([m, d]) => ({id: m, color: COL[m] || "#fff", datos: d}))) + nota(esc(j.aviso), "pend");
    };
    $("#pnUsar").onclick = async () => {
      const id = $("#pnId").value; if (!id) { $("#pnUsoRes").innerHTML = nota("Primero consulta un pronóstico (sección 1).", "err"); return; }
      const j = await api("/api/pronostico/usar", {id, horas: parseInt($("#pnHoras").value, 10) || 72, permitir_poca_lluvia: $("#pnPoca").checked});
      $("#pnUsoRes").innerHTML = j.error ? nota(esc(j.error), "err") : nota(`<b>Forzamiento declarado</b>: ${fmt(j.P_total_mm, 1)} mm en ${fmt(j.duracion_h, 0)} h (${fmt(j.sim_horas, 0)} h simuladas) · estación ${esc(j.estacion)}.<br>${esc(j.siguiente_paso)}<br>${(j.advertencias || []).map(esc).join("<br>")}`, "ok");
    };
    $("#pnQuitar").onclick = async () => { const j = await api("/api/proyecto/evento_quitar", {}); $("#pnUsoRes").innerHTML = j.error ? nota(esc(j.error), "err") : nota("Listo: vuelve la tormenta de diseño (IDF).", "ok"); };
    $("#pnRioGo").onclick = async () => {
      $("#pnRioRes").innerHTML = '<p class="chip">Consultando GEOGLOWS…</p>'; const j = await api("/api/pronostico/geoglows", {river_id: $("#pnRio").value, horas: parseInt($("#pnRioH").value, 10) || 96});
      $("#pnRioRes").innerHTML = j.error ? nota(esc(j.error), "err") : nota(`Tramo ${j.river_id}: caudal máximo pronosticado <b>${fmt(j.q_mediana_max_m3s, 1)} m³/s</b> (mediana) y <b>${fmt(j.q_alta_max_m3s, 1)} m³/s</b> (banda alta) en ${j.horas} h.<br>Archivos en <code>${esc(j.carpeta)}</code>.<br><b>Filas para el módulo 7</b> (cambia &lt;x&gt; y &lt;y&gt; por la entrada sobre el cauce del 2D):<br><code>${Object.values(j.filas_hidrograma_de_entrada).map(esc).join("<br>")}</code><br>${esc(j.nota)}`, "ok") + nota(esc(j.aviso), "pend");
    };
  }
  VISTAS.pronostico = vPronostico;
})();
