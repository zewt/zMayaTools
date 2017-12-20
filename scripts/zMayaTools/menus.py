import pymel.core as pm

from zMayaTools import maya_logging
log = maya_logging.get_log()

class Menu(object):
    """
    A helper for adding and removing menu items.
    """
    def __init__(self):
        self.menu_items = []

    def add_menu_item(self, name, *args, **kwargs):
        # Don't create menu items in batch mode.  It causes a warning.
        if pm.about(batch=True):
            return

        # insertAfter=None causes the menu item to be added at the beginning.  We want
        # that to add at the end, so remove the argument.
        if 'insertAfter' in kwargs and kwargs['insertAfter'] is None:
            del kwargs['insertAfter']

        # In case this menu item has already been created, remove the old one.  Maya is a
        # little silly here and throws an error if it doesn't exist, so just ignore that
        # if it happens.
        try:
            pm.deleteUI(name, menuItem=True)
        except RuntimeError:
            pass

        item = pm.menuItem(name, *args, **kwargs)
        self.menu_items.append(item)
        return item

    def remove_menu_items(self):
        for item in self.menu_items:
            try:
                pm.deleteUI(item, menuItem=True)
            except RuntimeError:
                pass
        self.menu_items = []

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

