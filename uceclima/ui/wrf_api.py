# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""Rutas de WRF (/api/wrf/*) y del Time of Emergence (/api/cmip6/toe*)."""
import json
from pathlib import Path

from .. import wrf as W, toe as T, cmip6_figuras as CF


def _png(h, b):
    h.send_response(200); h.send_header("Content-Type", "image/png"); h.send_header("Content-Length", str(len(b))); h.send_header("Cache-Control", "no-store"); h.end_headers(); h.wfile.write(b)


def _ultimo_toe(carpeta):
    b = Path(carpeta) / "registro" / "cmip6"
    l = sorted(b.glob("toe_*")) if b.exists() else []
    return l[-1] if l else None


def get(h, E, ruta, q, js):
    if not E.datos:
        return js(h, {"error": "Abre un proyecto."}, 400)
    a1 = lambda k, d=None: (q.get(k) or [d])[0]
    try:
        if ruta == "/api/cmip6/toe":
            d = _ultimo_toe(E.carpeta)
            if not d:
                return js(h, {"toe": None})
            return js(h, {"toe": json.loads((d / "toe_resumen.json").read_text(encoding="utf-8")), "carpeta": d.name})
        if ruta == "/api/cmip6/toe.png":
            d = _ultimo_toe(E.carpeta)
            if not d or not (d / "toe_sn.png").exists():
                return js(h, {"error": "Aún no hay ToE."}, 404)
            return _png(h, (d / "toe_sn.png").read_bytes())
        if ruta == "/api/cmip6/figura.png":                                         # Epsilon: gráficas principales
            nombre = a1("nombre", "")
            if nombre not in ("bondad_qqm", "toe_indicadores", "toe_sn_grande", "toe_cabeza_PRCPTOT", "toe_cabeza_CDD", "toe_cabeza_Rx1day"):
                return js(h, {"error": "figura desconocida"}, 400)
            base = Path(E.carpeta) / "registro" / "cmip6"
            d = CF._ultimo(base, "analisis_*") if nombre == "bondad_qqm" else _ultimo_toe(E.carpeta)
            f = d / f"{nombre}.png" if d else None
            return _png(h, f.read_bytes()) if f and f.exists() else js(h, {"error": "Aún no generada."}, 404)
        if ruta == "/api/wrf/lista":
            base = Path(E.carpeta) / "datos"
            out = []
            for d in sorted(base.glob("wrf_*"), reverse=True) if base.exists() else []:
                if (d / "resumen.json").exists():
                    out.append(json.loads((d / "resumen.json").read_text(encoding="utf-8")))
            cor = sorted((Path(E.carpeta) / "wrf_corridas").glob("corrida_*"), reverse=True) if (Path(E.carpeta) / "wrf_corridas").exists() else []
            return js(h, {"salidas": out, "corridas": [json.loads((c / "LEEME.json").read_text(encoding="utf-8")) for c in cor if (c / "LEEME.json").exists()]})
        if ruta == "/api/wrf/png":
            c = a1("carpeta", "")
            if not c.startswith("datos/wrf_") or ".." in c:
                return js(h, {"error": "carpeta inválida"}, 400)
            f = Path(E.carpeta) / c / "wrf_lluvia.png"
            return _png(h, f.read_bytes()) if f.exists() else js(h, {"error": "sin figura"}, 404)
    except (W.WRFError, T.ToEError, ValueError, KeyError, OSError) as e:
        return js(h, {"error": str(e)[:400]}, 400)
    return js(h, {"error": "Ruta desconocida."}, 404)


def post(h, E, ruta, c, js):
    if not E.datos:
        return js(h, {"error": "Abre un proyecto."}, 400)
    try:
        if ruta == "/api/cmip6/toe":
            u = [float(x) for x in (c.get("umbrales") or (1.0, 2.0))]
            return js(h, T.calcular(E.carpeta, ventana=int(c.get("ventana") or 20), umbrales=tuple(u)))
        if ruta == "/api/cmip6/figuras":                                            # Epsilon: genera las tres gráficas principales
            return js(h, CF.todas(E.carpeta))
        if ruta == "/api/wrf/leer":
            return js(h, W.procesar(E.carpeta, E.datos, c.get("ruta", ""), c.get("ambito") or "sitio", c.get("correccion") or "chirps", c.get("rol") or "X", c.get("nombre") or None))
        if ruta == "/api/wrf/estacion":
            car = c.get("carpeta", "")
            if not car.startswith("datos/wrf_") or ".." in car:
                return js(h, {"error": "carpeta inválida"}, 400)
            return js(h, W.registrar_como_estacion(E.carpeta, E.datos, car))
        if ruta == "/api/wrf/preparar":
            tam = [int(x) for x in (c.get("tam") or (100, 100, 100))]
            return js(h, W.preparar_corrida(E.carpeta, E.datos, c.get("inicio", ""), c.get("fin", ""), float(c.get("dx_km") or 27), int(c.get("razon") or 3), tam, c.get("forzante") or "ERA5"))
    except (W.WRFError, T.ToEError, ValueError, KeyError, TypeError, OSError) as e:
        return js(h, {"error": str(e)[:400]}, 400)
    except Exception as e:
        return js(h, {"error": f"{type(e).__name__}: {str(e)[:300]}"}, 400)
    return js(h, {"error": "Ruta desconocida."}, 404)
