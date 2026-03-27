import os
import json
from anthropic import Anthropic, APIError

_client: Anthropic | None = None


def get_client(config: dict) -> Anthropic:
    global _client
    if _client is None:
        api_key = config["llm"].get("api_key") or os.environ.get(config["llm"].get("api_key_env", ""))
        if not api_key:
            raise RuntimeError("Missing LLM api_key in config")
        base_url = config["llm"].get("base_url")
        _client = Anthropic(api_key=api_key, timeout=120.0, **(({"base_url": base_url}) if base_url else {}))
    return _client


def analyze_game(config: dict, moves: list, analysis: list) -> str:
    """
    对完整对局进行AI教练分析。
    moves: 走法列表，每项含 move_no, seat, from_x, from_y, to_x, to_y, fen, round_time
    analysis: 引擎分析结果，每项含 move_no, score, best_move, pv
    返回：中文复盘报告字符串
    """
    # 前15步走法序列，用于开局识别
    opening_moves = [
        f"{m['move_no']}.{'红' if m['seat']==0 else '黑'} ({m['from_x']},{m['from_y']})->({m['to_x']},{m['to_y']})"
        for m in moves[:15]
    ]

    # 找出关键失误：按红方视角评分突变超过1兵的节点
    blunders = []
    prev_score_red = analysis[0].get("score_red", analysis[0]["score"]) if analysis else None
    for i in range(1, len(analysis)):
        curr = analysis[i]
        score_red = curr.get("score_red", curr["score"])
        delta = score_red - prev_score_red
        fen_side = moves[i - 1]["fen"].split()[1] if i - 1 < len(moves) and moves[i - 1].get("fen") else "b"
        mover_is_red = fen_side == "b"
        is_blunder = (mover_is_red and delta < -1.0) or ((not mover_is_red) and delta > 1.0)
        if is_blunder:
            blunders.append({
                "move_no": curr["move_no"],
                "seat": "红方" if mover_is_red else "黑方",
                "score_before": round(prev_score_red, 2),
                "score_after": round(score_red, 2),
                "engine_best": analysis[i - 1]["best_move"],
                "pv": analysis[i - 1]["pv"],
                "fen": moves[i - 1]["fen"] if i - 1 < len(moves) else "",
            })
        prev_score_red = score_red

    prompt = f"""你是一位专业的中国象棋教练，请对以下对局进行系统复盘分析。

## 基本信息
- 对局共 {len(moves)} 步
- 引擎：Pikafish（评分单位：兵，正值红方优势，负值黑方优势）

## 前15步走法（坐标系：x=0-8左→右，y=0红方底线，y=9黑方顶线）
{chr(10).join(opening_moves)}

## 引擎发现的关键失误（评分突变超过1兵）
{json.dumps(blunders, ensure_ascii=False, indent=2)}

请按以下结构输出复盘报告：

### 一、开局识别
- 判断本局属于哪种开局体系（如当头炮、顺炮、列炮、飞象局、仙人指路等）
- 指出大约在第几步脱离了常见定式，脱谱后局面的优劣

### 二、关键失误分析
- 逐一分析每个失误节点，说明当时局面特征和错误原因
- 引擎推荐走法的意图是什么
- 尽量使用中文象棋术语（如「马后炮」「空心炮」「铁门栓」「双车错」等）

### 三、全局总结
- 本局双方各自的问题出在哪个阶段（开局/中局/残局）
- 优势是如何建立或丢失的

### 四、训练建议
- 针对本局暴露的具体问题，给出2-3条可操作的练习方向
- 推荐重点研究的棋型或战术主题

请用简洁易懂的语言，适合业余爱好者阅读。"""

    client = get_client(config)
    try:
        response = client.messages.create(
            model=config["llm"]["model"],
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
    except APIError as exc:
        raise RuntimeError(f"LLM request failed: {exc}") from exc
    return response.content[0].text
