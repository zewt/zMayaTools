from pymel import core as pm

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

