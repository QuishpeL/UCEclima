# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""Omega · figuras en INGLÉS solo para los papers (regla del usuario, 27-oct-2026): el programa, los informes y el manual siguen en español.
traducir(fig) recorre todos los textos de una figura de matplotlib (títulos, ejes, leyendas, rótulos, ticks y barra de color) y aplica un diccionario
de frases (de la más larga a la más corta) + coma decimal → punto. restos(fig) devuelve los textos que aún parecen español, para revisarlos."""
import re

FRASES = [
    # --- indicadores ETCCDI y notas (antes que las palabras sueltas)
    ("Ciclo anual: corrección de sesgo QQM\nvalidación cruzada impar/par", "Annual cycle: QQM bias correction\nodd/even cross-validation"),
    ("Intensidad media en días de lluvia (mm/día)", "Simple daily intensity index, SDII (mm/day)"), ("Lluvia en días muy húmedos > p95 (mm)", "Rainfall on very wet days > p95, R95p (mm)"),
    ("Racha húmeda máxima, días ≥ 1 mm (CWD)", "Maximum wet spell, days ≥ 1 mm (CWD)"), ("Racha seca máxima, días < 1 mm (CDD)", "Maximum dry spell, days < 1 mm (CDD)"),
    ("Racha seca máxima CDD (días)", "Maximum dry spell CDD (days)"), ("Días secos consecutivos · CDD (días < 1 mm)", "Consecutive dry days · CDD (days < 1 mm)"),
    ("Lluvia máxima en 24 h · Rx1day (mm)", "Maximum 24-h rainfall · Rx1day (mm)"), ("Precipitación total anual (mm)", "Total annual precipitation · PRCPTOT (mm)"),
    ("Máximo de 1 día (mm)", "Maximum 1-day rainfall, Rx1day (mm)"), ("Máximo de 5 días (mm)", "Maximum 5-day rainfall, Rx5day (mm)"), ("Días con ≥ 20 mm", "Days with ≥ 20 mm, R20mm"),
    ("Meses con SPI-3 ≤ −1 (sequía)", "Months with SPI-3 ≤ −1 (drought)"), ("SPI-12 mínimo del año (sequía)", "Minimum annual SPI-12 (drought)"),
    ("Es un diagnóstico de UN modelo; el ToE del ensamble (ruido interno + entre modelos) está en toe_sn_grande.png.", "This is a SINGLE-model diagnostic; the ensemble ToE (internal + inter-model noise) is shown in the S/N figure."),
    ("(validación cruzada)", "(cross-validation)"), ("validación cruzada", "cross-validation"), ("(mm/día)", "(mm/day)"),
    # --- CMIP6
    ("Time of Emergence — cuándo el cambio supera la variabilidad natural (SSP5-8.5) · serie solo-modelo:", "Time of Emergence — when the change exceeds natural variability (SSP5-8.5) · single-model series:"),
    ("Time of Emergence del ensamble", "ensemble Time of Emergence"), ("Time of Emergence bajo SSP5-8.5", "Time of Emergence under SSP5-8.5"),
    ("la señal no sale de ±1σ de forma permanente", "the signal does not leave ±1σ permanently"), ("no sale de ±1σ de forma permanente", "does not leave ±1σ permanently"),
    ("la señal sale de ±1σ desde", "the signal leaves ±1σ from"), ("Ciclo anual: corrección de sesgo QQM\nvalidación cruzada impar/par", "Annual cycle: QQM bias correction\nodd/even cross-validation"),
    ("Q-Q antes / después (totales mensuales)", "Q-Q before / after (monthly totals)"), ("RMSE ciclo anual", "Annual-cycle RMSE"),
    ("Validación cruzada: calibra con años impares y evalúa en pares (y al revés). La corrección ajusta la distribución histórica; no crea procesos que el modelo no simula (Maraun 2013).",
     "Cross-validation: calibrated on odd years and evaluated on even years (and vice versa). The correction adjusts the historical distribution; it does not create processes the model does not simulate (Maraun 2013)."),
    ("Puntos grises: valor anual del mejor modelo corregido (QQM/QDM). Franja magenta: dispersión de la señal entre modelos. ",
     "Grey dots: annual value of the best bias-corrected model (QQM/QDM). Magenta band: inter-model spread of the signal. "),
    ("Magenta: S/N de cada modelo (trayectorias plausibles) · Blanco: S/N del ensamble (ruido interno + entre modelos) · Líneas amarillas: |S/N| = 1 y 2",
     "Magenta: S/N of each model (plausible trajectories) · White: ensemble S/N (internal + inter-model noise) · Yellow lines: |S/N| = 1 and 2"),
    ("proyección con sesgo corregido (QQM/QDM), no predicción. El ToE del ensamble (ruido interno + entre modelos) está en toe_sn_grande.png.",
     "bias-corrected projection (QQM/QDM), not a prediction. The ensemble ToE (internal + inter-model noise) is in the S/N figure."),
    ("±2σ de la base 1981–2014", "±2σ of the 1981–2014 baseline"), ("±2σ (base 1981–2014)", "±2σ (1981–2014 baseline)"), ("±1σ (variabilidad natural)", "±1σ (natural variability)"),
    ("valor anual ·", "annual value ·"), ("corregido", "bias-corrected"), ("mediana de los modelos", "multi-model median"), ("modelos CMIP6", "CMIP6 models"), ("modelos", "models"),
    ("p10–p90 de", "p10–p90 of"), ("ToE solo-modelo", "single-model ToE"), ("acuerdo de signo", "sign agreement"), ("señal / ruido", "signal / noise"), ("señal", "signal"),
    ("no emerge", "no emergence"), ("cuantiles CHIRPS (mm)", "CHIRPS quantiles (mm)"), ("cuantiles modelo (mm)", "model quantiles (mm)"), ("P mensual (mm)", "Monthly P (mm)"),
    ("lluvia de referencia", "reference rainfall"), ("Mejor modelo = RMSE más bajo del ranking", "Best model = lowest RMSE in the ranking"), ("crudo", "raw"), ("ensamble", "ensemble"),
    ("Lluvia máxima en 24 h", "Maximum 24-h rainfall"), ("Precipitación total anual", "Total annual precipitation"), ("Lluvia total anual", "Total annual rainfall"),
    ("Días secos consecutivos", "Consecutive dry days"), ("días secos consecutivos", "consecutive dry days"), ("días", "days"), ("hoy", "today"), ("años", "years"), ("año", "year"),
    # --- mapas e inundación
    ("calado suavizado solo para visualización", "depth smoothed for display only"), ("calles, edificios y equipamiento OSM", "OSM streets, buildings and facilities"),
    ("evento real, modelo no calibrado", "observed event, uncalibrated model"), ("escenario de diseño, no calibrado", "design scenario, uncalibrated"),
    ("Inundación 2D", "2D flood"), ("evento observado", "observed event"), ("calado p99", "p99 depth"), ("edificios con ≥ 0,5 m", "buildings with ≥ 0.5 m"),
    ("OSM sin edificios en la zona", "no OSM buildings in the area"), ("Edificio con calado ≥ 0,5 m", "Building with depth ≥ 0.5 m"), ("Edificio con calado ≥ 1 m", "Building with depth ≥ 1 m"),
    ("Salud (hospital/clínica)", "Health (hospital/clinic)"), ("Educación", "Education"), ("Policía / bomberos", "Police / fire"), ("Gobierno / municipio", "Government / municipality"),
    ("Ríos (merge MDT + HydroSHEDS)", "Rivers (DEM + HydroSHEDS merge)"), ("Ríos HydroSHEDS", "HydroSHEDS rivers"), ("Calado máximo (m)", "Maximum depth (m)"), ("Calado máximo", "Maximum depth"), ("salida", "outlet"), ("base:", "basemap:"),
    ("Hidrograma en la salida", "Outlet hydrograph"), ("diseño", "design"), ("no calibrado ni validado", "uncalibrated and unvalidated"), ("caudal", "discharge"), ("tiempo", "time"),
    ("lluvia", "rainfall"), ("Lluvia", "Rainfall"), ("Caudal", "Discharge"), ("horas", "hours"),
]
_ES = re.compile(r"[áéíóúñ¿¡]|\b(de|del|los|las|con|sin|para|lluvia|año|señal|modelo|calado|cuenca|evento)\b", re.I)


def _tr(t):
    if not t:
        return t
    for a, b in FRASES:
        t = t.replace(a, b)
    t = re.sub(r"(\d),(\d)", r"\1.\2", t)                                  # coma decimal → punto
    return t


def traducir(fig):
    """Traduce in situ todos los textos de la figura."""
    from matplotlib.text import Text
    for t in fig.findobj(Text):
        s = t.get_text()
        if s:
            t.set_text(_tr(s))
    for ax in fig.axes:                                                    # ticks con formato propio
        for eje in (ax.xaxis, ax.yaxis):
            labs = [l.get_text() for l in eje.get_ticklabels()]
            if any(labs) and any("," in l for l in labs):
                eje.set_ticklabels([_tr(l) for l in labs])
    return fig


def restos(fig):
    from matplotlib.text import Text
    return sorted({t.get_text() for t in fig.findobj(Text) if t.get_text() and _ES.search(t.get_text())})
