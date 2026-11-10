import pytest

from src.core.exceptions import InvalidData
from src.default_behaviors import DEFAULT_BEHAVIORS
from src.engine._03_to_builder.behavior_executor import load_on_tick
from src.schemas.behavior import CreateUpdateBehaviorRequest
from src.services.behavior_service import create_behavior, validate_behavior_code
from src.models.behavior import BehaviorType

VALIDO = "def on_tick(api):\n    return"


# validate_behavior_code (al guardar)

def test_deberia_aceptar_codigo_valido():
    validate_behavior_code(VALIDO, BehaviorType.PLAYER)


def test_deberia_lanzar_invalid_data_si_hay_error_de_sintaxis():
    with pytest.raises(InvalidData):
        validate_behavior_code("def on_tick(api:\n    return", BehaviorType.PLAYER)


def test_deberia_lanzar_invalid_data_si_usa_for():
    with pytest.raises(InvalidData):
        validate_behavior_code("def on_tick(api):\n    for i in range(3):\n        pass", BehaviorType.PLAYER)


def test_deberia_lanzar_invalid_data_si_no_define_on_tick():
    with pytest.raises(InvalidData):
        validate_behavior_code("def otra_funcion(api):\n    return", BehaviorType.PLAYER)


#  load_on_tick (al ejecutar) 

def test_deberia_fallar_al_ejecutar_si_usa_una_funcion_no_permitida():
    # cargar funciona: el error aparece recién cuando se llama a on_tick
    on_tick = load_on_tick("def on_tick(api):\n    return open('x')")
    with pytest.raises(NameError):
        on_tick(None)


def test_deberia_validar_y_cargar_los_comportamientos_por_defecto():
    for behavior in DEFAULT_BEHAVIORS:
        validate_behavior_code(behavior["code"], BehaviorType.PLAYER)
        load_on_tick(behavior["code"]) # Defensive utiliza Point2D asi que con este test ya se que los imports inyectados en namespace funcionan bien

 
# conexion con create behavior

def test_deberia_lanzar_invalid_data_al_crear_con_codigo_invalido():
    body = CreateUpdateBehaviorRequest(
        name="Nuevo",
        description="Descripcion",
        code="def on_tick(api):\n    while True:\n        pass",
        behavior_type=BehaviorType.PLAYER
    )
    # la validacion del codigo ocurre antes de usar la base, por eso no hace falta una sesión real
    with pytest.raises(InvalidData):
        create_behavior(None, 1, body)