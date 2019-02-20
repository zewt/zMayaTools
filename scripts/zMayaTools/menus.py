import bisect
import pymel.core as pm
from zMayaTools import maya_helpers, preferences

from zMayaTools import maya_logging
log = maya_logging.get_log()

class _MenuRegistration(object):
    def __init__(self):
        # Menus which currently have their items added:
        self.registered_menus = set()

        self.optvars = maya_helpers.OptionVars()
        self.optvars.add('zMayaToolsShowTopLevelMenu', 'bool', True)

        # When the zMayaToolsShowTopLevelMenu option changes in the preferences window, recreate
        # menus.
        def top_level_option_changed(optvar):
            self.recreate_all_menus()

        self.optvars.get('zMayaToolsShowTopLevelMenu').add_on_change_listener(top_level_option_changed)

        # Create our preferences window block.
        def create_prefs_widget(pref_handler):
            pm.checkBoxGrp('zmt_ShowMenu',
                numberOfCheckBoxes=1,
                label='',
                cw2=(140, 300),
                label1='Show top-level zMayaTools menu',
                cc1=pref_handler.get_change_callback('zMayaToolsShowTopLevelMenu'))
            
        self.preference_handler = preferences.PreferenceHandler('1_menus', create_prefs_widget)
        self.preference_handler.add_option(self.optvars.get('zMayaToolsShowTopLevelMenu'), 'zmt_ShowMenu')

    def _update_preference_registration(self):
        """
        Register our preference window if we have any menus, otherwise unregister it.

        If we have no menus (because no plugins are loaded that add any), it doesn't make
        sense to show the menu preferences, since they won't do anything.
        """
        if self.registered_menus:
            self.preference_handler.register()
        else:
            self.preference_handler.unregister()

    def register_menu(self, menu):
        self.registered_menus.add(menu)
        self._update_preference_registration()

    def unregister_menu(self, menu):
        try:
            self.registered_menus.remove(menu)
        except KeyError:
            pass

        self._update_preference_registration()

    def recreate_all_menus(self):
        """
        Remove and readd all menus.

        This is used to update menus when menu preferences are changed.
        """
        menus = set(self.registered_menus)
        for menu in menus:
            menu.remove_menu_items()

        # Make sure the top-level zMayaTools menu was removed.  It should always be
        # cleaned up as a side-effect of removing all menu items, but if it wasn't
        # then it won't be recreated if the top-level pref has changed.
        try:
            pm.deleteUI('zMayaTools_Menu')
            log.warning('zMayaTools_Menu should have been cleaned up')
        except RuntimeError:
            pass
            
        for menu in menus:
            menu.add_menu_items()

    @property
    def show_top_level_menu(self):
        """
        """
        return self.optvars['zMayaToolsShowTopLevelMenu']

_menu_registration = _MenuRegistration()

def _delete_menu_item(name):
    """
    Delete a menu item.

    Maya is a little silly here and throws an error if it doesn't exist, so
    just ignore that if it happens.
    """
    try:
        pm.deleteUI(name, menuItem=True)
    except RuntimeError:
        pass

class Menu(object):
    """
    A helper for adding and removing menu items.
    """
    def __init__(self):
        self.menu_items = set()
        self.related_items = {}

    @classmethod
    def _get_sorted_insertion_point(cls, name, subMenu, parent):
        # Get the label and submenu flag for the menu items that will be label's siblings.
        class Item(object):
            def __init__(self, label, submenu):
                self.label = label
                self.submenu = submenu

            def __cmp__(self, rhs):
                if self.submenu != rhs.submenu:
                    # self.submenu true comes before self.submenu false.
                    return cmp(not self.submenu, not rhs.submenu)
                if self.label != rhs.label:
                    return cmp(self.label, rhs.label)
                return 0

        submenu_items = pm.menu(parent, q=True, ia=True)
        sibling_labels = []
        for item in submenu_items:
            # Ignore options boxes.
            if pm.menuItem(item, q=True, optionBox=True):
                continue

            label = Item(item, pm.menuItem(item, q=True, subMenu=True))
            sibling_labels.append(label)

        item = Item(name, subMenu)
        insertion_point = bisect.bisect_left(sibling_labels, item)
        if insertion_point == 0:
            return None
        else:
            return sibling_labels[insertion_point-1].label

    def add_menu_item(self, name, top_level_path=None, top_level_only=False, insert_sorted=False, *args, **kwargs):
        """
        Create a menu item.

        If top_level_only is true, only an entry in the top-level menu will be created.
        If the top-level menu is disabled, no menu item will be created.

        If top_level_path isn't None, it's a pipe-separated path indicating where
        this should be added to the standalone menu.

        If insert_sorted is true, the item will be added in sorted order with other
        entries in the same menu.  This is only used for items in the top level menus.
        """
        if not top_level_only:
            item = self._add_menu_item_internal(name, insert_sorted=False, *args, **kwargs)
            if item is not None:
                self.related_items.setdefault(name, []).append(item)

        # If we have a standalone path, create the standalone menu entry.
        if top_level_path is not None:
            standalone_item = self._add_standalone_menu_item(name, top_level_path=top_level_path, *args, **kwargs)
            if standalone_item is not None:
                self.related_items.setdefault(name, []).append(standalone_item)

        return name

    def _add_menu_item_internal(self, name, insert_sorted=False, *args, **kwargs):
        if 'optionBox' in kwargs:
            # Maya creates an option box by adding it as a separate menu item.  We do it
            # by passing optionBox=function when creating the menu item itself, since it
            # makes things simpler.
            option_box = kwargs['optionBox']
            del kwargs['optionBox']
        else:
            option_box = None

        # We always need a label, even for dynamic menu names, so we can tell where to
        # put the menu item when insert_sorted is true.
        assert 'label' in kwargs

        # Don't create menu items in batch mode.  It causes a warning.
        if pm.about(batch=True):
            return

        # In case this menu item has already been created, remove the old one.
        _delete_menu_item(name)

        if insert_sorted:
            assert 'insertAfter' not in kwargs
            kwargs['insertAfter'] = self._get_sorted_insertion_point(name=name, subMenu=kwargs.get('subMenu', False), parent=kwargs.get('parent'))

            # If insertAfter is '' then the insertion point is the beginning.  However, Maya prints
            # an incorrect warning if you say insertAfter='' and there are no items in the submenu,
            # so remove it in this case.
            if not pm.menu(kwargs.get('parent'), q=True, ia=True):
                del kwargs['insertAfter']

        elif 'insertAfter' in kwargs and kwargs['insertAfter'] is None:
            # insertAfter=None causes the menu item to be added at the beginning.  We want
            # that to add at the end, so remove the argument.  This way, if a search for
            # a menu insertion point fails and returns None, we put things at the end (putting
            # them at the beginning is obnoxious).
            del kwargs['insertAfter']

        item = pm.menuItem(name, *args, **kwargs)

        # Add the option box, if any.
        if option_box is not None:
            option_box_name = name + 'Options'
            _delete_menu_item(option_box_name)

            # Maya option boxes are weird: they're regular menu items, and they appear over the
            # previous menu item, so we need to add if after the above menu item.
            item_name = item.split('|')[-1]
            name = pm.menuItem(optionBox=True, command=option_box, insertAfter=item_name, parent=kwargs['parent'])
            self.menu_items.add(name)

        # self.menu_items is a list of items that we need to remove.  Don't add submenus
        # to this list.  Rather than deleting them directly when we're unloaded, we leave
        # them alone and use the empty menu cleanup down below to remove them, so if two
        # plugins create the same submenu and one is unloaded, it doesn't remove the other
        # plugin's menu with it.
        if not kwargs.get('subMenu'):
            self.menu_items.add(item)
        return item

    def _add_standalone_menu_item(self, name, top_level_path, *args, **kwargs):
        if not _menu_registration.show_top_level_menu:
            return None
        assert 'top_level_path' not in kwargs

        # Make sure the edit menu is built so we can add to it.  Maya defers this
        # for "heap memory reasons", but that was in 2009 and it doesn't really
        # make sense anymore.
        pm.mel.eval('buildDeferredMenus')

        path_parts = top_level_path.split('|')
        assert len(path_parts) >= 1, top_level_path

        # Find or create our menu.
        parent_submenu = 'zMayaTools_Menu'

        pm.setParent('MayaWindow')

        # Create the top-level menu.
        if not pm.menu(parent_submenu, q=True, exists=True):
            item = pm.menu(parent_submenu, label='zMayaTools', tearOff=True)

        # All but the final entry in top_level_path is a submenu name.  Create
        # the submenu tree.
        path_so_far = []
        for part in path_parts[:-1]:
            path_so_far.append(part.replace(' ', '_'))

            # Prefix the submenu to make sure it's unique.
            submenu_item_name = 'zMayaTools_Menu_' + '_'.join(path_so_far)

            # We can add menu items in any order.  Make the menu ordering consistent: always put
            # submenus above regular menu items, and sort alphabetically within that.
            submenu_items = pm.menu(parent_submenu, q=True, ia=True)
            if submenu_item_name not in submenu_items:
                parent_submenu = self._add_menu_item_internal(submenu_item_name, label=part, parent=parent_submenu, subMenu=True, tearOff=True, insert_sorted=True)
            else:
                parent_submenu = submenu_item_name

        # Remove options that only apply when adding the integrated menu item, since
        # we're adding the standalone one.
        kwargs = dict(kwargs)
        kwargs['parent'] = parent_submenu
        if 'insertAfter' in kwargs:
            del kwargs['insertAfter']

        name = '_'.join(path_parts).replace(' ', '_')

        return self._add_menu_item_internal(name, insert_sorted=True, *args, **kwargs)

    def get_related_menu_items(self, item):
        """
        When we create a menu item with add_menu_item, we might add it to more
        than one place.

        Given the original name for a menu item, return a list of all menu items
        that were actually created.
        """
        return self.related_items.get(item, [])

    def add_menu_items(self):
        """
        Add this menu's menu items.

        This should be overridden by the subclass.
        """
        _menu_registration.register_menu(self)

    def remove_menu_items(self):
        """
        Remove this menu's menu items.

        This should be overridden by the subclass.
        """
        _menu_registration.unregister_menu(self)

        for item in self.menu_items:
            try:
                pm.deleteUI(item, menuItem=True)
            except RuntimeError:
                continue

            # Walk up the parent submenus, and remove them if they're empty.  This cleans
            # up any submenus we created if all plugins with items inside them are unloaded.
            # Don't recurse all the way up to the top MayaWindow.
            parts = item.split('|')
            for end in xrange(len(parts)-2, 0, -1):
                # See if the parent menu has any items left.
                parent_menu_path = '|'.join(parts[0:end+1])
                if len(pm.menu(parent_menu_path, q=True, itemArray=True)) == 0:
                    pm.deleteUI(parent_menu_path)
        self.menu_items = set()
        self.related_items = {}

    @classmethod
    def find_menu_section_by_name(cls, menu_items, label):
        """
        Given a list of menu items, return the subset within the section having the
        given label.

        If the label isn't found, return the entire list.
        """
        # Find the section.
        start_idx = cls.find_item_by_name(menu_items, label, divider=True, return_last_item_by_default=False)
        if start_idx is None:
            return menu_items

        # The next menu item is the first one in the section.
        start_idx += 1

        end_idx = start_idx
        for idx in xrange(start_idx+1, len(menu_items)):
            menu_item = menu_items[idx]
            section = pm.menuItem(menu_item, q=True, label=True)
            
            if not pm.menuItem(menu_items[idx], q=True, divider=True):
                continue

            return menu_items[start_idx:idx]
        else:
            return menu_items[start_idx:]

    @classmethod
    def find_item_by_name(cls, menu_items, text, divider=False, return_last_item_by_default=True):
        """
        Find an item with the given label, and return its index.
        
        If it's not found, return the last element in the menu if return_last_item_by_default
        is true, otherwise return None.
        """
        for idx, item in enumerate(menu_items):
            if divider and not pm.menuItem(item, q=True, divider=True):
                continue

            section = pm.menuItem(item, q=True, label=True)
            if section == text:
                return idx

        log.warning('Couldn\'t find the "%s" menu section' % text)
        if return_last_item_by_default:
            return len(menu_items)-1
        else:
            return None

    @classmethod
    def find_menu_section_containing_command(cls, menu_items, command):
        """
        Given a list of menu items, find the menu item that runs the given command.
        Return the subset of the menu for the section containing the command.

        If the label isn't found, return the entire list.
        """
        # Find the command.
        idx = cls.find_item_with_command(menu_items, command, return_last_item_by_default=False)
        if idx is None:
            return menu_items

        return cls.find_menu_section_around_index(menu_items, idx)

    @classmethod
    def find_menu_section_containing_item(cls, menu_items, item):
        """
        Given a list of menu items, find the menu item that runs the given menu item.
        Return the subset of the menu for the section containing the command.

        If the label isn't found, return the entire list.
        """
        try:
            # Find the menu item.
            idx = menu_items.index(item)
            return cls.find_menu_section_around_index(menu_items, idx)
        except ValueError:
            return menu_items

    @classmethod
    def find_menu_section_around_index(cls, menu_items, idx):
        """
        Find the section containing the menu_items[idx], and return its start and end
        index.
        """
        start_idx = idx
        # Search upwards for the start of the section.
        while start_idx > 0:
            if pm.menuItem(menu_items[start_idx], q=True, divider=True):
                start_idx += 1
                break

            start_idx -= 1

        for end_idx in xrange(start_idx+1, len(menu_items)):
            if not pm.menuItem(menu_items[end_idx], q=True, divider=True):
                continue

            return menu_items[start_idx:end_idx]
        else:
            return menu_items[start_idx:]

    @classmethod
    def find_item_with_command(cls, menu_items, command, divider=False, return_last_item_by_default=True):
        """
        Find an item with the given command, and return its index.
        
        If it's not found, return the last element in the menu if return_last_item_by_default
        is true, otherwise return None.

        This is more reliable than find_item_by_name, since it's not affected by localization.
        """
        for idx, item in enumerate(menu_items):
            if divider and not pm.menuItem(item, q=True, divider=True):
                continue

            section = pm.menuItem(item, q=True, c=True)
            if section == command:
                return idx

        log.warning('Couldn\'t find the menu item with command "%s"' % command)
        if return_last_item_by_default:
            return len(menu_items)-1
        else:
            return None

    @classmethod
    def find_submenu_by_name(cls, section, label, default):
        """
        Find the submenu with the given label.

        If it isn't found, return default.
        """
        for item in section:
            if not pm.menuItem(item, q=True, subMenu=True):
                continue
            if pm.menuItem(item, q=True, label=True) != label:
                continue

            return item

        log.warning('Couldn\'t find the "%s" submenu' % label)
        return default

