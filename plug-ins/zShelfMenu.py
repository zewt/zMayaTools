from maya import OpenMaya as om
import pymel.core as pm
from pprint import pprint
from zMayaTools import shelf_menus
reload(shelf_menus)

shelf_menu = None
def initializePlugin(mobject):
    if om.MGlobal.mayaState() != om.MGlobal.kInteractive:
        return

    global shelf_menu
    shelf_menu = shelf_menus.ShelfMenu()

def uninitializePlugin(mobject):
    global shelf_menu
    if shelf_menu is None:
        return

    # Remove the menu on unload.
    shelf_menu.remove()
    shelf_menu = None

