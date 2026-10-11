import jwt
import pytest

from src.config.settings import settings
from src.core.exceptions import AppError
from src.core.security import ALGORITHM, JOIN_LEAGUE, create_join_token, hash_password
from src.models.league import League, LeagueStatus
from src.services.league_service import check_league_password
from src.services.user_service import create_user_with_team


@pytest.fixture
def usuario(session):
    return create_user_with_team(
        session,
        username="Maradona10",
        email="diego@famaf.unc.edu.ar",
        password="Password123!",
        team_data={
            "team_name": "alfajoresFC",
            "team_logo": "https://example.com/logos/alfajores.png",
        },
    )


def crear_liga(session, usuario, contrasena=None):
    liga = League(
        league_name="Liga test",
        max_teams=4,
        password_hash=hash_password(contrasena) if contrasena else None,
        host_team_id=usuario.team_id,
        match_duration=2,
        status=LeagueStatus.PENDING,
    )
    session.add(liga)
    session.commit()
    return liga


def test_deberia_dar_un_token_de_union_valido_si_la_contraseña_es_correcta(session, usuario):
    liga = crear_liga(session, usuario, "clave123")

    check_league_password(session, liga.league_id, "clave123")  # no debe lanzar error
    token = create_join_token(usuario.user_id, liga.league_id)

    datos = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    assert datos["type"] == JOIN_LEAGUE
    assert datos["league_id"] == liga.league_id
    assert datos["sub"] == str(usuario.user_id)


def test_deberia_dar_401_password_incorrect_si_la_contraseña_es_incorrecta(session, usuario):
    liga = crear_liga(session, usuario, "clave123")

    with pytest.raises(AppError) as error:
        check_league_password(session, liga.league_id, "otra_clave")

    assert error.value.status_code == 401
    assert error.value.error_code == "PASSWORD_INCORRECT"


def test_deberia_dar_400_league_not_private_si_la_liga_es_publica(session, usuario):
    liga = crear_liga(session, usuario)  # sin contraseña

    with pytest.raises(AppError) as error:
        check_league_password(session, liga.league_id, "cualquiera")

    assert error.value.status_code == 400
    assert error.value.error_code == "LEAGUE_NOT_PRIVATE"


def test_deberia_dar_404_si_la_liga_no_existe(session):
    with pytest.raises(AppError) as error:
        check_league_password(session, 9999, "cualquiera")

    assert error.value.status_code == 404