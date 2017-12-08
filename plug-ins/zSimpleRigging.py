from pymel import core as pm
from zMayaTools.menus import Menu
from zMayaTools.rigging import eye_rig

class PluginMenu(Menu):
    def add_menu_items(self):
        menu = 'MayaWindow|mainRigSkeletonsMenu'

        # Make sure the menu is built.
        pm.mel.eval('ChaSkeletonsMenu "%s";' % menu)

        def run(unused):
            eye_rig.create_eye_rig()

        self.add_menu_item('zSimpleRigging_EyeRig', label='Eye Rig', command=run, parent=menu, insertAfter='hikWindowItem')

menu = PluginMenu()
def initializePlugin(mobject):
    menu.add_menu_items()

def uninitializePlugin(mobject):
    menu.remove_menu_items()

