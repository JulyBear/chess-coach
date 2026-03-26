import os
import json
from anthropic import Anthropic

_client: Anthropic | None = None


def get_client(config: dict) -> Anthropic:
    global _client
    if _client is None:
        api_key = os.environ.get(config["llm"]["api_key_env"])
        _client = Anthropic(api_key=api_key)
    return _client


def analyze_game(config: dict, moves: list, analysis: list) -> str:
    """
    对完整对局进行AI教练分析。
    moves: 走法列表，每项含 move_no, seat, from_x, from_y, to_x, to_y, fen, round_time
    analysis: 引擎分析结果，每项含 move_no, score, best_move, pv
    返回：中文复盘报告字符串
    """
    # 找出关键失误：评分突变超过1分的节点
    blunders = []
    for i in range(1, len(analysis)):
        prev = analysis[i - 1]
        curr = analysis[i]
        delta = curr["score"] - prev["score"]
        seat = moves[i]["seat"] if i < len(moves) else 0
        is_blunder = (seat == 0 and delta < -1.0) or (seat == 1 and delta > 1.0)
        if is_blunder:
            blunders.append({
                "move_no": curr["move_no"],
                "seat": "红方" if seat == 0 else "黑方",
                "score_before": prev["score"],
                "score_after": curr["score"],
                "engine_best": prev["best_move"],
                "pv": prev["pv"],
                "fen": moves[i]["fen"] if i < len(moves) else "",
            })

    prompt = f"""你是一位专业的中国象棋教练，请对以下对局进行复盘分析。

对局共 {len(moves)} 步。引擎（Pikafish）发现以下关键失误节点（评分单位：兵）：

{json.dumps(blunders, ensure_ascii=False, indent=2)}

请完成：
1. 逐一解释每个失误的原因（用中文象棋术语，如「马后炮」「空心炮」等）
2. 说明引擎推荐走法的意图
3. 总结该棋手本局的主要问题（开局/中局/残局）
4. 给出针对性的训练建议

请用简洁易懂的语言，适合业余爱好者阅读。"""

    client = get_client(config)
    response = client.messages.create(
        model=config["llm"]["model"],
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text
