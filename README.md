# Stata Econ MCP

让 Claude（Desktop 聊天 / Claude Code）直接驱动本机 Stata 18 MP 跑回归。

- 走 Stata 官方自带的 pystata 引擎（`/Applications/Stata/utilities/pystata`），用的是你自己的 Stata、许可证和已装的外部命令。
- Stata 跑在独立子进程里，会话常驻（数据、`estimates store`、locals 在调用之间保留）；卡死可 `stata_restart`。
- 内置应用计量知识包（面板 FE / DID / 错时 DID / DDD / 事件研究 / LaTeX 表 / 审稿标准），Claude 用 `stata_guide` 读取。

## 工具
| 工具 | 作用 |
|---|---|
| `stata_run` | 执行一段代码（快速检查） |
| `stata_do` | 存成 do 文件并执行，带 log（正式分析用） |
| `stata_wait` / `stata_restart` | 长任务继续等待 / 重启 Stata |
| `stata_data` | 数据概览、describe、summarize、xtdescribe、缺失值等 |
| `stata_results` | 结构化读取系数、SE、p 值、N、聚类数、FE |
| `stata_table` | esttab 生成 booktabs LaTeX 回归表 |
| `stata_graph` | 导出图（PNG 在对话中显示 + PDF 给 LaTeX） |
| `stata_help` | 读官方/外部命令帮助文件 |
| `stata_guide` | 计量知识包 |
| `stata_status` / `stata_set_workdir` | 状态与已装包检查 / 切换项目文件夹 |

## 输出放在哪
`<项目文件夹>/stata_output/{do,logs,tables,figures}`。

- Claude Code / Desktop 的 Code 页签：项目文件夹 = 会话所在文件夹。
- Desktop 普通聊天（没有文件夹）：默认 `~/Documents/Stata研究/`；也可以直接说"把项目放在 ~/xxx"，Claude 会调用 `stata_set_workdir`。
- 每条命令都会追加到 `logs/history_<日期>.do`，便于复现。

## 安装 / 注册（已完成）
```bash
uv sync
claude mcp add stata --scope user -- "/Users/kyle/Documents/Growth/Stata MCP/.venv/bin/stata-econ-mcp"
```
Claude Desktop：`~/Library/Application Support/Claude/claude_desktop_config.json` 的 `mcpServers.stata`
指向同一个可执行文件。修改后需完全退出并重启 Claude Desktop。

## 环境变量（可选）
`STATA_DIR`（默认自动找 /Applications/Stata）、`STATA_EDITION`（mp/se/be）、`STATA_MCP_WORKDIR`、
`STATA_MCP_DEFAULT_DIR`、`STATA_MCP_OUTPUT_SUBDIR`（默认 stata_output）、`STATA_MCP_WAIT_SECONDS`（默认 240）。

## 已知事项
- 你的 `profile.do` 在无界面模式下会在 `window menu` 处报错中止；服务器启动后会补设 `more off / type double / maxvar / linesize`。
- Stata 内嵌 Python 不支持带空格的解释器路径（本项目在 "Stata MCP/" 下），worker 已自动用无空格的软链接绕过。
- 未安装：`did_imputation`、`eventstudyinteract`、`did_multiplegt_dyn`、`event_plot`（需要时 `ssc install`）。
