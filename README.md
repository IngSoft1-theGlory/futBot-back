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
6. [Estructura del proyecto](#6-estructura-del-proyecto)
7. [Notas](#7-notas)

## 1. Requisitos

* Python 3.12+ (incluye el módulo `venv`)
* Docker y Docker Compose (para levantar Postgres localmente)
* `make`

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
> targets como `docker-up`, `dev` y `test-postgres` leen sus variables.

## 3. Variables de entorno

Completá los valores necesarios en el `.env` que copiaste en el paso anterior.

Variables disponibles (ver `.env.example`):

| Variable       | Descripción                                              | Default (ejemplo)                                      |
|----------------|-----------------------------------------------------------|----------------------------------------------------------|
| `ENVIRONMENT`      | Entorno de ejecución                                  | `development`                                             |
| `DATABASE_URL` | Cadena de conexión a la base de datos (**requerida**)     | `postgresql://postgres:secretpassword@localhost:5432/futbot_db` |
| `CORS_ORIGINS` | Orígenes permitidos para el frontend  | `http://localhost:5173` |
| `POSTGRES_USER` | Usuario con el que se inicializa el contenedor de Postgres (usado por `docker-compose.yml`) | `postgres` |
| `POSTGRES_PASSWORD` | Contraseña del usuario de Postgres en el contenedor (usado por `docker-compose.yml`) | `secretpassword` |
| `POSTGRES_DB` | Nombre de la base de datos creada al inicializar el contenedor | `futbot_db` |

`DATABASE_URL` no tiene valor hardcodeado en el código: si falta, la app no
levanta y avisa qué variable falta.

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

## 6. Estructura del proyecto

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
├── tests/
│   └── unit/
├── docker-compose.yml    # Postgres (+ backend opcional) para desarrollo local
├── Dockerfile
├── Makefile
├── requirements.txt
├── .env.example
└── .gitignore
```

## 7. Notas

* Los módulos de `engine/`, `sandbox/` y `realtime/` están inicializados como
  esqueleto funcional (imports correctos, clases base) para que el resto de
  los endpoints y la lógica de simulación se puedan implementar en los
  próximos tickets sin reorganizar la estructura de carpetas.
* CORS está habilitado para los orígenes definidos en `CORS_ORIGINS`, pensado
  para el desarrollo local del frontend en React.