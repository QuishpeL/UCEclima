/* Series y gráficas (premódulo): barras anuales con tendencia, climatología mensual, hidrograma diario con eventos, hidrograma-hietograma por evento y curva de duración.
   SVG propio, sin librerías. Solo dibuja lo que entrega /api/series/*: no calcula ni corrige nada en el navegador (salvo la media móvil y la recta de Sen que ya vienen del servidor). */
(() => {
  "use strict";
  const NS = "http://www.w3.org/2000/svg";
  const C = {cian: "#6cc4ec", cian2: "#2b86b5", rosa: "#ff2d95", ambar: "#e8b84d", verde: "#7bd88f", texto: "#e6edf5", tenue: "#93a4b8", reja: "rgba(147,164,184,.16)", gris: "#5b6b80"};
  const nf = (v, d = 1) => (v === null || v === undefined || Number.isNaN(v)) ? "—" : Number(v).toLocaleString("es-EC", {minimumFractionDigits: d, maximumFractionDigits: d});
  const E = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
  let tt = null;
  function tip(html, ev) {
    if (!tt) { tt = document.createElement("div"); tt.style.cssText = "position:fixed;z-index:80;pointer-events:none;background:rgba(8,14,24,.96);border:1px solid #2d4058;border-radius:10px;padding:8px 11px;font:13px 'Calibri Light',Calibri,Arial,sans-serif;color:#e6edf5;box-shadow:0 8px 24px rgba(0,0,0,.5);max-width:300px;display:none"; document.body.appendChild(tt); }
    if (!html) { tt.style.display = "none"; return; }
    tt.innerHTML = html; tt.style.display = "block";
    const w = tt.offsetWidth, x = ev.clientX + 16 + w > innerWidth ? ev.clientX - w - 16 : ev.clientX + 16; tt.style.left = x + "px"; tt.style.top = Math.max(8, ev.clientY - 12) + "px";
  }
  const lin = (d0, d1, r0, r1) => v => r0 + (v - d0) / ((d1 - d0) || 1) * (r1 - r0);
  function nice(max) { const p = Math.pow(10, Math.floor(Math.log10(max || 1))), f = max / p; return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * p; }
  function marco(W, H, defs = "") {
    return `<svg viewBox="0 0 ${W} ${H}" role="img" style="width:100%;height:auto;display:block;overflow:visible"><defs>
      <linearGradient id="gA" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="${C.cian}" stop-opacity=".95"/><stop offset="1" stop-color="${C.cian2}" stop-opacity=".35"/></linearGradient>
      <linearGradient id="gQ" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="${C.cian}" stop-opacity=".55"/><stop offset="1" stop-color="${C.cian}" stop-opacity="0"/></linearGradient>
      <linearGradient id="gR" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#9fb4ff" stop-opacity=".95"/><stop offset="1" stop-color="#4a63c9" stop-opacity=".55"/></linearGradient>
      <pattern id="hach" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="6" height="6" fill="rgba(91,107,128,.25)"/><line x1="0" y1="0" x2="0" y2="6" stroke="${C.gris}" stroke-width="2"/></pattern>
      <filter id="brillo" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="2.2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>${defs}</defs>`;
  }
  function ejeY(x0, x1, y, vmax, un, pasos = 4, fmt = v => nf(v, v < 10 ? 1 : 0)) {
    let s = ""; for (let i = 0; i <= pasos; i++) { const v = vmax * i / pasos, yy = y(v); s += `<line x1="${x0}" x2="${x1}" y1="${yy}" y2="${yy}" stroke="${C.reja}"/><text x="${x0 - 8}" y="${yy + 4}" text-anchor="end" font-size="12" fill="${C.tenue}">${fmt(v)}</text>`; }
    return s + `<text x="${x0}" y="11" text-anchor="start" font-size="12" fill="${C.tenue}">${E(un)}</text>`;
  }
  function hover(svg, W, fn) {
    svg.addEventListener("mousemove", ev => { const r = svg.getBoundingClientRect(); const x = (ev.clientX - r.left) / r.width * W; tip(fn(x), ev); });
    svg.addEventListener("mouseleave", () => tip(null));
  }
  const caja = (titulo, sub, cuerpo, id) => `<section class="tarjeta"><h2>${titulo}</h2>${sub ? `<p class="chip">${sub}</p>` : ""}<div id="${id}">${cuerpo || ""}</div></section>`;

  /* ------------------------------------------------------------ 1. barras anuales con tendencia */
  function barrasAnuales(el, r) {
    const W = 1000, H = 330, L = 62, Rm = 20, T = 30, B = 36, n = r.anios.length; if (!n) { el.innerHTML = '<p class="chip">Sin datos.</p>'; return; }
    const vals = r.total_mm.map(v => v || 0), vmax = nice(Math.max(...vals) * 1.12);
    const x = i => L + (i + .5) * (W - L - Rm) / n, bw = Math.max(3, (W - L - Rm) / n * .68), y = lin(0, vmax, H - B, T);
    let s = marco(W, H) + ejeY(L, W - Rm, y, vmax, "mm/año");
    r.anios.forEach((a, i) => { const v = r.total_mm[i]; if (v === null) return; const h = H - B - y(v);
      s += `<rect x="${x(i) - bw / 2}" y="${y(v)}" width="${bw}" height="${h}" rx="2" fill="${r.completo[i] ? "url(#gA)" : "url(#hach)"}" stroke="${r.completo[i] ? "none" : C.gris}" stroke-width="1"/>`;
      if (n <= 24 || a % 5 === 0) s += `<text x="${x(i)}" y="${H - B + 16}" text-anchor="middle" font-size="11.5" fill="${C.tenue}">${a}</text>`; });
    const comp = r.anios.map((a, i) => [a, r.total_mm[i], r.completo[i]]).filter(t => t[2] && t[1] !== null);
    if (r.media_total_mm) s += `<line x1="${L}" x2="${W - Rm}" y1="${y(r.media_total_mm)}" y2="${y(r.media_total_mm)}" stroke="${C.ambar}" stroke-dasharray="6 5" stroke-width="1.4"/><text x="${L + 6}" y="${y(r.media_total_mm) - 6}" text-anchor="start" font-size="12" fill="${C.ambar}">media ${nf(r.media_total_mm, 0)} mm</text>`;
    // media móvil de 5 años (solo años completos)
    const mm = comp.map((t, k) => { const w = comp.slice(Math.max(0, k - 2), k + 3); return [t[0], w.reduce((a, b) => a + b[1], 0) / w.length]; });
    if (mm.length > 4) s += `<polyline fill="none" stroke="#fff" stroke-opacity=".85" stroke-width="2" filter="url(#brillo)" points="${mm.map(t => x(r.anios.indexOf(t[0])) + "," + y(t[1])).join(" ")}"/>`;
    const tt_ = r.tendencia_total;
    if (tt_ && tt_.sen_por_anio !== null && comp.length) {
      const b = (arr => { const s2 = arr.slice().sort((p, q) => p - q), m = s2.length >> 1; return s2.length % 2 ? s2[m] : (s2[m - 1] + s2[m]) / 2; })(comp.map(t => t[1] - tt_.sen_por_anio * t[0]));
      const a0 = comp[0][0], a1 = comp[comp.length - 1][0], sig = tt_.p < 0.05;
      s += `<line x1="${x(r.anios.indexOf(a0))}" y1="${y(b + tt_.sen_por_anio * a0)}" x2="${x(r.anios.indexOf(a1))}" y2="${y(b + tt_.sen_por_anio * a1)}" stroke="${C.rosa}" stroke-width="2.6" ${sig ? "" : 'stroke-dasharray="9 6"'} filter="url(#brillo)"/>`;
    }
    el.innerHTML = s + "</svg>"; const svg = el.querySelector("svg");
    hover(svg, W, px => { const i = Math.round((px - L) / ((W - L - Rm) / n) - .5); if (i < 0 || i >= n) return null; return `<b>${r.anios[i]}</b><br>total ${nf(r.total_mm[i], 0)} mm<br>máx. diario ${nf(r.max_dia_mm[i], 1)} mm<br>días con dato ${r.con_dato[i]}${r.completo[i] ? "" : "<br><span style='color:#e8b84d'>año incompleto: no entra en la tendencia</span>"}`; });
  }
  function tarjetasTend(r) {
    const t = r.tendencia_total, m = r.tendencia_max_dia;
    const f = (x, un) => x && x.sen_por_anio !== null ? `<b style="color:${x.p < 0.05 ? C.rosa : C.texto}">${x.sen_por_anio >= 0 ? "+" : ""}${nf(x.sen_por_anio, 1)} ${un}</b> <span class="chip">p = ${nf(x.p, 2)} · τ = ${nf(x.tau, 2)} · n = ${x.n}</span>${x.p < 0.05 ? "" : ' <span class="chip">no significativa</span>'}` : `<span class="chip">${E(x ? x.aviso : "")}</span>`;
    return `<div class="metricas"><div class="metrica"><div class="v">${nf(r.media_total_mm, 0)} mm</div><div class="k">total anual medio (${r.años_completos} años completos)</div></div>
      <div class="metrica"><div class="v" style="font-size:16px">${f(t, "mm/año")}</div><div class="k">tendencia del total anual (Sen)</div></div>
      <div class="metrica"><div class="v" style="font-size:16px">${f(m, "mm/año")}</div><div class="k">tendencia del máximo diario anual</div></div></div>`;
  }

  /* ------------------------------------------------------------ 2. climatología mensual */
  function climatologia(el, r) {
    const W = 1000, H = 270, L = 62, Rm = 20, T = 30, B = 30, c = r.clima_mensual, M = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];
    const vmax = nice(Math.max(...c.p75.filter(v => v !== null), ...c.media.filter(v => v !== null)) * 1.1), y = lin(0, vmax, H - B, T), bw = (W - L - Rm) / 12;
    let s = marco(W, H) + ejeY(L, W - Rm, y, vmax, "mm/mes");
    c.mes.forEach((m, i) => { const v = c.media[i]; if (v === null) return; const cx = L + (i + .5) * bw;
      s += `<rect x="${cx - bw * .3}" y="${y(v)}" width="${bw * .6}" height="${H - B - y(v)}" rx="3" fill="url(#gR)"/><line x1="${cx}" x2="${cx}" y1="${y(c.p25[i])}" y2="${y(c.p75[i])}" stroke="#fff" stroke-opacity=".8" stroke-width="1.6"/>
        <line x1="${cx - 5}" x2="${cx + 5}" y1="${y(c.p25[i])}" y2="${y(c.p25[i])}" stroke="#fff" stroke-opacity=".8"/><line x1="${cx - 5}" x2="${cx + 5}" y1="${y(c.p75[i])}" y2="${y(c.p75[i])}" stroke="#fff" stroke-opacity=".8"/>
        <text x="${cx}" y="${H - B + 17}" text-anchor="middle" font-size="12" fill="${C.tenue}">${M[i]}</text>`; });
    el.innerHTML = s + "</svg>"; hover(el.querySelector("svg"), W, px => { const i = Math.floor((px - L) / bw); if (i < 0 || i > 11) return null; return `<b>${M[i]}</b><br>media ${nf(c.media[i], 0)} mm<br>rango intercuartil ${nf(c.p25[i], 0)}–${nf(c.p75[i], 0)} mm`; });
  }

  /* ------------------------------------------------------------ 3. hidrograma diario con eventos */
  function hidrograma(el, q, o) {
    const W = 1000, H = 340, L = 62, Rm = 20, T = 30, B = 36, t0 = Date.parse(q.fecha_inicio), DIA = 864e5;
    const d0 = o.desde ? Math.max(0, Math.round((Date.parse(o.desde) - t0) / DIA)) : 0, d1 = o.hasta ? Math.min(q.q.length - 1, Math.round((Date.parse(o.hasta) - t0) / DIA)) : q.q.length - 1;
    const vals = q.q.slice(d0, d1 + 1), vmax = nice(Math.max(...vals.filter(v => v !== null)) * 1.08), log = o.log;
    const yv = log ? (v => Math.log10(Math.max(v, 1))) : (v => v), ymax = log ? Math.ceil(Math.log10(vmax)) : vmax, y = lin(0, ymax, H - B, T), x = lin(d0, d1, L, W - Rm);
    let s = marco(W, H), path = "", abierto = false;
    if (log) for (let e = 0; e <= ymax; e++) s += `<line x1="${L}" x2="${W - Rm}" y1="${y(e)}" y2="${y(e)}" stroke="${C.reja}"/><text x="${L - 8}" y="${y(e) + 4}" text-anchor="end" font-size="12" fill="${C.tenue}">${Math.pow(10, e)}</text>`;
    else s += ejeY(L, W - Rm, y, vmax, "m³/s");
    (q.eventos || []).forEach(e => { const a = Math.round((Date.parse(e.ventana_inicio) - t0) / DIA), b = Math.round((Date.parse(e.ventana_fin) - t0) / DIA); if (b < d0 || a > d1) return;
      const xa = x(Math.max(a, d0)), xb = x(Math.min(b, d1)); s += `<rect x="${xa}" y="${T}" width="${Math.max(2, xb - xa)}" height="${H - B - T}" fill="${e.rol === "validacion" ? C.verde : C.rosa}" opacity=".13"/>`; });
    let d = "", area = "", ini = null, ult = null;
    const cerrar = () => { if (ini !== null) area += `L${x(ult).toFixed(1)} ${H - B} L${x(ini).toFixed(1)} ${H - B} Z `; ini = null; };
    for (let i = d0; i <= d1; i++) { const v = q.q[i]; if (v === null) { abierto = false; cerrar(); continue; } const px = x(i).toFixed(1) + " " + y(yv(v)).toFixed(1); d += (abierto ? "L" : "M") + px; area += (ini === null ? "M" : "L") + px + " "; if (ini === null) ini = i; ult = i; abierto = true; }
    cerrar();
    s += `<path d="${area}" fill="url(#gQ)" stroke="none" opacity=".9"/><path d="${d}" fill="none" stroke="${C.cian}" stroke-width="1.5" filter="url(#brillo)"/>`;
    (q.eventos || []).forEach(e => { const i = Math.round((Date.parse(e.fecha_pico_lluvia) - t0) / DIA); if (i < d0 || i > d1) return; s += `<line x1="${x(i)}" x2="${x(i)}" y1="${T}" y2="${H - B}" stroke="${e.rol === "validacion" ? C.verde : C.rosa}" stroke-width="1.2" opacity=".8"/>`; });
    const anios = []; for (let a = new Date(t0 + d0 * DIA).getUTCFullYear(); a <= new Date(t0 + d1 * DIA).getUTCFullYear(); a++) anios.push(a);
    const paso = Math.ceil(anios.length / 14); anios.forEach((a, k) => { if (k % paso) return; const i = Math.round((Date.UTC(a, 0, 1) - t0) / DIA); if (i >= d0 && i <= d1) s += `<text x="${x(i)}" y="${H - B + 16}" text-anchor="middle" font-size="11.5" fill="${C.tenue}">${a}</text>`; });
    el.innerHTML = s + `<line id="cruz" y1="${T}" y2="${H - B}" stroke="#fff" stroke-opacity=".5" style="display:none"/></svg>`;
    const svg = el.querySelector("svg"), cruz = svg.querySelector("#cruz");
    hover(svg, W, px => { const i = Math.round(d0 + (px - L) / (W - L - Rm) * (d1 - d0)); if (i < d0 || i > d1) { cruz.style.display = "none"; return null; } cruz.style.display = ""; cruz.setAttribute("x1", x(i)); cruz.setAttribute("x2", x(i));
      const f = new Date(t0 + i * DIA).toISOString().slice(0, 10), ev = (q.eventos || []).find(e => e.ventana_inicio <= f && f <= e.ventana_fin);
      return `<b>${f}</b><br>caudal ${nf(q.q[i], 1)} m³/s${ev ? `<br><span style="color:${ev.rol === "validacion" ? C.verde : C.rosa}">evento ${E(ev.evento)} (${E(ev.rol)})</span>` : ""}`; });
  }

  /* ------------------------------------------------------------ 4. evento: hietograma + hidrograma */
  function eventoGraf(el, e) {
    const W = 1000, H = 440, L = 62, Rm = 24, Tt = 22, hH = 120, gap = 34, yQ0 = Tt + hH + gap, B = 40, n = e.fecha.length;
    const x = i => L + (i + .5) * (W - L - Rm) / n, bw = (W - L - Rm) / n * .66;
    const otra0 = Object.values(e.otras || {})[0] || [], pmax = nice(Math.max(...e.lluvia_mm.filter(v => v !== null), ...otra0.filter(v => v !== null), 1) * 1.15), qmax = nice(Math.max(...e.caudal_m3s.filter(v => v !== null), 1) * 1.1);
    const yp = lin(0, pmax, Tt, Tt + hH), yq = lin(0, qmax, H - B, yQ0);
    let s = marco(W, H);
    for (let i = 0; i <= 3; i++) { const v = pmax * i / 3; s += `<line x1="${L}" x2="${W - Rm}" y1="${yp(v)}" y2="${yp(v)}" stroke="${C.reja}"/><text x="${L - 8}" y="${yp(v) + 4}" text-anchor="end" font-size="11.5" fill="${C.tenue}">${nf(v, 0)}</text>`; }
    s += `<text x="${L - 8}" y="10" text-anchor="end" font-size="12" fill="${C.tenue}">mm/día</text>` + ejeY(L, W - Rm, yq, qmax, "m³/s", 4, v => nf(v, v < 10 ? 1 : 0));
    e.lluvia_mm.forEach((v, i) => { if (v === null) return; s += `<rect x="${x(i) - bw / 2}" y="${Tt}" width="${bw}" height="${yp(v) - Tt}" rx="2" fill="url(#gR)"/>`; });
    const otra = Object.values(e.otras || {})[0]; if (otra) otra.forEach((v, i) => { if (v === null || v <= 0) return; s += `<rect x="${x(i) - bw / 2 - 1}" y="${Tt}" width="${bw + 2}" height="${yp(v) - Tt}" rx="2" fill="none" stroke="#fff" stroke-opacity=".6" stroke-dasharray="3 3"/>`; });
    const base = e.meta.Q_base_previo_m3s, pts = e.caudal_m3s.map((v, i) => v === null ? null : [x(i), yq(v)]);
    let d = ""; let ab = false; pts.forEach(p => { if (!p) { ab = false; return; } d += (ab ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1); ab = true; });
    const ip = e.fecha.indexOf(e.meta.fecha_pico_lluvia);
    if (base != null && ip >= 0) { const seg = pts.slice(ip).filter(Boolean); if (seg.length) s += `<path d="M${seg[0][0]} ${yq(base)} ${seg.map(p => `L${p[0]} ${Math.min(p[1], yq(base))}`).join(" ")} L${seg[seg.length - 1][0]} ${yq(base)} Z" fill="${C.rosa}" opacity=".22"/>`; }
    s += `<path d="${d} L${x(n - 1)} ${H - B} L${x(0)} ${H - B} Z" fill="url(#gQ)"/><path d="${d}" fill="none" stroke="${C.cian}" stroke-width="2.2" filter="url(#brillo)"/>`;
    if (base != null) s += `<line x1="${L}" x2="${W - Rm}" y1="${yq(base)}" y2="${yq(base)}" stroke="${C.ambar}" stroke-dasharray="6 5"/><text x="${W - Rm}" y="${yq(base) - 5}" text-anchor="end" font-size="12" fill="${C.ambar}">caudal base previo ${nf(base, 1)} m³/s</text>`;
    if (ip >= 0) s += `<line x1="${x(ip)}" x2="${x(ip)}" y1="${Tt}" y2="${H - B}" stroke="${C.rosa}" stroke-width="1.2" opacity=".8"/><text x="${x(ip) + 5}" y="${Tt + 12}" font-size="12" fill="${C.rosa}">pico de lluvia</text>`;
    e.fecha.forEach((f, i) => { if (n <= 12 || i % Math.ceil(n / 12) === 0) s += `<text x="${x(i)}" y="${H - B + 16}" text-anchor="middle" font-size="11.5" fill="${C.tenue}">${f.slice(5)}</text>`; });
    el.innerHTML = s + "</svg>"; hover(el.querySelector("svg"), W, px => { const i = Math.floor((px - L) / ((W - L - Rm) / n)); if (i < 0 || i >= n) return null; return `<b>${e.fecha[i]}</b><br>lluvia ${nf(e.lluvia_mm[i], 1)} mm${otra ? `<br>CHIRPS píxel ${nf(otra[i], 1)} mm` : ""}<br>caudal ${nf(e.caudal_m3s[i], 1)} m³/s`; });
  }

  /* ------------------------------------------------------------ 5. curva de duración */
  function fdc(el, q) {
    const W = 1000, H = 290, L = 62, Rm = 20, T = 30, B = 34, v = q.fdc, vmax = Math.max(...v), vmin = Math.max(Math.min(...v.filter(a => a > 0)), 0.1);
    const lo = Math.floor(Math.log10(vmin)), hi = Math.ceil(Math.log10(vmax)), y = lin(lo, hi, H - B, T), x = lin(0, 100, L, W - Rm);
    let s = marco(W, H); for (let e = lo; e <= hi; e++) s += `<line x1="${L}" x2="${W - Rm}" y1="${y(e)}" y2="${y(e)}" stroke="${C.reja}"/><text x="${L - 8}" y="${y(e) + 4}" text-anchor="end" font-size="12" fill="${C.tenue}">${Math.pow(10, e)}</text>`;
    for (let p = 0; p <= 100; p += 10) s += `<text x="${x(p)}" y="${H - B + 16}" text-anchor="middle" font-size="11.5" fill="${C.tenue}">${p}</text>`;
    s += `<text x="${W - Rm}" y="${H - 4}" text-anchor="end" font-size="12" fill="${C.tenue}">% del tiempo que se iguala o supera (m³/s, escala log)</text>`;
    const pts = q.fdc_pct.map((p, i) => x(100 - p) + "," + y(Math.log10(Math.max(v[i], 0.1)))).join(" ");
    s += `<polyline fill="none" stroke="${C.ambar}" stroke-width="2.4" filter="url(#brillo)" points="${pts}"/>`;
    el.innerHTML = s + "</svg>"; hover(el.querySelector("svg"), W, px => { const p = Math.round((px - L) / (W - L - Rm) * 100); if (p < 0 || p > 100) return null; return `Se supera el <b>${p} %</b> del tiempo:<br>${nf(v[100 - p], 1)} m³/s`; });
  }

  /* ------------------------------------------------------------ vista */
  // Dibuja barras anuales con tendencia, climatología, hidrograma y curva de duración de las series de un catálogo. `ep` = rutas de la API de donde salen los datos.
  const EP_PROYECTO = {lluvia: "/api/series/lluvia?id=", caudal: "/api/series/caudal?id=", evento: "/api/series/evento?id=", vacio: "Este proyecto aún no tiene series. Descárgalas en «CHIRPS» o «Datos / GEE»."};
  function montarSeries(body, cat, ep) {
    const lluv = cat.series.filter(s => s.tipo === "lluvia"), cau = cat.series.filter(s => s.tipo === "caudal");
    if (!lluv.length && !cau.length) { body.innerHTML = '<div class="nota pend">' + E(ep.vacio || "Aún no hay series.") + '</div>'; return; }
    body.innerHTML = `<section class="tarjeta"><div class="fila">
      <div><label for="serL">Serie de lluvia</label><select id="serL">${lluv.map(s => `<option value="${E(s.id)}">${E(s.nombre)} · ${s.inicio.slice(0, 4)}–${(s.fin || "").slice(0, 4)}</option>`).join("") || "<option value=''>— ninguna —</option>"}</select></div>
      <div><label for="serQ">Serie de caudal</label><select id="serQ">${cau.map(s => `<option value="${E(s.id)}">${E(s.nombre)}</option>`).join("") || "<option value=''>— ninguna —</option>"}</select></div></div></section><div id="serL1"></div><div id="serQ1"></div>`;
    const pintarLluvia = async () => {
      const id = body.querySelector("#serL").value; const cont = body.querySelector("#serL1"); if (!id) { cont.innerHTML = ""; return; }
      cont.innerHTML = '<p class="chip">Calculando…</p>'; const r = await api(ep.lluvia + encodeURIComponent(id));
      if (r.error) { cont.innerHTML = `<div class="nota err">${E(r.error)}</div>`; return; }
      cont.innerHTML = caja("Lluvia anual y tendencia", E(r.nota) + ' · línea blanca: media móvil de 5 años · línea rosa: pendiente de Sen (discontinua si no es significativa)', tarjetasTend(r) + '<div id="cA" style="margin-top:10px"></div>', "bxA") +
        caja("Climatología mensual", "Media de cada mes con su rango intercuartil (años con al menos 20 días de dato en el mes).", "", "bxB");
      barrasAnuales(cont.querySelector("#cA"), r); climatologia(cont.querySelector("#bxB"), r);
    };
    const pintarCaudal = async () => {
      const id = body.querySelector("#serQ").value; const cont = body.querySelector("#serQ1"); if (!id) { cont.innerHTML = ""; return; }
      cont.innerHTML = '<p class="chip">Cargando hidrograma…</p>'; const q = await api(ep.caudal + encodeURIComponent(id));
      if (q.error) { cont.innerHTML = `<div class="nota err">${E(q.error)}</div>`; return; }
      const fi = q.fecha_inicio, ff = new Date(Date.parse(fi) + (q.q.length - 1) * 864e5).toISOString().slice(0, 10);
      cont.innerHTML = caja("Hidrograma diario", `${E(q.nota)} Bandas: ventana de cada evento (rosa = calibración, verde = validación). ${q.sospechosos.length ? `<span style="color:${C.ambar}">Días anulados por pico absurdo: ${q.sospechosos.map(E).join(", ")}.</span>` : ""}`,
        `<div class="metricas" style="margin-bottom:10px"><div class="metrica"><div class="v">${nf(q.media, 1)}</div><div class="k">media m³/s</div></div><div class="metrica"><div class="v">${nf(q.mediana, 1)}</div><div class="k">mediana</div></div><div class="metrica"><div class="v">${nf(q.p95, 0)}</div><div class="k">percentil 95</div></div><div class="metrica"><div class="v">${nf(q.max, 0)}</div><div class="k">máximo (sin días anulados)</div></div></div>
         <div class="fila"><div><label for="hDes">Desde</label><input type="text" id="hDes" value="${fi}" style="width:130px"></div><div><label for="hHas">Hasta</label><input type="text" id="hHas" value="${ff}" style="width:130px"></div><label class="tog" style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="hLog"> escala logarítmica</label></div><div id="cH" style="margin-top:8px"></div>`, "bxH") +
        caja("Curva de duración de caudales", "Qué porcentaje del tiempo se iguala o supera cada caudal (sin los días anulados).", "", "bxF") +
        (q.eventos.length ? caja("Hidrograma y hietograma de un evento", "Lluvia (barras, arriba), caudal diario (abajo). El área rosa es el volumen directo sobre el caudal base previo; el contorno punteado blanco es CHIRPS del píxel (la barra azul es la media de la caja).",
          `<div class="fila"><div><label for="evSel">Evento</label><select id="evSel">${q.eventos.map(e => `<option value="${E(e.evento)}">${E(e.evento)} · ${E(e.fecha_pico_lluvia)} · ${E(e.rol)} · ΔQ ${nf(e.dQ_m3s, 0)} m³/s</option>`).join("")}</select></div></div><div id="cE" style="margin-top:8px"></div>`, "bxE") : "");
      const redib = () => hidrograma(cont.querySelector("#cH"), q, {desde: cont.querySelector("#hDes").value.trim(), hasta: cont.querySelector("#hHas").value.trim(), log: cont.querySelector("#hLog").checked});
      redib(); ["#hDes", "#hHas", "#hLog"].forEach(s => cont.querySelector(s).addEventListener("change", redib)); fdc(cont.querySelector("#bxF"), q);
      if (q.eventos.length) { const ev = async () => { const e = await api(ep.evento + encodeURIComponent(cont.querySelector("#evSel").value)); if (!e.error) eventoGraf(cont.querySelector("#cE"), e); }; cont.querySelector("#evSel").addEventListener("change", ev); ev(); }
    };
    body.querySelector("#serL").addEventListener("change", pintarLluvia); body.querySelector("#serQ").addEventListener("change", pintarCaudal);
    pintarLluvia(); pintarCaudal();
  }
  async function vSeries() {
    const P = document.querySelector("#principal");
    P.innerHTML = `<h1>Series y gráficas</h1><p class="sub"><b>Barras anuales con tendencia</b>, climatología e <b>hidrogramas</b> de lo que hay en el proyecto. Los años incompletos se dibujan aparte y no entran en la tendencia; nada se rellena.</p><div id="serBody"></div>`;
    const body = P.querySelector("#serBody");
    const cat = await api("/api/series/catalogo");
    if (cat.error) { body.innerHTML = `<div class="nota err">${E(cat.error)}</div>`; return; }
    montarSeries(body, cat, EP_PROYECTO);
  }
  window.GRAF = {C, nf, E, tip, lin, nice, marco, ejeY, hover, caja};
  window.SERIES = {montar: montarSeries, EP_PROYECTO};
  VISTAS.series = vSeries;
})();
