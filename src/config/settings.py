from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    Configuración de la app leída desde variables de entorno (.env).
    Cada atributo de acá abajo es una variable que pydantic-settings
    busca automáticamente y valida con el tipo indicado, sin que
    tengamos que llamar a os.getenv() a mano en ningún lado.
    """

    PROJECT_NAME: str = "FutBot Backend"

    # Sin valor por defecto: si falta en el .env, la app
    # directamente no arranca en vez de conectarse a cualquier cosa.
    DATABASE_URL: str

    CORS_ORIGINS: str = "http://localhost:5173"

    # La secret_key es para firmar los JWT. Obligatoria y sin default:
    # si alguien la dejara con un valor "de muestra" hardcodeado acá,
    # cualquiera que lea el código podría firmar tokens válidos.
    SECRET_KEY: str

    # Cuánto dura un token antes de que el usuario tenga que loguearse
    # de nuevo
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120

    # Segundos de vida del token temporal para conectarse al WS global
    # (se emite en POST /live-token/global). 
    WS_GLOBAL_TOKEN_EXPIRE_SECONDS: int = 60

    # URL base para construir las direcciones de conexión WebSocket
    WS_BASE_URL : str = "ws://localhost:8000"

    # --- General ---
    ENVIRONMENT: str = "development"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,   
        extra="ignore",        # variables de más en el .env no rompen nada
    )


# Instancia única: el resto de la app importa este `settings` ya armado,
# en vez de crear un Settings() nuevo (y releer el .env) en cada archivo.
settings = Settings()

