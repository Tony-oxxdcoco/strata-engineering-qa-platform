# 工程 QA 网页说明

网页使用原生 ES modules 和 CSS，由 FastAPI 与 `/api/v1` 在同一来源下提供。运行时需要后端，直接以本地文件打开 `index.html` 或只上传 HTML 到静态托管都不能运行完整应用。

1.4.0页面按工作流导航：Sources & revisions、Data adaptation、Rules & evidence、Check workspace、Findings & reports；管理区提供Audit trail、Team & access及Validation。原始资料上传需要鉴权；下载来源文件和报告时，先带会话令牌请求，再以本地 Blob URL 打开。用户输入和来源文字在 HTML 展示前转义。切换选择时清除当前显示的运行结果，原记录仍保存在服务端历史中。

首次设置 → 创建项目 → Load example → 选择输入／任务 → Run review → 查看发现、引用、工具轨迹 → 复核人确认 → 打印为 PDF 或导出 JSON。上传真实规则依据时取消自动创建快照，复制精确原文建立草稿，再由 reviewer 批准。表格／PDF 需要映射时明确补充，界面不自行猜测工程字段。

本轮沿用原生ES modules：设计token集中于design-system.css，图标/表格由ui-foundation.js复用，dialog-controller.js管理弹窗，ui-page-state.js按项目/页面/运行保存页内草稿。没有引入新框架或依赖；具体组织和验证见 `docs/frontend/README.md`。
