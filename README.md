# Minutas Villa Hermosa

Sistema web para registrar compradores, generar minutas financiadas y crear cronogramas de pago del Condominio Villa Hermosa.

## Descripción

Minutas Villa Hermosa convierte los datos del cliente y del lote en una minuta lista para descargar, sin editar Word manualmente. La aplicación conserva el contenido contractual aprobado, admite uno o varios compradores, organiza pagos de inicial por fecha y genera un cronograma vertical junto con el documento final.

El proyecto funciona con SQLite durante el desarrollo local y utiliza Supabase Postgres en producción. La interfaz y la API Python se publican en Vercel.

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
- Supabase Postgres para persistencia en producción.
- Vercel Functions para alojamiento de la web y la API.
- OOXML para completar y generar documentos Word en memoria.

## Sitio web

La aplicación se despliega en Vercel. La URL de producción se incorpora aquí después del primer despliegue.

## Repositorio

[github.com/sergilozada/minutas-villahermosa](https://github.com/sergilozada/minutas-villahermosa)

## Objetivo del proyecto

Reducir el tiempo y los errores al preparar contratos financiados, centralizar los expedientes comerciales y mantener una plantilla legal consistente para todo el equipo de Villa Hermosa.

## Arquitectura

```text
Navegador
   │
   ▼
Vercel ── interfaz estática + función Python + generación DOCX
   │
   ▼
Supabase Postgres ── usuarios, sesiones, minutas y auditoría
```

Supabase y Vercel se usan juntos: Supabase no hospeda este backend Python y el disco de las funciones de Vercel no sirve para conservar una base SQLite.

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

## Despliegue en Vercel y Supabase

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
```

No guardes valores reales en `.env.example`, commits, capturas ni logs. `DATABASE_URL` y las contraseñas deben existir únicamente como secretos del proveedor y, si se necesita una copia local, en un archivo ignorado por Git.

## Estructura del proyecto

```text
api/                         entrada serverless para Vercel
backend/                     API, autenticación, datos y motor DOCX
config/minute_schema.json    campos, validaciones y tokens
static/                      interfaz web y activos de marca
supabase/migrations/         esquema PostgreSQL versionado
templates/                   plantilla interna de la minuta
tests/                       pruebas automatizadas
tools/prepare_template.py    preparación reproducible de la plantilla
server.py                    servidor de desarrollo local
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
