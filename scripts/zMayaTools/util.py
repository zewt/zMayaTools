import contextlib, functools, glob, os, traceback, sys, subprocess

def mkdir_p(path):
    # makedirs is buggy and raises an error if the directory already exists,
    # so we have to check manually.  It should behave like mkdir -p.
    if os.path.exists(path):
        return
    os.makedirs(path)

def empty_directory(path):
    """
    Delete all files in path.

    Delting the actual directory causes problems in Windows, which handles file locking
    very stupidly, so we don't actually delete the directory itself.  This also doesn't
    recurse into subdirectories.
    """
    if not os.path.exists(path):
        return
    for fn in glob.glob('%s/*' % path):
        if stat.S_ISDIR(os.stat(fn).st_mode):
            continue

        os.unlink(fn)

def scale(x, l1, h1, l2, h2):
    """
    Scale x from the range [l1,h1] to the range [l2,h2].
    """
    return (x - l1) * (h2 - l2) / (h1 - l1) + l2

def make_contiguous_list(items):
    """
    Given a list of integers, eg. [0,1,2,5,6,7,10], return a list of contiguous
    items as [start,end] tuples, eg. [(0,2),(5,7),(10,10)].

    This is useful for rendering a list of frames, since Maya's rendering APIs
    only take ranges and not lists.
    """
    items = sorted(items)

    results = []
    current_start = None
    current_end = None
    for item in items:
        if current_start is None:
            current_start = current_end = item
            continue

        if item == current_end + 1:
            current_end = item
            continue

        results.append((current_start, current_end))
        current_start = current_end = item
    if current_start is not None:
        results.append((current_start, current_end))

    return results

def log_errors(func):
    """
    A wrapper to print exceptions raised from functions that are called by callers
    that silently swallow exceptions, like render callbacks.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            # Exceptions from calls like this aren't well-defined, so just log the
            # error and don't reraise it.
            traceback.print_exc()

    return wrapper

def get_main_window_hwnd():
    """
    Return the window handle of the main Maya window.

    On other platforms, raise NotImplemented.
    """
    # This shouldn't be called on non-Windows platforms.
    if sys.platform != 'win32':
        raise NotImplementedError()

    from maya import OpenMayaUI as omui
    from shiboken2 import wrapInstance
    from PySide2 import QtWidgets
    main_window = omui.MQtUtil.mainWindow()
    window = wrapInstance(long(main_window), QtWidgets.QMainWindow)
    return int(window.winId())

def show_file_in_explorer(filename):
    """
    Show the given file in a File Explorer window.

    This is only supported on Windows.
    """
    if os.name != 'nt':
        log.error('Not supported on this platform')
        return

    # Work around an Explorer bug: unlike everything else in Windows it doesn't understand
    # normal forward-slash paths.
    #
    # Note that we can't use os.startfile here.  We could use that to open the directory
    # containing the scene, but if we give it the filename it'll just load the scene in a
    # new instance of Maya.
    filename = filename.replace('/', '\\')
    cmd = u'explorer /select,"%s"' % filename
    subprocess.Popen(cmd.encode('mbcs'))

FLASHW_ALL = 0x00000003
FLASHW_CAPTION = 0x00000001
FLASHW_STOP = 0
FLASHW_TIMER = 0x00000004
FLASHW_TIMERNOFG = 0x0000000C
FLASHW_TRAY = 0x00000002

def flash_taskbar(hwnd=None, flags=FLASHW_ALL|FLASHW_TIMERNOFG, count=1, timeout=0):
    """
    Flash the Windows taskbar.
    """
    # Don't do anything on other platforms.
    if sys.platform != 'win32':
        return

    if hwnd is None:
        hwnd = get_main_window_hwnd()

    import ctypes

    class FLASHWINFO(ctypes.Structure):
        _fields_ = [('cbSize', ctypes.c_ulonglong),
                    ('hwnd', ctypes.c_ulonglong),
                    ('dwFlags', ctypes.c_uint),
                    ('uCount', ctypes.c_uint),
                    ('dwTimeout', ctypes.c_uint)]
                    
    winfo = FLASHWINFO(ctypes.sizeof(FLASHWINFO), hwnd, flags, count, timeout)
    ctypes.windll.user32.FlashWindowEx(ctypes.byref(winfo))

class CancelledException(Exception): pass

class ProgressWindow(object):
    def __init__(self, total_progress_values=10, title=''):
        self._cancel = False

    def hide(self):
        pass

    def cancel(self):
        self._cancel = True

    def set_total_progress_value(self, total_progress_values):
        """
        Change the number of total progress values.

        Once progress has started the total shouldn't be changed, since progress
        bars should never go backwards, but this can be useful to create the
        window before the total amount of work to do is known.
        """
        raise NotImplementedError

    def check_cancellation(self):
        if self._cancel:
            raise CancelledException()

    def update(self, advance_by=1, text='', force=False):
        """
        Advance the progress bar.

        This should be called at the start of a task.  For example,

        progress = ProgressWindow(10)
        for idx in xrange(10:
            progress.update()
            work()

        The update may be skipped for performance if updates are happening too quickly.
        To force an update (eg. to ensure the final 100% update is displayed), set force
        to true.
        """
        # Check for cancellation when we update progress.
        self.check_cancellation()

    def __enter__(self, *args, **kwargs):
        return self

    def __exit__(self, exc, e, tb):
        self.hide()

@contextlib.contextmanager
def CombinedProgressBar(progress_bar_classes, *args, **kwargs):
    """
    Wrap one or more other ProgressWindows.

    This can be used to display progress in multiple ways, such as with both
    a ProgressWindowMaya and a ProgressWindowWindowsTaskbar.
    """
    # Create each progress bar.
    bars = []
    for progress_bar_class in progress_bar_classes:
        progress_bar = progress_bar_class(*args, **kwargs)
        bars.append(progress_bar)

    # This just forwards all calls to all progress bars.
    class CombinedProgressBar(ProgressWindow):
        pass
        
    combined_bar = CombinedProgressBar()

    # Add a wrapper for each function that we support.
    def create_wrapper(func_name):
        base_func = getattr(super(CombinedProgressBar, combined_bar), func_name)
        def wrapper(*args, **kwargs):
            for bar in bars:
                func = getattr(bar, func_name)
                func(*args, **kwargs)

        setattr(combined_bar, func_name, wrapper)

    for func_name in ('hide', 'cancel', 'set_total_progress_value', 'check_cancellation', 'update'):
        create_wrapper(func_name)

    with combined_bar:
        yield combined_bar

