# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Agentes de VS Code: Copilot (.vscode/mcp.json, clave «servers») y Claude Code (.mcp.json, clave «mcpServers»), ambos con el servidor MCP
`uceclima` (UCEclima.exe --mcp). Se escriben también AGENTS.md y CLAUDE.md (mismo contenido) y la autorización del servidor del proyecto para
Claude Code (.claude/settings.local.json · enabledMcpjsonServers). Antes de reescribir un archivo distinto se deja un .bak. No se guardan credenciales."""
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from . import ia_config

INSTRUCCIONES = """# UCEclima · instrucciones para el agente
Este proyecto se opera con el servidor MCP `uceclima` (VS Code/Copilot: .vscode/mcp.json · Claude Code: .mcp.json).
El servidor abre UCEclima si está cerrado y abre este proyecto. Usa `narrar` para contar en la pantalla qué haces.
- X = condiciones existentes; Y = CMIP6 SSP5-8.5 (magenta).
- No inventar parámetros ni datos; si falta algo, preguntar.
- Una corrida o descarga a la vez. Nada se sobrescribe. Nada se calibra solo: la persona acepta.
- La persona confirma la identidad de cada serie observada.
- Resultados sin calibrar ni validar: se rotulan así y no son predicciones.
"""
_CACHE = {"t": 0.0, "ext": []}


def ejecutable():
    for c in (os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\bin\code.cmd"), shutil.which("code"), shutil.which("code.cmd"),
              os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"), r"C:\Program Files\Microsoft VS Code\Code.exe"):
        if c and Path(c).exists():
            return str(c)
    return None


def _extensiones():
    if time.time() - _CACHE["t"] < 600:
        return _CACHE["ext"]
    exe = ejecutable(); ext = []
    if exe and exe.lower().endswith(".cmd"):
        try:
            r = subprocess.run([exe, "--list-extensions"], capture_output=True, text=True, timeout=30, creationflags=0x08000000 if os.name == "nt" else 0)
            ext = [x.strip().lower() for x in r.stdout.splitlines() if x.strip()]
        except Exception:
            ext = []
    _CACHE.update(t=time.time(), ext=ext)
    return ext


def _escribir(p, texto):
    p = Path(p)
    if p.exists():
        viejo = p.read_text(encoding="utf-8", errors="replace")
        if viejo == texto:
            return False
        p.with_name(f"{p.name}.{time.strftime('%Y%m%d_%H%M%S')}.bak").write_text(viejo, encoding="utf-8")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(texto, encoding="utf-8")
    return True


def estado(carpeta=None):
    ext = _extensiones()
    e = ia_config.estado(carpeta) if carpeta else {}
    return {"vscode": ejecutable() is not None, "ruta_vscode": ejecutable(), "proyecto": str(carpeta) if carpeta else None,
            "copilot_instalado": any(x.startswith("github.copilot") for x in ext), "claude_code_instalado": "anthropic.claude-code" in ext,
            "conectado_copilot": bool(carpeta) and e.get("vscode", {}).get("instalado", False),
            "conectado_claude": bool(carpeta) and e.get("claude_code", {}).get("instalado", False),
            "conectado": bool(carpeta) and e.get("vscode", {}).get("instalado", False) and e.get("claude_code", {}).get("instalado", False)}


def configurar(carpeta):
    """Escribe/actualiza los archivos de ambos agentes en la carpeta del proyecto. Devuelve la lista de archivos tocados."""
    carpeta = Path(carpeta); tocados = []
    for destino in ("vscode", "claude_code"):
        tocados.append(ia_config.instalar(destino, carpeta)["archivo"])
    for nombre in ("AGENTS.md", "CLAUDE.md"):
        if _escribir(carpeta / nombre, INSTRUCCIONES):
            tocados.append(str(carpeta / nombre))
    sl = carpeta / ".claude" / "settings.local.json"
    actual = {}
    if sl.exists():
        try:
            actual = json.loads(sl.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            actual = {}
    habil = list(dict.fromkeys((actual.get("enabledMcpjsonServers") or []) + ["uceclima"]))
    if habil != actual.get("enabledMcpjsonServers"):
        nuevo = {**actual, "enabledMcpjsonServers": habil}
        if _escribir(sl, json.dumps(nuevo, ensure_ascii=False, indent=2)):
            tocados.append(str(sl))
    return tocados


def conectar(carpeta, abrir=True, agente="ambos"):
    if not carpeta:
        raise ValueError("Abre un proyecto: el agente trabaja en su carpeta.")
    tocados = configurar(carpeta)
    exe = ejecutable(); abierto = False
    if abrir and exe:
        subprocess.Popen([exe, str(carpeta)], creationflags=0x08000000 if os.name == "nt" else 0); abierto = True
    e = estado(carpeta)
    falta = []
    if agente in ("copilot", "ambos") and not e["copilot_instalado"]:
        falta.append("GitHub Copilot Chat (extensión de VS Code) no está instalado: sin él VS Code no usa servidores MCP en modo agente.")
    if agente in ("claude", "ambos") and not e["claude_code_instalado"]:
        falta.append("La extensión Claude Code no está instalada en VS Code.")
    msg = ("VS Code abierto en el proyecto. " if abierto else "Configuración lista. ") + (
        "En Claude Code: abre su panel; el servidor «uceclima» ya está autorizado. " if agente in ("claude", "ambos") else "") + (
        "En Copilot: chat en modo Agente → herramientas → uceclima." if agente in ("copilot", "ambos") else "")
    return {**e, "archivos": tocados, "abierto": abierto, "avisos": falta, "mensaje": msg if exe else "Configuración lista; VS Code no está instalado en este equipo."}
