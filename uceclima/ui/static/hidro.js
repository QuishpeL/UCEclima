/* 6 · hidro — una sola entrada en el menú con pestañas: Cuenca · Hidrología · Calibración (y Cuencas/canales solo en el proyecto Milagro). */
(() => {
  "use strict";
  const BASE = [["cuenca", "Cuenca"], ["hidrologia", "Hidrología"], ["calibracion", "Calibración"]];
  const leer = () => { try { return localStorage.getItem("uceclima_hidro"); } catch (e) { return null; } };
  async function vHidro() {
    const esMilagro = /milagro/i.test(((S.estado || {}).proyecto || {}).nombre || "");
    const tabs = esMilagro ? BASE.concat([["cuencas", "Cuencas / canales (Milagro)"]]) : BASE;
    let tab = S.hidroTab || leer() || "cuenca";
    if (!tabs.some(t => t[0] === tab)) tab = "cuenca";
    S.hidroTab = tab;
    $("#principal").innerHTML = "";
    await VISTAS[tab]();
    $("#principal").insertAdjacentHTML("afterbegin", `<nav class="pestanas" aria-label="Pestañas de hidro">${tabs.map(([id, t]) => `<button data-htab="${id}" class="${id === tab ? "principal" : ""}" aria-current="${id === tab}">${t}</button>`).join("")}</nav>`);
    document.querySelectorAll("[data-htab]").forEach(b => b.onclick = () => { S.hidroTab = b.dataset.htab; try { localStorage.setItem("uceclima_hidro", S.hidroTab); } catch (e) {} vHidro(); });
  }
  VISTAS.hidro = vHidro;
})();
