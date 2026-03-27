"""
象棋坐标/FEN 工具

JJ象棋坐标系：
  x: 0-8（列，左到右）
  y: 0-9（行，y=0=红方底线，y=9=黑方顶线）
  — 即从红方视角向前数，与 Pikafish UCI rank 相同

UCI/Pikafish rank 坐标系：
  rank 0 = 红方底线，rank 9 = 黑方顶线
  rank == JJ y（两者一致）
  file 0-8 对应 x=0-8

FEN 字符串排列（_fen_to_board 中的 board 索引）：
  board[0] = FEN 第一段  = 黑方顶线（Pikafish rank 9 / JJ y=9）
  board[9] = FEN 第十段  = 红方底线（Pikafish rank 0 / JJ y=0）
  因此：board 索引 = 9 - JJ_y，即 board[9-y][x] 才是正确映射。
"""

# 初始局面 FEN
START_FEN = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"

# 棋子代码映射（FEN字符）
# 红方大写，黑方小写
_PIECE_MAP = {
    # 红方
    "R": "车", "H": "马", "E": "相", "A": "仕", "K": "帅",
    "C": "炮", "P": "兵",
    # 黑方
    "r": "车", "h": "马", "e": "象", "a": "士", "k": "将",
    "c": "炮", "p": "卒",
}


def coords_to_uci(from_x: int, from_y: int, to_x: int, to_y: int) -> str:
    """JJ坐标 → 走法标识字符串（仅用于日志展示，不用于引擎输入）。
    注：JJ y=0 对应黑方顶线，而 Pikafish UCI rank=0 是红方底线，两者相反。
    引擎分析始终使用 FEN 字符串而非此格式。
    """
    col_from = chr(ord('a') + from_x)
    col_to = chr(ord('a') + to_x)
    return f"{col_from}{from_y}{col_to}{to_y}"


def apply_move(fen: str, from_x: int, from_y: int, to_x: int, to_y: int) -> str:
    """在给定FEN上执行一步走法，返回新FEN。
    JJ y=0=红方底线，Pikafish rank 0=红方底线，两者一致。
    _fen_to_board 中 board[0]=黑方顶线（rank 9），board[9]=红方底线（rank 0），
    所以正确映射是 board[9-y][x]。
    """
    board = _fen_to_board(fen)
    piece = board[9 - from_y][from_x]
    board[9 - from_y][from_x] = None
    board[9 - to_y][to_x] = piece

    # 切换走棋方
    parts = fen.split()
    turn = "b" if parts[1] == "w" else "w"
    move_no = int(parts[5])
    if turn == "w":
        move_no += 1

    return _board_to_fen(board, turn, move_no)


def _fen_to_board(fen: str) -> list:
    """FEN棋盘部分 → 10x9 二维列表，board[y][x]"""
    board = [[None] * 9 for _ in range(10)]
    rank_strs = fen.split()[0].split("/")
    # FEN rank 0 = y=0（黑方底线）
    for y, rank_str in enumerate(rank_strs):
        x = 0
        for ch in rank_str:
            if ch.isdigit():
                x += int(ch)
            else:
                board[y][x] = ch
                x += 1
    return board


def _board_to_fen(board: list, turn: str, move_no: int) -> str:
    ranks = []
    for y in range(10):
        empty = 0
        rank_str = ""
        for x in range(9):
            piece = board[y][x]
            if piece is None:
                empty += 1
            else:
                if empty:
                    rank_str += str(empty)
                    empty = 0
                rank_str += piece
        if empty:
            rank_str += str(empty)
        ranks.append(rank_str)
    board_fen = "/".join(ranks)
    return f"{board_fen} {turn} - - 0 {move_no}"
