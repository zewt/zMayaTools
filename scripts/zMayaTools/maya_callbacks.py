import pymel.core as pm
from maya import OpenMaya as om
from zMayaTools import maya_helpers, Qt, qt_helpers

from zMayaTools import maya_logging
log = maya_logging.get_log()

class MayaCallback(object):
    """
    A helper for registering and unregistering Maya callbacks.

    To call a NodeAddedCallback:
    def func():
        print 'callback'
    callback = MayaCallback(func, lambda cb: msg.addNodeAddedCallback(cb, 'node_type', None))

    Enable the callback:
    callback.registered = True

    Disable the callback:
    callback.registered = False
    """
    def __init__(self, callback, registration_func, async=True):
        """
        If async is true, multiple callbacks will be coalesced and called from the main
        loop.  Async callbacks don't receive arguments.
        """
        self.callback_id = None
        self.callback = callback
        self.async = async
        self.registration_func = registration_func

    def __del__(self):
        self.registered = False

    @property
    def registered(self):
        return self.callback_id is not None

    @registered.setter
    def registered(self, value):
        if value:
            if self.callback_id is not None:
                return

            self.callback_id = self.registration_func(self._callback)
        else:
            if self.callback_id is None:
                return

            om.MMessage.removeCallback(self.callback_id)
            self.callback_id = None

    def _callback(self, *args, **kwargs):
        # If we get a callback when we're not registered, ignore it.
        if not self.registered:
            return

        if not self.async:
            self.callback(*args, **kwargs)
        else:
            self._queue_callback()

    def _queue_callback(self):
        qt_helpers.run_async_once(self._async_callback)

    def _async_callback(self):
        if not self.registered:
            return

        self.callback()

class AttributeChangedCallback(MayaCallback):
    """
    Run a callback on attribute changed (MNodeMessage.addAttributeChangedCallback).
    mask is an MNodeMessage::AttributeMessage bitmask.
    """
    def __init__(self, callback, node, mask=0xFFFFFFFF, async=True):
        self._user_callback = callback
        self._user_async = async
        self.mask = mask
        super(AttributeChangedCallback, self).__init__(
                self._attribute_changed,
                lambda func: om.MNodeMessage.addAttributeChangedCallback(node.__apimobject__(), func, None), async=False)

    def _attribute_changed(self, msg, plug, otherPlug, data):
        # If this isn't an attribute change type that we're interested in, ignore it.
        if (msg & self.mask) == 0:
            return

        if not self._user_async:
            self._user_callback(msg, plug, otherPlug, data)
        else:
            qt_helpers.run_async_once(self._async_user_callback)

    def _async_user_callback(self):
        if not self.registered:
            return

        self._user_callback()

class MayaCallbackList(object):
    """
    A helper for registering and unregistering several Maya callbacks.

    This works like MayaCallback, but maintains a list of callbacks.

    def func():
        print 'callback'
    callbacks = MayaCallbacks()
    callbacks.add(func, lambda cb: msg.addNodeAddedCallback(cb, 'node_type', None))
    callbacks.add(func, lambda cb: msg.addNodeRemovedCallback(cb, 'node_type', None))
    callbacks = True
    """
    def __init__(self):
        self._registered = False
        self.callbacks = []

    def add_callback(self, maya_callback):
        self.callbacks.append(maya_callback)
        maya_callback.registered = self.registered

    def add(self, func, registration_func, async=True):
        """
        Add a MayaCallback.

        If we're currently registered, the new callback will also be registered.
        """
        maya_callback = MayaCallback(func, registration_func, async=async)
        self.add_callback(maya_callback)
        return maya_callback

    def clear(self):
        """
        Unregister and remove all callbacks.
        """
        registered = self.registered
        self.registered = False
        self.callbacks = []
        self.registered = registered

    @property
    def registered(self):
        return self._registered

    @registered.setter
    def registered(self, value):
        if self._registered == value:
            return
        self._registered = value

        for callback in self.callbacks:
            callback.registered = value

