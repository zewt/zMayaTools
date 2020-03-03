from zMayaTools import Qt
from pymel import core as pm

from zMayaTools import maya_logging
log = maya_logging.get_log()

class NoDragPreviewMixin(object):
    """
    Disable drag preview images.
    """
    def __init__(self, parent):
        super(NoDragPreviewMixin, self).__init__(parent)
    
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

        super(NoDragPreviewMixin, self).startDrag(supportedActions)

def _is_descendant(index, target):
    """
    Return true if index is a parent of target.
    """
    while target.isValid():
        if target == index:
            return True
        target = target.parent()
    return False

def _any_is_descendant(selection, target):
    """
    Return true if any index in selection is a parent of target.
    """
    for index in selection:
        if _is_descendant(index, target):
            return True
    return False

class DragFromMayaMixin(object):
    """
    This adds support for dragging Maya nodes and attributes into a widget.
    """
    # Note that the arguments for these actually depend on the base class type, and can be eg. a
    # QListWidgetItem.

    # source, target (or None for DropIndicatorPosition.OnViewport), dropIndicatorPosition
    dragged_internally = Qt.Signal(Qt.QObject, Qt.QDropEvent, Qt.QAbstractItemView.DropIndicatorPosition)

    # nodes, target (or None for DropIndicatorPosition.OnViewport), dropIndicatorPosition
    dragged_from_maya = Qt.Signal(str, Qt.QTreeWidgetItem, Qt.QAbstractItemView.DropIndicatorPosition)

    def __init__(self, parent):
        super(DragFromMayaMixin, self).__init__(parent)

    def checkDragFromMaya(self, nodes):
        """
        Given a list of nodes/attributes being dragged into the widget, return a list of
        which ones should be accepted.

        If the returned list is empty, the drag will be ignored.
        """
        return pm.ls(nodes, type='transform')

    def dropEvent(self, event):
        # QTreeWidget and QListWidget::dropEvent have crazy handling for drops from ourself.  They just
        # move items around on their own assuming the model will have exactly the same behavior, and
        # then change MoveAction to CopyAction, confusing what's actually happening.
        #
        # This doesn't happen if the event is already accepted.   QListModeViewBase::dropOn, etc. will
        # return false and the dropEvent won't do this.  It may still do other things, like stop auto-scrolling.
        # So, do our event checks first, accept the event if we process it, then run the base implementation
        # last.

        if 'application/x-maya-data' in event.mimeData().formats():
            if event.dropAction() == Qt.Qt.DropAction.CopyAction:
                event.accept()

                nodes = event.mimeData().text().rstrip().split()

                nodes = [pm.PyNode(node) for node in nodes]
                nodes = self.checkDragFromMaya(nodes)
                if nodes:
                    target = self.itemAt(event.pos())
                    self.dragged_from_maya.emit(nodes, target, self.dropIndicatorPosition())

            # event.source() crashes if the drag comes from a Maya object, so don't check the other cases.
        elif event.source() is not None:
            # Always accept drops (including for move events) to prevent the crazy base class behavior.
            event.accept()

            if event.dropAction() == Qt.Qt.DropAction.CopyAction:
                target = self.itemAt(event.pos())

                # If this is a tree and we're dragging onto ourself, if any index in the selection
                # is a child of the drop position, the drop is invalid.
                ignore_event = False
                if isinstance(self, Qt.QTreeWidget) and event.source() is self:
                    selected_indexes = self.selectedIndexes()
                    target_index = self.indexAt(event.pos())
                    ignore_event = _any_is_descendant(selected_indexes, target_index)

                if not ignore_event:
                    indicator_position = self.dropIndicatorPosition()
                    self.dragged_internally.emit(target, event, self.dropIndicatorPosition())

        super(DragFromMayaMixin, self).dropEvent(event)

    def dragMoveEvent(self, event):
        # In QT 4, QAbstractItemViewPrivate::position normally gives a margin of 2 pixels
        # on the top and bottom for AboveItem and BelowItem, which is much too small and makes
        # dragging painful.  In QT 5 it gives a fraction of the heigh, which is much more usable.
        # Maya uses QT 5, and its built-in UIs like the shape editor have QT 5's behavior, but
        # for some reason QTreeView, etc. still have QT 4's behavior.
        #
        # Work around this by looking at the event position.  If it's in a position where an
        # above or below drag should be happening, snap the drag position to the boundary so
        # it's treated as an above or below drag.
        pos = event.pos()
        index = self.indexAt(event.pos())
        if index.isValid():
            rect = self.visualRect(index)
            margin = round(float(rect.height()) / 5.5)
            margin = min(max(margin, 2), 12)
            if pos.y() < margin + rect.top() :
                # Move the drag position to the top of the item, forcing AboveItem.
                pos.setY(rect.top())
            elif pos.y() > rect.bottom() - margin:
                # Move the drag position to the bottom of the item, forcing BelowItem.
                pos.setY(rect.bottom())
            elif rect.contains(pos, True):
                # Move the drag position to the center of the item, forcing OnItem.
                pos.setY((rect.bottom() + rect.top()) / 2)
            
        # Create a new, equivalent QDragMoveEvent with our adjusted position.
        #
        # The QT docs say not to construct these.  But, it doesn't offer any alternative,
        # there's no setPos, and this works fine.
        event2 = Qt.QDragMoveEvent(
                pos,
                event.dropAction(),
                event.mimeData(),
                event.mouseButtons(),
                event.keyboardModifiers(),
                event.type())
        super(DragFromMayaMixin, self).dragMoveEvent(event2)

    def mouseMoveEvent(self, event):
        # Match Maya's behavior and only drag on MMB-drag, since Qt's LMB-dragging is
        # broken with multiple selection.
        buttons = event.buttons()
        middle_pressed = bool(buttons & Qt.Qt.MiddleButton)
        self.setDragEnabled(middle_pressed)

        super(DragFromMayaMixin, self).mouseMoveEvent(event)

    def dragEnterEvent(self, event):
        super(DragFromMayaMixin, self).dragEnterEvent(event)

        # For Maya nodes, check if the nodes are an accepted type.
        if 'application/x-maya-data' in event.mimeData().formats():
            if not event.mimeData().hasText():
                event.ignore()
                return

            nodes = event.mimeData().text().rstrip().split()
            nodes = self.checkDragFromMaya(nodes)
            if not nodes:
                event.ignore()

    def mimeTypes(self):
        """
        Add Maya nodes to the MIME types accepted for drag and drop.
        """
        result = super(DragFromMayaMixin, self).mimeTypes()
        result.append('application/x-maya-data')
        return result

