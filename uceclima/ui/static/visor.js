/* Visor 3D de resultados · UCEclima. Terreno y capas REALES de una corrida (hmax, vmax, duración) en una maqueta isométrica nocturna.
   Solo dibuja lo que entrega /api/visor/datos; no calcula ni inventa. El «barrido por calado» recorre el umbral de calado (no es evolución en el tiempo). */
(() => {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const nf = (v, d = 2) => Number(v).toLocaleString("es-EC", { minimumFractionDigits: d, maximumFractionDigits: d });
  const RAMPAS = {
    terreno: [[0, "#2e6b4a"], [.18, "#709e52"], [.38, "#cdc86e"], [.58, "#d6a55c"], [.78, "#9e6e46"], [1, "#d6ccbe"]],
    hmax: [[0, "#1b2b4a"], [.35, "#2f6fa8"], [.7, "#5cc8e8"], [1, "#eaffff"]],
    vmax: [[0, "#2b1d5c"], [.45, "#a1308f"], [.75, "#ff6a3d"], [1, "#ffe27a"]],
    duracion: [[0, "#12304a"], [.5, "#3fa796"], [.8, "#e8d44d"], [1, "#fff5c2"]],
  };
  const hex = (h) => [parseInt(h.slice(1, 3), 16) / 255, parseInt(h.slice(3, 5), 16) / 255, parseInt(h.slice(5, 7), 16) / 255];
  function ramp(nombre, t) {
    const r = RAMPAS[nombre]; t = Math.min(1, Math.max(0, t));
    for (let i = 1; i < r.length; i++) if (t <= r[i][0]) {
      const a = hex(r[i - 1][1]), b = hex(r[i][1]), u = (t - r[i - 1][0]) / (r[i][0] - r[i - 1][0]);
      return [a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u, a[2] + (b[2] - a[2]) * u];
    }
    return hex(r[r.length - 1][1]);
  }
  const css = (n) => "linear-gradient(90deg," + RAMPAS[n].map(([t, c]) => `${c} ${t * 100}%`).join(",") + ")";
  const fallo = (m) => { const e = $("#error"); e.hidden = false; e.innerHTML = "<div><p style='font-size:15px'>" + m + "</p><p class='dim' style='color:#8b95a3'>Vuelve a UCEclima, etapa «Corrida», ejecuta un caso pequeño y regresa aquí.</p></div>"; $("#carga").classList.add("fuera"); };

  const id = new URLSearchParams(location.search).get("id") || "";
  fetch("/api/visor/datos" + (id ? "?id=" + encodeURIComponent(id) : "")).then((r) => r.json()).then((D) => {
    if (D.error) return fallo(D.error);
    try { construir(D); } catch (e) { console.error(e); fallo("No se pudo construir la vista 3D: " + e.message); }
  }).catch((e) => fallo("No se pudieron leer los datos del visor: " + e.message));

  function construir(D) {
    const nx = D.nx, ny = D.ny, dx = D.dx_m, W = nx * dx, H = ny * dx, N = nx * ny;
    const zmin = D.z_min, zmax = D.z_max, relieve = Math.max(zmax - zmin, 0.5);
    const Z = Float32Array.from(D.z, (v) => (v == null ? zmin : v));
    const valido = Uint8Array.from(D.z, (v) => (v == null ? 0 : 1));
    const capa = {}; for (const k in D.capas) capa[k] = Float32Array.from(D.capas[k], (v) => (v == null ? 0 : v));
    const info = Object.fromEntries(D.capas_info.map((c) => [c.id, c]));
    const H0 = capa.hmax || new Float32Array(N);
    const hmaxMax = (info.hmax && info.hmax.max) || 1;

    // película: estado del tiempo (se llena si la corrida guardó evolucion_calado.npz)
    const T = { activo: false, jugando: false, s: 0, fin: 0, t: null, idx: null, F: null, V: null, H: new Float32Array(N), ultimo: 0 };
    const hhmm = (s) => { const m = Math.round(s / 60); return Math.floor(m / 60) + " h " + String(m % 60).padStart(2, "0") + " min"; };
    const E = { exag: Math.min(40, Math.max(1, +(0.12 * Math.max(W, H) / relieve).toFixed(1))), umbral: Math.min(0.05, hmaxMax / 4), capa: info.hmax ? "hmax" : "terreno" };
    { const q = new URLSearchParams(location.search).get("capa"); if (q === "terreno" || info[q]) E.capa = q; }
    $("#exag").value = E.exag; $("#umbral").max = hmaxMax.toFixed(2); $("#umbral").value = E.umbral;
    $("#titulo").textContent = D.proyecto || "Visor 3D de resultados";
    $("#subtitulo").textContent = D.corrida + " · " + nx + "×" + ny + " celdas de " + nf(dx, 0) + " m · " + D.crs + (D.sintetico ? " · SINTÉTICO" : "") + (D.escenario ? " · escenario: " + D.escenario.nombre : "");
    $("#aviso").textContent = (D.sintetico ? "SINTÉTICO: terreno inventado, no es un lugar real. " : "") + D.aviso + " Altura vertical exagerada; la cota no tiene datum verificado.";
    document.title = "Visor 3D · " + (D.proyecto || "UCEclima");

    // ---------------------------------------------------------------- escena
    const cont = $("#lienzo");
    const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2)); renderer.setSize(innerWidth, innerHeight); cont.appendChild(renderer.domElement);
    renderer.setClearColor(0x0f1a29);
    const scene = new THREE.Scene(); scene.fog = new THREE.Fog(0x0f1a29, Math.max(W, H) * 2.2, Math.max(W, H) * 6);
    const R = Math.max(W, H);
    const hemi = new THREE.HemisphereLight(0x8aa0c0, 0x10161f, 0.42); scene.add(hemi);
    const sol = new THREE.DirectionalLight(0xffe9cc, 0.95); sol.position.set(-R, R * 1.1, R * 0.6); scene.add(sol);
    const rellena = new THREE.DirectionalLight(0x4a6a9a, 0.25); rellena.position.set(R, R * 0.4, -R * 0.8); scene.add(rellena);

    const yDe = (k) => (Z[k] - zmin) * E.exag;
    const X = (i) => (i + 0.5) * dx - W / 2, Zw = (j) => (j + 0.5) * dx - H / 2;

    // terreno
    const gT = new THREE.BufferGeometry(), pT = new Float32Array(N * 3), cT = new Float32Array(N * 3);
    const idx = new Uint32Array((nx - 1) * (ny - 1) * 6); let q = 0;
    for (let j = 0; j < ny - 1; j++) for (let i = 0; i < nx - 1; i++) { const a = j * nx + i, b = a + 1, c = a + nx, d = c + 1; idx[q++] = a; idx[q++] = c; idx[q++] = b; idx[q++] = b; idx[q++] = c; idx[q++] = d; }
    for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) { const k = j * nx + i, col = ramp("terreno", (Z[k] - zmin) / relieve); pT[3 * k] = X(i); pT[3 * k + 2] = Zw(j); cT.set([col[0] * 0.62, col[1] * 0.62, col[2] * 0.62], 3 * k); }
    gT.setAttribute("position", new THREE.BufferAttribute(pT, 3)); gT.setAttribute("color", new THREE.BufferAttribute(cT, 3)); gT.setIndex(new THREE.BufferAttribute(idx, 1));
    const U = { uGrid: { value: 1 }, uStep: { value: 1 }, uCell: { value: 100 } };
    const mT = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.92, metalness: 0.02 });
    mT.onBeforeCompile = (s) => {
      Object.assign(s.uniforms, U);
      s.vertexShader = s.vertexShader.replace("#include <common>", "#include <common>\nvarying vec3 vW;").replace("#include <begin_vertex>", "#include <begin_vertex>\nvW = (modelMatrix * vec4(position,1.0)).xyz;");
      s.fragmentShader = s.fragmentShader.replace("#include <common>", "#include <common>\nvarying vec3 vW; uniform float uGrid; uniform float uStep; uniform float uCell;")
        .replace("#include <color_fragment>", `#include <color_fragment>
        { float c1 = abs(fract(vW.y/uStep-0.5)-0.5)/max(fwidth(vW.y/uStep),1e-4); float cl = (1.0-clamp(c1,0.0,1.0))*uGrid;
          vec2 g = abs(fract(vW.xz/uCell-0.5)-0.5)/max(fwidth(vW.xz/uCell),vec2(1e-4)); float gl = (1.0-clamp(min(g.x,g.y),0.0,1.0))*uGrid;
          diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.04,0.06,0.09), cl*0.55);
          diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.36,0.78,0.91), gl*0.28); }`);
    };
    const terreno = new THREE.Mesh(gT, mT); scene.add(terreno);

    // zócalo (bloque de maqueta)
    const grosor = Math.max(R * 0.045, relieve * E.exag * 0.12), zocalo = new THREE.Group(); scene.add(zocalo);
    const bordes = []; for (let i = 0; i < nx; i++) bordes.push([i, 0]); for (let j = 1; j < ny; j++) bordes.push([nx - 1, j]); for (let i = nx - 2; i >= 0; i--) bordes.push([i, ny - 1]); for (let j = ny - 2; j > 0; j--) bordes.push([0, j]);
    const gS = new THREE.BufferGeometry(), nb = bordes.length, pS = new Float32Array((nb + 1) * 2 * 3), cS = new Float32Array((nb + 1) * 2 * 3), iS = [];
    function esquinas() { return bordes; }
    for (let m = 0; m <= nb; m++) { const [i, j] = bordes[m % nb]; pS.set([X(i), 0, Zw(j)], 6 * m); pS.set([X(i), -grosor, Zw(j)], 6 * m + 3); const t = ramp("terreno", (Z[j * nx + i] - zmin) / relieve); cS.set([t[0] * .3, t[1] * .3, t[2] * .3, 0.04, 0.05, 0.08], 6 * m); if (m < nb) iS.push(2 * m, 2 * m + 1, 2 * m + 2, 2 * m + 1, 2 * m + 3, 2 * m + 2); }
    gS.setAttribute("position", new THREE.BufferAttribute(pS, 3)); gS.setAttribute("color", new THREE.BufferAttribute(cS, 3)); gS.setIndex(iS);
    const faldon = new THREE.Mesh(gS, new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.DoubleSide })); zocalo.add(faldon);
    const base = new THREE.Mesh(new THREE.PlaneGeometry(W, H), new THREE.MeshBasicMaterial({ color: 0x0d1724, side: THREE.DoubleSide })); base.rotation.x = -Math.PI / 2; base.position.y = -grosor; zocalo.add(base);
    const marco = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(W, grosor, H)), new THREE.LineBasicMaterial({ color: 0x5cc8e8, transparent: true, opacity: 0.35 }));
    marco.position.y = -grosor / 2; zocalo.add(marco);
    const suelo = new THREE.Mesh(new THREE.PlaneGeometry(R * 12, R * 12), new THREE.MeshBasicMaterial({ color: 0x0f1a29 })); suelo.rotation.x = -Math.PI / 2; suelo.position.y = -grosor - 0.5; scene.add(suelo);
    const rej = new THREE.GridHelper(R * 3, 30, 0x2a4260, 0x172536); rej.position.y = -grosor - 0.2; scene.add(rej);

    // agua (hmax) coloreada con la capa elegida
    const gW = new THREE.BufferGeometry(), pW = new Float32Array(N * 3), cW = new Float32Array(N * 3), aW = new Float32Array(N);
    for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) { pW[3 * (j * nx + i)] = X(i); pW[3 * (j * nx + i) + 2] = Zw(j); }
    gW.setAttribute("position", new THREE.BufferAttribute(pW, 3)); gW.setAttribute("aCol", new THREE.BufferAttribute(cW, 3)); gW.setAttribute("aA", new THREE.BufferAttribute(aW, 1)); gW.setIndex(new THREE.BufferAttribute(idx, 1));
    const mW = new THREE.ShaderMaterial({
      transparent: true, depthWrite: false, side: THREE.DoubleSide,
      uniforms: { uBri: { value: 1.25 } },
      vertexShader: "attribute vec3 aCol; attribute float aA; varying vec3 vC; varying float vA; varying vec3 vP; void main(){ vC=aCol; vA=aA; vP=(modelMatrix*vec4(position,1.0)).xyz; gl_Position=projectionMatrix*viewMatrix*modelMatrix*vec4(position,1.0);} ",
      fragmentShader: "varying vec3 vC; varying float vA; varying vec3 vP; uniform float uBri; void main(){ vec3 n=normalize(cross(dFdx(vP),dFdy(vP))); float l=0.65+0.35*abs(n.y); gl_FragColor=vec4(vC*l*uBri, vA*0.9); }",
    });
    mW.extensions = { derivatives: true };
    const agua = new THREE.Mesh(gW, mW); agua.renderOrder = 2; scene.add(agua);


    // ---------------------------------------------------------------- comparación: el calado máximo de OTROS escenarios sobre el mismo terreno. Y (CMIP6) se dibuja ENCIMA e intenso solo donde supera a X
    // paleta única: X (condiciones existentes) en tonos fríos, Y (CMIP6) en tonos cálidos
    const colHex = id => { const m = /^cc_(ssp\d+)_(\d{4})-(\d{4})/.exec(id || ""); if (m) { const fin = m[3] === "2100"; return m[1] === "ssp585" ? (fin ? "#ff1493" : "#ff3cc8") : (fin ? "#f05cc0" : "#ff9fd8"); }
      return {directa: "#6cc4ec", observado: "#9fb4ff", chirps: "#7bd88f", escalada: "#93a4b8"}[id] || "#93a4b8"; };
    const rgb = h => [parseInt(h.slice(1, 3), 16) / 255, parseInt(h.slice(3, 5), 16) / 255, parseInt(h.slice(5, 7), 16) / 255];
    const FANT = new Map();
    function actualizarFantasmas() {
      FANT.forEach(f => { const pa = f.geo.attributes.position.array, aa = f.geo.attributes.aA.array;
        for (let k = 0; k < N; k++) { const h = f.H[k], base = f.cc ? H0[k] : 0, m = valido[k] && h >= E.umbral && h > 0 && $("#agua").checked && (!f.cc || h > base + 0.01);
          pa[3 * k + 1] = m ? yDe(k) + h * E.exag + (f.cc ? 0.06 : 0) : yDe(k) - 0.03; aa[k] = m ? (f.cc ? 0.95 : 0.6) : 0; }
        f.geo.attributes.position.needsUpdate = f.geo.attributes.aA.needsUpdate = true; });
    }
    async function quitarOAgregarFantasma(run, esc, on) {
      if (!on) { const f = FANT.get(run); if (f) { scene.remove(f.mesh); f.geo.dispose(); FANT.delete(run); } return; }
      const r = await (await fetch("/api/visor/capa?id=" + encodeURIComponent(run) + "&capa=hmax")).json();
      if (r.error || r.nx !== nx || r.ny !== ny) { alert("No se pudo dibujar ese escenario sobre esta malla."); return; }
      const geo = new THREE.BufferGeometry(), p = new Float32Array(pW), c = new Float32Array(N * 3), a = new Float32Array(N), col = rgb(colHex((esc || {}).id));
      for (let k = 0; k < N; k++) c.set(col, 3 * k);
      geo.setAttribute("position", new THREE.BufferAttribute(p, 3)); geo.setAttribute("aCol", new THREE.BufferAttribute(c, 3)); geo.setAttribute("aA", new THREE.BufferAttribute(a, 1)); geo.setIndex(new THREE.BufferAttribute(idx, 1));
      const cc = /^cc_/.test((esc || {}).id || "");                                                   // Y CMIP6: encima, intenso y solo donde supera a X (el impacto)
      const mat = mW.clone(); mat.uniforms = { uBri: { value: cc ? 1.8 : 1.0 } }; mat.extensions = { derivatives: true };
      const mesh = new THREE.Mesh(geo, mat); mesh.renderOrder = cc ? 3 : 1; scene.add(mesh);
      FANT.set(run, {geo, mesh, cc, H: Float32Array.from(r.v, v => (v == null ? 0 : v))}); actualizarFantasmas();
    }
    fetch("/api/estado").then(r => r.json()).then(est => {
      (est.corridas || []).forEach(c => { if (!c.escenario_id && c.estado === "completado") c.escenario_id = /_cc_/.test(c.id) ? "cc_" + c.id : "x_" + c.id; });   // Eta (32a): corridas X antiguas sin escenario
      const sel = document.getElementById("selCorrida");                                     // Eta (32b): elegir qué corrida abrir
      if (sel) { sel.innerHTML = (est.corridas || []).filter(c => c.estado === "completado").map(c => `<option value="${c.id}" ${c.id === D.corrida ? "selected" : ""}>${/_cc_/.test(c.id) ? "Y · " : "X · "}${c.id.replace(/^corrida_/, "")}</option>`).join(""); sel.onchange = () => { location.search = "?id=" + encodeURIComponent(sel.value); }; }
      const otros = (est.corridas || []).filter(c => c.estado === "completado" && c.id !== D.corrida && c.escenario_id && (!c.escenario_id.startsWith("cc_") || c.escenario_id.startsWith("cc_ssp585") || /_cc_/.test(c.id)));
      const box = $("#fant"); if (!box) return;
      if (!otros.length) { box.innerHTML = ""; return; }
      const porId = {}; otros.forEach(c => { if (!porId[c.escenario_id] || c.id > porId[c.escenario_id].id) porId[c.escenario_id] = c; });          // la corrida más reciente de cada escenario
      const lista = Object.values(porId), item = c => `<label class="tog"><input type="checkbox" data-run="${c.id}" data-esc="${c.escenario_id}"><i class="ch" style="background:${colHex(c.escenario_id)}"></i>${(c.escenario || c.escenario_id).replace(/&/g, "&amp;").replace(/</g, "&lt;")}</label>`;
      const X = lista.filter(c => !c.escenario_id.startsWith("cc_")), Y = lista.filter(c => c.escenario_id.startsWith("cc_")).sort((a, b) => a.escenario_id.localeCompare(b.escenario_id));
      box.innerHTML = '<div class="gh">Escenarios plausibles · X condiciones existentes</div>' + (X.map(item).join("") || '<div class="gh" style="text-transform:none">—</div>') + (Y.length ? '<div class="gh">Escenarios plausibles · Y CMIP6 SSP5-8.5 (magenta = dónde Y supera a X)</div>' + Y.map(item).join("") : "");
      box.querySelectorAll("input").forEach(i => i.addEventListener("change", () => quitarOAgregarFantasma(i.dataset.run, {id: i.dataset.esc}, i.checked)));
      const qf = new URLSearchParams(location.search).get("fant");                                  // sin parámetro: si la corrida abierta es X, las Y del proyecto vienen marcadas
      const pre = qf != null ? qf.split(",").filter(Boolean) : (/^cc_/.test((D.escenario || {}).id || "") ? [] : Y.map(c => c.escenario_id));
      box.querySelectorAll("input").forEach(i => { if (pre.includes(i.dataset.esc)) { i.checked = true; quitarOAgregarFantasma(i.dataset.run, {id: i.dataset.esc}, true); } });
    }).catch(() => {});

    // ---------------------------------------------------------------- actualización
    // ---------------------------------------------------------------- Omega O3: ríos HydroSHEDS sobre el terreno (siempre, salvo que se desmarque)
    const rios = new THREE.Group(); rios.renderOrder = 3; scene.add(rios); const lineasRio = [];
    for (const r of (D.rios || [])) {
      const g = new THREE.BufferGeometry(), p = new Float32Array(r.ij.length * 3); g.setAttribute("position", new THREE.BufferAttribute(p, 3));
      const ancho = Math.min(1, 0.35 + Math.log10(Math.max(r.area_km2, 1)) / 4);
      const l = new THREE.Line(g, new THREE.LineBasicMaterial({ color: 0x39d0ff, transparent: true, opacity: 0.55 + 0.4 * ancho, depthTest: false })); l.renderOrder = 3; rios.add(l); lineasRio.push([r, g]);
    }
    function actualizarRios() {
      for (const [r, g] of lineasRio) {
        const p = g.attributes.position.array;
        r.ij.forEach(([i, j], m) => { const ii = Math.min(nx - 1, Math.max(0, Math.round(i))), jj = Math.min(ny - 1, Math.max(0, Math.round(j))); p[3 * m] = X(i); p[3 * m + 1] = yDe(jj * nx + ii) + H0[jj * nx + ii] * E.exag + 0.08; p[3 * m + 2] = Zw(j); });
        g.attributes.position.needsUpdate = true; g.computeBoundingSphere();
      }
    }
    rios.visible = !!($("#rios") && $("#rios").checked);                    // Eta (Mejora 2): la red HydroSHEDS va apagada por defecto
    const osm = new THREE.Group(); osm.renderOrder = 3; scene.add(osm); const lineasOsm = [];      // Eta (punto 32): vías y ríos de OpenStreetMap
    for (const [lista, colV, colP] of [[D.vias || [], 0xd9d9d9, 0xffd27a], [D.rios_osm || [], 0x3aa0ff, 0x1f8fff]]) {
      for (const r of lista) {
        const pr = /motorway|trunk|primary|secondary|tertiary|river|canal/.test(r.clase || "");
        const g = new THREE.BufferGeometry(), p = new Float32Array(r.ij.length * 3); g.setAttribute("position", new THREE.BufferAttribute(p, 3));
        const l = new THREE.Line(g, new THREE.LineBasicMaterial({ color: pr ? colP : colV, transparent: true, opacity: pr ? 0.95 : 0.5, depthTest: false })); l.renderOrder = 3; osm.add(l); lineasRio.push([r, g]);
      }
    }
    if ($("#vias")) $("#vias").addEventListener("change", (e) => { osm.visible = e.target.checked; });
    if ($("#rios")) { $("#rios").addEventListener("change", (e) => { rios.visible = e.target.checked; }); if (!(D.rios || []).length) $("#rios").parentElement.title = "Sin red de ríos descargada en este proyecto (hidro › Cuenca › Descargar ríos HydroSHEDS)"; }
    function actualizarTerreno() {
      const a = gT.attributes.position.array;
      for (let k = 0; k < N; k++) a[3 * k + 1] = yDe(k);
      gT.attributes.position.needsUpdate = true; gT.computeVertexNormals(); gT.computeBoundingSphere(); gT.computeBoundingBox();
      for (let m = 0; m <= nb; m++) { const [i, j] = bordes[m % nb]; pS[6 * m + 1] = yDe(j * nx + i); pS[6 * m + 4] = -grosor; }
      gS.attributes.position.needsUpdate = true;
      const paso = (() => { const t = relieve / 12, c = [0.1, 0.25, 0.5, 1, 2, 5, 10, 20]; return c.find((v) => v >= t) || 20; })();
      U.uStep.value = paso * E.exag; U.uCell.value = Math.pow(10, Math.floor(Math.log10(R / 4)));
      actualizarRios();
    }
    function actualizarAgua() {
      const nombre = E.capa, v = capa[nombre], vmax = (info[nombre] && info[nombre].max) || 1;
      const pa = gW.attributes.position.array, ca = gW.attributes.aCol.array, aa = gW.attributes.aA.array;
      let mojadas = 0, hmx = 0;
      const HS = T.activo ? T.H : H0;                       // en la película: calado del instante; si no, el máximo
      for (let k = 0; k < N; k++) {
        const h = HS[k], mojada = valido[k] && h >= E.umbral && h > 0 && $("#agua").checked && nombre !== "terreno";
        const yb = yDe(k);
        if (mojada) {
          mojadas++; if (h > hmx) hmx = h;
          pa[3 * k + 1] = yb + h * E.exag + 0.02;
          const t = nombre === "hmax" || T.activo ? h / hmaxMax : (v ? v[k] / vmax : 0), c = ramp(T.activo ? "hmax" : nombre, 0.08 + 0.92 * t);
          ca[3 * k] = c[0]; ca[3 * k + 1] = c[1]; ca[3 * k + 2] = c[2]; aa[k] = 0.92;
        } else { pa[3 * k + 1] = yb - 0.02; aa[k] = 0; }
      }
      gW.attributes.position.needsUpdate = gW.attributes.aCol.needsUpdate = gW.attributes.aA.needsUpdate = true; gW.computeBoundingSphere();
      const area = mojadas * dx * dx;
      $("#stats").innerHTML = [
        [nf(hmx, 2) + " m", T.activo ? "calado máx. en t = " + hhmm(T.s) : "calado máx. mostrado"], [area >= 1e5 ? nf(area / 1e6, 3) + " km²" : nf(area / 1e4, 2) + " ha", "área con calado ≥ " + nf(E.umbral, 2) + " m"],
        [mojadas.toLocaleString("es-EC"), "celdas con agua de " + N.toLocaleString("es-EC")], [nf(zmin, 1) + "–" + nf(zmax, 1) + " m", "cota del terreno"],
      ].map(([a, b]) => `<div class="card"><b>${a}</b><span>${b}</span></div>`).join("");
    }
    function leyenda() {
      const n = E.capa, inf = info[n];
      $("#barra").style.background = css(n);
      $("#leyMin").textContent = n === "terreno" ? nf(zmin, 1) + " m" : "0";
      $("#leyMax").textContent = n === "terreno" ? nf(zmax, 1) + " m" : nf(inf.max, 2) + " " + inf.unidad;
      $("#leyTit").textContent = n === "terreno" ? "cota (hipsométrica)" : inf.titulo.toLowerCase();
    }
    function dibujarCapas() {
      const lista = [["terreno", "Terreno", "cota", "#709e52"]].concat(D.capas_info.map((c) => [c.id, c.titulo, c.unidad, RAMPAS[c.id][2][1]]));
      $("#capas").innerHTML = lista.map(([id, t, u, c]) => `<button type="button" role="radio" aria-checked="${E.capa === id}" data-capa="${id}" title="${(info[id] || {}).nota || "Terreno coloreado por cota"}"><i style="--c:${c}"></i>${t}<small>${u}</small></button>`).join("");
      document.querySelectorAll("#capas button").forEach((b) => b.addEventListener("click", () => { E.capa = b.dataset.capa; dibujarCapas(); leyenda(); actualizarAgua(); }));
    }

    // ---------------------------------------------------------------- cámara y postproceso
    let ortografica = true, camara, controles;
    const centro = new THREE.Vector3(0, relieve * E.exag * 0.3, 0);
    function crearCamara() {
      const asp = innerWidth / innerHeight, d = R * (innerWidth > 1300 ? 0.6 : 0.74);
      const dir = new THREE.Vector3(1, 0.62, 1).normalize();
      const prev = camara ? camara.position.clone().sub(controles.target) : dir.clone().multiplyScalar(R * 2.2);
      camara = ortografica ? new THREE.OrthographicCamera(-d * asp, d * asp, d, -d, -R * 10, R * 20) : new THREE.PerspectiveCamera(32, asp, R * 0.05, R * 30);
      camara.position.copy(centro).add(prev);
      if (controles) controles.dispose();
      controles = new THREE.OrbitControls(camara, renderer.domElement); controles.target.copy(centro); controles.enableDamping = true; controles.dampingFactor = 0.08;
      controles.maxPolarAngle = Math.PI * 0.49; controles.screenSpacePanning = true; controles.update();
      if (rp) rp.camera = camara;
      if (typeof desplazar === "function" && rp) desplazar();
    }
    function desplazar() {                                   // en pantallas anchas la maqueta se centra en el espacio libre a la derecha del panel
      const dx0 = innerWidth > 760 ? Math.min(170, innerWidth * 0.12) : 0;
      if (dx0) camara.setViewOffset(innerWidth, innerHeight, -dx0, 0, innerWidth, innerHeight); else camara.clearViewOffset();
      camara.updateProjectionMatrix();
    }
    let rp = null; crearCamara(); desplazar();
    rp = new THREE.RenderPass(scene, camara);
    const bloom = new THREE.UnrealBloomPass(new THREE.Vector2(innerWidth, innerHeight), 0.55, 0.55, 0.82);
    const comp = new THREE.EffectComposer(renderer); comp.addPass(rp); comp.addPass(bloom);
    function vistaInicial() { ortografica = true; $("#proy").textContent = "Isométrica"; camara = null; crearCamara(); }

    // ---------------------------------------------------------------- lectura bajo el cursor
    const ray = new THREE.Raycaster(), pt = new THREE.Vector2(); let pendiente = false;
    renderer.domElement.addEventListener("pointermove", (ev) => {
      if (pendiente) return; pendiente = true;
      requestAnimationFrame(() => {
        pendiente = false; pt.set((ev.clientX / innerWidth) * 2 - 1, -(ev.clientY / innerHeight) * 2 + 1); ray.setFromCamera(pt, camara);
        const hit = ray.intersectObject(terreno, false)[0]; if (!hit) return;
        const i = Math.min(nx - 1, Math.max(0, Math.floor((hit.point.x + W / 2) / dx))), j = Math.min(ny - 1, Math.max(0, Math.floor((hit.point.z + H / 2) / dx))), k = j * nx + i;
        const E0 = D.origen[0] + (i + 0.5) * dx, N0 = D.origen[1] - (j + 0.5) * dx;
        const filas = [`Este ${nf(E0, 0)} · Norte ${nf(N0, 0)}`, `cota <b>${nf(Z[k], 2)} m</b>`];
        for (const c of D.capas_info) filas.push(`${c.titulo.toLowerCase()} <b>${nf(capa[c.id][k], c.id === "duracion" ? 2 : c.id === "vmax" ? 3 : 2)} ${c.unidad}</b>`);
        $("#lectura").innerHTML = filas.join("<br>");
      });
    });

    // ---------------------------------------------------------------- controles
    $("#umbral").addEventListener("input", (e) => { E.umbral = +e.target.value; $("#umbralV").textContent = nf(E.umbral, 2) + " m"; actualizarAgua(); actualizarFantasmas(); });
    $("#exag").addEventListener("input", (e) => { E.exag = +e.target.value; $("#exagV").textContent = "×" + nf(E.exag, 1); actualizarTerreno(); actualizarAgua(); actualizarFantasmas(); });
    $("#bloom").addEventListener("change", () => {}); $("#rejilla").addEventListener("change", (e) => { U.uGrid.value = e.target.checked ? 1 : 0; rej.visible = e.target.checked; });
    $("#agua").addEventListener("change", () => { actualizarAgua(); actualizarFantasmas(); });
    $("#proy").addEventListener("click", () => { ortografica = !ortografica; $("#proy").textContent = ortografica ? "Isométrica" : "Perspectiva"; crearCamara(); });
    $("#reset").addEventListener("click", vistaInicial);
    let barriendo = false, t0 = 0;
    const umbral0 = E.umbral; $("#barrer").title = "Sube poco a poco el «calado mínimo para dibujar agua» para ver qué zonas quedan con más agua. Al detenerlo, el calado mínimo vuelve a su valor inicial.";
    $("#barrer").addEventListener("click", () => { barriendo = !barriendo; t0 = performance.now(); $("#barrer").setAttribute("aria-pressed", barriendo); $("#barrer").textContent = barriendo ? "■ Detener barrido" : "▶ Barrido por calado";
      if (!barriendo) { E.umbral = umbral0; $("#umbral").value = umbral0; $("#umbralV").textContent = nf(umbral0, 2) + " m"; actualizarAgua(); actualizarFantasmas(); } });   // Eta: al detener, el agua vuelve a verse
    // ---------------------------------------------------------------- película: evolución del calado en el tiempo, más lenta en la crecida
    // «Crecida» = instantes con volumen de agua en el dominio ≥ ~40 % de su máximo; ahí la reproducción baja hasta ×0,2 con transición suave.
    const sstep = (a, b, x) => { const u = Math.min(1, Math.max(0, (x - a) / (b - a))); return u * u * (3 - 2 * u); };
    function lentitud(s) { if (!$("#lenta").checked || !T.V) return 1; const v = interpV(s) / T.Vmax; return 1 - 0.8 * sstep(0.4, 0.8, v); }
    function cuadro(s) { let i = 0; while (i < T.t.length - 2 && T.t[i + 1] <= s) i++; const u = T.t[i + 1] > T.t[i] ? Math.min(1, Math.max(0, (s - T.t[i]) / (T.t[i + 1] - T.t[i]))) : 0; return [i, u]; }
    function interpV(s) { const [i, u] = cuadro(s); return T.V[i] + (T.V[Math.min(i + 1, T.V.length - 1)] - T.V[i]) * u; }
    function ponerTiempo(s) {
      T.s = Math.min(T.fin, Math.max(0, s)); const [i, u] = cuadro(T.s), a = T.F[i], b = T.F[Math.min(i + 1, T.F.length - 1)];
      T.H.fill(0); for (let m = 0; m < T.idx.length; m++) T.H[T.idx[m]] = (a[m] + (b[m] - a[m]) * u) / 1000;   // entre fotos (cada pocos min) se interpola solo para la animación
      $("#tiempo").value = T.s / T.fin; $("#tiempoV").textContent = hhmm(T.s) + " de " + hhmm(T.fin);
      const f = lentitud(T.s); $("#ritmo").textContent = f < 0.95 ? "×" + nf(f, 2) + " · crecida (cámara lenta)" : "×1";
      $("#ritmo").style.color = f < 0.95 ? "#ffd27a" : ""; curva(); actualizarAgua();
    }
    function curva() {
      const cv = $("#curvaV"), g = cv.getContext("2d"), w = cv.width, h = cv.height, n = T.t.length; g.clearRect(0, 0, w, h);
      const xs = (s) => 4 + (w - 8) * s / T.fin, ys = (v) => h - 6 - (h - 14) * v / T.Vmax;
      g.fillStyle = "rgba(255,210,122,0.16)"; for (let k = 0; k < w; k++) { const s = (k / w) * T.fin; if ($("#lenta").checked && lentitud(s) < 0.95) g.fillRect(k, 0, 1, h); }
      g.strokeStyle = "#5cc8e8"; g.lineWidth = 1.6; g.beginPath(); for (let k = 0; k < n; k++) { const x = xs(T.t[k]), y = ys(T.V[k]); k ? g.lineTo(x, y) : g.moveTo(x, y); } g.stroke();
      g.strokeStyle = "#ffffff"; g.lineWidth = 1; g.beginPath(); g.moveTo(xs(T.s), 2); g.lineTo(xs(T.s), h - 2); g.stroke();
      g.fillStyle = "#8b95a3"; g.font = "10px sans-serif"; g.fillText("volumen de agua en el dominio · " + nf(T.Vmax / 1e3, 0) + " mil m³ máx.", 6, 11);
    }
    function modoTiempo(on) {
      T.activo = on; T.jugando = on; T.ultimo = performance.now(); if (on && T.s >= T.fin - 1) T.s = 0;
      $("#pelicula").setAttribute("aria-pressed", on); $("#pelicula").textContent = on ? "■ Detener" : "▶ Evolución en el tiempo";
      if (on) { barriendo = false; $("#barrer").setAttribute("aria-pressed", false); $("#barrer").textContent = "▶ Barrido por calado"; E.capa = "hmax"; dibujarCapas(); leyenda(); ponerTiempo(T.s); }
      else { $("#ritmo").textContent = ""; actualizarAgua(); }
    }
    fetch("/api/visor/fotos?id=" + encodeURIComponent(D.corrida)).then((r) => r.json()).then((P) => {
      if (P.error || P.nx !== nx || P.ny !== ny || !P.t_s || P.t_s.length < 2) return;            // corridas anteriores a Gamma: sin película
      T.t = P.t_s; T.fin = P.t_s[P.t_s.length - 1]; T.idx = Uint32Array.from(P.idx); T.F = P.h_mm.map((f) => Uint16Array.from(f)); T.V = P.volumen_m3; T.Vmax = Math.max(...T.V, 1);
      $("#tiempoBox").hidden = false; T.s = T.fin; $("#tiempoV").textContent = hhmm(T.fin); curva();
      $("#pelicula").addEventListener("click", () => modoTiempo(!T.jugando));
      $("#tiempo").addEventListener("input", (e) => { T.activo = true; T.jugando = false; $("#pelicula").textContent = "▶ Seguir"; $("#pelicula").setAttribute("aria-pressed", false); ponerTiempo(+e.target.value * T.fin); });
      $("#lenta").addEventListener("change", () => (T.activo ? ponerTiempo(T.s) : curva()));
      window.__visor.fotos = T.t.length;
    }).catch(() => {});

    addEventListener("resize", () => {
      renderer.setSize(innerWidth, innerHeight); comp.setSize(innerWidth, innerHeight); const asp = innerWidth / innerHeight;
      if (ortografica) { const d = R * (innerWidth > 1300 ? 0.6 : 0.74); camara.left = -d * asp; camara.right = d * asp; camara.top = d; camara.bottom = -d; } else camara.aspect = asp; camara.updateProjectionMatrix(); desplazar();
    });
    const quieto = matchMedia("(prefers-reduced-motion: reduce)").matches;

    $("#umbralV").textContent = nf(E.umbral, 2) + " m"; $("#exagV").textContent = "×" + nf(E.exag, 1);
    actualizarTerreno(); dibujarCapas(); leyenda(); actualizarAgua();
    function bucle() {
      requestAnimationFrame(bucle);
      if (barriendo) {
        const u = ((performance.now() - t0) / (quieto ? 12000 : 9000)) % 1.15, v = Math.min(1, u / 1.0) * hmaxMax * 0.98;
        E.umbral = v; $("#umbral").value = v; $("#umbralV").textContent = nf(v, 2) + " m"; actualizarAgua(); actualizarFantasmas();
      }
      if (T.jugando) {                                        // la corrida completa dura ~30 s a ritmo ×1; en la crecida baja hasta ×0,2
        const ahora = performance.now(), dt = Math.min(0.1, (ahora - T.ultimo) / 1000); T.ultimo = ahora;
        const s = T.s + dt * (T.fin / (quieto ? 45 : 30)) * lentitud(T.s);
        if (s >= T.fin) { ponerTiempo(T.fin); T.jugando = false; $("#pelicula").textContent = "↺ Repetir"; $("#pelicula").setAttribute("aria-pressed", false); } else ponerTiempo(s);
      }
      controles.update(); bloom.enabled = $("#bloom").checked;
      if (bloom.enabled) comp.render(); else renderer.render(scene, camara);
    }
    bucle();
    window.__visor = { E, N, nx, ny, listo: true };
    setTimeout(() => $("#carga").classList.add("fuera"), 350);
  }
})();
