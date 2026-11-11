# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""Selección estadística de eventos (lluvia diaria de la estación CUMBE=Milagro, caudal del aforo AJ_CHIMBO/H390 por confirmar). Sin red. Salidas en uceclima/salidas/."""
import json
from pathlib import Path
import numpy as np, pandas as pd, openpyxl
import uceclima
from uceclima import seleccion_eventos as S

H = "C:/Users/agdgq/Desktop/MILAGROCODEX/hms_referencia/"
XLS = r"C:\Users\agdgq\Desktop\Curva-IDF-de-M0037 - INAMHI.xlsx"
OUT = Path(__file__).resolve().parents[1] / "salidas" / "seleccion_eventos_milagro"; OUT.mkdir(parents=True, exist_ok=True)
d = S.cargar_series(H + "Milagro_Precipitation_Hourly_Master_HMS_2003_2014.csv", H + "Milagro_Observed_Daily_Flow_Master_HMS_2003_2014.csv")
ws = openpyxl.load_workbook(XLS, data_only=True)["Registros Pluviómetro"]
g = S.gumbel_sin_correccion([ws.cell(r, 14).value for r in range(4, 35)])
c = S.Criterios()
e = S.filtrar(S.evaluar(d, S.identificar_picos(d, c), g, c), c)
hms = [("HMS EVT_002C", "2004-03-21", "2004-03-30"), ("HMS EVT_006C", "2006-03-09", "2006-03-16"), ("HMS EVT_015C", "2008-04-18", "2008-04-27"),
       ("HMS EVT_026C", "2011-02-01", "2011-02-10"), ("HMS EVT_036C", "2013-03-25", "2013-04-02")]
sel, bl = S.seleccionar_por_bloques(e, hms)
e.to_csv(OUT / "candidatos_todos.csv", index=False); sel.to_csv(OUT / "eventos_seleccionados.csv", index=False); bl.to_csv(OUT / "bloques_anio_hidrologico.csv", index=False)
meta = {"criterios": c.__dict__, "gumbel_maximos_anuales_24h_sin_factor_1.13": g, "periodo": [str(d.fecha.min().date()), str(d.fecha.max().date())],
        "dias": int(len(d)), "dias_lluvia_ausente": int(d.P_mm.isna().sum()), "dias_caudal_ausente": int(d.Q_m3s.isna().sum()),
        "horas_uniformes_dentro_del_dia": d.attrs["horas_uniformes_dentro_del_dia"], "picos_candidatos": int(len(e)), "cumplen": int(e.cumple.sum()), "seleccionados": int(len(sel)),
        "estacion_lluvia": "CUMBE (identificada por el usuario como Milagro, 13-oct-2026; verificación documental pendiente)", "aforo": "AJ_CHIMBO / H390: identidad por confirmar",
        "limites": ["La serie horaria es una desagregación UNIFORME diaria: no hay lluvia subdiaria observada.", "Todos los picos de 2003–2014 tienen Tr ≤ 5,4 años (Gumbel de máximos anuales de 24 h): no hay eventos extremos con caudal en este periodo; 1998 y 2002 (194 y 178 mm) quedan fuera de los datos de caudal.",
                    "Caudal de cuenca grande (Chimbo) frente a lluvia puntual: la correlación lluvia-caudal puede ser débil; el retardo ≥10 d se marca.", "La selección usa solo estadística de los datos, no el ajuste de ningún modelo."]}
(OUT / "resumen_seleccion.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
print(bl.round(2).to_string(index=False)); print(sel[["rol", "evento", "fecha_pico_lluvia", "P_max_dia_mm", "Tr_P_max_dia_anios", "dQ_m3s", "advertencia"]].round(1).to_string(index=False))
