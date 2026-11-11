/* ★ Mapa 2D tipo RAS (Zeta) — planta del calado máximo: X = condiciones existentes (azules), Y = cambio climático CMIP6 (magentas) y la diferencia Y − X.
   Usa las mismas capas que el visor 3D (/api/visor/datos y /api/visor/capa). Terreno sombreado de fondo, ríos, escala, norte, lectura de celda y exportar PNG.
   Resultados no calibrados ni validados: el calado es el máximo del modelo, no una huella observada. */
(() => {
  "use strict";
  const ST = {x: null, y: null, vista: "d", umbral: 0.3, D: null, Y: null, vias: true, riosOsm: true, riosRed: false};   // Eta: abre en «Diferencia Y − X» con 0,3 m
  const esY = c => /_cc_/.test(c.id) || (c.escenario && /cc_/.test(c.escenario.id || c.escenario));
  const rampa = (stops, t) => { t = Math.max(0, Math.min(1, t)); const n = stops.length - 1, i = Math.min(n - 1, Math.floor(t * n)), f = t * n - i, a = stops[i], b = stops[i + 1]; return [0, 1, 2].map(k => Math.round(a[k] + (b[k] - a[k]) * f)); };
  const AZUL = [[198, 233, 250], [107, 190, 235], [30, 120, 200], [10, 55, 140], [5, 25, 80]];
  const MAG = [[255, 214, 236], [255, 140, 200], [230, 40, 140], [160, 10, 95], [90, 0, 55]];
  const DIV = [[30, 90, 190], [140, 185, 235], [245, 245, 245], [245, 140, 200], [190, 10, 110]];

  async function vMapa2d() {
    const P = document.querySelector("#principal");
    P.innerHTML = encabezado("★ Mapa 2D tipo RAS · X vs Y", "Planta del <b>calado máximo</b> como en RAS Mapper: <b style='color:#6cc4ec'>X = condiciones existentes</b> (azules), <b style='color:#ff4da6'>Y = cambio climático CMIP6</b> (magentas) y la <b>diferencia Y − X</b> (dónde el agua sube o baja). Pasa el cursor para leer una celda. Resultados sin calibrar ni validar: no es una huella de inundación observada.") + '<div id="m2Body"></div>';
    if (!S.estado.proyecto) { P.querySelector("#m2Body").innerHTML = nota("Abre un proyecto con corridas completadas.", "pend"); return; }
    await cargarEstado();
    const corr = (S.estado.corridas || []).filter(c => c.estado === "completado"), X = corr.filter(c => !esY(c)), Y = corr.filter(esY);
    if (!corr.length) { P.querySelector("#m2Body").innerHTML = nota("Este proyecto aún no tiene corridas completadas (módulo 7).", "pend"); return; }
    ST.x = ST.x && X.some(c => c.id === ST.x) ? ST.x : (X[0] || corr[0]).id; ST.y = ST.y && Y.some(c => c.id === ST.y) ? ST.y : (Y[0] ? Y[0].id : "");
    const opt = (l, sel) => l.map(c => `<option value="${esc(c.id)}" ${c.id === sel ? "selected" : ""}>${esc(c.id.replace(/^corrida_/, ""))}</option>`).join("");
    P.querySelector("#m2Body").innerHTML = `<section class="tarjeta"><div class="fila" style="flex-wrap:wrap;gap:12px">
      <div><label for="m2X">X · condiciones existentes</label><select id="m2X">${opt(X.length ? X : corr, ST.x)}</select></div>
      <div><label for="m2Y">Y · cambio climático (CMIP6)</label><select id="m2Y"><option value="">— sin Y —</option>${opt(Y, ST.y)}</select></div>
      <div><label for="m2V">Ver</label><select id="m2V"><option value="x">X: calado actual</option><option value="y">Y: calado con cambio climático</option><option value="d">Diferencia Y − X</option></select></div>
      <div><label for="m2U">Calado mínimo (m)</label><input type="text" id="m2U" value="${ST.umbral}" style="width:70px"></div>
      <button id="m2Png">Exportar PNG</button></div>
      <div class="fila" style="flex-wrap:wrap;gap:14px;margin-top:6px">
       <label class="tog"><input type="checkbox" id="m2Vias" ${ST.vias ? "checked" : ""}> Vías (OpenStreetMap)</label>
       <label class="tog"><input type="checkbox" id="m2RiosO" ${ST.riosOsm ? "checked" : ""}> Ríos y esteros (OpenStreetMap)</label>
       <label class="tog" title="HydroSHEDS/GEOGLOWS son redes gruesas: sirven para la cuenca y el orden de magnitud del caudal, no para ubicar el cauce"><input type="checkbox" id="m2RiosR" ${ST.riosRed ? "checked" : ""}> Red HydroSHEDS (aproximada, ±1 km)</label></div>
      <div style="position:relative;margin-top:10px"><canvas id="m2C" style="width:100%;max-width:1100px;border-radius:8px;background:#0b1622;cursor:crosshair"></canvas>
      <div id="m2Lee" class="chip" style="position:absolute;left:10px;top:10px;background:rgba(10,20,30,.8);padding:6px 10px;display:none"></div></div>
      <div id="m2Ley" style="margin-top:8px"></div><div id="m2Est"></div></section>`;
    document.querySelector("#m2V").value = ST.vista;
    const q = s => document.querySelector(s);
    q("#m2X").onchange = async e => { ST.x = e.target.value; await cargar(); };
    q("#m2Y").onchange = async e => { ST.y = e.target.value; await cargar(); };
    q("#m2V").onchange = e => { ST.vista = e.target.value; dibujar(); };
    q("#m2U").onchange = e => { ST.umbral = Math.max(0, parseFloat(String(e.target.value).replace(",", ".")) || 0); dibujar(); };
    q("#m2Vias").onchange = e => { ST.vias = e.target.checked; dibujar(); }; q("#m2RiosO").onchange = e => { ST.riosOsm = e.target.checked; dibujar(); }; q("#m2RiosR").onchange = e => { ST.riosRed = e.target.checked; dibujar(); };
    q("#m2Png").onclick = () => { const a = document.createElement("a"); a.download = `mapa2d_${ST.vista}_${(ST.vista === "x" ? ST.x : ST.y) || ST.x}.png`; a.href = q("#m2C").toDataURL("image/png"); a.click(); };
    await cargar();
  }

  async function cargar() {
    const q = s => document.querySelector(s); q("#m2Est").innerHTML = '<p class="chip">Leyendo resultados…</p>';
    ST.D = await api("/api/visor/datos?id=" + encodeURIComponent(ST.x));
    if (ST.D.error) { q("#m2Est").innerHTML = nota(esc(ST.D.error), "err"); return; }
    ST.Y = ST.y ? await api(`/api/visor/capa?id=${encodeURIComponent(ST.y)}&capa=hmax`) : null;
    if (ST.Y && (ST.Y.error || ST.Y.nx !== ST.D.nx || ST.Y.ny !== ST.D.ny)) { q("#m2Est").innerHTML = nota(ST.Y.error ? esc(ST.Y.error) : "La corrida Y no tiene la misma malla que X: elige corridas del mismo terreno.", "pend"); ST.Y = null; }
    if (!ST.Y && ST.vista !== "x") ST.vista = "x", q("#m2V").value = "x";
    dibujar();
  }

  function dibujar() {
    const D = ST.D; if (!D || D.error) return;
    const c = document.querySelector("#m2C"), nx = D.nx, ny = D.ny, k = Math.max(1, Math.floor(Math.min(1100 / nx, 900 / ny)));
    c.width = nx * k; c.height = ny * k; const g = c.getContext("2d"), im = g.createImageData(nx, ny);
    const z = D.z, hx = (D.capas || {}).hmax || [], hy = ST.Y ? ST.Y.v : null, dx = D.dx_m, u = ST.umbral;
    let maxv = 0, maxd = 0;
    for (let i = 0; i < nx * ny; i++) { const a = hx[i] || 0, b = hy ? (hy[i] || 0) : 0; maxv = Math.max(maxv, ST.vista === "y" ? b : a); if (hy) maxd = Math.max(maxd, Math.abs(b - a)); }
    const vtop = Math.min(Math.max(maxv, 0.5), 5), dtop = Math.max(0.05, Math.min(maxd, 2));
    for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) {
      const p = j * nx + i, zz = z[p]; let col;
      if (zz == null) col = [11, 22, 34];
      else {                                                       // sombreado del terreno (luz del noroeste)
        const zl = z[p - (i > 0 ? 1 : 0)] ?? zz, zr = z[p + (i < nx - 1 ? 1 : 0)] ?? zz, zu = z[p - (j > 0 ? nx : 0)] ?? zz, zd = z[p + (j < ny - 1 ? nx : 0)] ?? zz;
        const sx = (zr - zl) / (2 * dx), sy = (zd - zu) / (2 * dx), sh = Math.max(0, Math.min(1, 0.62 + (-sx - sy) * 1.6));
        const gr = Math.round(70 + 120 * sh); col = [gr, gr, gr];
        const a = hx[p] || 0, b = hy ? (hy[p] || 0) : 0;
        if (ST.vista === "x" && a >= u) col = mezcla(col, rampa(AZUL, a / vtop), 0.88);
        else if (ST.vista === "y" && b >= u) col = mezcla(col, rampa(MAG, b / vtop), 0.88);
        else if (ST.vista === "d" && (a >= u || b >= u) && Math.abs(b - a) >= 0.01) col = mezcla(col, rampa(DIV, 0.5 + (b - a) / (2 * dtop)), 0.9);
      }
      im.data.set([col[0], col[1], col[2], 255], p * 4);
    }
    const tmp = document.createElement("canvas"); tmp.width = nx; tmp.height = ny; tmp.getContext("2d").putImageData(im, 0, 0);
    g.imageSmoothingEnabled = false; g.drawImage(tmp, 0, 0, nx * k, ny * k);
    g.lineCap = "round"; g.lineJoin = "round";
    const linea = (l) => { g.beginPath(); l.ij.forEach(([ii, jj], n) => n ? g.lineTo((ii + .5) * k, (jj + .5) * k) : g.moveTo((ii + .5) * k, (jj + .5) * k)); g.stroke(); };
    if (ST.vias) {                                                              // Eta (punto 32): las vías OSM siempre como referencia
      (D.vias || []).forEach(l => { const pr = /motorway|trunk|primary|secondary|tertiary/.test(l.clase); g.strokeStyle = pr ? "rgba(255,214,120,.95)" : "rgba(235,235,235,.55)"; g.lineWidth = pr ? 2.2 : 0.9; linea(l); });
    }
    if (ST.riosOsm) { g.strokeStyle = "rgba(40,150,255,.95)"; (D.rios_osm || []).forEach(l => { g.lineWidth = /river|canal/.test(l.clase) ? 2.6 : 1.2; linea(l); }); }
    if (ST.riosRed) {                                                           // HydroSHEDS/GEOGLOWS: red aproximada (±1 km), apagada por defecto
      g.strokeStyle = "rgba(120,200,255,.8)"; g.setLineDash([6, 5]);
      (D.rios || []).forEach(r => { g.lineWidth = Math.max(1, Math.min(4, Math.log10(1 + (r.area_km2 || 1)) * 1.4)); linea(r); }); g.setLineDash([]);
    }
    const W = c.width, H = c.height, km = (nx * dx) / 1000, paso = km > 8 ? 2 : km > 3 ? 1 : 0.5, lpx = paso * 1000 / dx * k;   // escala y norte
    g.fillStyle = "rgba(10,20,30,.75)"; g.fillRect(W - lpx - 34, H - 40, lpx + 24, 30); g.fillStyle = "#fff"; g.fillRect(W - lpx - 22, H - 22, lpx, 4);
    g.font = "12px Segoe UI"; g.fillText(`${paso} km`, W - lpx - 22, H - 26);
    g.beginPath(); g.moveTo(W - 24, 18); g.lineTo(W - 31, 36); g.lineTo(W - 17, 36); g.closePath(); g.fill(); g.fillText("N", W - 28, 50);
    leyenda(vtop, dtop); estadisticas();
    c.onmousemove = ev => { const r = c.getBoundingClientRect(), i = Math.floor((ev.clientX - r.left) / r.width * nx), j = Math.floor((ev.clientY - r.top) / r.height * ny), p = j * nx + i;
      if (i < 0 || j < 0 || i >= nx || j >= ny) return; const a = hx[p], b = hy ? hy[p] : null;
      document.querySelector("#m2Lee").style.display = "block";
      document.querySelector("#m2Lee").innerHTML = `celda ${i},${j} · cota ${fmt(z[p], 1)} m · X ${fmt(a || 0, 2)} m` + (hy ? ` · Y ${fmt(b || 0, 2)} m · Y−X <b>${(b - a) >= 0 ? "+" : ""}${fmt((b || 0) - (a || 0), 2)} m</b>` : ""); };
  }
  const mezcla = (a, b, f) => [0, 1, 2].map(k => Math.round(a[k] * (1 - f) + b[k] * f));
  function leyenda(vtop, dtop) {
    const barra = (st, a, b, tit) => `<div style="display:flex;align-items:center;gap:8px;font-size:12px"><span>${a}</span><span style="display:inline-block;width:240px;height:12px;border-radius:6px;background:linear-gradient(90deg,${st.map(s => `rgb(${s})`).join(",")})"></span><span>${b}</span><span class="chip">${tit}</span></div>`;
    document.querySelector("#m2Ley").innerHTML = ST.vista === "d" ? barra(DIV, `−${fmt(dtop, 2)} m`, `+${fmt(dtop, 2)} m`, "Y − X: azul = baja, magenta = sube con el cambio climático")
      : barra(ST.vista === "y" ? MAG : AZUL, `${fmt(ST.umbral, 2)} m`, `≥ ${fmt(vtop, 1)} m`, ST.vista === "y" ? "calado máximo Y (CMIP6)" : "calado máximo X (condiciones existentes)");
  }
  function estadisticas() {
    const D = ST.D, hx = (D.capas || {}).hmax || [], hy = ST.Y ? ST.Y.v : null, a1 = (D.dx_m * D.dx_m) / 1e6;
    const area = (v, t) => v ? v.reduce((s, x) => s + ((x || 0) >= t ? 1 : 0), 0) * a1 : null;
    const fila = t => { const ax = area(hx, t), ay = area(hy, t); return `<tr><td>≥ ${t} m</td><td class="num">${fmt(ax, 2)}</td><td class="num">${ay == null ? "—" : fmt(ay, 2)}</td><td class="num">${ay == null ? "—" : (ay - ax >= 0 ? "+" : "") + fmt(ay - ax, 2) + (ax ? ` (${ay - ax >= 0 ? "+" : ""}${fmt((ay / ax - 1) * 100, 0)} %)` : "")}</td></tr>`; };
    document.querySelector("#m2Est").innerHTML = `<table style="max-width:640px"><thead><tr><th>Área inundada (km²)</th><th class="num">X</th><th class="num">Y</th><th class="num">Y − X</th></tr></thead><tbody>${[0.05, 0.5, 1].map(fila).join("")}</tbody></table>
      <p class="chip">${esc(D.aviso || "")}</p>`;
  }
  VISTAS.mapa2d = vMapa2d;
})();
