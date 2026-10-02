import asyncio

MAX_QUEUE_SIZE = 100    # Tamaño maximo de la cola
                        # cambiar aca si se quiere otro tamaño 

class EventBus:
    """Bus de eventos en memoria. Cada suscriptor es una asyncio.Queue
    
    Importante: publish() debe llamarse desde el event loop (async def).
    Las colas de asyncio no son thread-safe.
    """

    def __init__(self):
        self._subscribers = set() 

    def subscribe(self) -> asyncio.Queue:
        """ 
        Registra un nuevo subscriptor y devuelve una cola(queue) 
        """
        # se crea la cola con un tamaño maximo
        queue = asyncio.Queue(maxsize = MAX_QUEUE_SIZE)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        """ 
        Se saca la cola del bus, 
        pero no se saca las colas de los demas subscriptores 
        """
        self._subscribers.discard(queue)

    def publish(self, event_name: str, data: dict) -> None:
        """ 
        Deja el evento en la cola de cada subscriptor,
        sin tener que esperar a ninguno
        """
        message = {"event": event_name, "data": data}
        
        # se recorrer el conjunto
        for queue in set(self._subscribers):
            try:
                queue.put_nowait(message) # deja el msj sin esperar

            except asyncio.QueueFull: # captura de error 
                pass  # descarte silencioso, ignora el elem
                        # que no entro en la cola


# Instancia unica del bus, compartida por todo el servidor
# quien publique o se suscriba debe importa este objeto
event_bus = EventBus