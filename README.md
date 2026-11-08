# Stata Econ MCP

让 Claude（Claude Desktop 聊天 / Claude Code）直接驱动你本机的 Stata 跑回归。

- 使用 Stata 官方自带的 pystata 引擎（`<Stata 安装目录>/utilities/pystata`），用的是你自己的 Stata、许可证和已安装的外部命令（reghdfe、csdid 等）。
- Stata 跑在独立子进程里，会话常驻：数据、`estimates store`、locals 在调用之间保留；卡死可 `stata_restart`。
- 内置应用计量知识包（面板 FE / DID / 错时 DID / DDD / 事件研究 / LaTeX 表 / 审稿标准），Claude 通过 `stata_guide` 读取。

## 环境要求
- Stata 17 或更高（MP / SE / BE），已在本机安装并激活许可证
- [uv](https://docs.astral.sh/uv/)（或 Python 3.11+）
- 已在 macOS (Apple Silicon) + Stata 18 MP 上测试；Linux / Windows 理论可用但未测试，需要设置 `STATA_DIR`

## 安装
```bash
git clone https://github.com/shanyuzhang/stata-econ-mcp.git
cd stata-econ-mcp
uv sync
```
可执行文件位于 `<仓库路径>/.venv/bin/stata-econ-mcp`（下文记为 `<SERVER>`，请填绝对路径）。

### 接入 Claude Code
```bash
claude mcp add stata --scope user -- "<SERVER>"
```

### 接入 Claude Desktop
编辑 `~/Library/Application Support/Claude/claude_desktop_config.json`（Windows：`%APPDATA%\Claude\claude_desktop_config.json`），在 `mcpServers` 中加入：
```json
{
  "mcpServers": {
    "stata": {
      "command": "<SERVER>",
      "args": []
    }
  }
}
```
保存后完全退出并重新打开 Claude Desktop。

如果 Stata 不在默认位置（macOS 默认搜索 `/Applications/Stata`、`/Applications/StataNow` 等），在配置里加环境变量：
```json
"env": { "STATA_DIR": "/path/to/Stata", "STATA_EDITION": "mp" }
```

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
| `stata_help` | 读官方 / 外部命令的帮助文件 |
| `stata_guide` | 计量知识包 |
| `stata_status` / `stata_set_workdir` | 状态与已装包检查 / 切换项目文件夹 |

## 输出位置
`<项目文件夹>/stata_output/{do,logs,tables,figures}`

- Claude Code（或 Desktop 的 Code 页签）：项目文件夹 = 会话所在文件夹。
- Desktop 普通聊天（没有文件夹）：默认 `~/Documents/Stata研究/`；也可以直接告诉 Claude "项目放在某某目录"，它会调用 `stata_set_workdir`。
- 每条命令都会追加到 `logs/history_<日期>.do`，便于复现。

## 环境变量（可选）
| 变量 | 默认值 |
|---|---|
| `STATA_DIR` | 自动搜索 |
| `STATA_EDITION` | 按安装目录自动判断（mp / se / be） |
| `STATA_MCP_WORKDIR` | 自动（会话文件夹 → 默认目录） |
| `STATA_MCP_DEFAULT_DIR` | `~/Documents/Stata研究` |
| `STATA_MCP_OUTPUT_SUBDIR` | `stata_output` |
| `STATA_MCP_WAIT_SECONDS` | `240`（超时后任务继续在后台跑，用 `stata_wait` 取结果） |

## 推荐安装的 Stata 外部命令
```stata
ssc install reghdfe
ssc install ftools
ssc install estout
ssc install coefplot
ssc install csdid
ssc install drdid
ssc install did_imputation
ssc install eventstudyinteract
ssc install event_plot
ssc install boottest
```
`stata_status` 会列出哪些已安装。

## 已知事项
- 如果你的 `profile.do` 含有只在图形界面下可用的命令（如 `window menu`），无界面模式下它会中途停止；服务器启动后会补设 `more off`、`type double`、`maxvar`、`linesize`。
- Stata 内嵌 Python 不支持带空格的解释器路径；若仓库放在带空格的目录下，worker 会自动创建无空格的软链接（`~/.cache/stata-econ-mcp/python`）绕过。
- 安全约束（不执行 `shell` / `!`、不删除用户文件、安装外部命令前先询问）只通过给 Claude 的指令实现，代码层面没有强制拦截；它运行的是你本机的完整 Stata，请只在信任的客户端中使用。

## 许可证
MIT
