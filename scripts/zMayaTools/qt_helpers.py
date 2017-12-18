import fnmatch, os, maya
from fnmatch import fnmatch
from zMayaTools import maya_logging, Qt
from StringIO import StringIO
import xml.etree.cElementTree as ET

log = maya_logging.get_log()

def mtime(path):
    try:
        return os.stat(path).st_mtime
    except OSError:
        return 0

def compile_all_layouts():
    # Add the resource directory to QT for the zMayaTools prefix.  See fixup_ui_source.
    Qt.QDir.setSearchPaths('zMayaTools', [os.path.dirname(__file__) + '/qt_resources'])
    
    qt_path = os.path.dirname(__file__) + '/qt/'
    qt_generated_path = os.path.dirname(__file__) + '/qt_generated/'

    # If qt_generated/__init__.py doesn't exist, create it so the directory is treated
    # as a module.  This isn't checked into the source tree so that all of the files in
    # that directory can be safely deleted.
    init_file = '%s/__init__.py' % qt_generated_path
    if not os.access(init_file, os.R_OK):
        open(init_file, 'w').close()

    # Compile *.ui layout files.
    for fn in os.listdir(qt_path):
        if not fnmatch(fn, '*.ui'):
            continue

        input_file = qt_path + fn
        output_file = qt_generated_path + fn.replace('.ui', '.py')
        if mtime(input_file) < mtime(output_file):
            continue

        with open(input_file) as input:
            input_xml = input.read()

        input_xml = fixup_ui_source(input_xml)

        with open(output_file, 'w') as output:
            Qt.pysideuic.compileUi(StringIO(input_xml), output)

def fixup_ui_source(data):
    """
    QT isn't very good, so we need to jump some hoops.

    The QT designer will only load images either as part of a resource file, or with paths
    relative to the UI file.  There's no API to compile resources in Python, and we want all
    resource compiling to happen at runtime so there are no build steps.  Paths relative to
    the UI file will work in the designer, but not when we load them at runtime.

    Work around this:

    - We have a resources file which is used only in the designer.  Images are referenced
    through this.  This results in paths like "/zMayaTools/image/path.png" in the UI (XML)
    file.
    - When we load UI files to compile them, search for these and replace them with
    "zMayaTools:image/path.png", which is the search path syntax that the designer doesn't
    seem to support.  This lets us point the "zMayaTools" prefix at the resource directory
    so we can load them without a resource compiler.
    - Search for the resources element that would import the resource file and remove it.
    If we leave it in, importing the layouts later will fail since the resources_rc file
    doesn't actually exist.

    QT's resource loading is one of those systems that's so overdesigned, it can't do the
    simple stuff.
    """
    root = ET.fromstring(data)

    # Remove the resources.qrc import, if any.
    resources_path = '../qt_resources/resources.qrc'
    resource_node = root.findall(".//resources/include[@location='%s']/.." % resources_path)
    if resource_node is not None:
        root.remove(resource_node[0])

    def replace_path(s):
        return s.replace(':/zMayaTools/', 'zMayaTools:')

    def replace_recursively(node):
        # Why are text children of a node stored inside "tail" in a child?  ElementTree
        # is an awful XML API, but it seems to be the only one included with Maya.
        node.text = replace_path(node.text)
        node.tail = replace_path(node.tail)

        for child in node:
            replace_recursively(child)

    for node in root.findall(".//*[@resource]"):
        if node.attrib['resource'] != resources_path:
            continue

        replace_recursively(node)

    return ET.tostring(root)

_run_once_pending = {}
def run_async_once(func):
    """
    Run func from the main UI thread loop.

    This is trickier than it should be:

    - If we're not in the main UI thread, we need to use maya.utils.executeDeferred.
    If we use Qt.QTimer.singleShot, it'll try to execute it in the loop for this thread,
    which probably doesn't exist.
    - If the user is dragging the time slider, executeDeferred won't execute the function
    until the drag is released.  This prevents us from updating the UI while dragging
    the time slider around.  If we're in the main thread, use Qt.QTimer.singleShot instead,
    which always runs.

    executeDeferred really needs to have an option to tell it whether you want it to
    run during playback and timeline scrubbing or not.

    If this is called multiple times with the same function before it executes, it won't
    be queued a second time.  This helps coalesce UI updates when we receive a lot of update
    messages in a row for the same update.  This isn't locked, and we don't try to guarantee
    that this won't happen.
    """
    def go():
        if not _run_once_pending.get(func):
            return
        del _run_once_pending[func]
        func()

    # _run_once_pending[func] is 1 if we've queued it with executeDeferred,  and 2 if we've queued
    # it with QTimer.  QTimer (2) is better.  If it's 1 (executeDeferred) and we're in the same
    # thread (able to use QTimer), queue it with QTimer anyway.
    currently_queued = _run_once_pending.get(func, 0)

    if Qt.QApplication.instance().thread() != Qt.QThread.currentThread():
        if currently_queued >= 1:
            # This is already queued (with either method).
            return

        maya.utils.executeDeferred(go)
        _run_once_pending[func] = 1
    else:
        if currently_queued >= 2:
            # This is already queued with QTimer.
            return

        Qt.QTimer.singleShot(0, go)
        _run_once_pending[func] = 2

