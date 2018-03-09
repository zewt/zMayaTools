import ctypes
from ctypes import wintypes
from zMayaTools import maya_helpers

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
SWP_SHOWWINDOW = 0x0040
SWP_HIDEWINDOW = 0x0080
SWP_NOOWNERZORDER = 0x0200

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
WS_EX_NOACTIVATE = 0x08000000

SetWindowLong = ctypes.windll.user32.SetWindowLongPtrW
SetWindowLong.restype  = wintypes.LPVOID
SetWindowLong.argtypes = (wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID)

SetWindowPos = ctypes.windll.user32.SetWindowPos
SetWindowPos.restype = wintypes.BOOL
SetWindowPos.argtypes = (wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint)

EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int))

_optvars = maya_helpers.OptionVars()
_optvars.add('zHideOutputWindowEnabled', 'bool', False)

def _get_window_class_name(hwnd):
    class_name = ctypes.create_unicode_buffer(1024)
    ctypes.windll.user32.GetClassNameW(hwnd, class_name, 1023)
    return class_name.value

def _get_window_pid(hwnd):
    proc_id = ctypes.c_ulong()
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(proc_id))
    return proc_id.value

def _find_output_window():
    """
    Find the window handle of the Maya output window.
    """
    pid = ctypes.windll.kernel32.GetCurrentProcessId()
    found_window = [None]

    def find_window(hwnd, lParam):
        if _get_window_pid(hwnd) != pid:
            return True
        if not _get_window_class_name(hwnd).startswith('mayaConsole'):
            return True

        found_window[0] = hwnd
        return False

    ctypes.windll.user32.EnumWindows(EnumWindowsProc(find_window), 0)

    return found_window[0]

def is_hidden():
    """
    Return true if the output window is currently hidden.
    """
    hwnd = _find_output_window()
    if hwnd is None:
        return False

    style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    return (style & WS_EX_TOOLWINDOW) != 0

def _set_output_window(hide=True):
    # Don't do anything if the output window is already in the wanted state, so we don't
    # focus the output window if it was already shown.
    if is_hidden() == hide:
        return

    hwnd = _find_output_window()
    if hwnd is None:
        return

    # We have to hide the window before changing window styles, or the taskbar entry won't change.
    SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP_HIDEWINDOW|SWP_NOACTIVATE|SWP_NOSIZE|SWP_NOMOVE|SWP_NOZORDER|SWP_NOOWNERZORDER)

    style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    if hide:
        style &= ~WS_EX_APPWINDOW
        style |= WS_EX_TOOLWINDOW # hide from alt-tab
        style |= WS_EX_NOACTIVATE # hide from taskbar
    else:
        style |= WS_EX_APPWINDOW
        style &= ~WS_EX_TOOLWINDOW
        style &= ~WS_EX_NOACTIVATE

    ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)

    # Restore the visible state.  This isn't important (we're hiding the window anyway), but the window
    # will be re-displayed by Maya in this way whenever anything is written to it.  Showing it now makes
    # sure that the above is actually working, and makes sure nothing weird happens like the output window
    # stealing focus.
    SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP_SHOWWINDOW|SWP_NOACTIVATE|SWP_NOSIZE|SWP_NOMOVE|SWP_NOZORDER|SWP_NOOWNERZORDER|SWP_FRAMECHANGED)
    if not hide:
        ctypes.windll.user32.BringWindowToTop(hwnd)

def show():
    _set_output_window(hide=False)

def toggle():
    _optvars['zHideOutputWindowEnabled'] = not _optvars['zHideOutputWindowEnabled']
    refresh_visibility()

def refresh_visibility():
    """
    Show or hide the output window depending on the zHideOutputWindowEnabled option.
    """
    _set_output_window(_optvars['zHideOutputWindowEnabled'])

