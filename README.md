# Mizushio Desktop Pet Noi v1.0

一个使用 Python 3.14 与 PySide6 制作的轻量 Windows 桌面宠物。

桌宠拥有两套服装、44 个动作、鼠标互动、自动散步、睡眠、边缘探头、
时间状态与定时台词。程序以透明窗口运行，默认处于桌面层，不会持续遮挡
浏览器、游戏或工作窗口。

## 主要功能

- 两套完整服装：深绿洋装（默认）与经典女仆装
- 44 个动画动作，包含待机、互动、挥手、害羞、爱心、生气、睡眠、拖拽、
  跑步、探头、消息提示与晕头转向
- 30 FPS 动画渲染与动作过渡
- 自动偶尔散步，可随时手动触发
- 长时间无操作后自动打盹，并在 20～40 秒后自然醒来
- 偶尔看向鼠标；注视期间让鼠标绕角色两圈可触发眩晕反应
- 根据本机时间切换早晨、白天与夜晚状态
- 工作日上班、午休、复工和下班时间提醒，以及随机台词
- 拖拽时播放抓起、悬空、下落和落地动作
- 拖到屏幕左右边缘后进入探头状态，单击即可跳回桌面
- 记忆角色位置、大小、服装与各项开关
- 可在桌面层和始终置顶之间切换

正式版不包含已废弃的实验性游戏模块，也不依赖 WebEngine、HTML 或 JavaScript。

## 系统要求

- Windows 10 或 Windows 11（64 位）
- 源码运行与打包：64 位 Python 3.14
- 运行依赖：PySide6 6.10.1 以上、低于 6.11
- EXE 打包依赖：PyInstaller 6.15 以上、低于 7

## 快速开始

### 运行已经打包的版本

双击 `MizushioDesktopPet.exe` 即可启动。退出时右键单击桌宠，选择“退出”。

### 从源码运行

1. 安装 64 位 Python 3.14，并确保 `py` 命令可用。
2. 解压项目到一个可写目录。
3. 双击 `run.bat`。

首次运行会在项目目录创建 `.venv` 并安装依赖，之后会直接启动。

也可以在 PowerShell 中执行：

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

## 操作方式

| 操作 | 效果 |
| --- | --- |
| 左键单击 | 关闭当前气泡，或播放一次互动；睡眠中会唤醒 |
| 按住左键拖动 | 抓起角色并随鼠标移动 |
| 松开左键 | 播放下落与落地动画 |
| 拖到屏幕左／右边缘 | 落地后进入对应方向的探头状态 |
| 单击探头状态 | 从边缘跳出并恢复普通待机 |
| 注视期间让鼠标绕角色两圈 | 播放晕头转向动作 |
| 4.5 秒内连续单击 6 次 | 进入生气状态；停止点击后自然恢复 |
| `Ctrl` + 鼠标滚轮 | 调整桌宠大小 |
| 右键单击 | 打开功能菜单 |

右键菜单提供以下项目：

- 立即互动、预览消息提示动作、预览晕头转向动作
- 切换服装
- 开关自动散步、自动打盹、鼠标注视、时间状态与定时说话
- 立即散步、立即打盹或立即说一句
- 调整桌宠大小
- 回到屏幕右下角
- 切换桌面层／始终置顶
- 退出程序

## 窗口层级

默认启用“桌面层（不压住其他窗口）”，角色会以较低层级显示在桌面上。
如果希望角色覆盖其他窗口，可在右键菜单取消该选项；再次勾选即可恢复。

## 打包 Windows EXE

在 Windows 上双击 `build_exe.bat`。脚本会自动建立 `.venv`、安装构建依赖并
运行 PyInstaller。完成后的文件位于：

```text
dist\MizushioDesktopPet.exe
```

Windows EXE 必须在 Windows 环境中构建，不能直接从 Linux 交叉生成。

## 项目结构

```text
.
├─ main.py                     程序入口与版本信息
├─ pet_app.py                  桌宠窗口、动画状态机和交互逻辑
├─ circle_gesture.py           鼠标绕圈手势识别
├─ assets/
│  ├─ character_spritesheet.png
│  ├─ character_spritesheet_dark_green.png
│  ├─ sprite_manifest.json     动作、时间、速度和显示配置
│  └─ pet.ico
├─ tests/test_project.py       回归测试
├─ tools/
│  ├─ audit_animation_consistency.py
│  ├─ package_release.py
│  └─ prepare_action_pack.py
├─ requirements.txt            运行依赖
├─ requirements-build.txt      EXE 构建依赖
├─ requirements-tools.txt      素材工具依赖
├─ run.bat                     源码启动脚本
└─ build_exe.bat               Windows EXE 构建脚本
```

## 动作与配置

运行时使用两张 `1024×13760` 的透明帧表。每格为 `256×320`，两套服装共用
同一套动作坐标与播放时间。

`assets/sprite_manifest.json` 可配置：

- 默认服装与服装帧表
- 显示尺寸和可选缩放比例
- 各动作的帧坐标与逐帧停留时间
- 待机动作池、点击动作池与补间设置
- 自动散步、睡眠、鼠标注视和边缘探头参数
- 早晨、上班、午休、复工、下班与夜晚时间
- 生气状态的点击阈值与恢复时间
- 随机台词、提醒台词和气泡显示时间
- 默认窗口层级

修改素材后，可重新构建最终帧表：

```powershell
py -3.14 -m pip install -r requirements-tools.txt
py -3.14 tools\prepare_action_pack.py
```

随后执行视觉一致性审计：

```powershell
py -3.14 tools\audit_animation_consistency.py
```

## 测试

安装工具依赖后运行：

```powershell
py -3.14 -m unittest discover -s tests -v
```

测试覆盖动作与帧表完整性、双服装一致性、人物尺寸和锚点、睡眠与拖拽链、
边缘探头、鼠标绕圈、消息动作、发布清单以及正式版版本号。

## 生成源码发布包

```powershell
py -3.14 tools\package_release.py
```

默认生成 `WindowsDesktopPet_v1.0.zip`。脚本会校验发布白名单、ZIP CRC，
并在临时目录独立解压后逐文件比较 SHA-256，防止缺失文件或混入历史残留。

## v1.0 发布说明

- 将经过持续迭代和清理的桌宠本体确定为首个正式版本
- 保留两套服装、44 个动作及全部桌面互动功能
- 统一程序版本、README 与发布包命名为 v1.0
- 精简发布边界，移除历史实验功能及其运行依赖
