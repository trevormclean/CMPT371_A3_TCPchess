import socket
import threading
import json
import select

from board import Board, Move, WHITE, BLACK, Queen, Rook, Bishop, Knight

HOST = "127.0.0.1"
PORT = 5050

matchmaking_queue = []

# Maps promotion piece classes to short protocol codes.
PROMO_TO_CODE = {
    Queen: "Q",
    Rook: "R",
    Bishop: "B",
    Knight: "N",
}

# Reverse mapping for decoding promotion codes from the client.
CODE_TO_PROMO = {
    "Q": Queen,
    "R": Rook,
    "B": Bishop,
    "N": Knight,
}


def send_json(conn: socket.socket, msg: dict) -> bool:
    """Send one newline-delimited JSON message to a client.

    Returns False if the socket is closed/reset.
    """
    data = json.dumps(msg) + "\n"
    try:
        conn.sendall(data.encode("utf-8"))
        return True
    except (ConnectionResetError, OSError):
        return False


def recv_json(conn: socket.socket, buffer: str) -> tuple[dict | None, str]:
    """Receive a single newline-delimited JSON message.

    Returns (message, updated_buffer). Message is None on disconnect/reset.
    """
    while "\n" not in buffer:
        try:
            data = conn.recv(4096)
        except (ConnectionResetError, OSError):
            return None, buffer

        if not data:
            return None, buffer

        buffer += data.decode("utf-8")

    line, buffer = buffer.split("\n", 1)
    line = line.strip()
    if not line:
        return None, buffer
    return json.loads(line), buffer


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


def move_is_legal(board: Board, move: Move) -> bool:
    """Validate a client move against the server's legal move generator."""
    sr, sc = move.start
    legal_moves = board.get_legal_moves(sr, sc)
    for m in legal_moves:
        if (
            m.start == move.start and
            m.end == move.end and
            m.promotion == move.promotion and
            m.en_passant == move.en_passant and
            m.kside_castle == move.kside_castle and
            m.qside_castle == move.qside_castle
        ):
            return True
    return False


def game_status(board: Board) -> tuple[str, str | None]:
    """Compute a high-level game status string (and winner if applicable)."""
    if board.is_checkmate():
        winner = "white" if board.turn == BLACK else "black"
        return "checkmate", winner
    if board.is_stalemate():
        return "stalemate", None
    if board.in_check(board.turn):
        return "check", None
    return "ongoing", None


def broadcast_state(conn_white: socket.socket, conn_black: socket.socket, board: Board, last_move: Move | None = None) -> bool:
    """Send the current board status to both clients."""
    status, winner = game_status(board)
    msg = {
        "type": "STATE",
        "turn": board.turn,
        "status": status,
        "winner": winner,
        "last_move": move_to_dict(last_move) if last_move else None,
    }
    ok1 = send_json(conn_white, msg)
    ok2 = send_json(conn_black, msg)
    return ok1 and ok2


def game_session(conn_white: socket.socket, conn_black: socket.socket):
    """Run a single two-player chess session with rematch support."""
    board = Board()
    game_finished = False

    if not send_json(conn_white, {"type": "WELCOME", "color": "white"}):
        return
    if not send_json(conn_black, {"type": "WELCOME", "color": "black"}):
        return
    if not broadcast_state(conn_white, conn_black, board):
        return

    buffers = {
        conn_white: "",
        conn_black: "",
    }
    colors = {
        conn_white: WHITE,
        conn_black: BLACK,
    }

    try:
        while True:
            readable, _, _ = select.select([conn_white, conn_black], [], [])

            for conn in readable:
                msg, buffers[conn] = recv_json(conn, buffers[conn])
                color = colors[conn]
                other_conn = conn_black if conn is conn_white else conn_white

                if msg is None:
                    # Only send a disconnect result if the game was still active.
                    if not game_finished:
                        winner = "black" if color == WHITE else "white"
                        send_json(other_conn, {
                            "type": "GAME_OVER",
                            "status": "disconnect",
                            "winner": winner,
                        })
                    return

                msg_type = msg.get("type")

                if msg_type == "NEW_GAME":
                    if not game_finished:
                        send_json(conn, {
                            "type": "ERROR",
                            "message": "Game is still in progress",
                        })
                        continue

                    board = Board()
                    game_finished = False
                    send_json(conn_white, {"type": "RESET"})
                    send_json(conn_black, {"type": "RESET"})
                    broadcast_state(conn_white, conn_black, board)
                    continue

                if msg_type == "RESIGN":
                    if game_finished:
                        send_json(conn, {
                            "type": "ERROR",
                            "message": "Game is already over",
                        })
                        continue

                    winner = "black" if color == WHITE else "white"
                    send_json(conn_white, {
                        "type": "GAME_OVER",
                        "status": "resign",
                        "winner": winner,
                    })
                    send_json(conn_black, {
                        "type": "GAME_OVER",
                        "status": "resign",
                        "winner": winner,
                    })
                    game_finished = True
                    continue

                if msg_type != "MOVE":
                    send_json(conn, {
                        "type": "ERROR",
                        "message": "Unknown message type",
                    })
                    continue

                if game_finished:
                    send_json(conn, {
                        "type": "ERROR",
                        "message": "Game is over. Start a new game.",
                    })
                    continue

                if color != board.turn:
                    send_json(conn, {
                        "type": "ERROR",
                        "message": "Not your turn",
                    })
                    continue

                move = dict_to_move(msg["move"])

                if not move_is_legal(board, move):
                    send_json(conn, {
                        "type": "ERROR",
                        "message": "Illegal move",
                    })
                    continue

                board.apply_move(move)
                if not broadcast_state(conn_white, conn_black, board, last_move=move):
                    return

                status, winner = game_status(board)
                if status in ("checkmate", "stalemate"):
                    send_json(conn_white, {
                        "type": "GAME_OVER",
                        "status": status,
                        "winner": winner,
                    })
                    send_json(conn_black, {
                        "type": "GAME_OVER",
                        "status": status,
                        "winner": winner,
                    })
                    game_finished = True

    finally:
        conn_white.close()
        conn_black.close()


def start_server():
    """Accept connections, match players in pairs, and start sessions."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, PORT))
    server.listen()
    print(f"[STARTING] Chess server listening on {HOST}:{PORT}")

    try:
        while True:
            conn, addr = server.accept()
            data = conn.recv(1024).decode("utf-8")

            if "CONNECT" in data:
                # Simple matchmaking: queue connections and start a game per pair.
                matchmaking_queue.append(conn)
                print(f"[QUEUE] Player added from {addr}. Queue size: {len(matchmaking_queue)}")

                if len(matchmaking_queue) >= 2:
                    player_white = matchmaking_queue.pop(0)
                    player_black = matchmaking_queue.pop(0)
                    print("[MATCH] 2 players found. Starting chess session.")
                    threading.Thread(
                        target=game_session,
                        args=(player_white, player_black),
                        daemon=True,
                    ).start()
    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Server closing...")
    finally:
        server.close()


if __name__ == "__main__":
    start_server()