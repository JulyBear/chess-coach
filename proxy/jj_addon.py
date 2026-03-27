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

from mitmproxy.websocket import WebSocketMessage, Opcode

sys.path.insert(0, str(Path(__file__).parent.parent))
from server.db import get_conn, init_db
from server.xiangqi import START_FEN, apply_move, coords_to_uci

MSG_LOBBY  = 0x14801  # 客户端→服务器 大厅/棋局请求
MSG_ACK    = 0x0000   # 服务器→客户端 回应
MSG_CHESS_MOVE = 0x03F3
DB_PATH = Path(__file__).parent.parent / "chess.db"

# 当前活跃对局缓存：matchid -> {game_id, fen, move_no, my_seat, ended}
_game_cache: dict = {}
_conn: sqlite3.Connection | None = None


def _get_conn():
    global _conn
    if _conn is None:
        _conn = get_conn(str(DB_PATH))
        init_db(_conn)
    return _conn


def _parse(data: bytes):
    """解析帧头，返回 (msg_type, payload_str) 或 None"""
    if len(data) < 8:
        return None
    msg_type = struct.unpack_from("<I", data, 0)[0]
    payload_len = struct.unpack_from("<I", data, 4)[0]
    try:
        payload = data[8: 8 + payload_len].decode("utf-8")
        return msg_type, json.loads(payload)
    except Exception:
        return None


def _handle_start(matchid: int, conn):
    """收到 startclientex_ack_msg，强制新建 game 记录"""
    game_id = conn.execute(
        "INSERT INTO games (matchid, start_time) VALUES (?, ?)",
        (matchid, datetime.now().isoformat())
    ).lastrowid
    conn.commit()
    _game_cache[matchid] = {"game_id": game_id, "fen": START_FEN, "move_no": 0, "my_seat": None, "ended": False}
    print(f"[chess] NEW GAME matchid={matchid} game_id={game_id}")


def _handle_my_seat(matchid: int, is_red: int, conn):
    """从 chessbotinfo_req_msg 或 chessmove_req_msg 推断 rain 的座位"""
    if matchid not in _game_cache:
        return
    cache = _game_cache[matchid]
    if cache["my_seat"] is not None:
        return
    # isRed=1 表示 rain 是红棋 seat=0，isRed=0 表示黑棋 seat=1
    my_seat = 0 if is_red else 1
    cache["my_seat"] = my_seat
    conn.execute("UPDATE games SET my_seat=? WHERE id=?", (my_seat, cache["game_id"]))
    conn.commit()
    color = "红" if my_seat == 0 else "黑"
    print(f"[chess] matchid={matchid} rain 是{color}棋 (seat={my_seat})")


def _handle_end(matchid: int, result: str, conn):
    """标记对局结束"""
    if matchid not in _game_cache:
        return
    cache = _game_cache[matchid]
    if cache["ended"]:
        return
    cache["ended"] = True
    conn.execute(
        "UPDATE games SET end_time=?, result=? WHERE id=?",
        (datetime.now().isoformat(), result, cache["game_id"])
    )
    conn.commit()
    print(f"[chess] GAME OVER matchid={matchid} result={result}")


def websocket_message(flow):
    msg: WebSocketMessage = flow.websocket.messages[-1]
    data = msg.content

    if msg.type != Opcode.BINARY:
        return

    parsed = _parse(data)
    if not parsed:
        return
    msg_type, obj = parsed

    conn = _get_conn()

    # --- 大厅/棋局请求（客户端发） ---
    if msg_type == MSG_LOBBY:
        lobby = obj.get("lobby_req_msg", {})
        chess = obj.get("chess_req_msg", {})
        matchid = chess.get("matchid") or lobby.get("matchid")

        # rain 颜色：chessbotinfo_req_msg 含 isRed（人机模式）
        bot_info = chess.get("chessbotinfo_req_msg", {})
        if bot_info and matchid:
            _handle_my_seat(matchid, bot_info.get("isRed", 1), conn)

        # FIXME: chessmove_req_msg 检测不可靠，可能拦截到对手的 seat
        # 暂时禁用，避免误判。人人对战需手动修正 my_seat
        # move_req = chess.get("chessmove_req_msg", {})
        # if move_req and matchid and matchid in _game_cache:
        #     if _game_cache[matchid]["my_seat"] is None:
        #         my_seat = move_req.get("seat")
        #         if my_seat is not None:
        #             _game_cache[matchid]["my_seat"] = my_seat
        #             conn.execute("UPDATE games SET my_seat=? WHERE id=?", (my_seat, _game_cache[matchid]["game_id"]))
        #             conn.commit()
        #             color = "红" if my_seat == 0 else "黑"
        #             print(f"[chess] matchid={matchid} rain 是{color}棋 (seat={my_seat})")

        # 认输
        surrender = chess.get("chesssurrender_req_msg")
        if surrender and matchid and matchid in _game_cache:
            seat = surrender.get("seat")
            cache = _game_cache[matchid]
            if cache["my_seat"] is not None:
                result = "负" if seat == cache["my_seat"] else "胜"
            else:
                result = f"seat{seat}认输"
            _handle_end(matchid, result, conn)
        return

    # --- 服务器回应 ---
    if msg_type == MSG_ACK:
        lobby_ack = obj.get("lobby_ack_msg", {})

        # 新局开始
        start = lobby_ack.get("startclientex_ack_msg")
        if start:
            matchid = start.get("matchid")
            if matchid:
                _handle_start(matchid, conn)
            return

        # 积分更新 = 对局结束（绝杀）
        score_ack = lobby_ack.get("pushuserscore_ack_msg")
        if score_ack:
            for matchid, cache in _game_cache.items():
                if not cache["ended"]:
                    # 最后一步是对方走的 → rain 输；最后一步是 rain 走的 → rain 胜
                    my_seat = cache.get("my_seat")
                    last_seat = cache.get("last_seat")
                    if my_seat is not None and last_seat is not None:
                        result = "负" if last_seat != my_seat else "胜"
                    else:
                        result = "unknown"
                    _handle_end(matchid, result, conn)
            return
        return

    # --- 落子消息 ---
    if msg_type != MSG_CHESS_MOVE:
        # 未知消息类型，打印用于协议分析
        import json as _json
        print(f"[chess] unknown msg_type=0x{msg_type:04X} payload={_json.dumps(obj, ensure_ascii=False)[:300]}")
        return

    ack = obj.get("chess_ack_msg", {})
    matchid = ack.get("matchid")
    move_msg = ack.get("chessmove_ack_msg", {})

    if not matchid or not move_msg:
        return

    from_x = move_msg.get("beginposx")
    from_y = move_msg.get("beginposy")
    to_x   = move_msg.get("endposx")
    to_y   = move_msg.get("endposy")
    seat   = move_msg.get("seat", 0)
    round_time = move_msg.get("roundtime", 0)
    is_local = move_msg.get("islocal", 0)

    if None in (from_x, from_y, to_x, to_y):
        return

    # islocal=1 表示回放/看棋谱，不记录
    if is_local:
        # 如果之前已经因为这个 matchid 创建了 game 记录（误判），清理掉
        if matchid in _game_cache:
            cache = _game_cache.pop(matchid)
            gid = cache["game_id"]
            if cache["move_no"] == 0:
                # 还没写入任何走法，直接删除 game 记录
                conn.execute("DELETE FROM games WHERE id=?", (gid,))
                conn.commit()
                print(f"[chess] REPLAY detected, removed empty game_id={gid} matchid={matchid}")
            else:
                # 已有走法写入，标记为 replay 忽略后续
                conn.execute("UPDATE games SET result='replay' WHERE id=?", (gid,))
                conn.commit()
                print(f"[chess] REPLAY detected mid-game, marked game_id={gid} as replay")
        else:
            print(f"[chess] REPLAY move skipped matchid={matchid}")
        return

    # 确保 game 记录存在（兼容旧数据/无 startclientex 的情况）
    if matchid not in _game_cache:
        row = conn.execute("SELECT id FROM games WHERE matchid=? ORDER BY id DESC LIMIT 1", (matchid,)).fetchone()
        if row:
            game_id = row[0]
            last_move = conn.execute(
                "SELECT fen, move_no FROM moves WHERE game_id=? ORDER BY move_no DESC LIMIT 1",
                (game_id,)
            ).fetchone()
            fen = last_move["fen"] if last_move else START_FEN
            move_no = last_move["move_no"] if last_move else 0
        else:
            game_id = conn.execute(
                "INSERT INTO games (matchid, start_time) VALUES (?, ?)",
                (matchid, datetime.now().isoformat())
            ).lastrowid
            conn.commit()
            fen = START_FEN
            move_no = 0
        _game_cache[matchid] = {"game_id": game_id, "fen": fen, "move_no": move_no, "my_seat": None, "ended": False}

    cache = _game_cache[matchid]
    if cache["ended"]:
        return

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
    cache["last_seat"] = seat

    uci = coords_to_uci(from_x, from_y, to_x, to_y)
    print(f"[chess] matchid={matchid} move#{move_no} seat={seat} {uci} | {new_fen[:30]}...")
