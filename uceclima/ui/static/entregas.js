/* 11 · Resultados y entregas — todo en shapes, CSV/Excel, mapas y figuras, y la carpeta de INSUMOS para los siguientes programas (BCA FEMA y El Niño / La Niña).
   Solo se empaqueta lo que existe; lo que falta se dice. Resultados sin calibrar ni validar. */
(() => {
  "use strict";
  async function vEntregas() {
    const P = document.querySelector("#principal");
    P.innerHTML = encabezado("11 · Resultados y entregas", "Arma <b>una carpeta ordenada</b> con todo lo del proyecto —<b>shapefiles</b> (WGS84 y UTM + GeoPackage), <b>CSV y Excel</b>, <b>mapas</b> y <b>figuras</b>— y, dentro, los <b>insumos para los siguientes programas</b>: <b>BCA FEMA</b> (análisis beneficio–costo) y el software de <b>El Niño / La Niña</b>. Nada se sobrescribe; cada entrega es una carpeta nueva con su manifiesto.") + '<div id="enBody"></div>';
    if (!S.estado.proyecto) { P.querySelector("#enBody").innerHTML = nota("Abre un proyecto (módulo 1) con corridas completadas.", "pend"); return; }
    P.insertAdjacentHTML("beforeend", zetaTarjetas());
    zetaEventos();
    if (window.peligroTarjeta) { P.insertAdjacentHTML("beforeend", window.peligroTarjeta()); window.peligroEventos(); }     // Lambda: calado · velocidad · peligro (TIFF, shapefile, PNG)
    await pintar();
  }
  // ---------------------------------------------------------------- Zeta Z4 (productos ordenados) y Z5 (receta de los papers)
  function zetaTarjetas() {
    return `<div class="rejilla">
     <section class="tarjeta"><h2>Productos ordenados por módulo (Zeta)</h2>
      <p>Cada módulo deja sus <b>shapes, figuras, CSV, rásteres e informe</b> en <code>productos\\NN_modulo\\</code> dentro del proyecto. Se actualiza solo después de cada paso; aquí puedes ordenarlo todo ahora.</p>
      <div class="fila"><button class="principal" id="zProd">Ordenar productos ahora</button></div><div id="zProdMsg"></div></section>
     <section class="tarjeta"><h2>Receta de los papers (Zeta)</h2>
      <p>Qué combinación de <b>estaciones, CHIRPS y CMIP6</b> conviene según el <b>uso</b>, con los diagnósticos de los papers 1–3 calculados con los datos de este proyecto (varianza, número efectivo de modelos, tiempo de emergencia con ruido de la estación).</p>
      <div class="fila"><div class="crece"><label for="zEst">Estación de referencia (opcional; vacío = CHIRPS, por defecto)</label><input type="text" id="zEst" placeholder="vacío = CHIRPS · p. ej. M0037"></div>
       <div><label for="zUso">Uso</label><select id="zUso"><option value="diseno">Lluvia de diseño (IDF, Tr)</option><option value="emergencia" selected>Tiempo de emergencia</option><option value="balance">Balance hídrico</option></select></div>
       <div><label for="zRed">Red de estaciones</label><select id="zRed"><option value="auto" selected>Automática (≥ 3 estaciones = densa)</option><option value="densa">Densa</option><option value="dispersa">Dispersa</option></select></div></div>
      <div class="fila"><button id="zRec">Ver receta</button><button class="principal" id="zCalc">Calcular diagnósticos</button></div><div id="zPapMsg"></div></section></div>`;
  }
  function zetaEventos() {
    const q = s => document.querySelector(s);
    q("#zProd").onclick = async () => { q("#zProdMsg").innerHTML = '<p class="chip">Ordenando…</p>'; const j = await api("/api/productos/generar", {});
      q("#zProdMsg").innerHTML = j.error ? nota(esc(j.error), "err") : nota(`Listo: ${Object.keys(j.modulos || {}).length} módulo(s) en <code>${esc(j.carpeta)}</code>. Abre <code>index.html</code>.`, "ok"); };
    const receta = r => `<table><tbody>${Object.entries(r).filter(([k, v]) => typeof v === "string" && !["uso", "red"].includes(k)).map(([k, v]) => `<tr><th>${esc(k.replace(/_/g, " "))}</th><td>${esc(v)}</td></tr>`).join("")}</tbody></table>
      <p class="chip">${(r.citas_texto || []).map(esc).join(" · ")}</p>`;
    q("#zRec").onclick = async () => { const red = q("#zRed").value === "auto" ? (q("#zEst").value.trim() ? "densa" : "dispersa") : q("#zRed").value;
      const r = await api(`/api/papers/receta?uso=${q("#zUso").value}&red=${red}`); q("#zPapMsg").innerHTML = r.error ? nota(esc(r.error), "err") : receta(r); };
    q("#zCalc").onclick = async () => { const est = q("#zEst").value.trim();
      q("#zPapMsg").innerHTML = '<p class="chip">Calculando (puede tardar un minuto con CMIP6)…</p>';
      const r = await api("/api/papers/receta", {estacion: est, uso: q("#zUso").value, red: q("#zRed").value});
      if (r.error) { q("#zPapMsg").innerHTML = nota(esc(r.error), "err"); return; }
      q("#zPapMsg").innerHTML = nota(`Diagnósticos en <code>${esc(r.carpeta)}</code> (CSV, figuras e informe).`, "ok") + receta(r.receta) + ((r.avisos || []).length ? nota(r.avisos.map(esc).join("<br>"), "pend") : ""); };
  }
  async function pintar(ultima) {
    const body = document.querySelector("#enBody"); if (!body) return;
    const r = await api("/api/entregas"); if (r.error) { body.innerHTML = nota(esc(r.error), "err"); return; }
    const x = r.corridas.filter(c => c.tipo.startsWith("X")), y = r.corridas.filter(c => !c.tipo.startsWith("X"));
    body.innerHTML = `
    <section class="tarjeta"><h2>Armar la entrega</h2>
      <p>Corridas completadas: <b>${x.length}</b> de condiciones existentes (X) y <b style="color:#ff4da6">${y.length}</b> de cambio climático (Y, magenta). ${r.corridas.length ? "" : "Aún no hay corridas: la entrega incluirá solo lluvia y cambio climático."}</p>
      <table><thead><tr><th>Carpeta</th><th>Programa / contenido</th></tr></thead><tbody>
        <tr><td><code>01_resultados</code></td><td>tablas, mapas, figuras, rásteres y shapes de todas las corridas (X frente a Y)</td></tr>
        <tr><td><code>02_BCA_FEMA</code></td><td>${esc(r.programas["02_BCA_FEMA"])}: calado por escenario y por clase, frecuencia (Tr, factor CC), exposición de edificaciones, población y vías</td></tr>
        <tr><td><code>03_ENSO_El_Nino_La_Nina</code></td><td>${esc(r.programas["03_ENSO_El_Nino_La_Nina"])}: lluvia CHIRPS mensual y anual, series del premódulo, índice ONI, factores CMIP6</td></tr></tbody></table>
      <p class="chip">La exposición (edificios, población, vías) usa las capas de «Otras descargas» del módulo 2; si no están bajadas, la entrega lo dice. Un programa más está previsto: se añade como otra carpeta.</p>
      ${r.corridas.length ? `<h3>Corridas que entran en la entrega</h3><div class="fila" style="flex-wrap:wrap;gap:12px">${r.corridas.map(c => `<label class="tog"><input type="checkbox" class="enCor" value="${esc(c.id)}" checked> <span style="color:${c.tipo.startsWith("X") ? "#6cc4ec" : "#ff4da6"}">${c.tipo.startsWith("X") ? "X" : "Y"}</span> ${esc(c.id.replace(/^corrida_/, ""))}</label>`).join("")}</div><p class="chip">Desmarca las corridas de prueba. Los archivos llevan la fecha y hora de cada corrida en el nombre.</p>` : ""}
      <div class="fila"><button class="principal" id="enGo">Armar la carpeta de entrega</button></div><div id="enMsg">${ultima || ""}</div></section>
    <section class="tarjeta"><h2>Entregas anteriores</h2>${r.entregas.length ? `<table><thead><tr><th>Carpeta</th><th>Creada</th><th class="num">Archivos</th><th class="num">Corridas</th></tr></thead><tbody>${r.entregas.map(e => `<tr><td><code>entregas/${esc(e.id)}</code></td><td>${esc(e.creado || "")}</td><td class="num">${e.archivos}</td><td class="num">${e.corridas}</td></tr>`).join("")}</tbody></table>` : '<p class="chip">Todavía no hay entregas.</p>'}</section>
    <section class="tarjeta"><h2>Visor VOTEX 4D</h2><p class="chip">El visor 3D + tiempo solo puede mostrar estados temporales realmente calculados; hoy el solver entrega el máximo (hmax). Abre el <a href="#/visor">Visor 3D de resultados</a> para las capas reales.</p></section>`;
    document.querySelector("#enGo").onclick = async () => {
      const b = document.querySelector("#enGo"); b.disabled = true; document.querySelector("#enMsg").innerHTML = '<p class="chip">Armando la entrega (unos segundos)…</p>';
      const ids = [...document.querySelectorAll(".enCor")].filter(x => x.checked).map(x => x.value);
      const j = await api("/api/entregas/construir", ids.length ? {corridas: ids} : {}); b.disabled = false;
      if (j.error) { document.querySelector("#enMsg").innerHTML = nota(esc(j.error), "err"); return; }
      aviso("Entrega lista");
      pintar(nota(`<b>Entrega lista</b> · ${j.archivos} archivos en <code>${esc(j.ruta_completa)}</code><br><span class="chip">${Object.entries(j.por_carpeta).map(([k, v]) => esc(k) + ": " + v).join(" · ")}</span>${(j.notas || []).length ? "<br><b>Lo que falta:</b><ul>" + j.notas.map(n => `<li>${esc(n)}</li>`).join("") + "</ul>" : ""}`, "ok"));
    };
  }
  VISTAS.entregas = vEntregas;
})();
