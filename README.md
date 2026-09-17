# Minutas Villa Hermosa

Sistema web para registrar compradores, generar minutas financiadas y crear cronogramas de pago del Condominio Villa Hermosa.

## Descripción

Minutas Villa Hermosa convierte los datos del cliente y del lote en una minuta lista para descargar, sin editar Word manualmente. La aplicación conserva el contenido contractual aprobado, admite uno o varios compradores, organiza pagos de inicial por fecha y genera un cronograma vertical junto con el documento final.

La versión integrada en Control Villa Hermosa se publica en Firebase Hosting, guarda las minutas en Cloud Firestore y genera el archivo Word en el navegador con el motor Python empaquetado en el propio Hosting. La descarga no utiliza Render ni un servidor externo. El servidor Python con SQLite/Supabase permanece como modo independiente y legado.

## Funcionalidades principales

- Inicio de sesión con cuentas autorizadas y roles `admin` y `asesor`.
- Acceso del administrador a todos los expedientes y acceso del asesor únicamente a los suyos.
- Registro de 1 a 10 compradores con identidad, ocupación, estado civil, domicilio y contacto.
- Formulario guiado con validación inmediata y guardado de borradores.
- Cálculo de saldo financiado, cuotas regulares, cuota final y cronograma mensual.
- Cuota regular calculada automáticamente y editable después del cálculo.
- Registro de múltiples pagos de inicial mediante Yape, Plin, depósito, transferencia bancaria o transferencia interbancaria.
- Orden automático de los pagos desde la fecha más antigua hasta la más reciente.
- Generación de una minuta `.docx` a partir de la plantilla interna protegida.
- Cronograma de pagos vertical anexado al final de cada minuta.
- Panel responsive con la identidad visual de Villa Hermosa y A&T House.
- Auditoría básica de creación, actualización, generación y eliminación de expedientes.

## Tecnologías utilizadas

- Python 3.12 y `BaseHTTPRequestHandler` para la API.
- HTML5, CSS3 y JavaScript sin framework para la interfaz.
- SQLite para desarrollo local.
- Firebase Authentication y Cloud Firestore para la versión integrada en producción.
- Firebase Hosting y Pyodide local para generar y descargar el DOCX sin Render.
- SQLite/Supabase y el contenedor Python se conservan para el modo independiente.
- OOXML para completar y generar documentos Word en memoria.

## Sitio web

La versión activa está publicada en [Minutas Villa Hermosa](https://minutas-villa-hermosa.web.app/) e integrada en [Control Villa Hermosa](https://villa-hermosa-lotes.web.app/).

## Repositorio

[github.com/sergilozada/minutas-villahermosa](https://github.com/sergilozada/minutas-villahermosa)

## Objetivo del proyecto

Reducir el tiempo y los errores al preparar contratos financiados, centralizar los expedientes comerciales y mantener una plantilla legal consistente para todo el equipo de Villa Hermosa.

## Arquitectura

```text
Control Villa Hermosa ── sección Minutas (iframe autorizado)
   │
   ▼
Firebase Hosting ── interfaz + motor DOCX en el navegador
   │
   ▼
Firebase Authentication + Cloud Firestore ── sesión y minutas
```

El generador descarga desde el mismo Hosting su motor y plantilla, y produce el `.docx` localmente. El modo Python/Supabase descrito más abajo es legado e independiente: no interviene en la descarga del Control actual.

## Ejecución local

El modo local usa SQLite y no necesita configurar Supabase.

```powershell
python server.py
```

Luego abre [http://127.0.0.1:8000](http://127.0.0.1:8000).

En el primer arranque se crean `admin@villahermosa.com` y `asesor@villahermosa.com`. Define claves únicas de 16 caracteres o más antes de iniciar:

```powershell
$env:VH_ADMIN_PASSWORD = "una-clave-local-segura"
$env:VH_ASESOR_PASSWORD = "otra-clave-local-segura"
python server.py
```

Las variables solo crean cuentas que todavía no existen; no reemplazan la contraseña de una cuenta ya guardada.

## Despliegue legado con Supabase (no usado por Control)

El contenedor incluido admite Cloud Run y Render. En ambos casos utiliza `DATABASE_URL`, escucha el `PORT` del proveedor y activa cookies seguras. El servidor rechaza un arranque alojado sin PostgreSQL; el modo local sigue usando SQLite si no se configura `DATABASE_URL`.

1. Utiliza un proyecto Supabase independiente, sin importar datos de Firebase ni archivos SQLite locales.
2. Obtén la conexión del *transaction pooler* en **Connect → Direct → Transaction pooler**. Codifica los caracteres especiales de la contraseña y añade `?sslmode=require`.
3. Configura las variables privadas indicadas abajo en el alojamiento, nunca como variables `VITE_*`.
4. Despliega usando `Dockerfile`, puerto 8080 y comprobación de salud `/api/health`.
5. El primer arranque crea el esquema privado con RLS y únicamente las cuentas que aún no existen. No migra clientes ni sobrescribe contraseñas existentes.
6. Comprueba login, permisos y generación DOCX con datos ficticios antes de usarlo.
7. Configura **solo la URL HTTPS pública** en `VITE_MINUTAS_SERVICE_URL` del panel React y recompílalo.
8. Configura `VH_FRAME_ANCESTORS` con el origen HTTPS exacto del panel. La aplicación se integra en esa sección mediante un `iframe`; ningún otro sitio queda autorizado a incrustarla.

### Costes y disponibilidad

- [Cloud Run](https://cloud.google.com/run/pricing): sin suscripción mensual fija, con facturación por consumo y cuota gratuita. Requiere una cuenta de facturación; transferencia, compilación y almacenamiento pueden generar cargos. Instancias mínimas 0 y un máximo reducido disminuyen consumo, pero **no son un límite monetario garantizado**.
- [Render Free](https://render.com/docs/free): adecuado para una vista previa; se suspende tras 15 minutos de inactividad y puede tardar aproximadamente un minuto en reactivarse. Tiene límites de uso y el proveedor desaconseja producción. La persistencia se mantiene en Supabase, no en Render Postgres gratuito ni en SQLite.
- [Vercel Hobby](https://vercel.com/docs/limits/fair-use-guidelines) no permite uso comercial; no usar ese plan para el sistema de la inmobiliaria.

No se activa un plan de pago automáticamente.

### Vista previa en Render Free

`render.yaml` define un único servicio **Free**, sin discos ni bases Render adicionales,
y con despliegues automáticos desactivados. Al crear el Blueprint, configura
`DATABASE_URL` (Supabase con SSL) y `VH_ADMIN_EMAIL`. Render genera contraseñas
independientes y aleatorias para administrador y asesor; consérvalas en un gestor
de contraseñas desde la sección privada **Environment**. No se imprimen en los logs
ni se guardan en Git. Configura acceso de GitHub solo a este repositorio.

### Entrada alternativa para Vercel

1. Crea un proyecto de Supabase y ejecuta la migración de `supabase/migrations/`.
2. Copia la conexión del *transaction pooler* de Supabase; es la indicada para funciones serverless.
3. Importa este repositorio en Vercel.
4. Configura las variables privadas del proyecto en Vercel.
5. Despliega y verifica `/api/health`, el login y la descarga de una minuta de prueba.

Variables requeridas en producción:

```dotenv
DATABASE_URL=<conexion-pooler-suministrada-por-supabase>
VH_ADMIN_EMAIL=<correo-administrador-autorizado>
VH_ADMIN_PASSWORD=<secreto-unico-de-16-o-mas-caracteres>
VH_ASESOR_EMAIL=<correo-asesor-autorizado>
VH_ASESOR_PASSWORD=<otro-secreto-unico-de-16-o-mas-caracteres>
VH_COOKIE_SECURE=1
VH_FRAME_ANCESTORS=https://dominio-exacto-del-panel.example
```

No guardes valores reales en `.env.example`, commits, capturas ni logs. `DATABASE_URL` y las contraseñas deben existir únicamente como secretos del proveedor y, si se necesita una copia local, en un archivo ignorado por Git.

## Estructura del proyecto

```text
api/                         entrada serverless opcional para Vercel
backend/                     API, autenticación, datos y motor DOCX
config/minute_schema.json    campos, validaciones y tokens
static/                      interfaz web y activos de marca
supabase/migrations/         esquema PostgreSQL versionado
templates/                   plantilla interna de la minuta
tests/                       pruebas automatizadas
tools/prepare_template.py    preparación reproducible de la plantilla
server.py                    servidor local o alojado con PostgreSQL
Dockerfile                   contenedor sin credenciales ni bases locales
vercel.json                  rutas y configuración de despliegue
```

La base local se guarda en `data/villahermosa.db`. Tanto esa base como `.env`, archivos temporales y credenciales están excluidos de Git.

## Protección de la plantilla

La minuta fuente no se modifica. El script de preparación verifica su SHA-256 auditado, convierte los grupos previstos de `X` en tokens semánticos y consolida los bloques dinámicos en una copia interna. Las letras `X` que forman parte del texto legal se conservan.

Para reconstruir la plantilla interna desde una fuente auditada:

```powershell
python tools\prepare_template.py `
  "<ruta-a-MINUTA-FINANCIADO.docx>" `
  "templates\minuta_financiado_template.docx"
```

## Alcance legal

La automatización no sustituye una revisión jurídica. Antes de usar cambios contractuales en producción, una asesoría legal peruana debe aprobar el texto fijo, la definición colectiva de varios compradores, los casos de compradores casados y cualquier modalidad distinta del financiamiento previsto.
