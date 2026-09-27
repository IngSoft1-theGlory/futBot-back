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


def test_create_user_persists_user_and_team(session):
    user = create_user_with_team(
        session, username="Maradona10", email="diego@famaf.unc.edu.ar",
        password="Password123!", team_data={"name": "alfajoresFC", "logo": "https://example.com/logos/alfajores.png"},
    )
    assert user.user_id is not None
    assert user.team_id is not None
    persisted_user = session.get(User, user.user_id)
    persisted_team = session.get(Team, user.team_id)
    assert persisted_user is not None and persisted_team is not None
    assert persisted_user.email == "diego@famaf.unc.edu.ar"
    assert persisted_team.name == "alfajoresFC"


def test_duplicate_email_fails_and_rolls_back_completely(session):
    create_user_with_team(
        session, username="Primero", email="repetido@famaf.unc.edu.ar",
        password="Password123!", team_data={"name": "EquipoUno", "logo": "https://example.com/logo.png"},
    )
    with pytest.raises(DuplicateEmailError):
        create_user_with_team(
            session, username="Segundo", email="repetido@famaf.unc.edu.ar",
            password="OtraPassword456!", team_data={"name": "EquipoDos", "logo": "https://example.com/logo.png"},
        )
    assert len(session.scalars(select(User)).all()) == 1
    assert len(session.scalars(select(Team)).all()) == 1  # no quedó EquipoDos


def test_empty_username_fails_and_persists_nothing(session):
    with pytest.raises(EmptyUsernameError):
        create_user_with_team(
            session, username="   ", email="nadie@famaf.unc.edu.ar",
            password="Password123!", team_data={"name": "EquipoFantasma", "logo": "https://example.com/logo.png"},
        )
    assert session.scalars(select(User)).all() == []
    assert session.scalars(select(Team)).all() == []


def test_password_is_stored_hashed_not_plaintext(session):
    plain_password = "Password123!"
    user = create_user_with_team(
        session,
        username="Pepe",
        email="pepe@famaf.unc.edu.ar",
        password=plain_password,
        team_data={"name": "PepeFC", "logo": "https://example.com/logo.png"},
    )

    assert user.password_hash != plain_password
    assert bcrypt.checkpw(plain_password.encode("utf-8"), user.password_hash.encode("utf-8"))


def test_password_never_exposed_when_reading_user(session):
    user = create_user_with_team(
        session, username="Sin Password Expuesta", email="segura@famaf.unc.edu.ar",
        password="Password123!", team_data={"name": "SeguraFC", "logo": "https://example.com/logo.png"},
    )
    fetched = get_user_by_id(session, user.user_id)
    public_data = fetched.to_public_dict()
    assert "password" not in public_data and "password_hash" not in public_data
    assert "password" not in repr(fetched)
    assert fetched.password_hash not in repr(fetched)


def test_user_team_relationship_is_one_to_one(session):
    user = create_user_with_team(
        session, username="Relacion", email="relacion@famaf.unc.edu.ar",
        password="Password123!", team_data={"name": "RelacionFC", "logo": "https://example.com/logo.png"},
    )
    assert user.team is not None
    assert user.team.team_id == user.team_id
    assert user.team.user is user


def test_get_user_by_email_helper(session):
    create_user_with_team(
        session, username="Buscable", email="buscable@famaf.unc.edu.ar",
        password="Password123!", team_data={"name": "BuscableFC", "logo": "https://example.com/logo.png"},
    )
    assert get_user_by_email(session, "buscable@famaf.unc.edu.ar") is not None
    assert get_user_by_email(session, "no-existe@famaf.unc.edu.ar") is None


def test_atomicity_team_construction_failure_leaves_no_user(session):
    """Si falla la creación de Team, no debe quedar un User huérfano.

    name/logo válidos para pasar las validaciones de negocio (VOID_TEAM_*)
    y llegar hasta Team(**team_data); el TypeError lo produce el kwarg
    extra "campo_inexistente", que no es un atributo mapeado de Team.
    """
    with pytest.raises(TypeError):
        create_user_with_team(
            session, username="SinEquipo", email="sinequipo@famaf.unc.edu.ar",
            password="Password123!",
            team_data={
                "name": "EquipoValido",
                "logo": "https://example.com/logo.png",
                "campo_inexistente": "valor",
            },
        )
    assert get_user_by_email(session, "sinequipo@famaf.unc.edu.ar") is None
    assert session.scalars(select(Team)).all() == []


def test_atomicity_user_failure_rolls_back_already_flushed_team(session, monkeypatch):
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
            password="Password123!", team_data={"name": "EquipoQueNoDeberiaQuedar", "logo": "https://example.com/logo.png"},
        )
    assert session.scalars(select(Team)).all() == []
    assert get_user_by_email(session, "rollback-profundo@famaf.unc.edu.ar") is None


def test_delete_user_cascades_to_team(session):
    user = create_user_with_team(
        session, username="ParaEliminar", email="eliminar@famaf.unc.edu.ar",
        password="Password123!", team_data={"name": "EquipoAEliminar", "logo": "https://example.com/logo.png"},
    )
    user_id, team_id = user.user_id, user.team_id
    session.delete(user)
    session.commit()
    assert session.get(User, user_id) is None
    assert session.get(Team, team_id) is None


def test_hash_password_rejects_empty_password():
    with pytest.raises(ValueError):
        hash_password("")