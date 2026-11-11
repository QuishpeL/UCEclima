/* CMIP6 · cambio climático (Y). X = condiciones existentes (válidas); Y = escenario CMIP6 (NASA NEX-GDDP, 25 km) con sesgo corregido (QQM) y señal preservada (QDM).
   La decisión de asumir la línea base es del usuario y queda registrada; todo lo de Y se rotula como proyección bajo supuesto. */
(() => {
  "use strict";
  const G = window.GRAF, {C, nf, E, lin, nice, marco, ejeY, hover} = G;
  const COL = {obs: "#ffffff", orig: "#93a4b8", qqm: "#6cc4ec", ens: "#9fb4ff", s245: "#ff9fd8", s585: "#d4147f"};     // magenta = SOLO cambio climático (SSP); el ensamble histórico va en azul-violeta
  const MAG = (ssp, fin) => ssp === "ssp585" ? (fin ? "#d4147f" : "#ff4da6") : (fin ? "#f05cc0" : "#ff9fd8");
  const ST = {estado: null};
  const num = (v, d = 1) => nf(v, d);

  async function vCmip6() {
    const P = document.querySelector("#principal");
    P.innerHTML = `<h1>9 · CMIP6</h1><p class="sub" hidden><b>X</b> = condiciones existentes (las válidas, siempre en tonos fríos). <b>Y</b> = escenario CMIP6 de NASA NEX-GDDP (25 km, libre en Earth Engine) con el sesgo corregido contra CHIRPS y la señal de cambio preservada; se muestra en <b style="color:#ff7ac8">magenta degradado</b> y sombreado. CMIP6 se traduce en una <b>tasa de cambio de la lluvia de entrada</b> del modelo.</p><div id="cmBody"></div><div id="cmExt"></div><div id="cmPapers"></div><div id="cmFrontera"></div>`;
    await pintar();
    pintarExtremos(); pintarPapers(); pintarFrontera();
  }
  // ---------------------------------------------------------------- Eta (punto 29i): «Analizar extremos» — no cambia Y ni los factores
  async function pintarExtremos(calcular) {
    const el = document.querySelector("#cmExt"); if (!el || !S.estado.proyecto) return;
    const tit = '<h2>Extremos: años tipo El Niño por década</h2>';
    const intro = '<p>La serie anual del módulo es el <b>promedio de los modelos</b>: muestra la tendencia, pero los años extremos de cada modelo caen en fechas distintas y se cancelan. Esta capa muestra <b>el mejor modelo solo</b> con sus picos, el <b>umbral de año extremo</b> (p90 o p95 del máximo diario anual de CHIRPS 1981–2014) y <b>cuántos años extremos llegan por década</b>. No cambia Y ni los factores; usa lo ya descargado.</p>';
    if (calcular) el.innerHTML = `<section class="tarjeta">${tit}<p class="chip">Analizando…</p></section>`;
    const r = calcular ? await api("/api/cmip6/extremos", {percentil: +((document.querySelector("#cmExtP") || {}).value || 90)}) : await api("/api/cmip6/extremos");
    const ctl = `<div class="fila"><div><label for="cmExtP">Umbral</label><select id="cmExtP"><option value="90">p90 (por defecto)</option><option value="95">p95 (más extremo)</option></select></div><button class="principal" id="cmExtGo">Analizar extremos</button><button id="cmExp" title="Junta en resultados/cmip6_<fecha>/ el histórico y el futuro crudos, la evaluación, los factores, los diagnósticos, los extremos, un LEEME y un Excel">Exportar datos CMIP6 del territorio</button></div><div id="cmExpMsg"></div>`;
    if (r.error) el.innerHTML = `<section class="tarjeta">${tit}${intro}${calcular ? nota(esc(r.error), "pend") : '<p class="chip">Necesita los pasos 1 a 5 (con el futuro descargado).</p>'}${ctl}</section>`;
    else el.innerHTML = `<section class="tarjeta">${tit}${intro}
        <img src="/api/cmip6/extremos.png?t=${Date.now()}" alt="Máximo diario anual y frecuencia de años extremos por década" style="width:100%;max-width:1100px;border-radius:8px;background:#fff">
        <ul>${(r.lectura || []).map(l => `<li>${esc(l)}</li>`).join("")}</ul>
        <p class="chip">${esc(r.aviso)} · carpeta <code>${esc(r.carpeta)}</code></p>${ctl}</section>`;
    const sel = document.querySelector("#cmExtP"); if (sel && r.percentil) sel.value = String(r.percentil);
    const b = document.querySelector("#cmExtGo"); if (b) b.onclick = () => pintarExtremos(true);
    const x = document.querySelector("#cmExp"); if (x) x.onclick = async () => { document.querySelector("#cmExpMsg").innerHTML = '<p class="chip">Juntando archivos…</p>'; const j = await api("/api/cmip6/exportar", {}); document.querySelector("#cmExpMsg").innerHTML = j.error ? nota(esc(j.error), "err") : nota(`Listo: <code>${esc(j.carpeta)}</code> (${j.contenido.length} partes, con LEEME.md y resumen_cmip6.xlsx).`, "ok"); };
  }
  // ---------------------------------------------------------------- CMIP6 experimental: diagnósticos de los papers 1–3, en lenguaje sencillo (no cambian Y)
  async function pintarPapers(recalcular) {
    const el = document.querySelector("#cmPapers"); if (!el || !S.estado.proyecto) return;
    el.innerHTML = '<section class="tarjeta"><h2>CMIP6 experimental · diagnósticos de los papers 1–3</h2><p class="chip">' + (recalcular ? "Calculando (unos segundos)…" : "Leyendo…") + "</p></section>";
    const r = recalcular ? await api("/api/cmip6/papers", {}) : await api("/api/cmip6/papers");
    const boton = '<div class="fila"><button class="principal" id="cmPapCalc">Calcular diagnósticos experimentales</button></div>';
    if (r.error) { el.innerHTML = `<section class="tarjeta"><h2>CMIP6 experimental · diagnósticos de los papers 1–3</h2><p>Se calculan solos al terminar los factores de cambio (paso de abajo), o con el botón. Responde cuatro preguntas: <b>¿cuándo emerge la señal?</b> (con el ruido real, no el de los modelos), <b>¿cuántos modelos independientes hay?</b>, <b>¿la corrección infla el ruido?</b> y <b>¿cuál es la banda del cambio en la lluvia de diseño?</b></p>${boton}${recalcular ? nota(esc(r.error), "pend") : ""}</section>`; }
    else {
      const NE = "no emerge antes de 2100";
      const tabla = (r.toe || []).length ? `<table><thead><tr><th>Índice</th><th>Cambio</th><th class="num">Emerge (ruido modelos)</th><th class="num">Emerge (ruido real · ${esc(r.referencia_texto)})</th><th class="num">Serie media (Jensen)</th><th class="num">Modelos uno a uno (mediana)</th><th class="num">Modelos que emergen solos</th></tr></thead><tbody>${r.toe.map(f => `<tr><td><b>${esc(f.indice)}</b></td><td>${esc(f.signo)}</td><td class="num">${f.toe_ruido_modelos || NE}</td><td class="num"><b>${f.toe_ruido_referencia || NE}</b></td><td class="num">${f.toe_serie_media || "—"}</td><td class="num">${f.toe_mediana_miembros || "—"}</td><td class="num">${f.n_miembros_emergen != null ? f.n_miembros_emergen + " de " + ((r.n_efectivo || {}).n_modelos || "—") : "—"}</td></tr>`).join("")}</tbody></table>` : "";
      const ne = r.n_efectivo || {};
      const novato = `<details open><summary><b>Cómo leer esta tarjeta</b> (para quien empieza)</summary><ul>
        <li><b>Tiempo de emergencia (ToE):</b> el año en que el cambio de la lluvia supera el «ruido» natural de un año a otro. Se mide con el ruido de los modelos y con el ruido real de la referencia. <b>«No emerge» no significa «no hay riesgo»</b>: significa que el cambio todavía se confunde con la variabilidad natural.</li>
        <li><b>Efecto Jensen:</b> la serie promedio de los modelos emerge antes que cada modelo por separado, porque promediar borra su ruido. Por eso se muestran las dos.</li>
        <li><b>Modelos independientes:</b> ${ne.n_modelos || "—"} modelos equivalen a ${ne.n_eff || "—"} modelos independientes en sus errores. ${ne.n_filas ? `Se estimó con <b>${ne.n_filas} filas</b> (climatología mensual): es una estimación débil, tómala como orden de magnitud.` : ""}</li>
        <li><b>Razón de varianza:</b> cuánto varía cada modelo corregido de un año a otro frente a la referencia (ideal 1). Si es menor que 1, los modelos son más «tranquilos» y subestiman los años extremos: mira la tarjeta de extremos.</li>
        <li><b>Banda del factor:</b> el rango p10–p90 del cambio en la lluvia de diseño entre modelos. Reporta la banda, no solo la mediana.</li></ul></details>`;
      el.innerHTML = `<section class="tarjeta"><h2>CMIP6 experimental · diagnósticos de los papers 1–3 <span class="chip">no cambian Y</span></h2>${novato}
        <img src="/api/cmip6/papers.png?t=${Date.now()}" alt="Infografía: emergencia, modelos independientes, varianza y banda del factor de cambio" style="width:100%;max-width:1100px;border-radius:8px;background:#fff">
        <ul>${(r.lectura || []).map(l => `<li>${esc(l.trim().replace(/emerge en ningún año antes de 2100/g, "no emerge antes de 2100"))}</li>`).join("")}</ul>${tabla}
        <p class="chip">${(r.citas || []).map(esc).join(" · ")} · Cálculo: ${esc(r.creado || "")} · carpeta <code>${esc(r.carpeta)}</code></p>${boton}</section>`;
    }
    const b = document.querySelector("#cmPapCalc"); if (b) b.onclick = () => pintarPapers(true);
  }
  // ---------------------------------------------------------------- Zeta: versión de frontera de CMIP6 (método de los papers), EN EVALUACIÓN, frente al método de referencia
  async function pintarFrontera(calcular) {
    const el = document.querySelector("#cmFrontera"); if (!el || !S.estado.proyecto) return;
    const tit = '<h2>CMIP6 · versión de frontera (método de los papers 1–3) <span class="chip">en evaluación</span></h2>';
    el.innerHTML = `<section class="tarjeta">${tit}<p class="chip">${calcular ? "Calculando: evalúa los modelos contra la referencia de los papers y calcula sus factores (puede tardar unos minutos)…" : "Leyendo…"}</p></section>`;
    const cuerpo = {estacion: (document.querySelector("#cmFrEst") || {}).value || null};
    const r = calcular ? await api("/api/cmip6/frontera", cuerpo) : await api("/api/cmip6/frontera");
    const fr = r.frontera, x = v => v == null ? "—" : "×" + num(v, 2), b = v => v ? `${num(v[0], 2)}–${num(v[1], 2)}` : "—";
    const tabla = (r.filas || []).length ? `<table><thead><tr><th>Horizonte</th><th class="num">Referencia (Omega)</th><th class="num">p10–p90</th><th class="num">Frontera (papers)</th><th class="num">p10–p90</th></tr></thead><tbody>${r.filas.map(f => `<tr><td>${esc(f.horizonte)}</td><td class="num">${x(f.referencia_omega)}</td><td class="num">${b(f.referencia_p10_p90)}</td><td class="num" style="color:#d4147f"><b>${x(f.frontera)}</b></td><td class="num">${b(f.frontera_p10_p90)}</td></tr>`).join("")}</tbody></table><p class="chip">Factor sobre la lluvia de diseño Tr 100 (24 h) · SSP5-8.5</p>` : "";
    const toe = fr && (fr.toe_oficial || []).length ? `<table><thead><tr><th>Índice</th><th>Cambio</th><th class="num">Emerge · referencia (ruido de los modelos)</th><th class="num">Emerge · frontera (ruido real, P1)</th></tr></thead><tbody>${fr.toe_oficial.map(f => `<tr><td><b>${esc(f.indice)}</b></td><td>${esc(f.signo || "")}</td><td class="num">${f.toe_metodo_referencia || "no emerge"}</td><td class="num"><b>${f.toe || "no emerge"}</b></td></tr>`).join("")}</tbody></table>` : "";
    const info = fr ? `<p><b>Referencia de la corrección:</b> ${esc(fr.referencia_texto)} · red ${esc(fr.red)}${fr.n_efectivo && fr.n_efectivo.n_eff ? ` · <b>${fr.n_efectivo.n_modelos}</b> modelos equivalen a <b>${fr.n_efectivo.n_eff}</b> independientes (P3)` : ""}${fr.razon_varianza_mediana ? ` · razón de varianza ${num(fr.razon_varianza_mediana, 2)} (ideal 1, P2)` : ""}</p><p class="chip">Cálculo ${esc(fr.creado)} · carpeta <code>${esc(fr.carpeta)}</code></p>` : "<p>Aún no se calcula. Repite la cadena CMIP6 con el método de los papers: con estación y red densa, CHIRPS reescalado mes a mes a la estación (P2); si no, CHIRPS crudo (P3); el ToE se mide con el ruido real (P1).</p>";
    el.innerHTML = `<section class="tarjeta">${tit}
      <div class="nota pend">${esc(r.nota || "Versión de frontera en evaluación: no reemplaza el método de referencia, que es el que usan la IDF y el 2D.")}</div>
      ${info}${tabla}${toe}${calcular && r.error ? nota(esc(r.error), "pend") : ""}
      ${fr && !fr.estacion ? nota("Sin una estación de red densa, la versión de frontera usa la misma referencia (CHIRPS crudo) y coincide con la referencia: su valor aparece cuando hay estaciones con al menos 10 años de 1981–2014 (paper 2).", "") : ""}
      <p class="chip">La estación sirve si tiene al menos 10 años dentro de 1981–2014 y forma parte de una red densa (3 o más estaciones). Una sola estación corta (p. ej. 2014–2026) no sirve: el cálculo cae a CHIRPS crudo.</p>
      <div class="fila"><div class="crece"><label for="cmFrEst">Estación de referencia (opcional; vacío = CHIRPS)</label><input type="text" id="cmFrEst" placeholder="código de una estación del proyecto, p. ej. M0024" value="${E((fr && fr.estacion) || "")}"></div>
      <button class="principal" id="cmFrCalc">Calcular versión de frontera</button></div></section>`;
    const bt = document.querySelector("#cmFrCalc"); if (bt) bt.onclick = () => pintarFrontera(true);
  }
  async function pintar() {
    const body = document.querySelector("#cmBody"); if (!body) return;
    if (!S.estado.proyecto) { body.innerHTML = '<div class="nota pend">Abre un proyecto (por ejemplo Mazar).</div>'; return; }
    const [comp, res, desc, bd] = await Promise.all([api("/api/cmip6/compuerta"), api("/api/cmip6/resultados"), api("/api/descargas"), api("/api/bd/esquema")]);
    const dec = comp.anulacion, an = res.analisis ? res : null, dl = (desc.descargas || []).filter(d => /^cmip6/.test(d.fuente));
    const hist = dl.find(d => d.fuente === "cmip6_historico" && d.estado === "completado"), fut = dl.find(d => d.fuente === "cmip6_futuro" && d.estado === "completado"), corr = dl.find(d => d.estado === "en_curso"), inte = dl.find(d => d.estado === "interrumpida");
    body.innerHTML = `
    <section class="tarjeta"><h2>Pasos</h2>
      <div class="fila">
        <button id="cmH" ${!corr ? "" : "disabled"}>1 · Descargar histórico</button><button id="cmE" ${hist && !corr ? "" : "disabled"}>2 · Evaluar y ordenar modelos</button>
        <button id="cmF" ${an && !corr ? "" : "disabled"}>3 · Descargar futuro de los mejores</button><button id="cmK" ${an && fut && !corr ? "" : "disabled"}>4 · Calcular tasa de cambio</button><button id="cmB" ${an ? "" : "disabled"}>5 · Sincronizar base de datos</button></div>
      <div class="fila"><div class="crece"><label for="cmMod">Modelos (vacío = todos, lo normal)</label><input type="text" id="cmMod" placeholder="Solo para clase: GISS-E2-1-G, MPI-ESM1-2-HR, CanESM5" value="${E(localStorage.getItem("uce_cmip6_modelos") || "")}"></div></div>
      <div class="nota pend" id="cmPed" ${(localStorage.getItem("uce_cmip6_modelos") || "").trim() ? "" : "hidden"}>Ensamble PEDAGÓGICO con pocos modelos: sirve para enseñar el procedimiento; no representa la incertidumbre entre modelos.</div>
      ${inte && !corr ? `<div class="fila"><div class="nota pend">${E(inte.fuente)} se interrumpió en ${Math.round((inte.progreso || 0) * 100)} %. Lo ya bajado se reutiliza.</div><button class="principal" id="cmRe">Reanudar</button></div>` : ""}
      <div id="cmMsg">${corr ? `<div class="nota">Descargando: ${E(corr.fuente)} · ${Math.round((corr.progreso || 0) * 100)} % · ${E(corr.mensaje || "")}</div>` : ""}</div></section>
    <div id="cmRes"></div>`;
    const $$ = s => body.querySelector(s), msg = (t, k) => { $$("#cmMsg").innerHTML = nota(E(t), k || ""); };
    const lanzar = async (fuente, par, txt) => { const j = await api("/api/descargas/iniciar", {fuente, parametros: par}); if (j.error) { msg(j.error, "err"); return; } msg(txt, "ok"); setTimeout(pintar, 2500); };
    const mp = /lon\s*(-?[\d.]+)\D+lat\s*(-?[\d.]+)/.exec((S.estado.proyecto || {}).ubicacion || ""), pt = mp ? {lon: +mp[1], lat: +mp[2]} : null;
    if (!pt) { msg("El proyecto no tiene sitio (lon, lat).", "err"); }
    const elegidos = () => ($$("#cmMod") ? $$("#cmMod").value : "").split(/[,;\s]+/).map(s => s.trim()).filter(Boolean);
    if ($$("#cmMod")) $$("#cmMod").oninput = () => { try { localStorage.setItem("uce_cmip6_modelos", $$("#cmMod").value); } catch (e) {} $$("#cmPed").hidden = !elegidos().length; };
    if ($$("#cmH")) $$("#cmH").onclick = () => { const m = elegidos(); lanzar("cmip6_historico", m.length ? {...pt, modelos: m} : pt, m.length ? `Descargando el histórico 1981–2014 de ${m.length} modelo(s) elegidos (ensamble pedagógico)…` : "Descargando el histórico 1981–2014 de todos los modelos (unos 6 minutos)…"); };
    if ($$("#cmE")) $$("#cmE").onclick = async () => { msg("Evaluando modelos…"); const j = await api("/api/cmip6/evaluar", {referencia: "chirps:celda_nex_mm", k: 5}); if (j.error) msg(j.error, "err"); else { await api("/api/bd/sincronizar", {}); pintar(); } };
    if ($$("#cmF")) $$("#cmF").onclick = () => lanzar("cmip6_futuro", {...pt, modelos: elegidos().length ? elegidos() : Object.keys(an.resumen.pesos), escenarios: ["ssp585"]}, "Descargando el futuro 2015–2100 de los mejores modelos (SSP5-8.5, el extremo)…");
    if ($$("#cmK")) $$("#cmK").onclick = async () => { msg("Calculando factores (QDM)…"); const j = await api("/api/cmip6/factores", {}); if (j.error) msg(j.error, "err"); else { await api("/api/bd/sincronizar", {}); pintar(); } };
    if ($$("#cmB")) $$("#cmB").onclick = async () => { msg("Sincronizando…"); const j = await api("/api/bd/sincronizar", {}); if (j.error) msg(j.error, "err"); else { msg("Base de datos lista: " + Object.entries(j.tablas).map(([k, v]) => k + " " + v).join(" · "), "ok"); pintar(); } };
    if ($$("#cmRe")) $$("#cmRe").onclick = async () => { const j = await api("/api/descargas/reanudar", {id: inte.id}); if (j.error) msg(j.error, "err"); else setTimeout(pintar, 1500); };
    if (corr) { clearTimeout(ST.t); ST.t = setTimeout(pintar, 3000); }
    if (!an) { $$("#cmRes").innerHTML = ""; return; }
    resultados($$("#cmRes"), an, bd);
    $$("#cmRes").insertAdjacentHTML("beforeend", '<div id="cmToe"></div>'); toe($$("#cmToe"));
  }

  function resultados(el, an, bd) {
    const r = an.resumen, g = an.graficas;
    const rk = an.ranking.filter(x => x.estado !== "descartado").slice().sort((a, b) => (a.rmse_clim_mm_mes ?? 1e9) - (b.rmse_clim_mm_mes ?? 1e9)).map((m, i) => ({...m, posicion: i + 1}));
    r.mejor_modelo = rk.length ? rk[0].modelo : r.mejor_modelo;
    el.innerHTML = `
    <section class="tarjeta"><h2>Modelos contra CHIRPS · mejor = RMSE más bajo: ${E(r.mejor_modelo)}</h2>
      
      <div class="tabla-ancha"><table><thead><tr><th>#</th><th>Modelo</th><th class="num">Sesgo total (%)</th><th class="num">RMSE climatología (mm/mes)</th><th class="num">RMSE cuantiles original → QQM (mm, validación)</th><th class="num">RMSE máx. anuales (mm)</th><th class="num">Mejora QQM</th><th class="num">Peso</th></tr></thead><tbody>
      ${rk.slice(0, 14).map(m => `<tr${m.seleccionado ? ' style="background:rgba(108,196,236,.08)"' : ""}><td>${m.posicion}</td><td>${m.posicion === 1 ? "★ " : ""}<b>${E(m.modelo)}</b></td><td class="num">${num(m.bias_total_pct)}</td><td class="num">${num(m.rmse_clim_mm_mes)}</td><td class="num">${num(m.rmse_cuantiles_mm_val_original)} → <b>${num(m.rmse_cuantiles_mm_val_qqm)}</b></td><td class="num">${num(m.rmse_max_anuales_mm)}</td><td class="num" style="color:${m.mejora_qqm_cuantiles_pct > 0 ? C.verde : C.ambar}">${num(m.mejora_qqm_cuantiles_pct, 0)} %</td><td class="num">${m.peso ? num(m.peso * 100, 0) + " %" : "—"}</td></tr>`).join("")}</tbody></table></div>
      </section>
    <section class="tarjeta"><h2>Calidad de los datos y pesos del ensamble</h2>
      <div class="nota ${(r.cobertura && r.cobertura.descartados.length) ? "pend" : "ok"}"><b>Cobertura temporal:</b> ${r.cobertura ? num(r.cobertura.cobertura_efectiva_media_pct, 1) : "—"} % de los días esperados con dato válido (calendario ${r.cobertura ? E(r.cobertura.calendarios.join(", ")) : ""}).
        ${r.cobertura && Object.keys(r.cobertura.anios_excluidos_por_modelo).length ? "Años excluidos por modelo: " + E(JSON.stringify(r.cobertura.anios_excluidos_por_modelo)) : "Ningún año ni mes quedó excluido."}
        ${r.cobertura && r.cobertura.descartados.length ? "<br>Modelos descartados: " + r.cobertura.descartados.map(d => E(d.modelo + " (" + d.motivo + ")")).join("; ") : ""}<br><span class="chip">${r.cobertura ? E(r.cobertura.regla) : ""}</span></div>
      <h3>Pesos ClimWIP por modelo (desempeño × independencia; es la parte histórica, por eso no va en magenta)</h3><div id="gPesos"></div>
      </section>
    <section class="tarjeta"><h2>Validación cruzada impar/par y ensamble por quintiles</h2>
      
      <div class="rejilla"><div><h3>RMSE de cuantiles de días húmedos (mm)</h3><div id="gVC"></div></div><div><h3>RMSE de climatología mensual (mm/mes)</h3><div id="gVM"></div></div></div>
      <h3>Ensamble por quintiles de intensidad (RMSE por quintil, mm; menor es mejor)</h3><div id="gQuint"></div>
      
      <h3>Totales mensuales ordenados (Q-Q, mm/mes) · mejor modelo</h3><div id="gQM" style="max-width:560px"></div></section>
    <section class="tarjeta"><h2>Datos crudos y corregidos (1981–2014)</h2>
      <div class="rejilla"><div><h3>Cuantiles de días húmedos</h3><div id="gQQ"></div></div><div><h3>Climatología mensual (mm/mes)</h3><div id="gCL"></div></div></div>
      <h3>Máximos anuales de 24 h ordenados (mm)</h3><div id="gAM"></div></section>
    <section class="tarjeta"><h2>Serie anual 1981–2100: observado, crudo y corregido</h2>
      <div class="fila"><label class="tog" style="display:flex;gap:6px;align-items:center"><input type="radio" name="cmv" value="tot" checked> total anual</label><label class="tog" style="display:flex;gap:6px;align-items:center"><input type="radio" name="cmv" value="max"> máximo diario anual</label><label class="tog" style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="cmCrudo" checked> mostrar crudo</label></div><div id="gAnual"></div></section>
    <div id="cmFact"></div><div id="cmEsc"></div><div id="cmBD"></div>`;
    pesos(el.querySelector("#gPesos"), g.pesos); valida(el.querySelector("#gVC"), r.rmse_cuantiles_val, "mm"); valida(el.querySelector("#gVM"), r.rmse_clim_val, "mm/mes"); quintiles(el.querySelector("#gQuint"), g.quintiles); qm(el.querySelector("#gQM"), g.qq_mensual);
    qq(el.querySelector("#gQQ"), g.qq_humedos); clima(el.querySelector("#gCL"), g.clim_mensual); amax(el.querySelector("#gAM"), g.max_anuales);
    anual(el);
    factores(el.querySelector("#cmFact"), an); escenarios(el.querySelector("#cmEsc")); basedatos(el.querySelector("#cmBD"), bd);
  }

  const leyenda = items => `<div style="display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:${C.tenue};margin:4px 0">${items.map(([c, t, d]) => `<span><i style="display:inline-block;width:18px;border-top:3px ${d ? "dashed" : "solid"} ${c};vertical-align:3px;margin-right:5px"></i>${t}</span>`).join("")}</div>`;
  function lineas(el, W, H, xs, series, opt) {
    const L = 58, R = 16, T = 28, B = 34, xmin = opt.xmin ?? Math.min(...xs), xmax = opt.xmax ?? Math.max(...xs), vals = series.flatMap(s => s.y.filter(v => v !== null && isFinite(v))), vmax = opt.vmax || nice(Math.max(...vals) * 1.08);
    const x = lin(xmin, xmax, L, W - R), y = lin(0, vmax, H - B, T); let s = marco(W, H) + ejeY(L, W - R, y, vmax, opt.unidad || "mm");
    if (opt.linea11) s += `<line x1="${x(0)}" y1="${y(0)}" x2="${x(vmax)}" y2="${y(vmax)}" stroke="rgba(255,255,255,.25)" stroke-dasharray="4 4"/>`;
    (opt.xticks || []).forEach(t => { s += `<text x="${x(t[0])}" y="${H - B + 16}" text-anchor="middle" font-size="11.5" fill="${C.tenue}">${t[1]}</text>`; });
    series.forEach(se => { const pts = xs.map((a, i) => se.y[i] === null || !isFinite(se.y[i]) ? null : x(a) + "," + y(se.y[i])).filter(Boolean).join(" "); s += `<polyline fill="none" stroke="${se.c}" stroke-width="${se.w || 2}" ${se.d ? 'stroke-dasharray="6 5"' : ""} ${se.glow ? 'filter="url(#brillo)"' : ""} points="${pts}"/>`; });
    el.innerHTML = s + "</svg>";
    const svg = el.querySelector("svg"); hover(svg, W, px => { const v = xmin + (px - L) / (W - L - R) * (xmax - xmin); let k = 0, best = 1e18; xs.forEach((a, i) => { if (Math.abs(a - v) < best) { best = Math.abs(a - v); k = i; } }); return `<b>${opt.fmtX ? opt.fmtX(xs[k]) : nf(xs[k], 1)}</b><br>` + series.map(se => `<span style="color:${se.c}">${E(se.n)}</span> ${nf(se.y[k], 1)}`).join("<br>"); });
  }
  function barrasH(el, items, opt) {            // barras horizontales; items [{n, v, c, extra}]
    const W = opt.W || 1000, fila = 22, H = 20 + items.length * fila + 26, L = opt.L || 210, R = 90, vmax = opt.vmax || nice(Math.max(...items.map(i => i.v)) * 1.1), x = lin(0, vmax, L, W - R); let s = marco(W, H);
    for (let k = 0; k <= 4; k++) { const v = vmax * k / 4; s += `<line x1="${x(v)}" x2="${x(v)}" y1="10" y2="${H - 24}" stroke="${C.reja}"/><text x="${x(v)}" y="${H - 8}" text-anchor="middle" font-size="11.5" fill="${C.tenue}">${nf(v, opt.d ?? 2)}</text>`; }
    items.forEach((it, i) => { const yy = 14 + i * fila; s += `<text x="${L - 8}" y="${yy + 12}" text-anchor="end" font-size="12" fill="#e6edf5">${E(it.n)}</text><rect x="${L}" y="${yy + 2}" width="${Math.max(1, x(it.v) - L)}" height="${fila - 7}" rx="3" fill="${it.c}" opacity=".85"/><text x="${x(it.v) + 6}" y="${yy + 12}" font-size="11.5" fill="${C.tenue}">${it.extra ?? nf(it.v, opt.d ?? 2)}</text>`; });
    el.innerHTML = s + "</svg>";
  }
  function pesos(el, p) {
    const it = Object.entries(p).sort((a, b) => b[1].climwip - a[1].climwip).slice(0, 16).map(([m, v]) => ({n: m, v: v.climwip * 100, c: COL.qqm, extra: nf(v.climwip * 100, 1) + " % (quintil extremo " + nf(v.q5 * 100, 1) + " %)"}));
    barrasH(el, it, {d: 0, L: 170}); }
  function valida(el, v, u) {
    if (!v) { el.innerHTML = ""; return; }
    barrasH(el, [{n: "original NEX", v: v.original, c: COL.orig}, {n: "QQM (este programa)", v: v.qqm, c: COL.qqm}, {n: "EQM (Machala/Gualaquiza)", v: v.eqm_agente, c: COL.ens}].map(i => ({...i, extra: nf(i.v, 2) + " " + u})), {L: 150, d: 1, W: 520}); }
  function quintiles(el, q) {
    if (!q || !q.QMME) { el.innerHTML = ""; return; }
    const W = 1000, H = 280, L = 60, R = 16, T = 24, B = 54, ks = [["EMME", COL.orig], ["WMME", COL.ens], ["QMME", COL.qqm], ["mejor", "#ffd166"]], vmax = nice(Math.max(...ks.flatMap(([k]) => q[k])) * 1.1), y = lin(0, vmax, H - B, T);
    let s = marco(W, H) + ejeY(L, W - R, y, vmax, "mm"); const gw = (W - L - R) / 5;
    q.nombres.forEach((nm, i) => { const x0 = L + i * gw + gw * .12, bw = gw * .76 / 4; ks.forEach(([k, c], j) => { const v = q[k][i]; s += `<rect x="${x0 + j * bw}" y="${y(v)}" width="${bw - 3}" height="${H - B - y(v)}" rx="2" fill="${c}" opacity=".88"/>`; });
      s += `<text x="${L + i * gw + gw / 2}" y="${H - B + 16}" text-anchor="middle" font-size="12" fill="${C.tenue}">${E(nm)}</text>`; });
    el.innerHTML = leyenda(ks.map(([k, c]) => [c, k])) + s + "</svg>"; }
  function qm(el, q) { if (!q) { el.innerHTML = ""; return; } const xs = q.obs; lineas(el, 520, 300, xs, [{n: "CHIRPS", c: COL.obs, y: q.obs, w: 2.4}, {n: "original", c: COL.orig, y: q.original, d: 1}, {n: "QQM impar/par", c: COL.qqm, y: q.qqm_impar_par}, {n: "EQM impar/par", c: COL.ens, y: q.eqm_agente_impar_par, d: 1}],
    {xmin: 0, xmax: Math.max(...xs) * 1.05, vmax: nice(Math.max(...xs, ...q.original) * 1.05), unidad: "modelo (mm/mes)", linea11: true, fmtX: v => "observado " + nf(v, 0) + " mm/mes"}); }
  function qq(el, q) { const xs = q.obs; lineas(el, 520, 300, xs, [{n: "CHIRPS", c: COL.obs, y: q.obs, w: 2.4}, {n: "modelo original", c: COL.orig, y: q.mejor_original, d: 1}, {n: "corregido QQM", c: COL.qqm, y: q.mejor_qqm, glow: 1}, {n: "ensamble corregido", c: COL.ens, y: q.ensamble_qqm, glow: 1}],
    {xmin: 0, xmax: Math.max(...q.obs) * 1.05, vmax: nice(Math.max(...q.obs, ...q.mejor_original, ...q.ensamble_qqm) * 1.05), unidad: "modelo (mm)", linea11: true, fmtX: v => "observado " + nf(v, 1) + " mm", xticks: [0, 10, 20, 30, 40, 50, 60, 80].filter(t => t <= Math.max(...q.obs) * 1.05).map(t => [t, t])});
    // eje X real = cuantil observado: se dibuja modelo vs observado (1:1 = perfecto)
    const svg = el.querySelector("svg"); }
  function clima(el, c) { const W = 520, H = 300, L = 58, R = 12, T = 28, B = 30, M = ["E", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"], vmax = nice(Math.max(...c.obs, ...c.mejor_original) * 1.1), y = lin(0, vmax, H - B, T), x = i => L + (i + .5) * (W - L - R) / 12;
    let s = marco(W, H) + ejeY(L, W - R, y, vmax, "mm/mes"); M.forEach((m, i) => { s += `<text x="${x(i)}" y="${H - B + 16}" text-anchor="middle" font-size="12" fill="${C.tenue}">${m}</text>`; });
    [["orig", c.mejor_original, 1], ["qqm", c.mejor_qqm_impar_par, 0], ["ens", c.ensamble_climwip_qqm, 0], ["obs", c.obs, 0]].forEach(([k, v, d]) => { s += `<polyline fill="none" stroke="${COL[k]}" stroke-width="${k === "obs" ? 2.8 : 2}" ${d ? 'stroke-dasharray="6 5"' : ""} ${k !== "orig" ? 'filter="url(#brillo)"' : ""} points="${v.map((a, i) => x(i) + "," + y(a)).join(" ")}"/>`; });
    el.innerHTML = s + "</svg>"; hover(el.querySelector("svg"), W, px => { const i = Math.floor((px - L) / ((W - L - R) / 12)); if (i < 0 || i > 11) return null; return `<b>${["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"][i]}</b><br>CHIRPS ${nf(c.obs[i], 0)}<br>original ${nf(c.mejor_original[i], 0)}<br>QQM ${nf(c.mejor_qqm[i], 0)}<br>ensamble ${nf(c.ensamble_climwip_qqm[i], 0)}`; }); }
  function amax(el, a) { const n = a.obs.length, xs = a.obs.map((_, i) => i + 1); lineas(el, 1000, 280, xs, [{n: "CHIRPS", c: COL.obs, y: a.obs, w: 2.6}, {n: "modelo original", c: COL.orig, y: a.mejor_original, d: 1}, {n: "corregido QQM", c: COL.qqm, y: a.mejor_qqm, glow: 1}, {n: "ensamble ponderado corregido", c: COL.ens, y: a.ensamble_cuantiles_q5, glow: 1}],
    {unidad: "mm/día", fmtX: v => "puesto " + v + " de " + n + " (de menor a mayor)", xticks: xs.filter(v => v === 1 || v % 5 === 0).map(v => [v, v])}); }

  async function anual(el) {
    const box = el.querySelector("#gAnual"); box.innerHTML = ''; const a = await api("/api/cmip6/anual");
    if (a.error) { box.innerHTML = nota(E(a.error), "err"); return; }
    const dib = () => { const v = el.querySelector('input[name="cmv"]:checked').value, crudo = el.querySelector("#cmCrudo").checked, kc = v === "tot" ? "tot_c" : "max_c", ko = v === "tot" ? "tot_o" : "max_o";
      const W = 1000, H = 360, L = 62, R = 16, T = 28, B = 36, xmin = 1981, xmax = 2100, all = [];
      const E_ = a.escenarios, h = E_.historical, s2 = null, s5 = E_.ssp585; [h, s5].forEach(s => s && ["p90"].forEach(q => (crudo ? [kc, ko] : [kc]).forEach(k => s[k][q].forEach(w => w !== null && all.push(w))))); a.obs[v === "tot" ? "total_mm" : "max_dia_mm"].forEach(w => all.push(w));
      const vmax = nice(Math.max(...all) * 1.05), x = lin(xmin, xmax, L, W - R), y = lin(0, vmax, H - B, T); let s = marco(W, H) + ejeY(L, W - R, y, vmax, v === "tot" ? "mm/año" : "mm/día");
      for (let t = 1990; t <= 2100; t += 10) s += `<text x="${x(t)}" y="${H - B + 16}" text-anchor="middle" font-size="11.5" fill="${C.tenue}">${t}</text>`;
      const banda = (sc, k, c, op) => { if (!sc) return; const an = sc.anios, up = [], lo = []; an.forEach((aa, i) => { if (sc[k].p90[i] !== null) { up.push(x(aa) + "," + y(sc[k].p90[i])); lo.unshift(x(aa) + "," + y(sc[k].p10[i])); } }); if (up.length) s += `<polygon points="${up.join(" ")} ${lo.join(" ")}" fill="${c}" opacity="${op}"/>`; };
      const med = (sc, k, c, w, d) => { if (!sc) return; const pts = sc.anios.map((aa, i) => sc[k].mediana[i] === null ? null : x(aa) + "," + y(sc[k].mediana[i])).filter(Boolean).join(" "); s += `<polyline fill="none" stroke="${c}" stroke-width="${w}" ${d ? 'stroke-dasharray="5 4"' : ""} ${d ? "" : 'filter="url(#brillo)"'} points="${pts}"/>`; };
      if (crudo) { [h, s5].forEach(sc => { banda(sc, ko, COL.orig, 0.13); med(sc, ko, COL.orig, 1.3, 1); }); }
      banda(h, kc, COL.qqm, 0.22); med(h, kc, COL.qqm, 2.2); banda(s5, kc, COL.s585, 0.2); med(s5, kc, COL.s585, 2.2);
      const ob = a.obs; s += `<polyline fill="none" stroke="#fff" stroke-width="2.4" filter="url(#brillo)" points="${ob.anios.map((aa, i) => x(aa) + "," + y(ob[v === "tot" ? "total_mm" : "max_dia_mm"][i])).join(" ")}"/>`;
      s += `<line x1="${x(2014.5)}" x2="${x(2014.5)}" y1="${T}" y2="${H - B}" stroke="rgba(255,255,255,.25)" stroke-dasharray="3 5"/><text x="${x(2014.5) + 5}" y="${T + 12}" font-size="12" fill="${C.tenue}">histórico | proyección</text>`;
      box.innerHTML = leyenda([["#fff", "CHIRPS (observado)"], [COL.orig, "NEX original (crudo)", 1], [COL.qqm, "histórico corregido (mediana de los modelos)"], [COL.s585, "SSP5-8.5 corregido (mediana de los modelos)"]]) + s + "</svg>" +
        '<p class="chip">La línea es la <b>mediana de los modelos</b>: los años de El Niño no coinciden entre modelos y se cancelan, por eso no se ven los picos de CHIRPS. Para ver los extremos de un modelo solo y su frecuencia por década, usa «Analizar extremos» más abajo.</p>';
      hover(box.querySelector("svg"), W, px => { const yr = Math.round(xmin + (px - L) / (W - L - R) * (xmax - xmin)); if (yr < xmin || yr > xmax) return null; const f = (sc, k) => { if (!sc) return "—"; const i = sc.anios.indexOf(yr); return i < 0 || sc[k].mediana[i] === null ? "—" : nf(sc[k].mediana[i], 0) + " (" + nf(sc[k].p10[i], 0) + "–" + nf(sc[k].p90[i], 0) + ")"; };
        const io = a.obs.anios.indexOf(yr); return `<b>${yr}</b>${io >= 0 ? "<br>CHIRPS " + nf(a.obs[v === "tot" ? "total_mm" : "max_dia_mm"][io], 0) : ""}<br>histórico corr. ${f(h, kc)}<br>SSP5-8.5 corr. ${f(s5, kc)}${crudo ? "<br><span style='color:" + C.tenue + "'>crudo hist. " + f(h, ko) + "</span>" : ""}`; }); };
    el.querySelectorAll('input[name="cmv"]').forEach(i => i.addEventListener("change", dib)); el.querySelector("#cmCrudo").addEventListener("change", dib); dib();
  }

  function factores(el, an) {
    const f = an.factores; if (!f) { el.innerHTML = '<section class="tarjeta"><h2>Tasa de cambio de la lluvia (Y frente a X)</h2></section>'; return; }
    const m = f.factores.filter(x => x.metrica === "Tr100 de 24 h" && x.escenario === "ssp585"), W = 1000, H = 70 + 2 * 62, L = 190, R = 40, vals = f.factores.flatMap(x => [x.p10, x.p90]), vmin = Math.min(0.8, ...vals) - 0.02, vmax = Math.max(1.4, ...vals) + 0.03, x = lin(vmin, vmax, L, W - R);
    let s = marco(W, H) + `<line x1="${x(1)}" x2="${x(1)}" y1="26" y2="${H - 30}" stroke="${C.cian}" stroke-width="2"/><text x="${x(1)}" y="18" text-anchor="middle" font-size="12" fill="${C.cian}">X = 1,00 (sin cambio)</text>`;
    for (let t = Math.ceil(vmin * 10) / 10; t <= vmax; t += 0.1) s += `<text x="${x(t)}" y="${H - 12}" text-anchor="middle" font-size="11.5" fill="${C.tenue}">${nf(t, 1)}</text><line x1="${x(t)}" x2="${x(t)}" y1="26" y2="${H - 30}" stroke="${C.reja}"/>`;
    const filas = []; ["ssp585"].forEach(e => ["2040-2069", "2071-2100"].forEach(h => filas.push([e, h])));
    filas.forEach(([e, h], i) => { const yy = 48 + i * 62, c = MAG(e, h === "2071-2100");
      s += `<text x="${L - 14}" y="${yy + 5}" text-anchor="end" font-size="13" fill="#e6edf5">${e === "ssp585" ? "SSP5-8.5" : "SSP2-4.5"} · ${h}</text>`;
      [["QQM/QDM", 0, 1], ["original NEX", 16, 0.4]].forEach(([ver, dy, op]) => { const r = m.find(z => z.escenario === e && z.horizonte === h && z.version === ver); if (!r) return;
        s += `<line x1="${x(r.p10)}" x2="${x(r.p90)}" y1="${yy + dy}" y2="${yy + dy}" stroke="${c}" stroke-width="${ver === "QQM/QDM" ? 9 : 4}" stroke-linecap="round" opacity="${op * 0.55}"/><circle cx="${x(r.mediana_ponderada)}" cy="${yy + dy}" r="${ver === "QQM/QDM" ? 7 : 4}" fill="${c}" opacity="${op}" ${ver === "QQM/QDM" ? 'filter="url(#brillo)"' : ""}/>
          <text x="${x(r.p90) + 10}" y="${yy + dy + 4}" font-size="12" fill="${c}" opacity="${Math.max(op, .7)}">${r.mediana_ponderada >= 1 ? "+" : ""}${nf((r.mediana_ponderada - 1) * 100, 0)} % (${nf((r.p10 - 1) * 100, 0)} a ${(r.p90 >= 1 ? "+" : "") + nf((r.p90 - 1) * 100, 0)})</text>`; }); });
    const VERS = ["QQM/QDM", "QQM/QDM · ensamble de cuantiles", "EQM (método Machala/Gualaquiza)", "original NEX"], ordTr = z => (/^Tr(\d+)/.exec(z.metrica) || [0, 0])[1] * 1;
    const filasTr = pr => f.factores.filter(z => z.escenario === "ssp585" && /^Tr/.test(z.metrica) && pr(z)).sort((a, b) => a.horizonte.localeCompare(b.horizonte) || ordTr(a) - ordTr(b) || VERS.indexOf(a.version) - VERS.indexOf(b.version)).map(z => `<tr${z.version === "QQM/QDM" ? "" : ' style="opacity:.78"'}><td>SSP5-8.5</td><td>${E(z.horizonte)}</td><td>${E(z.metrica)}</td><td>${E(z.version)}</td><td class="num" style="color:#ff4da6"><b>${z.mediana_ponderada >= 1 ? "+" : ""}${nf((z.mediana_ponderada - 1) * 100, 1)} %</b></td><td class="num">${nf((z.p10 - 1) * 100, 1)} a ${nf((z.p90 - 1) * 100, 1)} %</td><td class="num">${z.n_modelos}</td><td class="num">${z.anios_efectivos ?? "—"}</td><td style="font-size:11.5px;color:${C.tenue}">${E(z.estado_estimacion || "")}</td></tr>`).join("");
    const tabla = filasTr(z => z.version.startsWith("QQM/QDM")), tabla2 = filasTr(z => !z.version.startsWith("QQM/QDM"));
    const tot = f.factores.filter(z => z.escenario === "ssp585" && z.metrica === "total anual" && z.version === "QQM/QDM").map(z => `${E(z.horizonte)}: ${z.mediana_ponderada >= 1 ? "+" : ""}${nf((z.mediana_ponderada - 1) * 100, 1)} % (${nf((z.p10 - 1) * 100, 1)} a ${nf((z.p90 - 1) * 100, 1)})`).join(" · ");
    const ver = an.verificacion;
    const pesos_ = (an.resumen && an.resumen.pesos) || {}, malos = (ver || []).filter(v => /QQM/.test(v.version || "") && Math.abs(v.bias_total_pct || 0) > 20 && ((pesos_[v.modelo] || {}).climwip || pesos_[v.modelo] || 0) > 0.15);
    const avisoPeso = malos.length ? nota("⚠ " + malos.map(v => `<b>${E(v.modelo)}</b> pesa ${nf((((pesos_[v.modelo] || {}).climwip) || pesos_[v.modelo]) * 100, 1)} % en el ensamble pero en la verificación 2015–2025 tiene un sesgo de ${nf(v.bias_total_pct, 0)} % aun corregido`).join("; ") + ". Revisa la banda p10–p90 antes de usar la mediana.", "pend") : "";
    el.innerHTML = `<section class="tarjeta"><h2>Tasa de cambio de la lluvia de entrada · Y frente a X</h2><div class="nota pend"><b>Supuesto exploratorio.</b> ${E(f.supuesto_idf || "")}</div>
      <h3>Tr 100 de 24 h: factor (punto = mediana ponderada · barra = rango p10–p90 entre modelos)</h3>${s}</svg>
      <div class="tabla-ancha"><table><thead><tr><th>Escenario</th><th>Horizonte</th><th>Métrica</th><th>Versión</th><th class="num">Cambio (mediana)</th><th class="num">Rango p10–p90 entre modelos</th><th class="num">Modelos</th><th class="num">Años efectivos</th><th>Estado de la estimación</th></tr></thead><tbody>${tabla}</tbody></table></div><details><summary>Versiones comparadoras: método Machala/Gualaquiza (EQM) y producto NEX original</summary><div class="tabla-ancha"><table><thead><tr><th>Escenario</th><th>Horizonte</th><th>Métrica</th><th>Versión</th><th class="num">Cambio (mediana)</th><th class="num">Rango p10–p90 entre modelos</th><th class="num">Modelos</th><th class="num">Años efectivos</th><th>Estado de la estimación</th></tr></thead><tbody>${tabla2}</tbody></table></div></details>
      ${avisoPeso}${ver ? `<h3>Verificación independiente 2015–2025 (datos que la calibración no vio)</h3><div class="tabla-ancha"><table><thead><tr><th>Modelo</th><th>Versión</th><th class="num">Sesgo total (%)</th><th class="num">RMSE climatología</th><th class="num">RMSE cuantiles</th><th class="num">RMSE máx. anuales</th></tr></thead><tbody>${ver.map(v => `<tr><td>${E(v.modelo)}</td><td>${E(v.version)}</td><td class="num">${nf(v.bias_total_pct, 1)}</td><td class="num">${nf(v.rmse_clim_mm_mes, 1)}</td><td class="num">${nf(v.rmse_cuantiles_mm, 1)}</td><td class="num">${nf(v.rmse_max_anuales_mm, 1)}</td></tr>`).join("")}</tbody></table></div>` : ""}</section>`;
    hover(el.querySelector("svg"), W, () => null);
  }

  async function escenarios(el) {
    const d = await api("/api/escenarios/idf"); const cc = (d.escenarios || []).filter(x => x.tipo === "cmip6" && x.ssp === "ssp585");
    if (!cc.length) { el.innerHTML = ""; return; }
    el.innerHTML = `<section class="tarjeta"><h2>Escenarios Y listos para correr en el modelo</h2>
      <div class="fila"><div><label for="ccTr">Período de retorno Tr (años)</label><select id="ccTr">${[2, 5, 10, 25, 50, 100].map(t => `<option ${t === 100 ? "selected" : ""}>${t}</option>`).join("")}</select></div><p class="chip">Una corrida por Tr (100 por defecto). Cada corrida 2D grande tarda horas: lanza una y espera a que termine.</p></div>
      <div class="tabla-ancha"><table><thead><tr><th>Escenario Y</th><th class="num">Cambio de la lluvia</th><th class="num">Factor por Tr (2·5·10·25·50·100)</th><th class="num">Lluvia 24 h (mm)</th><th></th></tr></thead><tbody>${cc.map(x => `<tr><td><b>${E(x.nombre)}</b><br><span class="chip" style="color:#ff9fd8">supuesto exploratorio · IDF no validada</span><br><span class="chip">${E(x.estadistico)} · ${x.n_modelos} modelos</span></td><td class="num">${(x.tasa_cambio_pct >= 0 ? "+" : "") + nf(x.tasa_cambio_pct, 0)} %<br><span class="chip">p10–p90: ${nf(x.rango_pct[0], 0)} a ${nf(x.rango_pct[1], 0)} %</span></td><td class="num" style="font-size:11.5px">${x.factor_por_tr ? Object.values(x.factor_por_tr).map(v => nf(v, 2)).join(" · ") : "—"}</td><td class="num">${nf(x.p24_mm, 0)}</td><td><button data-cc="${E(x.id)}">Correr</button></td></tr>`).join("")}</tbody></table></div><div id="ccMsg"></div></section>`;
    el.querySelectorAll("[data-cc]").forEach(b => b.onclick = async () => { b.disabled = true; const j = await api("/api/corrida/iniciar", {escenario: b.dataset.cc, tr: +(el.querySelector("#ccTr") || {}).value || 100}); el.querySelector("#ccMsg").innerHTML = j.error ? nota(E(j.error), "err") : nota("Corrida lanzada (" + E(j.id) + "). Mira el avance en el panel de actividad; al terminar compárala en «8 · Evaluación».", "ok"); setTimeout(() => b.disabled = false, 4000); });
  }

  async function basedatos(el, bd) {
    const t = (bd && bd.tablas) || [];
    el.innerHTML = `<section class="tarjeta"><h2>Base de datos del proyecto</h2>
      ${t.length ? `<div class="tabla-ancha"><table><thead><tr><th>Tabla</th><th class="num">Filas</th><th>Columnas</th></tr></thead><tbody>${t.map(x => `<tr><td><b>${E(x.tabla)}</b></td><td class="num">${x.filas.toLocaleString("es-EC")}</td><td style="font-size:12px;color:${C.tenue}">${E(x.columnas.join(", "))}</td></tr>`).join("")}</tbody></table></div>` : ''}
      <div class="fila"><div class="crece"><label for="sqlQ">Consulta SQL (SELECT)</label><input type="text" id="sqlQ" value="SELECT modelo, escenario, SUBSTR(fecha,1,4) AS anio, ROUND(SUM(pr_original_mm)) AS crudo_mm, ROUND(SUM(pr_corregida_mm)) AS corregido_mm FROM cmip6_series WHERE modelo = (SELECT modelo FROM cmip6_modelos WHERE posicion=1) AND escenario='ssp585' GROUP BY anio ORDER BY anio LIMIT 12"></div><button id="sqlGo">Consultar</button></div><div id="sqlRes"></div></section>`;
    el.querySelector("#sqlGo").onclick = async () => { const j = await api("/api/bd/consulta", {sql: el.querySelector("#sqlQ").value, max_filas: 200}); el.querySelector("#sqlRes").innerHTML = j.error ? nota(E(j.error), "err") : `<div class="tabla-ancha"><table><thead><tr>${j.columnas.map(c => `<th>${E(c)}</th>`).join("")}</tr></thead><tbody>${j.filas.slice(0, 60).map(f => `<tr>${f.map(v => `<td class="num">${E(v)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`; };
  }

  async function toe(el) {
    const r = await api("/api/cmip6/toe"), t = r.toe;
    el.innerHTML = `<section class="tarjeta"><h2>Time of Emergence (ToE)</h2>
      <div class="fila"><div><label for="toeV">Ventana (años)</label><input type="text" id="toeV" value="${t ? t.meta.ventana_anios : 20}" style="width:70px"></div>
        <div><label for="toeU">Umbrales S/N</label><input type="text" id="toeU" value="${t ? t.meta.umbrales_sn.join(", ") : "1, 2"}" style="width:90px"></div><button class="principal" id="toeGo">Calcular ToE</button></div><div id="toeMsg"></div>
      ${t ? `<h3 style="margin-top:14px">Gráficas principales</h3>
      <p class="chip">Primero, las tres principales en grande: total anual, días secos consecutivos (CDD) y lluvia máxima en 24 h. Después: bondad de la corrección de sesgo (validación cruzada impar/par), ToE por indicador y S/N del ensamble. Clic en una gráfica para verla a tamaño completo.</p>
      <div class="fila"><button id="figGo">Generar o actualizar gráficas principales</button></div><div id="figMsg"></div>
      <div id="figs">${["toe_cabeza_PRCPTOT", "toe_cabeza_CDD", "toe_cabeza_Rx1day", "bondad_qqm", "toe_indicadores", "toe_sn_grande"].map(n => `<a href="/api/cmip6/figura.png?nombre=${n}&t=${Date.now()}" target="_blank"><img class="mapa" alt="${n}" data-fig="${n}" style="width:100%;border-radius:10px;margin:10px 0;background:#fff" src="/api/cmip6/figura.png?nombre=${n}&t=${Date.now()}" onerror="this.style.display='none'"></a>`).join("")}</div>
      ${t.meta.cobertura_temporal && !/^todos/.test(t.meta.cobertura_temporal) ? nota(E(t.meta.cobertura_temporal), "pend") : ""}
      ${t.meta.version_metodo ? `<p class="chip">${E(t.meta.version_metodo)} · base ${t.meta.periodo_base.join("–")} sin tendencia · ruido = interno + entre modelos</p>` : nota("ToE calculado con la versión anterior (mediana de los años de cada modelo): vuelve a calcularlo.", "pend")}
      <table><thead><tr><th>Índice</th><th class="num">S/N ≥</th><th class="num">ToE del ensamble</th><th>Sentido</th><th class="num">Acuerdo de signo (peso)</th><th class="num">Rango de modelos del mismo signo</th></tr></thead><tbody>
      ${t.ensamble.map(f => { const toe = f.toe_ensamble !== undefined ? f.toe_ensamble : f.toe_mediana, ac = f.acuerdo_signo;
        return `<tr><td>${E(f.nombre)}</td><td class="num">${f.umbral_sn}</td><td class="num" style="color:#ff4da6"><b>${toe ?? "no emerge"}</b></td><td>${E(f.signo || f.signo_dominante || "")}</td>
        <td class="num" ${ac != null && ac < 0.66 ? 'style="color:#ffd27a" title="Menos de 2/3 del peso coincide en el signo: sin acuerdo entre modelos"' : ""}>${ac != null ? num(ac * 100, 0) + " %" : "—"}</td><td class="num">${f.toe_p10 != null ? f.toe_p10 + "–" + f.toe_p90 : "—"}</td></tr>`; }).join("")}</tbody></table>
      <img class="mapa" alt="ToE" style="max-width:100%;border-radius:10px;margin-top:8px" src="/api/cmip6/toe.png?t=${Date.now()}">` : ""}</section>`;
    const fg = el.querySelector("#figGo");
    if (fg) fg.onclick = async () => {
      el.querySelector("#figMsg").innerHTML = '<p class="chip">Generando gráficas…</p>';
      const j = await api("/api/cmip6/figuras", {});
      const errs = Object.entries(j).filter(([k, v]) => v && v.error).map(([k, v]) => k + ": " + v.error);
      el.querySelector("#figMsg").innerHTML = j.error ? nota(E(j.error), "err") : (errs.length ? nota(E(errs.join(" · ")), "pend") : (j.bondad_qqm && j.bondad_qqm.rmse_ciclo_crudo_mm != null ? nota(`RMSE del ciclo anual (${E(j.bondad_qqm.modelo)}): crudo ${num(j.bondad_qqm.rmse_ciclo_crudo_mm, 1)} → QQM validado ${num(j.bondad_qqm.rmse_ciclo_qqm_validado_mm, 1)} mm`, "ok") : ""));
      el.querySelectorAll("#figs img").forEach(i => { i.style.display = ""; i.src = `/api/cmip6/figura.png?nombre=${i.dataset.fig}&t=${Date.now()}`; });
    };
    el.querySelector("#toeGo").onclick = async () => {
      el.querySelector("#toeMsg").innerHTML = '<p class="chip">Calculando…</p>';
      const j = await api("/api/cmip6/toe", {ventana: el.querySelector("#toeV").value, umbrales: el.querySelector("#toeU").value.split(/[,;\s]+/).filter(Boolean).map(Number)});
      if (j.error) el.querySelector("#toeMsg").innerHTML = nota(E(j.error), "err"); else { await api("/api/cmip6/figuras", {}); toe(el); }
    };
  }
  VISTAS.cmip6 = vCmip6;
})();
