"""
jj_addon.py - mitmproxy addon，拦截JJ象棋 WebSocket 落子消息

用法：
    mitmproxy -s proxy/jj_addon.py --listen-port 8080
    或
    mitmdump -s proxy/jj_addon.py --listen-port 8080

需在系统/JJ象棋中设置HTTP代理 127.0.0.1:8080，并安装mitmproxy CA证书。
"""
import json
import struct
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from mitmproxy import websocket
from mitmproxy.websocket import WebSocketMessage

sys.path.insert(0, str(Path(__file__).parent.parent))
from server.db import get_conn, init_db
from server.xiangqi import START_FEN, apply_move, coords_to_uci

MSG_CHESS_MOVE = 0x03F3
DB_PATH = Path(__file__).parent.parent / "chess.db"

# game_id 缓存：matchid -> (game_id, current_fen, move_no)
_game_cache: dict = {}
_conn: sqlite3.Connection | None = None


def _get_conn():
    global _conn
    if _conn is None:
        _conn = get_conn(str(DB_PATH))
        init_db(_conn)
    return _conn


def websocket_message(flow):
    msg: WebSocketMessage = flow.websocket.messages[-1]
    data = msg.content

    # 只处理二进制帧，且至少8字节
    if msg.type != "binary" or len(data) < 8:
        return

    msg_type = struct.unpack_from("<I", data, 0)[0]
    payload_len = struct.unpack_from("<I", data, 4)[0]

    if msg_type != MSG_CHESS_MOVE:
        return

    try:
        payload = data[8: 8 + payload_len].decode("utf-8")
        obj = json.loads(payload)
    except Exception:
        return

    ack = obj.get("chess_ack_msg", {})
    matchid = ack.get("matchid")
    move_msg = ack.get("chessmove_ack_msg", {})

    if not matchid or not move_msg:
        return

    from_x = move_msg.get("beginposx")
    from_y = move_msg.get("beginposy")
    to_x = move_msg.get("endposx")
    to_y = move_msg.get("endposy")
    seat = move_msg.get("seat", 0)
    round_time = move_msg.get("roundtime", 0)

    if None in (from_x, from_y, to_x, to_y):
        return

    conn = _get_conn()

    # 确保game记录存在
    if matchid not in _game_cache:
        row = conn.execute("SELECT id FROM games WHERE matchid=?", (matchid,)).fetchone()
        if row:
            game_id = row[0]
            last_move = conn.execute(
                "SELECT fen, move_no FROM moves WHERE game_id=? ORDER BY move_no DESC LIMIT 1",
                (game_id,)
            ).fetchone()
            fen = last_move["fen"] if last_move else START_FEN
            move_no = last_move["move_no"] if last_move else 0
        else:
            conn.execute(
                "INSERT INTO games (matchid, start_time) VALUES (?,?)",
                (matchid, datetime.utcnow().isoformat())
            )
            conn.commit()
            game_id = conn.execute("SELECT id FROM games WHERE matchid=?", (matchid,)).fetchone()[0]
            fen = START_FEN
            move_no = 0
        _game_cache[matchid] = {"game_id": game_id, "fen": fen, "move_no": move_no}

    cache = _game_cache[matchid]
    game_id = cache["game_id"]
    new_fen = apply_move(cache["fen"], from_x, from_y, to_x, to_y)
    move_no = cache["move_no"] + 1

    conn.execute(
        "INSERT INTO moves (game_id, move_no, seat, from_x, from_y, to_x, to_y, fen, round_time) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (game_id, move_no, seat, from_x, from_y, to_x, to_y, new_fen, round_time)
    )
    conn.commit()

    cache["fen"] = new_fen
    cache["move_no"] = move_no

    uci = coords_to_uci(from_x, from_y, to_x, to_y)
    print(f"[chess] matchid={matchid} move#{move_no} seat={seat} {uci} | {new_fen[:30]}...")
