import asyncio

MAX_QUEUE_SIZE = 100  

class EventBus:
    """Bus de eventos en memoria. Cada suscriptor es una asyncio.Queue
    
    Importante: publish() debe llamarse desde el event loop (async def).
    Las colas de asyncio no son thread-safe.
    """

    def __init__(self):
        self._subscribers = set() 

    def subscribe(self) -> asyncio.Queue:
        queue = asyncio.Queue(maxsize = MAX_QUEUE_SIZE)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    def publish(self, event_name: str, data: dict) -> None:
        message = {"event": event_name, "data": data}
        
        # se recorrer el conjunto
        for queue in set(self._subscribers):
            try:
                queue.put_nowait(message)

            except asyncio.QueueFull:
                pass  # Descarte silencioso, ignora el elem
                        # que no entro en la cola