/* Hidrología y calibración · hietograma, hidrogramas observado/simulado, volúmenes acumulados, balance por subcuenca y tránsito por tramo, con las series reales del núcleo.
   Sin observaciones válidas el resultado se rotula «SIMULACIÓN SIN CALIBRAR». La referencia externa de hidro es un modelo, NO una observación. X en tonos fríos; los escenarios de cambio climático (cc_*) en magenta. */
(() => {
  "use strict";
  const G = window.GRAF, {C, nf, E, lin, nice, marco, ejeY, hover} = G;
  const COL = {sim: "#6cc4ec", ref: "#93a4b8", obs: "#ffffff", lluvia: "#ffd166", salida: "#a98bff", cc: "#ff4da6"};
  const ST = {casos: null, fuente: "corrida", id: "", sub: "", caso: "C1", datos: null};
  const colSim = id => /^cc_|_cc_/.test(id || "") ? COL.cc : COL.sim;

  async function vHidro() {
    const P = document.querySelector("#principal");
    P.innerHTML = `<h1>hidro · Hidrología</h1><p class="sub">Series reales de las corridas del proyecto, con unidades y fechas tal cual. Las métricas contra observaciones se calculan <b>solo en los instantes coincidentes con dato válido</b>. Si faltan observaciones, el resultado es una <b>simulación sin calibrar</b>. Sin caudales observados confirmados no hay calibración posible.</p><div id="hiBody"><p class="chip">Cargando…</p></div>`;
    ST.casos = await api("/api/hidrologia/casos");
    if (ST.casos.error) { document.querySelector("#hiBody").innerHTML = nota(E(ST.casos.error), "err"); return; }
    if (!ST.id) { const c = (ST.casos.corridas || [])[0]; if (c) { ST.fuente = "corrida"; ST.id = c.id; } }
    await cargar();
  }

  async function cargar() {
    const body = document.querySelector("#hiBody"); if (!body) return;
    const c = ST.casos, opC = (c.corridas || []).map(r => `<option value="corrida|${E(r.id)}" ${ST.fuente === "corrida" && ST.id === r.id ? "selected" : ""}>${E(r.id.replace("corrida_", ""))} · ${E(r.escenario || "")} · ${nf(r.P_total_mm, 0)} mm</option>`).join("");
    body.innerHTML = `<section class="tarjeta"><div class="fila"><div class="crece"><label for="hiSel">Caso</label><select id="hiSel">${opC}</select></div>
        <button class="principal" id="hiExp" disabled>Exportar gráficas y tablas</button></div><div id="hiMsg"></div></section><div id="hiRes"><p class="chip">Cargando serie…</p></div>`;
    body.querySelector("#hiSel").onchange = e => { const [f, i] = e.target.value.split("|"); ST.fuente = f; ST.id = i; ST.sub = ""; cargar(); };
    if (!ST.id) { body.querySelector("#hiRes").innerHTML = nota("Este proyecto aún no tiene corridas con resultados. Ejecuta una corrida (módulo land · Corrida 2D) y vuelve aquí. " + E(c.subcuencas || ""), "pend"); return; }
    const d = await api(`/api/hidrologia/serie?fuente=${ST.fuente}&id=${encodeURIComponent(ST.id)}`);
    if (d.error) { body.querySelector("#hiRes").innerHTML = nota(E(d.error), "err"); return; }
    ST.datos = d; body.querySelector("#hiExp").disabled = false;
    body.querySelector("#hiExp").onclick = async () => { const b = body.querySelector("#hiExp"); b.disabled = true; const j = await api("/api/hidrologia/exportar", {fuente: ST.fuente, id: ST.id}); b.disabled = false;
      body.querySelector("#hiMsg").innerHTML = j.error ? nota(E(j.error), "err") : nota(`Exportado en una carpeta nueva: <b>${E(j.carpeta)}</b><br>Tablas: ${j.tablas.map(E).join(", ")}<br>Gráficas: ${j.graficas.map(E).join(", ")}`, "ok"); };
    pintar(body.querySelector("#hiRes"), d);
  }

  const leyenda = items => `<div style="display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:${C.tenue};margin:4px 0">${items.map(([c, t, d]) => `<span><i style="display:inline-block;width:18px;border-top:3px ${d ? "dashed" : "solid"} ${c};vertical-align:middle"></i> ${E(t)}</span>`).join("")}</div>`;
  const hh = s => nf(s / 3600, 1);

  // líneas con eje X en horas (o fechas si las hay); series [{n, c, x, y, d, w}]
  function lineas(el, series, o) {
    const W = o.W || 1000, H = o.H || 300, L = 62, R = 16, T = 24, B = 38, xs = series.flatMap(s => s.x), xmin = Math.min(...xs), xmax = Math.max(...xs), vals = series.flatMap(s => s.y.filter(v => v !== null && isFinite(v)));
    const vmax = o.vmax || nice(Math.max(...vals, 1e-9) * 1.08), x = lin(xmin, xmax, L, W - R), y = lin(0, vmax, H - B, T); let s = marco(W, H) + ejeY(L, W - R, y, vmax, o.unidad);
    const n = 6; for (let k = 0; k <= n; k++) { const v = xmin + (xmax - xmin) * k / n; s += `<text x="${x(v)}" y="${H - B + 16}" text-anchor="middle" font-size="11.5" fill="${C.tenue}">${o.fmtX(v)}</text>`; }
    series.forEach(se => { const pts = se.x.map((a, i) => se.y[i] === null || !isFinite(se.y[i]) ? null : x(a) + "," + y(se.y[i])).filter(Boolean).join(" ");
      s += se.pts ? se.x.map((a, i) => `<circle cx="${x(a)}" cy="${y(se.y[i])}" r="4" fill="${se.c}"/>`).join("") : `<polyline fill="none" stroke="${se.c}" stroke-width="${se.w || 2.2}" ${se.d ? 'stroke-dasharray="6 5"' : ""} points="${pts}"/>`; });
    el.innerHTML = leyenda(series.map(z => [z.c, z.n, z.d])) + s + "</svg>";
    hover(el.querySelector("svg"), W, px => { const v = xmin + (px - L) / (W - L - R) * (xmax - xmin); if (v < xmin || v > xmax) return null; return `<b>${o.fmtX(v)}</b>` + series.map(se => { let k = 0, best = 1e18; se.x.forEach((a, i) => { if (Math.abs(a - v) < best) { best = Math.abs(a - v); k = i; } }); const val = se.y[k]; return val === null || !isFinite(val) ? "" : `<br><span style="color:${se.c}">${E(se.n.slice(0, 38))}</span> ${nf(val, o.dec ?? 2)}`; }).join(""); });
  }

  function pintar(el, d) {
    const cal = d.estado.calibracion === "sin_calibrar", h = d.hietograma, m = d.metricas;
    const xh = h.inicio_s.map((a, i) => (a + h.fin_s[i]) / 2);
    el.innerHTML = `
    <section class="tarjeta"><h2 style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">Estado del resultado <span class="chip" style="border:1px solid ${cal ? "#ffd166" : C.cian};color:${cal ? "#ffd166" : C.cian};padding:3px 10px;border-radius:12px;font-weight:700">${E(d.estado.etiqueta)}</span></h2>
      <p class="chip">${E(d.estado.motivo)}.</p><p class="chip">Observaciones: ${E(d.observaciones)}. Tiempo: ${E(d.tiempo.nota)}${d.tiempo.referencia ? " · inicio " + E(d.tiempo.referencia) : ""}.</p>
      <details><summary>Aviso</summary><p class="chip">${E(d.aviso)}</p></details></section>
    <section class="tarjeta"><h2>Hietograma</h2><p class="chip">${E(h.unidad)} · barras hacia abajo (convención de hietograma); línea = acumulado (mm, eje derecho).</p><div id="hiH"></div></section>
    <section class="tarjeta"><h2>Hidrogramas</h2>${d.fuente === "cuenca_hms" ? `<div class="fila"><div class="crece"><label for="hiSub">Subcuenca</label><select id="hiSub">${d.balance.map(b => `<option value="${E(b.unidad_espacial)}" ${((ST.sub || d.balance[0].unidad_espacial) === b.unidad_espacial) ? "selected" : ""}>${E(b.unidad_espacial)} · ${nf(b.area_km2, 1)} km²</option>`).join("")}</select></div></div>` : ""}<p class="chip" id="hiHN"></p><div id="hiQ"></div>
      <div id="hiMet"></div></section>
    <section class="tarjeta"><h2>Volúmenes acumulados</h2><p class="chip">${E(d.volumenes.unidad)}${d.volumenes.nota_vol ? " · " + E(d.volumenes.nota_vol) : ""}</p><div id="hiV"></div></section>
    <section class="tarjeta"><h2>Balance ${d.fuente === "cuenca_hms" ? "por subcuenca" : "del dominio"}</h2><style>#hiB td,#hiB th{white-space:nowrap}</style><div id="hiB"></div></section>
    <section class="tarjeta"><h2>Tránsito por tramo</h2><p class="chip">${E(d.transito_nota)}</p><div id="hiT"></div></section>`;
    hietograma(el.querySelector("#hiH"), h, xh, d);
    const selS = el.querySelector("#hiSub"); if (selS) selS.onchange = e => { ST.sub = e.target.value; hidro(el, d); };
    hidro(el, d); volumenes(el.querySelector("#hiV"), d); balance(el.querySelector("#hiB"), d); transito(el.querySelector("#hiT"), d);
  }

  function hietograma(el, h, xh, d) {
    const W = 1000, H = 280, L = 62, R = 62, T = 22, B = 38, xmax = Math.max(...h.fin_s), vmax = nice(Math.max(...h.mm) * 1.15), acmax = nice(Math.max(...h.acumulado_mm) * 1.05), x = lin(0, xmax, L, W - R), yb = lin(0, vmax, T, H - B), ya = lin(0, acmax, H - B, T);
    let s = marco(W, H);
    for (let k = 0; k <= 4; k++) { const v = vmax * k / 4; s += `<text x="${L - 8}" y="${yb(v) + 4}" text-anchor="end" font-size="11.5" fill="${C.tenue}">${nf(v, 1)}</text><line x1="${L}" x2="${W - R}" y1="${yb(v)}" y2="${yb(v)}" stroke="${C.reja}"/>`; const a = acmax * k / 4; s += `<text x="${W - R + 8}" y="${ya(a) + 4}" font-size="11.5" fill="${COL.lluvia}">${nf(a, 0)}</text>`; }
    h.mm.forEach((v, i) => { s += `<rect x="${x(h.inicio_s[i]) + 1}" y="${yb(0)}" width="${Math.max(1, x(h.fin_s[i]) - x(h.inicio_s[i]) - 2)}" height="${yb(v) - yb(0)}" fill="${COL.sim}" opacity=".85"/>`; });
    s += `<polyline fill="none" stroke="${COL.lluvia}" stroke-width="2.4" points="${xh.map((a, i) => x(a) + "," + ya(h.acumulado_mm[i])).join(" ")}"/>`;
    for (let k = 0; k <= 6; k++) { const v = xmax * k / 6; s += `<text x="${x(v)}" y="${H - B + 16}" text-anchor="middle" font-size="11.5" fill="${C.tenue}">${d.tiempo.referencia && h.fecha_inicio ? E((h.fecha_inicio[Math.min(h.fecha_inicio.length - 1, Math.round(k / 6 * (h.fecha_inicio.length - 1)))] || "").slice(5, 16)) : hh(v) + " h"}</text>`; }
    el.innerHTML = s + "</svg>";
    hover(el.querySelector("svg"), W, px => { const t = (px - L) / (W - L - R) * xmax; const i = h.inicio_s.findIndex((a, k) => t >= a && t < h.fin_s[k]); return i < 0 ? null : `<b>${hh(h.inicio_s[i])}–${hh(h.fin_s[i])} h</b><br>${nf(h.mm[i], 2)} mm · acumulado ${nf(h.acumulado_mm[i], 1)} mm`; });
  }

  function hidro(el, d) {
    let series = d.hidrogramas, nombre = "";
    if (d.fuente === "cuenca_hms") {
      const s = ST.sub || d.balance[0].unidad_espacial, q = d.hidrogramas_subcuencas[s]; nombre = s;
      series = [{nombre: "hidro (SCS-CN + UH gamma, PRF " + d.resumen.prf + ") · " + s, tipo: "simulado", t_s: q.t_s, q: q.q_clim}, {nombre: "hidro de referencia (modelo externo, NO observación) · " + s, tipo: "referencia_modelo", t_s: q.t_s, q: q.q_hms}];
    }
    const usaFecha = series.some(s => s.fecha && s.tipo === "observado");
    const S = series.map(s => ({n: s.nombre, c: s.tipo === "observado" ? COL.obs : s.tipo === "referencia_modelo" ? COL.ref : colSim(d.id + (d.escenario || "")), d: s.tipo === "referencia_modelo", pts: s.tipo === "observado" && s.q.length < 40,
      x: usaFecha ? s.fecha.map(f => new Date(f).getTime() / 3600000) : s.t_s.map(t => t / 3600), y: s.q}));
    el.querySelector("#hiHN").textContent = d.fuente === "cuenca_hms" ? "Caudal local de la subcuenca (sin tránsito por tramo), m³/s. Gris punteado = modelo de referencia externo (hidro), no observación." : "Caudal simulado en la frontera de salida del dominio 2D (m³/s), obtenido del balance de agua del solver; no es un caudal en una sección aforada.";
    lineas(el.querySelector("#hiQ"), S, {unidad: "m³/s", fmtX: v => usaFecha ? new Date(v * 3600000).toISOString().slice(0, 16).replace("T", " ") : nf(v, 1) + " h", dec: 2});
    const m = d.metricas, M = el.querySelector("#hiMet");
    if (d.fuente === "cuenca_hms") {
      const b = d.balance.find(z => z.unidad_espacial === nombre); M.innerHTML = b ? `<p class="chip"><b>Acuerdo hidro–referencia</b> (no es error contra observaciones): volumen ${b.dif_vol_pct >= 0 ? "+" : ""}${nf(b.dif_vol_pct, 1)} % · pico ${b.dif_pico_pct >= 0 ? "+" : ""}${nf(b.dif_pico_pct, 1)} % · tiempo al pico ${nf(b.tp_clim_h, 2)} h frente a ${nf(b.tp_hms_h, 2)} h.</p>` : ""; return;
    }
    M.innerHTML = m ? (m.calculado ? `<div class="tabla-ancha"><table><thead><tr><th>Pares coincidentes</th><th class="num">NSE</th><th class="num">KGE</th><th class="num">PBIAS %</th><th class="num">RMSE (m³/s)</th><th class="num">Error de pico %</th><th class="num">Error t. pico (min)</th><th class="num">Error de volumen %</th></tr></thead>
      <tbody><tr><td>${m.n_pares} (${E((m.periodo_coincidente || []).join(" → "))})</td><td class="num">${nf(m.NSE, 2)}</td><td class="num">${nf(m.KGE, 2)}</td><td class="num">${nf(m.PBIAS_pct, 1)}</td><td class="num">${nf(m.RMSE, 2)}</td><td class="num">${nf(m.error_pico_pct, 1)}</td><td class="num">${nf(m.error_tiempo_pico_min, 0)}</td><td class="num">${nf(m.error_volumen_pct, 1)}</td></tr></tbody></table></div><p class="chip">${E(m.criterio)}. ${E(m.nota)}</p>` : nota(E(m.motivo), "pend"))
      : '<div class="nota pend"><b>Sin métricas:</b> no hay observaciones válidas coincidentes con esta simulación (la corrida de diseño no tiene fechas, o no hay aforos con identidad confirmada). Resultado: simulación sin calibrar.</div>';
  }

  function volumenes(el, d) {
    const v = d.volumenes, t = v.t_s.map(a => a / 3600), S = [];
    if (v.lluvia_m3) S.push({n: "lluvia sobre el dominio", c: COL.lluvia, x: t, y: v.lluvia_m3}, {n: "escorrentía generada", c: COL.sim, x: t, y: v.escorrentia_m3}, {n: "salida acumulada", c: COL.salida, x: t, y: v.salida_m3}, {n: "almacenado", c: COL.ref, x: t, y: v.almacenado_m3, d: 1}, {n: "pérdidas inferidas (lluvia − escorrentía)", c: "#7fd1b9", x: t, y: v.perdidas_inferidas_m3, d: 1});
    else S.push({n: "hidro · suma de hidrogramas locales", c: COL.sim, x: t, y: v.clim_acum_m3}, {n: "hidro (referencia externa) · suma de hidrogramas locales", c: COL.ref, x: t, y: v.hms_acum_m3, d: 1});
    lineas(el, S, {unidad: "m³", fmtX: a => nf(a, 1) + " h", dec: 0});
  }

  const fm = (v, dd = 0) => v === null || v === undefined || !isFinite(v) ? "—" : nf(v, dd);
  function balance(el, d) {
    if (d.fuente === "cuenca_hms") {
      el.innerHTML = `<p class="chip">Por subcuenca: lluvia, exceso (pérdidas SCS-CN) y volumen de escorrentía de hidro frente a la referencia externa (modelo). Total hidro ${fm(d.volumenes.vol_clim_total_m3 / 1e6, 2)} hm³ · ref. ${fm(d.volumenes.vol_hms_total_m3 / 1e6, 2)} hm³.</p>
      <div class="tabla-ancha"><table><thead><tr><th>Subcuenca</th><th class="num">Área km²</th><th class="num">CN</th><th class="num">Lluvia mm</th><th class="num">Exceso hidro mm</th><th class="num">Exceso ref. mm</th><th class="num">Vol. hidro m³</th><th class="num">Vol. ref. m³</th><th class="num">Δ vol. %</th><th class="num">Qp hidro</th><th class="num">Qp ref.</th><th class="num">Δ pico %</th></tr></thead>
      <tbody>${d.balance.map(b => `<tr><td><b>${E(b.unidad_espacial)}</b></td><td class="num">${fm(b.area_km2, 1)}</td><td class="num">${fm(b.cn, 1)}</td><td class="num">${fm(b.lluvia_mm, 1)}</td><td class="num">${fm(b.exceso_clim_mm, 1)}</td><td class="num">${fm(b.exceso_hms_mm, 1)}</td><td class="num">${fm(b.vol_clim_m3)}</td><td class="num">${fm(b.vol_hms_m3)}</td><td class="num">${fm(b.dif_vol_pct, 1)}</td><td class="num">${fm(b.Qp_clim, 1)}</td><td class="num">${fm(b.Qp_hms, 1)}</td><td class="num">${fm(b.dif_pico_pct, 1)}</td></tr>`).join("")}</tbody></table></div>`;
      return;
    }
    const b = d.balance[0]; const it = [["Lluvia", b.lluvia_m3, COL.lluvia], ["Escorrentía generada", b.escorrentia_generada_m3, COL.sim], ["Pérdidas inferidas", b.perdidas_inferidas_m3, "#7fd1b9"], ["Salida del dominio", b.salida_m3, COL.salida], ["Almacenado final", b.almacenado_final_m3, COL.ref]];
    const vmax = Math.max(...it.map(i => i.v ?? i[1]));
    el.innerHTML = `<p class="chip">${E(b.nota)} Residual del solver ${fm(b.residual_m3, 6)} m³ (error máx. ${b.error_balance_max_pct?.toExponential(1)} %). No hay subcuencas en el modelo 2D: una sola unidad.</p>
      <div class="tabla-ancha"><table><thead><tr><th>Componente</th><th class="num">Volumen (m³)</th><th class="num">hm³</th><th class="num">% de la lluvia</th><th></th></tr></thead><tbody>${it.map(([n, v, c]) => `<tr><td>${n}</td><td class="num">${fm(v)}</td><td class="num">${fm(v / 1e6, 3)}</td><td class="num">${fm(100 * v / b.lluvia_m3, 1)}</td><td style="width:34%"><div style="height:10px;border-radius:5px;background:${c};width:${Math.max(1, 100 * v / vmax)}%"></div></td></tr>`).join("")}</tbody></table></div>`;
  }

  function transito(el, d) {
    if (!d.transito.length) { el.innerHTML = '<div class="nota pend">No aplica a esta fuente.</div>'; return; }
    const t = d.transito.find(z => z.caso === ST.caso) || d.transito[0];
    el.innerHTML = `<div class="fila">${d.transito.map(z => `<button data-c="${E(z.caso)}" ${z.caso === t.caso ? 'class="principal"' : ""}>${E(z.caso)} · K ${z.K_h} h · X ${z.X} · n ${z.subtramos}</button>`).join("")}</div><p class="chip">${E(t.nota || "")} dt ${t.dt_min} min · Q inicial ${t.q0_m3s} m³/s.</p><div id="hiTq"></div>`;
    el.querySelectorAll("button[data-c]").forEach(b => b.onclick = () => { ST.caso = b.dataset.c; transito(el, d); });
    const dev = t.CLIMANET.map((v, i) => Math.max(Math.abs(v - t.q0_m3s), Math.abs(t.entrada[i] - t.q0_m3s))), mx = Math.max(...dev); let fin = dev.length - 1; while (fin > 0 && dev[fin] < 0.01 * mx) fin--;
    fin = Math.min(dev.length - 1, Math.ceil(fin * 1.2)); const cut = a => a.slice(0, fin + 1), x = cut(t.t_min).map(a => a / 60);
    lineas(el.querySelector("#hiTq"), [{n: "entrada (sintética)", c: COL.lluvia, x, y: cut(t.entrada)}, {n: "hidro (referencia externa)", c: COL.ref, x, y: cut(t.HMS), d: 1}, {n: "hidro", c: COL.sim, x, y: cut(t.CLIMANET)}], {unidad: "m³/s", fmtX: a => nf(a, 1) + " h", dec: 2});
  }

  VISTAS.hidrologia = vHidro;
})();
