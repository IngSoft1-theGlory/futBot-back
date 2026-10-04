import pytest

from src.core.exceptions import MatchNotFoundError, UnauthorizedError
from src.models import Match, MatchStatus, Team, User
from src.services.match_access_service import get_match_in_progress, user_participates


def _crear_usuario(session, n: int) -> User:
    user = User(
        username=f"user{n}", email=f"user{n}@example.com",
        password_hash="hash-falso", team=Team(team_name=f"Equipo {n}"),
    )
    session.add(user)
    session.commit()
    return user


def _crear_partido(session, host: User, away: User | None, status=MatchStatus.IN_PROGRESS) -> Match:
    match = Match(
        match_duration=2, status=status,
        team_host_id=host.team_id,
        team_away_id=away.team_id if away else None,
    )
    session.add(match)
    session.commit()
    return match


def test_get_match_in_progress_deberia_devolver_el_partido_en_curso(session):
    host, away = _crear_usuario(session, 1), _crear_usuario(session, 2)
    match = _crear_partido(session, host, away)
    assert get_match_in_progress(session, match.match_id).match_id == match.match_id


def test_get_match_in_progress_deberia_fallar_si_el_partido_no_existe(session):
    with pytest.raises(MatchNotFoundError):
        get_match_in_progress(session, 999)


def test_get_match_in_progress_deberia_fallar_si_el_partido_esta_pending(session):
    match = _crear_partido(session, _crear_usuario(session, 1), None, MatchStatus.PENDING)
    # revisar que el partido no está en ejecución
    with pytest.raises(MatchNotFoundError):
        # intentar obtener el partido en progreso
        get_match_in_progress(session, match.match_id)


def test_get_match_in_progress_deberia_fallar_si_el_partido_esta_finished(session):
    host, away = _crear_usuario(session, 1), _crear_usuario(session, 2)
    match = _crear_partido(session, host, away, MatchStatus.FINISHED)
    with pytest.raises(MatchNotFoundError):
        get_match_in_progress(session, match.match_id)


def test_user_participates_deberia_ser_true_para_el_anfitrion(session):
    host, away = _crear_usuario(session, 1), _crear_usuario(session, 2)
    match = _crear_partido(session, host, away)
    assert user_participates(session, host.user_id, match) is True


def test_user_participates_deberia_ser_true_para_el_visitante(session):
    host, away = _crear_usuario(session, 1), _crear_usuario(session, 2)
    match = _crear_partido(session, host, away)
    assert user_participates(session, away.user_id, match) is True


def test_user_participates_deberia_ser_false_para_quien_no_juega(session):
    host, away, otro = (_crear_usuario(session, n) for n in (1, 2, 3))
    match = _crear_partido(session, host, away)
    # revisar que el usuario 3 no participa en el partido
    assert user_participates(session, otro.user_id, match) is False


def test_user_participates_deberia_fallar_si_el_usuario_no_existe(session):
    host, away = _crear_usuario(session, 1), _crear_usuario(session, 2)
    match = _crear_partido(session, host, away)
    # revisar que el usuario 999 no existe
    with pytest.raises(UnauthorizedError):
        user_participates(session, 999, match)