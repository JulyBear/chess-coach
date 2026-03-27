# ADR-007：第一期统一展现系统采用 7 个核心组件与统一展现协议

## 状态
已采纳

## 背景
为了保证后续题库训练、布局学习、个性化强化都建立在第一期展现系统之上，第一期不能只按单页面功能堆叠，而需要先定义统一展现组件与统一数据协议。

## 决策
第一期统一展现系统由 7 个核心组件组成：
1. BoardViewer
2. MoveListViewer
3. EvalPanel
4. EvalChart
5. ExplanationPanel
6. PositionSummary
7. SessionShell

同时前端内部统一收口到 5 类核心协议对象：
- Position
- MoveItem
- Evaluation
- Explanation
- SessionMeta

## 原因
- 后续不同学习模式只需更换数据源
- 避免每个模式各自发明棋盘与讲解协议
- 降低前端长期复杂度
- 保证训练系统天然继承复盘系统能力

## 放弃的方案
- 把 `web/review.html` 当作一次性页面继续堆逻辑
- 后续题库、布局、强化训练分别再建独立展示层
- 页面直接耦合 games/analysis 数据表结构，不做统一协议

## 影响
- 第一期前端需要按组件职责拆状态与函数。
- 后续接口设计要尽量围绕统一展现协议演进。
- 后续新增训练模式时，优先做数据映射，不重做展现层。
