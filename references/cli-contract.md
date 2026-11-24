# CLI 契约

Memo-TXT 只暴露以下稳定入口；不要临时拼 TXT 容器或在 skill 里另写校验器。

```text
python -B scripts/cli.py lint <TXT> [--require-answer-line]
python -B scripts/cli.py finalize <TXT> [--member pro|free] [--require-answer-line]
python -B scripts/cli.py guide
python -B scripts/cli.py web-media --help
```

- `lint`：结构校验；成功退出 0，失败退出 1；
- `finalize`：先校验，再输出导入教程和交付自检；失败退出 1；
- `guide`：只打印教程并复制 GIF 到当前工作目录；
- `lint`、`finalize`、`guide` 不联网、不读取 token、不替用户导入。
- `web-media` 是独立的联网页面流程，依赖 Playwright 和 Chrome，使用手动登录的独立浏览器配置，见 [web-media.md](web-media.md)。不改变既有离线命令。

## 禁止

- 不手写 `###` / `===` / `---` 以外的替代分卡符；
- 不临时写脚本“拼 TXT”；
- 不把 `finalize` 的输出改写成另一套教程；
- 不把未通过的 lint 结果说成交付完成。
