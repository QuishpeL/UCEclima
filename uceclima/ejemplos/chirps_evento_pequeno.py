# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Ejemplo pequeño y reproducible: evento fechado de 2 días, 28 subcuencas de Milagro, ventanas ±5 y ±21 días con CHIRPS (v3 DAILY_SAT preferido).
Uso (desde MILAGRO): python -m uceclima.ejemplos.chirps_evento_pequeno [AAAA-MM-DD inicio] [AAAA-MM-DD fin]
Requiere haber autorizado Earth Engine una vez (`earthengine authenticate`). Si no hay acceso: escribe la solicitud reproducible y se detiene."""
import json, sys
from pathlib import Path
import pandas as pd
import uceclima
from uceclima import gee_chirps as G
from uceclima.eventos import Evento
from climanet import cuencas as C

ini = sys.argv[1] if len(sys.argv) > 1 else "2011-02-02"
fin = sys.argv[2] if len(sys.argv) > 2 else "2011-02-04"
ev = Evento(f"evento_{ini}", f"{ini}T00:00:00-05:00", f"{fin}T00:00:00-05:00", "M0037")
plan = ev.plan()
salida = Path(__file__).resolve().parents[1] / "salidas" / ev.nombre; salida.mkdir(parents=True, exist_ok=True)
(salida / "plan_consulta.json").write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
estado, ee = G.iniciar()
print("GEE:", {k: v for k, v in estado.items() if k != "error"}, "| error:", estado["error"])
if ee is None:
    print("BLOQUEADO: sin autenticación de Earth Engine. Solicitud reproducible en", salida / "plan_consulta.json"); sys.exit(2)
disp = G.disponibilidad(plan, ee)
sel = G.seleccionar(plan, disp)
print("producto:", sel.get("version"), "| fallback:", sel.get("fallback"), "| cobertura completa:", sel["cobertura_completa"])
if not sel["cobertura_completa"]:
    print("faltantes:", {k: v["dias_faltantes"][:5] for k, v in sel["diagnostico"].items()}); sys.exit(3)
g, _ = C.leer_capa("supervision_codex/cuencas_zip/archivomxdshapefiles/subcuencas/subcuencas_080726.shp")
_, g = C.diagnostico_geometria(g)
df, carpeta = G.serie_por_cuenca(sel, plan, g, ee)
w = G.ventanas(df, plan)
w.to_csv(salida / "acumulados_por_ventana.csv", index=False)
print("caché:", carpeta)
ev6 = ["MI-010", "BE-030", "BE-040", "MO-030", "MO-020", "BE-010"]
print(w[w.nombre.isin(ev6)].pivot(index="nombre", columns="ventana", values="acumulado_mm").round(1).to_string())
print("manifiesto:", json.loads((carpeta / "manifiesto.json").read_text(encoding="utf-8"))["dias_con_dato"], "días con dato /", json.loads((carpeta / "manifiesto.json").read_text(encoding="utf-8"))["dias"])
