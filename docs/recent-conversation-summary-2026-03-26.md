# 近期对话摘要存档

日期：2026-03-26

## 一、当前共识

项目已经从“单一复盘页”升级为更清晰的产品定位：

- 核心唯一自研能力：**JJ 象棋自动采谱**
- 第一期目标：先做稳定的 **复盘展现底座**
- 后续创新方向：
  - 杀法/残局/战术题库训练
  - 定式/布局学习
  - 用户个人错误总结
  - 个性化强化训练闭环

同时明确：
- **不做对局中的实时提示**
- 所有后续训练能力，都必须建立在第一期展现系统基础上
- 不允许后面再起第二套棋盘展示体系

---

## 二、已经固化的关键判断

### 1. 基础复盘能力只是底座，不是最终创新点
“其他软件已经有的，我们都需要”，包括：
- 棋盘回放
- 走法列表
- 引擎评分
- 最佳着法
- 主变 PV
- 局势曲线
- 关键失误标记
- AI 复盘报告

这些能力需要在第一期补齐，但它们不是产品最终壁垒。

### 2. 真正创新点在 AI 驱动的训练产品
后续创新重点已经明确为：
- 常见杀法库与训练
- 题库自然语言调用
- 定式/布局学习
- 对用户个人棋谱错误进行总结归类
- 为用户生成个性化强化训练

### 3. 后续训练必须复用第一期展现底座
后面所有训练模式，本质上都只是更换数据源：
- 复盘模式：真实对局数据
- 题库模式：题目局面与标准答案
- 布局模式：定式主线与变化
- 强化模式：从用户错局中提炼出的训练局面

因此第一期必须做成统一展现系统，而不是一次性页面。

---

## 三、第一期范围共识

### 第一期只做 5 个模块

#### 1. 采谱模块
文件：`proxy/jj_addon.py`

职责：
- 监听 JJ WebSocket 落子消息
- 解析 `matchid`、坐标、走子方、用时
- 生成 FEN
- 写入 `games` / `moves`

#### 2. 复盘数据模块
当前承载：`server/db.py`

职责：
- 管理 `games`
- 管理 `moves`
- 管理 `analysis`
- 管理 `coach_reports`

关键边界：
- `analysis` 只存逐步引擎分析
- `coach_reports` 只存整局 AI 报告

#### 3. 引擎分析模块
文件：`server/engine.py`

职责：
- 输入局面 FEN
- 输出 `score / best_move / pv`

#### 4. AI 教练模块
文件：`server/llm.py`

职责：
- 输入 `moves + analysis`
- 输出整局中文报告

#### 5. 复盘前端模块
文件：`web/index.html`、`web/review.html`

职责：
- 对局列表
- 棋盘回放
- 引擎信息展示
- AI 报告展示
- 局势曲线展示

---

## 四、第一期接口协议共识

第一期统一采用 **REST + JSON**。

### 读取类接口
- `GET /api/games`
- `GET /api/games/{game_id}`
- `GET /api/games/{game_id}/analysis`
- `GET /api/games/{game_id}/coach-report`

### 动作类接口
- `POST /api/games/{game_id}/analysis`
- `POST /api/games/{game_id}/coach-report`

关键原则：
- `GET` 只读，不写库
- `POST` 负责动作触发
- 不允许再用读取接口顺手写分析结果
- 不允许再把 AI 报告写进 `analysis` 表

---

## 五、第一期统一展现系统共识

第一期已经明确不是单纯“复盘页”，而是后续训练系统的统一展现底座。

### 已定义的 7 个核心组件
1. `BoardViewer`
2. `MoveListViewer`
3. `EvalPanel`
4. `EvalChart`
5. `ExplanationPanel`
6. `PositionSummary`
7. `SessionShell`

### 已定义的 5 类统一展现协议对象
1. `Position`
2. `MoveItem`
3. `Evaluation`
4. `Explanation`
5. `SessionMeta`

这一层的意义是：
后面题库训练、布局学习、个性化强化，都只做数据映射，不重做展示层。

---

## 六、按 vibing coding cn 对照后的判断

### 当前已经明显对齐的点
- 先设计，后编码
- 核心边界逐渐清晰
- 胶水思维明显增强
- 决策开始沉淀到 docs/decisions
- 已明确后续训练复用第一期展现底座

### 当前仍需警惕的问题
- 设计已经很多，但代码还没同步收口
- 一期必须做/不做的边界还需要继续冻结
- 训练产品的数据资源与标签体系还没正式落方案
- `server/xiangqi.py` 仍需防止演化成自写规则引擎

### 当前总体判断
和之前相比，整体方向已经明显更符合 vibing coding cn，但下一步必须尽快从文档进入最小实现验证。

---

## 七、已新增或更新的文档

### 架构总览
- `docs/architecture.md`

### 已固化 ADR
- `docs/decisions/ADR-003-postgame-only.md`
- `docs/decisions/ADR-004-innovation-focus-training.md`
- `docs/decisions/ADR-005-phase1-modules-and-api.md`
- `docs/decisions/ADR-006-training-reuses-phase1-presentation.md`
- `docs/decisions/ADR-007-phase1-presentation-components.md`

---

## 八、下一步建议（对话结束时的共识）

最合理的下一步顺序是：

1. 先继续冻结第一期范围
2. 再开始最小代码实现验证
3. 代码改造顺序优先：
   - `server/db.py`
   - `server/main.py`
   - `web/review.html`

目的不是一下做很多功能，而是先把第一期底座真正跑起来。
