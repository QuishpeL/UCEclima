# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
import urllib.request, json, os
B="http://127.0.0.1:8765"
clave=open(os.path.join(os.environ["USERPROFILE"],".uceclima","api_key.txt")).read().strip()
def post(r,c=None):
    q=urllib.request.Request(B+r,data=json.dumps(c or {}).encode(),method="POST",headers={"Content-Type":"application/json","Authorization":"Bearer "+clave})
    try:
        with urllib.request.urlopen(q,timeout=600) as x: return x.status,json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code,json.loads(e.read())
def get(r):
    with urllib.request.urlopen(B+r,timeout=300) as x: return json.loads(x.read())
