# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Premódulo de preparación de datos. Ejecutar: python -m uceclima.tests.test_preparacion"""
import json, sys, tempfile, traceback
from pathlib import Path
import numpy as np
import pandas as pd

from uceclima import preparacion as P


def _ancho(carpeta, estaciones=("M0001", "M0002"), anios=(2010, 2011), quitar=((2011, 5),), conflicto=False):
    """Excel ancho tipo anuario INAMHI con los defectos reales: fila de título, encabezados corridos, columna vacía, filas de grupo y faltantes."""
    import calendar, openpyxl
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Hoja1"
    ws.append(["PRECIPITACION"])
    ws.append(["Estacion", "NombreEstacion", "Longitud2", "Latitud2", "altitud", "codigo", "anio", "mes"] + [f"v{i}" for i in range(1, 31)] + ["v31.1"])   # encabezados corridos
    rng = np.random.default_rng(1)
    for e, est in enumerate(estaciones):
        ws.append(["REGION" if e == 0 else "OTRA"])                                                                                         # fila de grupo
        for a in anios:
            for m in range(1, 13):
                if (a, m) in quitar:
                    continue
                nd = calendar.monthrange(a, m)[1]
                dias = [None if rng.random() < 0.02 else round(float(rng.gamma(0.4, 8)), 1) for _ in range(nd)] + [None] * (31 - nd)
                if est == "M0001" and a == 2010 and m == 2:
                    dias[nd - 1] = 5.0                                                                                                       # 29/30 de febrero no existe: no aplica (nd real)
                ws.append([est, None, f"ESTACION {est}", -79.4 + e * 0.1, -0.02 - e * 0.1, 400 + e, est, a, m] + dias)
    p = Path(carpeta) / "anuario.xlsx"; wb.save(p)
    return p


def test_ancho_encabezados_corridos_grupos_y_calidad():
    with tempfile.TemporaryDirectory() as t:
        p = _ancho(t)
        info = P.clasificar_archivo(p); assert info["tipo"] == "precipitacion_ancha_inamhi", info
        r = P.leer_precip_ancha(p)
        cod = {x["codigo"] for x in r["problemas"]}
        assert {"filas_titulo", "filas_de_grupo", "encabezados_corridos"} <= cod, cod
        assert set(r["largo"]["estacion"]) == {"M0001", "M0002"} and r["catalogo"].set_index("estacion").loc["M0001", "nombre"] == "ESTACION M0001"
        assert abs(r["catalogo"].set_index("estacion").loc["M0001", "lon"] + 79.4) < 1e-6 and r["largo"]["fecha"].dt.year.isin([2010, 2011]).all()
        cal = P.calidad_serie(r["largo"])["M0001"]
        assert cal["inicio"] == "2010-01-01" and cal["fin"] == "2011-12-31" and cal["completitud_pct"] < 100 and cal["mayores_huecos"][0]["desde"] == "2011-05-01"     # mayo/2011 no está en el archivo
        assert cal["mayores_huecos"][0]["dias"] >= 31


def test_larga_fusion_y_conflictos_no_se_promedian():
    with tempfile.TemporaryDirectory() as t:
        a = pd.DataFrame({"Estacion": "X1", "Fecha": pd.date_range("2020-01-01", periods=5), "Precipitacion": [1.0, 2.0, np.nan, 4.0, 5.0]})
        b = pd.DataFrame({"Estacion": "X1", "Fecha": pd.date_range("2020-01-02", periods=5), "Precipitacion": [2.0, 3.0, 9.9, 5.0, 6.0]})   # 03: a=NaN,b=3 ; 04: a=4,b=9.9 conflicto
        pa, pb = Path(t) / "a.csv", Path(t) / "b.csv"; a.to_csv(pa, index=False); b.to_csv(pb, index=False)
        ra, rb = P.leer_precip_larga(pa), P.leer_precip_larga(pb)
        u, inf = P.fusionar([("a.csv", ra["largo"]), ("b.csv", rb["largo"])])
        u = u.set_index("fecha")["precipitacion_mm"]
        assert u[pd.Timestamp("2020-01-02")] == 2.0 and u[pd.Timestamp("2020-01-03")] == 3.0                                       # coinciden / se completa desde la otra fuente
        assert np.isnan(u[pd.Timestamp("2020-01-04")]) and inf["conflictos"] == 1 and inf["rellenados_desde_otra_fuente"] == 1       # contradicción: queda vacío
        assert u[pd.Timestamp("2020-01-01")] == 1.0 and u[pd.Timestamp("2020-01-06")] == 6.0 and inf["dias_solo_en_una_fuente"]["a.csv"] == 1


def _inventario(carpeta):
    d = pd.DataFrame({"PROVINCIA": "Guayas", "CANTON": ["Milagro"] * 6, "PARROQUIAS": "Milagro", "LATITUD": [-2.1, -2.1, -2.1, -2.12, -2.3, np.nan], "LONGITUD": [-79.58, -79.58, -79.58, -79.6, -79.9, np.nan],
                      "EVENTO": ["Inundación", "Inundación", "Incendio Estructural", "Lluvias Intensas", "Inundación", "Inundación"],
                      "FECHA DEL EVENTO": pd.to_datetime(["2020-01-10", "2020-01-10", "2020-01-12", "2020-01-20", "2020-02-01", None]),
                      "FAMILIAS AFECTADAS": [30, 30, 0, 5, 10, 1]})
    p = Path(carpeta) / "inv.xlsx"; d.to_excel(p, index=False, sheet_name="Todos_Eventos"); return p


def test_inventario_normaliza_y_marca_problemas():
    with tempfile.TemporaryDirectory() as t:
        p = _inventario(t); assert P.clasificar_archivo(p)["tipo"] == "inventario_eventos"
        r = P.leer_inventario(p)
        cod = {x["codigo"] for x in r["problemas"]}
        assert {"fechas_nulas", "posibles_duplicados", "sin_coordenadas"} <= cod, cod
        assert r["resumen"]["n_eventos"] == 6 and r["resumen"]["n_hidromet"] == 5 and "subregistro" in r["resumen"]["advertencia"]    # el incendio no es hidrometeorológico


def test_contraste_percentil_retorno_y_filtro_de_lugar():
    with tempfile.TemporaryDirectory() as t:
        rng = np.random.default_rng(3)
        idx = pd.date_range("2018-01-01", "2021-12-31"); s = pd.Series(np.where(rng.random(len(idx)) < .3, rng.gamma(1.2, 6, len(idx)), 0.0), index=idx)
        s["2020-01-09":"2020-01-10"] = [80.0, 60.0]; s["2020-02-01"] = np.nan                                                      # tormenta fuerte antes del evento; dato ausente en otro
        inv = P.leer_inventario(_inventario(t))
        c = P.contrastar(s, inv["eventos"], -2.1, -79.58, radio_km=15)
        tab = c["tabla"].drop_duplicates("fecha").set_index("fecha")
        assert "2020-01-10" in tab.index and tab.loc["2020-01-10", "mm_3d"] >= 140 and tab.loc["2020-01-10", "percentil_3d"] > 99                    # la lluvia del evento es extrema
        assert tab.loc["2020-01-10", "retorno_empirico_3d_anios"] >= 1 and "2020-01-12" not in tab.index                              # el incendio no se contrasta
        assert "2020-02-01" not in tab.index or tab.loc["2020-02-01", "dias_con_dato_ventana"] < 3                                     # el dato ausente se nota
        assert c["tasa_por_clase"] and any("causalidad" in a for a in c["avisos"]) and c["resumen"]["eventos_fuera_del_periodo"] == 0
        try:
            P.contrastar(s, inv["eventos"], 10.0, 10.0, radio_km=5); raise SystemExit("sin eventos en el filtro debió fallar")
        except P.PrepError:
            pass


def test_ordenar_y_guardar_no_toca_crudos_y_escribe_carpeta_nueva():
    with tempfile.TemporaryDirectory() as t:
        p = _ancho(t); h0 = P.sha256(p)
        csv = Path(t) / "M0001.csv"; pd.DataFrame({"Estacion": "M0001", "Fecha": pd.date_range("2010-01-01", periods=10), "Precipitacion": 1.5}).to_csv(csv, index=False)
        o = P.ordenar_y_guardar([p, csv], Path(t) / "out", inventario=_inventario(t))
        d = Path(o["carpeta"]); assert d.name.startswith("preparados_") and {"precipitacion_diaria.csv", "estaciones.csv", "informe_calidad.json", "manifest.json", "LEEME_preparacion.txt", "inventario_eventos_normalizado.csv"} <= set(o["archivos"])
        assert P.sha256(p) == h0                                                                                                   # el crudo no cambió
        m = json.loads((d / "manifest.json").read_text(encoding="utf-8")); assert all(len(e["sha256"]) == 64 for e in m["entradas"])
        sal = pd.read_csv(d / "precipitacion_diaria.csv"); assert {"estacion", "fecha", "precipitacion_mm", "bandera", "fuente"} <= set(sal.columns) and sal["precipitacion_mm"].notna().any()
        assert o["fusion"]["conflictos"] >= 0 and "M0001" in o["calidad"]


def test_larga_filas_sin_estacion_se_infieren_solo_si_es_seguro():
    with tempfile.TemporaryDirectory() as t:
        d = pd.DataFrame({"Estacion": ["A1", "A1", None, None, "A1"], "Fecha": pd.date_range("2020-01-01", periods=5), "Precipitacion": [1.0, 2.0, np.nan, np.nan, 3.0]})
        p = Path(t) / "x.csv"; d.to_csv(p, index=False)
        r = P.leer_precip_larga(p)
        assert set(r["largo"]["estacion"]) == {"A1"} and len(r["largo"]) == 5 and r["largo"]["precipitacion_mm"].isna().sum() == 2
        assert any(x["codigo"] == "filas_sin_estacion" and "inferencia" in x["texto"] for x in r["problemas"])
        d.loc[2, "Precipitacion"] = 9.0; d.to_csv(p, index=False)                                   # una lluvia sin estación NO se asigna a nadie
        r = P.leer_precip_larga(p)
        assert 9.0 not in set(r["largo"]["precipitacion_mm"].dropna()) and any(x["codigo"] == "valores_sin_estacion" for x in r["problemas"])


def test_datos_reales_mazar_si_existen():
    d = Path(r"C:\Users\agdgq\Downloads\PREMODULO MAZAR SUR")
    if not d.exists():
        return
    e = P.escanear(d); tipos = {a["archivo"]: a["tipo"] for a in e["archivos"]}
    assert "precipitacion_ancha_inamhi" in tipos.values() and "precipitacion_larga" in tipos.values()
    r = P.leer_precip_ancha(d / "ESTA-RR- (1).xlsx"); assert r["largo"]["estacion"].nunique() == 12 and {"filas_titulo", "filas_de_grupo", "encabezados_corridos"} <= {x["codigo"] for x in r["problemas"]}
    q = P.calidad_serie(r["largo"])["M0138"]; assert 1987 in q["anios_sin_ningun_dato"] and q["max_mm_dia"] == 97.2 and q["fecha_max"] == "1982-03-26"
    c = P.leer_precip_larga(d / "2.preciptacion_M0138_preparado.csv")["largo"]; assert set(c["estacion"]) == {"M0138"}
    u, inf = P.fusionar([("xlsx", r["largo"][r["largo"]["estacion"] == "M0138"]), ("csv", c[c["estacion"] == "M0138"])]); assert inf["conflictos"] == 0 and inf["coinciden"] == 12101


if __name__ == "__main__":
    fallos = 0
    for nombre, f in list(globals().items()):
        if nombre.startswith("test_"):
            try:
                f(); print("OK   ", nombre)
            except BaseException:
                fallos += 1; print("FALLA", nombre); traceback.print_exc()
    sys.exit(1 if fallos else 0)
