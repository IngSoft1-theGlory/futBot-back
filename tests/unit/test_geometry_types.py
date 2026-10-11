"""
Tests de los tipos geométricos del motor: Vector2D y Point2D.
Puros: no necesitan base de datos ni servidor.
"""

from dataclasses import FrozenInstanceError

import pytest

from src.engine._01_to_world.data_types import Point2D, Vector2D


def test_debería_magnitud_de_vector_3_4_ser_5():
    """Triángulo 3-4-5: la magnitud es la hipotenusa."""
    assert Vector2D(3, 4).magnitude() == pytest.approx(5.0)


def test_deberia_magnitud_de_vector_cero_ser_cero():
    """El vector cero tiene magnitud 0."""
    assert Vector2D(0, 0).magnitude() == 0.0


def test_deberia_normalizar_vector_3_4_dar_vector_unitario():
    """(3, 4) normalizado es (0.6, 0.8) y su magnitud es 1."""
    normalizado = Vector2D(3, 4).normalize()

    assert normalizado.x == pytest.approx(0.6)
    assert normalizado.y == pytest.approx(0.8)
    assert normalizado.magnitude() == pytest.approx(1.0)


def test_deberia_normalizar_vector_cero_devolver_vector_cero_sin_excepcion():
    """Decisión documentada: normalize() de (0, 0) devuelve (0, 0), no ZeroDivisionError."""
    assert Vector2D(0, 0).normalize() == Vector2D(0, 0)


def test_deberia_distancia_entre_puntos_0_0_y_3_4_ser_5():
    """distance_to usa Pitágoras sobre la resta de coordenadas."""
    assert Point2D(0, 0).distance_to(Point2D(3, 4)) == pytest.approx(5.0)


def test_deberia_distancia_de_un_punto_a_si_mismo_ser_cero():
    """Borde: mismo punto, distancia 0."""
    assert Point2D(7, 2).distance_to(Point2D(7, 2)) == 0.0


def test_deberia_distancia_ser_simetrica():
    """La distancia de A a B es igual a la de B a A."""
    a, b = Point2D(1, 1), Point2D(4, 5)

    assert a.distance_to(b) == pytest.approx(b.distance_to(a))


def test_deberia_direccion_hacia_otro_punto_ser_vector_unitario():
    """De (1, 1) a (4, 5) la dirección es (0.6, 0.8)."""
    direccion = Point2D(1, 1).direction_to(Point2D(4, 5))

    assert direccion.x == pytest.approx(0.6)
    assert direccion.y == pytest.approx(0.8)


def test_deberia_direccion_en_linea_recta_ser_exacta():
    """Sobre un eje la dirección es exactamente (1, 0)."""
    assert Point2D(0, 0).direction_to(Point2D(10, 0)) == Vector2D(1, 0)


def test_deberia_direccion_hacia_el_mismo_punto_ser_vector_cero():
    """Borde: direction_to hacia sí mismo no explota, devuelve (0, 0)."""
    assert Point2D(5, 5).direction_to(Point2D(5, 5)) == Vector2D(0, 0)


def test_deberia_point2d_ser_inmutable():
    """frozen=True: asignar un atributo lanza FrozenInstanceError."""
    punto = Point2D(1, 2)

    with pytest.raises(FrozenInstanceError):
        punto.x = 10


def test_deberia_vector2d_ser_inmutable():
    """frozen=True: asignar un atributo lanza FrozenInstanceError."""
    vector = Vector2D(1, 2)

    with pytest.raises(FrozenInstanceError):
        vector.y = 10


def test_deberian_dos_puntos_con_mismos_valores_ser_iguales():
    """Igualdad por valor; al ser frozen se pueden usar en sets."""
    assert Point2D(1, 2) == Point2D(1, 2)
    assert len({Point2D(1, 2), Point2D(1, 2)}) == 1
