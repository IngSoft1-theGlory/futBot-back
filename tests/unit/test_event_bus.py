import asyncio

import pytest

from src.realtime.event_bus import MAX_QUEUE_SIZE, EventBus


@pytest.fixture
def bus():
    """Un bus nuevo por test, para que no se contaminen entre sí."""
    return EventBus()


def test_deberia_publicar_sin_suscriptores_sin_lanzar_excepcion(bus):
    bus.publish("FRIENDLY_CREATED", {"match_id": 1})  # si lanza algo, el test falla


def test_deberia_entregar_el_mismo_evento_a_dos_suscriptores_una_sola_vez(bus):
    q1 = bus.subscribe()
    q2 = bus.subscribe()

    bus.publish("FRIENDLY_CREATED", {"match_id": 1})

    assert q1.qsize() == 1
    assert q2.qsize() == 1
    assert q1.get_nowait() == q2.get_nowait()


def test_deberia_publicar_desde_fuera_de_un_endpoint(bus):
    # No hay request HTTP, ni TestClient, ni FastAPI, solo una función de test
    # llamando a publish() directamente. Si igual llega, el bus no depende de REST.
    q = bus.subscribe()

    bus.publish("MATCH_FINISHED", {"match_id": 7, "status": "FINISHED"})

    assert q.qsize() == 1


def test_deberia_entregar_el_mensaje_con_el_formato_del_contrato(bus):
    q = bus.subscribe()

    bus.publish("MATCH_STARTED", {"match_id": 12})

    assert q.get_nowait() == {"event": "MATCH_STARTED", "data": {"match_id": 12}}


def test_deberia_dejar_de_entregar_eventos_despues_de_unsubscribe(bus):
    q_sale = bus.subscribe()
    q_queda = bus.subscribe()

    bus.unsubscribe(q_sale)
    bus.publish("FRIENDLY_CANCELLED", {"match_id": 1})

    assert q_sale.qsize() == 0
    assert q_queda.qsize() == 1  # el que se queda sigue recibiendo


def test_deberia_permitir_unsubscribe_repetido_sin_fallar(bus):
    q = bus.subscribe()

    bus.unsubscribe(q)
    bus.unsubscribe(q)  # segunda vez no debe lanzar


def test_deberia_permitir_unsubscribe_de_una_cola_que_nunca_se_suscribio(bus):
    cola_ajena = asyncio.Queue()

    bus.unsubscribe(cola_ajena)  # no debe lanzar


def test_deberia_saltear_una_cola_llena_sin_afectar_a_las_otras(bus):
    q_llena = bus.subscribe()
    for i in range(MAX_QUEUE_SIZE):
        bus.publish("X", {"n": i})  # la llenamos
    q_sana = bus.subscribe()  # se suscribe después, está vacía

    bus.publish("X", {"n": "extra"})  # no debe lanzar QueueFull

    assert q_llena.qsize() == MAX_QUEUE_SIZE  # la llena no recibió el extra
    assert q_sana.qsize() == 1  # la sana sí


def test_deberia_mantener_el_orden_de_los_eventos(bus):
    q = bus.subscribe()

    bus.publish("A", {"n": 1})
    bus.publish("B", {"n": 2})
    bus.publish("C", {"n": 3})

    assert [q.get_nowait()["event"] for _ in range(3)] == ["A", "B", "C"]


def test_deberia_devolver_una_cola_distinta_en_cada_subscribe(bus):
    q1 = bus.subscribe()
    q2 = bus.subscribe()

    assert q1 is not q2