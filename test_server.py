"""Unit tests for server.py (WebSocket bridge and static HTTP server)."""
import asyncio
import json
import time
import urllib.request
import websockets

import server


def test_server():
    # Use non-default ports for testing to avoid conflicts
    ws_port = 8795
    http_port = 8796

    url = server.start_server(
        ws_port=ws_port,
        http_port=http_port,
        serve_dir="superfront end",
        open_browser=False,
    )
    time.sleep(0.5)

    try:
        # 1. Test HTTP server redirect and static file serving
        req = urllib.request.urlopen(f"http://localhost:{http_port}/", timeout=3)
        assert req.status == 200
        assert req.geturl() == f"http://localhost:{http_port}/Kurious.dc.html"
        body = req.read().decode("utf-8")
        assert "<x-dc>" in body
        print("HTTP server test passed.")

        # 2. Test WebSocket connection and event broadcasting
        async def test_ws():
            uri = f"ws://localhost:{ws_port}"
            async with websockets.connect(uri) as ws:
                # Expect initial 'listening' message upon connection
                init_msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
                assert init_msg.get("type") == "listening"

                assert server.has_clients()

                # Broadcast partial
                server.broadcast({"type": "partial", "text": "napoleon war"})
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
                assert msg == {"type": "partial", "text": "napoleon war"}

                # Broadcast query
                server.broadcast({"type": "query", "words": ["napoleon", "war"], "new": "war"})
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
                assert msg == {"type": "query", "words": ["napoleon", "war"], "new": "war"}

                # Broadcast article
                art_payload = {
                    "type": "article",
                    "title": "French invasion of Russia",
                    "url": "https://en.wikipedia.org/wiki/French_invasion_of_Russia",
                    "description": "1812 campaign",
                    "extract": "The French invasion...",
                    "thumbnail": "",
                    "parts": {"rel": 0.6, "cov": 1.0, "int": 0.9},
                    "also": ["Napoleon"],
                }
                server.broadcast(art_payload)
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
                assert msg == art_payload

                # Broadcast stopped
                server.broadcast({"type": "stopped"})
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
                assert msg == {"type": "stopped"}

                # Test sending command from client
                received_cmd = []
                server.set_command_callback(lambda cmd: received_cmd.append(cmd))
                await ws.send(json.dumps({"action": "toggle_pause"}))
                await asyncio.sleep(0.1)
                assert received_cmd == [{"action": "toggle_pause"}]

        asyncio.run(test_ws())
        print("WebSocket bridge and command dispatch test passed.")

    finally:
        server.stop_server()
        time.sleep(0.3)
        print("Clean shutdown passed.")


if __name__ == "__main__":
    test_server()
    print("All server tests passed.")
