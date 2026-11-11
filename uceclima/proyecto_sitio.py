# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""R2 (editar el sitio) y R3 (nombre con sufijo «ucec», renombrar, listar). Nada se borra: se respaldan los archivos y se anota la procedencia."""
import json
import os
import re
import shutil
import time
from datetime import datetime
from pathlib import Path

DEPENDEN_DEL_SITIO = ("mdt", "suelo", "cn_manning", "geoglows", "sitio")
SUFIJO = "ucec"


class SitioError(ValueError):
    pass


def carpeta_con_sufijo(slug):
    return slug if slug.endswith(SUFIJO) else f"{slug}{SUFIJO}"


def _bak(p):
    p = Path(p)
    if p.exists():
        shutil.copy2(p, p.with_name(f"{p.name}.{time.strftime('%Y%m%d_%H%M%S')}.bak"))


def cambiar_sitio(carpeta, datos, lon=None, lat=None, centrar_cuenca=False):
    from . import descargas as D
    from .ui import proyecto as P
    carpeta = Path(carpeta)
    if centrar_cuenca:
        from .cuenca import extension_activa
        import geopandas as gpd
        act = carpeta / "cuenca" / "activa.json"
        if not act.exists():
            raise SitioError("No hay cuenca activa para centrar el sitio.")
        a = json.loads(act.read_text(encoding="utf-8"))
        c = gpd.read_file(carpeta / a["carpeta"] / "cuenca.gpkg").to_crs(4326).geometry.unary_union.representative_point()
        lon, lat = c.x, c.y
    try:
        lon, lat = float(str(lon).replace(",", ".")), float(str(lat).replace(",", "."))
    except (TypeError, ValueError):
        raise SitioError("Escribe la longitud y la latitud en grados decimales.")
    if not D.punto_admitido(lon, lat):
        raise SitioError(D.MENSAJE_FUERA)
    m = re.search(r"lon\s*(-?[\d.]+)\D+lat\s*(-?[\d.]+)", str(datos.get("ubicacion", "")))
    antes = {"lon": float(m.group(1)), "lat": float(m.group(2))} if m else None
    crs_nuevo = f"EPSG:{D.utm_epsg(lon, lat)}"; crs_viejo = datos.get("crs")
    pf = carpeta / "proyecto_uceclima.json"; _bak(pf)
    d2 = json.loads(json.dumps(datos))
    d2["ubicacion"] = f"lon {lon:.4f}, lat {lat:.4f}"; d2["crs"] = crs_nuevo
    proc = d2.setdefault("procedencia", {}) if isinstance(d2.get("procedencia"), dict) else {}
    proc.setdefault("sitios_anteriores", []).append({"lon": antes and antes["lon"], "lat": antes and antes["lat"], "crs": crs_viejo, "cambiado": datetime.now().isoformat(timespec="seconds")})
    d2["procedencia"] = proc
    P.guardar(d2, carpeta, sobrescribir=True)
    cfgp = carpeta / datos.get("config_climanet", "config_climanet.json")
    if cfgp.exists():
        _bak(cfgp); cfg = json.loads(cfgp.read_text(encoding="utf-8"))
        from .ui.sitio_api import en_ecuador
        if en_ecuador(lon, lat):
            for k in ("idf_inamhi", "idf_x"):
                if isinstance(cfg.get(k), dict):
                    cfg[k].update(lat=lat, lon=lon)
        else:                                                                     # Zeta: fuera de Ecuador la IDF del INAMHI no aplica (se declara una IDF propia)
            for k in ("idf_inamhi", "idf_x"):
                cfg.pop(k, None)
        cfgp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    viejas = [d.name for d in sorted((carpeta / "datos_descargados").glob("*_2*")) if d.name.rsplit("_", 2)[0] in DEPENDEN_DEL_SITIO and not _ambito_cuenca(d)] if (carpeta / "datos_descargados").exists() else []
    reg = {"fecha": datetime.now().isoformat(timespec="seconds"), "motivo": "cambio de sitio", "sitio_anterior": antes, "sitio_nuevo": {"lon": lon, "lat": lat},
           "descargas_desactualizadas": viejas, "idf_desactualizada": True, "crs_cambio": crs_nuevo != crs_viejo}
    (carpeta / "registro").mkdir(exist_ok=True)
    (carpeta / "registro" / "desactualizadas.json").write_text(json.dumps(reg, ensure_ascii=False, indent=1), encoding="utf-8")
    avisos = []
    if crs_nuevo != crs_viejo:
        avisos.append(f"La zona UTM cambió ({crs_viejo} → {crs_nuevo}): vuelve a descargar y registrar el MDT antes de correr.")
    return {**reg, "crs": crs_nuevo, "avisos": avisos, "rehacer": ["5 · Terreno → MDT de Earth Engine", "2 · Datos / GEE → Uso de suelo y suelo → CN y Manning", "4 · IDF → fijar de nuevo"]}


def _ambito_cuenca(d):
    """G11 (Delta): una descarga hecha con ámbito «cuenca» cubre la cuenca entera; mover el sitio dentro de ella no la invalida."""
    try:
        return json.loads((d / "estado.json").read_text(encoding="utf-8")).get("parametros", {}).get("ambito") == "cuenca"
    except Exception:
        return False


def desactualizadas(carpeta):
    f = Path(carpeta) / "registro" / "desactualizadas.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def listar(base):
    base = Path(base); out = []
    if base.exists():
        for d in sorted(base.iterdir()):
            f = d / "proyecto_uceclima.json"
            if d.is_dir() and f.exists():
                try:
                    j = json.loads(f.read_text(encoding="utf-8"))
                except Exception:
                    continue
                out.append({"carpeta": str(d), "nombre": j.get("nombre"), "ucec": d.name.endswith(SUFIJO), "modificado": datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="minutes")})
    return sorted(out, key=lambda x: (not x["ucec"], x["nombre"] or ""))


def renombrar(carpeta, datos, nombre):
    from .ui import proyecto as P, sitio_api
    nombre = (nombre or "").strip()
    if len(nombre) < 3:
        raise SitioError("El nombre debe tener al menos 3 letras.")
    carpeta = Path(carpeta); nueva = carpeta.parent / carpeta_con_sufijo(sitio_api._slug(nombre))
    if nueva.exists() and nueva.resolve() != carpeta.resolve():
        raise SitioError(f"Ya existe {nueva}.")
    d2 = json.loads(json.dumps(datos)); antes = d2.get("nombre")
    d2["nombre"] = nombre
    proc = d2.setdefault("procedencia", {}) if isinstance(d2.get("procedencia"), dict) else {}
    proc.setdefault("renombrado", []).append({"antes": antes, "carpeta_antes": str(carpeta), "fecha": datetime.now().isoformat(timespec="seconds")}); d2["procedencia"] = proc
    _bak(carpeta / "proyecto_uceclima.json"); P.guardar(d2, carpeta, sobrescribir=True)
    if nueva.resolve() != carpeta.resolve():
        os.rename(carpeta, nueva)
    try:
        from .ui import agente_vscode
        agente_vscode.configurar(nueva)                               # la ruta del proyecto cambió: el agente apunta a la nueva
    except Exception:
        pass
    return {"carpeta": str(nueva), "nombre": nombre, "antes": antes}
