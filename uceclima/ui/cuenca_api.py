# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Rutas de los módulos Cuenca (6) y Calibración (10). Aditivo: el servidor solo delega aquí las rutas /api/cuenca/* y /api/calibracion/*."""
from pathlib import Path

from .. import cuenca as C, calibracion as K, lluvia_areal as LA, calibracion_graficas as CG


def _png(h, b):
    h.send_response(200); h.send_header("Content-Type", "image/png"); h.send_header("Content-Length", str(len(b))); h.send_header("Cache-Control", "no-store"); h.end_headers(); h.wfile.write(b)


def get(h, E, ruta, q, js):
    if not E.datos:
        return js(h, {"error": "Abre un proyecto."}, 400)
    a1 = lambda k, d=None: (q.get(k) or [d])[0]
    try:
        if ruta == "/api/cuenca/estado":
            return js(h, C.estado(E.carpeta))
        if ruta == "/api/cuenca/mapa.png":
            nombre = a1("nombre")
            if nombre and ("/" in nombre or "\\" in nombre or ".." in nombre):
                return js(h, {"error": "nombre inválido"}, 400)
            return _png(h, C.mapa_png(E.carpeta, nombre))
        if ruta == "/api/cuenca/salidas":                                       # C5: salida (aforo) desde estaciones conocidas
            import json as _json
            from .. import estaciones_ref, idf_x
            lat, lon = idf_x.punto(E.datos); out = []
            for e in estaciones_ref.cercanas(lat, lon, n=12)["hidrometricas"]:
                out.append({"nombre": f"{e['codigo']} {e['nombre']} (INAMHI, {e['dist_km']} km del sitio)", "lon": e["lon"], "lat": e["lat"]})
            idx = Path(E.carpeta) / "datos" / "series_premodulo" / "indice.json"
            for m in (_json.loads(idx.read_text(encoding="utf-8")) if idx.exists() else []):
                if m.get("tipo") == "caudal" and m.get("lon") is not None:
                    out.insert(0, {"nombre": f"{m['nombre']} (caudal del proyecto)", "lon": m["lon"], "lat": m["lat"]})
            return js(h, {"salidas": out})
        if ruta == "/api/calibracion/estado":
            return js(h, K.estado(E.carpeta))
        if ruta == "/api/calibracion/barrido":
            import pandas as pd, json
            b = a1("id", "")
            d = Path(E.carpeta) / "calibracion" / "barridos" / b
            if not b.startswith("barrido_") or not (d / "resultados.csv").exists():
                return js(h, {"error": "Barrido no encontrado."}, 404)
            r = pd.read_csv(d / "resultados.csv"); ev = pd.read_csv(d / "eventos.csv")
            return js(h, {"barrido": b, "mejores": r.head(int(a1("n", 25))).round(4).where(r.notna(), None).to_dict("records"), "eventos": ev.to_dict("records"),
                          "config": json.loads((d / "config.json").read_text(encoding="utf-8"))})
        if ruta == "/api/calibracion/estaciones_areal":
            from shapely.geometry import Point
            cu, _a = LA._cuenca(E.carpeta, E.datos["crs"]); r_km = float(a1("radio_km", 10))
            l = [{"id": e["id"], "nombre": e["nombre"], "fuente": e["fuente"], "dentro": cu.contains(Point(e["x"], e["y"])), "dist_km": round(cu.distance(Point(e["x"], e["y"])) / 1000, 2),
                  "dias": int(e["serie"].notna().sum())} for e in LA.estaciones(E.carpeta, E.datos["crs"])]
            return js(h, {"estaciones": sorted([x for x in l if x["dist_km"] <= r_km], key=lambda x: x["dist_km"]), "fuera": len([x for x in l if x["dist_km"] > r_km])})
        if ruta == "/api/calibracion/recesion":
            q, mq = K.observaciones(E.carpeta)
            if q is None:
                return js(h, {"error": mq}, 400)
            p, _ = K.lluvia_cuenca(E.carpeta); q.index = q.index.normalize()
            return js(h, K.k_recesion(q[~q.index.duplicated()], p))
        if ruta in ("/api/calibracion/comparacion", "/api/calibracion/comparacion.png"):
            b = a1("barrido", "")
            if not b.startswith("barrido_") or "/" in b or "\\" in b or ".." in b:
                return js(h, {"error": "barrido inválido"}, 400)
            r = CG.comparar(E.carpeta, b, int(a1("id", 0)))
            if ruta.endswith(".png"):
                f = a1("f", "")
                if f not in r["figuras"]:
                    return js(h, {"error": "figura desconocida"}, 404)
                return _png(h, (Path(E.carpeta) / r["carpeta"] / f).read_bytes())
            return js(h, r)
        if ruta == "/api/calibracion/figura.png":
            b = a1("barrido", "")
            if not b.startswith("barrido_") or "/" in b or "\\" in b or ".." in b:
                return js(h, {"error": "barrido inválido"}, 400)
            return _png(h, K.figura(E.carpeta, b, int(a1("id", 0))))
    except (C.CuencaError, K.CalibracionError, LA.ArealError, ValueError, KeyError, FileNotFoundError, OSError) as e:
        return js(h, {"error": str(e)[:400]}, 400)
    return js(h, {"error": "Ruta desconocida."}, 404)


def post(h, E, ruta, c, js):
    if not E.datos:
        return js(h, {"error": "Abre un proyecto."}, 400)
    if E.gestor and E.gestor.activa():
        return js(h, {"error": "Hay una corrida en curso; espera a que termine."}, 409)
    try:
        if ruta == "/api/cuenca/shape":
            return js(h, C.cargar_shape(E.carpeta, E.datos, c.get("ruta", ""), c.get("crs") or None))
        if ruta == "/api/cuenca/malla":
            return js(h, C.malla_chirps(E.carpeta, E.datos, c.get("medio_km") or None))
        if ruta == "/api/cuenca/activar":
            return js(h, C.activar(E.carpeta, c.get("nombre", ""), c.get("persona") or None))
        if ruta == "/api/calibracion/vista_previa":
            return js(h, K.vista_previa(c.get("ruta", ""), c.get("hoja") or None))
        if ruta == "/api/calibracion/registrar":
            u = c.get("umbral_sospechoso")
            return js(h, K.registrar_observacion(E.carpeta, c.get("ruta", ""), c.get("col_fecha", ""), c.get("col_caudal", ""), c.get("tipo", "desconocido"), c.get("fuente", ""), c.get("estacion", ""),
                                                 bool(c.get("confirmado")), c.get("persona", ""), c.get("nota", ""), c.get("hoja") or None, float(u) if u not in (None, "") else None))
        if ruta == "/api/calibracion/registrar_lluvia":
            return js(h, K.registrar_lluvia(E.carpeta, c.get("ruta", ""), c.get("col_fecha", ""), c.get("col_mm", ""), c.get("estacion", ""), c.get("fuente", ""), c.get("persona", ""), c.get("nota", ""),
                                            c.get("col_estacion") or None, c.get("hoja") or None))
        if ruta == "/api/calibracion/usar_lluvia":
            return js(h, K.usar_lluvia(E.carpeta, c.get("fuente", "")))
        if ruta == "/api/calibracion/lluvia_areal":
            return js(h, LA.registrar(E.carpeta, E.datos, c.get("metodo") or "thiessen", float(c.get("radio_km") or 10), c.get("ids") or None, c.get("persona", "")))
        if ruta == "/api/calibracion/eventos":
            q, mq = K.observaciones(E.carpeta)
            if q is None:
                return js(h, {"error": mq}, 400)
            p, mp_ = K.lluvia_cuenca(E.carpeta)
            if p is None:
                return js(h, {"error": mp_}, 400)
            q.index = q.index.normalize(); q = q[~q.index.duplicated()]
            kw = {k: float(c[k]) if k == "percentil" else int(c[k]) for k in ("percentil", "dias_antes", "dias_despues", "separacion_dias", "max_eventos", "cada_validacion") if c.get(k) not in (None, "")}
            act = Path(E.carpeta) / "cuenca" / "activa.json"
            if act.exists():                                                   # D4: «lluvia dudosa» necesita el área de la cuenca
                import json as _j
                kw["area_km2"] = _j.loads(act.read_text(encoding="utf-8")).get("area_km2")
            return js(h, K.eventos(q, p, **kw))
        if ruta == "/api/calibracion/barrido":
            rng = lambda k, d: tuple(float(x) for x in (c.get(k) or d))
            kr = c.get("k_rec")
            kr = "auto" if (kr == "auto" or (isinstance(kr, list) and "auto" in kr)) else tuple(kr or (None,))
            return js(h, K.barrido(E.carpeta, cn=rng("cn", (50, 90, 9)), lag_h=rng("lag_h", (6, 120, 12)), prf=rng("prf", (484, 284)), lam=rng("lam", (0.2, 0.05)),
                                   eventos_tabla=c.get("eventos") or None, persona=c.get("persona", ""), k_rec=kr, humedad=tuple(c.get("humedad") or ("ninguna",))))
        if ruta == "/api/calibracion/benchmark":                                # D5
            from .. import benchmark as BM
            return js(h, BM.correr(E.carpeta, c.get("pet_mm_d"), c.get("barrido") or None, c.get("id"), c.get("persona", "")))
        if ruta == "/api/calibracion/aceptar":
            return js(h, K.aceptar(E.carpeta, c.get("barrido", ""), int(c.get("id", -1)), c.get("persona", ""), c.get("nota", "")))
    except (C.CuencaError, K.CalibracionError, LA.ArealError, ValueError, KeyError, TypeError, FileNotFoundError, OSError) as e:
        return js(h, {"error": str(e)[:400]}, 400)
    return js(h, {"error": "Ruta desconocida."}, 404)
