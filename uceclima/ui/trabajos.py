# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""Gestor de corridas: una tarea por vez, proceso hijo, cancelación segura, registro persistente y detección de corridas interrumpidas.
Estados: pendiente · en_curso · completado · fallido · cancelado · interrumpido. «completado» solo significa que el proceso terminó."""
import json, os, subprocess, sys, time
from datetime import datetime
from pathlib import Path

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _pid_vivo(pid):
    if not pid:
        return False
    if os.name == "nt":
        r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, creationflags=CREATE_NO_WINDOW)   # bytes: la consola usa cp850/cp1252, no UTF-8
        return str(pid).encode() in (r.stdout or b"")
    try:
        os.kill(pid, 0); return True
    except OSError:
        return False


class GestorTrabajos:
    def __init__(self, carpeta_resultados):
        self.base = Path(carpeta_resultados); self.base.mkdir(parents=True, exist_ok=True)
        self.proc = None; self.run = None

    # ---------------------------------------------------------------- consulta
    def estado_de(self, run):
        run = Path(run)
        p = run / "estado.json"
        if not p.exists():
            return {"estado": "pendiente", "id": run.name}
        e = json.loads(p.read_text(encoding="utf-8")); e["id"] = run.name
        if e.get("estado") == "en_curso" and not (self.proc and self.proc.poll() is None and self.run == run) and not _pid_vivo(e.get("pid")):
            e["estado"] = "interrumpido"; e["mensaje"] = "El proceso ya no existe y no dejó un cierre limpio (cierre de la interfaz, apagado o error fatal). Resultado incompleto."
            p.write_text(json.dumps(e, ensure_ascii=False, indent=1), encoding="utf-8")
        if e.get("estado") == "interrumpido":                                            # Eta (Mejora 1): ¿quedó un punto de control?
            pc = self.punto_control(run)
            e["reanudable"] = bool(pc)
            if pc:
                e["punto_control"] = pc
                e["mensaje"] = f"Interrumpida al {int(pc['progreso'] * 100)} % (último punto de control: {pc['guardado'].replace('T', ' ')}). Pulsa «Reanudar» para seguir desde ahí: no se repite lo ya calculado."
        if e.get("estado") == "en_curso" and self.proc and self.proc.poll() is not None and self.run == run:
            e["estado"] = "fallido" if self.proc.returncode else "completado"
        return e

    def listar(self):
        corridas = sorted((d for d in self.base.glob("corrida_*") if d.is_dir()), reverse=True)
        return [self.estado_de(d) for d in corridas]

    def activa(self):
        return bool(self.proc and self.proc.poll() is None)

    # ---------------------------------------------------------------- control
    def iniciar(self, config, proyecto, tipo, base_proyecto, etiqueta="caso", escenario=None):
        if self.activa():
            raise RuntimeError("Ya hay una corrida en curso: la interfaz ejecuta una tarea por vez.")
        for e in self.listar():
            if e.get("estado") == "en_curso":
                raise RuntimeError(f"La corrida {e['id']} figura en curso (otro proceso). Espera o cancélala antes.")
        run = self.base / f"corrida_{datetime.now():%Y%m%d_%H%M%S}_{etiqueta}"
        if run.exists():
            raise RuntimeError("Ya existe esa carpeta de corrida; no se sobrescribe.")
        run.mkdir(parents=True)
        (run / "entrada.json").write_text(json.dumps({"config": config, "proyecto": proyecto, "tipo": tipo, "base": str(base_proyecto),
                                                      "creado": datetime.now().isoformat(timespec="seconds"), "escenario": escenario}, ensure_ascii=False, indent=1), encoding="utf-8")
        log = open(run / "registro.log", "wb")
        raiz = Path(__file__).resolve().parents[2]
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
        self.proc = subprocess.Popen(([sys.executable, "--worker", str(run)] if getattr(sys, "frozen", False) else [sys.executable, "-u", "-m", "uceclima.ui.worker", str(run)]), cwd=raiz, stdout=log, stderr=subprocess.STDOUT,
                                     creationflags=CREATE_NO_WINDOW, env=env)
        self.run = run
        (run / "estado.json").write_text(json.dumps({"estado": "en_curso", "pid": self.proc.pid, "progreso": 0.0, "mensaje": "Arrancando proceso", "escenario": (escenario or {}).get("nombre"), "escenario_id": (escenario or {}).get("id"),
                                                      "inicio": datetime.now().isoformat(timespec="seconds")}, ensure_ascii=False), encoding="utf-8")
        return run.name

    def punto_control(self, run):
        f = next(iter(sorted(Path(run).glob("salida/*/punto_control.npz"))), None)
        if not f:
            return None
        try:
            import numpy as np
            with np.load(f, allow_pickle=False) as F:
                m = json.loads(str(F["meta"]))
            return {"archivo": str(f.relative_to(run)), "progreso": float(m.get("progreso", 0)), "pasos": int(m.get("step", 0)), "guardado": m.get("guardado", "")}
        except Exception:
            return None

    def reanudar(self, run_id):
        """Eta (Mejora 1): relanza el proceso de cálculo de una corrida interrumpida desde su último punto de control (misma carpeta)."""
        if self.activa():
            raise RuntimeError("Ya hay una corrida en curso: la interfaz ejecuta una tarea por vez.")
        run = self.base / run_id
        if not run_id or not (run / "entrada.json").exists():
            raise FileNotFoundError(f"No existe la corrida {run_id}.")
        e = self.estado_de(run)
        if e.get("estado") != "interrumpido" or not e.get("reanudable"):
            raise RuntimeError("Solo se puede reanudar una corrida interrumpida que dejó un punto de control.")
        with open(run / "registro.log", "ab") as f:
            f.write(f"\n[{datetime.now():%H:%M:%S}] REANUDADA desde el punto de control ({int(e['punto_control']['progreso'] * 100)} %).\n".encode("utf-8"))
        log = open(run / "registro.log", "ab")
        raiz = Path(__file__).resolve().parents[2]
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
        self.proc = subprocess.Popen(([sys.executable, "--worker", str(run), "--reanudar"] if getattr(sys, "frozen", False) else [sys.executable, "-u", "-m", "uceclima.ui.worker", str(run), "--reanudar"]),
                                     cwd=raiz, stdout=log, stderr=subprocess.STDOUT, creationflags=CREATE_NO_WINDOW, env=env)
        self.run = run
        est = json.loads((run / "estado.json").read_text(encoding="utf-8"))
        est.update(estado="en_curso", pid=self.proc.pid, mensaje=f"Reanudando desde el {int(e['punto_control']['progreso'] * 100)} %", reanudaciones=int(est.get("reanudaciones", 0)) + 1)
        (run / "estado.json").write_text(json.dumps(est, ensure_ascii=False), encoding="utf-8")
        return run.name

    def cancelar(self):
        if not self.activa():
            return False
        pid = self.proc.pid
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, creationflags=CREATE_NO_WINDOW)
        else:
            self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except Exception:
            pass
        e = json.loads((self.run / "estado.json").read_text(encoding="utf-8"))
        e.update(estado="cancelado", mensaje="Cancelada por el usuario. Resultado incompleto; no usar.", fin=datetime.now().isoformat(timespec="seconds"))
        (self.run / "estado.json").write_text(json.dumps(e, ensure_ascii=False, indent=1), encoding="utf-8")
        with open(self.run / "registro.log", "ab") as f:
            f.write(f"\n[{datetime.now():%H:%M:%S}] CANCELADA por el usuario.\n".encode("utf-8"))
        return True

    def cola_log(self, run, n=6000):
        p = self.base / run / "registro.log"
        return p.read_bytes()[-n:].decode("utf-8", errors="replace") if p.exists() else ""

    def resultado(self, run):
        d = self.base / run
        out = {"estado": self.estado_de(d)}
        for k, nombre in (("resumen", "resumen.json"), ("evaluacion", "evaluacion_numerica.json"), ("mapa", "mapa_info.json")):
            f = next(iter(d.rglob(nombre)), None) if d.exists() else None
            if f: out[k] = json.loads(f.read_text(encoding="utf-8"))
        out["mapa_png"] = (d / "mapa_hmax.png").exists()
        al = []                                                                                    # C20: alertas con causas posibles
        try:
            ev = out.get("evaluacion") or {}
            f = next(iter(d.rglob("vmax.tif")), None)
            if f:
                import rasterio, numpy as np
                with rasterio.open(f) as s_:
                    v = s_.read(1, masked=True); vm = float(np.nanmax(v.filled(np.nan))) if v.count() else None
                if vm is not None and vm > 10:
                    try:
                        dem_ = str(json.loads((d / "entrada.json").read_text(encoding="utf-8"))["config"].get("dem", "")).lower()
                    except Exception:
                        dem_ = ""
                    if "fabdem" in dem_ or "dtm" in dem_ or "suelo" in dem_:
                        al.append(f"Velocidad máxima {vm:.1f} m/s (> 10 m/s) con un MDT de suelo desnudo (FABDEM): suele pasar en celdas muy someras y empinadas, en bordos o en el borde del cauce. Mira dónde están en v_anomala.tif (8 · Evaluación › Velocidades anómalas); usa áreas, no el máximo de una celda.")
                    else:
                        al.append(f"Velocidad máxima {vm:.1f} m/s (> 10 m/s): suele indicar escalones del DSM (edificios, árboles) o pendientes extremas; revisa el MDT o usa uno sin edificaciones (FABDEM).")
            lim = ev.get("porcentaje_pasos_con_limitador")
            if lim is not None and lim > 50:
                al.append(f"{lim:.1f} % de los pasos usaron el limitador de positividad (> 50 %): malla con celdas muy someras o DSM urbano; prueba rellenar depresiones o mayor resolución.")
            alm = ev.get("porcentaje_volumen_almacenado")
            if alm is not None and alm > 80:
                al.append(f"{alm:.1f} % del volumen sigue almacenado al final (> 80 %): la simulación es corta para que el agua salga o hay depresiones cerradas; aumenta el tiempo simulado (⚙) o rellena depresiones.")
        except Exception:
            pass
        out["alertas"] = al
        try:
            out["escenario"] = json.loads((d / "entrada.json").read_text(encoding="utf-8")).get("escenario")
        except Exception:
            out["escenario"] = None
        return out
