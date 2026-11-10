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
from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from src.core.exceptions import InvalidJoinTokenError, JoinTokenExpiredError, UnauthorizedError

import jwt
import bcrypt

_MAX_PASSWORD_BYTES = 72  # límite para algoritmo bcrypt
ALGORITHM = "HS256"  # fijo a propósito: no es un secreto ni varía por entorno

# claims personalizados para diferenciar tokens 
HTTP = "http" 
WS_GLOBAL = "ws_global"
JOIN_LEAGUE = "join_league"

# --- hasheo y verificacion de contraseñas --- 
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


def verify_password(plain_password: str, hashed_password: str) -> bool: 
    """
    Compara una contraseña en texto plano contra un hash ya guardado.
    No decodifica el hash ni lo revierte, sino que bcrypt vuelve a hashear
    `plain_password` internamente y compara los resultados.

    `hashed_password` ya es un hash válido generado por
    hash_password(), no una contraseña sin hashear.
    """

    # bcrypt trabaja a bajo nivel con bytes, asi que es necesario convertir los textos antes de pasarselos
    password_bytes = plain_password.encode("utf-8")
    hashed_bytes = hashed_password.encode("utf-8")

    # bcrypt hashea password_bytes con la misma sal que ya tiene
    # guardada adentro de hashed_bytes, y compara los dos resultados
    matches = bcrypt.checkpw(password_bytes, hashed_bytes)

    return matches


# --- token de acceso a la hora de iniciar sesion --- 
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

    token_type = HTTP 
    encode.update({"type": token_type})

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
         raise UnauthorizedError("El token de sesión no es válido o ha expirado")

    token = credentials.credentials  # el JWT, ya sin el prefijo "Bearer"

    try:
        payload = jwt.decode(token, key=settings.SECRET_KEY, algorithms=[ALGORITHM])

    except jwt.InvalidTokenError:
        # Caso 2: cubre tanto token expirado como cualquier otro token invalido: firma inválida, formato corrupto, algoritmo distinto, etc.
        raise  UnauthorizedError("El token de sesión no es válido o ha expirado")

    if payload.get("type") != HTTP:
        raise UnauthorizedError("El token de sesión no es válido o ha expirado")        

    # paso user_id de vuelta a int para que el resto del código lo use como user_id
    user_id_str = payload.get("sub")
    
    user_id = int(user_id_str)
    return user_id


# --- generacion y decodificacion de token de ws global ---
def create_ws_global_token(user_id: int, expires_delta: timedelta = timedelta(seconds=settings.WS_GLOBAL_TOKEN_EXPIRE_SECONDS),) -> str:
    """
    Genera un JWT firmado que identifica a un usuario ya autenticado para WebSocket.
    No consulta la base de datos ni sabe nada de contraseñas: solo
    empaqueta un user_id y una expiración, y los firma con SECRET_KEY.

    expires_delta tiene un default (la duración configurada en settings),
    pero se puede pasar un valor propio, por ejemplo en los tests, para
    generar a propósito un token ya vencido y probar que se lo rechaza.
    """

    encode = {"sub": str(user_id)}

    token_type = WS_GLOBAL
    encode.update({"type": token_type})

    iat = datetime.now(timezone.utc) # claim estándar: cuando se emitio / issued at
    encode.update({"iat": iat}) 

    expires = iat + expires_delta
    encode.update({"exp": expires}) 

    return jwt.encode(encode, key=settings.SECRET_KEY, algorithm=ALGORITHM)

def decode_ws_global_token(token: str) -> int:
    """
    Decodifica un JWT de WebSocket y devuelve el user_id que contiene.
    Si el token es invalido o expiro, lanza UnauthorizedError.
    """

    try:
        payload = jwt.decode(token, key=settings.SECRET_KEY, algorithms=[ALGORITHM])

    except jwt.InvalidTokenError:
        raise UnauthorizedError("Se requiere autenticación para conectarse a los eventos del sistema")

    if payload.get("type") != WS_GLOBAL:
        raise UnauthorizedError("Se requiere autenticación para conectarse a los eventos del sistema")        

    user_id_str = payload.get("sub")

    user_id = int(user_id_str)

    return user_id

# --- token para unirse a una liga privada --- 
def create_join_token(user_id: int,  league_id: int, expires_delta: timedelta = timedelta(seconds=300)) -> str: 
    encode = {"sub": str(user_id)}
    encode.update({"type": JOIN_LEAGUE})
    encode.update({"league_id": league_id}) 
    
    expires = datetime.now(timezone.utc) + expires_delta
    encode.update({"exp": expires}) 
    
    return jwt.encode(encode, key=settings.SECRET_KEY, algorithm=ALGORITHM)


def verify_join_token(token: str, user_id: int, league_id: int) -> None:
    """
    Valida un join_token: firma, vencimiento, tipo y que haya sido emitido
    para este usuario y esta liga. Lanza JoinTokenExpiredError o InvalidJoinTokenError.
    """
    try:
        payload = jwt.decode(token, key=settings.SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise JoinTokenExpiredError("El token de unión a la liga venció")
    except jwt.InvalidTokenError:
        raise InvalidJoinTokenError("El token de unión a la liga no es válido")

    if (
        payload.get("type") != JOIN_LEAGUE
        or payload.get("sub") != str(user_id)
        or payload.get("league_id") != league_id
    ):
        raise InvalidJoinTokenError("El token de unión a la liga no es válido")
