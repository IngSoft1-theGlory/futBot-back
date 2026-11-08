"""
Tests de las estadisticas globales de los clubes (ranking global).

Al terminar un partido de liga publica se suma su resultado a los dos equipos,
en la misma transaccion que el resultado, y despues se publica RANKING_UPDATED.
"""

from unittest.mock import MagicMock, call

import pytest
from sqlalchemy.orm import sessionmaker

from src.models import Match, MatchStatus, Team
from src.realtime.event_bus import event_bus
from src.services import league_run_service, match_start_service
from src.services.match_start_service import make_on_finished, save_match_result
from tests.unit.test_league_match_finished import _armar_amistoso_en_juego, _estado_final
from tests.unit.test_start_league_round import _armar_liga_iniciada, _partidos_de_la_fecha


def _partido_en_juego(session, liga):
    """El primer partido de la fecha 1 de la liga, ya en juego"""
    partido = _partidos_de_la_fecha(session, liga, 1)[0]
    partido.status = MatchStatus.IN_PROGRESS
    session.commit()
    return partido

def _estadisticas(session, team_id):
    """Las estadisticas globales del equipo, leidas de la base"""
    session.expire_all()  # para leer lo que quedo guardado, no lo que recuerda la sesion
    equipo = session.get(Team, team_id)
    return {
        "matches_played": equipo.matches_played,
        "wins": equipo.wins,
        "draws": equipo.draws,
        "losses": equipo.losses,
        "goals_for": equipo.goals_for,
        "goals_against": equipo.goals_against,
        "points": equipo.points,
    }

SIN_PARTIDOS = {
    "matches_played": 0, "wins": 0, "draws": 0, "losses": 0,
    "goals_for": 0, "goals_against": 0, "points": 0,
}

@pytest.fixture()
def publicar(monkeypatch):
    """Reemplaza event_bus.publish por un mock, para ver que eventos se publicaron"""
    mock = MagicMock()
    monkeypatch.setattr(event_bus, "publish", mock)
    return mock


def test_deberia_sumar_el_resultado_a_los_dos_equipos_al_terminar_un_partido_de_liga_publica(session, publicar):
    liga = _armar_liga_iniciada(session)  # sin contraseña: es publica
    partido = _partido_en_juego(session, liga)
    local, visitante = partido.team_host_id, partido.team_away_id

    save_match_result(session, partido.match_id, home_goals=2, away_goals=1)

    assert _estadisticas(session, local) == {
        "matches_played": 1, "wins": 1, "draws": 0, "losses": 0,
        "goals_for": 2, "goals_against": 1, "points": 3,
    }
    assert _estadisticas(session, visitante) == {
        "matches_played": 1, "wins": 0, "draws": 0, "losses": 1,
        "goals_for": 1, "goals_against": 2, "points": 0,
    }
    publicar.assert_any_call("RANKING_UPDATED", {})

def test_deberia_sumar_un_empate_y_un_punto_a_cada_equipo(session, publicar):
    liga = _armar_liga_iniciada(session)
    partido = _partido_en_juego(session, liga)

    save_match_result(session, partido.match_id, home_goals=1, away_goals=1)

    empate = {
        "matches_played": 1, "wins": 0, "draws": 1, "losses": 0,
        "goals_for": 1, "goals_against": 1, "points": 1,
    }
    assert _estadisticas(session, partido.team_host_id) == empate
    assert _estadisticas(session, partido.team_away_id) == empate

def test_deberia_contar_como_victoria_de_2_puntos_un_partido_ganado_por_penales(session, publicar):
    # misma regla que la tabla de posiciones de la liga (standings_service)
    liga = _armar_liga_iniciada(session)
    partido = _partido_en_juego(session, liga)

    save_match_result(session, partido.match_id, 1, 1, home_penalty_goals=4, away_penalty_goals=3)

    assert _estadisticas(session, partido.team_host_id)["wins"] == 1
    assert _estadisticas(session, partido.team_host_id)["points"] == 2
    assert _estadisticas(session, partido.team_away_id)["losses"] == 1
    assert _estadisticas(session, partido.team_away_id)["points"] == 0

def test_no_deberia_modificar_las_estadisticas_un_partido_de_liga_privada(session, publicar):
    liga = _armar_liga_iniciada(session)
    liga.password_hash = "hash-falso"  # con contraseña: es privada
    session.commit()
    partido = _partido_en_juego(session, liga)

    save_match_result(session, partido.match_id, home_goals=2, away_goals=1)

    assert _estadisticas(session, partido.team_host_id) == SIN_PARTIDOS
    assert _estadisticas(session, partido.team_away_id) == SIN_PARTIDOS
    assert call("RANKING_UPDATED", {}) not in publicar.call_args_list

def test_no_deberia_modificar_las_estadisticas_un_amistoso(session, publicar):
    amistoso = _armar_amistoso_en_juego(session)

    save_match_result(session, amistoso.match_id, home_goals=3, away_goals=0)

    assert _estadisticas(session, amistoso.team_host_id) == SIN_PARTIDOS
    assert _estadisticas(session, amistoso.team_away_id) == SIN_PARTIDOS
    assert call("RANKING_UPDATED", {}) not in publicar.call_args_list

def test_no_deberia_sumar_dos_veces_un_partido_si_su_cierre_se_ejecuta_dos_veces(session, publicar, monkeypatch):
    liga = _armar_liga_iniciada(session)
    partido = _partido_en_juego(session, liga)
    # aislo el test: no quiero que se avance la liga, solo ver las estadisticas
    monkeypatch.setattr(league_run_service, "advance_league", MagicMock())
    on_finished = make_on_finished(sessionmaker(bind=session.get_bind(), expire_on_commit=False))

    on_finished(_estado_final(partido.match_id, 2, 1))
    on_finished(_estado_final(partido.match_id, 2, 1))  # el cierre se repite por algun error

    assert _estadisticas(session, partido.team_host_id)["matches_played"] == 1
    assert _estadisticas(session, partido.team_host_id)["points"] == 3
    assert _estadisticas(session, partido.team_away_id)["matches_played"] == 1
    assert publicar.call_args_list.count(call("RANKING_UPDATED", {})) == 1  # se avisa una sola vez

def test_deberia_publicar_ranking_updated_despues_de_guardar_las_estadisticas(session, monkeypatch):
    liga = _armar_liga_iniciada(session)
    partido = _partido_en_juego(session, liga)
    local = partido.team_host_id
    fabrica = sessionmaker(bind=session.get_bind())
    puntos_vistos = []

    def publish_espia(nombre, data):
        if nombre == "RANKING_UPDATED":
            # una sesion distinta solo ve lo que ya esta confirmado (commit)
            with fabrica() as otra_sesion:
                puntos_vistos.append(otra_sesion.get(Team, local).points)

    monkeypatch.setattr(event_bus, "publish", publish_espia)

    save_match_result(session, partido.match_id, home_goals=2, away_goals=0)

    assert puntos_vistos == [3]

def test_no_deberia_guardar_nada_si_falla_la_suma_de_las_estadisticas(session, publicar, monkeypatch):
    liga = _armar_liga_iniciada(session)
    partido = _partido_en_juego(session, liga)
    id_partido, local = partido.match_id, partido.team_host_id

    def sumar_a_medias(session, match):
        match.host_team.points += 3  # alcanza a sumarle al local...
        raise RuntimeError("...y falla antes de sumarle al visitante")

    monkeypatch.setattr(match_start_service, "add_match_to_global_stats", sumar_a_medias)

    with pytest.raises(RuntimeError):
        save_match_result(session, id_partido, home_goals=2, away_goals=0)

    session.expire_all()
    assert session.get(Match, id_partido).status is MatchStatus.IN_PROGRESS  # el resultado tampoco se guardo
    assert _estadisticas(session, local) == SIN_PARTIDOS                     # ni la mitad de las estadisticas
    publicar.assert_not_called()                                              # y no se aviso nada
