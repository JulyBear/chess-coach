import sqlite3


def get_conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS games (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            matchid     INTEGER,
            start_time  TEXT,
            end_time    TEXT,
            result      TEXT,
            my_seat     INTEGER,
            opening_tag TEXT
        );

        CREATE TABLE IF NOT EXISTS moves (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id    INTEGER REFERENCES games(id),
            move_no    INTEGER,
            seat       INTEGER,  -- JJ座位号，哪个seat=红方因局而异（先走的seat=红）
            from_x     INTEGER,
            from_y     INTEGER,
            to_x       INTEGER,
            to_y       INTEGER,
            fen        TEXT,
            round_time INTEGER
        );

        CREATE TABLE IF NOT EXISTS analysis (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id   INTEGER REFERENCES games(id),
            move_no   INTEGER,
            score     REAL,
            best_move TEXT,
            pv        TEXT,
            UNIQUE(game_id, move_no)
        );

        CREATE TABLE IF NOT EXISTS coach_reports (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id    INTEGER REFERENCES games(id),
            report     TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
    """)

    columns = {row[1] for row in conn.execute("PRAGMA table_info(games)").fetchall()}
    for col, typedef in [("opening_tag", "TEXT"), ("end_time", "TEXT"), ("my_seat", "INTEGER")]:
        if col not in columns:
            conn.execute(f"ALTER TABLE games ADD COLUMN {col} {typedef}")

    conn.execute(
        "DELETE FROM analysis WHERE id NOT IN ("
        "SELECT MAX(id) FROM analysis GROUP BY game_id, move_no"
        ")"
    )

    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_analysis_game_move ON analysis(game_id, move_no)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_moves_game_move_no ON moves(game_id, move_no)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_coach_reports_game_id_id ON coach_reports(game_id, id DESC)"
    )
    conn.commit()
