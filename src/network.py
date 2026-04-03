import socket
import json
import threading
from queue import Queue, Empty

from board import Move, Queen, Rook, Bishop, Knight, WHITE, BLACK

HOST = "127.0.0.1"
PORT = 5050

# Maps promotion piece classes to short protocol codes.
PROMO_TO_CODE = {
    Queen: "Q",
    Rook: "R",
    Bishop: "B",
    Knight: "N",
}

# Reverse mapping for decoding promotion codes from the server.
CODE_TO_PROMO = {
    "Q": Queen,
    "R": Rook,
    "B": Bishop,
    "N": Knight,
}

# Converts server color strings into the board module's color constants.
SERVER_TO_LOCAL_COLOR = {
    "white": WHITE,
    "black": BLACK,
}


def move_to_dict(move: Move) -> dict:
    """Convert a Move object into a JSON-serializable dictionary."""
    return {
        "start": list(move.start),
        "end": list(move.end),
        "promotion": PROMO_TO_CODE.get(move.promotion),
        "en_passant": move.en_passant,
        "kside_castle": move.kside_castle,
        "qside_castle": move.qside_castle,
    }


def dict_to_move(data: dict) -> Move:
    """Convert a received move dictionary back into a Move object."""
    promo_code = data.get("promotion")
    promo_piece = CODE_TO_PROMO.get(promo_code) if promo_code else None
    return Move(
        start=tuple(data["start"]),
        end=tuple(data["end"]),
        promotion=promo_piece,
        en_passant=data.get("en_passant", False),
        kside_castle=data.get("kside_castle", False),
        qside_castle=data.get("qside_castle", False),
    )


class NetworkClient:
    """TCP client for the chess server.

    Uses a background receive thread that parses newline-delimited JSON messages
    and pushes them into an inbox queue for the GUI to poll each frame.
    """
    def __init__(self, host: str = HOST, port: int = PORT):
        self.host = host
        self.port = port
        self.sock: socket.socket | None = None
        self.recv_thread: threading.Thread | None = None
        self.inbox: Queue[dict] = Queue()
        self.running = False
        self.buffer = ""

    def connect(self):
        """Connect to the server and start the receive loop."""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.host, self.port))
        self.running = True
        # Tell the server we want to join a game session.
        self._send_json({"type": "CONNECT"})
        # Receive messages on a daemon thread so the GUI loop never blocks.
        self.recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self.recv_thread.start()

    def close(self):
        """Stop the receive loop and close the socket."""
        self.running = False
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass

    def _send_json(self, msg: dict):
        if self.sock is None:
            return
        # Protocol: one JSON object per line (newline-delimited JSON).
        data = json.dumps(msg) + "\n"
        self.sock.sendall(data.encode("utf-8"))

    def send_move(self, move: Move):
        """Send a move request to the server."""
        self._send_json({
            "type": "MOVE",
            "move": move_to_dict(move),
        })

    def send_resign(self):
        """Notify the server that this player resigns."""
        self._send_json({"type": "RESIGN"})

    def send_new_game(self):
        """Request a new game from the server."""
        self._send_json({"type": "NEW_GAME"})

    def poll_message(self) -> dict | None:
        """Non-blocking read of the next received message (or None)."""
        try:
            return self.inbox.get_nowait()
        except Empty:
            return None

    def _recv_loop(self):
        """Continuously receive data, split into JSON lines, and enqueue them."""
        while self.running and self.sock is not None:
            try:
                data = self.sock.recv(4096)
                if not data:
                    # Peer closed the connection.
                    self.inbox.put({"type": "DISCONNECT"})
                    break

                self.buffer += data.decode("utf-8")
                # Process any complete newline-terminated JSON messages.
                while "\n" in self.buffer:
                    line, self.buffer = self.buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    self.inbox.put(json.loads(line))
            except (OSError, json.JSONDecodeError):
                if self.running:
                    # If the socket fails or incoming data cannot be parsed, end the connection.
                    self.inbox.put({"type": "DISCONNECT"})
                break

        self.running = False