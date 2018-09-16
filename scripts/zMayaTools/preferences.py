from zMayaTools import maya_helpers
from pymel import core as pm
from contextlib import contextmanager

# This handles creating a preference page in the preferences window.
#
# Modules can register preferences blocks, which will all appear in the same zMayaTools
# preferences tab.  If a module is unloaded it'll unregister its preferences block, so
# only preferences for loaded modules will appear.
_layout_name = 'zMayaToolsPrefs'

@contextmanager
def _set_parent_layout():
    """
    Run a with block with our layout set as the UI parent.

    If the UI parent doesn't exist, the block won't be executed.
    """
    if not pm.window(pm.mel.globals['gPreferenceWindow'], exists=True):
        return
    if pm.columnLayout(_layout_name, q=True, numberOfChildren=True) == 0:
        return

    pm.setParent(_layout_name)
    yield

class PreferencesTabManager(object):
    """
    This singleton keeps track of registered PreferenceHandler, and does the
    main work of setting up the preferences tab.
    """
    def __init__(self):
        self.preference_handlers = []

    @classmethod
    def get(cls):
        if hasattr(cls, '_singleton'):
            return cls._singleton
        cls._singleton = PreferencesTabManager()
        return cls._singleton

    def all_optvars_to_window(self):
        for pref_handler in self.preference_handlers:
            pref_handler.all_optvars_to_window()

    def create_layout(self):
        pm.frameLayout(labelVisible=False, borderVisible=False, marginWidth=10, marginHeight=10)
        pm.columnLayout(_layout_name, adj=True)

    def backup_options(self):
        """
        Temporarily save the current values of our options.

        The values can be restored with restore_options.
        """
        for pref_handler in self.preference_handlers:
            pref_handler.backup_options()

    def restore_options(self):
        """
        Restore the values of options saved with a call to backup_options.
        """
        for pref_handler in self.preference_handlers:
            pref_handler.restore_options()

    def _update_window_registration(self):
        """
        Register or unregister our preferences tab if needed.

        We only register our window if we have registered preference handlers, so we
        unregister if all modules that have prefs are unregistered.
        """
        if self.preference_handlers:
            self._register_prefs_window()
        else:
            self._unregister_prefs_window()

    def _register_prefs_window(self):
        # If we call addCustomPrefsTab when we're already registered it'll add a duplicate,
        # so we have to check first.
        if u'zMayaToolsPrefs_CreateWidgets' in pm.mel.globals['gPrefsCustomTabCreate']:
            return
        
        pm.mel.eval("""
            addCustomPrefsTab(
                "zMayaToolsPrefs_CreateWidgets",
                "zMayaToolsPrefs_CreateLayout",
                "zMayaToolsPrefs_SetWindowToOptions",
                "zMayaToolsPrefs_HoldState",
                "zMayaToolsPrefs_ResetOptions",
                "zMayaTools Preferences",
                "    zMayaTools");
        """);

    def _unregister_prefs_window(self):
        pm.mel.eval("""deleteCustomPrefsTab("zMayaToolsPrefs_CreateWidgets");""")

    def create_widgets(self):
        pm.setParent(pm.mel.globals['gPreferenceWindow'])

        # Stop if this already exists.
        if pm.columnLayout(_layout_name, q=True, numberOfChildren=True) > 0:
            return

        # Create the UI
        pm.setParent(_layout_name)
        pm.setUITemplate('prefsTemplate', pushTemplate=True)
        try:
            # This is used to force the width to fill the window
            pm.separator(style='none', h=1)

            pm.frameLayout(label='zMayaTools')
            pm.columnLayout(adj=True)

            for pref_handler in self.preference_handlers:
                pref_handler.create_widgets()
            
        finally:
            pm.setUITemplate(popTemplate=True)

        # Load the optvars into the window.
        self.all_optvars_to_window()

    def register_options(self, preference_handler):
        """
        Register a PreferenceHandler.

        This is normally called through PreferenceHandler.register().
        """
        if preference_handler in self.preference_handlers:
            return

        self.preference_handlers.append(preference_handler)
        self.preference_handlers.sort(key=lambda item: item.name)
        self._update_window_registration()

    def unregister_options(self, preference_handler):
        """
        Unregister a PreferenceHandler.

        This is normally called through PreferenceHandler.unregister().
        """
        if preference_handler not in self.preference_handlers:
            return

        self.preference_handlers.remove(preference_handler)
        self._update_window_registration()

class PreferenceHandler(object):
    """
    A PreferenceHandler is created to handle a single block in the preferences
    tab, which sets any number of options.
    """
    def __init__(self, name, create_widgets):
        self.name = name
        self.options = {}
        self.saved_options = {}
        self.create_widgets = create_widgets

    def add_option(self, optvar, widget_name):
        self.options[optvar.name] = _Option(optvar, widget_name)

    def optvar_to_window(self, name):
        self.options[name].optvar_to_window()

    def window_to_optvar(self, name):
        self.options[name].window_to_optvar()

    def all_optvars_to_window(self):
        for option in self.options.values():
            option.optvar_to_window()

    def get_change_callback(self, name):
        assert name in self.options
        def field_changed(unused=None):
            self.window_to_optvar(name)
        return field_changed

    def register(self):
        """
        Register this PreferenceHandler, so it will appear in the preferences tab.
        """
        PreferencesTabManager.get().register_options(self)
        
    def unregister(self):
        """
        Unregister this PreferenceHandler, so it will no longer appear in the preferences tab.
        """
        PreferencesTabManager.get().unregister_options(self)

    def backup_options(self):
        for name, option in self.options.items():
            self.saved_options[name] = option.optvar.value

    def restore_options(self):
        for name, option in self.options.items():
            option.optvar.value = self.saved_options[name]

class _Option(object):
    def __init__(self, optvar, widget_name):
        self.optvar = optvar
        self.widget_name = widget_name

    def optvar_to_window(self):
        with _set_parent_layout():
            if self.optvar.var_type == 'string':
                pm.textField(self.widget_name, e=True, text=self.optvar.value)
            elif self.optvar.var_type == 'bool':
                pm.checkBoxGrp(self.widget_name, e=True, value1=self.optvar.value)
            else:
                raise Exception('Unknown optvar type %s for %s' % (self.optvar.var_type, self.optvar.name))

    def window_to_optvar(self):
        with _set_parent_layout():
            if self.optvar.var_type == 'string':
                if not pm.textField(self.widget_name, exists=True):
                    return
                self.optvar.value = pm.textField(self.widget_name, q=True, text=True)
            elif self.optvar.var_type == 'bool':
                self.optvar.value = pm.checkBoxGrp(self.widget_name, q=True, value1=True)
            else:
                raise Exception('Unknown optvar type %s for %s' % (self.optvar.var_type, self.optvar.name))

# The actual interface to Maya's preference tab is with MEL calls.  Register our
# functions as simple wrappers for the above.

@maya_helpers.py2melProc(procName='zMayaToolsPrefs_SetWindowToOptions')
def zMayaToolsPrefs_SetWindowToOptions():
    """
    Set the preference window to the current value of our options.
    """
    PreferencesTabManager.get().all_optvars_to_window()

@maya_helpers.py2melProc(procName='zMayaToolsPrefs_CreateLayout')
def zMayaToolsPrefs_CreateLayout():
    PreferencesTabManager.get().create_layout()

@maya_helpers.py2melProc(procName='zMayaToolsPrefs_CreateWidgets')
def zMayaToolsPrefs_CreateWidgets():
    PreferencesTabManager.get().create_widgets()

@maya_helpers.py2melProc(procName='zMayaToolsPrefs_HoldState')
def zMayaToolsPrefs_HoldState(mode):
    if mode == 'save':
        PreferencesTabManager.get().backup_options()
    elif mode == 'restore':
        PreferencesTabManager.get().restore_options()

@maya_helpers.py2melProc(procName='zMayaToolsPrefs_ResetOptions')
def zMayaToolsPrefs_ResetOptions():
    optvars.reset()

