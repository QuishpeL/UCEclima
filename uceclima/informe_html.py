# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""Omega O6 · INFORME HTML autocontenido de un proyecto (un solo archivo: figuras incrustadas, sin dependencias externas, legible en el celular).
Todo sale de los resultados del proyecto (resumen.json, exposicion.xlsx, configuración, estaciones, cuencas, CMIP6): ninguna cifra se escribe a mano.
Cada sección aparece solo si existen sus insumos; lo que falta se dice. Los resultados siguen siendo NO calibrados ni validados."""
import base64, html, io, json
from datetime import datetime
from pathlib import Path
import pandas as pd

E = lambda s: html.escape(str(s))


def _n(v, d=1):
    try:
        return f"{float(v):,.{d}f}".replace(",", "X").replace(".", ",").replace("X", " ")
    except Exception:
        return "—"


def _img(p, maxw=1200, q=84):
    p = Path(p)
    if not p.exists():
        return None
    try:
        from PIL import Image
        im = Image.open(p).convert("RGB")
        if im.width > maxw:
            im = im.resize((maxw, int(im.height * maxw / im.width)))
        b = io.BytesIO(); im.save(b, "JPEG", quality=q, optimize=True)
        return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()
    except Exception:
        return None


def _fig(p, pie):
    s = _img(p)
    return f'<figure><img src="{s}" alt="{E(pie)}"><figcaption>{E(pie)}</figcaption></figure>' if s else ""


def _tabla(df, cols=None):
    if df is None or not len(df):
        return '<p class="nada">Sin datos.</p>'
    d = df[cols] if cols else df
    cab = "".join(f"<th>{E(c)}</th>" for c in d.columns)
    def cel(v):
        if v is None or (isinstance(v, float) and v != v):
            return "—"
        if isinstance(v, float):
            return f"{v:.0e}" if 0 < abs(v) < 0.01 else _n(v, 2)
        return E(v)
    fil = "".join("<tr>" + "".join(f"<td>{cel(v)}</td>" for v in r) + "</tr>" for r in d.itertuples(index=False))
    return f'<div class="tw"><table><thead><tr>{cab}</tr></thead><tbody>{fil}</tbody></table></div>'


def _stat(v, l):
    return f'<div class="stat"><b>{v}</b><span>{E(l)}</span></div>'


CSS = """:root{--az:#1F4E79;--az2:#2E75B6;--tx:#1b2533;--gr:#5a6f95;--fondo:#f6f8fb}
*{box-sizing:border-box}body{margin:0;font-family:"Calibri Light",Calibri,"Segoe UI",sans-serif;color:var(--tx);background:var(--fondo);line-height:1.5}
header{background:linear-gradient(120deg,#0d2a63,#1F4E79 45%,#2E75B6);color:#fff;padding:34px 18px 26px}
header h1{margin:0 0 6px;font-size:clamp(24px,4vw,36px);font-weight:600}header p{margin:0;opacity:.88}
main{max-width:1100px;margin:0 auto;padding:10px 16px 40px}
h2{color:var(--az);border-bottom:2px solid #d6e2f2;padding-bottom:4px;margin-top:34px;font-weight:600}h3{color:var(--az2);margin-bottom:4px}
.aviso{background:#fff6e0;border-left:4px solid #e0a100;padding:10px 14px;border-radius:6px;margin:14px 0}
.nota{background:#eef3fb;border-left:4px solid var(--az2);padding:9px 13px;border-radius:6px;margin:10px 0}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:14px 0}
.stat{background:#fff;border-radius:10px;padding:12px 14px;box-shadow:0 1px 3px rgba(13,42,99,.12)}.stat b{display:block;font-size:22px;color:var(--az)}.stat span{font-size:13px;color:var(--gr)}
figure{margin:16px 0;background:#fff;border-radius:10px;padding:8px;box-shadow:0 1px 3px rgba(13,42,99,.12)}figure img{width:100%;height:auto;border-radius:6px}
figcaption{font-size:13px;color:var(--gr);padding:6px 4px 2px}
.tw{overflow-x:auto}table{border-collapse:collapse;width:100%;background:#fff;font-size:13.5px;margin:8px 0}th{background:#1F4E79;color:#fff;font-weight:600;text-align:left}
th,td{padding:6px 9px;border-bottom:1px solid #e3e9f2}tr:nth-child(even) td{background:#f7f9fc}
.nada{color:var(--gr);font-style:italic}footer{font-size:12.5px;color:var(--gr);text-align:center;padding:20px}
code{background:#eef3fb;padding:1px 5px;border-radius:4px}"""


def _caso(c):
    base = f"Tr {c['tr']} años" if c["tr"] else "evento observado"
    if str(c.get("escenario", "")).startswith("cc_"):
        return f"{base} · Y {c.get('nombre') or c['escenario']}"
    return f"{base} · X condiciones existentes"


def construir(proyecto, datos, cs, destino, manifiesto=None):
    """Escribe destino/informe.html. cs = entregas.corridas(proyecto). Por caso (Tr/evento × escenario) se muestra la corrida más reciente; las anteriores van a una tabla de diagnóstico."""
    from . import __version__
    ult = {}
    for c in sorted(cs, key=lambda x: x["id"]):
        ult[(c["tr"], str(c.get("escenario")))] = c
    anteriores = [c for c in cs if ult.get((c["tr"], str(c.get("escenario")))) is not c]
    cs = sorted(ult.values(), key=lambda x: (x["tr"] is None, x["tr"] or 0, str(x.get("escenario")).startswith("cc_"), str(x.get("escenario"))))
    proyecto = Path(proyecto); destino = Path(destino); sec = []
    try:
        cfg = json.loads((proyecto / datos.get("config_climanet", "config_climanet.json")).read_text(encoding="utf-8"))
    except Exception:
        cfg = {}
    nombre = datos.get("nombre", proyecto.name)
    # ---------------- resumen
    filas = []
    for c in cs:
        r = c["resumen"]; ex = {}
        xl = next(iter(c["salida"].glob("exposicion.xlsx")), None)
        if xl:
            try:
                ex = pd.read_excel(xl, sheet_name="resumen").iloc[0].to_dict()
            except Exception:
                ex = {}
        caso = _caso(c)
        filas.append({"corrida": c["id"], "caso": caso, "escenario": c["tipo"].split(" ")[0], "lluvia_mm": r.get("P_total_mm"), "h_max_m": r.get("calado_max_m"),
                      "area_≥0,05_km2": r.get("area_ge_0.05_km2"), "area_≥0,5_km2": r.get("area_ge_0.5_km2"), "area_≥1_km2": r.get("area_ge_1.0_km2"),
                      "edificios_≥0,5_m": ex.get("edificios_calado_ge_0.5m"), "error_masa_pct": r.get("error_balance_max_pct")})
    tab = pd.DataFrame(filas)
    st = [_stat(len(cs), "corridas completadas")]
    if len(tab):
        st += [_stat(_n(tab["area_≥0,5_km2"].max(), 1) + " km²", "mayor área con calado ≥ 0,5 m"), _stat(_n(tab["h_max_m"].max(), 2) + " m", "calado máximo del modelo"),
               _stat(f"{tab['error_masa_pct'].max():.0e} %", "error máximo de balance de masa")]
    sec.append(f"<h2>Resumen</h2><div class='stats'>{''.join(st)}</div>{_tabla(tab)}")
    # ---------------- datos
    cat = proyecto / "datos" / "estaciones" / "catalogo.csv"
    if cat.exists():
        ce = pd.read_csv(cat); fl = []
        for _, e in ce.iterrows():
            q = proyecto / "datos" / "estaciones" / f"{e['id']}.qc.json"; qc = json.loads(q.read_text(encoding="utf-8"))["calidad"] if q.exists() else {}
            fl.append({"estación": e["id"], "nombre": e.get("nombre"), "registros": qc.get("n_registros"), "inicio (UTC)": str(qc.get("inicio_utc", ""))[:10], "fin (UTC)": str(qc.get("fin_utc", ""))[:10],
                       "paso (min)": qc.get("paso_min_detectado"), "huecos": qc.get("huecos"), "zona horaria": e.get("zona_horaria_origen")})
        sec.append(f"<h2>Datos de lluvia</h2><p>Estaciones del proyecto (los huecos no se rellenan).</p>{_tabla(pd.DataFrame(fl))}")
    ev = cfg.get("evento_observado")
    # ---------------- terreno
    sec.append(f"<h2>Terreno</h2><div class='stats'>{_stat(E(datos.get('tipo_terreno', '—')), 'tipo de terreno declarado')}{_stat(_n(cfg.get('res'), 0) + ' m', 'celda del modelo')}"
               f"{_stat(_n((cfg['aoi'][1] - cfg['aoi'][0]) * (cfg['aoi'][3] - cfg['aoi'][2]) / 1e6, 1) + ' km²' if cfg.get('aoi') else '—', 'área de cálculo')}</div>"
               f"<div class='nota'>Terreno: <code>{E(Path(str(cfg.get('dem', ''))).name)}</code> · datum vertical: {E(datos.get('datum_vertical', '—'))}"
               + (". <b>FABDEM</b> (Hawker et al. 2022) es GLO-30 con bosques y edificios quitados: un suelo desnudo estimado, no medido; también suaviza cauces pequeños." if "fabdem" in str(cfg.get("dem", "")).lower() else "") + "</div>")
    # ---------------- cuencas
    filas_c = []
    act = proyecto / "cuenca" / "activa.json"
    if act.exists():
        a = json.loads(act.read_text(encoding="utf-8")); filas_c.append({"rol": "cuenca activa (salida del dominio)", "carpeta": a["carpeta"], "área_km2": a.get("area_km2")})
    for c_ in cfg.get("cuencas_externas") or []:
        filas_c.append({"rol": f"cuenca externa {c_['nombre']} (CN {c_['cn']}, lag {c_['lag_h']} h)", "carpeta": c_["shp"].split("/")[1], "área_km2": None})
    for e_ in cfg.get("entradas_hidrograma") or []:
        filas_c.append({"rol": f"hidrograma de entrada {e_['nombre']}", "carpeta": Path(e_['csv']).name, "área_km2": None})
    if filas_c:
        sec.append(f"<h2>Cuencas y entradas de agua</h2>{_tabla(pd.DataFrame(filas_c))}<p class='nada'>Las cuencas externas usan la MISMA tormenta de la 2D y solo su área fuera del dominio; el borde se cierra junto a cada entrada.</p>")
    # ---------------- corridas
    sec.append("<h2>Resultados por corrida</h2>")
    for c in cs:
        r = c["resumen"]; caso = _caso(c)
        mr = next(iter(c["salida"].glob("mapa_referencias.png")), None) or c["mapa"]
        hs = r.get("hidrograma_salida") or {}
        sec.append(f"<h3>{E(caso)} · <code>{E(c['id'])}</code></h3><div class='stats'>{_stat(_n(r.get('P_total_mm'), 1) + ' mm', 'lluvia')}{_stat(_n(r.get('area_ge_0.3_km2'), 2) + ' km²', 'área ≥ 0,3 m')}"
                   f"{_stat(_n(r.get('area_ge_1.0_km2'), 2) + ' km²', 'área ≥ 1 m')}{_stat(_n(hs.get('pico_2d_m3s'), 1) + ' m³/s' if hs else '—', 'pico 2D en la salida')}</div>"
                   + _fig(mr, f"Calado máximo · {caso} (suavizado solo para visualización).") + _fig(next(iter(c["salida"].glob("hidrograma_salida.png")), Path("_")), f"Hidrograma 2D en la salida · {caso}."))
    if anteriores:
        sec.append("<h3>Corridas anteriores (diagnóstico y sensibilidad)</h3><p class='nada'>No son resultados del caso: se conservan como registro del proceso (nada se sobrescribe).</p>"
                   + _tabla(pd.DataFrame([{"corrida": c["id"], "caso": _caso(c), "área_≥0,5_km2": c["resumen"].get("area_ge_0.5_km2"), "pico_salida_m3s": (c["resumen"].get("hidrograma_salida") or {}).get("pico_2d_m3s")} for c in anteriores])))
    # ---------------- CMIP6
    bc = proyecto / "registro" / "cmip6"
    fg = [f for f in sorted(bc.rglob("toe_cabeza_*.png")) + sorted(bc.rglob("bondad_qqm.png")) + sorted(bc.rglob("toe_indicadores.png")) if not f.stem.endswith("_en")] if bc.exists() else []
    dec = proyecto / "registro" / "cmip6_decision.json"
    if fg:
        try:
            txt_dec = json.loads(dec.read_text(encoding="utf-8")).get("texto", "") if dec.exists() else ""
        except Exception:
            txt_dec = ""
        sec.append("<h2>Cambio climático (CMIP6, SSP5-8.5)</h2>" + (f"<div class='aviso'>Línea base asumida por decisión del usuario; no calibrada ni validada. {E(txt_dec)}</div>" if dec.exists() else "") + "".join(_fig(f, f.stem.replace("_", " ")) for f in fg[-6:]))
    else:
        sec.append("<h2>Cambio climático (CMIP6)</h2><p class='nada'>Sin gráficas CMIP6 en este proyecto (no se corrió el escenario Y o la línea base no fue asumida por el usuario).</p>")
    # ---------------- visor y archivos
    sec.append("<h2>Visor 3D</h2><p>Cada corrida se puede recorrer en el <b>★ Visor 3D</b> de UCEclima (terreno, calado, velocidad, película del agua y ríos HydroSHEDS).</p>")
    if manifiesto:
        grupos = {}
        for a in manifiesto.get("archivos", []):
            k = a["ruta"].split("/")[0]; grupos[k] = grupos.get(k, 0) + 1
        sec.append("<h2>Archivos de esta entrega</h2>" + _tabla(pd.DataFrame([{"carpeta": k, "archivos": v} for k, v in sorted(grupos.items())])) + "<p class='nada'>Tablas en CSV y Excel; capas en shapefile WGS84 y UTM y GeoPackage; rásteres GeoTIFF.</p>")
    sec.append("<h2>Limitaciones</h2><div class='aviso'>Modelo <b>no calibrado ni validado</b> con observaciones de la zona: los mapas son escenarios, no predicción ni huella observada. "
               "La capacidad de canales y las pérdidas de carga no se evalúan. OpenStreetMap puede estar incompleto. El terreno global (30 m) no resuelve el drenaje urbano fino.</div>")
    pie = f"UCEclima {E(__version__)} · {E(nombre)} · generado {datetime.now():%Y-%m-%d %H:%M} · todas las cifras salen de los resultados del proyecto"
    doc = (f"<!doctype html><html lang='es'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Informe · {E(nombre)}</title><style>{CSS}</style></head>"
           f"<body><header><h1>Informe de inundación · {E(nombre)}</h1><p>UCEclima {E(__version__)} · {('evento observado y ' if ev or any(not c['tr'] for c in cs) else '')}escenarios de diseño · {datetime.now():%d-%m-%Y}</p></header>"
           f"<main><div class='aviso'>Resultados no calibrados ni validados. No son predicción ni huella de inundación observada.</div>{''.join(sec)}</main><footer>{pie}</footer></body></html>")
    f = destino / "informe.html"; f.write_text(doc, encoding="utf-8")
    return f
