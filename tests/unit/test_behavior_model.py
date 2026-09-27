"""
Tests que verifican los Criterios de Aceptacion del ticket
"Implementar modelo y persistencia de comportamiento":

  1. Debe existir un modelo Behavior con los atributos behavior_id, name,
     description, code, user_id y is_default.
  2. Debe existir una estructura persistente para almacenar los comportamientos.
  3. Cada comportamiento debe tener un identificador unico.
  4. Los datos almacenados deben corresponder con los atributos definidos
     en el modelo.

Usan el User y el Team reales del repo (no mocks) porque Behavior.user_id
es una ForeignKey a la tabla "users".
"""
from src.models.behavior import Behavior


def test_behavior_tiene_los_atributos_requeridos():
    """CA1: el modelo expone behavior_id, name, description, code, user_id e is_default."""
    behavior = Behavior(
        name="Patear pelota",
        description="El jugador patea la pelota",
        code="def on_tick(PlayerAPI): ...",
        user_id=1,
        is_default=False,
    )

    assert hasattr(behavior, "behavior_id")
    assert behavior.name == "Patear pelota"
    assert behavior.description == "El jugador patea la pelota"
    assert behavior.code == "def on_tick(PlayerAPI): ..."
    assert behavior.user_id == 1
    assert behavior.is_default is False


def test_behavior_se_persiste_en_la_base_de_datos(session, usuario_con_equipo):
    """CA2 y CA4: existe una estructura persistente y los datos guardados
    corresponden con los atributos definidos al crear el objeto."""
    nuevo = Behavior(
        name="Correr al arco",
        description="El jugador corre hacia el arco rival",
        code="def on_tick(PlayerAPI): ...",
        user_id=usuario_con_equipo.user_id,
        is_default=False,
    )

    session.add(nuevo)
    session.commit()
    session.refresh(nuevo)

    guardado = session.get(Behavior, nuevo.behavior_id)

    assert guardado is not None
    assert guardado.name == "Correr al arco"
    assert guardado.description == "El jugador corre hacia el arco rival"
    assert guardado.code == "def on_tick(PlayerAPI): ..."
    assert guardado.user_id == usuario_con_equipo.user_id
    assert guardado.is_default is False


def test_behavior_id_es_unico_y_autogenerado(session, usuario_con_equipo):
    """CA3: cada comportamiento tiene un identificador unico."""
    b1 = Behavior(name="A", description="a", code="pass", user_id=usuario_con_equipo.user_id)
    b2 = Behavior(name="B", description="b", code="pass", user_id=usuario_con_equipo.user_id)

    session.add_all([b1, b2])
    session.commit()

    assert b1.behavior_id is not None
    assert b2.behavior_id is not None
    assert b1.behavior_id != b2.behavior_id


def test_is_default_por_defecto_es_false(session, usuario_con_equipo):
    """Un comportamiento personalizado, si no se especifica, no es default."""
    behavior = Behavior(
        name="Custom", description="desc", code="pass", user_id=usuario_con_equipo.user_id
    )

    session.add(behavior)
    session.commit()
    session.refresh(behavior)

    assert behavior.is_default is False


def test_behavior_default_puede_no_tener_usuario(session):
    """Un comportamiento predeterminado del sistema no pertenece a ningún
    usuario (user_id nullable)."""
    behavior = Behavior(
        name="Patear pelota",
        description="Comportamiento del sistema",
        code="pass",
        user_id=None,
        is_default=True,
    )

    session.add(behavior)
    session.commit()
    session.refresh(behavior)

    assert behavior.behavior_id is not None
    assert behavior.user_id is None
    assert behavior.is_default is True


def test_relacion_user_behaviors(session, usuario_con_equipo):
    """La relación User.behaviors <-> Behavior.user queda bien configurada
    (back_populates en ambos lados, sin la cual configure_mappers() falla)."""
    behavior = Behavior(
        name="Defender",
        description="desc",
        code="pass",
        user_id=usuario_con_equipo.user_id,
    )
    session.add(behavior)
    session.commit()
    session.refresh(usuario_con_equipo)

    assert behavior.user.user_id == usuario_con_equipo.user_id
    assert behavior in usuario_con_equipo.behaviors


def test_borrar_usuario_borra_sus_comportamientos_personalizados(session, usuario_con_equipo):
    """cascade="all, delete-orphan" en User.behaviors: al borrar el User,
    sus Behaviors personalizados se borran (no quedan huérfanos)."""
    behavior = Behavior(
        name="Defender",
        description="desc",
        code="pass",
        user_id=usuario_con_equipo.user_id,
    )
    session.add(behavior)
    session.commit()
    behavior_id = behavior.behavior_id

    session.delete(usuario_con_equipo)
    session.commit()

    assert session.get(Behavior, behavior_id) is None
