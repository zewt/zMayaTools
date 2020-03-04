import copy, six
from maya import OpenMaya as om
import pymel.core as pm
from pprint import pprint
from maya.app.general.shelfEditorWindow import shelfEditorWindow
from zMayaTools import maya_helpers, preferences
try:
    from importlib import reload
except ImportError:
    pass

from zMayaTools import maya_logging
log = maya_logging.get_log()

gMainWindow = pm.mel.eval("$x = $gMainWindow")
gShelfTopLevel = pm.mel.eval("$x = $gShelfTopLevel");

separator = object()

# A comma-separated list of shelves to display as menus.
pinned_shelves = maya_helpers.OptionVar('shelvesPinnedToMenu', 'string', '')

# If true, we'll also show a "Shelves" menu, with all shelves as submenus.
show_shelf_menu = maya_helpers.OptionVar('zMayaToolsShowMainShelfMenu', 'bool', False)

class Shelf(object):
    """
    This helps access the contents of a Maya shelf.
    """
    def __init__(self, path, label):
        self.path = path
        self.label = label
        self._buttons = None

    def __repr__(self):
        return 'Shelf(%s)' % self.path
        
    def load_shelf(self):
        """
        Ensure the shelf is loaded.  Shelves are loaded the first time they're viewed, so we can't
        query shelves that haven't been loaded yet.
        """
        # These are 1-indexed for some reason.
        pm.mel.eval('loadShelf %i' % (self.shelf_idx+1))

    def refresh(self):
        self._buttons = None

    @property
    def buttons(self):
        if self._buttons is not None:
            return self._buttons

        # The shelf needs to be loaded to get this info.            
        self.load_shelf()

        try:
            buttons = pm.layout(self.path, q=True, childArray=True)
        except RuntimeError:
            # This raises RuntimeError if the shelf no longer exists.
            return []

        if buttons is None:
            return []
            
        self._buttons = []
        for shelf_button in buttons:
            if pm.objectTypeUI(shelf_button) == 'shelfButton':
                self.buttons.append(shelf_button)
            elif pm.objectTypeUI(shelf_button) == 'separator':
                self.buttons.append(separator)
        return self._buttons
                
    @property
    def shelf_idx(self):
        """
        Return the index of this shelf.

        This can change after we're created, eg. if shelves are reordered.
        """
        shelves = pm.tabLayout(gShelfTopLevel, q=True, childArray=True)
        try:
            return shelves.index(self.path)
        except IndexError:
            return -1

    @classmethod
    def get_shelves(cls):
        """
        Return an array of all shelves, as Shelf objects.
        """
        labels = pm.tabLayout(gShelfTopLevel, q=True, tabLabel=True)
        shelves = pm.tabLayout(gShelfTopLevel, q=True, childArray=True)
        results = []
        for idx, (shelf, label) in enumerate(zip(shelves, labels)):
            if pm.objectTypeUI(shelf) != 'shelfLayout':
                continue
                
            results.append(cls(shelf, label))
        return results

    def select_shelf(self):
        """
        Select this shelf in the main shelf.

        Return true on success, false if the shelf no longer exists.
        """
        idx = self.shelf_idx
        if idx == -1:
            log.warning('Shelf %s no longer exists', self.path)
            return False

        pm.tabLayout(gShelfTopLevel, edit=True, selectTabIndex=idx+1)
        return True

    def show_in_shelf_editor(self, button):
        """
        Open the shelf editor, and view the script for the shelf button with the given name.
        """
        # The shelf editor only works on the currently-selected shelf.
        if not self.select_shelf():
            return

        wnd = shelfEditorWindow()
        wnd.create(button, 2)

    def show_popup_in_shelf_editor(self, button, popup):
        """
        Open the shelf editor, and view the script for a popup in a shelf button.
        """
        # The shelf being edited needs to be selected in the shelf.
        if not self.select_shelf():
            return

        wnd = shelfEditorWindow()
        wnd.create(button, 4)

        # Find the index of the popup.
        popup_names = wnd.updateMenuItemList()
        popup_name = popup.split('|')[-1]
        try:
            idx = popup_names.index(popup_name)
        except ValueError:
            return

        wnd.updateMenuItemList(idx+1)

class Menu(object):
    """
    A helper for creating menus.

    Creating menus is cumbersome, since there's a separate API for top-level menus
    and submenus even though they're functionally identical.
    """
    def update_menu(self, unused1, unused2):
        self.update_func(self.menu_item)

    def __init__(self, name, label, update_func, parent_menu=None):
        self.is_top_level_menu = parent_menu is None
        self.update_func = update_func

        if self.is_top_level_menu:
            pm.setParent(gMainWindow)
            self.menu_item = name
            if not pm.menu(name, q=True, exists=True):
                pm.menu(name, tearOff=True)
            pm.menu(name, e=True, label=label)
            pm.menu(name, e=True, postMenuCommand=self.update_menu)
        else:
            pm.setParent(parent_menu, menu=True)
            self.menu_item = pm.menuItem(name, label=label, subMenu=True, tearOff=True)
            pm.menuItem(self.menu_item, e=True, postMenuCommand=self.update_menu)
            pm.setParent("..", menu=True)

        # Set a callback to populate the menu when it's opened.
        if self.is_top_level_menu:
            pm.menu(self.menu_item, e=True, postMenuCommand=self.update_menu)
        else:
            pm.menuItem(self.menu_item, e=True, postMenuCommand=self.update_menu)

    def remove(self):
        """
        Remove the menu item.
        """
        if self.is_top_level_menu:
            pm.deleteUI(self.menu_item, menu=True)
        else:
            pm.deleteUI(self.menu_item, menuItem=True)

def get_pinned_shelves():
    value = pinned_shelves.value
    if not value:
        return []
    return value.split(',')

def set_pinned_shelves(shelves):
    pinned_shelves.value = ','.join(shelves)

def get_menu_item_params(source, func):
    """
    Return the arguments to pass to pm.menuItem to create a menu item matching a shelf
    or shelf popup item.  source is the name of the shelf/popup, and func is either pm.shelfButton
    or pm.menuItem.
    """
    properties = ['label', 'image', 'annotation']
    cmd = {}
    for prop in properties:
        kwargs = {}
        kwargs[prop] = True
        cmd[prop] = func(source, q=True, **kwargs)
        
    return cmd

def execute_menu_item(name, button_type):
    """
    Execute a shelf item or popup item by name.

    We query the script at the time the user clicks it, rather than setting the command directly
    on the menu item, so we execute the latest version of the script.  Otherwise, if a menu was
    torn off and the shelf script was modified, clicking the torn off menu would run the old version
    of the script.

    button_type is either pm.shelfButton or pm.menuItem.
    """
    # This is called with an argument when it's executed from the menu, and with no argument
    # if it's executed by pressing G.
    def func(unused=None):
        command = button_type(name, q=True, command=True)
        sourceType = button_type(name, q=True, sourceType=True)

        if sourceType == 'python':
            env = {}
            exec(command, env, env)
        elif sourceType == 'mel':
            pm.mel.eval(command)
        else:
            raise RuntimeError('Unknown sourceType %s' % sourceType)

    return func
 
def get_shelf_submenus(shelf_button):
    popup_menus = pm.shelfButton(shelf_button, q=True, popupMenuArray=True)
    if not popup_menus:
        return []

    popup_menu = popup_menus[0]
    popup_menu_items = pm.popupMenu(popup_menu, q=True, itemArray=True) or []

    # Ignore popup items that are defaults, eg. "Open" and "Edit" that appear in the
    # shelf context menu.
    def is_default_menu_item(popup):
        cmd = pm.menuItem(popup, q=True, command=True)
        return isinstance(cmd, six.string_types) and cmd.startswith('/*dSBRMBMI*/')
    popup_menu_items = [p for p in  popup_menu_items if not is_default_menu_item(p)]

    # popupMenu returns ambiguous paths.  Prefix the path to the popup menu to make
    # sure we query the right thing.
    popup_menu_items = [popup_menu + '|' + item for item in popup_menu_items]

    # Replace any dividers with separator.
    popup_menu_items = [separator if pm.menuItem(p, q=True, divider=True) else p for p in popup_menu_items]
    
    return popup_menu_items

def create_shelf_button_menu(shelf, parent_menu=None):
    """
    Create a menu containing the buttons on a shelf.
    """
    latest_menu_cmds = {}

    def add_shelf_item(parent_menu, menu_cmds, shelf_button):
        # Create a menuItem matching the shelfButton.
        # See if this shelf button has any submenus.
        popup_menu_items = get_shelf_submenus(shelf_button)

        cmd = copy.copy(menu_cmds[shelf_button])

        # Set the command to run.  We always wrap commands, so we can read the current script.
        # This way, we always run the latest version of the script, even if it's in a torn-off
        # menu and the shelf script has been changed.
        cmd['command'] = execute_menu_item(shelf_button, pm.shelfButton)
        cmd['sourceType'] = 'python'

        if popup_menu_items:
            cmd['subMenu'] = True
            cmd['tearOff'] = True

        def add_menu_item(name, cmd, with_option_button=None):
            pm.menuItem(name, **cmd)
            if with_option_button is not None:
                pm.menuItem(name + '_opt', optionBox=True, command=with_option_button)

        if popup_menu_items:
            # We can't show an option box if there's a popup menu.
            option_button_func = None
        else:
            option_button_func = lambda unused: shelf.show_in_shelf_editor(shelf_button)

        add_menu_item(shelf_button, cmd, with_option_button=option_button_func)

        # If this shelf button has popup menu items, add them in a submenu.
        for popup_menu_item in popup_menu_items:
            if popup_menu_item is separator:
                pm.menuItem(divider=True)
                continue

            subcmd = copy.copy(menu_cmds[popup_menu_item])

            # This function is just to capture popup_menu_item:
            def add_submenu_item(popup_menu_item):
                subcmd['command'] = execute_menu_item(popup_menu_item, pm.menuItem)
                subcmd['sourceType'] = 'python'
                add_menu_item(popup_menu_item, subcmd, with_option_button=lambda unused: shelf.show_popup_in_shelf_editor(shelf_button, popup_menu_item))
                
            add_submenu_item(popup_menu_item)

        if popup_menu_items:
            pm.setParent('..', menu=True)
            
    def update_shelf_submenu(parent_menu):
        """
        Populate a shelf submenu with the contents of a shelf.
        """
        shelf.refresh()

        # Gather the menu items, including submenus.
        pm.setParent(parent_menu, menu=True)
        menu_cmds = {}
        for shelf_button in shelf.buttons:
            if shelf_button is separator:
                continue
            menu_cmds[shelf_button] = get_menu_item_params(shelf_button, pm.shelfButton)

            popup_menu_items = get_shelf_submenus(shelf_button)
            for popup_menu_item in popup_menu_items:
                if popup_menu_item is separator:
                    continue
                menu_cmds[popup_menu_item] = get_menu_item_params(popup_menu_item, pm.menuItem)

            # Store the list of popup menu item names as a dummy entry in menu_cmds.  This
            # won't be looked up by add_shelf_item.  This just makes sure that if the list of
            # popups changes, menu_cmds will be different from latest_menu_cmds and we'll refresh
            # the menu.
            menu_cmds['__popups_%s' % shelf_button] = popup_menu_items

        # If the menu hasn't changed since the last time it was displayed, don't update it.
        # Updating menus is usually fast, but sometimes becomes very slow for no obvious reason.
        if latest_menu_cmds == menu_cmds:
            return

        # Update latest_menu_cmds so we remember the latest update.
        latest_menu_cmds.clear()
        latest_menu_cmds.update(menu_cmds)

        # Clear the menu.
        pm.setParent(parent_menu, menu=True)
        pm.menu(parent_menu, e=True, deleteAllItems=True)

        for shelf_button in shelf.buttons:
            if shelf_button is separator:
                pm.menuItem(divider=True)
            else:
                add_shelf_item(parent_menu, menu_cmds, shelf_button)

    return Menu(shelf.path, shelf.label, update_func=update_shelf_submenu, parent_menu=parent_menu)

def create_shelf_tab_menu(parent_menu=None):
    """
    Create a menu containing all shelves.
    """
    def update_shelf_top_menu(menu):
        """
        Populate the shelves menu with one menu item per shelf tab.
        """
        # Clear the menu so it can be repopulated.
        pm.setParent(menu, menu=True)
        pm.menu(menu, e=True, deleteAllItems=True)

        shelves = Shelf.get_shelves()
    
        for shelf in shelves:
            create_shelf_button_menu(shelf, menu)

    return Menu('ShelfMenu', 'Shelves', update_func=update_shelf_top_menu, parent_menu=parent_menu)


class ShelfMenu(object):
    """
    This class manages creating the menus.
    """
    def __init__(self):
        self.menus = []
        pinned_shelves.add_on_change_listener(self.refresh)
        show_shelf_menu.add_on_change_listener(self.refresh)
        self.refresh()

    def refresh(self, unused=None):
        """
        Recreate all shelf menus.

        This is called on startup, and by pinned_shelves when the user toggles a shelf.
        """
        for menu in self.menus:
            menu.remove()

        self.menus = []

        # Create the top-level shelves menu.
        if show_shelf_menu.value:
            self.menus.append(create_shelf_tab_menu())

        # Create the individual shelf menus.
        pinned_shelves = set(get_pinned_shelves())
        shelves = [shelf for shelf in Shelf.get_shelves() if shelf.path in pinned_shelves]
        for shelf in shelves:
            self.menus.append(create_shelf_button_menu(shelf))

    def remove(self):
        for menu in self.menus:
            menu.remove()
        self.menus = []

        pinned_shelves.remove_on_change_listener(self.refresh)

class _OptionHandler_PinnedShelves(preferences.OptionHandler):
    """
    An OptionHandler to handle syncing the list of shelf checkboxes with the
    pinned_shelves preference.
    """
    def optvar_to_window(self, pref_handler):
        # Update the shelf checkboxes with the saved list of pinned shelves.
        currently_pinned_shelves = set(get_pinned_shelves())
        for shelf_name, checkbox_name in pref_handler.shelf_items:
            pm.checkBoxGrp(checkbox_name, e=True, value1=shelf_name in currently_pinned_shelves)
            
    def window_to_optvar(self, pref_handler):
        # Update the list of pinned shelves from the checkbox list.
        all_shelves = {shelf.label: shelf for shelf in Shelf.get_shelves()}
        
        new_pinned_shelves = []
        for shelf_name, checkbox_name in pref_handler.shelf_items:
            checked = pm.checkBoxGrp(checkbox_name, q=True, value1=True)
            if checked:
                new_pinned_shelves.append(shelf_name)
        set_pinned_shelves(new_pinned_shelves)
        
    @property
    def saved_value(self):
        return pinned_shelves.value

    @saved_value.setter
    def saved_value(self, value):
        pinned_shelves.value = value

def create_preference_handler():
    """
    Create a preferences window block for shelf menus.
    """
    def create_shelves_widget(pref_handler):
        pm.frameLayout(label='Shelf Menus')

        currently_pinned_shelves = set(get_pinned_shelves())
        all_shelves = Shelf.get_shelves()

        # Create a scroller with checkboxes.
        #
        # A textScrollList looks more appropriate, but there seems to be no way to set
        # a single-click-multiple-select mode for that widget.
        pm.scrollLayout(h=150, childResizable=False)
        pm.columnLayout(adj=True)

        pm.checkBoxGrp('zmt_ShowMainShelfMenu',
            numberOfCheckBoxes=1,
            label='',
            label1='Show "Shelves" menu',
            cc=pref_handler.get_change_callback(show_shelf_menu.name))

        shelf_items = []
        for idx, shelf in enumerate(all_shelves):
            name = pm.checkBoxGrp(
                numberOfCheckBoxes=1,
                label='',
                label1=shelf.label,
                cc=pref_handler.get_change_callback(pinned_shelves.name))
            shelf_items.append((shelf.label, name))

        # Store the shelf checbkxes on the handler so we can access them in OptionHandler_PinnedShelves.
        pref_handler.shelf_items = shelf_items
      
    pref_handler = preferences.PreferenceHandler('5_shelf_menus', create_shelves_widget)
    pref_handler.add_option_handler(pinned_shelves.name, _OptionHandler_PinnedShelves())
    pref_handler.add_option(show_shelf_menu, 'zmt_ShowMainShelfMenu')
    return pref_handler

