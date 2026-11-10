import pytest

from src.core.exceptions import BehaviorNotFoundError, ForbiddenError, InvalidData
from src.models import Behavior, BehaviorType
from src.schemas.behavior import CreateUpdateBehaviorRequest
from src.services.behavior_service import create_behavior, update_behavior
from src.services.user_service import create_user_with_team


@pytest.fixture()
def usuario(session):
    return create_user_with_team(
        session,
        username="nanana10",
        email="nanana@famaf.unc.edu.ar",
        password="Password123!",
        team_data={"team_name": "alfajoresFC", "team_logo": "https://example.com/logos/alfajores.png"},
    )


@pytest.fixture()
def otro_usuario(session):
    return create_user_with_team(
        session,
        username="otro10",
        email="otro@famaf.unc.edu.ar",
        password="Password123!",
        team_data={"team_name": "dulceDeLecheFC", "team_logo": "https://example.com/logos/ddl.png"},
    )


def crear_comportamiento(session, user_id=None, is_default=False):
    behavior = Behavior(name="Nombre", description="Descripcion", code="def on_tick(api):\n    pass",
                        user_id=user_id, is_default=is_default)
    session.add(behavior)
    session.commit()
    return behavior


def cuerpo(name="Nuevo", description="Descripcion nueva", code="def on_tick(api):\n    return", behavior_type=BehaviorType.PLAYER):
    return CreateUpdateBehaviorRequest(name=name, description=description, code=code, behavior_type=behavior_type)


# ---------- post ----------

def test_deberia_crear_comportamiento_propio_no_predeterminado(session, usuario):
    behavior = create_behavior(session=session, user_id=usuario.user_id, payload=cuerpo())

    assert behavior.behavior_id is not None
    assert behavior.name == "Nuevo"
    assert behavior.user_id == usuario.user_id
    assert behavior.is_default is False
    assert behavior.behavior_type == BehaviorType.PLAYER


def test_deberia_lanzar_invalid_data_y_no_crear_si_el_nombre_esta_vacio(session, usuario):
    with pytest.raises(InvalidData):
        create_behavior(session=session, user_id=usuario.user_id, payload=cuerpo(name=""))

    assert session.query(Behavior).filter_by(user_id=usuario.user_id).count() == 0 # chequeo que el usuario no tiene ningun behavior


# ---------- put ----------

def test_deberia_reemplazar_los_tres_campos(session, usuario):
    behavior = crear_comportamiento(session, user_id=usuario.user_id)
    # el nombre y la descripción no cambian, solamente el codigo, pero igual se reemplazan los tres
    payload = cuerpo(name="Nombre", description="Descripcion", code="def on_tick(api):\n    return")

    resultado = update_behavior(payload=payload, user_id=usuario.user_id, behavior_id=behavior.behavior_id, session=session)

    assert resultado.name == "Nombre"
    assert resultado.description == "Descripcion"
    assert resultado.code == "def on_tick(api):\n    return"


def test_deberia_lanzar_invalid_data_y_no_modificar_si_el_nombre_esta_vacio(session, usuario):
    behavior = crear_comportamiento(session, user_id=usuario.user_id)

    with pytest.raises(InvalidData):
        update_behavior(payload=cuerpo(name=""), user_id=usuario.user_id, behavior_id=behavior.behavior_id, session=session)

    session.refresh(behavior)  # refresh vuelve a leer el comportamiento desde la base, para comprobar que no se modifico
    assert behavior.name == "Nombre"


def test_deberia_lanzar_forbidden_si_el_comportamiento_es_predeterminado(session, usuario):
    default = crear_comportamiento(session, user_id=None, is_default=True)

    with pytest.raises(ForbiddenError):
        update_behavior(payload=cuerpo(), user_id=usuario.user_id, behavior_id=default.behavior_id, session=session)


def test_deberia_lanzar_not_found_si_el_comportamiento_no_existe(session, usuario):
    with pytest.raises(BehaviorNotFoundError):
        update_behavior(payload=cuerpo(), user_id=usuario.user_id, behavior_id=7777, session=session)


def test_deberia_lanzar_not_found_si_el_comportamiento_es_de_otro_usuario(session, usuario, otro_usuario):
    ajeno = crear_comportamiento(session, user_id=otro_usuario.user_id)

    with pytest.raises(BehaviorNotFoundError):
        update_behavior(payload=cuerpo(), user_id=usuario.user_id, behavior_id=ajeno.behavior_id, session=session)