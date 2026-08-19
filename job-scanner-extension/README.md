# Plugin One

Manifest V3 Chrome 扩展。Popup 只控制任务；Content Script 串行遍历并采集 DOM；Background Service Worker 负责访问本地 FastAPI。

插件等待 FastAPI 响应的默认上限是 150 秒，以覆盖通常耗时 60～90 秒的 Coze
工作流，并为 FastAPI 返回结果预留余量。可在 `config/constants.js` 的
`requestTimeoutMs` 中调整；修改后需在 Chrome 扩展管理页重新加载插件。

## 加载

1. 启动 `local-server`。
2. 打开 `chrome://extensions`，开启“开发者模式”。
3. 选择“加载已解压的扩展程序”，选择本目录 `plugin-one`。
4. 打开或刷新 `https://www.zhipin.com/web/geek/jobs?...`。
5. 打开扩展 Popup，点击“开始”。

暂停会在当前岗位操作安全结束后生效；停止会取消等待器和当前循环，但不会清除已经处理的岗位 ID。若要重新测试所有岗位，可在扩展详情页清除扩展存储。

Popup 的“清除当前岗位信息”会停止并等待当前循环退出，清空扫描计数、匹配计数及 `processedJobs` 去重历史，并把列表或页面滚动回顶部。状态恢复为 `IDLE` 后，再次点击“开始”会从第一个岗位重新处理。

为避免岗位切换过快导致 SPA 重载，插件默认在首次点击前等待 1.8～3 秒，后续两次岗位点击至少间隔 5～8 秒，并在详情标题更新后额外等待 0.5～1 秒让描述和 HR 区域稳定。所有等待均可被“停止”中断；具体数值集中在 `config/constants.js` 中。

岗位采集会优先使用卡片中的薪资、地点、经验和学历，并以详情头部补全；技能标签会排除经验、学历和薪资。职位描述读取渲染后的可见文本，再裁掉样式、隐藏干扰词、招聘者卡片、工作地址及页面操作文字。

HR 文本 fallback 支持“刚刚活跃、今日活跃、在线”以及“3日内活跃、2周内活跃、4月内活跃”等可变时间格式。活动状态格式变化不会再导致 `hr_name`、`hr_title` 为空或招聘者卡片混入职位描述。

薪资中的私有区字体字符会按 `constants.js` 的 `salaryPrivateUseStart` 与 `salaryPrivateUseDigits` 转回普通数字。描述标题之后、正文之前连续出现的短技术词会自动移动到 `job_tags`，不会继续混在 `job_description` 中。若网站将来更换字体映射，插件会把未知私有区字符显示为 `?` 并记录 `SALARY_PRIVATE_USE_CHAR_UNKNOWN`，避免静默保存乱码。

沟通成功弹窗会先按“已向BOSS发送消息”文本节点及“留在此页/继续沟通”的公共祖先确认容器，不再要求弹窗具有特定 class。插件优先点击“留在此页”；按钮找不到或点击无效时改点弹窗内部具有关闭语义的右上角“×”。只有确认弹窗关闭后才继续，否则任务暂停，避免点击遮罩层下的岗位。

识别到沟通成功弹窗后，插件默认随机等待 1～2 秒再点击关闭控件。时间由 `modalDismissDelayMinMs` 和 `modalDismissDelayMaxMs` 控制，该等待可被“停止”立即取消。

## DOM Selector 适配指南

截图只能说明元素位置和文本，不能确定真实 class 或 DOM 层级。因此 [selectors.js](config/selectors.js) 为每类元素提供了多个候选 selector；命中顺序从数组前到后。BOSS 页面改版后，只需优先修改这个文件。

需要在真实页面重点确认：

- `jobList`：左侧岗位卡片的共同根节点；它可以只是普通容器，不要求自身可滚动。
- 滚动容器由 `findScrollContainer()` 自动识别；若列表及其祖先均不可独立滚动，会使用 `document.scrollingElement` 进行全局页面滚动。
- `jobCard`、`cardLink`：卡片根节点与含岗位详情 URL/`jobId` 的链接。
- `detailRoot`：整个右侧详情容器。
- `jobTitle`、`salary`、`location`、`experience`、`education`。
- `companyName`、`hrName`、`hrTitle`。
- `jobDescription`：应覆盖“职位描述/岗位职责/任职要求”的完整文本节点。
- `jobTags`。
- `communicateButton`：右侧详情内部的“立即沟通”。
- `successModal`：内容包含“已向BOSS发送消息”的弹窗根节点。
- `stayHereButton`：上述弹窗内部的“留在此页”。

在 BOSS 页面按 F12，先用元素选择器选中目标节点，再在 Console 顶部的 JavaScript context 下拉框选择本扩展的 Content Script 执行上下文，然后运行：

```js
window.__BOSS_PLUGIN_DEBUG__.printSelectors()
window.__BOSS_PLUGIN_DEBUG__.findJobList()
window.__BOSS_PLUGIN_DEBUG__.findScrollContainer()
window.__BOSS_PLUGIN_DEBUG__.getVisibleJobs()
window.__BOSS_PLUGIN_DEBUG__.extractCurrentJob()
window.__BOSS_PLUGIN_DEBUG__.findCommunicateButton()
window.__BOSS_PLUGIN_DEBUG__.findCommunicationModal()
```

也可以对 DevTools 当前选中的 `$0` 检查关键属性：

```js
({
  tag: $0.tagName,
  className: $0.className,
  id: $0.id,
  data: { ...$0.dataset },
  href: $0.href,
  role: $0.getAttribute("role"),
  parent: $0.parentElement?.className
})
```

把确认稳定且能唯一命中的 selector 放到对应数组首位。避免依赖动态哈希 class、`nth-child` 或屏幕坐标。`DEBUG_SELECTORS` 的等价配置是 `constants.js` 中的 `debugSelectors: true`，命中元素会输出到 Console。

如果目标页面不允许打开 DevTools，插件仍会在 selector 失败后，仅在右侧详情根节点内根据“职位描述、岗位职责、任职要求”等标题及文本块长度自动定位描述。该 fallback 不读取整页，也不尝试绕过页面的保护机制。

## 安全与运行限制

此项目是本地测试工具。自动沟通会对真实招聘方产生外部动作；默认后端分数为 50，不会触发。只有在你确认 selector 和页面状态后，才应把 `DEFAULT_MATCH_SCORE` 改为 80 测试沟通流程。请遵守网站条款并控制使用频率。
