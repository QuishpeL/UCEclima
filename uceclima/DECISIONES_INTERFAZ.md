# Decisiones de la interfaz de UCEclima

| Decisión | Alternativas | Motivo |
|---|---|---|
| **Servidor local en la biblioteca estándar (`http.server`) + página HTML/CSS/JS propia**, ventana tipo aplicación con Edge/Chrome `--app` | Tkinter (referencia inicial), PySide6 (instalado, ~500 MB), Flask (instalado), Streamlit/Dash | Sin dependencia nueva ni framework pesado; el mismo Python del núcleo; diseño moderno y adaptable (ventana estrecha, teclado, contraste) que Tkinter no da; capturas verificables con Edge sin cabeza; el cálculo vive en otro proceso, así que cambiar la interfaz no toca la ciencia. Costo: HTML/JS a mano (sin componentes de un framework). |
| **Interfaz y cálculo separados**: la interfaz solo valida, lanza `python -m uceclima.ui.worker` y lee archivos | Llamar al solver dentro del servidor | Cancelación segura (se mata el proceso), interfaz que no se congela, registro persistente, corridas interrumpidas detectables. El worker llama a `climanet.pipeline.run` sin cambios. |
| **Una tarea por vez** y topes (250 000 celdas, 12 h simuladas) | Cola de tareas | Pedido explícito: nada de casos grandes ni nocturnos desde la interfaz. |
| **Proyecto = carpeta con `proyecto_uceclima.json`** validado con JSON Schema; rutas relativas resueltas a absolutas antes de pasar al núcleo | Rutas absolutas fijas | Portabilidad entre equipos. Hallazgo: el núcleo resolvía rutas relativas contra el directorio de trabajo; se corrigió en la interfaz (`resolver_rutas`) sin tocar el núcleo. |
| **Nunca sobrescribir**: guardar-como rechaza carpetas con proyecto; cada corrida es una carpeta nueva con marca de tiempo | Sobrescritura con aviso | Pedido explícito. |
| **Seguridad local**: solo 127.0.0.1, comprobación de `Host`, token de sesión en cada POST | Sin protección | Evita que otra página abierta en el navegador dispare acciones (CSRF) y ataques de re-enlace DNS. |
| **Credenciales**: la interfaz no las lee ni las guarda; GEE usa las del sistema | Pedir token en un formulario | Pedido explícito. |
| **«Pendiente» visible**: los botones de funciones no implementadas están desactivados con su motivo; CMIP6 bloqueado con las razones reales de la compuerta | Ocultarlos / simularlos | No hay éxito ficticio. |
| **Mapa estático hecho con los rásteres del núcleo** (matplotlib), sin satélite | Mapa web con teselas | Sin licencias ni Internet; sin superponer agua sobre imágenes reales. En el proyecto sintético lleva marca de agua. |
| **Visor 3D+tiempo**: solo la maqueta sintética de Codex, rotulada | Animar hmax | El solver no exporta estados temporales; no se inventa evolución. |
