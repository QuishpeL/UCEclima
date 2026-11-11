# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""R1 · agentes VS Code (Copilot) y Claude Code: archivos del proyecto y servidor MCP legible aunque stdio venga en cp1252 (como en el .exe).
Ejecutar: python -m uceclima.tests.test_r1_agentes"""
import json, os, shutil, subprocess, sys, tempfile, traceback
from pathlib import Path

import uceclima
from uceclima.ui import sitio_api, agente_vscode as AV

TMP = Path(tempfile.mkdtemp(prefix="uceclima_r1_"))
RAIZ = Path(uceclima.__file__).resolve().parents[1]


def test_proyecto_queda_configurado_para_los_dos_agentes():
    car = sitio_api.crear("r1 agentes", -78.4678, -0.1807, base=str(TMP))
    AV.configurar(car)
    vs = json.loads((Path(car) / ".vscode" / "mcp.json").read_text(encoding="utf-8"))["servers"]["uceclima"]
    cc = json.loads((Path(car) / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]["uceclima"]
    assert vs["command"] == cc["command"] and vs["args"] == cc["args"] and cc["env"]["UCECLIMA_PROYECTO"] == str(Path(car).resolve())
    assert (Path(car) / "AGENTS.md").read_text(encoding="utf-8") == (Path(car) / "CLAUDE.md").read_text(encoding="utf-8")
    assert "uceclima" in json.loads((Path(car) / ".claude" / "settings.local.json").read_text(encoding="utf-8"))["enabledMcpjsonServers"]
    assert AV.configurar(car) == [] or not any(".bak" in t for t in AV.configurar(car))          # reabrir no reescribe


def test_mcp_responde_en_utf8_aunque_stdio_sea_cp1252():
    env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    entrada = (json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}) + "\n" + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}) + "\n").encode()
    p = subprocess.run([sys.executable, "-m", "uceclima.mcp_servidor"], input=entrada, capture_output=True, env=env, cwd=str(RAIZ), timeout=60)
    assert all(b < 128 for b in p.stdout), "la salida MCP debe ser ASCII/UTF-8"
    r = [json.loads(l) for l in p.stdout.decode("utf-8").splitlines()]
    assert r[0]["result"]["serverInfo"]["name"] == "uceclima" and len(r[1]["result"]["tools"]) > 30


if __name__ == "__main__":
    fallos = 0
    for n, f in list(globals().items()):
        if n.startswith("test_") and callable(f):
            try:
                f(); print("OK   ", n)
            except BaseException:
                fallos += 1; print("FALLA", n); traceback.print_exc(limit=4, file=sys.stdout)
    shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(1 if fallos else 0)
