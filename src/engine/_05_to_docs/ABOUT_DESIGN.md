# Decisiones de diseño

---

## Motor

- **El motor no toca la base de datos.** Los datos se leen antes de arrancar y el partido corre en memoria. Al terminar, `match_runner` llama a `on_finished`, una función que le pasa `match_start_service` desde afuera y que guarda el resultado.

### `state.py` — estado del partido en memoria

guarda todo lo que el motor necesita saber mientras el partido se juega. Tiene cuatro partes:

- El estado del partido (`MatchState`: jugadores, pelota, marcador, pausas y penales);
- Los registros en memoria (`match_registry` con los partidos en curso y `coach_registry` con el DT elegido);
- El armado del estado inicial (`build_initial_state`);
- Las sustituciones.

#### Decisiones de state.py

- **Hay dos niveles de estado.** `MatchState` es el estado real y solo lo modifica el motor. Cada jugador recibe una copia (`GameState`), así el código de los usuarios no puede alterar el partido ni ver datos ajenos: solo devuelve una `Intention`.
- **Los lados cambian, los equipos no.** En el Half-Time cada equipo pasa a defender el arco contrario (`host_side` cambia). `host_team_id` y `away_team_id` no cambian nunca, y el marcador sigue al equipo y no al lado.
- **En cancha o en el banco.** Un jugador está en cancha si tiene `position`, y en el banco si `position` es `None` (en el banco, `role` e `initial_position` también son `None`).
- **Reglas de sustituciones.** Solo se puede cambiar durante una pausa, y un cambio por equipo en cada una. Si un equipo planificó un cambio antes, se aplica al empezar la pausa, y se descarta si ya no sirve.
- **El DT vive en memoria, no en la base.** El comportamiento de DT elegido por cada equipo está en `coach_registry`. Si el servidor se reinicia, se pierde y hay que volver a elegirlo. Se lee al armar cada partido, por eso rige desde el próximo.
- **Los errores del motor no son errores HTTP.** `MatchInitializationError` y `SubstitutionError` no son `AppError` a propósito: el motor no sabe de HTTP y quien lo llama los traduce.

### `match_runner.py` — ciclo del partido

- **Orden de cada tick:** los comportamientos deciden → se aplican las intenciones → se detecta el gol → se suma al marcador → sube el tick → los DT pueden cambiar comportamientos → se notifica.
- **Las intenciones de todos se juntan antes de aplicar ninguna,** así nadie gana las disputas por la pelota solo por estar primero en el diccionario.
- **Un error no frena el partido.** Si falla un comportamiento, ese jugador queda en `IDLE`. Si falla `apply_intentions`, el tick sigue sin aplicar movimientos. Si falla `detect_goal`, se asume que no hubo gol. Si falla `notify` o el DT, el partido sigue.
- **`play_tick` no tiene `await`, a propósito.** El servidor cambia de tarea solo en un `await`, así que un tick se ejecuta completo y quien consulta el estado del partido ve el de antes o el de después, nunca uno a medias. El costo es que un comportamiento lento frena a todos los partidos.
- **Las piezas se reciben por parámetro** (`execute_behavior`, `apply_intentions`, `detect_goal`, `notify`), así los tests pueden pasar versiones falsas.
- **Fin del partido (`run_match`):** primero se guarda el resultado (`on_finished`) y después se libera el partido del registry, así mientras se guarda sigue consultable. Si el motor muere con un error inesperado, `_on_task_done` (en `match_start_service`) guarda el marcador del momento para que no quede en `IN_PROGRESS`.
- **Pausas (Cooling Break y Half-Time):** el reloj se detiene. Al empezar, los DT pueden cambiar comportamientos y se aplican las sustituciones planificadas, antes de avisar a los clientes, así el front ya ve la alineación nueva. Los lados se cambian al final del Half-Time, para que los suplentes que entraron también queden del lado nuevo.
- **Penales:** si un partido de liga con penales empata, la tanda se juega antes de `FINISHED`, y el resultado se guarda una sola vez.

### `player_api.py` — primitivas (`run_to`, `kick_ball`)

- **Si se llama a varias primitivas en un tick, gana la última.** Si no se llama a ninguna, la intención es `IDLE`.
- **Solo registran la intención.** El movimiento o la patada real los calcula `resolve`.
- **Argumentos inválidos:** lanzan `ValueError` y el jugador queda en `IDLE`.
- **Cada jugador tiene su propio `PlayerAPI` en cada tick** (lo crea `execute_behavior`). `on_tick` no devuelve nada: lo que decide queda registrado en el `api` y el motor lo lee con `api.intention`. Por eso la intención nunca se arrastra de un tick a otro ni entre jugadores.

### Código del usuario — `behavior_service.py` y `behavior_executor.py`

- **El código del usuario está limitado.** Al guardar (`behavior_service`) se rechazan `for`, `while`, `import`, comprensiones y `__`, y un DT no puede usar primitivas de jugador ni al revés. Al ejecutar (`behavior_executor`), solo tiene un puñado de funciones (`abs`, `min`, `len`, etc.) más `math`, `random`, `Point2D` y `Vector2D` ya cargados.

### `pitch.py` — cancha, arcos y goles

- **La cancha** mide 105 × 60 m. HOME defiende `x = 0` y ataca hacia `x = 105`; AWAY es el espejo.
- **Formaciones:** las posiciones iniciales se definen solo para HOME y se giran 180° para AWAY.
- **El arco se representa de dos formas:** `team_goal` y `opponent_goal` son un punto (para apuntar al patear). `GoalArea` es un rango entre los postes (para detectar goles) y es de uso interno: nunca llega a los comportamientos.
- **`detect_goal`** devuelve el lado que convierte (no el que recibe) y solo mira dónde termina la pelota en el tick. Para que un tiro rápido no se escape, `goal_line_crossing` calcula por dónde cruza la línea y `simulation._move_ball` frena la pelota ahí (o la ataja un arquero, y entonces no hay gol). El reinicio de la cancha ocurre al principio del tick siguiente: si fuera al final del mismo tick, `detect_goal` nunca vería el gol.

#### Recorrido de un gol

1. `simulation._move_ball` mueve la pelota y la frena en lo primero que toca: un arquero (atajada, no hay gol) o la línea de gol.
2. `pitch.detect_goal` mira dónde quedó la pelota y detecta el gol.
3. `match_runner.run_tick` suma 1 al marcador del equipo que convirtió.
4. `simulation._reset_after_goal` pone la pelota quieta sobre la línea central, corrida 14 m hacia el arco del equipo que recibió el gol (así ese equipo saca), y a los jugadores en su posición inicial, al principio del tick siguiente. Si fuera al final, `detect_goal` nunca vería el gol.
5. Al terminar el partido, `match_start_service` guarda el marcador final en la base.

---

## Comportamientos y DT

- **Los comportamientos por default no se pueden editar.**
- **Una sola pantalla sirve para crear, editar y ver un comportamiento.**
- **Toda liga arranca sin DT.** El DT elegido rige desde el próximo partido, así que el primero nunca tiene DT.
- **El DT actúa distinto que un jugador.** No registra intenciones: modifica el partido directo, después de cada tick y al empezar cada pausa, y solo sobre su propio equipo. Puede cambiar el comportamiento de un titular y hacer sustituciones.

---

## Penales

- **Comportamientos del sistema:** el pateador y el arquero usan comportamientos propios del sistema, no los de los usuarios. No se guardan en la base (no aparecen en `GET /behaviors`) y se asignan en memoria en cada turno.
- **Quién patea y ataja:** solo los titulares. El orden de pateo y el de atajada se sortean por separado, una sola vez al empezar la tanda.
- **Cómo se decide:** cada ronda es un penal de cada equipo, con un máximo de 3 rondas. Gana el equipo que convierte cuando el otro no. Si tras las 3 rondas siguen empatados, se sortea al ganador y se le suma un gol de penal, así la tanda nunca termina empatada.
- **Límites de tiempo:** cada penal dura como máximo 20 ticks (10 s) y, si nadie convierte en ese tiempo, no hay gol. Entre un penal y el siguiente hay una pausa de 3 s con el estado congelado, para que se vea cómo terminó el anterior. Antes de cada patada se muestra la pelota quieta y los jugadores en su lugar durante 1,5 s.
- **Marcador y arco:** reutiliza `play_tick`, pero sus goles van a un marcador aparte (`phome` y `paway`). Se patea siempre contra el mismo arco, por eso el gol se le suma al equipo que patea y no al lado que “mete el gol”.

---

## Ligas

- **Las ligas admiten solo una cantidad par de equipos.** El cupo máximo puede ser 4, 6, 8, 10 o 12. Se decidió así para que en cada fecha todos los equipos jueguen y ninguno quede libre. El fixture (`fixture_service`) solo se genera con una cantidad par.
- **No se puede iniciar a mano una liga con una cantidad impar de inscriptos** (por ejemplo, 5 de 6). Cuando se completa el cupo, la liga se inicia sola.