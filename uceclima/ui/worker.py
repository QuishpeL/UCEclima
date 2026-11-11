# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Proceso de cálculo (separado de la interfaz). Uso: python -m uceclima.ui.worker <carpeta_de_corrida>
Lee entrada.json, ejecuta el núcleo CLIMANET (pipeline.run), escribe estado.json/registro.log y genera el mapa. No hay lógica científica aquí."""
import json, re, sys, time, traceback
from datetime import datetime
from pathlib import Path


def _estado(run, **kw):
    """Actualiza estado.json. En Windows la interfaz puede estar leyéndolo justo en ese instante («Acceso denegado»): se reintenta, y una
    actualización de progreso que no se pudo escribir se omite sin detener el cálculo; los cambios de estado final insisten más."""
    p = run / "estado.json"; tmp = run / "estado.json.tmp"
    intentos = 60 if "estado" in kw else 10
    for k in range(intentos):
        try:
            e = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
            e.update(kw, actualizado=datetime.now().isoformat(timespec="seconds"))
            tmp.write_text(json.dumps(e, ensure_ascii=False, indent=1), encoding="utf-8"); tmp.replace(p)
            return True
        except (PermissionError, json.JSONDecodeError, OSError):
            time.sleep(0.05 + 0.05 * k)
    return False


def _mantener_despierto(activo=True):
    """Eta (Mejora 1 · C): mientras corre, se pide a Windows que no suspenda el equipo (la pantalla sí se puede apagar)."""
    try:
        import ctypes
        ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if activo else 0))
    except Exception:
        pass


def _aviso_bateria():
    try:
        import ctypes

        class _SPS(ctypes.Structure):
            _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte), ("BatteryLifePercent", ctypes.c_ubyte), ("SystemStatusFlag", ctypes.c_ubyte),
                        ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong)]
        s = _SPS()
        if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(s)) and s.ACLineStatus == 0:
            return (f"AVISO: el equipo está a batería ({s.BatteryLifePercent} %). Conecta el cargador: si se apaga, la corrida se reanuda desde el último "
                    "punto de control, pero se pierde lo calculado después de ese punto.")
    except Exception:
        pass
    return None


def main(run, reanudar=False):
    try:                                                          # Eta (punto 12): registro en UTF-8 aunque la consola o el ejecutable usen otra codificación
        sys.stdout.reconfigure(encoding="utf-8", errors="replace"); sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    run = Path(run)
    ent = json.loads((run / "entrada.json").read_text(encoding="utf-8"))
    import os
    if reanudar:
        _estado(run, estado="en_curso", pid=os.getpid(), mensaje="Reanudando desde el punto de control")
    else:
        _estado(run, estado="en_curso", pid=os.getpid(), inicio=datetime.now().isoformat(timespec="seconds"), progreso=0.0, mensaje="Iniciando")
    _mantener_despierto(True)
    b_ = _aviso_bateria()
    if b_: print(b_, flush=True)
    ultimo = [0.0]

    def progreso(msg):
        print(msg, flush=True)
        m = re.search(r"(\d+)% \((\d+) pasos\)", str(msg))
        if m and time.time() - ultimo[0] > 0.4:
            ultimo[0] = time.time(); _estado(run, progreso=int(m.group(1)) / 100.0, pasos=int(m.group(2)), mensaje=f"Simulando: {m.group(1)} %")
    try:
        import uceclima                                           # fija sys.path al núcleo
        from climanet import pipeline
        cfg = ent["config"]; cfg["out_dir"] = str(run / "salida")
        if reanudar: cfg["_reanudar"] = True
        if not cfg.get("escenario_info") and ent.get("escenario"):
            es_ = ent["escenario"]; cfg["escenario_info"] = {"id": es_.get("id"), "nombre": es_.get("nombre"), "tipo": es_.get("tipo"), "factor": es_.get("factor")}
        print(f"[{datetime.now():%H:%M:%S}] {'Reanudación' if reanudar else 'Inicio'}. Proyecto: {ent['proyecto']} ({ent['tipo']})" + (f" · escenario {cfg['escenario_info'].get('nombre')}" if cfg.get("escenario_info") else "") + f" · Tr {cfg.get('Tr', 100)}.", flush=True)
        resumen = pipeline.run(cfg, progress=progreso)
        print(f"[{datetime.now():%H:%M:%S}] Núcleo terminado. Balance máx. {resumen['error_balance_max_pct']:.2e} %, CFL máx. {resumen['CFL_max']:.3f}.", flush=True)
        _estado(run, progreso=0.97, mensaje="Generando mapa")
        from uceclima.ui import mapas
        hm = next((run / "salida").rglob("hmax.tif"))
        info = mapas.render_hmax(cfg, ent["base"], hm, run / "mapa_hmax.png", sintetico=(ent["tipo"] == "sintetico"),
                                 titulo=f"Calado máximo · {ent['proyecto']}", subtitulo=((f"PRONÓSTICO «{(cfg.get('evento_observado') or {}).get('id')}» · modelo no calibrado · no es una observación ni una alerta oficial" if ((cfg.get('evento_observado') or {}).get('forzamiento_externo') or {}).get('tipo') == "pronostico"
                                       else f"Lluvia ESTIMADA POR SATÉLITE «{(cfg.get('evento_observado') or {}).get('id')}» · modelo no calibrado · no es una medición en tierra" if ((cfg.get('evento_observado') or {}).get('forzamiento_externo') or {}).get('tipo') == "satelite"
                                       else f"Evento observado «{(cfg.get('evento_observado') or {}).get('id')}» (histórico) · modelo no calibrado · no es una validación · no es una huella observada") if cfg.get("evento_observado")
                                           else (f"Diseño IDF con cambio climático Tr{resumen['Tr']}" if (ent.get("escenario") or {}).get("tipo") == "cmip6" else f"Diseño IDF histórica Tr{resumen['Tr']}") + (f" · {ent['escenario']['nombre']}" if ent.get("escenario") else "") + " · no es un evento observado · no calibrado · no validado"))
        (run / "mapa_info.json").write_text(json.dumps(info), encoding="utf-8")
        _estado(run, progreso=0.98, mensaje="Mapa con referencias (satélite + OSM)")
        try:                                                                       # Omega O5: mapa estilo RAS automático; si falla (sin red), la corrida sigue completada
            from uceclima import mapa_referencias as MR
            mr = MR.mapa(ent["base"], run.name, descargar=bool(cfg.get("mapa_osm", True)) and ent.get("tipo") != "sintetico")   # Eta: un proyecto sintético no es un lugar real: sin OSM
            print(f"[{datetime.now():%H:%M:%S}] Mapa con referencias: {mr.get('figura')}", flush=True)
        except Exception as ex:
            print(f"AVISO: no se generó el mapa con referencias ({str(ex)[:200]}). Puedes generarlo en 8 · Evaluación.", flush=True)
        _estado(run, estado="completado", progreso=1.0, fin=datetime.now().isoformat(timespec="seconds"),
                mensaje="Completado. El proceso terminó; esto NO significa que el modelo esté validado.")
        _mantener_despierto(False)
        return 0
    except BaseException as e:
        _mantener_despierto(False)                                    # incluye errores de configuración y de cálculo
        print("ERROR:", e, flush=True); traceback.print_exc()
        (run / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        _estado(run, estado="fallido", fin=datetime.now().isoformat(timespec="seconds"), mensaje=f"Falló: {str(e)[:300]}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], reanudar="--reanudar" in sys.argv[2:]))
