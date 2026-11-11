# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""Descargas reproducibles, proyecto desde un sitio y selección de eventos con datos descargados. Sin red: las fuentes externas se simulan.
Ejecutar: python -m uceclima.tests.test_descargas"""
import json, sys, tempfile, time, traceback
from pathlib import Path
import numpy as np
import pandas as pd

from uceclima import descargas as D, analisis_eventos as AEV
from uceclima.ui import sitio_api, proyecto as P


def _esperar(g, tmax=20):
    t = time.time()
    while g.activa() and time.time() - t < tmax:
        time.sleep(0.05)


def test_gestor_una_a_la_vez_carpeta_nueva_manifiesto_y_errores():
    with tempfile.TemporaryDirectory() as t:
        def lenta(destino, p, prog):
            prog(0.3, "trabajando"); time.sleep(0.4); (destino / "a.csv").write_text("x,y\n1,2\n", encoding="utf-8"); return {"archivos": ["a.csv"], "fuente": "falsa", "n_dias": 1}
        def mala(destino, p, prog):
            raise D.DescargaError("fuente caída")
        D.FUENTES["_lenta"] = lenta; D.FUENTES["_mala"] = mala
        try:
            g = D.GestorDescargas()
            did = g.iniciar(t, "_lenta", {"x": 1})
            try:
                g.iniciar(t, "_lenta", {}); raise SystemExit("debió rechazar una segunda descarga simultánea")
            except D.DescargaError as e:
                assert "una a la vez" in str(e)
            _esperar(g)
            d = Path(t) / "datos_descargados" / did
            m = json.loads((d / "manifiesto.json").read_text(encoding="utf-8")); assert m["parametros"]["x"] == 1 and m["parametros"]["proyecto"] == str(t) and len(m["sha256"]["a.csv"]) == 64 and m["creado_utc"]
            assert json.loads((d / "estado.json").read_text(encoding="utf-8"))["estado"] == "completado"
            time.sleep(1.1)
            did2 = g.iniciar(t, "_mala", {}); _esperar(g)
            assert did2 != did and json.loads((Path(t) / "datos_descargados" / did2 / "estado.json").read_text(encoding="utf-8"))["estado"] == "fallido"          # carpeta nueva; el fallo queda registrado
            l = D.listar(t); assert {x["estado"] for x in l} == {"completado", "fallido"}
            try:
                g.iniciar(t, "cmip6", {}); raise SystemExit("CMIP6 debe estar bloqueado")
            except D.DescargaError as e:
                assert "bloqueado" in str(e)
        finally:
            D.FUENTES.pop("_lenta", None); D.FUENTES.pop("_mala", None)


def test_utm_y_proyecto_nuevo_desde_un_sitio():
    assert D.utm_epsg(-78.645, -2.585) == 32717 and D.utm_epsg(-76.0, -1.0) == 32718 and D.utm_epsg(-79.6, -2.1) == 32717
    with tempfile.TemporaryDirectory() as t:
        c = sitio_api.crear("Mazar de prueba", -78.645, -2.585, base=t)
        datos, _ = P.abrir(str(c)); assert datos["crs"] == "EPSG:32717" and datos["tipo"] == "real" and (c / "config_climanet.json").exists()
        for malo in ((-60.0, -55.0), (-79.0, 60.0)):
            try:
                sitio_api.crear("Fuera", *malo, base=t); raise SystemExit("debió rechazar un punto fuera de la cobertura de CHIRPS")
            except D.DescargaError:
                pass
        try:
            sitio_api.crear("ab", -78.6, -2.5, base=t); raise SystemExit("nombre muy corto")
        except D.DescargaError:
            pass


def _proyecto_con_datos(t):
    c = sitio_api.crear("Sitio prueba", -78.645, -2.585, base=t)
    rng = np.random.default_rng(11)
    dias = pd.date_range("2010-01-01", "2016-12-31")
    est = np.where(rng.random(len(dias)) < 0.3, rng.gamma(1.0, 6, len(dias)), 0.0)
    est[(dias.month == 3) | (dias.month == 4)] *= 2.5
    base = pd.DataFrame({"fecha": dias.strftime("%Y-%m-%d"), "pixel_mm": est, "media_caja_mm": est * 0.8})
    d = c / "datos_descargados" / "sitio_20260101_000000"; (d / "chirps").mkdir(parents=True); (d / "celec").mkdir()
    base.to_csv(d / "chirps" / "chirps_diario.csv", index=False)
    q = 40 + pd.Series(est * 0.8, index=dias).rolling(3, min_periods=1).sum().shift(2).fillna(0) * 3 + rng.normal(0, 2, len(dias))
    q.iloc[1000] = 9000.0                                                                       # falla de sensor absurda
    pd.DataFrame({"fecha": dias.strftime("%Y-%m-%d"), "cota_msnm": 2100.0, "caudal_m3s": q.values}).to_csv(d / "celec" / "celec_mazar_diario.csv", index=False)
    return c


def test_seleccion_de_eventos_con_datos_descargados():
    with tempfile.TemporaryDirectory() as t:
        c = _proyecto_con_datos(t)
        Pl, _ = AEV.cargar_lluvia(c, "media_caja_mm"); Qc, _ = AEV.cargar_caudal(c, "celec")
        extra = {"CHIRPS_pixel_mm": AEV.cargar_lluvia(c, "pixel_mm")[0]}
        r = AEV.seleccionar(c, Pl, Qc, "CHIRPS", "CELEC", por_bloque=2, extra=extra)
        cr = r["criterios"]
        assert cr["derivados_de_los_datos"] and cr["umbral_pico_lluvia_mm"] > 0 and 1 <= cr["mes_inicio_anio_hidrologico"] <= 12
        assert cr["dias_caudal_sospechoso_anulados"] == 1 and cr["fechas_caudal_sospechoso"] == [(pd.Timestamp("2010-01-01") + pd.Timedelta(days=1000)).date().isoformat()]  # la falla se anula, no se corrige
        sel = r["seleccionados"]; assert len(sel) >= 4 and set(sel["rol"]) == {"calibracion", "validacion"} and (sel["V_directo_hm3"].dropna() >= 0).all()
        assert r["hidrogramas"] == len(sel)
        h = pd.read_csv(next((Path(r["carpeta"]) / "hidrogramas").glob("*.csv"))); assert {"fecha", "Q_m3s", "lluvia_serie_mm", "CHIRPS_pixel_mm"} <= set(h.columns)
        # los bloques de año hidrológico no se comparten entre calibración y validación
        bl = pd.read_csv(Path(r["carpeta"]) / "bloques.csv"); assert bl["rol"].nunique() == 2
        assert all(f"-21 d" or True for _ in [0]) and (pd.to_datetime(sel["fecha_pico_lluvia"]) - pd.to_datetime(sel["ventana_chirps_inicio"])).dt.days.eq(21).all()
        from uceclima import seleccion_eventos as SE
        assert SE.anio_hidrologico.__defaults__ == (8,)                                    # el cambio temporal del año hidrológico se restauró
        try:
            AEV.seleccionar(c, Pl.iloc[:100], Qc.iloc[:100], "a", "b"); raise SystemExit("poco traslape debía fallar")
        except AEV.AnalisisError:
            pass


def test_series_tendencia_y_graficas_del_proyecto():
    from uceclima import series_api as SER
    # Mann-Kendall + Sen: tendencia creciente clara, serie sin tendencia y serie corta
    t = SER.mann_kendall(np.arange(20) * 2.0 + np.random.default_rng(1).normal(0, 1, 20)); assert abs(t["sen_por_anio"] - 2.0) < 0.5 and t["p"] < 0.001 and t["tau"] > 0.9
    r = SER.mann_kendall(np.random.default_rng(2).normal(100, 5, 30)); assert r["p"] > 0.05
    assert SER.mann_kendall([1, 2, 3])["sen_por_anio"] is None
    with tempfile.TemporaryDirectory() as tmp:
        c = _proyecto_con_datos(tmp)
        cat = {x["id"]: x for x in SER.catalogo(c)}; assert {"chirps:media_caja_mm", "celec:caudal_m3s", "celec:cota_msnm"} <= set(cat)
        rr = SER.lluvia(c, "chirps:media_caja_mm"); assert rr["años_completos"] == 7 and len(rr["clima_mensual"]["media"]) == 12 and rr["tendencia_total"]["n"] == 7 and rr["tendencia_total"]["sen_por_anio"] is None   # 7 años < 8: no se estima tendencia
        Pl, _ = AEV.cargar_lluvia(c); Qc, _ = AEV.cargar_caudal(c); AEV.seleccionar(c, Pl, Qc, "CHIRPS", "CELEC")
        q = SER.caudal(c, "celec:caudal_m3s"); assert len(q["q"]) == len(pd.date_range("2010-01-01", "2016-12-31")) and q["sospechosos"] and len(q["eventos"]) >= 4 and len(q["fdc"]) == 101 and q["fdc"][0] >= q["fdc"][-1]
        e = SER.evento(c, q["eventos"][0]["evento"]); assert len(e["fecha"]) == len(e["caudal_m3s"]) == len(e["lluvia_mm"]) and e["meta"]["rol"] in ("calibracion", "validacion")
        try:
            SER.evento(c, "P999"); raise SystemExit("evento inexistente debía fallar")
        except SER.SerieError:
            pass


def test_bitacora_de_actividad_en_vivo():
    from uceclima.ui import servidor as SV
    n0 = SV.ESTADO.seq
    SV.ESTADO.log("Prueba", "detalle", "series", "ok", "IA / API")
    ev = [e for e in SV.ESTADO.actividad if e["n"] > n0]
    assert len(ev) == 1 and ev[0]["titulo"] == "Prueba" and ev[0]["modulo"] == "series" and ev[0]["origen"] == "IA / API"
    for i in range(450):
        SV.ESTADO.log(f"x{i}")
    assert len(SV.ESTADO.actividad) == 400                                                        # la bitácora tiene tope: no crece sin límite


def test_cn_manning_tablas_de_milagro_y_prioridad_del_usuario():
    from uceclima import parametros_gee as PG
    assert set(PG.CN) == set(PG.NMAP) and all(len(v) == 4 for v in PG.CN.values()) and set(PG.HSG) == set(range(1, 13)) and set(PG.HSG.values()) == {1, 2, 3, 4}
    assert PG.CN[80] == (100, 100, 100, 100) and PG.CN[10][0] < PG.CN[10][3] and all(0 < n < 0.2 for n in PG.NMAP.values())              # agua = 100; CN crece del grupo A al D
    m = Path("C:/Users/agdgq/Desktop/MILAGROCODEX/insumos/manifest_insumos.json")
    if m.exists():                                                                                                                          # mismas tablas con que se prepararon los insumos de Milagro
        t = json.loads(m.read_text(encoding="utf-8"))["tablas"]
        assert {int(k): v for k, v in t["manning"].items()} == PG.NMAP and {int(k): v for k, v in t["HSG"].items()} == PG.HSG and {int(k): tuple(v) for k, v in t["CN"].items()} == PG.CN
    with tempfile.TemporaryDirectory() as tmp:
        c = sitio_api.crear("Sitio CN", -78.6, -2.5, base=tmp)
        dest = c / "datos_descargados" / "cn_manning_x"; dest.mkdir(parents=True)
        r = PG.registrar(c, dest, {})
        assert r["estado"] == "registrado"
        cfg = json.loads((c / "config_climanet.json").read_text(encoding="utf-8")); assert cfg["cn_tif"].endswith("cn_gee.tif") and cfg["cn_origen"] == "gee" and list(c.glob("config_climanet.json.*.bak"))
        time.sleep(1.1)
        r2 = PG.registrar(c, dest, {}); assert r2["estado"] == "registrado"                                                                  # los de GEE se pueden reemplazar por otros de GEE
        cfg = json.loads((c / "config_climanet.json").read_text(encoding="utf-8"))
        cfg["cn_tif"] = "datos/mi_cn_detallado.tif"; cfg["cn_origen"] = "usuario"; (c / "config_climanet.json").write_text(json.dumps(cfg), encoding="utf-8")
        r3 = PG.registrar(c, dest, {}); assert r3["estado"] == "conservado_usuario" and "cn_tif" in r3["texto"]                                # lo detallado del usuario tiene prioridad
        assert json.loads((c / "config_climanet.json").read_text(encoding="utf-8"))["cn_tif"] == "datos/mi_cn_detallado.tif"


if __name__ == "__main__":
    fallos = 0
    for nombre, f in list(globals().items()):
        if nombre.startswith("test_"):
            try:
                f(); print("OK   ", nombre)
            except BaseException:
                fallos += 1; print("FALLA", nombre); traceback.print_exc()
    sys.exit(1 if fallos else 0)
