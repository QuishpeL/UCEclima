# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""UCEclima: módulos de lluvia/eventos, GEE/CHIRPS, terreno, hidrología, hidráulica y cambio climático sobre el núcleo CLIMANET."""
import sys
from pathlib import Path

_NUCLEO = Path(__file__).resolve().parents[1] / "climanet"          # proyecto CLIMANET (contiene el paquete interior `climanet`)
if str(_NUCLEO) not in sys.path:
    sys.path.insert(0, str(_NUCLEO))
_m = sys.modules.get("climanet")
if _m is not None and not hasattr(_m, "__version__"):               # un namespace accidental (carpeta MILAGRO/climanet) tapa al paquete real
    del sys.modules["climanet"]
__version__ = "9.2.0-lambda"


def _migrar_configuracion():
    """UCEclima usa ~/.uceclima. Si existe la configuración de un nombre anterior (~/.ucemi o ~/.climauce: ID del proyecto de Google Cloud, memoria del premódulo, clave de la API local), se COPIA una sola vez."""
    import shutil
    nuevo = Path.home() / ".uceclima"
    if nuevo.exists():
        return
    for nombre in (".ucemi", ".climauce"):
        viejo = Path.home() / nombre
        if viejo.exists():
            try:
                shutil.copytree(viejo, nuevo)
            except Exception:
                pass
            return


_migrar_configuracion()
