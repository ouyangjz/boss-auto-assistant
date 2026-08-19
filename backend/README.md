# FastAPI 本地测试服务

服务接收插件采集的原始岗位 JSON，调用本地 Coze Workflow 完成岗位匹配分析，将岗位、标签、结构化分析结果和完整 `coze_output` 事务化保存至 `data/jobs.db`，并向插件返回 Workflow 的 `match_score`。

数据库使用 SQLAlchemy，默认连接为 `sqlite:///data/jobs.db`。如需覆盖（例如以后切换 PostgreSQL），可在 `.env` 设置 `DATABASE_URL`。服务启动时只创建缺失的数据表，不会自动导入历史 JSON。

实时岗位分析会为每个岗位维护一条 `applications` 记录。匹配分达到当前
`MATCH_THRESHOLD`（默认 70）时状态为 `沟通`，否则为 `未投递`；已经由前端确认
为 `投递简历`、`面试阶段` 或 `入职阶段` 的记录不会被后续重新分析降级。高分岗位的
后台自我介绍 Workflow 成功返回后，首次生成的沟通语会写入 `communications`，后续
重复生成不会覆盖首次记录。

历史 JSON 使用独立脚本导入；脚本递归扫描 `data/`，保留原文件，并用内容哈希避免重复导入相同评估：

```powershell
conda run -n gluon1 python scripts/import_json_to_db.py
```

复制 `.env.example` 为 `.env` 后配置本地 Coze：

```env
COZE_BASE_URL=http://127.0.0.1:8080
COZE_WORKFLOW_ID=your-workflow-id
COZE_INTRODUCTION_WORKFLOW_ID=your-introduction-workflow-id
COZE_TOKEN=your-token
COZE_TIMEOUT_SECONDS=90
COZE_INTRODUCTION_TIMEOUT_SECONDS=90
COZE_TIMEOUT_FALLBACK_SCORE=50
```

`COZE_TIMEOUT_SECONDS` 是 FastAPI 等待 Coze Workflow 响应的最长秒数，默认
90 秒。Coze 超时会记录错误日志，并使用 `COZE_TIMEOUT_FALLBACK_SCORE`（默认
50）保存当前岗位、向插件返回分数，让插件跳过沟通并继续下一个岗位。保存的
`coze_output` 会包含 `fallback: true` 和 `fallback_reason: "COZE_TIMEOUT"`，便于
后续识别降级结果。修改 `.env` 后需要重启 FastAPI 服务。

## 岗位黑名单

服务会在调用 Coze 和保存岗位数据之前读取
`config/job_blacklist.json`。命中规则时返回原有响应结构：

```json
{
  "success": true,
  "match_score": 0
}
```

命中后不会调用 Coze、不会保存该岗位，并记录 `[BLACKLIST SKIP]` 日志。未命中
时继续原有流程，并以 `[COZE EVALUATE]` 标识 Coze 调用日志。配置文件缺失、编码
错误、JSON 错误或字段类型错误时，服务只记录 warning，禁用本次黑名单检查并
正常调用 Coze。

黑名单之前还会对请求中的非空 `job_id` 做数据库唯一性检查。`jobs` 表中已经存在
该 ID 时同样返回 0 分，不调用 Coze，也不新增评估或申请记录。

规则匹配只去除首尾空格并忽略英文大小写。后续手动增加规则时直接编辑 JSON，
例如：

```json
{
  "enabled": true,
  "job_name_exact": ["完整岗位名称"],
  "job_name_contains": ["低误杀的组合关键词"],
  "job_tag_contains": []
}
```

可通过 `.env` 中的 `JOB_BLACKLIST_CONFIG` 指定其他配置路径。配置会在每次评估前
重新读取，因此修改规则无需修改 Python 源码，也无需重启服务。

评估接口只向 Workflow 发送 `job_name`、`job_description` 和数组形式的 `job_tags`。Coze API 应兼容 `POST {COZE_BASE_URL}/v1/workflow/run`。

岗位匹配完成后的分支规则：

- `match_score < MATCH_THRESHOLD`：只返回原有评分响应。
- 分数达标但 `self_intro_context` 为空、为 `null` 或缺失：job-scanner-extension 仍可沟通，
  但服务不生成自我介绍。
- 分数达标且上下文非空：服务把任务加入 FastAPI `BackgroundTasks`，保持原有
  `/evaluate` 响应；后台向自我介绍 Workflow 原样传递 `job_name` 和
  `self_intro_context`，生成失败只记录日志。

自我介绍生成也提供独立路径：

```text
POST /api/v1/introductions/generate
```

该路径接收公司、HR、岗位、匹配分和非空的 `self_intro_context`，返回 `202` 与
`task_id`，随后在后台调用 Coze 并推送 chat-assistant-extension。`/jobs/evaluate` 不通过 HTTP
回调自身，而是复用该路径使用的同一个 introduction service，以避免同服务网络调用。

```json
{
  "company_name": "示例公司",
  "hr_name": "朱先生",
  "hr_title": "招聘经理",
  "job_name": "Python工程师",
  "match_score": 82,
  "self_intro_context": [
    {
      "target_requirements": ["Python后端开发"],
      "relevant_experiences": [],
      "matched_skills": ["Python", "FastAPI"],
      "highlight_points": []
    }
  ]
}
```

生成完成后通过同一 FastAPI 端口的 `ws://127.0.0.1:8000/ws/chat-assistant-extension` 推送。
未连接插件时消息保留在内存 pending 队列，插件重连后重推，收到 ACK 后删除。
服务重启会清空内存队列。

```powershell
conda activate gluon1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

打开 `http://127.0.0.1:8000/docs` 调试接口，或访问 `http://127.0.0.1:8000/health` 检查服务。

`POST /api/v1/chat-assistant-extension/test` 可以绕过岗位分析和自我介绍 Workflow，直接向
chat-assistant-extension 推送测试消息。扩展默认只回填；是否自动发送由插件弹窗中的本地
开关决定。请求示例见项目根 README 和 `chat-assistant-extension/README.md`。

运行测试：

```powershell
$env:PYTHONPATH = "."
pytest
```

接口测试示例：

```powershell
$body = @{
    job_id = "536be58482d10bd50nFy3ty0E1VR"
    job_name = "AI智能体开发"
    salary = "6-11K"
    experience = "1年以内"
    education = "大专"
    company_name = "示例公司"
    hr_name = "刘女士"
    hr_title = "经理"
    job_description = "职位描述`n1. 使用 AI 编程工具开发 Python 服务"
    job_tags = @("大模型算法", "Python", "SQL")
    source_url = "https://www.zhipin.com/job_detail/example.html"
} | ConvertTo-Json

Invoke-RestMethod -Method Post `
    -Uri "http://127.0.0.1:8000/api/v1/jobs/evaluate" `
    -ContentType "application/json" `
    -Body $body
```

海投接口使用同一请求体：

```text
POST /api/v1/jobs/bulk-evaluate
```

它按“数据库 `job_id` 唯一性 → 黑名单”的顺序检查；通过后保存岗位、固定 71 分
评估及按 `MATCH_THRESHOLD` 计算状态的申请记录，然后立即返回
`{"success": true, "match_score": 71}`。
该路径不调用岗位评估 Coze，也不会调度自我介绍 Workflow。重复或黑名单岗位返回 0 分。
