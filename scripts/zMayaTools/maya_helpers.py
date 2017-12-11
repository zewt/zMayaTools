import time
from pymel import core as pm
from zMayaTools import util

from zMayaTools import maya_logging
log = maya_logging.get_log()

class OptionVars(object):
    """
    A helper to simplify accessing Maya optionvars.

    This supports ints, floats and strings (arrays aren't supported).
    """
    _types = {
        'int': int,
        'float': (int, float),
        'string': basestring,
    }
    def __init__(self):
        self.keys = {}
        pass

    def add(self, name, var_type, default):
        assert var_type in self._types
        self.keys[name] = {
            'name': name,
            'type': var_type,
            'default': default,
        }

    def reset(self):
        for key, data in self.keys.items():
            pm.optionVar(remove=key)

    def __setitem__(self, name, value):
        data = self.keys.get(name)
        assert data is not None, 'Unknown option var name %s' % name

        expected_class = self._types[data['type']]
        assert isinstance(value, expected_class), 'Option %s has type %s and can\'t be set to "%s"' % (name, data['type'], value)

        kwargs = {}
        arg = data['type'] + 'Value' # intValue, floatValue or stringValue
        kwargs[arg] = (name, value)
        pm.optionVar(**kwargs)

    def __getitem__(self, name):
        data = self.keys.get(name)
        assert data is not None, 'Unknown option var name %s' % name

        if not pm.optionVar(exists=name):
            return data['default']

        value = pm.optionVar(q=name)

        # Make sure the value is of the type we expect.  If it's not, return the default instead.
        expected_class = self._types[data['type']]
        if not isinstance(value, expected_class):
            return data['default']

        return value

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
        pm.button(pm.mel.eval('getOptionBoxApplyBtn()'), edit=True, command=lambda unused: self.option_box_apply())
        pm.button(pm.mel.eval('getOptionBoxApplyAndCloseBtn()'), edit=True, command=lambda unused: self.option_box_apply_and_close())
    
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
        
    def option_box_apply_and_close(self):
        self.option_box_apply()
        pm.mel.eval('hideOptionBox()')

    def option_box_reset(self):
        self.optvars.reset()
        self.option_box_load()

class ProgressWindowMaya(util.ProgressWindow):
    main_progress_value = 0

    def __init__(self):
        super(ProgressWindowMaya, self).__init__()
        self.window = None
        self.last_refresh = None

    def show(self, title, total_progress_values):
        super(ProgressWindowMaya, self).show(title, total_progress_values)

        self.window = pm.window(title=title)
        pm.columnLayout()
        
        pm.text('status', w=300, align='left')
        self.progressControl1 = pm.progressBar(maxValue=total_progress_values, width=300)

        pm.text('status2', w=300, align='left')
        self.progressControl2 = pm.progressBar(maxValue=100, width=300, pr=5)
        pm.button(label='Cancel', command=self._cancel_clicked)
        pm.showWindow(self.window)
        pm.refresh()

    def hide(self):
        super(ProgressWindowMaya, self).hide()
        
        pm.deleteUI(self.window)
        self.window = None

    def _cancel_clicked(self, unused):
        log.debug('Cancel button clicked')
        self.cancel()

    def set_main_progress(self, job):
        super(ProgressWindowMaya, self).set_main_progress(job)
        
        # Reset the sub-task refresh timer when we change the main task.
        self.last_refresh = None
        self.last_task_percent = 0
        
        log.info(job)

        if self.window is None:
            return

        pm.text('status', e=True, label=job)
        pm.text('status2', e=True, label='')
        pm.progressBar(self.progressControl1, edit=True, progress=self.main_progress_value)
        pm.progressBar(self.progressControl2, edit=True, progress=0)

        # Hack: The window sometimes doesn't update if we don't call this twice.
        pm.refresh()
        pm.refresh()

        self.main_progress_value += 1

    def set_task_progress(self, label, percent=None, force=False):
        super(ProgressWindowMaya, self).set_task_progress(label, percent=percent, force=force)

#        log.debug(label)

        if percent is None:
            percent = self.last_task_percent
            
        self.last_task_percent = percent

        if self.window is None:
            return

        # Only refresh if we haven't refreshed in a while.  This is slow enough that it
        # can make the import slower if we're showing fine-grained progress.
        if not force and self.last_refresh is not None and time() - self.last_refresh < 0.1:
            return

        self.last_refresh = time.time()

        pm.text('status2', e=True, label=label)
        pm.progressBar(self.progressControl2, edit=True, progress=round(percent * 100))

        pm.refresh()
        pm.refresh()

