import pymel.core as pm

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

    def remove_menu_items(self):
        for item in self.menu_items:
            try:
                pm.deleteUI(item, menuItem=True)
            except RuntimeError:
                pass
        self.menu_items = []

    @classmethod
    def find_divider_by_name(self, menu_items, label_id):
        """
        Find a divider with the given label, and return its index.  If it's not
        found, return the last element in the menu.
        """
        text = pm.displayString(label_id, q=True, value=True)
        for idx, item in enumerate(menu_items):
            if pm.menuItem(item, q=True, divider=True):
                section = pm.menuItem(item, q=True, label=True)
            if section == text:
                return idx

        log.warning('Couldn\'t find the "%s" menu section' % text)
        return len(menu_items)-1

    @classmethod
    def find_end_of_section(cls, menu_items, from_idx):
        """
        Given a menu item in a section, return the menu item to insert after in order
        to put the item at the end of that section.
        
        If we're inserting at the end of the menu, return None instead of the last item.
        This is to work around a silly Maya warning if you use insertAfter to insert after
        the last element.
        """
        for idx in xrange(from_idx+1, len(menu_items)):
            menu_item = menu_items[idx]
            if pm.menuItem(menu_items[idx], q=True, divider=True):
                return menu_items[idx-1]

        return None

 
