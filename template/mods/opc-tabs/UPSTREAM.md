# opc-tabs 的上游来源

`main.js` / `model.js` 是 Herdr 自带 `tabs` mod 的副本，只多了「看板」入口
（代码里标了 `OPC 改动`）。复制是因为 Files / Changes 按钮组写死在自带 mod 里，
想在右上角加一个平级入口只能复制再改。

- 上游：Herdr 自带的 `tabs` mod（`~/.config/herdr-app/mods/tabs/`）
- 来源版本：以本机 Herdr 安装自带的版本为准，复制时没有单独记版本号
- 本文件只记录「为什么复制、差异在哪」，不记录 Herdr 版本

Herdr 升级后如果自带 tabs 的行为或 API 变了，按下面顺序对齐：

1. 对比 `~/.config/herdr-app/mods/tabs/main.js`，把所有非 `OPC 改动` 的差异同步过来；
2. 保留三处 OPC 改动：看板按钮、实例探测（`refreshInstance` / `probe`）、
   看板 tab 的开关计划（`dashboardTogglePlan`）；
3. 跑 `node --test tests/test_opc_tabs_mod.mjs`；
4. 重启 `herdr-app` 看效果。

实例探测包在 try/catch 里：读不到标记只隐藏入口，不会让整个标签栏崩掉。
