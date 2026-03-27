import json
import sqlite3
from datetime import datetime
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from .db import get_conn, init_db
from .engine import PikafishEngine
from .xiangqi import START_FEN
from . import llm

ROOT = Path(__file__).parent.parent
config = json.loads((ROOT / "config.json").read_text())

conn: sqlite3.Connection | None = None
engine: PikafishEngine | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global conn, engine
    db_path = ROOT / config["db"]["path"]
    conn = get_conn(str(db_path))
    init_db(conn)
    engine_path = ROOT / config["engine"]["path"]
    if engine_path.exists():
        engine = PikafishEngine(
            str(engine_path),
            depth=config["engine"]["depth"],
            threads=config["engine"]["threads"],
            hash_mb=config["engine"]["hash_mb"],
        )
    yield
    if engine:
        engine.close()
    if conn:
        conn.close()


app = FastAPI(title="Chess Coach", lifespan=lifespan)
app.mount("/web", StaticFiles(directory=str(ROOT / "web"), html=True), name="web")


def get_game_row(game_id: int):
    game = conn.execute("SELECT * FROM games WHERE id=?", (game_id,)).fetchone()
    if not game:
        raise HTTPException(404, "Game not found")
    return game


def get_game_moves(game_id: int):
    return conn.execute(
        "SELECT * FROM moves WHERE game_id=? ORDER BY move_no", (game_id,)
    ).fetchall()


def build_analysis_response(game_id: int, rows):
    items = [dict(r) for r in rows]
    move_rows = conn.execute(
        "SELECT move_no, fen FROM moves WHERE game_id=? ORDER BY move_no", (game_id,)
    ).fetchall()
    # FEN side-to-move is the side NOW to move AFTER the move was made.
    # Engine score is always from the perspective of the side to move in that FEN.
    # side='w' (red to move) → engine score = red's advantage → score_red = +score
    # side='b' (black to move) → engine score = black's advantage → score_red = -score
    move_meta = {
        row["move_no"]: {
            "fen_side": row["fen"].split()[1] if row["fen"] else "w",
        }
        for row in move_rows
    }

    prev_score_red = None
    for item in items:
        if item["move_no"] == 0:
            # Starting position: FEN has 'w' (red to move) → score_red = score
            item["score_red"] = item["score"]
            item["is_blunder"] = False
            prev_score_red = item["score_red"]
            continue

        meta = move_meta.get(item["move_no"], {"fen_side": "w"})
        fen_side = meta["fen_side"]
        # side='w' → red to move → score = red's advantage → score_red = score
        # side='b' → black to move → score = black's advantage → score_red = -score
        score_red = item["score"] if fen_side == "w" else -item["score"]
        item["score_red"] = score_red

        if prev_score_red is None:
            item["is_blunder"] = False
        else:
            delta = score_red - prev_score_red
            # Who just moved? The side that was to move in the PREVIOUS position.
            # Previous position had the opposite side: if current fen_side='w', red now moves,
            # so black just moved (mover_is_red=False). If fen_side='b', black now moves,
            # so red just moved (mover_is_red=True).
            mover_is_red = fen_side == "b"
            item["is_blunder"] = (mover_is_red and delta < -1.0) or ((not mover_is_red) and delta > 1.0)
        prev_score_red = score_red

    return items


@app.get("/api/games")
def list_games():
    rows = conn.execute(
        "SELECT g.id, g.matchid, g.start_time, g.result, g.my_seat, g.opening_tag, COUNT(m.id) as move_count "
        "FROM games g LEFT JOIN moves m ON m.game_id=g.id "
        "WHERE (g.result IS NULL OR g.result != 'replay') "
        "GROUP BY g.id ORDER BY g.start_time DESC"
    ).fetchall()
    return [{**dict(r)} for r in rows]


@app.get("/api/games/{game_id}")
def get_game(game_id: int):
    game = get_game_row(game_id)
    moves = get_game_moves(game_id)
    return {
        "game": dict(game),
        "moves": [dict(m) for m in moves],
    }


@app.post("/api/games/{game_id}/analysis")
def create_analysis(game_id: int):
    if not engine:
        raise HTTPException(503, "Engine not available")

    get_game_row(game_id)
    moves = get_game_moves(game_id)
    if not moves:
        raise HTTPException(404, "No moves found")

    start = engine.analyze(START_FEN)
    conn.execute(
        "INSERT INTO analysis (game_id, move_no, score, best_move, pv) VALUES (?,?,?,?,?) "
        "ON CONFLICT(game_id, move_no) DO UPDATE SET score=excluded.score, best_move=excluded.best_move, pv=excluded.pv",
        (game_id, 0, start["score"], start["best_move"], start["pv"]),
    )

    for m in moves:
        result = engine.analyze(m["fen"])
        conn.execute(
            "INSERT INTO analysis (game_id, move_no, score, best_move, pv) VALUES (?,?,?,?,?) "
            "ON CONFLICT(game_id, move_no) DO UPDATE SET score=excluded.score, best_move=excluded.best_move, pv=excluded.pv",
            (game_id, m["move_no"], result["score"], result["best_move"], result["pv"]),
        )

    conn.commit()
    return {
        "game_id": game_id,
        "status": "ok",
        "analyzed_moves": len(moves),
    }


@app.get("/api/games/{game_id}/analysis")
def get_analysis(game_id: int):
    get_game_row(game_id)
    rows = conn.execute(
        "SELECT * FROM analysis WHERE game_id=? ORDER BY move_no", (game_id,)
    ).fetchall()
    return build_analysis_response(game_id, rows)


@app.post("/api/games/{game_id}/coach-report")
def create_coach_report(game_id: int):
    get_game_row(game_id)
    moves = get_game_moves(game_id)
    analysis = conn.execute(
        "SELECT * FROM analysis WHERE game_id=? ORDER BY move_no", (game_id,)
    ).fetchall()
    if not moves or not analysis:
        raise HTTPException(400, "请先运行引擎分析")

    try:
        report = llm.analyze_game(config, [dict(m) for m in moves], [dict(a) for a in analysis])
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    created_at = datetime.utcnow().isoformat()
    cur = conn.execute(
        "INSERT INTO coach_reports (game_id, report, created_at) VALUES (?,?,?)",
        (game_id, report, created_at),
    )
    conn.commit()
    return {
        "game_id": game_id,
        "status": "ok",
        "report_id": cur.lastrowid,
    }


@app.get("/api/games/{game_id}/coach-report")
def get_coach_report(game_id: int):
    get_game_row(game_id)
    row = conn.execute(
        "SELECT * FROM coach_reports WHERE game_id=? ORDER BY id DESC LIMIT 1",
        (game_id,),
    ).fetchone()
    if not row:
        return {"report": None}
    return dict(row)
