import socket
import threading
import json

from board import Board, Move, WHITE, BLACK, Queen, Rook, Bishop, Knight

HOST = "127.0.0.1"
PORT = 5050

matchmaking_queue = []

PROMO_TO_CODE = {
    Queen: "Q",
    Rook: "R",
    Bishop: "B",
    Knight: "N",
}

CODE_TO_PROMO = {
    "Q": Queen,
    "R": Rook,
    "B": Bishop,
    "N": Knight,
}


def send_json(conn: socket.socket, msg: dict):
    data = json.dumps(msg) + "\n"
    conn.sendall(data.encode("utf-8"))


def recv_json(conn: socket.socket, buffer: str) -> tuple[dict | None, str]:
    while "\n" not in buffer:
        data = conn.recv(4096)
        if not data:
            return None, buffer
        buffer += data.decode("utf-8")

    line, buffer = buffer.split("\n", 1)
    line = line.strip()
    if not line:
        return None, buffer
    return json.loads(line), buffer


def move_to_dict(move: Move) -> dict:
    return {
        "start": list(move.start),
        "end": list(move.end),
        "promotion": PROMO_TO_CODE.get(move.promotion),
        "en_passant": move.en_passant,
        "kside_castle": move.kside_castle,
        "qside_castle": move.qside_castle,
    }


def dict_to_move(data: dict) -> Move:
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
    if board.is_checkmate():
        winner = "white" if board.turn == BLACK else "black"
        return "checkmate", winner
    if board.is_stalemate():
        return "stalemate", None
    if board.in_check(board.turn):
        return "check", None
    return "ongoing", None


def broadcast_state(conn_white: socket.socket, conn_black: socket.socket, board: Board, last_move: Move | None = None):
    status, winner = game_status(board)
    msg = {
        "type": "STATE",
        "turn": board.turn,
        "status": status,
        "winner": winner,
        "last_move": move_to_dict(last_move) if last_move else None,
    }
    send_json(conn_white, msg)
    send_json(conn_black, msg)


def game_session(conn_white: socket.socket, conn_black: socket.socket):
    board = Board()

    send_json(conn_white, {"type": "WELCOME", "color": "white"})
    send_json(conn_black, {"type": "WELCOME", "color": "black"})
    broadcast_state(conn_white, conn_black, board)

    sockets = {
        WHITE: conn_white,
        BLACK: conn_black,
    }
    other = {
        WHITE: conn_black,
        BLACK: conn_white,
    }
    buffers = {
        WHITE: "",
        BLACK: "",
    }

    try:
        while True:
            active_color = board.turn
            conn = sockets[active_color]

            msg, buffers[active_color] = recv_json(conn, buffers[active_color])
            if msg is None:
                winner = "black" if active_color == WHITE else "white"
                send_json(other[active_color], {
                    "type": "GAME_OVER",
                    "status": "disconnect",
                    "winner": winner,
                })
                break

            if msg["type"] == "RESIGN":
                winner = "black" if active_color == WHITE else "white"
                send_json(conn_white, {"type": "GAME_OVER", "status": "resign", "winner": winner})
                send_json(conn_black, {"type": "GAME_OVER", "status": "resign", "winner": winner})
                break

            if msg["type"] != "MOVE":
                send_json(conn, {"type": "ERROR", "message": "Unknown message type"})
                continue

            move = dict_to_move(msg["move"])

            if not move_is_legal(board, move):
                send_json(conn, {"type": "ERROR", "message": "Illegal move"})
                continue

            board.apply_move(move)
            broadcast_state(conn_white, conn_black, board, last_move=move)

            status, winner = game_status(board)
            if status in ("checkmate", "stalemate"):
                send_json(conn_white, {"type": "GAME_OVER", "status": status, "winner": winner})
                send_json(conn_black, {"type": "GAME_OVER", "status": status, "winner": winner})
                break

    finally:
        conn_white.close()
        conn_black.close()


def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, PORT))
    server.listen()
    print(f"[STARTING] Chess server listening on {HOST}:{PORT}")

    try:
        while True:
            conn, addr = server.accept()
            data = conn.recv(1024).decode("utf-8")

            if "CONNECT" in data:
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