"""
Utilidad de hashing de contraseñas.

No existía en el repositorio ningún mecanismo de hashing reutilizable, así
que este módulo implementa ÚNICAMENTE lo necesario para hashear una
contraseña de forma segura antes de persistirla.

A propósito NO incluye una función `verify_password` ni ninguna lógica de
comparación de credenciales: eso es autenticación (login), y pertenece al
ticket "[BACK] Implementar endpoint de login". Cuando ese ticket se
implemente, va a necesitar agregar esa función usando el mismo
`pwd_context` definido acá, para no duplicar el mecanismo de hashing.
"""

from __future__ import annotations

from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    """
    Devuelve el hash de una contraseña en texto plano.
    Nunca se persiste, se loguea ni se devuelve la contraseña en texto
    plano, sólo este hash.
    """
    if plain_password is None or plain_password == "":
        raise ValueError("La contraseña no puede estar vacía.")
    return pwd_context.hash(plain_password)