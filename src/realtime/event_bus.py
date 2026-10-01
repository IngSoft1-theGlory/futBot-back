import asyncio

MAX_QUEUE_SIZE = 100  

class EventBus:
    """Bus de eventos en memoria. Cada suscriptor es una asyncio.Queue
    """

    def __init__(self):
        self._subscribers = set() 

    def subscribe(self) -> asyncio.Queue:
        queue = asyncio.Queue(maxsize = MAX_QUEUE_SIZE)
        self._subscribers = queue 
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        queue.discard(self)

    def publish(self, event_name: str, data: dict) -> None:
        message = data 
        
        # se recorrer el conjunto
        for queue in set(self._subscribers):
            try:
                queue.put_nowait(event_name)

            except asyncio.QueuueFull:
                pass