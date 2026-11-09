"""
Tests del tipo de comportamiento (PLAYER / COACH)
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from src.core.exceptions import InvalidData
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


def crear_en_base(session, user_id, behavior_type=BehaviorType.PLAYER, code=CODIGO):
    behavior = Behavior(
        name="Nombre", description="Descripcion", code=code,
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


# primitivas según el tipo 
# Código de prueba: usa una primitiva de DT (CoachAPI) / una de jugador (PlayerAPI).
CODIGO_DT = "def on_tick(api):\n    api.change_behavior(1, 2)\n"
CODIGO_JUGADOR = "def on_tick(api):\n    api.idle()\n"


def cuerpo(behavior_type, code):
    return CreateUpdateBehaviorRequest(name="Nuevo", description="Descripcion", code=code, behavior_type=behavior_type)


def editar(session, user_id, behavior, payload):
    return update_behavior(payload=payload, user_id=user_id, behavior_id=behavior.behavior_id, session=session)


def test_deberia_guardar_un_coach_que_usa_solo_primitivas_de_dt_al_crear(session, usuario_con_equipo):
    behavior = create_behavior(session, usuario_con_equipo.user_id, cuerpo(BehaviorType.COACH, CODIGO_DT))

    assert behavior.code == CODIGO_DT


def test_deberia_guardar_un_coach_que_usa_solo_primitivas_de_dt_al_editar(session, usuario_con_equipo):
    behavior = crear_en_base(session, usuario_con_equipo.user_id, BehaviorType.COACH)

    editar(session, usuario_con_equipo.user_id, behavior, cuerpo(BehaviorType.COACH, CODIGO_DT))

    assert behavior.code == CODIGO_DT


def test_deberia_rechazar_un_coach_con_primitiva_de_jugador_al_crear(session, usuario_con_equipo):
    with pytest.raises(InvalidData):
        create_behavior(session, usuario_con_equipo.user_id, cuerpo(BehaviorType.COACH, CODIGO_JUGADOR))

    # no se guardó nada
    assert session.scalars(select(Behavior)).all() == []


def test_deberia_rechazar_un_coach_con_primitiva_de_jugador_al_editar(session, usuario_con_equipo):
    behavior = crear_en_base(session, usuario_con_equipo.user_id, BehaviorType.COACH)

    with pytest.raises(InvalidData):
        editar(session, usuario_con_equipo.user_id, behavior, cuerpo(BehaviorType.COACH, CODIGO_JUGADOR))

    # no se modificó: vuelvo a leerlo de la base
    session.refresh(behavior)
    assert behavior.code == CODIGO


def test_deberia_rechazar_un_player_con_primitiva_de_dt_al_crear(session, usuario_con_equipo):
    with pytest.raises(InvalidData):
        create_behavior(session, usuario_con_equipo.user_id, cuerpo(BehaviorType.PLAYER, CODIGO_DT))

    assert session.scalars(select(Behavior)).all() == []


def test_deberia_rechazar_un_player_con_primitiva_de_dt_al_editar(session, usuario_con_equipo):
    behavior = crear_en_base(session, usuario_con_equipo.user_id, BehaviorType.PLAYER)

    with pytest.raises(InvalidData):
        editar(session, usuario_con_equipo.user_id, behavior, cuerpo(BehaviorType.PLAYER, CODIGO_DT))

    session.refresh(behavior)
    assert behavior.code == CODIGO
