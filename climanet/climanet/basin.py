# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Modelo de cuencas (SCS-CN + hidrograma unitario triangular + tránsito Muskingum), NO equivalente a HEC-HMS.

Contrato temporal: la lluvia llega como pd.Series con DatetimeIndex regular cuyo paso es EXACTAMENTE `step_s`.
- Si el proveedor tiene un paso más fino se agrega conservando el acumulado (`agregar_conservativo`).
- Si tiene un paso más grueso se rechaza: no se inventan intensidades subdiarias a partir de lluvia diaria.
- Los datos ausentes (NaN) no se convierten en cero: por defecto el modelo se detiene e informa la cobertura.
Los volúmenes se contabilizan (entrada, salida, almacenamiento final del tránsito); nunca se recorta con maximum(q, 0).
"""
from dataclasses import dataclass
import math
import numpy as np
import pandas as pd
from .hydrology import scs_hydrograph

INTEGRATE = np.trapezoid if hasattr(np, "trapezoid") else np.trapz


@dataclass
class Subbasin:
    name: str
    area_km2: float          # área EXTERNA al dominio 2D (la interna se modela con lluvia sobre malla)
    cn: float
    tc_h: float = None       # retardo = 0.6 Tc salvo que se dé lag_h
    x: float = 0.0           # centroide, para consultar el proveedor de lluvia
    y: float = 0.0
    downstream: str = None   # subcuenca aguas abajo (None = salida)
    reach_k_h: float = 0.0   # Muskingum K total del tramo (h); 0 = sin tránsito
    reach_x: float = 0.2
    lag_h: float = None      # retardo directo (como HEC-HMS); tiene prioridad sobre tc_h
    prf: float = 484.0       # factor de pico del hidrograma unitario (484 estándar; ~240 equivale al DELMARVA de HMS en Milagro)
    imperv_frac: float = 0.0 # fracción impermeable (0-1): toda su lluvia es exceso


def paso_de(serie: pd.Series) -> float:
    """Paso (s) de una serie con índice datetime regular. Falla si es irregular o tiene menos de 2 datos."""
    if not isinstance(serie.index, pd.DatetimeIndex) or len(serie) < 2:
        raise ValueError("La lluvia debe ser una serie con DatetimeIndex y al menos 2 registros.")
    d = np.diff(serie.index.values).astype("timedelta64[s]").astype(float)
    if not np.allclose(d, d[0]) or d[0] <= 0:
        raise ValueError("Índice temporal irregular o duplicado: regularizar explícitamente antes de modelar.")
    return float(d[0])


def agregar_conservativo(serie: pd.Series, step_s: float) -> pd.Series:
    """Agrega una serie de lluvia (mm por paso) a un paso mayor múltiplo exacto, conservando el acumulado.
    Un bloque con algún NaN queda NaN (no se subestima en silencio)."""
    s0 = paso_de(serie)
    if abs(step_s - s0) < 1e-9:
        return serie
    if step_s < s0:
        raise ValueError(f"Paso de la serie ({s0:.0f} s) mayor que el del modelo ({step_s:.0f} s): no se desagrega "
                         "lluvia a intensidades subdiarias inventadas. Aportar datos con cadencia suficiente.")
    k = step_s / s0
    if abs(k - round(k)) > 1e-9:
        raise ValueError(f"El paso del modelo ({step_s:.0f} s) no es múltiplo del paso de la serie ({s0:.0f} s).")
    return serie.resample(f"{int(step_s)}s", label="left", closed="left").apply(
        lambda b: b.sum() if (len(b) == int(round(k)) and b.notna().all()) else np.nan)


def coeficientes_muskingum(dt_s, k_s, x):
    den = k_s * (1 - x) + 0.5 * dt_s
    return (-k_s * x + 0.5 * dt_s) / den, (k_s * x + 0.5 * dt_s) / den, (k_s * (1 - x) - 0.5 * dt_s) / den


def subtramos_muskingum(dt_s, k_s, x):
    """Nº de subtramos n para que K'=K/n cumpla C0>=0 y C2>=0: dt/(2(1-X)) <= K' <= dt/(2X)."""
    kmin, kmax = dt_s / (2 * (1 - x)), (dt_s / (2 * x) if x > 0 else math.inf)
    if k_s < kmin - 1e-9:
        raise ValueError(f"K={k_s/3600:.3f} h es demasiado corto para dt={dt_s:.0f} s (mínimo {kmin/3600:.3f} h): "
                         "usar un paso menor o K=0 (sin tránsito).")
    n = max(1, math.ceil(k_s / kmax - 1e-12)) if math.isfinite(kmax) else 1
    if k_s / n < kmin - 1e-9:
        raise ValueError("No existe discretización Muskingum admisible para K, X y dt dados.")
    return n


def muskingum(q_in, dt_s, k_h, x, cola=True, n=None, permitir_inadmisible=False):
    """Tránsito Muskingum en cascada de n subtramos con coeficientes no negativos (C0+C1+C2=1).
    Estado inicial en régimen permanente (O0 = I0), por lo que el tramo parte con almacenamiento S0 = K*I0 que se
    libera después: la continuidad es Ventrada + S0 = Vsalida + Sfinal (no se interpreta como agua creada).
    Devuelve (q_out, info). Con cola=True se extiende con ceros hasta drenar el almacenamiento."""
    q_in = np.asarray(q_in, float)
    k = k_h * 3600
    vin = float(INTEGRATE(q_in, dx=dt_s))
    if k <= 0:
        return q_in.copy(), {"n_subtramos": 0, "volumen_entrada_m3": vin, "volumen_salida_m3": vin,
                             "almacenamiento_inicial_m3": 0.0, "almacenamiento_final_m3": 0.0}
    n_auto = subtramos_muskingum(dt_s, k, x)
    n = int(n) if n else n_auto                     # n explícito: para contrastar con otro programa con los mismos subtramos
    c0, c1, c2 = coeficientes_muskingum(dt_s, k / n, x)
    inadmisible = min(c0, c1, c2) < -1e-12
    if inadmisible and not permitir_inadmisible:
        raise ValueError(f"Con n={n} subtramos los coeficientes son inadmisibles (C0={c0:.4f}, C2={c2:.4f}); se necesitan n>={n_auto} para dt={dt_s:.0f} s, K={k_h} h, X={x}.")
    assert abs(c0 + c1 + c2 - 1) < 1e-12
    extra = int(math.ceil(12 * k / dt_s)) if cola else 0
    q = np.r_[q_in, np.zeros(extra)]
    i_last = q[-1]
    for _ in range(n):
        out = np.zeros_like(q); out[0] = q[0]
        for i in range(1, len(q)):
            out[i] = c0 * q[i] + c1 * q[i - 1] + c2 * out[i - 1]
        q = out
    vout = float(INTEGRATE(q, dx=dt_s))
    s0 = k * float(q_in[0])                                   # sum_n (K/n)*I0
    sfin = k * float(q[-1]) * (1 - x) if cola else None       # aprox. del almacenamiento remanente (O_final ~ 0)
    info = {"n_subtramos": n, "coeficientes": (c0, c1, c2), "inadmisible": inadmisible, "volumen_entrada_m3": vin, "volumen_salida_m3": vout,
            "almacenamiento_inicial_m3": s0, "almacenamiento_final_m3": sfin}
    if cola:
        cierre = vin + s0 - vout - (sfin or 0.0)
        info["cierre_continuidad_m3"] = cierre
        if abs(cierre) > 1e-3 * max(vin + s0, 1.0):
            raise AssertionError(f"Tránsito no cierra continuidad: Vin+S0={vin + s0:.1f}, Vout+Sfin={vout + (sfin or 0):.1f} m3 (cola insuficiente).")
    return q, info


class BasinModel:
    def __init__(self, subbasins):
        self.sb = {s.name: s for s in subbasins}
        self.informe = {}

    def _lluvia(self, rain, s, step_s, faltantes):
        serie = rain.at(s.x, s.y)
        if getattr(serie.index, "tz", None) is None and not getattr(rain, "sintetico", False):
            raise ValueError(f"Subcuenca {s.name}: la serie de lluvia no tiene zona horaria; localizarla explícitamente.")
        serie = agregar_conservativo(serie, step_s)
        n_nan = int(serie.isna().sum())
        cobertura = 1 - n_nan / len(serie)
        self.informe[s.name] = {"registros": len(serie), "faltantes": n_nan, "cobertura": cobertura,
                                "lluvia_total_mm": float(serie.sum(skipna=True))}
        if n_nan:
            if faltantes == "error":
                raise ValueError(f"Subcuenca {s.name}: {n_nan} registros ausentes ({cobertura:.1%} de cobertura). "
                                 "No se imputan como cero; usar faltantes='cero_declarado' solo si es una decisión explícita.")
            if faltantes == "cero_declarado":
                self.informe[s.name]["imputacion"] = f"{n_nan} registros ausentes tratados como 0 mm (declarado)"
                serie = serie.fillna(0.0)
        return serie

    def run(self, rain, step_s=300, faltantes="error", ventana="exacta"):
        """Devuelve DataFrame Q(t) en el cierre de cada subcuenca (segundos desde el inicio COMÚN de la lluvia).
        Todas las subcuencas deben compartir inicio, paso y longitud ('exacta'); con ventana='interseccion' se recorta a la
        ventana común explícitamente (sin rellenar ausencias) y queda registrado en self.informe['_ventana']."""
        local = {}
        series = {s.name: self._lluvia(rain, s, step_s, faltantes) for s in self.sb.values()}
        ini = {n: v.index[0] for n, v in series.items()}; fin = {n: v.index[-1] for n, v in series.items()}
        if len(set(ini.values())) > 1 or len(set(fin.values())) > 1:
            if ventana != "interseccion":
                raise ValueError("Las series de lluvia de las subcuencas no comparten ventana temporal (inicio/fin distintos): "
                                 + ", ".join(f"{n}: {ini[n]}..{fin[n]}" for n in list(series)[:4]) + ". Use ventana='interseccion' solo si es intencional.")
            t0, t1 = max(ini.values()), min(fin.values())
            if t0 > t1:
                raise ValueError("Las series de lluvia no tienen ventana común.")
            series = {n: v.loc[t0:t1] for n, v in series.items()}
            self.informe["_ventana"] = {"inicio": str(t0), "fin": str(t1), "recorte": "interseccion"}
        else:
            self.informe["_ventana"] = {"inicio": str(next(iter(ini.values()))), "fin": str(next(iter(fin.values()))), "recorte": "ninguno"}
        for s in self.sb.values():
            p = series[s.name].values
            t, q, info = scs_hydrograph(p, step_s, s.area_km2, s.cn, s.tc_h, lag_h=s.lag_h, prf=s.prf, imperv_frac=s.imperv_frac)
            local[s.name] = pd.Series(q, index=t)
            self.informe[s.name].update({k: info[k] for k in ("volumen_m3", "exceso_mm")})
        done, routed_cache = {}, {}

        def outflow(name):
            if name not in done:
                q = local[name].copy()
                for up in (u for u in self.sb.values() if u.downstream == name):
                    q = q.add(routed(up.name), fill_value=0)
                done[name] = q
            return done[name]

        def routed(name):
            if name not in routed_cache:
                s = self.sb[name]
                q = outflow(name)
                qr, info = muskingum(q.values, step_s, s.reach_k_h, s.reach_x)
                self.informe[name]["transito"] = info
                routed_cache[name] = pd.Series(qr, index=np.arange(len(qr)) * float(step_s))
            return routed_cache[name]

        for n in self.sb:
            routed(n)
        return pd.DataFrame({n: outflow(n) for n in self.sb}).fillna(0)

    @staticmethod
    def volumes(q: pd.Series):
        """Volumen (m3), caudal pico y tiempo al pico de una serie Q(t)."""
        return {"volumen_m3": float(INTEGRATE(q.values, q.index.values)), "Qpico_m3s": float(q.max()),
                "t_pico_h": float(q.idxmax() / 3600)}
