# BOSS 直聘岗位筛选与自我介绍回填

项目包含两个 Chrome Manifest V3 插件和一个 FastAPI 后端服务：`job-scanner-extension`
采集岗位并按匹配分决定是否沟通；高分且存在 `self_intro_context` 时，服务在响应
岗位评估之后异步生成自我介绍，并通过 WebSocket 交给 `chat-assistant-extension` 在消息页回填。
`chat-assistant-extension` 默认只回填；用户也可以通过插件弹窗显式开启自动发送。

```text
Popup（开始/暂停/停止、状态展示）
  -> Content Script（DOM 遍历、串行采集、状态机）
  -> Background Service Worker（带 120 秒超时和取消能力的 HTTP 请求）
  -> FastAPI（SQLite 持久化、调用岗位匹配 Workflow）

高分且有上下文：

FastAPI BackgroundTask（自我介绍 Workflow）
  -> /ws/chat-assistant-extension
  -> Chat Assistant Extension（定位 HR、校验会话、回填，可选自动发送）
```

## 项目结构

```text
boss-job-dev/
├─ job-scanner-extension/
│  ├─ manifest.json
│  ├─ popup/                 # 用户控制与状态展示
│  ├─ background/            # FastAPI 网络通信
│  ├─ content/               # 状态机、采集、遍历、沟通
│  ├─ utils/                 # DOM、存储、日志工具
│  ├─ config/                # 常量和集中 selector 配置
│  ├─ icons/
│  └─ README.md              # 安装与 DOM Selector 适配指南
├─ backend/
│  ├─ app/
│  │  ├─ api/
│  │  ├─ schemas/
│  │  ├─ services/
│  │  ├─ core/
│  │  ├─ utils/
│  │  └─ main.py
│  ├─ data/
│  ├─ tests/
│  ├─ requirements.txt
│  ├─ .env.example
│  └─ README.md
├─ chat-assistant-extension/ # 消息页联系人定位与自我介绍回填
├─ .gitignore
└─ README.md
```

## 启动 FastAPI

```powershell
cd backend
conda activate gluon1
pip install -r requirements.txt
Copy-Item .env.example .env
Copy-Item config/job_whitelist.example.json config/job_whitelist.json
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

健康检查：`http://127.0.0.1:8000/health`；Swagger：`http://127.0.0.1:8000/docs`。

## 加载 Chrome 插件

在 Chrome 打开 `chrome://extensions`，开启开发者模式，点击“加载已解压的扩展程序”，选择 `job-scanner-extension`。随后打开 BOSS 岗位搜索列表并刷新页面，再点击扩展的“开始”。完整 selector 适配步骤见 [job-scanner-extension/README.md](job-scanner-extension/README.md)。

## 推荐验收顺序

1. 先访问 `/health`，再用 Swagger 提交一个岗位，确认 `backend/data/jobs.db` 出现对应数据且响应包含匹配分。
2. 加载扩展，在真实 BOSS 页面用 `window.__BOSS_PLUGIN_DEBUG__` 验证列表、详情和描述 selector。
3. 关闭“是否海投”，点击开始，确认逐个采集、保存、跳过，并根据页面结构滚动左侧容器或全局页面。
4. 确认沟通按钮和成功弹窗 selector 无误后，再小范围开启“是否海投”测试固定 71 分的“立即沟通 → 留在此页”流程。

在真实页面验证时应先使用一个确定低于 `MATCH_THRESHOLD` 的 Coze 测试结果，避免意外向招聘方发送消息，同时覆盖 DOM 采集、后台通信、数据库保存、去重、切换和滚动等核心能力。

插件等待 FastAPI 最多 120 秒；FastAPI 等待 Coze Workflow 默认最多 90 秒。
后端超时可通过 `backend/.env` 中的 `COZE_TIMEOUT_SECONDS` 调整，修改后需
重启 FastAPI；插件超时可在 `job-scanner-extension/config/constants.js` 中调整，修改后需在
Chrome 扩展管理页重新加载插件。

Coze Workflow 超时后，FastAPI 会记录错误日志，以默认 50 分保存带有降级标记的
岗位结果并正常响应插件。插件会将其视为匹配度不足，跳过沟通并继续处理下一岗位。
可通过 `COZE_TIMEOUT_FALLBACK_SCORE` 调整该默认分数。

## 第二阶段配置与测试

在 `backend/.env` 增加：

```env
COZE_INTRODUCTION_WORKFLOW_ID=your-introduction-workflow-id
COZE_INTRODUCTION_TIMEOUT_SECONDS=90
```

在 Chrome 扩展页加载 `chat-assistant-extension`，然后打开 BOSS 消息页。插件默认连接
`ws://127.0.0.1:8000/ws/chat-assistant-extension`。点击插件图标可切换“自动发送”，默认关闭；
开启后会在回填复核完成后等待 0.5～1 秒再发送。可调用测试接口单独验证回填：

```powershell
$body = @{
    company_name = "治粟科技"
    hr_name = "朱先生"
    hr_title = "招聘经理"
    job_name = "python开发工程师"
    greeting_message = "你好，这是插件2 WebSocket 自动回填测试消息。"
} | ConvertTo-Json

Invoke-RestMethod -Method Post `
    -Uri "http://127.0.0.1:8000/api/v1/chat-assistant-extension/test" `
    -ContentType "application/json" `
    -Body $body
```

完整安装和定位规则见 [chat-assistant-extension/README.md](chat-assistant-extension/README.md)。

自我介绍 Coze 链路还可以通过独立接口触发：

```text
POST http://127.0.0.1:8000/api/v1/introductions/generate
```

`/jobs/evaluate` 仍保持原有岗位评估响应，只在分数达标且
`self_intro_context` 非空时异步调用同一个 introduction service。

两个岗位入口都会先按非空 `job_id` 查询数据库，再检查黑名单。重复岗位或黑名单
岗位统一返回 0 分且不会继续处理。岗位筛选扩展弹窗中的“是否海投”默认关闭：关闭时
请求 `POST /api/v1/jobs/evaluate`；开启时请求 `POST /api/v1/jobs/bulk-evaluate`。
海投接口随后还会检查 `backend/config/job_whitelist.json`，只有命中白名单才保存岗位
及固定 71 分的评估结果；未命中返回 0 分且不保存，全程不调用任何 Coze Workflow。

插件使用可中断等待，避免测试过程中连续切换导致目标页面重载。间隔可在 `job-scanner-extension/config/constants.js` 中调整。
