from pymel import core as pm
from zMayaTools.menus import Menu
from zMayaTools.rigging import eye_rig

from zMayaTools import maya_logging, mirror_painted_weights
log = maya_logging.get_log()

class PluginMenu(Menu):
    def add_menu_items(self):
        menu = 'MayaWindow|mainRigSkeletonsMenu'

        # Make sure the menu is built.
        pm.mel.eval('ChaSkeletonsMenu "%s";' % menu)

        def run(unused):
            eye_rig.create_eye_rig()

        self.add_menu_item('zSimpleRigging_EyeRig', label='Eye Rig', command=run, parent=menu, insertAfter='hikWindowItem')

        for menu in ['mainDeformMenu', 'mainRigDeformationsMenu']:
            # Make sure the menu is built.
            pm.mel.eval('ChaDeformationsMenu "MayaWindow|%s";' % menu)

            # Add "Mirror Weights" in the "Weights" section at the bottom of the Deform menu.
            menu_items = pm.menu(menu, q=True, ia=True)
            idx = self.find_divider_by_name(menu_items, 'm_ChaDeformationsMenu.kDeformWeights')

            insert_after = self.find_end_of_section(menu_items, idx)

            def run():
                reload(mirror_painted_weights)
                ui = mirror_painted_weights.UI()
                ui.run()

            self.add_menu_item('zSimpleRigging_MirrorWeights_%s' % menu, label='Mirror Weights...', parent=menu,
                    annotation='Mirror painted weights on a mesh',
                    insertAfter=insert_after,
                    command=lambda unused: run())

menu = PluginMenu()
def initializePlugin(mobject):
    menu.add_menu_items()

def uninitializePlugin(mobject):
    menu.remove_menu_items()

