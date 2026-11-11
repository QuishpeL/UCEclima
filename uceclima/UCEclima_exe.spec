# -*- mode: python ; coding: utf-8 -*-
# Empaquetado de UCEclima (PyInstaller, carpeta). Compilar:  python -m PyInstaller --noconfirm --distpath <destino> --workpath <tmp> uceclima\UCEclima_exe.spec
import sys; sys.setrecursionlimit(8000)
from PyInstaller.utils.hooks import collect_submodules, collect_all
import os
RAIZ = os.path.abspath(os.path.join(SPECPATH, ".."))
datas, binaries, hidden = [], [], []
for m in ("ee", "rasterio", "pyproj", "shapely", "pyogrio", "jsonschema", "jsonschema_specifications", "referencing", "openpyxl", "netCDF4", "cftime", "contextily", "xyzservices", "mercantile"):
    try:
        d, b, h = collect_all(m); datas += d; binaries += b; hidden += h
    except Exception as e:
        print("aviso: no se pudo recoger", m, e)
hidden += ["skimage.morphology"]
hidden += collect_submodules("uceclima") + collect_submodules("climanet") + ["tkinter", "PIL", "PIL.Image", "scipy.special.cython_special", "scipy.spatial.transform._rotation_groups"]
datas += [
    (os.path.join(RAIZ, "uceclima", "ui", "static"), os.path.join("uceclima", "ui", "static")),
    (os.path.join(RAIZ, "uceclima", "ui", "esquema_proyecto.json"), os.path.join("uceclima", "ui")),
    (os.path.join(RAIZ, "uceclima", "datos_referencia"), os.path.join("uceclima", "datos_referencia")),                             # catálogo de estaciones hidrométricas INAMHI
    (os.path.join(RAIZ, "climanet", "climanet"), os.path.join("climanet", "climanet")),
]
for md in ("README.md", "INSTALACION.md", "ESTADO_INTERFAZ.md", "DECISIONES_INTERFAZ.md", "MODULO_CMIP6.md", "AGENTS.md", "DOCUMENTACION_MADRE.md", "CHANGELOG_BETA.md", "PRUEBAS_MANUALES_BETA.md", "PENDIENTES_GAMMA.md", "PENDIENTES_DELTA.md", "PENDIENTES_EPSILON.md", "PENDIENTES_ZETA.md", "PENDIENTES_ETA.md", "PENDIENTES_ETA_9_1.md", "CHANGELOG_LAMBDA.md"):
    datas.append((os.path.join(RAIZ, "uceclima", md), "docs"))
a = Analysis([os.path.join(RAIZ, "uceclima", "app_exe.py")], pathex=[RAIZ, os.path.join(RAIZ, "climanet")], binaries=binaries, datas=datas, hiddenimports=hidden,
             hookspath=[], runtime_hooks=[], excludes=["tensorflow", "keras", "torch", "torchvision", "tensorboard", "jax", "sklearn", "dask", "distributed", "bokeh", "panel", "holoviews", "xarray", "h5py", "zmq", "numba.tests", "scipy.tests", "pandas.tests", "PySide6", "PyQt5", "PyQt6", "IPython", "notebook", "pytest", "sphinx", "botocore", "boto3", "s3transfer", "pyarrow", "fsspec", "s3fs", "gcsfs", "fiona", "tkinter.test", "lib2to3", "unittest"], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="UCEclima", debug=False, strip=False, upx=False, console=False, icon=os.path.join(RAIZ, "uceclima", "ui", "static", "UCEclima.ico"))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="UCEclima")
