/* 12 · Validación de campo (Zeta, 31-oct-2026; reemplaza a la maqueta hipsométrica). Automático de punta a punta:
   0) Conectar mi hoja (una sola vez): hoja de Google propia + clave que solo conoce esta computadora.
   1) Un clic desde la corrida: encuesta «¿Se inunda?» (español o inglés) con los mapas del modelo (X y Y); se publica sola y devuelve
      el enlace del sitio (p. ej. climalab.net/validacion/e/?z=…), el QR y el mensaje de WhatsApp. También queda el HTML para el teléfono.
   2) Traer respuestas: lee la hoja, incorpora las marcas, contrasta con el calado y genera las láminas.
   No corre el modelo. Es un contraste con conocimiento local, no una validación física. */
(() => {
  "use strict";
  const LSE = "uceclima_campo_endpoint", LSI = "uceclima_campo_idioma";
  const ls = {get: k => { try { return localStorage.getItem(k) || ""; } catch (e) { return ""; } }, set: (k, v) => { try { localStorage.setItem(k, v); } catch (e) {} }};
  const carpetaDe = r => encodeURIComponent(String(r.carpeta || "").split(/[\\/]/).pop());
  const selIdioma = id => `<select id="${id}"><option value="es" ${ls.get(LSI) !== "en" ? "selected" : ""}>Español</option><option value="en" ${ls.get(LSI) === "en" ? "selected" : ""}>English</option></select>`;

  async function vCampo() {
    const P = document.querySelector("#principal");
    P.innerHTML = encabezado("12 · Validación de campo", "Pregunta a la comunidad <b>hasta dónde llega el agua</b> con un mapa en el teléfono. Las respuestas llegan solas a tu hoja y UCEclima las compara con el calado del modelo. "
      + "Es un <b>contraste con conocimiento local</b>, no una validación física: las personas recuerdan eventos reales y el modelo da eventos de diseño sin calibrar.") + '<div id="vcBody"></div>';
    const B = P.querySelector("#vcBody");
    if (!S.estado.proyecto) { B.innerHTML = nota("Abre un proyecto con al menos una corrida 2D completada (módulo 7).", "pend"); return; }
    const [e, cx] = await Promise.all([api("/api/campo/estado"), api("/api/campo/conexion")]);
    if (e.error) { B.innerHTML = nota(esc(e.error), "err"); return; }
    if (!e.corridas.length) { B.innerHTML = nota("Este proyecto aún no tiene corridas con calado máximo. Corre al menos la X (condiciones actuales) en el módulo 7.", "pend"); return; }
    const base = S.campoSel && e.corridas.find(c => c.id === S.campoSel) ? S.campoSel
      : ((e.corridas.filter(c => !c.Y).slice(-1)[0] || e.corridas.slice(-1)[0]).id);
    const op = e.corridas.map(c => `<label class="chip" style="display:inline-flex;gap:6px;align-items:center;margin:2px"><input type="checkbox" class="vcSel" value="${esc(c.id)}">${c.Y ? "Y" : "X"} · ${esc(c.id.replace(/^corrida_/, ""))}${c.Tr ? " · Tr " + c.Tr : ""}${c.P_mm ? " · " + c.P_mm + " mm" : ""}</label>`).join(" ");
    const ult = e.encuestas.length ? e.encuestas[e.encuestas.length - 1] : null;
    const conectada = cx && cx.conectada;
    B.innerHTML = `
    <details class="tarjeta" id="vcConex" ${conectada ? "" : "open"}><summary><b>0 · Conectar mi hoja</b> (una sola vez) · ${conectada ? '<span style="color:#0F766E">✓ conectada</span>' : '<span style="color:#B45309">sin conectar</span>'}</summary>
      <p>Las respuestas llegan a <b>tu</b> hoja de Google y UCEclima las lee con una clave que solo está en esta computadora. Usa una hoja <b>nueva</b>, solo para la validación (no la de otras encuestas).</p>
      <ol><li>Crea una hoja de Google nueva › <b>Extensiones › Apps Script</b>.</li>
        <li>Pega abajo la dirección <code>/exec</code> (si aún no la tienes, implementa primero cualquier código como aplicación web) y toca <b>Conectar</b>: aparece el código con tu clave.</li>
        <li>Copia ese código en el Apps Script (reemplaza todo), guarda y haz <b>Implementar › Administrar implementaciones › ✏️ › Nueva versión</b> (la dirección no cambia). Acceso: «cualquier persona».</li>
        <li>Toca <b>Probar</b>.</li></ol>
      <div class="fila" style="flex-wrap:wrap;gap:12px">
        <div style="flex:1;min-width:320px"><label for="vcEnd">Dirección /exec de tu hoja</label><input id="vcEnd" value="${esc((cx && cx.endpoint) || ls.get(LSE))}" placeholder="https://script.google.com/macros/s/…/exec" style="width:100%"></div>
        <div><label for="vcSitio">Tu sitio (donde está /validacion/e/)</label><input id="vcSitio" value="${esc((cx && cx.sitio) || "https://climalab.net")}" style="min-width:220px"></div>
      </div>
      <div class="fila"><button class="btn principal" id="vcConectar">Conectar</button><button class="btn" id="vcProbar">Probar</button></div>
      <div id="vcConexR"></div>
    </details>
    <section class="tarjeta" style="border-left:5px solid var(--acento,#0B4A8B)"><h2>1 · Validar con la comunidad (un clic)</h2>
      <p>Corrida <b>${esc(base)}</b>${e.corridas.find(c => c.id === base).Y ? " (Y · cambio climático)" : " y sus Y (CMIP6) del mismo Tr, si existen"}. Arma la encuesta con las preguntas completas (frecuencia, altura, qué se afecta, pérdidas, evento más fuerte, duración y medidas), la publica en tu hoja y te da el <b>enlace</b>, el <b>QR</b> y el mensaje de <b>WhatsApp</b>. Funciona en cualquier territorio.</p>
      <div class="fila" style="flex-wrap:wrap;gap:12px;align-items:flex-end">
        <div><label for="vcZona">Zona (título y dirección web)</label><input id="vcZona" value="${esc(S.estado.proyecto.nombre || "")}" style="min-width:240px"></div>
        <div><label for="vcIdi">Idioma de la encuesta</label>${selIdioma("vcIdi")}</div>
        <button class="btn principal" id="vcUno">Generar y publicar la encuesta</button></div>
      <div id="vcUnoR">${ult ? pintarEncuesta(ult, true) : ""}</div>
      <details><summary>Elegir otros mapas del modelo</summary><p class="chip">Si no eliges, va la corrida de arriba y sus Y: ${op}</p>
        <div class="fila"><button class="btn" id="vcGen">Generar con los mapas elegidos</button></div></details>
    </section>
    <section class="tarjeta"><h2>2 · Traer respuestas de la comunidad</h2>
      <p>Lee la hoja, incorpora las marcas al proyecto (respeta las que la gente corrigió o borró en el teléfono), las <b>contrasta</b> con el modelo y genera las <b>láminas</b>. Repítelo cuando quieras; nada se sobrescribe.</p>
      <div class="fila" style="flex-wrap:wrap;gap:12px;align-items:flex-end"><button class="btn principal" id="vcSync" ${conectada ? "" : "disabled"}>Traer respuestas, contrastar y generar láminas</button><div><label for="vcForm">Pestaña de la hoja (opcional)</label><input id="vcForm" placeholder="${esc(ult ? ult.form : "validacion_<zona>")}" style="min-width:220px"></div></div>
      <p class="chip" id="vcSyncR">Marcas en el proyecto: <b>${e.marcas}</b> (${e.se_inunda} «se inunda»).${conectada ? "" : " Conecta tu hoja (paso 0) para traerlas solas."}</p>
      <details><summary>Importar a mano (archivo .geojson de un grupo o .csv de la hoja)</summary>
        <div class="fila"><input id="vcArch" placeholder="C:\\ruta\\marcas_grupo.geojson  o  respuestas.csv" style="flex:1;min-width:320px"><button class="btn" id="vcImp">Importar</button></div></details>
    </section>
    <section class="tarjeta"><h2>3 · Contraste con el modelo</h2>
      <p>Lee el calado máximo del modelo en cada marca (punto: máximo en 3×3 celdas; zona: máximo y media) y lo compara con lo que dijo la comunidad. El modelo «moja» una marca si el calado es ≥ 5 cm.</p>
      <div class="fila"><select id="vcCorr">${e.corridas.map(c => `<option value="${esc(c.id)}" ${c.id === base ? "selected" : ""}>${c.Y ? "Y" : "X"} · ${esc(c.id.replace(/^corrida_/, ""))}${c.Tr ? " · Tr " + c.Tr : ""}</option>`).join("")}</select><button class="btn" id="vcCon">Contrastar otra corrida</button></div>
      <div id="vcConR"></div>
    </section>
    <section class="tarjeta"><h2>4 · Láminas para el informe (como el Taller 3 de Milagro)</h2>
      <p><b>1)</b> Mapa consolidado de las marcas con <b>buffer acumulativo</b> (donde varias se superponen, el color se oscurece), cuadrícula de referencia, altura declarada y lo que dijo la comunidad, sobre la mancha del modelo X; <b>2)</b> la comunidad frente al modelo <b>hoy (X)</b> y <b>con cambio climático (Y)</b>, si hay Y del mismo Tr.</p>
      <div class="fila"><label for="vcRad" style="margin:0">Radio del buffer (m)</label><input id="vcRad" type="number" min="50" max="2000" step="50" value="250" style="width:90px"><button class="btn" id="vcLam">Volver a dibujar</button></div>
      <div id="vcLamR"></div>
    </section>`;
    if (e.ultimo_contraste) pintar(e.ultimo_contraste);
    if (e.ultimas_laminas) pintarLaminas(e.ultimas_laminas);
    const $b = s => B.querySelector(s);
    $b("#vcIdi").onchange = ev => ls.set(LSI, ev.target.value);
    $b("#vcConectar").onclick = async ev => {
      ev.target.disabled = true; const r = await api("/api/campo/conectar", {endpoint: $b("#vcEnd").value.trim(), sitio: $b("#vcSitio").value.trim()}); ev.target.disabled = false;
      if (r.error) { $b("#vcConexR").innerHTML = nota(esc(r.error), "err"); return; }
      ls.set(LSE, r.endpoint);
      $b("#vcConexR").innerHTML = nota(`Copia este código en el Apps Script de tu hoja (reemplaza todo), guarda y haz <b>Nueva versión</b> de la implementación. Luego toca <b>Probar</b>. Copia también en <code>${esc(r.archivo_gs)}</code>.`, "ok")
        + `<textarea id="vcGs" rows="8" style="width:100%;font-family:monospace;font-size:12px" readonly>${esc(r.gs)}</textarea><div class="fila"><button class="btn" id="vcCopiar">Copiar el código</button></div>`;
      $b("#vcCopiar").onclick = async () => { const ta = $b("#vcGs"); ta.select(); try { await navigator.clipboard.writeText(ta.value); aviso("Código copiado"); } catch (x) { document.execCommand("copy"); aviso("Código copiado"); } };
    };
    $b("#vcProbar").onclick = async ev => {
      ev.target.disabled = true; ev.target.textContent = "Probando…"; const r = await api("/api/campo/probar", {}); ev.target.disabled = false; ev.target.textContent = "Probar";
      $b("#vcConexR").innerHTML = r.error ? nota(esc(r.error), "err") : nota(esc(r.mensaje), "ok");
      if (!r.error) setTimeout(vCampo, 1200);
    };
    const generar = async (btn, cuerpo, txt) => {
      btn.disabled = true; btn.textContent = "Generando y publicando…";
      const r = await api("/api/campo/encuesta", Object.assign({zona: $b("#vcZona").value.trim(), idioma: $b("#vcIdi").value}, cuerpo));
      btn.disabled = false; btn.textContent = txt;
      $b("#vcUnoR").innerHTML = r.error ? nota(esc(r.error), "err") : pintarEncuesta(r, false);
    };
    $b("#vcUno").onclick = ev => generar(ev.target, {base}, "Generar y publicar la encuesta");
    $b("#vcGen").onclick = ev => generar(ev.target, {ids: [...B.querySelectorAll(".vcSel:checked")].map(x => x.value)}, "Generar con los mapas elegidos");
    $b("#vcSync").onclick = async ev => {
      const btn = ev.target; btn.disabled = true; btn.textContent = "Trayendo respuestas…";
      const r = await api("/api/campo/sincronizar", {form: $b("#vcForm").value.trim()}); btn.disabled = false; btn.textContent = "Traer respuestas, contrastar y generar láminas";
      if (r.error) { $b("#vcSyncR").innerHTML = `<span style="color:var(--err,#c0392b)">${esc(r.error)}</span>`; return; }
      $b("#vcSyncR").innerHTML = `Pestaña <b>${esc(r.pestana)}</b>: ${r.filas} fila(s) en la hoja → <b>${r.marcas}</b> marca(s) vigentes (${r.se_inunda} «se inunda»)${r.borradas ? ", " + r.borradas + " borrada(s) en el teléfono" : ""}.${r.sin_cambios ? " Sin cambios desde la última vez." : ""}${r.aviso ? " " + esc(r.aviso) : ""}`;
      if (r.contraste) { const c = await api("/api/campo/estado"); if (c.ultimo_contraste) pintar(c.ultimo_contraste); if (c.ultimas_laminas) pintarLaminas(c.ultimas_laminas); }
    };
    $b("#vcLam").onclick = async ev => {
      ev.target.disabled = true; ev.target.textContent = "Dibujando…";
      const r = await api("/api/campo/laminas", {corrida: $b("#vcCorr").value || "", zona: $b("#vcZona").value.trim(), radio_m: +$b("#vcRad").value || 250});
      ev.target.disabled = false; ev.target.textContent = "Volver a dibujar";
      if (r.error) { $b("#vcLamR").innerHTML = nota(esc(r.error), "err"); return; }
      pintarLaminas(r);
    };
    $b("#vcImp").onclick = async () => {
      const r = await api("/api/campo/importar", {archivo: $b("#vcArch").value});
      if (r.error) { $b("#vcSyncR").innerHTML = `<span style="color:var(--err,#c0392b)">${esc(r.error)}</span>`; return; }
      aviso(`Importadas ${r.marcas} marcas (${r.se_inunda} «se inunda»).`); vCampo();
    };
    $b("#vcCon").onclick = async ev => {
      ev.target.disabled = true; const r = await api("/api/campo/contrastar", {corrida: $b("#vcCorr").value}); ev.target.disabled = false;
      if (r.error) { $b("#vcConR").innerHTML = nota(esc(r.error), "err"); return; }
      pintar(r);
    };
  }

  function pintarEncuesta(r, previa) {
    const c = carpetaDe(r);
    const html = `<a href="/api/campo/encuesta.html?c=${c}" target="_blank" rel="noopener">Abrir la encuesta (HTML para el teléfono)</a>`;
    const pub = r.enlace ? `<div class="fila" style="gap:16px;align-items:center;flex-wrap:wrap;margin-top:8px">
        <img src="/api/campo/qr.png?c=${c}&t=${Date.now()}" alt="Código QR de la encuesta" style="width:132px;height:132px;border-radius:8px;background:#fff">
        <div style="flex:1;min-width:260px"><p style="margin:0 0 6px">Enlace para compartir:<br><a href="${esc(r.enlace)}" target="_blank" rel="noopener"><b>${esc(r.enlace)}</b></a></p>
          <div class="fila"><a class="btn principal" href="${esc(r.whatsapp)}" target="_blank" rel="noopener">Compartir por WhatsApp</a><button class="btn" onclick="navigator.clipboard && navigator.clipboard.writeText('${esc(r.enlace)}');aviso('Enlace copiado')">Copiar enlace</button></div></div></div>` : "";
    const sin = !r.enlace ? (r.publicacion_error ? nota(esc(r.publicacion_error), "err") : nota("Sin publicar en línea: conecta tu hoja (paso 0) para obtener el enlace y el QR. Mientras tanto, envía el HTML por WhatsApp.", "pend")) : "";
    return nota(`${previa ? "Última encuesta" : "Lista"}: «${esc(r.titulo)}» · ${r.idioma === "en" ? "English" : "español"} · ${esc((r.capas || []).join(" · "))} · ${html}${r.publicada ? " · publicada " + esc(r.publicada.replace("T", " ")) : ""}`, "ok") + pub + sin;
  }
  function pintar(r) {
    const el = document.querySelector("#vcConR"); if (!el) return;
    const c = carpetaDe(r), a = r.altura || {};
    el.innerHTML = `<table style="max-width:680px"><thead><tr><th></th><th class="num">El modelo moja (≥ 5 cm)</th><th class="num">El modelo queda seco</th></tr></thead><tbody>
      <tr><td>La comunidad dice SE INUNDA</td><td class="num">${r.aciertos} acierto(s)</td><td class="num">${r.omisiones} omisión(es)</td></tr>
      <tr><td>La comunidad dice NO SE INUNDA</td><td class="num">${r.falsas_alarmas} falsa(s) alarma(s)</td><td class="num">${r.aciertos_secos} acierto(s)</td></tr></tbody></table>
      <p>Tasa de detección: <b>${r.tasa_deteccion ?? "—"}</b> · índice de éxito crítico: <b>${r.indice_exito_critico ?? "—"}</b> · fuera del dominio: ${r.fuera_del_dominio} · corrida ${esc(r.corrida)}</p>
      <p>Altura del agua frente al calado del modelo (marcas «se inunda»): coincide ${a["coincide"] || 0} · el modelo subestima ${a["el modelo subestima"] || 0} · sobreestima ${a["el modelo sobreestima"] || 0} · sin dato ${a["sin dato"] || 0}</p>
      ${r.aviso_muestra ? nota(esc(r.aviso_muestra), "pend") : ""}
      <img src="/api/campo/contraste.png?c=${c}&t=${Date.now()}" alt="Mapa del contraste de marcas con el calado del modelo" style="max-width:100%;border-radius:8px">
      <p class="chip">${esc(r.nota)} Archivos (CSV, GeoJSON, PNG) en <code>${esc(r.carpeta)}</code>.</p>`;
  }
  function pintarLaminas(r) {
    const el = document.querySelector("#vcLamR"); if (!el) return;
    const c = carpetaDe(r), t = Date.now();
    const img = (n, alt) => `<a href="/api/campo/lamina.png?c=${c}&n=${n}&t=${t}" target="_blank" rel="noopener"><img src="/api/campo/lamina.png?c=${c}&n=${n}&t=${t}" alt="${alt}" style="max-width:100%;border-radius:8px;margin-top:8px"></a>`;
    el.innerHTML = img(1, "Lámina 1: mapa consolidado de las marcas con buffer acumulativo") + (r.lamina2 ? img(2, "Lámina 2: la comunidad frente al modelo X y Y") : nota("Sin lámina 2: no hay corridas Y (CMIP6) del mismo Tr que la X.", "pend"))
      + `<p class="chip">Corrida X ${esc(r.corrida_X)} · ${r.marcas_en_dominio} marcas en el dominio · ${esc(r.fondo || "")} · PNG y buffer_acumulado.tif en <code>${esc(r.carpeta)}</code></p>`;
  }
  VISTAS.campo = vCampo;
})();
