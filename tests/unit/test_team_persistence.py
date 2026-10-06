"""
tests/test_team_persistence.py
"""

from __future__ import annotations

import pytest

from src.models.team import Team
from src.models.user import User
from src.services.team_service import (
    InvalidLogoFormatError,
    VoidTeamLogoError,
    VoidTeamNameError,
)
from src.services.user_service import create_user_with_team


def _valid_team_data() -> dict:
    return {"team_name": "AlfajoresFC", "team_logo": "https://example.com/logo.png"}


def test_registro_valido_crea_usuario_y_equipo_asociados(session):
    # si el registro sale bien, el user tiene que quedar apuntando
    # a un team con los datos que le pasamos, no a uno vacío o default
    user = create_user_with_team(
        session,
        username="messi10",
        email="messi@example.com",
        password="Password123!",
        team_data=_valid_team_data(),
    )

    assert user.user_id is not None
    assert user.team_id is not None
    assert user.team.team_name == "AlfajoresFC"
    assert user.team.team_logo == "https://example.com/logo.png"


def test_usuario_y_equipo_quedan_realmente_persistidos_en_la_db(session):
    user = create_user_with_team(
        session,
        username="kempes9",
        email="kempes@example.com",
        password="Password123!",
        team_data=_valid_team_data(),
    )

    session.expire_all()  # así lo que sigue lee de la db, no del objeto que ya tenemos en memoria

    persisted_user = session.get(User, user.user_id)
    assert persisted_user is not None

    persisted_team = session.get(Team, persisted_user.team_id)
    assert persisted_team is not None
    assert persisted_team.team_name == "AlfajoresFC"


def test_team_name_vacio_no_persiste_nada(session):
    # si falla la validación del nombre, no tiene que quedar el user
    # dando vueltas en la db 
    with pytest.raises(VoidTeamNameError):
        create_user_with_team(
            session,
            username="fantasma1",
            email="fantasma1@example.com",
            password="Password123!",
            team_data={"team_name": "", "team_logo": "https://example.com/logo.png"},
        )

    assert session.query(User).filter_by(email="fantasma1@example.com").first() is None


def test_team_logo_vacio_no_persiste_nada(session):
    with pytest.raises(VoidTeamLogoError):
        create_user_with_team(
            session,
            username="fantasma2",
            email="fantasma2@example.com",
            password="Password123!",
            team_data={"team_name": "AlfajoresFC", "team_logo": ""},
        )

    assert session.query(User).filter_by(email="fantasma2@example.com").first() is None


def test_team_logo_con_formato_invalido_no_persiste_nada(session):
    with pytest.raises(InvalidLogoFormatError):
        create_user_with_team(
            session,
            username="fantasma3",
            email="fantasma3@example.com",
            password="Password123!",
            team_data={"team_name": "AlfajoresFC", "team_logo": "no_es_una_url_valida"},
        )

    assert session.query(User).filter_by(email="fantasma3@example.com").first() is None


def test_borrar_usuario_borra_su_equipo(session):
    user = create_user_with_team(
        session,
        username="se_borra",
        email="se_borra@example.com",
        password="Password123!",
        team_data=_valid_team_data(),
    )
    team_id = user.team_id

    session.delete(user)
    session.flush()

    assert session.get(Team, team_id) is None
