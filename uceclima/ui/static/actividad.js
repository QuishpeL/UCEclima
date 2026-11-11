/* Panel «Actividad en vivo»: muestra lo que hacen la IA/API, las descargas y las corridas en tiempo real, y puede seguir al agente cambiando de módulo. */
(() => {
  "use strict";
  const KEY = "uceclima_seguir";
  let seguir = true; try { seguir = localStorage.getItem(KEY) !== "0"; } catch (e) {}
  let abierto = false, ultimo = null, cierre = null, items = [], ocupado = false;
  const el = document.createElement("aside");
  el.id = "actividad"; el.className = "plegado"; el.setAttribute("aria-label", "Actividad en vivo");
  el.innerHTML = `<header><span class="dot" aria-hidden="true"></span><b>Actividad en vivo</b><span class="est" id="actEst"></span>
    <label class="seg" title="La pantalla cambia al módulo en el que trabaja la IA"><input type="checkbox" id="actSeguir"> Seguir al agente</label><button id="actMin" aria-label="Plegar o desplegar" title="Plegar o desplegar">+</button></header>
    <ol id="actLista"><li class="vacio">Esperando actividad…</li></ol>`;
  document.body.appendChild(el);
  const css = document.createElement("style");
  css.textContent = `#actividad{position:fixed;right:16px;bottom:16px;width:390px;max-width:calc(100vw - 32px);z-index:60;background:rgba(12,20,32,.92);border:1px solid #26384f;border-radius:14px;backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);box-shadow:0 10px 36px rgba(0,0,0,.5);font-family:"Calibri Light",Calibri,Arial,sans-serif;color:#e6edf5;overflow:hidden}
  #actividad header{display:flex;align-items:center;gap:8px;padding:9px 12px;border-bottom:1px solid #26384f;font-size:14px}
  #actividad .dot{width:9px;height:9px;border-radius:50%;background:#7bd88f;box-shadow:0 0 10px #7bd88f;animation:pulso 1.6s infinite}
  #actividad.trabajando .dot{background:#ff2d95;box-shadow:0 0 12px #ff2d95;animation-duration:.8s}
  @keyframes pulso{50%{opacity:.35}} @media (prefers-reduced-motion:reduce){#actividad .dot{animation:none}}
  #actividad .est{flex:1;color:#93a4b8;font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  #actividad .seg{font-size:12px;color:#93a4b8;display:flex;gap:5px;align-items:center;margin:0;cursor:pointer;white-space:nowrap}
  #actividad .seg input{accent-color:#ff2d95}
  #actividad button{all:unset;cursor:pointer;padding:0 6px;color:#93a4b8;font-size:18px;line-height:1}
  #actividad ol{list-style:none;margin:0;padding:6px 0;max-height:300px;overflow:auto}
  #actividad.plegado ol{display:none}
  #actividad li{display:grid;grid-template-columns:54px 1fr;gap:8px;padding:6px 12px;border-bottom:1px solid rgba(38,56,79,.5);font-size:13px;animation:entra .35s}
  @keyframes entra{from{background:rgba(108,196,236,.18)}}
  #actividad li .t{color:#6f87a3;font-variant-numeric:tabular-nums;font-size:12px}
  #actividad li .o{display:inline-block;font-size:10.5px;padding:0 6px;border-radius:999px;border:1px solid #2d4058;color:#93a4b8;margin-right:6px;vertical-align:1px}
  #actividad li.error .tit{color:#ff8a7a} #actividad li.ok .tit{color:#7bd88f} #actividad li.aviso .tit{color:#e8b84d}
  #actividad li .det{display:block;color:#6f87a3;font-size:11.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  #actividad li.vacio{display:block;color:#6f87a3}
  @media (max-width:900px){#actividad{width:calc(100vw - 32px)}}`;
  document.head.appendChild(css);
  const $a = s => el.querySelector(s);
  $a("#actSeguir").checked = seguir;
  $a("#actSeguir").onchange = e => { seguir = e.target.checked; try { localStorage.setItem(KEY, seguir ? "1" : "0"); } catch (x) {} };
  $a("#actMin").onclick = () => { abierto = !abierto; el.classList.toggle("plegado", !abierto); $a("#actMin").textContent = abierto ? "–" : "+"; };
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
  function pintar() {
    $a("#actLista").innerHTML = items.length ? items.map(e => `<li class="${esc(e.nivel)}"><span class="t">${esc(e.t)}</span><span><span class="o">${esc(e.origen)}</span><span class="tit">${esc(e.titulo)}</span>${e.detalle ? `<span class="det" title="${esc(e.detalle)}">${esc(e.detalle)}</span>` : ""}</span></li>`).join("") : '<li class="vacio">Esperando actividad…</li>';
  }
  async function sondear() {
    if (ocupado) return; ocupado = true;
    try {
      const r = await (await fetch("/api/actividad?desde=" + (ultimo === null ? 0 : ultimo))).json();
      const nuevos = r.eventos || [];
      if (ultimo === null) { items = nuevos.slice(-8).reverse(); }
      else if (nuevos.length) {
        items = nuevos.slice().reverse().concat(items).slice(0, 40);
        if (nuevos.some(e => e.origen !== "interfaz")) { abierto = true; el.classList.remove("plegado"); $a("#actMin").textContent = "–"; clearTimeout(cierre); cierre = setTimeout(() => { abierto = false; el.classList.add("plegado"); $a("#actMin").textContent = "+"; }, 30000); }
        if (seguir) { const ult = nuevos.filter(e => e.modulo && e.origen === "IA / API").pop(); if (ult && location.hash !== "#/" + ult.modulo) location.hash = "#/" + ult.modulo; }
        const ia = nuevos.filter(e => e.origen === "IA / API" && e.titulo && !/^Probó|^Revisó/.test(e.titulo)).pop(); if (ia && window.aviso) window.aviso("IA: " + ia.titulo, 3500);
      }
      ultimo = r.ultimo; if (nuevos.length || ultimo !== null) pintar();
      const activo = r.corrida_activa || r.descarga_activa;
      el.classList.toggle("trabajando", !!activo);
      $a("#actEst").textContent = r.corrida_activa ? "corrida en curso…" : r.descarga_activa ? "descargando…" : (items[0] ? items[0].titulo : "");
    } catch (e) { $a("#actEst").textContent = "sin conexión con el programa"; }
    ocupado = false;
  }
  sondear(); setInterval(sondear, 1200);
})();
