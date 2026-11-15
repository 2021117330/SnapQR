"""SnapQR —— Windows 上的截图 + 二维码识别小工具。

模块划分::

    app.py            应用入口、托盘、单实例、快捷键装配
    overlay.py        全屏截图遮罩层（选区、放大镜、标注绘制）
    toolbar.py        选区下方浮动工具栏
    annotations.py    标注数据模型与绘制
    render.py         把截图 + 标注合成为最终图片
    capture.py        多显示器桌面捕获
    qrdecode.py       二维码 / 条形码识别（zxing-cpp 为主，OpenCV/pyzbar 兜底）
    qrpanel.py        识别结果弹窗
    pinwindow.py      贴图窗口
    settingsdialog.py 设置界面
    config.py         配置读写
    hotkey.py         Windows 全局快捷键
    winutil.py        Win32 相关的小工具（窗口枚举、开机自启等）
    icons.py          纯代码绘制的矢量图标
"""

__version__ = "1.0.1"
__app_name__ = "SnapQR"
__author__ = "SnapQR contributors"
