import contextlib, functools, logging, os, subprocess, time
from contextlib import contextmanager
from collections import namedtuple
from pymel import core as pm
from maya import OpenMaya as om
from zMayaTools import util, Qt, qt_helpers
from maya import OpenMayaUI as omui
from maya.app.general import mayaMixin
from maya.api.MDGContextGuard import MDGContextGuard
from maya import cmds
from shiboken2 import wrapInstance

from zMayaTools import maya_logging
log = maya_logging.get_log()

var_type = namedtuple('var_type', ('expected_type','maya_type'))
class OptionVar(object):
    """
    A helper for accessing a single optionvar.

    test = maya_helpers.OptionVar('test', 'bool', True)    
    print test.value
    test.value = False
    print test.value
    """

    _types = {
        'int': var_type(expected_type=int, maya_type='intValue'),
        'float': var_type(expected_type=(float, int), maya_type='floatValue'),
        'string': var_type(expected_type=basestring, maya_type='stringValue'),
        'bool': var_type(expected_type=(bool, int), maya_type='intValue'),
    }
    
    def __init__(self, name, var_type, default):
        """
        Note that on_change is only called if the optvar is changed via this object,
        since Maya has no way to register a callback when an optvar changes.
        """
        assert var_type in self._types
        self.name = name
        self.var_type = var_type
        self.default = default
        self.on_change_callbacks = []

    def __str__(self):
        return 'OptionVar(%s=%s)' % (self.name, self.value)

    def reset(self):
        """
        Reset the optvar to its default value.

        This just removes the var, so value will return the default.
        """
        pm.optionVar(remove=self.name)
        self._call_on_change()

    def _call_on_change(self):
        for callback in list(self.on_change_callbacks):
            try:
                callback(self)
            except Exception as e:
                # The callback may have nothing to do with the code changing the value, so
                # don't propagate the exception upwards.  Just log it.
                log.exception('on_change raised exception')

    def add_on_change_listener(self, on_change):
        self.on_change_callbacks.append(on_change)

    def remove_on_change_listener(self, on_change):
        if on_change in self.on_change_callbacks:
            self.on_change_callbacks.remove(on_change)

    @property
    def value(self):
        if not pm.optionVar(exists=self.name):
            return self.default

        value = pm.optionVar(q=self.name)

        # Make sure the value is of the type we expect.  If it's not, return the default instead.
        item_type = self._types[self.var_type]
        expected_class = item_type.expected_type
        if not isinstance(value, expected_class):
            return self.default

        # For bool, cast to bool.
        if self.var_type == 'bool':
            value = bool(value)

        return value

    @value.setter
    def value(self, value):
        old_value = self.value

        item_type = self._types[self.var_type]
        expected_class = item_type.expected_type
        assert isinstance(value, expected_class), 'Option %s has type %s and can\'t be set to "%s"' % (self.name, self.var_type, value)

        kwargs = {}
        arg = item_type.maya_type
        kwargs[arg] = (self.name, value)
        pm.optionVar(**kwargs)

        if value != old_value:
            self._call_on_change()

class OptionVars(object):
    """
    A helper to simplify accessing Maya optionvars.

    This supports ints, floats and strings (arrays aren't supported).
    """
    def __init__(self):
        self.keys = {}

    def add(self, name, *args, **kwargs):
        self.keys[name] = OptionVar(name, *args, **kwargs)

    def add_from(self, optvars):
        """
        Add all optvars from another OptionVars object.
        """
        self.keys.update(optvars.keys)

    def get(self, name):
        """
        Return the OptionVar for the given key.
        """
        return self.keys[name]

    def reset(self):
        for option in self.keys.values():
            option.reset()

    def __setitem__(self, name, value):
        option = self.keys.get(name)
        assert option is not None, 'Unknown option var name %s' % name
        option.value = value

    def __getitem__(self, name):
        option = self.keys.get(name)
        assert option is not None, 'Unknown option var name %s' % name

        return option.value

class OptionsBox(object):
    def __init__(self):
        self.optvars = OptionVars()

    # Set this to the title of the option box.
    title = '(not set)'

    def run(self):
        pm.setParent(pm.mel.eval('getOptionBox()'))
        
        pm.setUITemplate('DefaultTemplate', pushTemplate=True)

        pm.waitCursor(state=1)

        pm.tabLayout(tabsVisible=False, scrollable=True)
        
        self.options_box_setup()
        self.option_box_load()

        pm.waitCursor(state=0)
        
        pm.setUITemplate(popTemplate=True)

        # We need to set both apply and apply and close explicitly.  Maya breaks apply and close
        # if apply is set to a Python function.
        def apply(unused):
            self.option_box_save()
            self.option_box_apply()

        def apply_and_close(unused):
            self.option_box_save()
            self.option_box_apply()
            pm.mel.eval('hideOptionBox()')
            
        pm.button(pm.mel.eval('getOptionBoxApplyBtn()'), edit=True, command=apply)
        pm.button(pm.mel.eval('getOptionBoxApplyAndCloseBtn()'), edit=True, command=apply_and_close)
    
        # XXX: Is there a way for us to add a help link?
        pm.mel.eval('setOptionBoxCommandName("%s")' % self.title)
        # pm.mel.eval('setOptionBoxHelpTag "%s"' % self.title)
        pm.mel.eval('setOptionBoxTitle("%s");' % self.title)

        pm.mel.eval('showOptionBox()')

        # These need to be set directly to the menu item after showing the option box to
        # work around a Maya bug that breaks these when they're connected to Python functions.
        pm.menuItem(pm.mel.globals['gOptionBoxEditMenuSaveItem'], edit=True, command=lambda unused: self.option_box_save())
        pm.menuItem(pm.mel.globals['gOptionBoxEditMenuResetItem'], edit=True, command=lambda unused: self.option_box_reset())

    def options_box_setup(self):
        """
        Implement this to set up the options box.
        """
        raise NotImplemented

    def option_box_apply(self):
        """
        Implement this to run the action when the user clicks "Apply".
        """
        raise NotImplemented

    def option_box_save(self):
        """
        Save any persisted options to self.optvars.
        """
        raise NotImplemented

    def option_box_load(self):
        """
        Load any persisted options from self.optvars to the UI.
        """
        raise NotImplemented
        
    def option_box_reset(self):
        self.optvars.reset()
        self.option_box_load()

class ProgressWindow(Qt.QDialog):
    def __init__(self):
        super(ProgressWindow, self).__init__()

        # Make sure our UI has been generated.
        qt_helpers.compile_all_layouts()

        from zMayaTools.qt_generated import zProgressWindow
        reload(zProgressWindow)

        self.ui = zProgressWindow.Ui_zProgressWindow()
        self.ui.setupUi(self)
        self.ui.mainProgressBar.setMinimum(0)
        self.ui.mainProgressBar.setMaximum(1000)
        self.ui.mainProgressBar.setValue(500)

    def done(self, result):
        self.close()
        super(ProgressWindow, self).done(result)

    def force_redraw(self):
        self.repaint()
        Qt.QCoreApplication.processEvents(Qt.QEventLoop.ExcludeSocketNotifiers | Qt.QEventLoop.ExcludeUserInputEvents)

    def show(self):
        main_window = wrapInstance(long(omui.MQtUtil.mainWindow()), Qt.QMainWindow)
        self.setParent(main_window)

        # Disable minimize and maximize.
        self.setWindowFlags(Qt.Qt.Window|Qt.Qt.CustomizeWindowHint|Qt.Qt.WindowTitleHint|Qt.Qt.WindowSystemMenuHint)

        super(ProgressWindow, self).show()

class ProgressWindowMaya(util.ProgressWindow):
    def __init__(self, total_progress_values, title='Progress...',
            # Show a title above the main progress bar.  (If a secondary progress bar is displayed,
            # it will always have a title.)
            with_titles=False,

            # Show a secondary progress bar, which can be updated with set_task_progress.
            with_secondary_progress=False,

            # Show a cancel button.
            with_cancel=False):
        super(ProgressWindowMaya, self).__init__()
        self.window = None
        self.last_refresh = None
        self.last_task_refresh = None
        self.main_progress_value = -1
        self.with_titles = with_titles
        self.with_secondary_progress = with_secondary_progress

        self.window = ProgressWindow()
        self.window.setWindowTitle(title)
        self.window.setWindowFlags(Qt.Qt.Widget)

        self.window.ui.mainProgressBar.setMinimum(0)
        self.window.ui.mainProgressBar.setValue(0)
        self.set_total_progress_value(total_progress_values)

        # Hide UI elements that we're not using.
        if not self.with_secondary_progress:
            self.window.ui.secondaryProgressBar.hide()
            self.window.ui.secondaryTitle.hide()
        if not self.with_titles:
            self.window.ui.mainTitle.hide()
        if not with_cancel:
            self.window.ui.cancelButton.hide()

        self.window.ui.cancelButton.clicked.connect(self._cancel_clicked)

        self.window.setModal(True)
        self.window.resize(self.window.sizeHint())
        self.window.show()

        # Advance from -1 to 0.
        self.update(force=True)

    def check_cancellation(self):
        # Process input to allow clicks on the cancel button to be received.
        Qt.QCoreApplication.processEvents(Qt.QEventLoop.ExcludeSocketNotifiers)

        super(ProgressWindowMaya, self).check_cancellation()

    def set_total_progress_value(self, total_progress_values):
        self.window.ui.mainProgressBar.setMaximum(total_progress_values)

    def hide(self):
        super(ProgressWindowMaya, self).hide()
        self.window.close()

    def _cancel_clicked(self):
        log.debug('Cancel button clicked')
        self.cancel()

    def update(self, advance_by=1, text='', force=False):
        super(ProgressWindowMaya, self).update(advance_by, text)
        
        # Reset the task refresh timers when we change the main task.
        self.last_task_refresh = None
        self.last_task_percent = 0
        
        if text:
            log.info(text)

        if self.window is None:
            return

        # Only refresh if we haven't refreshed in a while.  This is slow enough to cause
        # performance issues if we're showing fine-grained progress.
        self.main_progress_value += advance_by
        if not force and self.last_refresh is not None and time.time() - self.last_refresh < 0.1:
            return

        self.last_refresh = time.time()

        if text:
            if self.with_titles:
                self.window.ui.mainTitle.setText(text)
            else:
                self.window.setWindowTitle(text)

        self.window.ui.mainProgressBar.setValue(self.main_progress_value)

        if self.with_secondary_progress:
            self.window.ui.secondaryProgressBar.setValue(0)

        self.window.force_redraw()

    def set_task_progress(self, label, percent=None, force=False):
        # Check for cancellation when we update progress.
        self.check_cancellation()

#        log.debug(label)

        if percent is None:
            percent = self.last_task_percent
            
        self.last_task_percent = percent

        if self.window is None:
            return

        # Only refresh if we haven't refreshed in a while.  This is slow enough to cause
        # performance issues if we're showing fine-grained progress.
        if not force and self.last_task_refresh is not None and time.time() - self.last_task_refresh < 0.1:
            return

        self.last_task_refresh = time.time()

        self.window.ui.secondaryTitle.setText(label)
        self.window.ui.secondaryProgressBar.setValue(round(percent * 100))
        self.window.force_redraw()

class TimeChangeListener(object):
    """
    Helper to receive a callback when the scene time changes.

    By default, callbacks are paused during playback to avoid impacting playback
    performance.  To always receive callbacks, set pause_during_playback to true.

    register() must be called to begin receiving callbacks.  unregister() must be
    called to clean up listeners before unloading code.
    """
    def __init__(self, callback, pause_during_playback=True):
        self.playing_back_job = None
        self.playback_callback_id = None
        self.callback = callback
        self._pause_during_playback = pause_during_playback

    def register(self):
        """
        Register the time changed listener if we're not currently in playback.

        We deregister this listener during playback, so we only update when scrubbing the timeline
        and don't slow down playback.
        """
        if self.playing_back_job is None:
            self.playing_back_job = pm.scriptJob(conditionTrue=('playingBack', self._playback_stopped))

        if self._enable_time_listener() and self.playback_callback_id is None:
            self._register_time_changed_listener()

    def unregister(self):
        if self.playing_back_job is not None:
            pm.scriptJob(kill=self.playing_back_job)
            self.playing_back_job = None
        
        self._unregister_time_changed_listener()

    def _time_changed(self, unused):
        # We want to unregister the time changed listener during playback, but there seems
        # to be no way to get a callback when playback starts.  scriptJob('playingBack') isn't
        # even called.
        #
        # If we unregister here, we'll register again when playback ends via scriptJob('playingBack').
        if not self._enable_time_listener():
            self._unregister_time_changed_listener()
            return

        self.callback()

    def _register_time_changed_listener(self):
        if self.playback_callback_id is not None:
            return

        self.playback_callback_id = om.MEventMessage.addEventCallback('timeChanged', self._time_changed)

    def _unregister_time_changed_listener(self):
        if self.playback_callback_id is None:
            return

        msg = om.MMessage()
        msg.removeCallback(self.playback_callback_id)
        self.playback_callback_id = None

    def _enable_time_listener(self):
        if not self._pause_during_playback:
            return True

        return not pm.play(q=True, state=True)

    def _playback_stopped(self):
        if not self._enable_time_listener():
            self._unregister_time_changed_listener()
            return
        
        # This is called when playback mode is exited (as well as when scrubbing is released, which
        # we don't care about).  Register the time changed listener, which we only use when not in
        # playback.
        self._register_time_changed_listener()

        # Make sure we refresh to show the state when playback stopped.
        self.callback()

class RestorableWindow(object):
    """
    This is a helper for creating a QT window that can be saved to the panel layout and restored when
    Maya loads.
    """
    def __init__(self, window_class, plugins=None, uiScript=None):
        self.ui = None
	self.window_class = window_class
        self.plugins = plugins
        self.uiScript = uiScript

    def _open_ui(self, restore):
        if restore:
            # We're being reopened, and a layout has already been created.
            restored_control = omui.MQtUtil.getCurrentParent()

        if self.ui is None:
            self.ui = self.window_class()
            def closed():
                self.ui = None
            self.ui.destroyed.connect(closed)

        if restore:
            # We're restoring into an existing layout.  Just add the control that was created
            # for us, and show() will be called automatically.
            ptr = omui.MQtUtil.findControl(self.ui.objectName())
            omui.MQtUtil.addWidgetToMayaLayout(long(ptr), long(restored_control))
            return

        # Disable retain, or we won't be able to create the window again after reloading the script
        # with an "Object's name 'DialogWorkspaceControl' is not unique" error.
        #
        # Watch out: this function has *args and *kwargs which shouldn't be there, which causes it to
        # silently eat unknown parameters instead of throwing an error.
        self.ui.setDockableParameters(dockable=True, retain=False,
                plugins=self.plugins, uiScript=self.uiScript )

        # If we just set plugins (which is really workspaceControl -requiredPlugin), the control
        # will be closed on launch.  We need to enable checksPlugins too to work around this.
        control_name = self.ui.objectName() + 'WorkspaceControl'
        pm.workspaceControl(control_name, e=True, checksPlugins=True)

        self.ui.show()

    def show(self):
        self._open_ui(restore=False)

    def hide(self):
        """
        Hide the UI.
        """
        if self.ui is not None:
            self.ui.hide()

    def close(self):
        if self.ui is None:
            return

        self.ui.close()
        self.ui = None

    def restore(self):
        """
        This is called by Maya via uiScript when a layout is restored.
        """
        self._open_ui(True)

@contextlib.contextmanager
def undo():
    """
    Run a block of code in an undo block.
    """
    pm.undoInfo(openChunk=True)
    try:
        yield
    finally:
        pm.undoInfo(closeChunk=True)

@contextlib.contextmanager
def without_undo():
    """
    Run a block of code with undo disabled.

    This should only be used by operations that have no actual effect on the scene.
    It's useful if a script makes temporary changes or nodes in the scene and cleans
    them up when it's done, to avoid creating pointless undo chunks.
    """
    undo_state = pm.undoInfo(q=True, state=True)
    pm.undoInfo(stateWithoutFlush=False)
    try:
        yield
    finally:
        pm.undoInfo(stateWithoutFlush=undo_state)

@contextlib.contextmanager
def temporary_namespace():
    """
    Create a temporary namespace, and delete the namespace and all of its contents at the end of
    the block.

    The allows creating temporary nodes, guaranteeing that they'll be deleted when the block ends.
    """
    try:
        # Create a temporary namespace to work in.  This lets us clean up when we're done by just deleting
        # the whole namespace.
        old_namespace = pm.namespaceInfo(currentNamespace=True)
        temporary_namespace = ':' + pm.namespace(add='temp#')
        pm.namespace(setNamespace=temporary_namespace)

        yield
    finally:
        # Delete the temporary namespace.
        pm.namespace(setNamespace=old_namespace)
        pm.namespace(rm=':' + temporary_namespace, deleteNamespaceContent=True)

@contextlib.contextmanager
def disable_auto_keyframe():
    """
    Disable auto-keyframe within a with block.
    """
    original_auto_keyframe = pm.autoKeyframe(q=True, state=True)
    try:
        pm.autoKeyframe(state=False)
        yield
    finally:
        pm.autoKeyframe(state=original_auto_keyframe)

def load_plugin(plugin_name, required=True):
    """
    Load plugin_name, if available.  If required is true and the plugin isn't available, raise RuntimeError.

    pm.loadPlugin() is slow if called when a plugin is already loaded.  This checks if the
    plugin is loaded to avoid that.
    """
    if not pm.pluginInfo(plugin_name, q=True, loaded=True):
        try:
            pm.loadPlugin(plugin_name, quiet=True)
        except RuntimeError as e:
            pass

    if not pm.pluginInfo(plugin_name, q=True, registered=True):
        if required:
            raise RuntimeError('Plugin "%s" isn\'t available.' % plugin_name)
        return False
    return True

def copy_weights_to_skincluster(src_attr, skin_cluster, shape):
    src_indices = src_attr.getArrayIndices()
    if not src_indices:
        log.warning('Input has no deformer weights: %s', src_attr)
        return False

    src_values = src_attr.get()
    src_index_count = max(src_indices)+1
    
    weights_array = om.MDoubleArray(src_index_count)

    # Initialize all weights to 1, which is the default mask weight for values not
    # in the array.
    for index in xrange(src_index_count):
        weights_array[index] = 1

    for index, value in zip(src_indices, src_values):
        weights_array[index] = value

    skin_cluster.setWeights(shape, [0], weights_array, False)

    return True

def lock_attr(attr, lock='lock'):
    """
    If lock is 'lock', lock attr and hide it in the CB.  This is for removing attributes
    like translation on control nodes, where we don't want it cluttering the channel box.

    If lock is "lock_visible", lock attr, but leave it in the CB.  This is for attributes
    we don't want modified, but which are on nodes that aren't normally selected by the
    user, like alignment nodes.  Leaving these in the channel box is convenient if they
    need to be unlocked later, since the AE UI for doing this is cumbersome.

    If lock is 'hide', hide it in the CB and make it unkeyable, but don't lock it.
    We do this with the transform of control nodes which are visible in the viewport
    but whose position doesn't matter, so you can still move them around and put them
    where you want, without cluttering the CB.

    If lock is "unkeyable", make it unkeyable but leave it in the CB.  This is for
    internal nodes where the property is meaningful and which we need unlocked, but
    that shouldn't be keyed by the user.

    It's important to mark nodes under the Rig hierarchy as unkeyable or locked
    if they're not user controls.  This prevents them from being added to character
    sets and auto-keyed, which removes a huge amount of clutter.  It also prevents
    accidental bad changes, such as using "preserve children" and accidentally moving
    an alignment node when you think you're moving a control.
    """
    if lock == 'lock':
        pm.setAttr(attr, lock=True, cb=False, keyable=False)
    elif lock == 'lock_visible':
        pm.setAttr(attr, lock=True, cb=True, keyable=False)
    elif lock == 'hide':
        pm.setAttr(attr, lock=False, cb=False, keyable=False)
    elif lock == 'unkeyable':
        pm.setAttr(attr, lock=False, cb=True, keyable=False)
    elif lock == 'keyable':
        pm.setAttr(attr, lock=False, cb=False, keyable=True)
    else:
        raise RuntimeError('Invalid lock state: %s' % lock)

def lock_translate(node, lock='lock'):
    for attr in ('translateX', 'translateY', 'translateZ'):
        try:
            lock_attr(node.attr(attr), lock=lock)
        except pm.MayaAttributeError:
            pass

def lock_rotate(node, lock='lock'):
    for attr in ('rotateX', 'rotateY', 'rotateZ'):
        try:
            lock_attr(node.attr(attr), lock=lock)
        except pm.MayaAttributeError:
            pass

def lock_scale(node, lock='lock'):
    for attr in ('scaleX', 'scaleY', 'scaleZ'):
        try:
            lock_attr(node.attr(attr), lock=lock)
        except pm.MayaAttributeError:
            pass

def lock_trs(node, lock='lock'):
    lock_translate(node, lock=lock)
    lock_rotate(node, lock=lock)
    lock_scale(node, lock=lock)

def create_attribute_proxy(node, attr):
    """
    Create a proxy for attr on node.  Return the new attribute.
    """
    # Be sure to assign both the long and short name.  Being inconsistent with the
    # original attribute can lead to issues with the CB.
    short_name = pm.attributeQuery(attr.attrName(), node=attr.node(), shortName=True)
    long_name = pm.attributeQuery(attr.attrName(), node=attr.node(), longName=True)
    pm.addAttr(node, ln=long_name, sn=short_name, proxy=attr)
    return node.attr(long_name)
    
def add_attr(nodes, name, *args, **kwargs):
    # Add the attribute to the first node.
    pm.addAttr(nodes[0], ln=name, *args, **kwargs)
    attr = nodes[0].attr(name)

    # If there's more than one node, add proxies to the rest.
    for node in nodes[1:]:
        create_attribute_proxy(node, attr)

    return attr

from pymel.tools.py2mel import py2melProc as origPy2melProc
def py2melProc(returnType='', procName=None, argTypes=None):
    """
    A wrapper t make pymel's py2melProc work properly as a decorator.
    
    Note that py2melProc is only partially implemented and can only be used for very
    simple cases.
    """
    def wrapper(function):
        function.mel_proc_name = origPy2melProc(function, returnType=returnType, procName=procName, argTypes=argTypes)
        return function
    return wrapper

# This set of helpers allows temporarily setting attributes, optionVars, etc., and
# restoring them to their original state later.
class SetAndRestore(object):
    def __init__(self, value=None):
        self.old_value = self.get()
        if value is not None:
            self.set(value)

    def restore(self):
        self.set(self.old_value)

class SetAndRestoreAttr(SetAndRestore):
    ConnectionWrapper = namedtuple('ConnectionWrapper', ['connection', 'value'])
            
    def __init__(self, attr, value=None, optional=False):
        self.attr = pm.PyNode(attr)
        self.optional = optional
        super(SetAndRestoreAttr, self).__init__(value)

    def __str__(self):
        return 'SetAndRestoreAttr(%s)' % self.attr

    def get(self):
        try:
            # See if this node is connected and needs to be disconnected to set the value.
            connections = self.attr.listConnections(s=True, d=False, p=True)
            assert len(connections) < 2 # can't have multiple inputs
            if connections:
                connection = connections[0]
                connection.disconnect(self.attr)
            else:
                connection = None

            # Get the value.
            value = self.attr.get()

            # Work around weirdness with some string attributes, like defaultRenderGlobals.preRenderMel.
            # These return None if they've never been set before, and if we set it to something, we
            # have no way to restore the original value, so restore the empty string instead.
            if value is None:
                attr_type = self.attr.get(type=True)

                # I've only seen this with strings.
                assert attr_type == 'string'

                value = ''

            # Include the original connection in the value, if any, so we can restore it later.
            # Wrap this in a small helper class, so we can distinguish it.
            return self.ConnectionWrapper(connection, value)
        except (pm.MayaNodeError, pm.MayaAttributeError):
            if self.optional:
                return None
            raise

    def set(self, value):
        try:
            connection = None

            if isinstance(value, self.ConnectionWrapper):
                # If value is a ConnectionWrapper, it contains both the value and an optional connection
                # to restore.  This is what we use in this class to restore values.
                connection = value.connection
                value = value.value
            elif isinstance(value, pm.general.Attribute):
                # If this is an attribute, connect to it.
                connection = value
                value = None
            else:
                # Otherwise, this is the value to set.
                pass

            # Restore the value.
            if value is not None:
                pm.setAttr(self.attr, value)

            if connection is not None:
                connection.connect(self.attr)
        except (pm.MayaNodeError, pm.MayaAttributeError):
            if self.optional:
                return
            raise

class SetAndRestoreOptionVar(SetAndRestore):
    def __init__(self, var, value=None):
        self.var = var
        super(SetAndRestoreOptionVar, self).__init__(value)

    def __str__(self):
        return 'SetAndRestoreOptionVar(%s)' % self.var

    def get(self):
        if not pm.optionVar(exists=self.var):
            return None
        return pm.optionVar(q=self.var)

    def set(self, value):
        if value is None:
            pm.optionVar(remove=self.var)
        else:
            pm.optionVar(sv=(self.var, value))

class SetAndRestoreCmd(SetAndRestore):
    def __init__(self, cmd, key, value=None, obj=None):
        """
        obj specifies an object name, if needed, eg. pm.cmd(obj, e=True, flag=value).
        If obj is specified, e=True will be added automatically.
        """
        self.cmd = cmd
        self.key = key
        self.obj = obj

        super(SetAndRestoreCmd, self).__init__(value)

    def __str__(self):
        return 'SetAndRestoreCmd(%s)' % self.cmd

    def get(self):
        args = []
        kwargs = { 'q': True }
        if self.obj is not None:
            args.append(self.obj)
        if self.key is not None:
            kwargs[self.key] = True
        result = self.cmd(*args, **kwargs)

        # Grr.  Why does this return an array?
        if self.cmd is pm.renderSetupLocalOverride:
            result = result[0]
        return result
    
    def set(self, value):
        args = []
        kwargs = {}
        if self.obj is not None:
            args.append(self.obj)
            kwargs['e'] = True

        if self.key is not None:
            # eg. pm.ogs(pause=True)
            kwargs[self.key] = value
        else:
            # eg. pm.currentTime(10)
            args.append(value)
        self.cmd(*args, **kwargs)

class SetAndRestorePauseViewport(SetAndRestoreCmd):
    """
    Pause and unpause the viewport.
    """
    def __init__(self, value=None):
        super(SetAndRestorePauseViewport, self).__init__(pm.ogs, 'pause', value)
        
    def set(self, value):
        # Work around ogs.pause being inconsistent with other Maya commands: instead of
        # ogs -pause 1 pausing and -pause 0 unpausing, -pause 1 toggles the current value.
        if self.get() != value:
            super(SetAndRestorePauseViewport, self).set(True)

from maya.app.renderSetup.model import renderSetup, renderLayer
class SetAndRestoreActiveRenderSetup(SetAndRestore):
    """
    Temporarily change the active render setup.
    """
    def get(self):
        return renderSetup.instance().getVisibleRenderLayer()

    def set(self, value):
        # value can be a RenderLayer object, the name of a render layer, or None
        # to switch to the default layer.
        rs = renderSetup.instance()    
        if value is None:
            value = rs.getDefaultRenderLayer()
        elif not isinstance(value, renderLayer.RenderLayer):
            # This throws a generic Exception if 
            value = rs.getRenderLayer(value)

        rs.switchToLayer(value)

@contextlib.contextmanager
def restores(name='undo_on_exception'):
    """
    Run a block of code, restoring a list of scene changes at the end.
    """
    try:
        restores = []
        yield restores
    finally:
        # Restore changes.
        for restore in reversed(restores):
            restore.restore()

class _FilterMFnWarnings(object):
    def filter(self, record):
        return 'Could not create desired MFn' not in record.msg

def quiet_pymel_warnings(func):
    """
    PyMel prints a lot of spurious warnings like this when accessing nodes:
        
    Warning: pymel.core.general : Could not create desired MFn. Defaulting to MFnDependencyNode.
    
    This obscures actual warnings.  This wrapper temporarily silences this warning.
    The logger will be returned to normal when we return.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        pymel_logger = logging.getLogger('pymel.core.general')
        temp_filter = _FilterMFnWarnings()
        try:
            pymel_logger.addFilter(temp_filter)
            return func(*args, **kwargs)
        finally:
            pymel_logger.removeFilter(temp_filter)
    return wrapper

def create_or_replace_runtime_command(name, *args, **kwargs):
    """
    A wrapper around pm.runTimeCommand that deletes the command if it already exists
    before running the command.
    """
    # Delete the command if it already exists.
    if pm.runTimeCommand(name, exists=True):
        pm.runTimeCommand(name, e=True, delete=True)
    pm.runTimeCommand(name, *args, **kwargs)
      

def scene_framerate():
    """
    Return the scene framerate.
    """
    # Why does currentUnit return strings?  Nobody wants to be told "ntsc" when they ask for the framerate.
    return pm.mel.eval('getCadenceLineWorkingUnitInFPS')

@contextmanager
def scene_frame(frame):
    """
    Temporarily evaluate the scene at the given time.
    """
    mtime = om.MTime()
    mtime.setValue(frame)
    with MDGContextGuard(om.MDGContext(mtime)) as guard:
        yield guard

def create_file_node(name=None):
    """
    Create a file node, with a place2dTexture node attached.

    This is similar to importImageFile, but that function spews a lot of junk to
    the console.
    """
    texture = pm.shadingNode('file', asTexture=True, isColorManaged=True, ss=True)
    if name is not None:
        pm.rename(texture, name)

    place = pm.shadingNode('place2dTexture', asUtility=True, ss=True)
    place.coverage.connect(texture.coverage)
    place.translateFrame.connect(texture.translateFrame)
    place.rotateFrame.connect(texture.rotateFrame)
    place.mirrorU.connect(texture.mirrorU)
    place.mirrorV.connect(texture.mirrorV)
    place.stagger.connect(texture.stagger)
    place.wrapU.connect(texture.wrapU)
    place.wrapV.connect(texture.wrapV)
    place.repeatUV.connect(texture.repeatUV)
    place.offset.connect(texture.offset)
    place.rotateUV.connect(texture.rotateUV)
    place.noiseUV.connect(texture.noiseUV)
    place.vertexUvOne.connect(texture.vertexUvOne)
    place.vertexUvTwo.connect(texture.vertexUvTwo)
    place.vertexUvThree.connect(texture.vertexUvThree)
    place.vertexCameraOne.connect(texture.vertexCameraOne)
    place.outUV.connect(texture.uv)
    place.outUvFilterSize.connect(texture.uvFilterSize)
    return texture, place

def sync_render_setup_layer():
    """
    Sync the current render layer.

    This is the same as pressing the sync buttin in the RS window, and updates any
    overrides that haven't yet been applied.
    """
    # This isn't a documented API.  Import this here, so if this API changes it only
    # breaks calls to this function and not all of maya_helpers.
    import maya.app.renderSetup.model.renderSetup as renderSetupModel

    render_setup_model = renderSetupModel.instance()
    visible_layer = render_setup_model.getVisibleRenderLayer()
    if visible_layer is None:
        return

    render_setup_model.switchToLayer(visible_layer)

def open_scene_in_explorer():
    """
    Show the current scene in a File Explorer window.

    This is only supported on Windows.
    """
    scene_path = cmds.file(q=True, sceneName=True)
    if not scene_path:
        log.info('The scene must be saved first')
        return
        
    util.show_file_in_explorer(scene_path)

def setup_runtime_commands():
    create_or_replace_runtime_command('zMatchPosition', category='Menu items.Command.Modify',
        label='Match Position',
        annotation='Match the translation and rotation of selected objects to the last-selected object.',
        command='matchTransform -pos -rot', commandLanguage='mel')

