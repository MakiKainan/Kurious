"""Bridge server: WebSocket on ws://localhost:8765 and static HTTP server for superfront end."""
import asyncio
import json
import logging
import os
import threading
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import websockets

logger = logging.getLogger("kurious.server")

_clients = set()
_clients_lock = threading.Lock()
_command_callback = None
_loop = None
_ws_server = None
_http_server = None
_ws_thread = None
_http_thread = None
_stop_event = None


def set_command_callback(cb):
    """Sets a callback function for commands received from WebSocket clients."""
    global _command_callback
    _command_callback = cb


class _FrontEndHTTPHandler(SimpleHTTPRequestHandler):
    """Serves the static superfront end folder, routing '/' to Kurious.dc.html."""

    def __init__(self, *args, directory=None, **kwargs):
        super().__init__(*args, directory=directory, **kwargs)

    def do_GET(self):
        if self.path in ("/", ""):
            self.send_response(302)
            self.send_header("Location", "/Kurious.dc.html")
            self.end_headers()
            return
        super().do_GET()

    def log_message(self, format, *args):
        # Suppress noisy HTTP request logging in stdout
        pass


async def _ws_handler(websocket):
    with _clients_lock:
        _clients.add(websocket)
    try:
        # Send initial state so the UI connects and initializes immediately
        await websocket.send(json.dumps({"type": "listening"}))
        async for message in websocket:
            try:
                data = json.loads(message)
                if _command_callback:
                    _command_callback(data)
            except Exception as e:
                logger.warning(f"Error handling client message: {e}")
    except Exception:
        pass
    finally:
        with _clients_lock:
            _clients.discard(websocket)


async def _run_ws(host, port, stop_evt):
    global _ws_server
    async with websockets.serve(_ws_handler, host, port) as server:
        _ws_server = server
        await stop_evt.wait()


def _ws_worker(host, port, stop_evt, ready_evt):
    global _loop
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    ready_evt.set()
    try:
        _loop.run_until_complete(_run_ws(host, port, stop_evt))
    except Exception as e:
        logger.error(f"WebSocket server error: {e}")
    finally:
        _loop.close()


def broadcast(msg):
    """Thread-safe broadcast of a JSON dictionary to all connected WebSocket clients."""
    with _clients_lock:
        if not _clients or _loop is None or not _loop.is_running():
            return
        clients_copy = set(_clients)
    data = json.dumps(msg)
    _loop.call_soon_threadsafe(lambda: websockets.broadcast(clients_copy, data))


def has_clients():
    """Returns True if there is at least one connected WebSocket client."""
    with _clients_lock:
        return len(_clients) > 0


def start_server(ws_port=8765, http_port=8000, serve_dir="superfront end", host="localhost", open_browser=True):
    """Starts both the WebSocket bridge server and the static HTTP server in background threads."""
    global _http_server, _stop_event, _ws_thread, _http_thread

    # Ensure serve directory exists
    base_dir = os.path.abspath(serve_dir)
    if not os.path.exists(base_dir):
        os.makedirs(base_dir, exist_ok=True)

    # 1. Start WebSocket server
    _stop_event = asyncio.Event()
    ready_evt = threading.Event()
    _ws_thread = threading.Thread(
        target=_ws_worker, args=(host, ws_port, _stop_event, ready_evt), daemon=True
    )
    _ws_thread.start()
    ready_evt.wait()

    # 2. Start HTTP server
    def make_handler(*args, **kwargs):
        return _FrontEndHTTPHandler(*args, directory=base_dir, **kwargs)

    _http_server = ThreadingHTTPServer((host, http_port), make_handler)
    _http_thread = threading.Thread(target=_http_server.serve_forever, daemon=True)
    _http_thread.start()

    url = f"http://{host}:{http_port}/Kurious.dc.html"
    print(f"\n[frontend ready] Web UI: {url} | WebSocket: ws://{host}:{ws_port}")

    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    return url


def stop_server():
    """Stops both the WebSocket and HTTP servers."""
    global _http_server, _stop_event, _loop
    if _stop_event and _loop and _loop.is_running():
        _loop.call_soon_threadsafe(_stop_event.set)
    if _http_server:
        try:
            _http_server.shutdown()
        except Exception:
            pass
        _http_server = None
