/* 4 · IDF INAMHI (X) — ecuaciones, cuadros y curvas del libro del INAMHI para el sitio del proyecto: la lluvia de diseño de las CONDICIONES EXISTENTES (X).
   Condición histórica, sin cambio climático; el cambio climático (Y) se aplica aparte, en CMIP6. */
(() => {
  "use strict";
  const ST = {estacion: null, modo: "auto", dur: 180, tr: 100, tabla: null};
  const MOD = {estacion: "Estación (cuadro exacto del libro)", escalada: "Escalada al sitio", sitio: "Ecuaciones de la zona con el Idtr del sitio"};

  async function vIdf() {
    const P = document.querySelector("#principal");
    P.innerHTML = '<div class="fila"><div><label for="idfPto">Punto de la IDF</label><select id="idfPto"><option value="sitio">sitio del proyecto</option><option value="cuenca">centroide de la cuenca activa</option></select></div></div>' + encabezado("4 · IDF (X)", "<b>En Ecuador</b> la IDF sale del libro del INAMHI; <b>en cualquier otro lugar</b>, usa la tarjeta «IDF fuera de Ecuador» (desde CHIRPS o propia). La lluvia de diseño de las <b>condiciones existentes (X)</b> sale del libro oficial del INAMHI: ecuaciones <b>i = K · Idtr · t<sup>−n</sup></b> por zona, cuadros IDF de 72 pluviográficas y 218 estaciones. Aquí eliges la pluviográfica de referencia y el modo, ves las ecuaciones, el cuadro y las curvas, y fijas la IDF como <b>X</b> del proyecto. Es condición histórica: el cambio climático (Y) se aplica aparte, siempre en magenta.") + '<div id="cfgI"></div><div id="idfBody"></div>'; panelConfig("idf", document.querySelector("#cfgI"));
    if (!S.estado.proyecto) { P.querySelector("#idfBody").innerHTML = nota("Primero crea o abre un proyecto en el módulo <b>1 · Proyecto</b>: la IDF se calcula para su sitio.", "pend"); return; }
    P.querySelector("#cfgI").insertAdjacentHTML("afterend", zetaIdf());                // Zeta: IDF en cualquier lugar del mundo
    zetaIdfEventos();
    const sp = document.querySelector("#idfPto"); if (sp) { sp.value = ST.punto || "sitio"; sp.onchange = () => { ST.punto = sp.value; ST.estacion = null; pintar(); }; }
    await pintar();
  }

  function zetaIdf() {
    return `<section class="tarjeta"><h2>IDF fuera de Ecuador o sin IDF oficial (Zeta)</h2>
      <p>El libro del INAMHI solo vale en Ecuador. En cualquier otro lugar elige una de estas dos opciones. La IDF queda como <b>X</b> del proyecto, se guarda con su fuente y los escenarios CMIP6 (Y) la escalan.</p>
      <div class="fila"><button id="zIdfCh">IDF desde CHIRPS (por defecto, sin estaciones)</button></div>
      <p class="chip">Gumbel de los máximos anuales de CHIRPS × 1,13 y coeficientes de duración de Campos (1978). Según los papers, CHIRPS subestima los máximos (≈ −31 %): esta IDF probablemente queda baja.</p>
      <div class="fila"><div class="crece"><label for="zIdfCsv">CSV de una IDF propia (Tr en la 1.ª columna, minutos en los encabezados, mm/h)</label><input type="text" id="zIdfCsv" placeholder="C:\\ruta\\idf.csv"></div><button id="zIdfExa">Examinar…</button></div>
      <div class="fila"><div class="crece"><label for="zIdfFte">Fuente (obligatoria: norma, estudio, estación, método)</label><input type="text" id="zIdfFte" placeholder="p. ej. Norma 5.2-IC, I1/Id = 11, Gumbel de 28 máximos anuales"></div><button class="principal" id="zIdfReg">Registrar IDF propia</button></div>
      <div id="zIdfMsg"></div></section>`;
  }

  function zetaIdfEventos() {
    const q = s => document.querySelector(s), msg = h => { q("#zIdfMsg").innerHTML = h; };
    const ok = j => msg(j.error ? nota(esc(j.error), "err") : nota(`IDF registrada como X: <code>${esc(j.archivo)}</code> · P24 Tr100 = ${fmt(j.p24_tr100_mm, 1)} mm.` + (j.advertencia ? " " + esc(j.advertencia) : ""), j.advertencia ? "pend" : "ok"));
    q("#zIdfCh").onclick = async () => { msg('<p class="chip">Calculando desde CHIRPS…</p>'); ok(await api("/api/idf/desde_chirps", {})); };
    q("#zIdfExa").onclick = async () => { const j = await api("/api/dialogo", {tipo: "archivo"}); if (j.ruta) q("#zIdfCsv").value = j.ruta; };
    q("#zIdfReg").onclick = async () => ok(await api("/api/idf/propia", {archivo: q("#zIdfCsv").value.trim(), fuente: q("#zIdfFte").value.trim(), nombre: "IDF propia"}));
  }

  async function pintar() {
    const body = document.querySelector("#idfBody"); if (!body) return;
    body.innerHTML = '<p class="chip">Leyendo el libro del INAMHI…</p>';
    const q = `?duracion=${ST.dur}&tr=${ST.tr}&punto=${ST.punto || "sitio"}` + (ST.estacion ? `&estacion=${encodeURIComponent(ST.estacion)}` : "");
    const r = await api("/api/idf/x" + q);
    if (r.error) { body.innerHTML = nota(esc(r.error), "err"); return; }
    ST.estacion = r.referencia.codigo; if (ST.modo === "auto") ST.modo = r.modo_auto;
    const tm = r.tablas[ST.modo] || r.tablas[r.modo_auto] || r.tablas.sitio, ref = r.referencia, fij = r.fijada;
    const tabla = t => !t ? '<p class="chip">No disponible para esta estación (falta el Idtr de la Tabla 3 del libro).</p>' : `<div class="tabla-ancha"><table><thead><tr><th>Tr (años)</th>${t.duraciones_min.map(d => `<th class="num">${d} min</th>`).join("")}</tr></thead><tbody>${t.tr.map((tr, i) => `<tr><td><b>${tr}</b></td>${t.intensidad_mmh[i].map(v => `<td class="num">${fmt(v, 1)}</td>`).join("")}</tr>`).join("")}</tbody></table></div><p class="chip">Intensidad en mm/h.</p>`;
    const img = n => `/api/idf/x/png?nombre=${n}&duracion=${ST.dur}&tr=${ST.tr}&estacion=${encodeURIComponent(ST.estacion)}&t=${Date.now()}`;
    body.innerHTML = `
    ${fij ? nota(`<b>IDF X fijada en este proyecto:</b> estación ${esc(fij.estacion || "(más cercana)")} · modo ${esc(fij.modo)} · ${esc(fij.fijada || "")}`, "ok") : nota("Este proyecto aún no tiene confirmada su IDF X (se usa la más cercana en modo automático). Elige y pulsa «Fijar esta IDF como X».", "pend")}
    <section class="tarjeta"><h2>Estación de referencia</h2>
      <p><b>${esc(ref.codigo)} · ${esc(ref.nombre)}</b> · a <b>${fmt(ref.dist_km, 1)} km</b> del sitio (lat ${fmt(r.lat, 4)}, lon ${fmt(r.lon, 4)}) · zona de ecuaciones ${ref.zona ?? "—"} · ${ref.anios ?? "—"} años de registro · ${ref.z_msnm != null ? fmt(ref.z_msnm, 0) + " m s. n. m." : ""}</p>
      <div class="fila"><div><label for="idfEst">Pluviográfica de referencia</label><select id="idfEst">${r.cercanas.map(c => `<option value="${esc(c.codigo)}" ${c.codigo === ST.estacion ? "selected" : ""}>${esc(c.codigo)} · ${esc(c.nombre)} · ${fmt(c.dist_km, 1)} km</option>`).join("")}</select></div>
        <div><label for="idfModo">Modo</label><select id="idfModo">${Object.entries(MOD).map(([k, v]) => `<option value="${k}" ${k === ST.modo ? "selected" : ""}>${esc(v)}</option>`).join("")}</select></div>
        ${campoI("Tr de la tormenta (años)", "idfTr", ST.tr)}${campoI("Duración (min)", "idfDur", ST.dur)}</div>
      <p class="chip">Modo automático del libro: «estación» si hay pluviográfica a ≤ 10 km; si no, «escalada» (cuadro de la estación × Idtr del sitio / Idtr de la estación). Aquí sugiere <b>${esc(MOD[r.modo_auto] || r.modo_auto)}</b>. Elegir «directa» (estación) usa el cuadro exacto de la pluviográfica sin escalar.</p>
      <div class="fila"><button class="principal" id="idfFijar">Fijar esta IDF como X del proyecto</button></div><div id="idfMsg"></div></section>
    <section class="tarjeta"><h2>Ecuaciones de la zona (libro del INAMHI)</h2>
      <p class="chip">${esc(r.metodo)} Idtr del sitio (mm/h, interpolado de las estaciones cercanas): ${Object.entries(r.idtr_sitio).map(([k, v]) => `${k.replace("TR", "Tr")} = <b>${fmt(v, 2)}</b>`).join(" · ")}</p>
      <div class="tabla-ancha"><table><thead><tr><th>Zona</th><th>Tramo</th><th class="num">t desde (min)</th><th class="num">t hasta (min)</th><th class="num">K</th><th class="num">n</th><th class="num">R²</th><th>Ecuación</th></tr></thead><tbody>
        ${r.ecuaciones.map(e => `<tr><td>${e.zona} · ${esc(e.nombre_zona)}</td><td>${e.tramo}</td><td class="num">${fmt(e.t_desde_min, 1)}</td><td class="num">${fmt(e.t_hasta_min, 1)}</td><td class="num">${fmt(e.K, 3)}</td><td class="num">${fmt(e.n, 3)}</td><td class="num">${fmt(e.R2, 3)}</td><td><code>i = ${fmt(e.K, 3)} · Idtr · t<sup>−${fmt(e.n, 3)}</sup></code></td></tr>`).join("")}</tbody></table></div></section>
    <section class="tarjeta"><h2>Cuadro IDF · modo «${esc(ST.modo)}»</h2>${tabla(tm)}
      <details><summary>Comparar los tres modos del libro</summary>${Object.entries(r.tablas).map(([m, t]) => `<h3>${esc(MOD[m])}</h3>${tabla(t)}`).join("")}</details></section>
    <section class="tarjeta"><h2>Curvas y tormenta de diseño</h2>
      <div class="rejilla"><div><img class="mapa" style="width:100%;border-radius:10px" alt="Curvas IDF" src="${img("idf_curvas.png")}"></div><div><img class="mapa" style="width:100%;border-radius:10px" alt="Modos Tr 100" src="${img("idf_modos_tr100.png")}"></div></div>
      <img class="mapa" style="max-width:760px;width:100%;border-radius:10px;margin-top:10px" alt="Tormenta de diseño" src="${img("tormenta_diseno.png")}">
      <p class="chip">Tormenta de bloques alternos de Tr ${r.tormenta.tr} años y ${r.tormenta.duracion_min} min · lluvia de 24 h de la IDF: ${fmt(r.tormenta.p24_mm, 1)} mm.</p></section>
    <section class="tarjeta"><h2>Límites</h2><ul>${r.avisos.map(a => `<li>${esc(a)}</li>`).join("")}</ul></section>`;
    const re = () => { ST.estacion = document.querySelector("#idfEst").value; ST.modo = document.querySelector("#idfModo").value; ST.tr = +document.querySelector("#idfTr").value || 100; ST.dur = +document.querySelector("#idfDur").value || 180; pintar(); };
    ["#idfEst", "#idfModo", "#idfTr", "#idfDur"].forEach(s => document.querySelector(s).addEventListener("change", re));
    document.querySelector("#idfFijar").onclick = async () => {
      const j = await api("/api/idf/x/guardar", {estacion: ST.estacion, modo: ST.modo, tr: ST.tr, duracion_min: ST.dur}); const m = document.querySelector("#idfMsg");
      if (j.error) { m.innerHTML = nota(esc(j.error), "err"); return; }
      m.innerHTML = nota(`IDF X fijada (estación <b>${esc(j.fijada.estacion)}</b>, modo <b>${esc(j.fijada.modo)}</b>). Guardado en <code>${esc(j.carpeta)}</code>: cuadros (CSV y Excel), ecuaciones, estaciones cercanas y gráficas.`, "ok"); aviso("IDF X fijada");
    };
  }
  const campoI = (et, id, v) => `<div><label for="${id}">${et}</label><input type="text" id="${id}" value="${esc(v)}" style="width:110px"></div>`;
  VISTAS.idf = vIdf;
})();
