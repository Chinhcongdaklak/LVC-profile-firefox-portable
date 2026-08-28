"""LVC Manager Profile - diem khoi chay."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _claim_taskbar_identity() -> None:
    """Cho Windows biet day la mot ung dung rieng, khong phai 'Python'.

    Khong khai bao AppUserModelID thi Windows gom cua so vao chung nhom voi
    pythonw.exe va lay icon cua Python cho thanh tac vu -- du cua so da co icon
    rieng. Phai goi TRUOC khi tao cua so dau tien moi an.
    """
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("LVC.ManagerProfile")
    except Exception:
        pass


if __name__ == "__main__":
    _claim_taskbar_identity()

    from ui.app import run

    run()
