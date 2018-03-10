from zMayaTools import Qt
from pymel import core as pm

class ControllerTreeWidget(Qt.QTreeWidget):
    def __init__(self, parent):
        super(ControllerTreeWidget, self).__init__(parent)

    # source, target (or None for DropIndicatorPosition.OnViewport), dropIndicatorPosition
    dragged_internally = Qt.Signal(Qt.QTreeWidgetItem, Qt.QTreeWidgetItem, Qt.QAbstractItemView.DropIndicatorPosition)

    # nodes, target (or None for DropIndicatorPosition.OnViewport), dropIndicatorPosition
    dragged_from_maya = Qt.Signal(basestring, Qt.QTreeWidgetItem, Qt.QAbstractItemView.DropIndicatorPosition)

    def startDrag(self, supportedActions):
        """
        This mess is only needed because apparently there's no way to simply tell QT
        that you don't want a big picture of the text you're dragging covering up the
        drag so you can't see where you're dropping.  QT is not a good API.
        """
        drag = Qt.QDrag(self)
        data = self.model().mimeData(self.selectedIndexes())
        drag.setMimeData(data)
        drag.exec_(supportedActions, Qt.Qt.MoveAction)

    def dropEvent(self, event):
        target = self.itemAt(event.pos())

        # event.source() crashes if the drag comes from a Maya object.
        if 'application/x-maya-data' in event.mimeData().formats():
            nodes = event.mimeData().text().rstrip().split()

            # Only accept transform nodes.
            nodes = pm.ls(nodes, type='transform')
            self.dragged_from_maya.emit(nodes, target, self.dropIndicatorPosition())
            return

        if event.source() is self:
            source = self.currentItem()
            target = self.itemAt(event.pos())
            indicator_position = self.dropIndicatorPosition()
            self.dragged_internally.emit(source, target, self.dropIndicatorPosition())

    def dragEnterEvent(self, event):
        super(ControllerTreeWidget, self).dragEnterEvent(event)
        if 'application/x-maya-data' in event.mimeData().formats() and event.mimeData().hasText():
            nodes = event.mimeData().text().rstrip().split()
            nodes = pm.ls(nodes, type='transform')
            if len(nodes) > 0:
                event.accept()
            else:
                event.ignore()

