# 近期对话摘要存档

日期：2026-03-27

## 一、本次会话关键发现

### 1. JJ 象棋 WebSocket 服务器地址
- 域名：`wxminigame.srv.jjmatch.cn:443`
- 微信小程序走系统 HTTP 代理（需先开 macOS 系统代理）
- 历史确认：之前使用 Charles（端口8888）分析协议，Charles 用于协议分析，mitmproxy 用于采谱，两者职责不同

### 2. JJ 象棋消息类型汇总

| msg_type | 方向 | 用途 |
|----------|------|------|
| `0x03F3` | 双向 | 落子消息（已实现采谱）|
| `0x14801` | 客户端→服务器 | 大厅请求（`lobby_req_msg`）、棋局请求（`chess_req_msg`）|
| `0x0000` | 服务器→客户端 | 大厅回应（`lobby_ack_msg`）、HTTP回应、ECA服务回应 |
| `0x0001` | 双向 | 心跳/ping |
| `0x210020A` | Bilibili WebSocket | 与象棋无关，忽略 |
| `0x310020A` | Bilibili WebSocket | 与象棋无关，忽略 |

### 3. 棋局结束消息

**认输消息（客户端发送）：**
```json
{"chess_req_msg": {"matchid": 124455923, "chesssurrender_req_msg": {"seat": 1}}}
```
- msg_type: `0x14801`
- `seat`: 认输方（0=红, 1=黑）

**认输后服务器推送（结束标志）：**
```json
{"lobby_ack_msg": {"pushuserscore_ack_msg": {"score": 0, "masterscore": 0}}}
```
- msg_type: `0x0000`
- 紧随 surrender 之后出现
- 还有 `pushusergrow_ack_msg`、`pushusergrow64_ack_msg` 等积分/成长值更新

**待确认：** 服务器是否发送专门的游戏结束 ack（如 `chessgameover_ack_msg`）——在 surrender 后有3条未解码的 WebSocket 消息，正在追踪中。

### 4. 对局入场消息（对局开始标志）
```json
{"lobby_ack_msg": {"startclientex_ack_msg": {"tourneyid": 251796, "matchid": 124455923, "gameid": 1011, "productid": 502235, "ticket": "..."}}}
```
- 这是对局开始的信号，可用来区分新对局
- `matchid` 可能被复用（同一 matchid 出现在不同时间的对局）

### 5. 用户身份确认
- rain = seat=0（红棋）
- 对手代号暂定 player_b（seat=1，黑棋）
- 注：某些局中 rain 也会持黑，需按对局实际 seat 判断

---

## 二、当前已知 Bug

### matchid 复用问题
- 同一 matchid 的不同对局被追加到同一条 game 记录
- game 2（matchid=231653905）从233步增长到了300+步
- **修复方向：** 监听 `startclientex_ack_msg`，每次收到时创建新 game 记录，不再依赖 matchid 唯一性

---

## 三、采谱系统运行方式（已验证）

1. macOS 系统代理设置为 `127.0.0.1:8080`
2. 启动 mitmproxy：
   ```bash
   cd /projects/chess-coach
   PYTHONUNBUFFERED=1 /opt/homebrew/Caskroom/miniforge/base/bin/mitmdump -s proxy/jj_addon.py --listen-port 8080
   ```
3. 微信小程序打开 JJ 象棋，流量自动经过代理
4. 落子数据实时写入 `chess.db`

---

## 四、下一步待办

1. **确认棋局结束的完整消息**：再打一局，抓取 surrender/gameover 的服务器 ack
2. **修复 matchid 复用 bug**：监听 `startclientex_ack_msg` 创建新对局
3. **在 games 表增加字段**：`result`（胜/负/和）、`red_player`、`black_player`
4. **继续推进第一期底座**：`server/db.py` → `server/main.py` → `web/review.html`
