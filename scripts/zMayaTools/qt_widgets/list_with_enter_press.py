from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *
import pymel.core as pm

class ListWidgetWithEnterPress(QListWidget):
    enter_pressed = Signal()
    
    def event(self, event):
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Return:
            self.enter_pressed.emit()
            return True

        return super(ListWidgetWithEnterPress, self).event(event)


