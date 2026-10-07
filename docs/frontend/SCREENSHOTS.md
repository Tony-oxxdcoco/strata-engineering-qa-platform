# 真实界面改造前后

同一隔离合成项目、同一类页面及对应视口的实际Chromium截图。before来源为独立immutable 1.3.0 / d0df3b0；after为1.4.0升级界面。不是设计效果图。桌面1440×960，手机390×844；完整手机截图较长，可打开查看原图。仅证明所记录软件页面，不代表客户工程验收。

| 页面 | before | after |
|---|---|---|
| 检查工作台 | [改造前](screenshots/workspace-before.png) | [改造后](screenshots/workspace-after.png) |
| 规则与依据 | [改造前](screenshots/rules-before.png) | [改造后](screenshots/rules-after.png) |
| 资料适配 | [改造前](screenshots/adaptation-before.png) | [改造后](screenshots/adaptation-after.png) |
| 中文手机工作台 | [改造前](screenshots/mobile-zh-before.png) | [改造后](screenshots/mobile-zh-after.png) |

实际操作截图：[原值与单位映射](screenshots/mapping-preview.png)、[草稿规则](screenshots/rule-draft.png)、[PASS](screenshots/check-pass.png)、[FAIL](screenshots/check-fail.png)、[NOT VERIFIED](screenshots/check-unverified.png)、[关联重检后复核](screenshots/review-approved.png)、[中文未保存提醒](screenshots/unsaved-dialog-zh.png)。这些来自实际界面操作，和外观对照分开记录。图片中的显示账号是专用合成测试账号，不包含个人账号或密码。操作手册见[前端交付](README.md)。

已运行的最终Docker界面：[4196工作台](screenshots/docker-final-workspace.png)。这是1.4.0历史界面证据，当前版本启动方式见[Docker说明](../DOCKER.md)。
