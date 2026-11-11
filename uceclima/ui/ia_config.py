# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""Conectar UCEclima a una IA: genera (y, con un clic del usuario, instala) la entrada del servidor MCP para Claude Desktop, Claude Code (.mcp.json) y VS Code (.vscode/mcp.json).
Fusiona sin borrar nada de lo que ya haya en esos archivos y deja una copia .bak. No toca credenciales: el servidor MCP lee la clave local de ~/.uceclima/api_key.txt."""
import json, os, sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]


class IAConfigError(ValueError):
    pass


def _comando():
    """(command, args, env, cwd) según se ejecute desde el .exe o desde Python."""
    if getattr(sys, "frozen", False):
        return sys.executable, ["--mcp"], {"UCEclima_EXE": sys.executable}, None
    return sys.executable, ["-m", "uceclima.mcp_servidor"], {"PYTHONPATH": str(RAIZ), "UCECLIMA_RAIZ": str(RAIZ), "PYTHONIOENCODING": "utf-8"}, str(RAIZ)


def entrada(destino, carpeta_proyecto=None):
    cmd, args, env, cwd = _comando()
    if carpeta_proyecto:
        env = {**env, "UCECLIMA_PROYECTO": str(Path(carpeta_proyecto).resolve())}     # el agente abre este proyecto
    if destino == "vscode":
        d = {"type": "stdio", "command": cmd, "args": args, "env": env}
        if cwd: d["cwd"] = cwd
        return {"servers": {"uceclima": d}}
    d = {"command": cmd, "args": args, "env": env}
    return {"mcpServers": {"uceclima": d}}


def rutas(carpeta_proyecto=None):
    base = Path(carpeta_proyecto) if carpeta_proyecto else RAIZ
    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return {"claude_desktop": Path(appdata) / "Claude" / "claude_desktop_config.json", "claude_code": base / ".mcp.json", "vscode": base / ".vscode" / "mcp.json"}


def estado(carpeta_proyecto=None):
    out = {}
    for k, p in rutas(carpeta_proyecto).items():
        inst = False
        if p.exists():
            try:
                j = json.loads(p.read_text(encoding="utf-8")); inst = "uceclima" in (j.get("servers") or j.get("mcpServers") or {})
            except Exception:
                inst = False
        out[k] = {"archivo": str(p), "existe": p.exists(), "instalado": inst, "entrada": entrada("vscode" if k == "vscode" else "mcp", carpeta_proyecto if k != "claude_desktop" else None)}
    return out


def instalar(destino, carpeta_proyecto=None):
    p = rutas(carpeta_proyecto).get(destino)
    if p is None:
        raise IAConfigError("Destino desconocido (claude_desktop | claude_code | vscode).")
    nuevo = entrada("vscode" if destino == "vscode" else "mcp", carpeta_proyecto if destino != "claude_desktop" else None)
    clave = "servers" if destino == "vscode" else "mcpServers"
    actual = {}
    if p.exists():
        try:
            actual = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise IAConfigError(f"El archivo {p.name} existe pero no es JSON válido; arréglalo o bórralo antes de instalar.") from e
        if (actual.get(clave) or {}).get("uceclima") == nuevo[clave]["uceclima"]:
            return {"archivo": str(p), "sin_cambios": True, "reiniciar": ""}                    # ya estaba igual: no se reescribe ni se deja .bak
        p.with_name(f"{p.name}.{datetime.now():%Y%m%d_%H%M%S}.bak").write_text(json.dumps(actual, ensure_ascii=False, indent=2), encoding="utf-8")
    actual.setdefault(clave, {})["uceclima"] = nuevo[clave]["uceclima"]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(actual, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"archivo": str(p), "reiniciar": "Claude Desktop: ciérralo del todo (también en la bandeja) y ábrelo de nuevo." if destino == "claude_desktop" else "Recarga la ventana de VS Code / reinicia Claude Code para que vea el servidor."}
