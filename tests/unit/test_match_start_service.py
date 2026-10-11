"""
Tests de match_start_service: base -> estado inicial, lanzamiento del motor
y persistencia del resultado.

Se usa la base de los tests (SQLite en memoria). Las piezas que todavía
implementan otros tickets (ejecución de comportamientos, aplicar
intenciones) se reemplazan con fakes: acá se prueba el ARRANQUE, no la
simulación.
"""

import asyncio

import pytest
from sqlalchemy.orm import sessionmaker

from src.engine.behavior_executor import make_execute_behavior
from src.engine.game_types import AttributeType
from src.engine.intentions import ActionType, Intention
from src.engine.pitch import TeamSide, starter_position
from src.engine.simulation import apply_intentions
from src.engine._02_to_match.state import MatchInitializationError, MatchRegistry
from src.models import Behavior, LineupEntry, Match, MatchStatus, Player, Team
from src.services.match_start_service import (
    launch_match,
    make_on_finished,
    prepare_match,
    save_match_result,
    start_match,
)

from src.realtime.event_bus import event_bus

ROLES_2_1 = ["DEF_LEFT", "DEF_RIGHT", "FORWARD"]
ROLES_1_2 = ["DEFENDER", "FORWARD_LEFT", "FORWARD_RIGHT"]


# --- Datos de base ----------------------------------------------------------


@pytest.fixture()
def comportamiento(session):
    behavior = Behavior(name="Quieto", description="No hace nada", code="def on_tick(api): pass", is_default=True)
    session.add(behavior)
    session.commit()
    return behavior


def _armar_partido(session, comportamiento, duracion=2, roles_local=ROLES_2_1, roles_visitante=ROLES_2_1):
    """Partido IN_PROGRESS con dos equipos y sus alineaciones completas."""
    local = Team(team_name="Local FC")
    visitante = Team(team_name="Visitante FC")
    session.add_all([local, visitante])
    session.flush()

    match = Match(
        team_host_id=local.team_id,
        team_away_id=visitante.team_id,
        match_duration=duracion,
        status=MatchStatus.IN_PROGRESS,
    )
    session.add(match)
    session.flush()

    _agregar_alineacion(session, match, local, roles_local, comportamiento)
    _agregar_alineacion(session, match, visitante, roles_visitante, comportamiento)
    session.commit()
    return match


def _agregar_alineacion(session, match, equipo, roles, comportamiento):
    jugadores = [
        Player(
            team_id=equipo.team_id, name=f"{equipo.team_name}-{n}", number=n,
            power=1, agility=1, control=1, speed=1, strength=1,
        )
        for n in range(1, 7)
    ]
    session.add_all(jugadores)
    session.flush()
    for indice, jugador in enumerate(jugadores):
        es_titular = indice < 3
        session.add(
            LineupEntry(
                match_id=match.match_id,
                team_id=equipo.team_id,
                player_id=jugador.player_id,
                behavior_id=comportamiento.behavior_id,
                role=roles[indice] if es_titular else None,
                is_starter=es_titular,
            )
        )
    session.flush()


@pytest.fixture()
def partido(session, comportamiento):
    return _armar_partido(session, comportamiento)


# --- Fakes de las piezas inyectadas -----------------------------------------
# Respetan la firma que launch_match/run_match esperan (ver los tipos en
# match_runner.py) pero no usan todos sus parámetros: el editor los marca
# como "is not accessed" y es esperado. Solo tienen que poder recibir los
# argumentos con los que el ciclo los llama.

def _idle_behavior(state, player_id) -> Intention:
    return Intention(ActionType.IDLE)


def _noop_apply(state, intentions) -> None:
    pass


async def _noop_notify(state) -> None:
    pass


def _fabrica_de_sesiones(session):
    """Sesiones nuevas contra la MISMA base del test (como en producción,
    donde el motor abre su propia sesión)."""
    return sessionmaker(bind=session.get_bind(), autoflush=False, expire_on_commit=False)


# --- prepare_match ----------------------------------------------------------


def test_deberia_prepare_match_armar_el_estado_con_los_12_jugadores(session, partido):
    state = prepare_match(session, partido.match_id)

    assert state.match_id == partido.match_id
    assert len(state.players) == 12
    assert state.current_tick == 0
    assert (state.score.home, state.score.away) == (0, 0)
    assert len(state.on_pitch_player_ids()) == 6


def test_deberia_prepare_match_poner_al_anfitrion_de_home_y_al_visitante_de_away(session, partido):
    state = prepare_match(session, partido.match_id)

    forward_local = next(p for p in state.players_of(partido.team_host_id) if p.role == "FORWARD")
    forward_visitante = next(p for p in state.players_of(partido.team_away_id) if p.role == "FORWARD")

    assert forward_local.position == starter_position("2-1", "FORWARD", TeamSide.HOME)
    assert forward_visitante.position == starter_position("2-1", "FORWARD", TeamSide.AWAY)


def test_deberia_prepare_match_deducir_la_formacion_de_cada_equipo(session, comportamiento):
    partido = _armar_partido(session, comportamiento, roles_local=ROLES_2_1, roles_visitante=ROLES_1_2)

    state = prepare_match(session, partido.match_id)

    defensor = next(p for p in state.players_of(partido.team_away_id) if p.role == "DEFENDER")
    assert defensor.position == starter_position("1-2", "DEFENDER", TeamSide.AWAY)


def test_deberia_prepare_match_cargar_los_atributos_de_cada_jugador_desde_la_base(session, partido):
    jugador = session.query(Player).filter_by(team_id=partido.team_away_id, number=3).one()
    jugador.power, jugador.agility, jugador.control, jugador.speed, jugador.strength = 11, 22, 33, 44, 55
    session.commit()

    state = prepare_match(session, partido.match_id)

    assert state.players[jugador.player_id].attributes == {
        AttributeType.POWER: 11,
        AttributeType.AGILITY: 22,
        AttributeType.CONTROL: 33,
        AttributeType.SPEED: 44,
        AttributeType.STRENGTH: 55,
    }
    # y los 12 jugadores tienen sus 5 atributos
    assert all(len(p.attributes) == 5 for p in state.players.values())


@pytest.mark.parametrize("minutos, ticks", [(2, 240), (5, 600)])
def test_deberia_prepare_match_calcular_total_ticks_segun_la_duracion(session, comportamiento, minutos, ticks):
    partido = _armar_partido(session, comportamiento, duracion=minutos)

    assert prepare_match(session, partido.match_id).total_ticks == ticks


def test_deberia_prepare_match_aceptar_un_partido_pending_con_visitante(session, partido):
    """Es el caso del join: se prepara ANTES del commit que lo pasa a IN_PROGRESS."""
    partido.status = MatchStatus.PENDING
    session.flush()

    assert len(prepare_match(session, partido.match_id).players) == 12


def test_deberia_prepare_match_fallar_si_el_partido_no_existe(session):
    with pytest.raises(MatchInitializationError):
        prepare_match(session, 999)


def test_deberia_prepare_match_fallar_si_el_partido_ya_termino(session, partido):
    partido.status = MatchStatus.FINISHED
    session.flush()

    with pytest.raises(MatchInitializationError):
        prepare_match(session, partido.match_id)


def test_deberia_prepare_match_fallar_si_no_hay_visitante(session, comportamiento):
    local = Team(team_name="Solo FC")
    session.add(local)
    session.flush()
    match = Match(team_host_id=local.team_id, match_duration=2, status=MatchStatus.PENDING)
    session.add(match)
    session.commit()

    with pytest.raises(MatchInitializationError):
        prepare_match(session, match.match_id)


def test_deberia_prepare_match_fallar_con_una_duracion_invalida(session, comportamiento):
    partido = _armar_partido(session, comportamiento, duracion=10)

    with pytest.raises(MatchInitializationError):
        prepare_match(session, partido.match_id)


def test_deberia_prepare_match_fallar_si_un_equipo_no_tiene_alineacion(session, partido):
    for entry in session.query(LineupEntry).filter_by(team_id=partido.team_away_id).all():
        session.delete(entry)
    session.commit()

    with pytest.raises(MatchInitializationError):
        prepare_match(session, partido.match_id)


def test_deberia_prepare_match_fallar_si_la_alineacion_esta_incompleta(session, partido):
    suplente = session.query(LineupEntry).filter_by(team_id=partido.team_host_id, is_starter=False).first()
    session.delete(suplente)
    session.commit()

    with pytest.raises(MatchInitializationError):
        prepare_match(session, partido.match_id)


def test_deberia_prepare_match_fallar_si_los_roles_no_forman_una_formacion(session, comportamiento):
    # Cada rol es válido por separado, pero mezclados no son ni 2-1 ni 1-2.
    partido = _armar_partido(session, comportamiento, roles_local=["DEF_LEFT", "FORWARD_LEFT", "FORWARD"])

    with pytest.raises(MatchInitializationError):
        prepare_match(session, partido.match_id)


# --- save_match_result / on_finished ----------------------------------------


def test_deberia_save_match_result_guardar_marcador_y_pasar_a_finished(session, partido):
    save_match_result(session, partido.match_id, home_goals=2, away_goals=1)

    session.expire_all()
    guardado = session.get(Match, partido.match_id)
    assert (guardado.home_goals, guardado.away_goals) == (2, 1)
    assert guardado.status is MatchStatus.FINISHED


def test_deberia_save_match_result_fallar_si_el_partido_no_existe(session):
    with pytest.raises(LookupError):
        save_match_result(session, 999, 0, 0)

@pytest.fixture()
def eventos_globales():
    """Un suscriptor al bus GLOBAL (el mismo bus que alimenta al WS global).
    Se desuscribe al terminar para no ensuciar a los otros tests."""
    cola = event_bus.subscribe()
    yield cola
    event_bus.unsubscribe(cola)


# --- evento MATCH_FINISHED --------------------------------------------------


def test_deberia_save_match_result_publicar_match_finished_con_el_formato_del_contrato(
    session, partido, eventos_globales
):
    save_match_result(session, partido.match_id, home_goals=2, away_goals=1)

    assert eventos_globales.qsize() == 1
    assert eventos_globales.get_nowait() == {
        "event": "MATCH_FINISHED",
        "data": {"match_id": partido.match_id, "status": "FINISHED"},
    }


def test_deberia_save_match_result_publicar_despues_de_guardar_en_la_base(session, partido, monkeypatch):
    fabrica = _fabrica_de_sesiones(session)
    estado_visto = []

    def publish_espia(nombre, data) -> None:
        # Una sesión distinta solo ve lo que ya está confirmado (commit).
        with fabrica() as otra_sesion:
            estado_visto.append(otra_sesion.get(Match, data["match_id"]).status)

    monkeypatch.setattr(event_bus, "publish", publish_espia)

    save_match_result(session, partido.match_id, home_goals=0, away_goals=0)

    assert estado_visto == [MatchStatus.FINISHED]


def test_deberia_save_match_result_no_publicar_si_el_partido_no_existe(session, eventos_globales):
    with pytest.raises(LookupError):
        save_match_result(session, 999, 0, 0)

    assert eventos_globales.qsize() == 0


@pytest.mark.asyncio
async def test_deberia_start_match_publicar_match_finished_una_sola_vez_al_terminar(
    session, partido, eventos_globales
):
    eventos_en_cola_durante_el_partido = []

    async def notify(state) -> None:
        eventos_en_cola_durante_el_partido.append(eventos_globales.qsize())

    task = start_match(
        session,
        partido.match_id,
        execute_behavior=_idle_behavior,
        apply_intentions=_noop_apply,
        notify=notify,
        registry=MatchRegistry(),
        on_finished=make_on_finished(_fabrica_de_sesiones(session)),
        tick_interval_seconds=0,
    )
    await task

    assert set(eventos_en_cola_durante_el_partido) == {0}  # nada se anuncia antes del final
    assert eventos_globales.qsize() == 1
    assert eventos_globales.get_nowait()["data"]["match_id"] == partido.match_id


@pytest.mark.asyncio
async def test_deberia_publicar_match_finished_tambien_con_el_resultado_parcial(
    session, partido, eventos_globales
):
    # Mismo truco que el test del resultado parcial: tick_interval_seconds=None
    # hace explotar el motor a la mitad.
    task = start_match(
        session,
        partido.match_id,
        execute_behavior=_idle_behavior,
        apply_intentions=_noop_apply,
        notify=_noop_notify,
        registry=MatchRegistry(),
        on_finished=make_on_finished(_fabrica_de_sesiones(session)),
        tick_interval_seconds=None,
    )
    with pytest.raises(TypeError):
        await task
    await asyncio.sleep(0)  # deja correr el callback de fin de tarea

    assert eventos_globales.qsize() == 1


# --- launch_match / start_match ---------------------------------------------


@pytest.mark.asyncio
async def test_deberia_start_match_correr_el_partido_y_persistir_el_resultado(session, partido):
    registry = MatchRegistry()
    estaba_en_el_registry = []

    async def notify(state) -> None:
        # Lo que lee el canal WS mientras el partido corre.
        estaba_en_el_registry.append(partido.match_id in registry)

    task = start_match(
        session,
        partido.match_id,
        execute_behavior=_idle_behavior,
        apply_intentions=_noop_apply,
        notify=notify,
        registry=registry,
        on_finished=make_on_finished(_fabrica_de_sesiones(session)),
        tick_interval_seconds=0,
    )
    await task

    assert len(estaba_en_el_registry) == 240
    assert all(estaba_en_el_registry)
    assert partido.match_id not in registry  # liberado al terminar

    session.expire_all()
    guardado = session.get(Match, partido.match_id)
    assert guardado.status is MatchStatus.FINISHED
    assert (guardado.home_goals, guardado.away_goals) == (0, 0)


CODIGO_CORRER_A_LA_PELOTA = """
def on_tick(api):
    api.run_to(api.get_game_state().ball_position, 1.0)
"""


@pytest.mark.asyncio
async def test_deberia_el_motor_real_mover_a_los_jugadores_con_los_atributos_de_la_base(session, partido, comportamiento):
    """Acople completo: base -> prepare_match -> execute_behavior y apply_intentions reales."""
    state = prepare_match(session, partido.match_id)
    posiciones_iniciales = {pid: p.position for pid, p in state.players.items() if p.position is not None}
    execute_behavior = make_execute_behavior({comportamiento.behavior_id: CODIGO_CORRER_A_LA_PELOTA})

    task = launch_match(
        state,
        execute_behavior=execute_behavior,
        apply_intentions=apply_intentions,
        notify=_noop_notify,
        registry=MatchRegistry(),
        on_finished=make_on_finished(_fabrica_de_sesiones(session)),
        tick_interval_seconds=0,
    )
    await task

    movidos = [pid for pid, pos in posiciones_iniciales.items() if state.players[pid].position != pos]
    assert len(movidos) == 6  # los 6 titulares corrieron: sin atributos cargados no se mueve nadie

    session.expire_all()
    assert session.get(Match, partido.match_id).status is MatchStatus.FINISHED


@pytest.mark.asyncio
async def test_deberia_start_match_no_lanzar_el_motor_si_la_inicializacion_falla(session, comportamiento):
    partido = _armar_partido(session, comportamiento, roles_local=["DEF_LEFT", "FORWARD_LEFT", "FORWARD"])
    registry = MatchRegistry()
    tareas_antes = asyncio.all_tasks()

    with pytest.raises(MatchInitializationError):
        start_match(
            session,
            partido.match_id,
            execute_behavior=_idle_behavior,
            apply_intentions=_noop_apply,
            notify=_noop_notify,
            registry=registry,
            tick_interval_seconds=0,
        )

    assert partido.match_id not in registry
    assert asyncio.all_tasks() == tareas_antes


@pytest.mark.asyncio
async def test_deberia_launch_match_rechazar_un_partido_que_ya_tiene_motor(session, partido):
    registry = MatchRegistry()
    state = prepare_match(session, partido.match_id)
    registry.add(state)  # ya hay un motor corriendo para este partido

    with pytest.raises(MatchInitializationError):
        launch_match(
            state,
            execute_behavior=_idle_behavior,
            apply_intentions=_noop_apply,
            notify=_noop_notify,
            registry=registry,
            on_finished=lambda s: None,
            tick_interval_seconds=0,
        )


def test_deberia_launch_match_fallar_claro_sin_event_loop(session, partido):
    state = prepare_match(session, partido.match_id)

    with pytest.raises(RuntimeError):
        launch_match(
            state,
            execute_behavior=_idle_behavior,
            apply_intentions=_noop_apply,
            notify=_noop_notify,
            registry=MatchRegistry(),
            on_finished=lambda s: None,
            tick_interval_seconds=0,
        )


# --- el motor muere a la mitad ---------------------------------------------


@pytest.mark.asyncio
async def test_deberia_guardar_el_resultado_parcial_si_el_motor_muere_a_la_mitad(session, partido):
    registry = MatchRegistry()

    # tick_interval_seconds=None hace explotar asyncio.sleep después del
    # primer tick con un error que ningún try del ciclo atrapa.
    task = start_match(
        session,
        partido.match_id,
        execute_behavior=_idle_behavior,
        apply_intentions=_noop_apply,
        notify=_noop_notify,
        registry=registry,
        on_finished=make_on_finished(_fabrica_de_sesiones(session)),
        tick_interval_seconds=None,
    )
    with pytest.raises(TypeError):
        await task
    await asyncio.sleep(0)  # deja correr el callback de fin de tarea

    assert partido.match_id not in registry
    session.expire_all()
    assert session.get(Match, partido.match_id).status is MatchStatus.FINISHED


@pytest.mark.asyncio
async def test_deberia_no_reintentar_si_lo_que_falla_es_guardar_el_resultado(session, partido):
    llamadas = []

    def on_finished_que_falla(state) -> None:
        llamadas.append(state.match_id)
        raise RuntimeError("la base no responde")

    registry = MatchRegistry()
    task = start_match(
        session,
        partido.match_id,
        execute_behavior=_idle_behavior,
        apply_intentions=_noop_apply,
        notify=_noop_notify,
        registry=registry,
        on_finished=on_finished_que_falla,
        tick_interval_seconds=0,
    )
    with pytest.raises(RuntimeError):
        await task
    await asyncio.sleep(0)

    assert llamadas == [partido.match_id]  # una sola vez, sin reintento
    assert partido.match_id not in registry
