# 象棋教练 Chess Coach

自动采集 JJ象棋（微信小程序）对局，结合 Pikafish 引擎分析 + Claude AI 生成复盘报告。

## 功能

- **自动采谱**：通过 mitmproxy 拦截 JJ象棋 WebSocket 流量，自动记录每一步落子
- **引擎分析**：调用 Pikafish UCI 引擎，逐步评分，标注关键失误
- **局势曲线**：可视化每步评分变化，点击曲线跳转对应局面
- **主变演示**：点击「▶ 演示」按钮，在棋盘上逐步展示引擎推荐走法
- **AI复盘报告**：调用 Claude 生成结构化复盘，包括开局识别、失误分析、训练建议
- **菜单栏 App**：状态栏一键启动/停止所有服务，自动管理系统代理

## 项目结构

```
chess-coach/
  proxy/jj_addon.py     # mitmproxy addon，拦截JJ象棋WebSocket
  server/
    main.py             # FastAPI 后端，提供 /api/games 等接口
    engine.py           # Pikafish UCI 引擎封装
    llm.py              # Claude AI 复盘分析
    db.py               # SQLite schema
    xiangqi.py          # FEN 操作工具
  web/
    index.html          # 对局列表
    review.html         # 复盘页（棋盘回放 + 分析 + 主变演示）
  tray.py               # macOS 菜单栏 App
  config.example.json   # 配置模板
```

## 安装

### 1. 依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

mitmproxy 需要单独安装（建议用 conda/miniforge）：
```bash
conda install mitmproxy
```

### 2. 配置

```bash
cp config.example.json config.json
```

编辑 `config.json`，填入：
- `llm.api_key`：Claude API Key
- `llm.base_url`：API 地址（默认 `https://api.anthropic.com`）
- `engine.path`：Pikafish 引擎二进制路径

### 3. 安装 mitmproxy CA 证书

首次运行 mitmproxy 后，访问 `http://mitm.it` 安装并信任 CA 证书，否则 HTTPS 会报错。

### 4. 启动

**方式一：菜单栏 App（推荐）**
```bash
source .venv/bin/activate
python tray.py
```
状态栏出现 ♟ 图标，点击「启动监控」即可。启动时自动设置系统代理，停止时自动清除。

**方式二：手动启动**
```bash
# 终端1：启动代理
mitmdump -s proxy/jj_addon.py --listen-port 8080

# 终端2：启动后端
source .venv/bin/activate
NO_PROXY='*' uvicorn server.main:app --host 127.0.0.1 --port 8888
```

手动将系统 HTTP/HTTPS 代理设为 `127.0.0.1:8080`。

## 使用

1. 启动监控后，正常打开微信 → JJ象棋小程序下棋
2. 对局结束后访问 `http://127.0.0.1:8888/web/index.html` 查看对局列表
3. 点击对局进入复盘页
4. 点击「生成引擎分析」等待 Pikafish 逐步分析
5. 点击「生成复盘报告」获取 AI 教练点评

## 技术说明

### 坐标系
- JJ 坐标：`x=0-8`（左→右），`y=0`=红方底线，`y=9`=黑方顶线
- FEN 映射：`board[9-y][x]`

### 引擎评分
- Pikafish 输出分数从当前走棋方视角
- 归一化为红方视角：FEN side=`w` → `score_red = +score`；side=`b` → `score_red = -score`

### 数据库
```sql
games(id, matchid, start_time, end_time, result, my_seat)
moves(game_id, move_no, seat, from_x, from_y, to_x, to_y, fen, round_time)
analysis(game_id, move_no, score, best_move, pv)
coach_reports(game_id, report, created_at)
```
