# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Módulo 1 — Lluvia y eventos. Dos objetos SEPARADOS que nunca se convierten entre sí en silencio:

  DisenoIDF        tormenta de diseño (Tr, duración, distribución por bloques alternos). Sin fecha meteorológica inherente.
  EventoObservado  lluvia por intervalos de un pluviógrafo (fechas, zona horaria, procedencia). Se usa tal cual en el forzamiento.

Reglas: la lluvia observada no se reemplaza por bloques IDF; no se inventa lluvia subdiaria; las ausencias no son cero; la lluvia diaria solo puede
convertirse a intervalos con `desagregar_uniforme`, que la rotula `desagregada` (no observada) y declara su incertidumbre.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import math
import numpy as np
import pandas as pd

from .eventos import Evento, validar_hietograma


# --------------------------------------------------------------------------- diseño IDF
@dataclass
class DisenoIDF:
    idf: pd.DataFrame                  # filas Tr (años), columnas duración (min), valores intensidad (mm/h)
    tr: int
    duracion_min: int
    fuente: str                        # p. ej. "INAMHI libro, estación M0037" o "Excel Caiza 2026 (CUMBE)"
    bloque_min: int = 5
    factor: float = 1.0                # histórico = 1; un factor distinto debe venir de un módulo climático con procedencia
    fecha_contexto: str = None         # si se da, el experimento es HÍBRIDO (no un evento observado)

    def __post_init__(self):
        if self.factor != 1.0:
            raise ValueError("Factor ≠ 1 solo desde el módulo de cambio climático (bloqueado hasta validar la línea base).")
        if self.tr not in self.idf.index:
            raise ValueError(f"Tr {self.tr} no está en la IDF (disponibles: {list(self.idf.index)}); no se extrapola en silencio.")

    @property
    def etiqueta(self):
        return "experimento_hibrido_diseno_con_fecha_de_contexto" if self.fecha_contexto else "diseno_idf"

    def hietograma(self):
        """Bloques alternos con el volumen exacto de la curva IDF. Devuelve bordes (s desde el inicio) y mm por bloque."""
        from climanet import idf as I
        edges, blocks = I.design_storm(self.idf, self.tr, self.duracion_min, self.factor, self.bloque_min)
        return {"tipo": self.etiqueta, "edges_s": edges, "mm": blocks, "fuente_idf": self.fuente, "tr": self.tr,
                "duracion_min": self.duracion_min, "sin_fecha_meteorologica": self.fecha_contexto is None,
                "fecha_contexto": self.fecha_contexto,
                "volumen_mm": float(blocks.sum()), "volumen_esperado_mm": self.intensidad_media_mm_h() * self.duracion_min / 60,
                "aviso": "No es un evento observado." + (" Experimento híbrido: la fecha es solo contexto." if self.fecha_contexto else "")}

    def intensidad_media_mm_h(self):
        d, i = self.idf.columns.astype(float).values, self.idf.loc[self.tr].values.astype(float)
        if not (d[0] <= self.duracion_min <= d[-1]):
            raise ValueError("La duración está fuera del soporte de la IDF.")
        return float(np.exp(np.interp(math.log(self.duracion_min), np.log(d), np.log(i))))


# --------------------------------------------------------------------------- evento observado
TIPOS = {"observada", "estimada", "desagregada"}


@dataclass
class EventoObservado:
    evento: Evento
    inicios: list
    finales: list
    mm: list
    tipo: str = "observada"
    fuente: str = "pluviografo"
    procedencia: dict = field(default_factory=dict)       # archivo, hash, escala/reloj confirmados, etc.

    def __post_init__(self):
        if self.tipo not in TIPOS:
            raise ValueError(f"tipo debe ser {sorted(TIPOS)}")
        self.resumen = validar_hietograma(self.inicios, self.finales, self.mm, self.evento)      # continuidad, zona horaria, ausencias≠0

    @classmethod
    def desde_csv(cls, path, evento, tipo="observada", **kw):
        d = pd.read_csv(path)
        faltan = {"inicio", "fin", "lluvia_mm"} - set(d.columns)
        if faltan:
            raise ValueError(f"Faltan columnas {sorted(faltan)}")
        if d["lluvia_mm"].isna().any():
            raise ValueError("Hay lluvia ausente: no se reemplaza por cero; resolver antes de modelar.")
        return cls(evento, d["inicio"].tolist(), d["fin"].tolist(), d["lluvia_mm"].astype(float).tolist(), tipo=tipo, **kw)

    def _t(self):
        t0 = datetime.fromisoformat(self.inicios[0])
        e = [(datetime.fromisoformat(x) - t0).total_seconds() for x in self.inicios] + [(datetime.fromisoformat(self.finales[-1]) - t0).total_seconds()]
        return np.array(e)

    def a_forzamiento(self):
        """Bordes (s) y mm por intervalo EXACTAMENTE como se observaron (sin remuestrear ni pasar por bloques IDF)."""
        return {"tipo": self.tipo, "edges_s": self._t(), "mm": np.array(self.mm, float), "volumen_mm": float(sum(self.mm)),
                "inicio": self.inicios[0], "fin": self.finales[-1], "estacion": self.evento.estacion, "fuente": self.fuente}

    def maxima_por_duracion(self, duraciones_min):
        """Máxima profundidad en cualquier ventana de la duración dada, suponiendo intensidad uniforme DENTRO de cada intervalo
        (supuesto declarado). La ventana óptima empieza o termina en un borde de intervalo, por lo que el cálculo es exacto bajo ese supuesto."""
        t = self._t(); P = np.r_[0.0, np.cumsum(self.mm)]
        out = {}
        for d in duraciones_min:
            D = d * 60.0
            if D > t[-1] + 1e-9:
                out[d] = {"profundidad_mm": None, "motivo": "ventana mayor que el evento"}; continue
            cand = np.unique(np.r_[t, t - D]); cand = cand[(cand >= -1e-9) & (cand + D <= t[-1] + 1e-9)]
            best = max((np.interp(s + D, t, P) - np.interp(s, t, P)) for s in cand)
            out[d] = {"profundidad_mm": float(best), "intensidad_mm_h": float(best / (D / 3600)), "supuesto": "intensidad uniforme dentro de cada intervalo"}
        paso_max = float(np.max(np.diff(t)) / 60)
        for d, v in out.items():
            if v["profundidad_mm"] is not None and d < paso_max:
                v["advertencia"] = f"duración menor que el intervalo más largo ({paso_max:.0f} min): no resuelta por el registro"
        return out

    def comparar_con_idf(self, idf, duraciones_min=(15, 30, 60, 120, 360)):
        """Tr implícito de la máxima observada por duración, interpolando ln i vs ln Tr de la IDF. Fuera de su rango de Tr: solo se indica '<' o '>'."""
        res = {}
        mx = self.maxima_por_duracion(duraciones_min)
        trs = np.array(idf.index, float)
        for d, v in mx.items():
            if v["profundidad_mm"] is None or "advertencia" in v or d not in idf.columns:
                res[d] = {**v, "Tr_implicito": None, "nota": "no comparable (ventana, resolución o duración ausente en la IDF)"}; continue
            i_idf = idf[d].values.astype(float); i_obs = v["intensidad_mm_h"]
            if i_obs < i_idf.min(): tr = f"< {trs.min():g}"
            elif i_obs > i_idf.max(): tr = f"> {trs.max():g}"
            else: tr = float(np.exp(np.interp(math.log(i_obs), np.log(i_idf), np.log(trs))))
            res[d] = {**v, "Tr_implicito": tr, "i_idf_Tr_min_max_mm_h": [float(i_idf.min()), float(i_idf.max())]}
        return res


def desagregar_uniforme(fechas_dia, mm_dia, evento, zona="America/Guayaquil", paso_min=60):
    """Reparto UNIFORME conservativo de lluvia diaria en intervalos. No crea información subdiaria: el resultado se rotula `desagregada`
    y debe tratarse con incertidumbre alta (se pierde el pico). Solo para análisis exploratorio; nunca etiquetar como observación."""
    from zoneinfo import ZoneInfo
    inicios, finales, mm = [], [], []
    n = 24 * 60 // paso_min
    for f, m in zip(fechas_dia, mm_dia):
        if m is None or not math.isfinite(m) or m < 0:
            raise ValueError("Día con lluvia ausente o negativa: no se desagrega ni se rellena.")
        d0 = datetime.fromisoformat(f).replace(tzinfo=ZoneInfo(zona))
        for k in range(n):
            a = d0 + timedelta(minutes=k * paso_min); b = a + timedelta(minutes=paso_min)
            inicios.append(a.isoformat()); finales.append(b.isoformat()); mm.append(m / n)
    return EventoObservado(evento, inicios, finales, mm, tipo="desagregada", fuente="lluvia diaria desagregada uniformemente",
                           procedencia={"metodo": "uniforme", "paso_min": paso_min, "incertidumbre": "alta: se desconoce la distribución intradiaria; pico subestimado"})
