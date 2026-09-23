# sleep_slider

一个原生 Windows 贴边睡眠开关：滑块拖到右侧后进入 5 秒倒计时，倒计时期间按空格键即可取消。

当前版本：`v1.1.0`

## 功能

- 透明高精度滑动开关，默认贴在任务栏上方。
- 拖动绿色区域可以移动开关；通过托盘菜单可以锁定位置。
- 拖到右侧后倒计时 5 秒，期间只监听空格键取消。
- 播放器或游戏进入真正的全屏状态时自动隐藏，退出全屏后恢复。
- 常驻通知区域（系统托盘），右键提供显示/隐藏、锁定位置和退出程序。
- 右键菜单提供两档尺寸：`0.5倍`（紧凑，默认）和 `1倍`（标准）。切换后立即生效，并保持开关中心位置不变。
- 单实例保护，重复启动不会创建多个浮层。
- 使用透明绿色滑动开关作为 EXE 与托盘图标。

## 运行

直接运行 Release 中的 `sleep_slider_win11_native.exe`。程序没有主界面窗口，启动后会显示贴近任务栏的开关，并在通知区域驻留。

右键浮层或托盘图标可以：

1. 显示或隐藏桌面睡眠开关；
2. 锁定或解锁开关位置；
3. 切换 `0.5倍` / `1倍` 显示尺寸；
4. 退出程序。

尺寸选择仅在当前运行期间生效，重启后默认使用 `0.5倍`。

## 下载

- [下载最新 Windows EXE](https://github.com/ghostltx/sleep_slider/releases/latest/download/sleep_slider_win11_native.exe)
- [查看所有版本](https://github.com/ghostltx/sleep_slider/releases)

## 从源码构建

环境：Windows 10/11、Python 3.12 或更高版本。

```powershell
python -m pip install -r requirements.txt
python -m PyInstaller --clean --noconfirm --onefile --windowed `
  --icon work/sleep_slider_download.ico `
  --add-data "outputs/download.png;." `
  --name sleep_slider_win11_native `
  --distpath outputs `
  --workpath build/pyinstaller `
  work/sleep_slider_app.py
```

安全测试（不会真正让电脑睡眠）：

```powershell
python work/sleep_slider_app.py --dry-run
```

## 项目结构

```text
work/sleep_slider_app.py       # 托盘驻留与单实例入口
work/sleep_slider_alpha.py     # 原生透明浮层、拖动和倒计时逻辑
outputs/download.png           # 透明绿色开关图标源
work/sleep_slider_download.ico # 多尺寸 EXE 图标
```

## 许可

当前仓库未指定开源许可证；如需对外分发，请先补充许可证文件。
