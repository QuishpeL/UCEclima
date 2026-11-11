/* 10 · WRF — leer salidas existentes (wrfout o NetCDF) como lluvia X o Y, y preparar una corrida para Linux/WSL. */
(() => {
  "use strict";
  const v = id => (document.getElementById(id) || {}).value?.trim() ?? "";
  const c = (et, id, val = "", w = "") => `<div ${w ? "" : 'class="crece"'}><label for="${id}">${et}</label><input type="text" id="${id}" value="${esc(String(val))}" ${w ? `style="width:${w}"` : ""}></div>`;

  async function vWrf() {
    const P = $("#principal");
    P.innerHTML = encabezado("10 · WRF", "") + '<div id="wrfBody"></div>';
    if (!S.estado.proyecto) { $("#wrfBody").innerHTML = nota("Abre o crea un proyecto.", "pend"); return; }
    await pintar();
  }

  async function pintar() {
    const body = $("#wrfBody"); if (!body) return;
    const l = await api("/api/wrf/lista");
    body.innerHTML = `<div class="rejilla">
     <section class="tarjeta"><h2>Leer salidas WRF</h2>
      <div class="fila"><div class="crece"><label for="wRuta">Carpeta con wrfout_* o archivo NetCDF</label><input type="text" id="wRuta" placeholder="C:\\ruta\\wrfout"></div><button id="wEx">Carpeta…</button><button id="wExA">Archivo…</button></div>
      <div class="fila"><div><label for="wAmb">Ámbito</label><select id="wAmb"><option value="sitio">Celda del sitio</option><option value="cuenca">Media de la cuenca activa</option></select></div>
        <div><label for="wRol">Rol</label><select id="wRol"><option value="X">X · condición existente / reanálisis</option><option value="Y">Y · escenario (magenta)</option></select></div>
        <div><label for="wCor">Corrección de sesgo</label><select id="wCor"><option value="chirps">QQM contra CHIRPS</option><option value="ninguna">Sin corrección</option></select></div>${c("Nombre", "wNom", "")}</div>
      <button class="principal" id="wLeer">Leer</button><div id="wMsg"></div></section>
     <section class="tarjeta"><h2>Preparar corrida WRF (Linux / WSL)</h2>
      <div class="fila">${c("Inicio (UTC)", "wIni", "", "160px")}${c("Fin (UTC)", "wFin", "", "160px")}<div><label for="wFor">Forzante</label><select id="wFor"><option>ERA5</option><option>GFS</option></select></div></div>
      <div class="fila">${c("dx d01 (km)", "wDx", 27, "80px")}${c("Celdas d01, d02, d03", "wTam", "100, 100, 100", "150px")}</div>
      <button class="principal" id="wPrep">Generar namelist y script</button><div id="wPMsg"></div></section></div>
     <section class="tarjeta"><h2>Salidas WRF del proyecto</h2>${(l.salidas || []).length ? l.salidas.map(s => `<div class="tarjeta" style="padding:12px;margin:8px 0">
        <b>${esc(s.nombre)}</b> ${badge(s.rol === "Y" ? "aviso" : "ok", "rol " + s.rol)} · ${esc(s.lectura.seleccion)} · ${esc(s.lectura.inicio)} → ${esc(s.lectura.fin)} · total ${fmt(s.lectura.total_mm, 1)} mm
        · corrección: ${s.correccion.corregido ? "QQM (" + s.correccion.dias_comunes + " días)" : esc(s.correccion.motivo || "no")}
        <img class="mapa" alt="Lluvia WRF" style="max-width:100%;border-radius:8px;margin-top:6px" src="/api/wrf/png?carpeta=${encodeURIComponent(s.carpeta)}">
        <div class="fila"><button data-west="${esc(s.carpeta)}">Usar como estación (forzamiento de land e hidro)</button></div></div>`).join("") : '<p class="chip">Sin salidas leídas.</p>'}</section>
     ${(l.corridas || []).length ? `<section class="tarjeta"><h2>Corridas preparadas</h2><table><thead><tr><th>Carpeta</th><th>Periodo</th><th>Dominios</th><th>Forzante</th></tr></thead><tbody>${l.corridas.map(r => `<tr><td>${esc(r.carpeta)}</td><td>${esc(r.inicio)} → ${esc(r.fin)}</td><td>${r.dominios.map(d => `${esc(d.dominio)} ${d.dx_km} km (${esc(d.celdas)})`).join(" · ")}</td><td>${esc(r.forzante)}</td></tr>`).join("")}</tbody></table></section>` : ""}`;
    $("#wEx").onclick = async () => { const j = await api("/api/dialogo", {tipo: "carpeta"}); if (j.ruta) $("#wRuta").value = j.ruta; };
    $("#wExA").onclick = async () => { const j = await api("/api/dialogo", {tipo: "archivo"}); if (j.ruta) $("#wRuta").value = j.ruta; };
    $("#wLeer").onclick = async () => {
      $("#wMsg").innerHTML = '<p class="chip">Leyendo…</p>';
      const j = await api("/api/wrf/leer", {ruta: v("wRuta"), ambito: $("#wAmb").value, rol: $("#wRol").value, correccion: $("#wCor").value, nombre: v("wNom")});
      $("#wMsg").innerHTML = j.error ? nota(esc(j.error), "err") : nota(`${esc(j.lectura.formato)} · ${j.lectura.n_pasos} pasos · total ${fmt(j.lectura.total_mm, 1)} mm` + (j.lectura.avisos.length ? "<ul>" + j.lectura.avisos.map(a => `<li>${esc(a)}</li>`).join("") + "</ul>" : ""), "ok");
      if (!j.error) setTimeout(pintar, 1200);
    };
    $("#wPrep").onclick = async () => {
      const j = await api("/api/wrf/preparar", {inicio: v("wIni"), fin: v("wFin"), forzante: $("#wFor").value, dx_km: v("wDx"), tam: v("wTam").split(/[,;\s]+/).filter(Boolean).map(Number)});
      $("#wPMsg").innerHTML = j.error ? nota(esc(j.error), "err") : nota(`Listo en <code>${esc(j.carpeta)}</code>: ${j.dominios.map(d => `${esc(d.dominio)} ${d.dx_km} km · ${d.lado_km} km de lado`).join(" · ")} · paso ${j.time_step_s} s.<ol>${j.pasos.map(p => `<li>${esc(p)}</li>`).join("")}</ol>`, "ok");
      if (!j.error) setTimeout(pintar, 2500);
    };
    document.querySelectorAll("[data-west]").forEach(b => b.onclick = async () => { b.disabled = true; const j = await api("/api/wrf/estacion", {carpeta: b.dataset.west}); aviso(j.error || `Estación ${j.estacion.id} creada: elígela como evento observado en 7 · land o como lluvia en hidro.`, 7000); });
  }
  VISTAS.wrf = vWrf;
})();
