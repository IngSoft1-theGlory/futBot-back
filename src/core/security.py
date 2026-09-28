"""
Utilidades de seguridad de la aplicación: hashing de contraseñas y
manejo de JWT para autenticación sin estado (stateless).

Hashing:
  - hash_password(): genera el hash de una contraseña para persistir.
JWT:
  - create_access_token(): emite un token firmado que identifica a un
    usuario ya autenticado, con una expiración configurable.
  - get_current_user(): dependencia de FastAPI que valida ese token en
    los endpoints protegidos y devuelve el user_id autenticado.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from src.config.settings import settings
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

import jwt
import bcrypt

_MAX_PASSWORD_BYTES = 72  # límite para algoritmo bcrypt
ALGORITHM = "HS256"  # fijo a propósito: no es un secreto ni varía por entorno

def hash_password(plain_password: str) -> str:
    """ 
    Devuelve el hash de una contraseña en texto plano.
    Nunca se persiste, se loguea ni se devuelve la contraseña en texto
    plano, sólo este hash. 
    """
    
    if plain_password is None or plain_password == "":
        raise ValueError("La contraseña no puede estar vacia.")
    
    # Se convierte la password en byte con estandar utf-8
    password_bytes = plain_password.encode("utf-8")
    if len(password_bytes) > _MAX_PASSWORD_BYTES:
        raise ValueError(f"La contraseña no puede superar los {_MAX_PASSWORD_BYTES} bytes.")

    # Genera un hash seguro y único usando un salt aleatorio
    # salt evita el uso de Rainbow Tables y contraseñas duplicadas visualmente
    # el string resultante incluye automáticamente el salt, el algoritmo y el costo
    hashed = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
    return hashed.decode("utf-8")

def create_access_token(user_id: int, expires_delta: timedelta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),) -> str:
    """
    Genera un JWT firmado que identifica a un usuario ya autenticado.
    No consulta la base de datos ni sabe nada de contraseñas: solo
    empaqueta un user_id y una expiración, y los firma con SECRET_KEY.

    expires_delta tiene un default (la duración configurada en settings),
    pero se puede pasar un valor propio, por ejemplo en los tests, para
    generar a propósito un token ya vencido y probar que se lo rechaza.
    """
    # 'sub' (subject) es un claim estándar de JWT: identifica a quién
    # pertenece el token.
    encode = {"sub": str(user_id)}

    # 'exp' (expiration) es otro claim estándar: pyjwt lo va a comparar
    # solo contra la hora actual al momento de decodificar
    expires = datetime.now(timezone.utc) + expires_delta
    encode.update({"exp": expires})

    # Firma el payload con la clave secreta
    return jwt.encode(encode, key=settings.SECRET_KEY, algorithm=ALGORITHM)

# Si falta el header Authorization, cancelo el autoerror de FastAPI (403) para poder decidir en get_current_user que responder
bearer_scheme = HTTPBearer(auto_error=False)

def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> int:
    """
    Dependencia de FastAPI para proteger endpoints: valida el JWT que
    venga en el header "Authorization: Bearer <token>" y devuelve el
    user_id que contiene. Si el token falta, es inválido o expiró,
    corta la request acá mismo con 401 (el endpoint protegido ni
    llega a ejecutarse).
    """
    # Caso 1: no vino ningun header Authorization.
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail={"error": "UNAUTHORIZED", "message": "El token de sesión no es válido o ha expirado"},
        )

    token = credentials.credentials  # el JWT, ya sin el prefijo "Bearer"

    try:
        payload = jwt.decode(token, key=settings.SECRET_KEY, algorithms=[ALGORITHM])

    except jwt.InvalidTokenError:
        # Caso 3: cubre tanto token expirado como cualquier otro token invalido: firma inválida, formato corrupto, algoritmo distinto, etc.
        raise HTTPException(
            status_code=401,
            detail={"error": "UNAUTHORIZED", "message": "El token de sesión no es válido o ha expirado"},
        )

    # paso user_id de vuelta a int para que el resto del código lo use como user_id
    user_id_str = payload.get("sub")
    user_id = int(user_id_str)

    return user_id
