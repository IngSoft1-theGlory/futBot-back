"""
Lógica de Behavior.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.core.exceptions import UnauthorizedError, InvalidQueryParamsError, BehaviorNotFoundError, InvalidData, ForbiddenError
from src.models.behavior import Behavior
from src.repositories.behavior_repository import list_behaviors_for_user, get_behavior_by_id
from src.repositories.user_repository import get_user_by_id
from src.schemas.behavior import CreateUpdateBehaviorRequest
import ast

INVALID_DATA = "Los datos ingresados para el comportamiento no son validos"

def create_behavior(session: Session, user_id: int, payload: CreateUpdateBehaviorRequest) -> Behavior:
    validate_fields(payload.name, payload.description, payload.code)
    validate_behavior_code(payload.code)
    try:  
        behavior = Behavior(
            name = payload.name,
            description = payload.description,
            code = payload.code,
            user_id = user_id,
            is_default = False,
            behavior_type = payload.behavior_type
        )
        session.add(behavior)
        session.commit()
    except Exception: 
        session.rollback() # hubo un problema, no guardo el behavior
        raise
    return behavior


def update_behavior(payload: CreateUpdateBehaviorRequest, user_id: int, behavior_id: int, session: Session) -> Behavior: 
    behavior = session.get(Behavior, behavior_id) # busco el comportamiento que quiero actualizar en la db

    if behavior is None or (not behavior.is_default and behavior.user_id != user_id): 
        raise BehaviorNotFoundError("No existe el comportamiento con el ID especificado") # aclaro "not is_default" porque los default nunca tienen user_id
    
    if behavior.is_default:
        raise ForbiddenError("No se puede modificar un comportamiento predeterminado")
    
    validate_fields(payload.name, payload.description, payload.code)
    validate_behavior_code(payload.code)
    
    try:
        behavior.name = payload.name
        behavior.description = payload.description
        behavior.code = payload.code
        session.commit() # no hago add pq ya existe en la db

    except Exception: 
        session.rollback() 
        raise

    return behavior


def validate_behavior_code(code: str) -> None: 
    """ 
    Valida el código de un comportamiento sin ejecutarlo.

    Usa el módulo ast, que convierte el texto del código en un árbol de
    "nodos" (uno por cada pieza: una asignación, un for, una llamada, etc)
    Así se puede revisar qué hay adentro sin correrlo. Ejemplo:

        tree = ast.parse("x = 1")
        [type(n).__name__ for n in ast.walk(tree)]
        # ['Module', 'Assign', 'Name', 'Constant', 'Store']
    """
    try: 
        tree = ast.parse(code) # ast parse devuelve un arbol con la estructura de un programa 
    except SyntaxError: 
        raise InvalidData(INVALID_DATA)

    if "__" in code: 
        raise InvalidData(INVALID_DATA) # no permitimos __import__, __builtin__, etc

    for node in ast.walk(tree): # ast.walk me da los nodos del arbol, los recorro
        if isinstance(node, (ast.For, ast.While, ast.Import, ast.ImportFrom, ast.comprehension)): # lo rechazo si el nodo es alguna de esas cosas 
            raise InvalidData(INVALID_DATA)

    for node in tree.body: # tree.body es el nivel mas arriba del code
        if isinstance(node, ast.FunctionDef) and node.name == "on_tick":
            return # si la funcion existe y esta definida como "on_tick", todo bien

    # pero si no hay on_tick, tira error 
    raise InvalidData(INVALID_DATA)

def validate_fields(name: str, description: str, code: str) -> None:
    if not name.strip() or not description.strip() or not code.strip(): 
        raise InvalidData(INVALID_DATA)
    if len(name) > 100 or len(description) > 500 or len(code) > 5000: 
        raise InvalidData(INVALID_DATA)

def parse_is_default(raw_value: str | None) -> bool | None:
    """
    Convierte el query param is_default ("true" / "false") a bool.
    Si no vino, devuelve None (sin filtro). Cualquier otro valor es 400,
    como pide el contrato (no 422 de validación genérica).
    """
    if raw_value is None:
        return None

    value = raw_value.strip().lower()
    if value == "true":
        return True
    if value == "false":
        return False

    raise InvalidQueryParamsError("El parámetro 'is_default' debe ser un booleano válido.")


def list_behaviors(
    session: Session,
    *,
    user_id: int,
    is_default: str | None = None,
) -> list[Behavior]:
    """
    Devuelve los comportamientos disponibles para el usuario autenticado.

      1) Verifica que el usuario del token siga existiendo.
      2) Valida el filtro is_default.
      3) Consulta los comportamientos (lista vacía si no hay ninguno).
    """
    user = get_user_by_id(session, user_id)
    if user is None:
        # token válido de un usuario que ya no existe
        raise UnauthorizedError("El token de sesión no es válido o ha expirado")

    filter_is_default = parse_is_default(is_default)

    return list_behaviors_for_user(session, user_id, filter_is_default)


def get_behavior(session: Session, *, user_id: int, behavior_id: int) -> Behavior:
    """
    Devuelve los detalles del comportamiento seleccionado.

      1) Verifica que el usuario del token siga existiendo.
      2) Valida que el comportamiento exista.
      3) Consulta si el comportamiento es propio del usuario o si es default.
    """
    user = get_user_by_id(session, user_id)
    if user is None:
        # token válido de un usuario que ya no existe
        raise UnauthorizedError("El token de sesión no es válido o ha expirado")

    behavior = get_behavior_by_id(session, behavior_id)
    if behavior is None:
        raise BehaviorNotFoundError("No existe el comportamiento con el ID especificado")

    can_view = behavior.user_id == user_id or behavior.is_default
    if not can_view:
        raise BehaviorNotFoundError("No existe el comportamiento con el ID especificado")

    return behavior