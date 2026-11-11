# UCEclima Delta · pendientes

Delta (5.0.0, 23-oct-2026) es la **última versión** prevista (Alfa → Beta → Gamma → Delta). Se instala aparte y no borra Gamma. Lo hecho está en `CHANGELOG_BETA.md`; la lista de Gamma sigue en `PENDIENTES_GAMMA.md`.

## Hecho en Delta
D1 recesión k en el barrido · D2 paso horario y lag 6–120 h · D3 humedad antecedente (opción) · D4 control de lluvia · D5 benchmark sin habilidad y GR4J · G5, G8, G10, G11, G13 (= D4), G12 (= D2, solo si hay lluvia horaria), G17, G22 (aviso).

## Sigue pendiente (no se tocó para no interferir)
| # | Qué falta |
|---|---|
| G2 | «Rellenar depresiones» ofrecido en la interfaz pero rechazado por el núcleo. |
| G3 | Tiempo simulado que no se adapta al tamaño de la cuenca; tope de 12 h en casos grandes. |
| G4 | Mapa de calado sin cuenca ni salida; sin hidrograma 2D en la salida. |
| G6 | Catálogo de coordenadas no aplicado al confirmar archivo por archivo. |
| G7 | Tipo de serie decidido por el nombre aunque se pase `tipo_defecto`. |
| G9 | Lo que hace un agente por la API no se refleja en la ventana abierta. |
| G12 | En Chalpi y Tambo solo hay lluvia diaria: el lag sigue sin ser identificable con esos datos. |
| G14 | WRF nunca probado con un `wrfout` real. |
| G16 | Informe del proceso en PDF desde la interfaz. |
| G19 | Pesos distintos entre el factor anual (quintiles) y el ToE (ClimWIP). |
| G20 | Resto: capa de diferencia Y − X y tabla X frente a Y en el visor. |
| G22 | El aviso no corrige: la persona decide qué periodo vale. |
| Benchmark | GR4J solo diario; ETP constante (sin serie de ETP). |
