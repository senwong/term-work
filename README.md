# Kaku Work

在 macOS 上，为 **Kaku + Claude Code** 保存多需求工作区，重启后一条命令恢复各个 Tab 和对应会话。

```sh
work restore
```

每个需求独立保存工作目录和完整会话 ID，同一目录中的多个会话也能分别恢复。后台监听自动发现正在运行的 Claude，无需逐个手动登记。

## 安装

### Homebrew（推荐）

```sh
brew install senwong/tap/kaku-work
kaku-work-setup
```

第一条安装程序和 Python 依赖；第二条在当前用户下启用后台监听，并安装 `work` 命令。`kaku-work` 也是同一 CLI 的 Homebrew 命令名。请先安装 Kaku 和 Claude Code。软件来自项目自己的 [Homebrew Tap](https://github.com/senwong/homebrew-tap)，不属于 homebrew/core。

更新：`brew upgrade kaku-work`，然后再次执行 `kaku-work-setup`，更新后台服务使用的副本。卸载：先 `kaku-work-setup --uninstall`，再 `brew uninstall kaku-work`；会话记录保留。不要再用 `brew services` 启动第二个监听器。

### GitHub Release（无需 Git）

从 [Releases](https://github.com/senwong/kaku-work/releases/latest) 下载 `kaku-work-0.1.0-macos.tar.gz` 和 `SHA256SUMS`，放在同一个目录：

```sh
shasum -a 256 -c SHA256SUMS
tar -xzf kaku-work-0.1.0-macos.tar.gz
cd kaku-work-0.1.0
python3 install.py
```

这是 Intel / Apple Silicon 通用的 Python 源码安装包，不是独立二进制或 DMG；需要本机 Python 3.9+、Kaku 和 Claude Code。下载页的版本号升级时，请相应替换文件名。

### 从源码安装

需要 macOS、Python **3.9+**、[Kaku](https://github.com/tw93/Kaku) 和 [Claude Code](https://code.claude.com/docs/en/overview)。支持 Intel 和 Apple Silicon；Python 可以通过 Homebrew 或 python.org 安装。

```sh
git clone https://github.com/senwong/kaku-work.git
cd kaku-work
python3 install.py
```

安装器会检查依赖、复制程序到 `~/.local/share/kaku-work/app`、安装 `~/.local/bin/work`，并启动登录后自动运行的 LaunchAgent。不需要 sudo，不修改 shell、Kaku 或 Claude 全局配置。若已有其他 `work` 命令，安装器会拒绝覆盖。

如果提示 `work: command not found`，将下行加入 `~/.zshrc`，并在当前终端执行一次：

```sh
export PATH="$HOME/.local/bin:$PATH"
```

打开 Kaku，等待几秒，再查看：

```sh
work list
work restore --dry-run
```

Python、Kaku 或 Claude 的安装位置变化后，重新运行安装器。可用 `KAKU_WORK_KAKU` 和 `KAKU_WORK_CLAUDE` 指定可执行文件路径。安装时的 `CLAUDE_CONFIG_DIR` 会保存到后台服务配置，默认 `~/.claude`。

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

平时也可以直接运行 `claude`，后台会自动登记。重启后打开 Kaku，再执行 `work restore`。脚本恢复对话上下文，不自动发送提示词或续跑关机前的系统命令。

## 关闭和恢复规则

每 **3 秒**检查一次；Kaku 分屏按 pane 管理。

| 观察到的情况 | 处理 |
| --- | --- |
| 单个 pane 消失，同一个 Kaku 进程和原有其他 pane 持续存在 | 观察 **15 秒**后标记“已关闭”，默认跳过恢复；可按名称找回 |
| 整个 Kaku 退出、崩溃、电脑重启或关机 | 保留恢复记录 |
| 多个 pane 同时消失、读取失败、GUI 重启、采样间隔过长 | 原因不明，保留恢复记录 |

这是保守推断，并非操作系统提供的关闭原因。连续关 Tab 或延迟退出 Kaku 可能产生歧义；已经确认“已关闭”的需求不会因之后退出 Kaku 自动重新进入恢复列表。存活不到一个采样周期的会话可能来不及登记。

`work done` 保留本地记录用于避免重新登记，不终止进程，也不删除 Claude 历史。`work restore 名称` 可重新启用该需求。命令使用的需求名称保持稳定，最新 Tab 标题单独记录。

## 工作原理

1. `kaku cli list --format json` 获取 pane 和 TTY。
2. 读取 Claude 的 `sessions/*.json`，取得 PID、session ID 和工作目录。
3. 用 `ps` 校验进程启动时间并取得 TTY，再精确对应到 Kaku pane。
4. 将对应关系原子写入本地 `tasks.json`，通过文件锁协调监听器和命令。
5. 恢复时在原目录启动 `claude --resume <完整会话ID>`；受管理会话用 SessionStart hook 跟踪 `/clear` 和 `/resume`。

运行中的会话会跳过。关闭记录与聊天历史分开保存，所有会话元数据留在本机；工具不上传会话或发送网络请求。Claude 本身仍按其正常方式运行。

## 限制和兼容性

- **目前只支持本机 Claude Code，不支持 Codex、SSH 远程会话或 tmux 内部会话映射。**
- 自动发现依赖 Claude 的本地会话元数据格式，这不是稳定的公共 API。最初验证环境为 Kaku 0.19.0、Claude Code 2.1.268；其他版本请先用 `work list` 验证。旧版本缺少元数据时可使用 `work start` / `work track`。
- 同一个 TTY 匹配到多个 Claude 进程时跳过，避免猜错。后台服务一次监控一个 Claude 配置目录。
- 恢复会创建新 Tab。Kaku 自带布局恢复留下的普通 shell Tab 不会被自动关闭或注入命令。
- 不会修改 Claude 权限模式。项目首次信任和其他正常交互仍需用户处理。

## 服务、更新和卸载

```sh
# 查看后台服务
launchctl print gui/$(id -u)/local.kaku-work.watcher

# 更新：在克隆目录运行
git pull --ff-only
python3 install.py

# 卸载命令和后台服务（保留恢复数据及安装副本）
python3 install.py --uninstall
```

也可以从安装副本卸载：

```sh
python3 ~/.local/share/kaku-work/app/install.py --uninstall
```

`python3 install.py --no-start` 只安装，本次不启动服务；下次登录仍会启动。

数据：`~/.local/share/kaku-work/tasks.json`。日志：同目录下 `watcher.log` 和 `watcher.error.log`。服务：`~/Library/LaunchAgents/local.kaku-work.watcher.plist`。卸载保留的数据和安装副本可按需手动删除。

## 开发

仅使用 Python 标准库：

```sh
python3 -m unittest discover -v
```

测试使用合成会话和临时目录，不会关闭实际 Tab 或修改真实会话。包含关闭观察期、整体退出、采样中断、GUI ID 复用、会话切换、完成状态与安装器检查。真实重启仍需在自己的环境中验证。

维护者发布：更新 `VERSION`、提交后创建对应版本标签，运行 `python3 build_release.py v0.1.0`。将 `dist/` 内的安装包和 `SHA256SUMS` 上传至对应 GitHub Release，然后更新独立 Tap 中的下载 URL 和 SHA-256。打包只读取已提交的标签，不包含工作区会话数据。

MIT License.
