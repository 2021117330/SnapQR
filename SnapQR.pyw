"""Windows 下双击启动 SnapQR（由 pythonw 运行，不弹控制台窗口）。

也可以直接 ``python -m snapqr``。
"""

from snapqr.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
