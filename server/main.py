import json
import sqlite3
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

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
    conn = get_conn(config["db"]["path"])
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


@app.get("/api/games")
def list_games():
    rows = conn.execute(
        "SELECT g.id, g.matchid, g.start_time, g.result, COUNT(m.id) as move_count "
        "FROM games g LEFT JOIN moves m ON m.game_id=g.id "
        "GROUP BY g.id ORDER BY g.start_time DESC"
    ).fetchall()
    return [{**dict(r)} for r in rows]


@app.get("/api/games/{game_id}")
def get_game(game_id: int):
    game = conn.execute("SELECT * FROM games WHERE id=?", (game_id,)).fetchone()
    if not game:
        raise HTTPException(404, "Game not found")
    moves = conn.execute(
        "SELECT * FROM moves WHERE game_id=? ORDER BY move_no", (game_id,)
    ).fetchall()
    return {
        "game": dict(game),
        "moves": [dict(m) for m in moves],
    }


@app.get("/api/games/{game_id}/analyze")
def analyze_game(game_id: int):
    if not engine:
        raise HTTPException(503, "Engine not available")
    moves = conn.execute(
        "SELECT * FROM moves WHERE game_id=? ORDER BY move_no", (game_id,)
    ).fetchall()
    if not moves:
        raise HTTPException(404, "No moves found")

    results = []
    # 分析初始局面
    start = engine.analyze(START_FEN)
    results.append({"move_no": 0, **start})

    for m in moves:
        result = engine.analyze(m["fen"])
        row = {"move_no": m["move_no"], **result}
        results.append(row)
        # 存入analysis表（upsert）
        conn.execute(
            "INSERT INTO analysis (game_id, move_no, score, best_move, pv) "
            "VALUES (?,?,?,?,?) ON CONFLICT DO NOTHING",
            (game_id, m["move_no"], result["score"], result["best_move"], result["pv"])
        )
    conn.commit()
    return results


@app.get("/api/games/{game_id}/analysis")
def get_analysis(game_id: int):
    rows = conn.execute(
        "SELECT * FROM analysis WHERE game_id=? ORDER BY move_no", (game_id,)
    ).fetchall()
    return [dict(r) for r in rows]


@app.post("/api/games/{game_id}/coach")
def coach_game(game_id: int):
    moves = conn.execute(
        "SELECT * FROM moves WHERE game_id=? ORDER BY move_no", (game_id,)
    ).fetchall()
    analysis = conn.execute(
        "SELECT * FROM analysis WHERE game_id=? ORDER BY move_no", (game_id,)
    ).fetchall()
    if not moves or not analysis:
        raise HTTPException(400, "请先运行引擎分析")

    report = llm.analyze_game(config, [dict(m) for m in moves], [dict(a) for a in analysis])

    # 把报告存到analysis表第一行
    conn.execute(
        "UPDATE analysis SET llm_comment=? WHERE game_id=? AND move_no=1",
        (report, game_id)
    )
    conn.commit()
    return {"report": report}
