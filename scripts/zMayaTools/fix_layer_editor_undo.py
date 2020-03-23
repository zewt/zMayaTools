# Work around an ancient annoying bug with the layer editor: it doesn't update properly on
# undo and when anything other than the layer editor makes changes to display layers, which
# causes the visibility display to often be wrong.  It does update layerState correctly.
# This seems to be a bug in the layerButton widget.

import pymel.core as pm
from maya import OpenMaya as om
from zMayaTools import maya_helpers, maya_callbacks

from zMayaTools import maya_logging
log = maya_logging.get_log()

class RefreshDisplayLayerUI(object):
    def __init__(self):
        self.callbacks = maya_callbacks.MayaCallbackList()
        self.node_callbacks = maya_callbacks.MayaCallbackList()
        self.callbacks.registered = self.node_callbacks.registered = True

        # Listen to node creation and deletion.
        msg = om.MDGMessage()
        self.callbacks.add(self._refresh_node_listeners, lambda func: msg.addNodeAddedCallback(func, 'displayLayer', None))
        self.callbacks.add(self._refresh_node_listeners, lambda func: msg.addNodeRemovedCallback(func, 'displayLayer', None))

        # Register for layers that already exist.
        self._refresh_node_listeners()

    def _refresh_node_listeners(self):
        """
        Create node-specific listeners.
        """
        self.node_callbacks.clear()

        msg = om.MDGMessage()
        for node in pm.ls(type='displayLayer'):
            self.node_callbacks.add_callback(maya_callbacks.AttributeChangedCallback(
                self.refresh_layer_editor,
                node,
                mask=om.MNodeMessage.kAttributeSet))

    def __del__(self):
        self.unregister()

    def unregister(self):
        self.callbacks.registered = self.node_callbacks.registered = False

    def refresh_layer_editor(self):
        for layer in pm.ls(type='displayLayer'):
            if not pm.layerButton(layer, exists=True):
                continue
                
            pm.layerButton(layer, edit=True, layerVisible=layer.visibility.get(), layerHideOnPlayback=layer.hideOnPlayback.get())

listener = None

def install():
    global listener
    if listener is not None:
        return

    listener = RefreshDisplayLayerUI()

def uninstall():
    global listener
    if listener is None:
        return

    listener.unregister()
    listener = None


