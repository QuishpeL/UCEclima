/* 0 · Preparación de datos — carga Excel/CSV de precipitación y caudal, los deja en MEMORIA y los grafica en esta misma pantalla (series, tendencias, climatología, curva de duración).
   Con eso se pasa al módulo 1 (crear la carpeta del proyecto o abrir una existente). Los archivos crudos no se modifican. */
(() => {
  "use strict";
  const ES = {lluvia: "Lluvia", caudal: "Caudal", nivel: "Nivel / cota"};
  const ST = {ultimo: null};

  async function vPrep() {
    const P = document.querySelector("#principal");
    P.innerHTML = encabezado("0 · Preparación de datos", "Carga tus archivos de <b>precipitación y caudal</b> (Excel o CSV). UCEclima los lee, los <b>guarda en memoria</b> y los <b>grafica aquí mismo</b> (barras anuales con tendencia, climatología, hidrograma y curva de duración). Con eso pasas al módulo <b>1 · Proyecto</b> para crear la carpeta del proyecto. Los archivos originales no se tocan.") + `
    <section class="tarjeta"><h2>1 · Cargar datos</h2>
      <div class="fila"><button class="principal" id="pArch">Elegir archivos… (Excel / CSV)</button><button id="pCarp">Elegir una carpeta…</button></div>
      <div class="fila"><div class="crece"><label for="pRuta">…o escribe/pega una ruta (archivo o carpeta)</label><input type="text" id="pRuta" placeholder="C:\\datos\\precipitacion_M0138.xlsx"></div><button id="pLeer">Leer</button></div>
      <div class="fila"><div><label for="pTipo">Columnas con código de estación (P46, M0024…) son</label><select id="pTipo"><option value="">preguntar</option><option value="lluvia">lluvia</option><option value="caudal">caudal</option><option value="nivel">nivel</option></select></div>
        <p class="chip" style="align-self:end">Carpetas o muchos archivos se leen en segundo plano. Un archivo con columnas código, lon, lat se usa como catálogo de coordenadas.</p></div>
      <p class="chip">Formatos: tabla con una columna de fechas y una o más de valores (lluvia, caudal o nivel), el anuario INAMHI (año/mes × 31 días) y archivos «largos» con una columna de estación. Si no sé qué es una columna, te lo pregunto; no adivino.</p>
      <div id="pRes"></div></section>
    <section class="tarjeta"><h2>2 · En memoria</h2><div id="pMem"></div></section>
    <section class="tarjeta"><h2>3 · Series y tendencias</h2><div id="pGraf"></div></section>
    <section class="tarjeta"><h2>Siguiente paso</h2><p>Con los datos cargados, crea la carpeta del proyecto (o abre una existente). Las series de la memoria se guardan dentro del proyecto con su origen y huella.</p>
      <div class="fila"><a class="btn principal" href="#/proyecto" style="text-decoration:none;display:inline-block">Ir al módulo 1 · Proyecto →</a></div></section>`;
    const leer = async (cuerpo) => {
      const tipo = P.querySelector("#pTipo").value;
      if (cuerpo.carpeta || (cuerpo.archivos || []).length > 3 || tipo) return lote(P, {...cuerpo, tipo_defecto: tipo});
      P.querySelector("#pRes").innerHTML = '<p class="chip">Leyendo…</p>';
      const j = await api("/api/prep/leer", cuerpo);
      if (j.error) { P.querySelector("#pRes").innerHTML = nota(esc(j.error), "err"); return; }
      ST.ultimo = j; pintarResultados(P, j); await refrescar(P);
    };
    P.querySelector("#pArch").onclick = async () => { const d = await api("/api/dialogo", {tipo: "datos"}); if (d.rutas && d.rutas.length) leer({archivos: d.rutas}); };
    P.querySelector("#pCarp").onclick = async () => { const d = await api("/api/dialogo", {tipo: "carpeta"}); if (d.ruta) leer({carpeta: d.ruta}); };
    P.querySelector("#pLeer").onclick = () => {
      const r = P.querySelector("#pRuta").value.trim().replace(/^"|"$/g, ""); if (!r) return;
      leer(/\.(xlsx|xlsm|xls|csv|txt)$/i.test(r) ? {archivos: [r]} : {carpeta: r});
    };
    await refrescar(P);
  }

  async function lote(P, cuerpo) {
    const el = P.querySelector("#pRes");
    const j = await api("/api/prep/lote", cuerpo);
    if (j.error) { el.innerHTML = nota(esc(j.error), "err"); return; }
    const seguir = async () => {
      if (!document.body.contains(el)) return;
      const e = await api("/api/prep/lote");
      const pct = e.total ? Math.round(100 * e.hechos / e.total) : 0;
      el.innerHTML = `<div class="barra-prog" style="margin:6px 0"><i style="width:${pct}%"></i></div>
        <p class="chip">${e.hechos} de ${e.total} archivos · ${e.series} series · ${e.ok} ok · ${e.confirmar} por confirmar · ${e.errores} con error${e.actual ? " · leyendo " + esc(e.actual) : ""}</p>`;
      if (e.activo) return setTimeout(seguir, 1000);
      const conf = e.resultados.filter(r => r.estado === "confirmar"), err = e.resultados.filter(r => r.estado === "error");
      el.innerHTML += (e.catalogo ? nota(`Catálogo: ${e.catalogo.estaciones} estaciones; coordenadas puestas a ${e.catalogo.con_coordenadas} series.`, "ok") : "")
        + (err.length ? `<details><summary>${err.length} archivo(s) con error</summary>${err.map(r => `<div class="nota err"><b>${esc(r.archivo)}</b> · ${esc(r.mensaje)}</div>`).join("")}</details>` : "")
        + conf.slice(0, 20).map(r => `<div class="nota pend" data-conf="${esc(r.ruta)}"><b>${esc(r.archivo)}</b> · ${esc(r.mensaje)}<div class="conf"></div></div>`).join("")
        + (conf.length > 20 ? `<p class="chip">${conf.length - 20} más por confirmar: elige un tipo por defecto y vuelve a leer.</p>` : "");
      conf.slice(0, 20).forEach(r => formConfirmar(P, el.querySelector(`[data-conf="${CSS.escape(r.ruta)}"] .conf`), r));
      await refrescar(P);
    };
    seguir();
  }

  function pintarResultados(P, j) {
    const el = P.querySelector("#pRes");
    const f = r => r.estado === "ok" ? `<div class="nota ok"><b>${esc(r.archivo)}</b> · ${esc(r.mensaje)}${(r.avisos || []).map(a => `<br><span class="chip">${esc(a)}</span>`).join("")}</div>`
      : r.estado === "confirmar" ? `<div class="nota pend" data-conf="${esc(r.ruta)}"><b>${esc(r.archivo)}</b> · ${esc(r.mensaje)}<div class="conf"></div></div>`
      : `<div class="nota err"><b>${esc(r.archivo)}</b> · ${esc(r.mensaje)}</div>`;
    el.innerHTML = `<p class="chip">${j.ok} archivo(s) leído(s) · ${j.por_confirmar} por confirmar · ${j.errores} con error</p>` + j.resultados.map(f).join("");
    j.resultados.filter(r => r.estado === "confirmar").forEach(r => formConfirmar(P, el.querySelector(`[data-conf="${CSS.escape(r.ruta)}"] .conf`), r));
  }

  function formConfirmar(P, cont, r) {
    const opt = (arr, sel) => arr.map(c => `<option value="${esc(c)}" ${c === sel ? "selected" : ""}>${esc(c)}</option>`).join("");
    cont.innerHTML = `<div class="tabla-ancha" style="margin:8px 0"><table><thead><tr>${r.columnas.map(c => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${r.vista.slice(0, 5).map(f => `<tr>${f.map(v => `<td>${esc(String(v).slice(0, 18))}</td>`).join("")}</tr>`).join("")}</tbody></table></div>
      <div class="fila"><div><label>Columna de fechas</label><select class="cf">${opt(r.columnas, r.col_fecha)}</select></div><div><label>Columna de valores</label><select class="cv">${opt(r.candidatos)}</select></div>
      <div><label>¿Qué es?</label><select class="ct">${Object.entries(r.tipos).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("")}</select></div><button class="principal cok">Usar esta configuración</button></div>`;
    cont.querySelector(".cok").onclick = async () => {
      const j = await api("/api/prep/confirmar", {ruta: r.ruta, config: {col_fecha: cont.querySelector(".cf").value, col_valor: cont.querySelector(".cv").value, tipo: cont.querySelector(".ct").value}});
      const x = j.resultado; cont.closest(".nota").outerHTML = x.estado === "ok" ? `<div class="nota ok"><b>${esc(x.archivo)}</b> · ${esc(x.mensaje)}</div>` : `<div class="nota err"><b>${esc(x.archivo)}</b> · ${esc(x.mensaje)}</div>`;
      await refrescar(P);
    };
  }

  async function refrescar(P) {
    const m = await api("/api/prep/memoria"); const el = P.querySelector("#pMem");
    if (!m.series.length) { el.innerHTML = '<div class="nota pend">Aún no hay datos en memoria. Carga archivos arriba.</div>'; P.querySelector("#pGraf").innerHTML = '<p class="chip">Los gráficos aparecen aquí cuando haya series.</p>'; return; }
    const fm = v => v === null || v === undefined ? "—" : fmt(v, 1);
    el.innerHTML = `<div class="tabla-ancha"><table><thead><tr><th>Serie</th><th>Tipo</th><th>Periodo</th><th class="num">Días con dato</th><th class="num">Faltantes %</th><th class="num">Años completos</th><th>Origen</th><th></th></tr></thead><tbody>
      ${m.series.map(s => `<tr><td><b>${esc(s.nombre)}</b></td><td>${esc(ES[s.tipo] || s.tipo)} (${esc(s.unidad)})</td><td>${esc(s.inicio)} → ${esc(s.fin)}</td><td class="num">${fmt(s.n, 0)}</td><td class="num">${fm(s.calidad.faltantes_pct)}</td><td class="num">${s.calidad.anios_completos}/${s.calidad.anios_total}</td><td style="font-size:12px">${esc(s.origen.archivo)}${s.origen.hoja ? " · " + esc(s.origen.hoja) : ""}</td><td><button data-q="${esc(s.id)}" title="Quitar de la memoria">✕</button></td></tr>`).join("")}</tbody></table></div>
      <div class="fila"><button id="pVaciar">Vaciar memoria</button></div><p class="chip">${esc(m.nota)}</p>`;
    el.querySelectorAll("[data-q]").forEach(b => b.onclick = async () => { await api("/api/prep/quitar", {id: b.dataset.q}); refrescar(P); });
    el.querySelector("#pVaciar").onclick = async () => { if (confirm("¿Vaciar toda la memoria del premódulo? Los archivos originales no se tocan.")) { await api("/api/prep/limpiar", {}); refrescar(P); } };
    const cat = await api("/api/prep/catalogo"); const g = P.querySelector("#pGraf"); g.innerHTML = '<div id="serBody"></div>';
    window.SERIES.montar(g.querySelector("#serBody"), cat, {lluvia: "/api/prep/lluvia?id=", caudal: "/api/prep/caudal?id=", evento: "/api/prep/caudal?id=", vacio: "Carga series de lluvia o caudal para verlas aquí."});
  }

  VISTAS.preparacion = vPrep;
})();
