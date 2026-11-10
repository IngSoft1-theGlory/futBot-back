# FutBot — Backend

API REST con **FastAPI**, base de datos con **SQLAlchemy 2.0** (migraciones con **Alembic**) y WebSockets para los eventos en vivo.

## Requisitos

- **Python 3.11+**
-- **Docker** (para Postgres): en Windows o macOS, con Docker Desktop abierto; en Linux, con el servicio de Docker activo.
- **make** (opcional). En Windows usá Git Bash o WSL; si no, mirá la tabla [Sin make](#sin-make).

## Levantar el backend (primera vez)

**1. Clonar y crear el entorno virtual**

```bash
git clone https://github.com/IngSoft1-theGlory/futBot-back.git
cd futBot-back
python3 -m venv .venv          # Windows: python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\Activate.ps1
```

Si PowerShell dice que la ejecución de scripts está deshabilitada, corré una vez `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`. Sabés que el entorno está activo cuando ves `(.venv)`. Todos los comandos siguientes se corren con el entorno activo.

**2. Instalar dependencias y crear el `.env`**

```bash
make install
cp .env.example .env           # Windows: Copy-Item .env.example .env
```

En el `.env` hay que completar la `SECRET_KEY`: pedísela al equipo (usamos la misma). Si trabajás solo, generá una con `python -c "import secrets; print(secrets.token_hex(32))"`. El resto de los valores funciona tal cual. El `.env` nunca se sube a git.

**3. Levantar Postgres**

```bash
make docker-up
docker compose ps              # el servicio "db" debe decir "healthy"
```

Solo si vas a correr los tests contra Postgres, creá una vez su base:

```bash
docker compose exec db psql -U postgres -c "CREATE DATABASE futbot_test_db;"
```

**4. Crear las tablas.** El backend no las crea solo: las crea Alembic.

```bash
make migrate
```

**5. Cargar los comportamientos por defecto** (Neutro, Ofensivo, Defensor). Se puede repetir sin duplicar nada.

```bash
python -m src.seed
```

**6. Levantar el servidor**

```bash
make dev
```

Documentación: <http://localhost:8000/docs> · Salud: <http://localhost:8000/api/v1/health>

Para frenar el servidor: `Ctrl + C`. Para apagar la base: `make docker-down` (los datos se conservan).

**Las próximas veces** alcanza con: activar el entorno, `make docker-up` (si Docker estaba apagado), `make migrate` (si hay migraciones nuevas) y `make dev`.

## Tests

- `make test`: con SQLite en memoria. No necesitan Docker.
- `make test-postgres`: contra la base `futbot_test_db`. 

## Migraciones

Si cambiás un modelo en `src/models/`, generá una migración y **revisala a mano** antes de commitearla.

| Qué querés hacer | Comando |
|---|---|
| Aplicar pendientes | `make migrate` |
| Generar una nueva | `make makemigrations m="agrego columna X"` |
| Deshacer la última | `make downgrade` |
| Volver a una puntual | `make downgrade rev=<id>` |

## Sin make

| Con make | Sin make |
|---|---|
| `make install` | `pip install -r requirements.txt` |
| `make docker-up` | `docker compose up --build -d db` |
| `make migrate` | `alembic upgrade head` |
| `make dev` | `uvicorn src.main:app --reload --port 8000` |
| `make test` | `pytest tests/ -v` |
| `make test-postgres` (Linux/macOS) | `TEST_DATABASE_URL=postgresql://postgres:secretpassword@localhost:5432/futbot_test_db pytest tests/ -v` |
| `make test-postgres` (PowerShell) | `$env:TEST_DATABASE_URL="postgresql://postgres:secretpassword@localhost:5432/futbot_test_db"; pytest tests/ -v` |

## Si algo falla

| Síntoma | Qué hacer |
|---|---|
| `connection refused` en `localhost:5432` | Postgres no está levantado: `make docker-up` y verificá que Docker esté abierto. |
| Tablas inexistentes (`relation "users" does not exist`) | Falta `make migrate`. |
| No hay comportamientos | Falta el seed: `python -m src.seed`. |
| `port is already allocated` (5432) | Otro Postgres usa ese puerto: apagalo o cambiá el puerto en `docker-compose.yml`. |
| `ModuleNotFoundError` | El entorno virtual no está activo o falta `make install`. |
| Errores raros tras un pull | `make migrate`. Si tu base es vieja, recreala (**borra tus datos locales**): `docker compose down -v`, `make docker-up`, `make migrate`, `python -m src.seed`. |

## Estructura

```
futBot-back/
├── src/
│   ├── main.py                # App FastAPI (routers y WebSockets)
│   ├── config/                # Settings 
│   ├── core/                  # Excepciones y seguridad
│   ├── database/              # Conexión a la base
│   ├── models/                # Tablas (SQLAlchemy)
│   ├── schemas/               # Entrada y salida de la API (Pydantic)
│   ├── repositories/          # Acceso a datos
│   ├── services/              # Lógica de negocio
│   ├── routes/                # Endpoints REST y WebSockets
│   ├── realtime/              # Conexiones en vivo y bus de eventos
│   ├── engine/                # Motor de simulación 
│   ├── utils/
│   ├── default_behaviors.py   # Comportamientos predeterminados
│   ├── penalty_behaviors.py   # Comportamientos del sistema para los penales
│   └── seed.py                # Carga los comportamientos por defecto
├── alembic/versions/          # Migraciones
├── tests/unit/                # Tests
├── docker-compose.yml         # Postgres y backend
├── Dockerfile
├── Makefile                   # Atajos de comandos
├── requirements.txt
└── .env.example               # Plantilla del .env
```
