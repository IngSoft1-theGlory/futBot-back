# FutBot — Backend

Backend de FutBot: API REST con **FastAPI**, base de datos con **SQLAlchemy 2.0**
(migraciones con **Alembic**) y WebSockets para los eventos en vivo.

---

## Antes de empezar

Necesitás tener instalado:

| Herramienta | Para qué | Notas |
|---|---|---|
| **Python 3.12+** | correr el backend | Incluye `venv` |
| **Docker Desktop** (o Docker + Compose) | levantar Postgres | Tiene que estar abierto/corriendo |
| **make** | atajos de comandos | Opcional: cada paso trae su versión "sin make" |

> **Windows:** `make` no viene instalado. Podés usar **Git Bash** (viene con Git for
> Windows) o **WSL**, o instalarlo con `choco install make`. Si preferís no usarlo,
> usá los comandos de la columna **Sin make**: andan en PowerShell.

---

## ÍNDICE
- [Paso a paso: levantar el backend](paso-a-paso-levantar-el-backend)
   - [1. Clonar y crear el entorno virtual](#1-clonar-y-crear-el-entorno-virtual)
   - [2. Instalar dependencias y crear el .env](#2-instalar-dependencias-y-crear-el-env)
   - [3. Levantar la base de datos (Postgres en Docker)](#3-levantar-la-base-de-datos-postgres-en-docker)
   - [4. Crear las tablas (migraciones de Alembic)](#4-crear-las-tablas-migraciones-de-alembic)
   - [5. Cargar los comportamientos por defecto (seed)](#5-cargar-los-comportamientos-por-defecto-seed)
   - [6. Levantar el servidor](#6-levantar-el-servidor)
- [Correr los tests](#correr-los-tests)
- [Migraciones (cuando cambiás un modelo)](#migraciones-cuando-cambiás-un-modelo)
- [Si algo falla](#si-algo-falla)
- [Estructura del proyecto](#estructura-del-proyecto)


## Paso a paso: levantar el backend

Los pasos van en orden. Hacelos una sola vez la primera vez; después alcanza con
los pasos 1 (activar el venv), 4 (si hay migraciones nuevas) y 5.

### 1. Clonar y crear el entorno virtual

**Linux / macOS**
```bash
git clone https://github.com/IngSoft1-theGlory/futBot-back.git
cd futBot-back

python3 -m venv .venv
source .venv/bin/activate
```

**Windows (PowerShell)**
```powershell
git clone https://github.com/IngSoft1-theGlory/futBot-back.git
cd futBot-back

python -m venv .venv
.venv\Scripts\Activate.ps1
```

Si PowerShell dice que *"la ejecución de scripts está deshabilitada"*, corré esto
una vez y volvé a activar:
```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Sabés que el entorno está activo cuando ves `(.venv)` al principio de la línea.
**Todos los comandos siguientes se corren con el entorno activado**, parado en la
carpeta `futBot-back`.

### 2. Instalar dependencias y crear el `.env`

| | Con make | Sin make |
|---|---|---|
| Dependencias | `make install` | `pip install -r requirements.txt` |

Crear el `.env` a partir del ejemplo:

```bash
# Linux / macOS
cp .env.example .env
```
```powershell
# Windows (PowerShell)
Copy-Item .env.example .env
```

Para desarrollo local **solo hay que generar una SECRET_KEY** mediante terminal: 
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```
Luego, los demás valores del ejemplo funcionan tal cual. El `.env` nunca se sube a git.

### 3. Levantar la base de datos (Postgres en Docker)

| | Comando Principal | Alternativo |
|---|---|---|
| **Levantar Postgres para producción** | `make docker-up` | `docker compose up --build -d db` |
| **Levantar Postgres para tests** | `docker compose exec db psql -U postgres -c "CREATE DATABASE futbot_test_db;"` |

Esto deja dos Postgres escuchando en `localhost:5432` con las bases **`futbot_db`**
(la base principal que usa el backend) y **`futbot_test_db`** (la base para correr los tests).Para verificar que está arriba:

```bash
docker compose ps        # la columna STATUS del servicio "db" debe decir "healthy"
```

### 4. Crear las tablas (migraciones de Alembic)

El backend **no crea las tablas solo**: las crea Alembic. Sin este paso la API
levanta pero falla en cuanto toca la base.

| | Con make | Sin make |
|---|---|---|
| Crear/Actualizar tablas | `make migrate` | `alembic upgrade head` |

Repetí este paso **cada vez que hagas pull** de cambios que traigan migraciones
nuevas (carpeta `alembic/versions/`).

### 5. Cargar los comportamientos por defecto (seed)

Sin esto no hay comportamientos predeterminados (Neutro, Ofensivo, Defensor) y no
se pueden armar alineaciones ni jugar un amistoso. Se corre **después** de migrar y
se puede repetir sin problema: no duplica nada.

```bash
python -m src.seed
```

(Es el mismo comando en Linux y en Windows.)

### 6. Levantar el servidor

| | Con make | Sin make |
|---|---|---|
| Desarrollo (recarga solo al editar) | `make dev` | `uvicorn src.main:app --reload --port 8000` |
| Sin recarga | `make run` | `uvicorn src.main:app --port 8000` |

Listo. Probá abrir:

- Documentación interactiva: <http://localhost:8000/docs>
- Salud del servidor: <http://localhost:8000/api/v1/health>

Para frenar el servidor: `Ctrl + C`. Para apagar la base: `make docker-down`
(o `docker compose down`). Los datos se conservan entre reinicios.

---

## Correr los tests

Hay dos formas. **La rápida es la que usás todos los días**; la de Postgres sirve
para chequear que todo ande también contra la base real antes de abrir una PR.

### 1. Tests rápidos (SQLite en memoria)

No necesitan Docker ni base levantada.

| | Con make | Sin make |
|---|---|---|
| Correr todos los tests | `make test` | `pytest tests/ -v` |

### 2. Tests contra Postgres (`futbot_test_db`)

Usan una base **separada** de la principal, para que los tests nunca toquen tus
datos de desarrollo (los tests crean y borran tablas en ella).

**Con make** (Linux / macOS / Git Bash / WSL)
```bash
make test-postgres
```

**Sin make — Linux / macOS**
```bash
TEST_DATABASE_URL=postgresql://postgres:secretpassword@localhost:5432/futbot_test_db pytest tests/ -v
```

**Sin make — Windows (PowerShell)**
```powershell
$env:TEST_DATABASE_URL="postgresql://postgres:secretpassword@localhost:5432/futbot_test_db"
pytest tests/ -v
Remove-Item Env:TEST_DATABASE_URL     # para volver a los tests rápidos
```

> Si cambiaste `POSTGRES_USER` o `POSTGRES_PASSWORD` en tu `.env`, usá esos valores
> en la URL.

---

## Migraciones (cuando cambiás un modelo)

Si agregás o modificás una tabla/columna en `src/models/`, hay que generar una
migración:

| Qué querés hacer | Con make | Sin make |
|---|---|---|
| Aplicar migraciones pendientes | `make migrate` | `alembic upgrade head` |
| Generar una migración nueva | `make makemigrations m="agrego columna X"` | `alembic revision --autogenerate -m "agrego columna X"` |
| Deshacer la última migración | `make downgrade` | `alembic downgrade -1` |
| Volver a una migración puntual | `make downgrade rev=<id>` | `alembic downgrade <id>` |
| Vaciar todo el esquema | `make downgrade rev=base` | `alembic downgrade base` |

**Siempre revisá a mano** el archivo generado en `alembic/versions/` antes de
commitearlo: el autogenerado puede equivocarse.

---

## Si algo falla

| Síntoma | Qué hacer |
|---|---|
| `connection refused` en `localhost:5432` | Postgres no está levantado: `make docker-up` y esperá a que diga `healthy`. Verificá que Docker Desktop esté abierto. |
| `relation "users" does not exist` / tablas inexistentes | Falta correr las migraciones: `make migrate`. |
| No hay comportamientos / no se puede armar la alineación | Falta el seed: `python -m src.seed`. |
| `port is already allocated` (5432) | Ya tenés otro Postgres usando ese puerto. Apagalo o cambiá el puerto en `docker-compose.yml`. |
| `ModuleNotFoundError` | El entorno virtual no está activo (no ves `(.venv)`) o falta `make install`. |
| En PowerShell, `make migrate` / `make test` fallan | Esos comandos del Makefile solo andan en Git Bash/WSL. En PowerShell usá la columna **Sin make**. |
| Tras un pull, errores raros de columnas | `make migrate`. Si tu base de desarrollo es vieja (creada antes de Alembic), la forma más simple es recrearla: `docker compose down -v`, `make docker-up`, `make migrate`, `python -m src.seed`. **Esto borra tus datos locales.** |

---

## Estructura del proyecto

```
futBot-back/
├── src/
│   ├── main.py             # App FastAPI (registra routers y WebSockets)
│   ├── config/             # Settings (lee el .env)
│   ├── core/               # Excepciones, seguridad, utilidades base
│   ├── database/           # Conexión a la base y Base declarativa
│   ├── models/             # Modelos SQLAlchemy (tablas)
│   ├── schemas/            # Esquemas Pydantic (entrada/salida de la API)
│   ├── repositories/       # Acceso a datos
│   ├── services/           # Lógica de negocio
│   ├── routes/             # Endpoints REST
│   ├── realtime/           # WebSockets y bus de eventos
│   ├── engine/             # Motor de simulación del partido (sin base de datos)
│   ├── sandbox/            # Ejecución del código de los comportamientos
│   ├── utils/
│   ├── default_behaviors.py  # Comportamientos predeterminados
│   └── seed.py             # Carga los comportamientos por defecto
├── alembic/versions/       # Migraciones
├── tests/unit/             # Tests
├── docker-compose.yml      # Postgres (y backend)
├── Makefile                # Atajos de comandos
├── requirements.txt
└── .env.example            # Plantilla del .env
```

---

