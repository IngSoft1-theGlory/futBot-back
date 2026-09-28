from __future__ import annotations

import pytest
from sqlalchemy import select

import bcrypt
from src.core.security import hash_password
from src.models.team import Team
from src.models.user import User
from src.repositories.user_repository import get_user_by_email, get_user_by_id
from src.services.user_service import (
    DuplicateEmailError,
    EmptyUsernameError,
    create_user_with_team,
)


def test_crear_usuario_persiste_usuario_y_equipo(session):
    user = create_user_with_team(
        session, username="Maradona10", email="diego@famaf.unc.edu.ar",
        password="Password123!",
        team_data={"team_name": "alfajoresFC", "team_logo": "https://example.com/logo.png"},
    )
    assert user.user_id is not None
    assert user.team_id is not None
    persisted_user = session.get(User, user.user_id)
    persisted_team = session.get(Team, user.team_id)
    assert persisted_user is not None and persisted_team is not None
    assert persisted_user.email == "diego@famaf.unc.edu.ar"
    assert persisted_team.team_name == "alfajoresFC"


def test_email_duplicado_falla_y_revierte_todo(session):
    create_user_with_team(
        session, username="Primero", email="repetido@famaf.unc.edu.ar",
        password="Password123!",
        team_data={"team_name": "EquipoUno", "team_logo": "https://example.com/logo.png"},
    )
    with pytest.raises(DuplicateEmailError):
        create_user_with_team(
            session, username="Segundo", email="repetido@famaf.unc.edu.ar",
            password="OtraPassword456!",
            team_data={"team_name": "EquipoDos", "team_logo": "https://example.com/logo.png"},
        )
    assert len(session.scalars(select(User)).all()) == 1
    assert len(session.scalars(select(Team)).all()) == 1  # no quedó EquipoDos


def test_username_vacio_falla_y_no_persiste_nada(session):
    with pytest.raises(EmptyUsernameError):
        create_user_with_team(
            session, username="   ", email="nadie@famaf.unc.edu.ar",
            password="Password123!",
            team_data={"team_name": "EquipoFantasma", "team_logo": "https://example.com/logo.png"},
        )
    assert session.scalars(select(User)).all() == []
    assert session.scalars(select(Team)).all() == []


def test_password_se_guarda_hasheada_no_en_texto_plano(session):
    plain_password = "Password123!"
    user = create_user_with_team(
        session,
        username="Pepe",
        email="pepe@famaf.unc.edu.ar",
        password=plain_password,
        team_data={"team_name": "PepeFC", "team_logo": "https://example.com/logo.png"},
    )

    assert user.password_hash != plain_password
    assert bcrypt.checkpw(plain_password.encode("utf-8"), user.password_hash.encode("utf-8"))


def test_password_nunca_se_expone_al_leer_usuario(session):
    user = create_user_with_team(
        session, username="Sin Password Expuesta", email="segura@famaf.unc.edu.ar",
        password="Password123!",
        team_data={"team_name": "SeguraFC", "team_logo": "https://example.com/logo.png"},
    )
    fetched = get_user_by_id(session, user.user_id)
    public_data = fetched.to_public_dict()
    assert "password" not in public_data and "password_hash" not in public_data
    assert "password" not in repr(fetched)
    assert fetched.password_hash not in repr(fetched)


def test_relacion_usuario_equipo_es_uno_a_uno(session):
    user = create_user_with_team(
        session, username="Relacion", email="relacion@famaf.unc.edu.ar",
        password="Password123!",
        team_data={"team_name": "RelacionFC", "team_logo": "https://example.com/logo.png"},
    )
    assert user.team is not None
    assert user.team.team_id == user.team_id
    assert user.team.user is user


def test_buscar_usuario_por_email(session):
    create_user_with_team(
        session, username="Buscable", email="buscable@famaf.unc.edu.ar",
        password="Password123!",
        team_data={"team_name": "BuscableFC", "team_logo": "https://example.com/logo.png"},
    )
    assert get_user_by_email(session, "buscable@famaf.unc.edu.ar") is not None
    assert get_user_by_email(session, "no-existe@famaf.unc.edu.ar") is None
    


def test_atomicidad_falla_creacion_equipo_no_deja_usuario(session):
    """Si falla la creación de Team, no debe quedar un User huérfano."""
    with pytest.raises(TypeError):
        create_user_with_team(
            session, username="SinEquipo", email="sinequipo@famaf.unc.edu.ar",
            password="Password123!", team_data={"campo_inexistente": "valor"},
        )
    assert get_user_by_email(session, "sinequipo@famaf.unc.edu.ar") is None
    assert session.scalars(select(Team)).all() == []


def test_atomicidad_falla_usuario_revierte_equipo_ya_flusheado(session, monkeypatch):
    """El Team llega a flushearse (flush #1) pero el User falla (flush #2):
    la transacción entera debe revertirse, sin dejar el Team persistido."""
    original_flush = session.flush
    call_count = {"n": 0}

    def flaky_flush(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("Fallo simulado creando al User")
        return original_flush(*args, **kwargs)

    monkeypatch.setattr(session, "flush", flaky_flush)

    with pytest.raises(RuntimeError):
        create_user_with_team(
            session, username="RollbackProfundo", email="rollback-profundo@famaf.unc.edu.ar",
            password="Password123!",
            team_data={"team_name": "EquipoQueNoDeberiaQuedar", "team_logo": "https://example.com/logo.png"},
        )
    assert session.scalars(select(Team)).all() == []
    assert get_user_by_email(session, "rollback-profundo@famaf.unc.edu.ar") is None


def test_eliminar_usuario_elimina_en_cascada_al_equipo(session):
    user = create_user_with_team(
        session, username="ParaEliminar", email="eliminar@famaf.unc.edu.ar",
        password="Password123!",
        team_data={"team_name": "EquipoAEliminar", "team_logo": "https://example.com/logo.png"},
    )
    user_id, team_id = user.user_id, user.team_id
    session.delete(user)
    session.commit()
    assert session.get(User, user_id) is None
    assert session.get(Team, team_id) is None


def test_hash_password_rechaza_password_vacia():
    with pytest.raises(ValueError):
        hash_password("")