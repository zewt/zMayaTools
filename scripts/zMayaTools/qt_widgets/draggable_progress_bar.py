from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *
import pymel.core as pm

class DraggableProgressBar(QProgressBar):
    # The first argument is true if we're in relative mode and the value should be added
    # to the current value, or false if we're in absolute mode and the value should replace
    # it.
    mouse_movement = Signal(bool, float)

    def __init__(self, parent):
        self.undo_chunk_around_dragging = None
        self.dragging = False
        self.undo_chunk_open = False
        super(DraggableProgressBar, self).__init__(parent)

    def _set_mouse_pos(self, event):
        pos = event.pos()
        size = self.size()
        x = pos.x() / float(size.width())
        self.mouse_movement.emit(False, x)

    def set_undo_chunk_around_dragging(self, name):
        """
        Put an undo chunk around drag events, so the whole drag can be undone in one step.
        """
        self.undo_chunk_around_dragging = name

    def mousePressEvent(self, event):
        if self.undo_chunk_around_dragging:
            self.undo_chunk_open = True
            pm.undoInfo(openChunk=True, undoName=self.undo_chunk_around_dragging)
        
        self.relative_dragging = event.modifiers() & Qt.ShiftModifier
        
        self._start_pos = event.globalX()

        screen = QGuiApplication.primaryScreen()
        screenGeometry = screen.geometry()
        self.screen_width = 500 # screenGeometry.width()
        
        if not self.relative_dragging:
            self._set_mouse_pos(event)

        return super(DraggableProgressBar, self).mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        # Close the undo chunk, if any.
        if self.undo_chunk_open:
            pm.undoInfo(closeChunk=True)
            self.undo_chunk_open = False

        return super(DraggableProgressBar, self).mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        if self.relative_dragging:
            current_pos = event.globalX()
            delta = current_pos - self._start_pos
            delta /= float(self.screen_width)
            self.mouse_movement.emit(True, delta)
            self._start_pos = event.globalX()
        else:
            self._set_mouse_pos(event)

        return super(DraggableProgressBar, self).mouseMoveEvent(event)

