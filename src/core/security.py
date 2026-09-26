"""
Utilidad de hashing de contraseñas.

Implementa ÚNICAMENTE lo necesario para hashear una contraseña de forma
segura antes de persistirla. A propósito NO incluye `verify_password` ni
ninguna lógica de comparación de credenciales: eso es autenticación
(login), y pertenece al ticket "[BACK] Implementar endpoint de login".
Ese ticket debería agregar esa función acá mismo (con `bcrypt.checkpw`),
en vez de duplicar el mecanismo de hashing.

Usa `bcrypt` directamente (sin passlib): passlib está sin mantenimiento
desde 2020 y es incompatible con bcrypt>=4.1 (perdió el atributo
`__about__` que passlib usaba para detectar la versión del backend),
lo que provocaba el error "password cannot be longer than 72 bytes"
incluso con contraseñas cortas.
"""

from __future__ import annotations

import bcrypt

_MAX_PASSWORD_BYTES = 72  # límite duro del algoritmo bcrypt


def hash_password(plain_password: str) -> str:
    """
    Devuelve el hash de una contraseña en texto plano.
    Nunca se persiste, se loguea ni se devuelve la contraseña en texto
    plano, sólo este hash.
    """
    if plain_password is None or plain_password == "":
        raise ValueError("La contraseña no puede estar vacía.")

    password_bytes = plain_password.encode("utf-8")
    if len(password_bytes) > _MAX_PASSWORD_BYTES:
        raise ValueError(f"La contraseña no puede superar los {_MAX_PASSWORD_BYTES} bytes.")

    hashed = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
    return hashed.decode("utf-8")