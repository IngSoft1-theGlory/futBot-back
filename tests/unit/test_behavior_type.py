"""
Tests del tipo de comportamiento (PLAYER / COACH)
"""

from __future__ import annotations

from src.models import Behavior
from src.models.behavior import BehaviorType
from src.schemas.behavior import CreateUpdateBehaviorRequest
from src.services.behavior_service import (
    create_behavior,
    get_behavior,
    list_behaviors,
    update_behavior,
)

CODIGO = "def on_tick(api):\n    return"


def cuerpo_sin_tipo():
    """Pedido sin indicar el tipo."""
    return CreateUpdateBehaviorRequest(name="Nuevo", description="Descripcion", code=CODIGO)


def cuerpo_con_tipo(behavior_type):
    """Pedido indicando el tipo."""
    return CreateUpdateBehaviorRequest(
        name="Nuevo", description="Descripcion", code=CODIGO, behavior_type=behavior_type
    )


def crear_en_base(session, user_id, behavior_type=BehaviorType.PLAYER):
    behavior = Behavior(
        name="Nombre", description="Descripcion", code=CODIGO,
        user_id=user_id, is_default=False, behavior_type=behavior_type,
    )
    session.add(behavior)
    session.commit()
    return behavior


# crear 

def test_deberia_crear_como_player_si_no_se_indica_el_tipo(session, usuario_con_equipo):
    behavior = create_behavior(session, usuario_con_equipo.user_id, cuerpo_sin_tipo())

    assert behavior.behavior_type == BehaviorType.PLAYER


def test_deberia_crear_como_coach_si_se_indica_coach(session, usuario_con_equipo):
    behavior = create_behavior(
        session, usuario_con_equipo.user_id, cuerpo_con_tipo(BehaviorType.COACH)
    )

    assert behavior.behavior_type == BehaviorType.COACH


# editar

def test_deberia_conservar_el_tipo_al_editar_aunque_el_pedido_traiga_otro(session, usuario_con_equipo):
    behavior = crear_en_base(session, usuario_con_equipo.user_id, BehaviorType.PLAYER)

    update_behavior(
        payload=cuerpo_con_tipo(BehaviorType.COACH),
        user_id=usuario_con_equipo.user_id,
        behavior_id=behavior.behavior_id,
        session=session,
    )

    assert behavior.behavior_type == BehaviorType.PLAYER


# las respuestas incluyen el tipo 

def test_deberia_incluir_el_tipo_al_listar(session, usuario_con_equipo):
    crear_en_base(session, usuario_con_equipo.user_id, BehaviorType.COACH) 

    comportamientos = list_behaviors(session, user_id=usuario_con_equipo.user_id, is_default=None)

    assert comportamientos[0].behavior_type == BehaviorType.COACH # tengo un solo comportamiento en la lista, chequeo su tipo


def test_deberia_incluir_el_tipo_al_ver_detalle(session, usuario_con_equipo):
    behavior = crear_en_base(session, usuario_con_equipo.user_id, BehaviorType.COACH)

    detalle = get_behavior(
        session, user_id=usuario_con_equipo.user_id, behavior_id=behavior.behavior_id
    )

    assert detalle.behavior_type == BehaviorType.COACH