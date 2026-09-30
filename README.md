# FutBot — Backend

Backend de FutBot construido con **FastAPI**. Expone la API REST y los
canales WebSocket definidos en el contrato de API del proyecto.

---

## Índice
1. [Requisitos](#1-requisitos)
2. [Clonar y configurar el entorno](#2-clonar-y-configurar-el-entorno)
3. [Variables de entorno](#3-variables-de-entorno)
4. [Levantar la base de datos](#4-levantar-la-base-de-datos)
5. [Levantar el backend localmente](#5-levantar-el-backend-localmente)
6. [Migraciones con Alembic](#6-migraciones-con-alembic)
7. [Correr los tests](#7-correr-los-tests)
8. [Estructura del proyecto](#8-estructura-del-proyecto)
9. [Notas](#9-notas)

## 1. Requisitos

* Python 3.12+ (incluye el módulo `venv`)
* Docker y Docker Compose (para levantar Postgres localmente)
* `make`
  * **Windows:** `make` no viene instalado por default. Usá Git Bash (viene
    con Git for Windows) o WSL para tener `make` disponible, o instalalo con
    `choco install make` / `scoop install make`. Todos los comandos de este
    README que empiezan con `make` asumen una de estas opciones.

## 2. Clonar y configurar el entorno

```bash
git clone https://github.com/IngSoft1-theGlory/futBot-back.git
cd futBot-back

python3 -m venv .venv
source .venv/bin/activate          # En Windows: .venv\Scripts\activate

cp .env.example .env               # crear el .env (ver sección 3)

make install                       # equivale a: pip install -r requirements.txt
```

> El `.env` se crea **antes** de correr cualquier comando de `make`, ya que
> targets como `docker-up`, `dev`, `migrate` y hasta `test` leen sus
> variables (`DATABASE_URL` no tiene default: si falta, ni siquiera importar
> `src.database.base` funciona — y eso incluye los tests).

## 3. Variables de entorno

Completá los valores necesarios en el `.env` que copiaste en el paso anterior.

Variables disponibles (ver `.env.example`):

| Variable       | Descripción                                              | Default (ejemplo)                                      |
|----------------|-------------------------------------------------------------|----------------------------------------------------------|
| `ENVIRONMENT`      | Entorno de ejecución                                  | `development`                                             |
| `DATABASE_URL` | Cadena de conexión a la base de datos (**requerida**)     | `postgresql://postgres:secretpassword@localhost:5432/futbot_db` |
| `CORS_ORIGINS` | Orígenes permitidos para el frontend  | `http://localhost:5173` |
| `POSTGRES_USER` | Usuario con el que se inicializa el contenedor de Postgres (usado por `docker-compose.yml`) | `postgres` |
| `POSTGRES_PASSWORD` | Contraseña del usuario de Postgres en el contenedor (usado por `docker-compose.yml`) | `secretpassword` |
| `POSTGRES_DB` | Nombre de la base de datos creada al inicializar el contenedor | `futbot_db` |

`DATABASE_URL` no tiene valor hardcodeado en el código: si falta, la app no
levanta y avisa qué variable falta. Es también la misma URL que usa Alembic
(sección siguiente) — no hay una URL separada para migraciones.

## 4. Levantar la base de datos

```bash
make docker-up      # levanta Postgres vía docker-compose
```

Esto crea un contenedor de Postgres con las credenciales definidas en
`docker-compose.yml` (coinciden con el `.env.example` por defecto).

## 5. Levantar el backend localmente

```bash
make dev             # uvicorn con auto-reload en http://localhost:8000
```

o directamente:

```bash
uvicorn src.main:app --reload
```

Endpoints de prueba:

* `GET http://localhost:8000/` → mensaje de bienvenida
* `GET http://localhost:8000/api/v1/health` → `{"status": "ok"}` (200 OK)
* Documentación interactiva: `http://localhost:8000/docs`

> **Importante:** el server ya **no** crea las tablas al arrancar. Antes de
> levantar el backend por primera vez (checkout limpio, o base de datos
> nueva) tenés que aplicar las migraciones — ver sección 6. Si te salteás
> este paso vas a ver `no such table: teams/users` (SQLite) o el equivalente
> en Postgres en el primer request.

## 6. Migraciones con Alembic

El esquema de la base de datos (tablas, columnas, FKs, constraints) está
versionado con [Alembic](https://alembic.sqlalchemy.org/), no se genera más
con `Base.metadata.create_all()` al arrancar la app. Esto permite aplicar
cambios de esquema de forma reproducible en cualquier ambiente (tu máquina,
la de un compañero, CI, producción) sin que cada uno tenga que borrar su
base local a mano cada vez que alguien cambia un modelo.

**La primera vez que levantás el proyecto** (o cada vez que la base está
vacía):

```bash
make migrate         # aplica todas las migraciones pendientes (alembic upgrade head)
```

**Flujo de trabajo cuando cambiás un modelo** (agregás una columna, un
modelo nuevo, etc.):

1. Modificá la clase en `src/models/`, como siempre.
2. Generá el borrador de migración a partir del diff entre los modelos y la
   base actual:
   ```bash
   make makemigrations m="descripción corta del cambio"
   ```
   Esto crea un archivo nuevo en `alembic/versions/`.
3. **Revisá ese archivo a mano antes de commitearlo.** `--autogenerate` no
   es confiable con renames de columna/tabla (los ve como un DROP + un ADD,
   lo que en una base con datos reales te borraría la columna entera) ni
   con algunos tipos de constraints. Si el diff no es lo que esperabas,
   corregilo vos en el archivo generado.
4. Commiteá el script de migración **junto con** el cambio del modelo que lo
   generó — son un solo cambio lógico, no dos PRs separados.
5. Quien pullee tu cambio corre `make migrate` para aplicar la migración
   sobre su base local. Esto reemplaza al viejo "che, borrate la base y
   volvé a levantarla" cuando cambiaba algo.

**Revertir una migración (downgrade):**

Si aplicaste una migración de prueba (o cualquiera que quieras descartar
antes de commitear), no se borra a mano ni con `DROP TABLE` — eso te
desincroniza `alembic_version` del resto y vas a terminar con un estado raro
(esquema real vacío pero Alembic pensando que está todo aplicado). El camino
correcto tiene tres pasos, los tres son necesarios:

```bash
make downgrade                 # deshace la última migración aplicada (un paso)
# o make downgrade rev=<id>    # retrocede hasta una revisión puntual
# o make downgrade rev=base    # deshace todas, deja el esquema vacío
```

1. `make downgrade` — corre el `downgrade()` de la migración actual y mueve
   `alembic_version` a la revisión anterior.
2. Borrá el archivo de esa migración en `alembic/versions/` (si era de
   prueba y no la vas a commitear).
3. Revertí también el cambio en el modelo (`src/models/...`) que la había
   generado — si el modelo sigue declarando el campo pero la migración ya
   no existe, `make makemigrations` te lo va a volver a "detectar" como
   faltante la próxima vez.

Los tres pasos van juntos: solo el `downgrade` arregla la base, pero deja el
modelo y el archivo de migración sueltos si no hacés los otros dos.

**Saber cuál es la versión actual de la Base de datos**
```bash
alembic current
```

**Importante — esto NO es lo mismo que borrar la base de datos.**
`alembic downgrade base` deja el *esquema* vacío (deshace todas las tablas),
pero la base de datos en sí (`futbot_db` como objeto de Postgres) sigue
existiendo. Alembic versiona lo que hay *adentro* de una base que ya existe;
no crea ni destruye la base en sí — eso es un comando de Postgres
(`DROP DATABASE`) o, en desarrollo local, tirar el volumen de Docker
(`docker compose down -v`).

**Cosas que conviene tener claras:**

* Los tests **no** usan Alembic para armar su base (ver sección 7) — sí lo
  hace, a propósito, el único test dedicado a probar que Alembic esté bien
  configurado.
* `make makemigrations` espera `m="mensaje"` (con `=`), **no** `-m "mensaje"`
  como `git commit` o `alembic` directo. Si usás `-m`, Make lo interpreta
  como una flag propia (la ignora) y trata `"mensaje"` como otro target a
  construir — el resultado es una migración generada igual, pero con el
  mensaje vacío (`alembic revision --autogenerate -m ""`), y un
  `make: *** No rule to make target...` al final.
* En Windows, si editás `Makefile` o algún archivo bajo `alembic/` a mano:
  las líneas de comandos del `Makefile` necesitan **tabs literales**, no
  espacios (es una regla de GNU Make, no de estilo). Si después de agregar
  o tocar un target te tira `make: Nothing to be done for '<target>'`, es
  casi siempre esto — muchos editores (VS Code incluido) autoconvierten
  tabs a espacios al pegar código. Si pasa, revisá con un editor que
  muestre whitespace, o volvé a copiar el `Makefile` sin dejar que el
  editor lo reformatee.

## 7. Correr los tests

```bash
make test            # equivale a: PYTHONPATH=. pytest tests/ -v
```

Necesitás el `.env` de la sección 3 incluso para correr los tests: importar
cualquier modelo pasa por `src/database/base.py`, que lee
`settings.DATABASE_URL` al importarse (aunque el motor real de esa URL no
se use en los tests — ver el punto siguiente).

La mayoría de los tests (`tests/unit/test_user_persistence.py`,
`test_register_endpoint.py`, etc.) arma su propia base SQLite en memoria vía
`tests/conftest.py`, completamente aislada de `DATABASE_URL` y de Alembic —
es intencional, para que los tests corran rápido y no dependan de un estado
compartido. La excepción es `test_alembic_migrations.py`, que sí ejecuta
`alembic upgrade head` de verdad, pero contra un archivo SQLite temporal
propio (no toca ni tu base local ni la de `.env`).

## 8. Estructura del proyecto

```
Backend/
├── src/
│   ├── config/       # Settings (variables de entorno)
│   ├── database/     # Engine, sesión y Base de SQLAlchemy
│   ├── schemas/      # Modelos Pydantic (request/response)
│   ├── routes/       # Routers de FastAPI (endpoints HTTP)
│   ├── services/     # Lógica de negocio por dominio
│   ├── engine/       # Motor de simulación del partido (tick a tick)
│   ├── sandbox/      # Validación y ejecución aislada de comportamientos Python
│   ├── realtime/     # Event Bus y canales WebSocket (global y por partido)
│   ├── core/         # Excepciones, seguridad y utilidades transversales
│   ├── utils/        # Helpers generales
│   └── main.py       # Punto de entrada de la app FastAPI
├── alembic/
│   ├── versions/     # Scripts de migración (uno por cambio de esquema)
│   └── env.py        # Configuración de Alembic (target_metadata, DATABASE_URL)
├── alembic.ini        # Config de Alembic (sin sqlalchemy.url hardcodeada)
├── tests/
│   └── unit/
├── docker-compose.yml    # Postgres (+ backend opcional) para desarrollo local
├── Dockerfile
├── Makefile
├── requirements.txt
├── .env.example
└── .gitignore
```

## 9. Notas

* Los módulos de `engine/`, `sandbox/` y `realtime/` están inicializados como
  esqueleto funcional (imports correctos, clases base) para que el resto de
  los endpoints y la lógica de simulación se puedan implementar en los
  próximos tickets sin reorganizar la estructura de carpetas.
* CORS está habilitado para los orígenes definidos en `CORS_ORIGINS`, pensado
  para el desarrollo local del frontend en React.
* **Windows en general:** el resto del flujo (venv, Docker, `make dev`,
  `make migrate`) funciona igual que en Linux/Mac una vez que tenés `make`
  disponible (ver sección 1) — no hay pasos manuales extra específicos de
  Windows más allá de activar el venv con `.venv\Scripts\activate` y tener
  cuidado con tabs vs. espacios si editás el `Makefile` (sección 6).
