// Maqueta isométrica de dispersión de contaminantes (base pedagógica de Epsilon; se desarrollará en el doctorado).
// Un tramo de río sobre una placa: orillas, lecho, la mancha del derrame coloreada por concentración y un bidón en la orilla
// en el punto del derrame. Los números salen de /api/contaminantes/calcular (uceclima/contaminantes.py), no del dibujo.
import * as k from "/static/iso/iso-kit.mjs";

const $ = (s) => document.querySelector(s);
const nf = (v, d = 2) => (v == null || Number.isNaN(v) ? "—" : Number(v).toLocaleString("es-EC", { maximumFractionDigits: d }));
const W = 900, H = 470;
const RAMPA = [[206, 208, 210], [158, 160, 162], [112, 113, 115], [66, 66, 68], [28, 28, 29]];   // Omega O4: carboncillo (gris perla → grafito)
const AGUA = "rgb(226,229,231)";
function color(f) {                                    // f en [0, 1] → rampa gris perla → grafito
  if (!(f > 0)) return null;
  const x = Math.min(1, f) * (RAMPA.length - 1), i = Math.min(RAMPA.length - 2, Math.floor(x)), u = x - i;
  return "rgb(" + RAMPA[i].map((c, j) => Math.round(c + (RAMPA[i + 1][j] - c) * u)).join(",") + ")";
}

let D = null, cuadro = 0, timer = null;
const LX = 340, BX = 70, PLACA = { x: -200, y: -70, w: 400, d: 140, r: 10 }, RIO = { x: -LX / 2, y: -BX / 2, w: LX, d: BX, r: 0 };
const ORI = 30, Z_LECHO = 0, Z_AGUA = 6, Z_ORILLA = 12;

function escena() {
  const P = k.fitProjection([...k.boxCorners(PLACA, -14, 0), ...k.boxCorners({ x: PLACA.x, y: PLACA.y, w: PLACA.w, d: PLACA.d }, 0, Z_ORILLA + 34)], W, H, { pad: 18, azimuth: 38 });
  const at = (p) => k.iso(p, P), S = (paths, st) => k.solidSvg(paths, st), L = (d, st) => k.lineSvg(d, st);
  const o = [];
  o.push(S(k.slabOf(PLACA, -12, 12, P, 8, 1.4), { tone: "mid" }));
  for (const [x, y] of k.corners(PLACA, 14)) o.push(S(k.cylinder(x, y, 5, -16, 4, P, 20), { tone: "lo" }));
  o.push(L(k.planOutline(k.insetPlan(PLACA, 5), 0, P), { tone: "lo" }));
  // orilla trasera (alta) y lecho
  o.push(S(k.slabOf({ x: RIO.x, y: RIO.y - ORI, w: LX, d: ORI, r: 2 }, 0, Z_ORILLA, P, 3, 0.6), { tone: "lo" }));
  o.push(S(k.slabOf(RIO, 0, Z_LECHO + 0.6, P, 2), { tone: "lo", crease: "none" }));
  // regla de distancias sobre la orilla trasera
  if (D) {
    const L_m = D.entradas.L_m, paso = Math.pow(10, Math.floor(Math.log10(L_m / 5)));
    for (let xm = 0; xm <= L_m + 1e-6; xm += paso) {
      const xw = RIO.x + LX * xm / L_m, may = Math.round(xm / paso) % 5 === 0;
      o.push(L(k.segment([xw, RIO.y - 2, Z_ORILLA], [xw, RIO.y - (may ? 10 : 6), Z_ORILLA], P), { tone: may ? "mid" : "lo" }));
      if (may) o.push(k.faceTextSvg(k.topMatrix([xw - 6, RIO.y - 16], Z_ORILLA, P, "x"), nf(xm, 0) + " m", { size: 4, tone: "lo" }));
    }
  }
  // agua: celdas coloreadas por concentración del cuadro actual
  const celdas = [];
  const modo = (document.querySelector("#modo") || {}).value || "ambos";
  if (D && modo !== "venas") {
    const C = D.C_mg_l[cuadro], ny = C.length, nx = C[0].length, cmax0 = Math.max(D.C_max_mg_l[0], 1e-9), cmin = Math.max((D.umbral_mg_l || cmax0 / 100) / 10, cmax0 / 1e4), dx = LX / nx, dy = BX / ny;
    for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) {
      const c = C[j][i], f = c > cmin ? Math.log10(c / cmin) / Math.log10(cmax0 / cmin) : 0, col = color(f > 0 ? Math.max(f, 0.08) : 0);
      const x0 = RIO.x + i * dx, y0 = RIO.y + j * dy;
      const pts = [[x0, y0], [x0 + dx, y0], [x0 + dx, y0 + dy], [x0, y0 + dy]].map(([x, y]) => at([x, y, Z_AGUA]));
      celdas.push(`<path d="M${pts.map((p) => p[0].toFixed(1) + "," + p[1].toFixed(1)).join("L")}Z" fill="${col || AGUA}" fill-opacity="${col ? (modo === "ambos" ? 0.6 : 0.92) : 0.9}" stroke="none"/>`);
    }
  } else {
    const pts = [[RIO.x, RIO.y], [RIO.x + LX, RIO.y], [RIO.x + LX, RIO.y + BX], [RIO.x, RIO.y + BX]].map(([x, y]) => at([x, y, Z_AGUA]));
    celdas.push(`<path d="M${pts.map((p) => p.join(",")).join("L")}Z" fill="${AGUA}" fill-opacity="0.9"/>`);
  }
  o.push(celdas.join(""));
  if (D && D.venas && modo !== "mancha") {                                       // venas: cada partícula es un trazo desde su posición anterior (rápidas = trazos largos)
    const V = D.venas, xs = V.x_m[cuadro], ys = V.y_m[cuadro], vr = V.v_rel[cuadro], Lm = D.entradas.L_m, Bm = D.entradas.B_m, pts = [];
    const xa = cuadro > 0 ? V.x_m[cuadro - 1] : null, ya = cuadro > 0 ? V.y_m[cuadro - 1] : null;
    const tono = (v) => { const f = Math.min(1, Math.max(0, (v - 0.3) / 1.3)), a = [150, 150, 152], b = [24, 24, 25]; return "rgb(" + a.map((c, i) => Math.round(c + (b[i] - c) * f)).join(",") + ")"; };
    for (let i = 0; i < xs.length; i++) {
      if (xs[i] < 0 || xs[i] > Lm) continue;
      const p = at([RIO.x + LX * xs[i] / Lm, RIO.y + BX * ys[i] / Bm, Z_AGUA + 0.4]), c = tono(vr[i]);
      if (xa) {
        const q = at([RIO.x + LX * Math.max(0, xa[i]) / Lm, RIO.y + BX * ya[i] / Bm, Z_AGUA + 0.4]);
        pts.push(`<path d="M${q[0].toFixed(1)},${q[1].toFixed(1)}L${p[0].toFixed(1)},${p[1].toFixed(1)}" stroke="${c}" stroke-width="0.7" stroke-opacity="0.75" stroke-linecap="round"/>`);
      }
      pts.push(`<circle cx="${p[0].toFixed(1)}" cy="${p[1].toFixed(1)}" r="0.7" fill="${c}"/>`);
    }
    o.push(pts.join(""));
  }
  o.push(L(k.planOutline(RIO, Z_AGUA, P, 2), { tone: "faint" }));
  // bidón del derrame en la orilla trasera (o boya al centro) en x0
  if (D) {
    const xw = RIO.x + LX * D.entradas.x0_m / D.entradas.L_m + 8, en_orilla = D.entradas.y0_frac === 0;
    const yb = en_orilla ? RIO.y - ORI / 2 : RIO.y + BX / 2, zb = en_orilla ? Z_ORILLA : Z_AGUA;
    o.push(S(k.cylinder(xw, yb, 6, zb, 14, P, 24), { tone: "hi", lit: true }));
    o.push(L(k.ring(xw, yb, 6, zb + 10, P, 24), { tone: "lo" }), L(k.ring(xw, yb, 6, zb + 4, P, 24), { tone: "lo" }));
    o.push(k.dotsSvg([at([xw, yb, zb + 14])], { size: 0.8 }));
  }
  // orilla delantera (baja, para ver el agua) y placa de rótulo
  o.push(S(k.slabOf({ x: RIO.x, y: RIO.y + BX, w: LX, d: 8, r: 1 }, 0, Z_AGUA + 1.5, P, 2, 0.4), { tone: "mid" }));
  o.push(k.faceTextSvg(k.topMatrix([PLACA.x + 12, PLACA.y + PLACA.d - 10], 0, P, "x"), "DISPERSIÓN DE UN DERRAME · ESCALA TRANSVERSAL EXAGERADA", { size: 4.2, tone: "lo" }));
  return k.figureSvg ? `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">${o.join("")}</svg>` : "";
}

function pintar() {
  $("#fig").innerHTML = escena();
  if (!D) return;
  const t = D.t_s[cuadro] / 3600, cm = D.C_max_mg_l[cuadro], h = D.hidraulica;
  $("#tt").textContent = `t = ${nf(t, 2)} h`;
  $("#cmaxEtq").textContent = `escala log: desde ${nf(Math.max((D.umbral_mg_l || D.C_max_mg_l[0] / 100) / 10, D.C_max_mg_l[0] / 1e4), 2)} hasta ${nf(D.C_max_mg_l[0], 1)} mg/L (C máx inicial)`;
  const sobre = D.tramo_sobre_umbral_m ? D.tramo_sobre_umbral_m[cuadro] : null;
  $("#lect").innerHTML = [["Velocidad U", nf(h.U_ms, 2) + " m/s"], ["Caudal Q", nf(h.Q_m3s, 1) + " m³/s"], ["K longitudinal", nf(D.K_m2s, 1) + " m²/s"], ["ε transversal", nf(D.epsilon_t_m2s, 3) + " m²/s"],
    ["C máxima ahora", nf(cm, 2) + " mg/L"], ["Pico en", nf(D.x_pico_m[cuadro], 0) + " m"], ["Tramo sobre el umbral", sobre == null ? "—" : nf(sobre, 0) + " m"], ["Mezcla transversal completa", nf(D.distancia_mezcla_transversal_m, 0) + " m"],
    ["Zona de venas (advectiva)", D.venas ? "≈ " + nf(D.venas.tiempo_zona_advectiva_s / 60, 0) + " min" : "—"], ["K de las partículas", D.venas ? nf(D.venas.K_particulas_m2s, 1) + " m²/s" : "—"],
    ["K de la fórmula", nf(D.K_m2s, 1) + " m²/s"], ["Etapa", D.venas ? (D.t_s[cuadro] < D.venas.tiempo_zona_advectiva_s ? "venas (zona advectiva)" : "mancha (dispersión)") : "—"]]
    .map(([a, b]) => `<div>${a}<b>${b}</b></div>`).join("");
}

function entradas() {
  return { M_kg: +$("#M").value, B: +$("#B").value, h: +$("#h").value, S: +$("#S").value, n: +$("#n").value, L_m: +$("#L").value, t_h: +$("#t").value,
           k_dia: +$("#k").value, y0_frac: +$("#y0").value, metodo: $("#met").value, umbral_mg_l: +$("#u").value || null, venas: true, irregularidad: +$("#irr").value };
}

async function calcular() {
  $("#msg").textContent = "Calculando…";
  const r = await fetch("/api/contaminantes/calcular?p=" + encodeURIComponent(JSON.stringify(entradas()))).then((x) => x.json());
  if (r.error) { $("#msg").textContent = r.error; return; }
  D = r; cuadro = 0; $("#ti").max = D.t_s.length - 1; $("#ti").value = 0; $("#msg").textContent = "";
  $("#refs").innerHTML = D.referencias.map((x) => `<li>${x.texto} ${x.doi.startsWith("10.") ? `<a href="https://doi.org/${x.doi}" target="_blank" rel="noopener">doi:${x.doi}</a>` : `(${x.doi})`} — ${x.uso}</li>`).join("");
  pintar(); jugar(true);
}

function jugar(on) {
  clearInterval(timer); timer = null; $("#play").textContent = "▶";
  if (on && D) { $("#play").textContent = "■"; timer = setInterval(() => { cuadro = (cuadro + 1) % D.t_s.length; $("#ti").value = cuadro; pintar(); if (cuadro === D.t_s.length - 1) jugar(false); }, 220); }
}

$("#f").onsubmit = (e) => { e.preventDefault(); calcular(); };
$("#ti").oninput = (e) => { jugar(false); cuadro = +e.target.value; pintar(); };
$("#play").onclick = () => jugar(!timer);
$("#modo").onchange = () => pintar();
$("#pgo").onclick = async () => {
  $("#pmsg").textContent = "Trazando el cauce y dibujando…";
  const r = await fetch("/api/contaminantes/planta", { method: "POST", headers: { "Content-Type": "application/json", "X-UCECLIMA-TOKEN": window.TOKEN },
    body: JSON.stringify({ lon: +$("#plon").value, lat: +$("#plat").value, exagerar_ancho: +$("#pexa").value || 8, params: entradas() }) }).then((x) => x.json());
  if (r.error) { $("#pmsg").textContent = r.error; return; }
  $("#pmsg").textContent = `Cauce trazado: ${nf(r.longitud_cauce_trazado_m, 0)} m.`;
  $("#pfig").innerHTML = `<img alt="Mancha en planta" style="width:100%;border-radius:8px" src="/api/proyecto/archivo.png?f=${encodeURIComponent(r.figura)}&t=${Date.now()}">`;
};
$("#g").onclick = async () => {
  const r = await fetch("/api/contaminantes/guardar", { method: "POST", headers: { "Content-Type": "application/json", "X-UCECLIMA-TOKEN": window.TOKEN }, body: JSON.stringify(entradas()) }).then((x) => x.json());
  $("#msg").textContent = r.error ? r.error : "Guardado: " + r.archivo;
};
pintar(); calcular();
