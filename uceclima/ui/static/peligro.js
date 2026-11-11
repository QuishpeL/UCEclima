/* Lambda · Botón «Calado, velocidad y peligro»: para una corrida genera GeoTIFF, shapefile y PNG de cada variable y una lámina de 3 paneles con OSM.
   Peligro = calado × velocidad (clases de Australian Rainfall and Runoff 2019). El mar se excluye. Resultados sin calibrar ni validar. */
(() => {
  "use strict";
  window.peligroTarjeta = () => {
    const comp = (S.estado.corridas || []).filter(c => c.estado === "completado");
    return `<section class="tarjeta" id="pelCard"><h2>Mapas de calado, velocidad y peligro</h2>
      <p class="chip">Para la corrida elegida: <b>calado máximo</b>, <b>velocidad máxima</b> y <b>peligro</b> (calado × velocidad, clases ARR 2019: bajo &lt; 0,3 · niños y autos · adultos · extremo &gt; 1,2 m²/s), cada uno en <b>GeoTIFF, shapefile (UTM y WGS84) y PNG</b>, más una lámina de 3 paneles con vías y edificios de OSM y un resumen de km² y edificios por clase. El mar o agua permanente se excluye. Cada vez se crea una carpeta nueva en <code>productos\\13_peligro\\</code>.</p>
      ${comp.length ? `<div class="fila"><div><label for="pelRun">Corrida</label><select id="pelRun">${comp.map(c => `<option value="${esc(c.id)}">${esc(c.id)}</option>`).join("")}<option value="todas">Todas las corridas completadas</option></select></div></div>
      <details><summary>Acercar a una zona (opcional)</summary><div class="fila">${campo("Longitud mínima", "pelX0", "", "-90.33")}${campo("Latitud mínima", "pelY0", "", "-0.76")}${campo("Longitud máxima", "pelX1", "", "-90.29")}${campo("Latitud máxima", "pelY1", "", "-0.72")}</div><p class="chip">Un solo número por casilla, con punto decimal. Vacío = toda el área.</p></details>
      <div class="fila"><button class="principal" id="pelGo">Generar calado, velocidad y peligro</button></div>` : nota("Todavía no hay corridas completadas: ejecuta una en el módulo 7.", "pend")}
      <div id="pelRes"></div></section>`;
  };
  window.peligroEventos = (idInicial) => {
    const go = $("#pelGo"); if (!go) return;
    if (idInicial && $("#pelRun") && [...$("#pelRun").options].some(o => o.value === idInicial)) $("#pelRun").value = idInicial;
    go.onclick = async () => {
      const z = ["#pelX0", "#pelY0", "#pelX1", "#pelY1"].map(s => parseFloat(($(s).value || "").replace(",", ".").replace(/[−–]/g, "-")));
      const zoom = z.every(Number.isFinite) ? z : null;
      if (z.some(Number.isFinite) && !zoom) { $("#pelRes").innerHTML = nota("Para acercar llena las cuatro casillas con un solo número cada una, o déjalas todas vacías.", "err"); return; }
      go.disabled = true; $("#pelRes").innerHTML = '<p class="chip">Generando los mapas (puede tardar un minuto por corrida)…</p>';
      const j = await api("/api/peligro/generar", {id: $("#pelRun").value, zoom}); go.disabled = false;
      if (j.error) { $("#pelRes").innerHTML = nota(esc(j.error), "err"); return; }
      aviso("Mapas de calado, velocidad y peligro listos", 5000);
      $("#pelRes").innerHTML = j.corridas.map(c => `<h3>${esc(c.id)}</h3>
        ${nota(`<b>${c.archivos} archivos</b> en <code>${esc(c.carpeta)}</code> (calado/, velocidad/, peligro/, lámina, resumen y LEEME).${c.mar_excluido ? ` Mar excluido: ${fmt(c.area_mar_km2, 1)} km².` : ""} Terreno de la corrida: ${esc(c.terreno)}.`, "ok")}
        <table><thead><tr><th>Clase de peligro (calado × velocidad)</th><th class="num">Área en tierra (km²)</th><th class="num">Edificios OSM</th></tr></thead><tbody>${c.resumen.map(f => `<tr><td>${esc(f.clase)}</td><td class="num">${fmt(f.area_tierra_km2, 3)}</td><td class="num">${f.edificios_osm != null ? fmt(f.edificios_osm, 0) : "—"}</td></tr>`).join("")}</tbody></table>
        <img class="mapa" alt="Calado, velocidad y peligro" style="max-width:100%;background:#fff;border-radius:8px" src="/api/proyecto/archivo.png?f=${encodeURIComponent(c.lamina)}&t=${Date.now()}">
        <p class="chip">${esc(c.aviso)} El peligro combina el calado máximo y la velocidad máxima de cada celda, que no ocurren a la vez: es una cota superior.</p>`).join("");
    };
  };
})();
