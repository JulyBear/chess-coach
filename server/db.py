import sqlite3
import json
from pathlib import Path


def get_conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS games (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            matchid   INTEGER UNIQUE,
            start_time TEXT,
            result    TEXT
        );

        CREATE TABLE IF NOT EXISTS moves (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id   INTEGER REFERENCES games(id),
            move_no   INTEGER,
            seat      INTEGER,  -- 0=red, 1=black
            from_x    INTEGER,
            from_y    INTEGER,
            to_x      INTEGER,
            to_y      INTEGER,
            fen       TEXT,
            round_time INTEGER
        );

        CREATE TABLE IF NOT EXISTS analysis (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id    INTEGER REFERENCES games(id),
            move_no    INTEGER,
            score      REAL,
            best_move  TEXT,
            pv         TEXT,
            llm_comment TEXT
        );
    """)
    conn.commit()
