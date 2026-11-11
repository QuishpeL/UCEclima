/* Comparación de escenarios de lluvia de diseño. SIEMPRE: X = condiciones existentes (IDF oficial, tonos fríos, el principal en cian) y Y = CMIP6 cambio climático (tonos cálidos, sombreados como «fantasmas»).
   Y es la lluvia de DISEÑO de entrada multiplicada por la tasa de cambio de CMIP6; el modelo hidráulico es el mismo. Ninguno está calibrado. */
(() => {
  "use strict";
  const COL_X = {directa: "#6cc4ec", observado: "#9fb4ff", chirps: "#7bd88f", escalada: "#93a4b8"};   // X: tonos fríos
const MAG = (ssp, fin) => ssp === "ssp585" ? (fin ? "#d4147f" : "#ff4da6") : (fin ? "#f05cc0" : "#ff9fd8");   // cambio climático = magenta (degradado); lo demás nunca usa magenta
  const colY = id => { const m = /^cc_(ssp\d+)_(\d{4})-(\d{4})/.exec(id) || []; return MAG(m[1], m[3] === "2100"); };
  const col = id => id.startsWith("cc_") ? colY(id) : (COL_X[id] || "#93a4b8");
  const nf = (v, d = 1) => (v === null || v === undefined || Number.isNaN(v)) ? "—" : Number(v).toLocaleString("es-EC", {minimumFractionDigits: d, maximumFractionDigits: d});
  const sg = v => (v >= 0 ? "+" : "") + nf(v, 0) + " %";
  const E = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
  window.ESC_COLORES = {col};                                           // el visor 3D usa la misma paleta
  const previa = VISTAS.evaluacion;
  VISTAS.evaluacion = async function () { await previa(); try { await comparacion(); } catch (e) { console.error(e); } };

  async function comparacion() {
    const est = await api("/api/estado");
    const runs = (est.corridas || []).filter(c => c.estado === "completado" && c.escenario_id);
    if (runs.length < 2) return;
    const porEsc = {}; runs.forEach(r => { if (!porEsc[r.escenario_id]) porEsc[r.escenario_id] = r; });          // la corrida más reciente de cada escenario
    const defsR = await api("/api/escenarios/idf"), defs = defsR.escenarios || [];
    const ordenX = ["directa", "observado", "chirps", "escalada"], ids = Object.keys(porEsc).filter(k => !k.startsWith("cc_") || k.startsWith("cc_ssp585"));          // Y: solo SSP5-8.5 (el extremo)
    const idsX = ordenX.filter(k => porEsc[k]), idsY = ids.filter(k => k.startsWith("cc_")).sort();
    const datos = await Promise.all(idsX.concat(idsY).map(async k => { const r = porEsc[k], res = await api("/api/corrida/resultado?id=" + r.id), h = await api("/api/corrida/hietograma?id=" + r.id); return {k, y: k.startsWith("cc_"), r, res, h, d: defs.find(x => x.id === k) || {nombre: r.escenario || k}}; }));
    const X = datos.find(d => d.k === "directa") || datos.find(d => !d.y); if (!X) return;
    const Y = datos.filter(d => d.y), OtrosX = datos.filter(d => !d.y && d !== X);
    const a03 = d => (d.res.resumen || {})["area_ge_0.3_km2"], pT = d => (d.res.resumen || {}).P_total_mm, vol = d => ((d.res.evaluacion || {}).volumen_disponible_m3);
    const dot = (c, dash) => `<span style="display:inline-block;width:11px;height:11px;border-radius:3px;background:${c};margin-right:7px;box-shadow:0 0 8px ${c};${dash ? "opacity:.75" : ""}"></span>`;
    const fila = d => { const rel = (a03(d) / a03(X) - 1) * 100, lluv = (pT(d) / pT(X) - 1) * 100;
      return `<tr><td>${dot(col(d.k), d.y)}<b>${E(d.d.nombre || d.k)}</b>${d.y ? ` <span class="chip">${E(d.d.estadistico === "mediana" ? "ensamble" : d.d.estadistico === "mejor" ? "mejor modelo" : "ensamble " + (d.d.estadistico || ""))}</span>` : ""}</td><td class="num">${nf(d.d.p24_mm, 0)}</td><td class="num">${nf(pT(d), 1)}</td>
        <td class="num">${d === X ? "—" : `<b style="color:${d.y ? col(d.k) : "inherit"}">${sg(lluv)}</b>${d.y && d.d.rango_pct ? `<br><span class="chip">rango p10–p90 del factor: ${sg(d.d.rango_pct[0])} a ${sg(d.d.rango_pct[1])}</span>` : ""}`}</td>
        <td class="num"><b>${nf(a03(d), 3)}</b></td><td class="num">${d === X ? "—" : `<b style="color:${d.y ? col(d.k) : "inherit"}">${sg(rel)}</b>`}</td><td class="num">${nf(vol(d) / 1000, 0)}</td></tr>`; };
    const cab = '<thead><tr><th>Escenario</th><th class="num">Lluvia 24 h (mm)</th><th class="num">Lluvia de la tormenta (mm)</th><th class="num">Cambio de la lluvia de entrada</th><th class="num">Área con calado ≥ 0,3 m (km²)</th><th class="num">Cambio del área vs X</th><th class="num">Escorrentía (mil m³)</th></tr></thead>';
    // ---- lluvia acumulada: X sólida, Y con la diferencia sombreada
    const W = 900, Hh = 270, L = 56, Rm = 70, T = 26, Bm = 32, tmax = Math.max(...datos.map(d => d.h.fin_s[d.h.fin_s.length - 1])), acum = d => { let c = 0; return d.h.lluvia_mm.map(v => (c += v)); };
    const pmax = Math.max(...datos.map(d => acum(d)[d.h.lluvia_mm.length - 1])) * 1.12, x = t => L + t / tmax * (W - L - Rm), y = p => Hh - Bm - p / pmax * (Hh - Bm - T);
    const curva = d => { const c = acum(d); return [[0, 0]].concat(d.h.fin_s.map((t, i) => [t, c[i]])); };
    const cX = curva(X); let g = "";
    for (let i = 0; i <= 4; i++) { const v = pmax * i / 4; g += `<line x1="${L}" x2="${W - Rm}" y1="${y(v)}" y2="${y(v)}" stroke="rgba(147,164,184,.16)"/><text x="${L - 8}" y="${y(v) + 4}" text-anchor="end" font-size="12" fill="#93a4b8">${nf(v, 0)}</text>`; }
    for (let m = 0; m <= tmax / 3600; m += 0.5) g += `<text x="${x(m * 3600)}" y="${Hh - Bm + 16}" text-anchor="middle" font-size="11.5" fill="#93a4b8">${m} h</text>`;
    const defsG = Y.map((d, i) => `<linearGradient id="gy${i}" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="${col(d.k)}" stop-opacity=".55"/><stop offset="1" stop-color="${col(d.k)}" stop-opacity=".05"/></linearGradient>`).join("");
    Y.forEach((d, i) => { const cY = curva(d), top = cY.map(p => x(p[0]) + "," + y(p[1])).join(" "), base = cX.slice().reverse().map(p => x(p[0]) + "," + y(Math.min(p[1], pmax))).join(" ");
      g += `<polygon points="${top} ${base}" fill="url(#gy${i})"/><polyline fill="none" stroke="${col(d.k)}" stroke-width="1.8" ${d.d.estadistico === "mediana" ? "" : 'stroke-dasharray="6 5"'} opacity=".95" points="${top}"/>`; });
    OtrosX.forEach(d => { g += `<polyline fill="none" stroke="${col(d.k)}" stroke-width="1.4" stroke-dasharray="3 5" opacity=".7" points="${curva(d).map(p => x(p[0]) + "," + y(p[1])).join(" ")}"/>`; });
    g += `<polyline fill="none" stroke="${col(X.k)}" stroke-width="3.4" filter="url(#brilloE)" points="${cX.map(p => x(p[0]) + "," + y(p[1])).join(" ")}"/>`;
    const etq = datos.map(d => ({d, v: acum(d)[d.h.lluvia_mm.length - 1]})).sort((p, q) => q.v - p.v); let ult = -1e9;
    etq.forEach(f => { let yy = y(f.v) + 4; if (yy < ult + 15) yy = ult + 15; ult = yy; g += `<text x="${W - Rm + 8}" y="${yy}" font-size="12" fill="${col(f.d.k)}">${nf(f.v, 0)} mm${f.d === X ? " · X" : f.d.y ? " · Y" : ""}</text>`; });
    const svgLluvia = `<svg viewBox="0 0 ${W} ${Hh}" style="width:100%;height:auto"><defs>${defsG}<filter id="brilloE" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
      <pattern id="hy" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="7" stroke="#fff" stroke-opacity=".5" stroke-width="2"/></pattern></defs><text x="${L}" y="14" font-size="12" fill="#93a4b8">lluvia acumulada de la tormenta de diseño (mm) · sombreado = lo que añade CMIP6 sobre X</text>${g}</svg>`;
    // ---- barras de área: X sólido; Y = base tenue + incremento rayado
    const todos = [X].concat(Y, OtrosX), amax = Math.max(...todos.map(a03)) * 1.2, BW = W - 360, bx = 320;
    const barras = todos.map((d, i) => { const yy = 12 + i * 38, wX = a03(X) / amax * BW, wD = a03(d) / amax * BW, c = col(d.k), etiq = E((d.d.nombre || d.k).replace(/ \(.*/, "").slice(0, 40));
      let s = `<text x="10" y="${yy + 19}" font-size="13" fill="#e6edf5">${(d === X ? "X · " : d.y ? "Y · " : "") + etiq}</text>`, finX = bx + Math.max(wD, wX);
      if (d === X || !d.y) s += `<rect x="${bx}" y="${yy}" width="${wD}" height="26" rx="5" fill="${c}" opacity="${d === X ? 0.95 : 0.5}"/>`;
      else { const base = Math.min(wD, wX); s += `<rect x="${bx}" y="${yy}" width="${base}" height="26" rx="5" fill="${col(X.k)}" opacity=".45"/>`;
        if (wD > wX) s += `<rect x="${bx + wX}" y="${yy}" width="${wD - wX}" height="26" rx="5" fill="${c}" opacity=".85"/><rect x="${bx + wX}" y="${yy}" width="${wD - wX}" height="26" rx="5" fill="url(#hy)"/>`; }
      if (d.y && d.d.estadistico === "mediana") { const gr = Y.filter(z => z.d.ssp === d.d.ssp && z.d.horizonte === d.d.horizonte), lo = gr.find(z => z.d.estadistico === "p10"), hi = gr.find(z => z.d.estadistico === "p90");
        if (lo || hi) { const x1 = bx + (lo ? a03(lo) : a03(d)) / amax * BW, x2 = bx + (hi ? a03(hi) : a03(d)) / amax * BW; finX = Math.max(finX, x2); s += `<line x1="${x1}" x2="${x2}" y1="${yy + 13}" y2="${yy + 13}" stroke="#fff" stroke-opacity=".85" stroke-width="2"/><line x1="${x1}" x2="${x1}" y1="${yy + 6}" y2="${yy + 20}" stroke="#fff" stroke-opacity=".85" stroke-width="2"/><line x1="${x2}" x2="${x2}" y1="${yy + 6}" y2="${yy + 20}" stroke="#fff" stroke-opacity=".85" stroke-width="2"/>`; } }
      return s + `<text x="${finX + 8}" y="${yy + 18}" font-size="13" fill="#e6edf5">${nf(a03(d), 3)} km²${d === X ? "" : " <tspan fill='" + c + "'>" + sg((a03(d) / a03(X) - 1) * 100) + "</tspan>"}</text>`; }).join("");
    const svgBarras = `<svg viewBox="0 0 ${W} ${todos.length * 38 + 20}" style="width:100%;height:auto"><defs><pattern id="hy" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="7" stroke="#fff" stroke-opacity=".5" stroke-width="2"/></pattern></defs>${barras}</svg>`;
    // ---- tasa de cambio de la lluvia de entrada (rango CMIP6)
    const tasa = Y.length ? `<h3>Tasa de cambio de la lluvia de entrada (CMIP6)</h3><p class="chip">Es el factor que multiplica la IDF de X para obtener Y: mediana del ensamble ponderado y rango entre modelos (p10–p90) de la lluvia de 24 h de Tr 100, ya corregida por sesgo (QQM) con preservación de la señal (QDM). El hietograma de Y conserva la forma de X.</p>` : "";
    const sec = document.createElement("section"); sec.className = "tarjeta";
    sec.innerHTML = `<h2>Comparar escenarios: X condiciones existentes · Y CMIP6</h2><p class="chip"><b>X</b> = IDF oficial del INAMHI (los tonos fríos; en cian el principal). <b>Y</b> = la misma lluvia de diseño con la tasa de cambio de CMIP6 (tonos cálidos, sombreados). Tr 100, misma tormenta, mismo terreno, CN y Manning. <b>Ninguno está calibrado ni validado.</b>
      ${Y.length ? "Y es una proyección bajo un supuesto de línea base decidido por el usuario." : ""}</p>
      <div class="tabla-ancha"><table>${cab}<tbody><tr><td colspan="7" style="background:rgba(108,196,236,.07)"><b>X · condiciones existentes</b></td></tr>${[X].concat(OtrosX).map(fila).join("")}${Y.length ? `<tr><td colspan="7" style="background:linear-gradient(90deg,rgba(255,45,149,.16),rgba(255,45,149,.03))"><b style="color:#ff7ac8">Y · CMIP6 cambio climático</b></td></tr>${Y.map(fila).join("")}` : ""}</tbody></table></div>
      ${tasa}<h3>Lluvia de diseño acumulada</h3>${svgLluvia}<h3>Área con calado ≥ 0,3 m · el rayado magenta es el incremento sobre X · la barra blanca es el rango del ensamble (p10–p90)</h3>${svgBarras}
      <p class="chip">Sobre el terreno: abre «Visor 3D de resultados» y marca los escenarios en «Fantasmas» (X y Y).</p>`;
    document.querySelector("#principal").appendChild(sec);
  }
})();
