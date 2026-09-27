"""
Utilidad de hashing de contraseñas.

Implementa UNICAMENTE lo necesario para hashear una contraseña de forma
segura antes de persistirla

NO incluye
- verificacion de_password 
- ni lógica de comparación de credenciales
"""

from __future__ import annotations
import bcrypt
_MAX_PASSWORD_BYTES = 72  # límite para algoritmo bcrypt


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