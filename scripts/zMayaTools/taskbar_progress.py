# This implements util.ProgressWindow as a progress bar in the Windows taskbar.
#
# This should usually not be used by itself.
import contextlib
from PySide2 import QtWidgets
from . import util

try:
    import comtypes.client as cc
    from comtypes.gen import TaskbarLib
except ImportError:
    cc = None
    TaskbarLib = None

def get_taskbar_interface():
    import comtypes.client as cc
    taskbar = cc.CreateObject('{56FDF344-FD6D-11d0-958A-006097C9A090}', interface=TaskbarLib.ITaskbarList3)
    taskbar.HrInit()
    return taskbar

class ProgressWindowWindowsTaskbar(object):
    def __init__(self, total_progress_values=10, title=''):
        self.total = total_progress_values
        self.taskbar = get_taskbar_interface()
        self.hwnd = util.get_main_window_hwnd()
        self.count = -1

        self.taskbar.SetProgressState(self.hwnd, TaskbarLib.TBPF_NORMAL)

        # Advance from -1 to 0.
        self.update(advance_by=1)

    def set_total_progress_value(self, total_progress_values):
        self.total = total_progress_values
        self.update(advance_by=0)

    def hide(self):
        self.taskbar.SetProgressState(self.hwnd, TaskbarLib.TBPF_NOPROGRESS)

    def update(self, advance_by=1):
        self.count += advance_by
        self.taskbar.SetProgressValue(self.hwnd, self.count, self.total + 1)

# If we don't support this (eg. non-Windows platform), replace ProgressWindowWindowsTaskbar
# with a no-op placeholder.
if TaskbarLib is None:
    class ProgressWindowWindowsTaskbarUnavailable(util.ProgressWindow):
        @classmethod
        def available(cls):
            return False

        def set_total_progress_value(self, total_progress_values):
            pass
    
    ProgressWindowWindowsTaskbar = ProgressWindowWindowsTaskbarUnavailable

