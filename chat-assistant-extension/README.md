# Plugin Two：BOSS 自我介绍回填助手

插件通过 WebSocket 接收 FastAPI 生成的 `introduction_ready` 任务，只在
`https://www.zhipin.com/web/geek/chat*` 页面定位联系人、切换聊天并回填消息。

点击浏览器工具栏中的插件图标，可以切换“自动发送”：

- 默认关闭：只回填输入框，由用户检查后手动发送。
- 开启：回填并验证成功后随机等待 0.5～1 秒，再次核对聊天对象和草稿内容，
  然后点击右下角文本严格为“发送”的按钮。

插件不会使用 Enter 发送；联系人、聊天对象、草稿或发送按钮任一校验失败都会取消发送。

## 安装

1. 打开 `chrome://extensions/`。
2. 开启“开发者模式”。
3. 点击“加载已解压的扩展程序”。
4. 选择本项目的 `plugin-two` 目录。
5. 打开并刷新 BOSS 消息页面。
6. 点击插件图标，根据需要选择是否自动发送；首次安装默认为“否”。

后台默认连接 `ws://127.0.0.1:8000/ws/plugin-two`。端口变化时同步修改
`config.js` 的 `websocketUrl`。

如果聊天页因插件重载或 SPA 导航而没有静态注入 content script，后台会在首次
发送任务失败时自动注入 `config.js` 和 `content.js`，然后重试同一任务。并发任务
会复用同一次注入，content script 也会跳过重复监听器注册。

## 联系人定位与防串线

- 对联系人行的完整 `textContent` 做空白标准化。
- 姓名匹配 +5、公司匹配 +3、职位匹配 +2。
- 必须匹配姓名，并至少匹配公司或职位；最高分仍有多个候选人时不点击。
- 最多滚动联系人虚拟列表 15 次，并结合 MutationObserver 在约 30 秒内等待新联系人出现。
- 点击后从右侧顶部重新校验 HR 姓名和公司，校验通过才允许写入。
- 支持 `textarea`、普通输入框和 `contenteditable`，写入后触发 `input`、`change` 并做稳定性验证。
- 自动发送开启时，仅点击右侧底部文本严格等于“发送”的可用按钮；点击前会再次确认
  HR、公司和草稿内容，发送后验证输入框已清空。
- `task_id` 已成功填写后保存在 `chrome.storage.local`，WebSocket 重连不会重复填写。

## 独立测试

先启动 FastAPI，在 BOSS 消息页打开目标联系人所在列表，然后执行：

```powershell
$body = @{
    company_name = "治粟科技"
    hr_name = "朱先生"
    hr_title = "招聘经理"
    job_name = "python开发工程师"
    greeting_message = "你好，这是插件2 WebSocket 自动回填测试消息。"
} | ConvertTo-Json

Invoke-RestMethod -Method Post `
    -Uri "http://127.0.0.1:8000/api/v1/plugin-two/test" `
    -ContentType "application/json" `
    -Body $body
```

扩展 Service Worker 控制台应出现 `[PluginTwo][WS] connected`，页面控制台应出现
联系人扫描、右侧校验及回填日志。分别测试开关关闭和开启两种模式。
