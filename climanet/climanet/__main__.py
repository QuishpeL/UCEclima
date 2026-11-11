# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""python -m climanet config.json

Solo condición de DISEÑO con IDF histórica. Cambio climático desactivado hasta aprobar la línea base.
"""
import sys, json
from pathlib import Path
from .pipeline import run
from . import baseline


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    cfg = json.load(open(args[0], encoding="utf-8"))
    trs = cfg.get("Tr_list", [cfg.get("Tr", 100)])
    hist = {}
    for tr in trs:
        s = run(cfg, "diseno_idf_historica", tr); hist[tr] = s
        print(f"[diseño IDF histórica Tr{tr}] área>=0.3 m: {s['area_ge_0.3_km2']:.2f} km2  hmax {s['calado_max_m']:.2f} m  P {s['P_total_mm']:.0f} mm  "
              f"bal {s['error_balance_max_pct']:.1e}%  {s['segundos']:.0f}s  IDF: {s['idf_fuente']}")
    val = None
    if cfg.get("validacion_csv"):
        tr = cfg.get("Tr_validacion", trs[0])
        val = baseline.validar_contra_observaciones(Path(cfg["out_dir"]) / f"Tr{tr}_diseno_idf_historica" / "hmax.tif", cfg["validacion_csv"])
        print("Validación vs evidencia:", val)
    ok, det = baseline.evaluar(hist[trs[0]], val)
    print("COMPUERTA LÍNEA BASE:", "APROBADA" if ok else "NO APROBADA", det)
    Path(cfg["out_dir"], "compuerta_linea_base.json").write_text(json.dumps({"aprobada": ok, "detalle": det, "validacion": val}, indent=2), encoding="utf-8")
    if cfg.get("escenarios") and set(cfg["escenarios"]) - {"diseno_idf_historica"}:
        print("Cambio climático DESACTIVADO: solo se ejecutó el diseño con IDF histórica.")


if __name__ == "__main__":
    main()
