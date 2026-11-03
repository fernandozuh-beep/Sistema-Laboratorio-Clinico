# Manual de instalación y modificación · OCAC (laboratorio clínico)

Sigue las partes en orden. Cada paso dice qué hacer y cómo saber que salió bien.

## PARTE 1 · Programas que necesitas
1. **Python 3.12 o 3.13** (python.org). En el instalador marca **Add Python to PATH**. Comprueba: abre una terminal y escribe `python --version`.
2. **PostgreSQL 16 o 17** (postgresql.org). Anota la contraseña del usuario `postgres`. Incluye pgAdmin 4.
3. **Visual Studio Code** (code.visualstudio.com).

## PARTE 2 · Crear la base de datos
1. Abre pgAdmin 4 → inicia sesión con tu contraseña.
2. `Servers` → `PostgreSQL` → clic derecho en **Databases** → **Create** → **Database…**
3. Nombre: `ocac_db` → **Save**.
4. Si ya tenías una `ocac_db` de la versión anterior: clic derecho → **Delete**, y créala de nuevo (el esquema cambió).

## PARTE 3 · Preparar el proyecto
1. Descomprime `ProyectoOCAC.zip` (por ejemplo en `C:\ProyectoOCAC`).
2. VS Code → **Archivo → Abrir carpeta** → elige `ProyectoOCAC`.
3. **Terminal → Nueva terminal**. Crea el entorno virtual:
   `python -m venv venv`
4. Actívalo: Windows `venv\Scripts\activate` · Mac/Linux `source venv/bin/activate`.
   Sabrás que funcionó si ves `(venv)` al inicio. Si PowerShell bloquea el script, ejecuta una vez
   `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` y repite.

## PARTE 4 · Instalar dependencias
Con `(venv)` activo: `pip install -r requirements.txt`. Debe terminar sin la palabra *ERROR*.

## PARTE 5 · Conectar con tu base de datos
Abre `models.py` y busca la línea que empieza con `URL =`. Cambia `TU_CONTRASEÑA` por la tuya:
`postgresql://postgres:MiClave@localhost:5432/ocac_db`
(Si tu contraseña tiene `@`, `#` o `/`, escríbelos como `%40`, `%23`, `%2F`.)

## PARTE 6 · Arrancar
1. `uvicorn main:app --reload`
2. Debe decir `Uvicorn running on http://127.0.0.1:8000`. En el primer arranque crea las tablas y los datos demo.
3. Abre **http://127.0.0.1:8000** en el navegador.
4. Para detener el sistema: `Ctrl + C` en la terminal.

## PARTE 7 · Primer recorrido (contraseña demo de todos: `Ocac2026!`)
| Entra como | Prueba |
|---|---|
| `recepcion` | **+ Nueva orden**, luego **Editar** |
| `qfb.ramirez` | **Resultados** en una orden → captura valores → **→ Validación** → **→ Entregado** |
| `dra.lopez` | Ver resultados, **PDF**, tendencias |
| `admin` | **Usuarios** (crear/desactivar), **Bitácora**, **Eliminar** |

Para ver **gráficas y delta-check**: entra como `qfb.ramirez` y abre la biometría de *José Luis Morales* (hemoglobina 13.8 → 12.1 → 10.2 → 6.4). Verás la gráfica y la etiqueta Δ.
Para ver una **alerta en vivo**: abre dos navegadores (uno como `dra.lopez`, otro como `qfb.ramirez`); captura en el segundo un potasio de 7 en una orden de electrolitos.

## PARTE 8 · Probar el analizador (HL7) y FHIR
1. Con el sistema encendido, abre una **segunda terminal** (con `(venv)`) y ejecuta:
   `python simular_analizador.py OC-DEMO-00006`
2. Debe responder un mensaje ACK con `MSA|AA|Resultados recibidos`. En la pantalla, la orden de HbA1c de Sofía Cabrera pasa a *Procesando* con su resultado.
3. En cualquier orden con resultados, el botón **FHIR** descarga un *Bundle* FHIR R4 (Patient + Observation + DiagnosticReport) con códigos LOINC.
4. Un analizador real debe enviar su mensaje ORU^R01 por HTTP POST a `/api/analizador/hl7` con el encabezado `X-API-Key`. El folio de la orden va en **OBR-3** y cada resultado en un segmento **OBX** (código LOINC o nombre en OBX-3). Muchos equipos hablan HL7 por MLLP/TCP: necesitarás un *gateway* (por ejemplo Mirth Connect) que lo convierta a HTTP.

## PARTE 9 · Cómo modificar cada cosa
| Quiero… | Archivo y lugar |
|---|---|
| Agregar un análisis o parámetro | `logic.py` → diccionario `CATALOGO`. Copia una línea `P("unidad", mín, máx, crít_mín, crít_máx)`. Si quieres FHIR/HL7 por código, agrega su LOINC en `extras.py` → `LOINC` |
| Cambiar rangos normales o críticos | `logic.py` → los números de cada `P(...)` |
| Ajustar sensibilidad del delta-check | `extras.py` → `DELTA_DEFAULT` (%) y `DELTA` (por parámetro) |
| Poner el nombre de tu hospital en el PDF | Variable de entorno `OCAC_HOSPITAL`, o cambia el valor en `extras.py` → `HOSPITAL` |
| Cambiar la clave del analizador | Variable `OCAC_ANALYZER_KEY` (o `extras.py` → `ANALIZADOR_KEY`) |
| Cambiar la clave de firma de sesiones | Variable `OCAC_SECRET` (o `security.py` → `SECRET`), mínimo 32 caracteres |
| Cambiar duración de sesión | `security.py` → `make_token(..., mins=30)` y en `static/index.html` el `15*60e3` de inactividad |
| Cambiar colores | `static/index.html` → bloque `:root{...}` al inicio |
| Cambiar estados del flujo | `logic.py` → `ESTADOS` y `TRANS` (y `ES`/`NEXT` en `index.html`) |
| Cambiar permisos por rol | `main.py` y `extras.py` → `sec.roles("admin","quimico")` en cada ruta |
| Quitar datos demo | `main.py` → borra la llamada `seed()` y crea tu admin desde pgAdmin/consola |

Después de editar un `.py` el servidor se recarga solo (`--reload`). Para variables de entorno en Windows (PowerShell): `$env:OCAC_SECRET="tu-clave-larga"` antes de `uvicorn`.

## PARTE 10 · Problemas comunes
- **`password authentication failed`**: la contraseña de `models.py` no es la de PostgreSQL.
- **`database "ocac_db" does not exist`**: falta la Parte 2.
- **`ModuleNotFoundError`**: no activaste `(venv)` o falta `pip install -r requirements.txt`.
- **`Address already in use`**: hay otro servidor en el puerto 8000; usa `--port 8001`.
- **Falla `psycopg2-binary` con tu versión de Python**: usa Python 3.12/3.13 o cambia en `requirements.txt` por `psycopg[binary]` y la URL a `postgresql+psycopg://...`.
- **La cuenta se bloqueó**: espera 10 minutos o, como admin, edítala en **Usuarios** y guárdala.
- **El PDF no abre**: permite ventanas emergentes para `127.0.0.1`.

## PARTE 11 · Antes de usarlo con datos reales
Este sistema es una base funcional, no un software clínico certificado.
1. Cambia las contraseñas demo y define `OCAC_SECRET` y `OCAC_ANALYZER_KEY`.
2. Sírvelo con **HTTPS** (nginx o Caddy como proxy) y en una red interna del hospital.
3. Haz respaldos: `pg_dump -U postgres ocac_db > respaldo.sql` (programa uno diario).
4. Que el responsable del laboratorio valide los rangos de referencia y valores críticos del catálogo.
5. Revisa con tu área legal/calidad el cumplimiento de la normatividad aplicable (por ejemplo NOM-004-SSA3 sobre expediente clínico y la ley de protección de datos personales).
