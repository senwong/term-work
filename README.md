# Term Work

在 macOS 上，为 **Kaku / WezTerm / iTerm2 / Ghostty + Claude Code** 保存多需求工作区，重启后一条命令恢复各个 Tab 和对应会话。

```sh
work restore
```

每个需求独立保存工作目录和完整会话 ID，同一目录中的多个会话也能分别恢复。后台监听自动发现正在运行的 Claude，无需逐个手动登记。

## 安装

### Homebrew（推荐）

```sh
brew install senwong/tap/term-work
term-work-setup
```

第一条安装程序和 Python 依赖；第二条在当前用户下启用后台监听，并安装 `work` 命令。`term-work` 也是同一 CLI 的 Homebrew 命令名。请先安装至少一个受支持的终端和 Claude Code。软件来自项目自己的 [Homebrew Tap](https://github.com/senwong/homebrew-tap)，不属于 homebrew/core。

更新：`brew upgrade term-work`，然后再次执行 `term-work-setup`，更新后台服务使用的副本。卸载：先 `term-work-setup --uninstall`，再 `brew uninstall term-work`；会话记录保留。不要再用 `brew services` 启动第二个监听器。

### GitHub Release（无需 Git）

从 [Releases](https://github.com/senwong/term-work/releases/latest) 下载 `term-work-0.2.0-macos.tar.gz` 和 `SHA256SUMS`，放在同一个目录：

```sh
shasum -a 256 -c SHA256SUMS
tar -xzf term-work-0.2.0-macos.tar.gz
cd term-work-0.2.0
python3 install.py
```

这是 Intel / Apple Silicon 通用的 Python 源码安装包，不是独立二进制或 DMG；需要本机 Python 3.9+、一个受支持的终端和 Claude Code。下载页的版本号升级时，请相应替换文件名。

### 从源码安装

需要 macOS、Python **3.9+**、Kaku / WezTerm / iTerm2 / Ghostty 任一终端，以及 [Claude Code](https://code.claude.com/docs/en/overview)。支持 Intel 和 Apple Silicon；Python 可以通过 Homebrew 或 python.org 安装。

```sh
git clone https://github.com/senwong/term-work.git
cd term-work
python3 install.py
```

安装器会检查依赖、复制程序到 `~/.local/share/term-work/app`、安装 `~/.local/bin/work`，并启动登录后自动运行的 LaunchAgent。不需要 sudo，不修改 shell、Kaku 或 Claude 全局配置。若已有其他 `work` 命令，安装器会拒绝覆盖。

如果提示 `work: command not found`，将下行加入 `~/.zshrc`，并在当前终端执行一次：

```sh
export PATH="$HOME/.local/bin:$PATH"
```

打开所选终端，等待几秒，再查看：

```sh
work list
work restore --dry-run
```

Python、Kaku 或 Claude 的安装位置变化后，重新运行安装器。可用 `TERM_WORK_KAKU` 和 `TERM_WORK_CLAUDE` 指定可执行文件路径。安装时的 `CLAUDE_CONFIG_DIR` 会保存到后台服务配置，默认 `~/.claude`。

## 终端选择

```sh
work terminals                             # 查看安装和运行状态
work start 新需求 --terminal wezterm
work start 新需求2 --terminal iterm2
work save --terminal iterm2                 # 手动扫描并处理首次授权
work restore                               # 各需求回到原终端
work restore 新需求 --terminal iterm2       # 将已退出的会话恢复到指定终端
```

新建时只有一个终端运行会自动选择它；多个终端同时运行时用 `--terminal` 明确指定，也可以设置 `TERM_WORK_TERMINAL`。旧版记录缺少终端字段时按 Kaku 处理。正在运行的会话会跳过，不会迁移或复制正在运行的会话。

安装器默认发现所有已安装的受支持终端。只启用一个：`term-work-setup --terminal wezterm` 或 `python3 install.py --terminal iterm2`。之后安装新终端，请重新运行 setup。无需安装 Kaku 才能使用 WezTerm / iTerm2 / Ghostty。

**iTerm2 首次使用：** 打开 iTerm2，在前台执行 `work save --terminal iterm2`，允许 macOS 自动化控制；如果后台日志仍提示无权限，请在系统设置 → 隐私与安全性 → 自动化中检查相关授权。拒绝授权时保留恢复记录，后台每 60 秒重试，不影响 Kaku 或 WezTerm。iTerm2 必须位于 `/Applications/iTerm.app` 或 `~/Applications/iTerm.app`。

iTerm2 适配使用其 AppleScript/JXA 接口，不需要第三方 Python 包或 Python API 开关。上游已将 AppleScript 标为 deprecated，因此未来版本可能需要改用 Python API。新建 Tab 时设置的自定义名称可能被 iTerm2 的自动标题（当前运行程序名，如 `claude`）覆盖，属显示行为，恢复用的需求名称仍以本地记录为准。

**Ghostty 首次使用：** 打开 Ghostty，在前台执行 `work save --terminal ghostty`，允许 macOS 自动化控制；授权被拒时的处理与 iTerm2 相同。Ghostty 必须位于 `/Applications/Ghostty.app` 或 `~/Applications/Ghostty.app`。Ghostty 的 AppleScript 终端对象不提供 TTY，无法像 Kaku / WezTerm 那样按 TTY 精确匹配：`work start` 建立的会话按面板 ID 跟踪，手动运行 `claude` 的会话按唯一工作目录匹配，且工作目录可能延迟数秒才上报；同一目录存在多个 Claude 会话时跳过该会话并保留恢复记录，此时请用 `work start` / `work track` 手动登记。

## 使用

```sh
work start 登录改造                      # 当前目录中新建需求，打开 Tab
work start 支付修复 --cwd ~/projects/app  # 指定目录
work list                               # 名称、状态、目录、完整会话 ID
work restore                            # 恢复待恢复的需求
work restore 登录改造                    # 恢复指定需求，也能找回已关闭的需求
work restore --dry-run                  # 仅预览
work done 登录改造                       # 标记完成，不再自动登记相同会话
work save                               # 立即扫描现有会话
work track 老需求 UUID --cwd ~/projects/app  # 手动登记历史会话
```

平时也可以直接运行 `claude`，后台会自动登记。重启后打开原终端，再执行 `work restore`。脚本恢复对话上下文，不自动发送提示词或续跑关机前的系统命令。

## 关闭和恢复规则

每 **3 秒**检查一次；分屏按 pane 管理，各终端独立判断。

| 观察到的情况 | 处理 |
| --- | --- |
| 单个 pane 消失，同一个终端进程和原有其他 pane 持续存在 | 观察 **15 秒**后标记“已关闭”，默认跳过恢复；可按名称找回 |
| 整个终端退出、崩溃、电脑重启或关机 | 保留恢复记录 |
| 多个 pane 同时消失、读取失败、GUI 重启、采样间隔过长 | 原因不明，保留恢复记录 |

这是保守推断，并非操作系统提供的关闭原因。连续关 Tab 或延迟退出终端 可能产生歧义；已经确认“已关闭”的需求不会因之后退出终端 自动重新进入恢复列表。存活不到一个采样周期的会话可能来不及登记。

`work done` 保留本地记录用于避免重新登记，不终止进程，也不删除 Claude 历史。`work restore 名称` 可重新启用该需求。命令使用的需求名称保持稳定，最新 Tab 标题单独记录。

## 工作原理

1. Kaku / WezTerm 使用 CLI 获取 pane 和 TTY；iTerm2 使用 JXA，Ghostty 使用其 AppleScript 接口（无 TTY，按唯一工作目录匹配）。
2. 读取 Claude 的 `sessions/*.json`，取得 PID、session ID 和工作目录。
3. 用 `ps` 校验进程启动时间并取得 TTY，再精确对应到所属终端的 pane。
4. 将对应关系原子写入本地 `tasks.json`，通过文件锁协调监听器和命令。
5. 恢复时在原目录启动 `claude --resume <完整会话ID>`；受管理会话用 SessionStart hook 跟踪 `/clear` 和 `/resume`。

运行中的会话会跳过。关闭记录与聊天历史分开保存，所有会话元数据留在本机；工具不上传会话或发送网络请求。Claude 本身仍按其正常方式运行。

## 限制和兼容性

- **目前只支持本机 Claude Code，不支持 Codex、SSH 远程会话或 tmux 内部会话映射。**
- 自动发现依赖 Claude 的本地会话元数据格式，这不是稳定的公共 API。最初验证环境为 Kaku 0.19.0、Claude Code 2.1.268；其他版本请先用 `work list` 验证。旧版本缺少元数据时可使用 `work start` / `work track`。
- 同一个 TTY 匹配到多个 Claude 进程时跳过，避免猜错。后台服务一次监控一个 Claude 配置目录。
- 恢复会创建新 Tab。终端自带布局恢复留下的普通 shell Tab 不会被自动关闭或注入命令。
- 不会修改 Claude 权限模式。项目首次信任和其他正常交互仍需用户处理。

## 服务、更新和卸载

```sh
# 查看后台服务
launchctl print gui/$(id -u)/local.term-work.watcher

# 更新：在克隆目录运行
git pull --ff-only
python3 install.py

# 卸载命令和后台服务（保留恢复数据及安装副本）
python3 install.py --uninstall
```

也可以从安装副本卸载：

```sh
python3 ~/.local/share/term-work/app/install.py --uninstall
```

`python3 install.py --no-start` 只安装，本次不启动服务；下次登录仍会启动。

数据：`~/.local/share/term-work/tasks.json`。日志：同目录下 `watcher.log` 和 `watcher.error.log`。服务：`~/Library/LaunchAgents/local.term-work.watcher.plist`。卸载保留的数据和安装副本可按需手动删除。

## 开发

仅使用 Python 标准库：

```sh
python3 -m unittest discover -v
```

四个终端均已在同一台 Mac 上实机验证面板列举（含 TTY 或工作目录）、新建 Tab（工作目录、参数、标题）、自动化授权，以及 `work start` / `work list` / `work save` / `work restore --dry-run` 端到端：Kaku 0.19.0、WezTerm 20240203、iTerm2 3.7.3、Ghostty 1.3.1。

测试使用合成会话和临时目录，不会关闭实际 Tab 或修改真实会话。包含关闭观察期、整体退出、采样中断、GUI ID 复用、会话切换、完成状态与安装器检查。真实重启仍需在自己的环境中验证。

维护者发布：更新 `VERSION`、提交后创建对应版本标签，运行 `python3 build_release.py v0.2.0`。将 `dist/` 内的安装包和 `SHA256SUMS` 上传至对应 GitHub Release，然后更新独立 Tap 中的下载 URL 和 SHA-256。打包只读取已提交的标签，不包含工作区会话数据。

接口参考：[WezTerm CLI](https://wezterm.org/cli/general.html)、[iTerm2 scripting](https://iterm2.com/documentation-scripting.html)。

MIT License.
