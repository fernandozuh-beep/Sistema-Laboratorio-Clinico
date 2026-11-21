# MonOCAC — Sistema de Laboratorio Clínico

Sistema web para gestionar las órdenes de un laboratorio clínico: clasifica, ordena y prioriza las solicitudes de análisis para el personal químico-farmacéutico, con alertas en tiempo real cuando un resultado sale crítico.

**Demo en vivo:** https://sistema-laboratorio-clinico.vercel.app

## Capturas

![Pantalla de inicio de sesión](readme-login.png?v=2)

![Panel de órdenes con alertas críticas](readme-panel.png?v=2)

## Qué hace

- **Órdenes por estados y prioridades:** flujo Recepcionado → Procesando → Validación → Entregado, con prioridades Crítica / Urgente / Rutina y tiempo de espera visible por orden.
- **Resultados con banderas clínicas:** cada parámetro se evalúa contra su rango de referencia y sus valores críticos (delta-check incluido contra resultados previos del paciente, con gráfica de tendencia).
- **Alertas críticas en tiempo real:** cuando un analizador o una captura produce un valor crítico, el panel de alertas y las notificaciones WebSocket avisan al instante.
- **Interoperabilidad:** recepción de resultados desde analizadores por **HL7 v2** (ORU^R01), exportación de resultados en **FHIR R4** y reporte imprimible en **PDF**.
- **Roles y bitácora:** usuarios con rol administrador, médico, químico o recepción (el médico ve su especialidad en la barra superior), bloqueo tras intentos fallidos de acceso y bitácora de auditoría de cada acción.
- **Interfaz cuidada:** modo oscuro, diseño adaptable a pantallas chicas y estilos de impresión para el reporte en papel.

## Stack

- **Backend:** FastAPI (Python) + SQLAlchemy, autenticación JWT con contraseñas bcrypt.
- **Base de datos:** PostgreSQL (en producción, Supabase; en local puede usarse SQLite).
- **Frontend:** una sola página servida por el propio backend (`static/index.html` + `styles.css` + `app.js`, sin frameworks).

## Variables de entorno

| Variable | Para qué sirve |
|---|---|
| `DATABASE_URL` | Cadena de conexión a PostgreSQL. **Debe empezar con `postgresql+psycopg2://`** (con `postgresql://` a secas, SQLAlchemy busca otro driver y el despliegue falla). |
| `OCAC_SECRET` | Clave con la que se firman las sesiones (JWT). En producción debe ser larga, aleatoria y secreta; si no se define se usa una de desarrollo que **no** es segura. |
| `OCAC_ANALYZER_KEY` | Clave que deben presentar los analizadores al enviar resultados por HL7. |
| `OCAC_HOSPITAL` | Nombre del hospital que aparece en la interfaz y en los reportes (por defecto, «Hospital General»). |

## Ejecución local

```bash
python -m venv venv
source venv/bin/activate        # en Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Abre http://127.0.0.1:8000 — si la base de datos está vacía, el sistema siembra usuarios y órdenes de demostración al arrancar.

> Para probar el envío de resultados como lo haría un analizador, revisa `simular_analizador.py`.

## Estructura

| Archivo | Contenido |
|---|---|
| `main.py` | API de órdenes, autenticación, estados, estadísticas y WebSocket de alertas. |
| `extras.py` | HL7 de analizadores, exportación FHIR, reporte PDF, delta-check e historial, gestión de usuarios. |
| `logic.py` | Catálogo de análisis con rangos de referencia y valores críticos. |
| `models.py` | Modelos de datos (usuarios, pacientes, órdenes, auditoría). |
| `security.py` | Hash de contraseñas y tokens de sesión. |
| `static/` | La página del sistema: `index.html`, `styles.css` y `app.js`. |
