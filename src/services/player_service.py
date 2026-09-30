"""
Lógica y persistencia de Player
"""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.core.exceptions import BadRequestError, UnauthorizedError
from src.models.player import Player
from src.repositories.user_repository import get_user_by_id

_NAME_MAX_LENGTH = 50  # mismo límite que la columna players.name
_NUMBER_MAX = 2**31 - 1  # máximo de la columna Integer en Postgres en 32 bits
_ATTRIBUTE_MIN = 20
_ATTRIBUTE_MAX = 100
_ATTRIBUTES_TOTAL = 300


class InvalidPlayerDataError(BadRequestError):
    error_code = "INVALID_PLAYER_DATA"


class InvalidPacssTotalError(BadRequestError):
    error_code = "INVALID_PACSS_TOTAL"


class DuplicateJerseyNumberError(BadRequestError):
    error_code = "DUPLICATE_JERSEY_NUMBER"


def create_player(
    session: Session, ##significa que se espera que session sea un objeto de tipo Session
    *, ##el * significa: todos los argumentos que aparecen después deben pasarse por nombre (esto lo saque de user_service)
    user_id: int,
    name: str,
    number: int,
    power: int,
    agility: int,
    control: int,
    speed: int,
    strength: int,
) -> Player:
    """
    Crea un Player en el equipo del usuario autenticado.

      1. Obtiene el equipo desde el usuario (nunca desde el body).
      2. Valida nombre y número, y después los atributos (sin tocar la DB).
      3. Persiste; si el número ya existe en el equipo, ROLLBACK y error.
    """
    user = get_user_by_id(session, user_id)
    if user is None:
        # token válido de un usuario que ya no existe
        raise UnauthorizedError("El token de sesión no es válido o ha expirado")

    name = name.strip()
    if name == "" or len(name) > _NAME_MAX_LENGTH:
        raise InvalidPlayerDataError(
            f"El nombre no puede estar vacío ni superar los {_NAME_MAX_LENGTH} caracteres." 
        ) 
    if number <= 1 or number > _NUMBER_MAX:
        raise InvalidPlayerDataError("El número de camiseta debe ser un entero positivo.")

    attributes = [power, agility, control, speed, strength]
    if any(not _ATTRIBUTE_MIN <= value <= _ATTRIBUTE_MAX for value in attributes):
        raise InvalidPacssTotalError(
            f"Cada atributo debe estar entre {_ATTRIBUTE_MIN} y {_ATTRIBUTE_MAX}."
        )## any signfica ¿Existe al menos uno que sea verdadero? (esto lo hice para no poner 5 if seguidos)
    if sum(attributes) != _ATTRIBUTES_TOTAL:
        raise InvalidPacssTotalError(
            f"La suma de los atributos debe ser {_ATTRIBUTES_TOTAL}."
        ) ## sum(attributes) suma todos los valores.

    player = Player(
        team_id=user.team_id,
        name=name,
        number=number,
        power=power,
        agility=agility,
        control=control,
        speed=speed,
        strength=strength,
    )

    try:
        session.add(player)
        session.commit()
    except IntegrityError as exc:
        # la unicidad (team_id, number) la garantiza la DB, así también
        # queda cubierta la carrera entre dos requests simultáneos
        session.rollback()
        raise DuplicateJerseyNumberError(
            f"El equipo ya tiene un jugador con el número {number}."
        ) from exc
    except Exception:
        session.rollback()
        raise

    return player
