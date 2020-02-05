from zMayaTools import Qt, qt_helpers
import pymel.core as pm
from maya.app.general.mayaMixin import MayaQWidgetDockableMixin

from zMayaTools import maya_logging
log = maya_logging.get_log()

class DockableWindow(MayaQWidgetDockableMixin, Qt.QDialog):
    """
    A base class for dockable QT windows.
    """
    def __init__(self):
        super(DockableWindow, self).__init__()

        self.shown = False

        # Build our *.ui files into qt/resources, so the subclass can load its layout.
        qt_helpers.compile_all_layouts()

        # How do we make our window handle global hotkeys?
        undo = Qt.QAction('Undo', self)
        undo.setShortcut(Qt.QKeySequence(Qt.Qt.CTRL + Qt.Qt.Key_Z))
        undo.triggered.connect(lambda: pm.undo())
        self.addAction(undo)

        redo = Qt.QAction('Redo', self)
        redo.setShortcut(Qt.QKeySequence(Qt.Qt.CTRL + Qt.Qt.Key_Y))
        redo.triggered.connect(lambda: pm.redo(redo=True))
        self.addAction(redo)

        style = ''
        # Maya's checkbox style makes the checkbox invisible when it's deselected,
        # which makes it impossible to tell that there's even a checkbox there to
        # click.  Adjust the background color to fix this.
        style += 'QTreeView::indicator:unchecked { background-color: #000; }'

        # Make tree and list view items slightly larger by default.
        style += 'QTreeView::item { height: 20px; }'
        style += 'QListView::item { height: 26px; }'
        self.setStyleSheet(self.styleSheet() + style)

    def __del__(self):
        self.shown = False
        self.shownChanged()

    def eventFilter(self, object, event):
        # Don't close dockable windows when escape is pressed.
        if object is self and event.type() == Qt.QEvent.KeyPress and event.key() == Qt.Qt.Key_Escape:
            return True

        return super(DockableWindow, self).eventFilter(object, event)

    def close(self):
        self.shown = False
        self.shownChanged()
        super(DockableWindow, self).close()

    def done(self, result):
        # MayaQWidgetDockableMixin overrides close, but not done.  This causes an error
        # the next time the window is opened, because the workspaceControl isn't marked
        # closed:
        #
        # RuntimeError: Object's name 'WindowWorkspaceControl' is not unique.
        self.close()
        super(DockableWindow, self).done(result)

    def dockCloseEventTriggered(self):
        # Work around closing the dialog by clicking X not calling closeEvent.
        self.shown = False
        self.shownChanged()

    def showEvent(self, event):
        # Why is there no isShown()?
        if self.shown:
            return

        self.shown = True
        self.shownChanged()

    def hideEvent(self, event):
        if not self.shown:
            return

        self.shown = False
        self.shownChanged()

    def shownChanged(self):
        """
        This is called when self.shown changes.
        """
        pass

