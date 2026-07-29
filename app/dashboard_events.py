from fastapi import WebSocket

_clients: set[WebSocket] = set()


async def register(websocket: WebSocket) -> None:
    await websocket.accept()
    _clients.add(websocket)


def unregister(websocket: WebSocket) -> None:
    _clients.discard(websocket)


async def broadcast(event: dict) -> None:
    """Best-effort fan-out to every connected dashboard client. A dashboard
    that isn't listening (or has gone away) must never affect the actual
    call, so failures here are swallowed rather than raised."""
    dead = []
    for ws in list(_clients):
        try:
            await ws.send_json(event)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _clients.discard(ws)
