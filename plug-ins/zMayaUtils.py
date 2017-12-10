from pymel import core as pm
from zMayaTools.menus import Menu

from zMayaTools import maya_logging
log = maya_logging.get_log()

class PluginMenu(Menu):
    def add_menu_items(self):
        menu = 'MayaWindow|mainRigSkeletonsMenu'

        # Make sure the menu is built.
        pm.mel.eval('ChaSkeletonsMenu "%s";' % menu)

        def run_eye_rig(unused):
            from zMayaTools.rigging import eye_rig
            eye_rig.create_eye_rig()
        self.add_menu_item('zMayaTools_EyeRig', label='Eye Rig', parent=menu, insertAfter='hikWindowItem',
                command=run_eye_rig)

        for menu in ['mainDeformMenu', 'mainRigDeformationsMenu']:
            # Make sure the menu is built.
            pm.mel.eval('ChaDeformationsMenu "MayaWindow|%s";' % menu)

            # Add "Mirror Weights" in the "Weights" section at the bottom of the Deform menu.
            menu_items = pm.menu(menu, q=True, ia=True)
            idx = self.find_divider_by_name(menu_items, 'm_ChaDeformationsMenu.kDeformWeights')

            insert_after = self.find_end_of_section(menu_items, idx)

            def run_mirror_painted_weights(unused):
                from zMayaTools import mirror_painted_weights
                ui = mirror_painted_weights.UI()
                ui.run()

            self.add_menu_item('zMayaTools_MirrorWeights_%s' % menu, label='Mirror Weights...', parent=menu,
                    annotation='Mirror painted weights on a mesh',
                    insertAfter=insert_after,
                    command=run_mirror_painted_weights)

            for item in pm.menu(menu, q=True, ia=True):
                # Find the "Edit" section.
                if pm.menuItem(item, q=True, divider=True):
                    section = pm.menuItem(item, q=True, label=True)
                if section != 'Edit':
                    continue

                # Find the "Blend Shape" submenu.
                if not pm.menuItem(item, q=True, subMenu=True):
                    continue
                if pm.menuItem(item, q=True, label=True) != 'Blend Shape':
                    continue

                def run_blend_shape_retargetting(unused):
                    from zMayaTools import blend_shape_retargetting
                    blend_shape_retargetting.UI().run()
                self.add_menu_item('zBlendShapeRetargetting_%s' % menu, label='Retarget Blend Shapes', parent=item,
                        command=run_blend_shape_retargetting)

            # Make sure file menu is built.
            pm.mel.eval('ChaDeformationsMenu "MayaWindow|%s";' % menu)

            for item in pm.menu(menu, q=True, ia=True):
                # Find the "Edit" section.
                if pm.menuItem(item, q=True, divider=True):
                    section = pm.menuItem(item, q=True, label=True)
                if section != 'Edit':
                    continue

                # Find the "Blend Shape" submenu.
                if not pm.menuItem(item, q=True, subMenu=True):
                    continue
                if pm.menuItem(item, q=True, label=True) != 'Blend Shape':
                    continue

                def run_split_blend_shapes(unused):
                    from zMayaTools import split_blend_shapes
                    split_blend_shapes.UI().run()
   
                self.add_menu_item('zSplitBlendShape_%s' % menu, label='Split Blend Shape', parent=item,
                        annotation='Split a blend shape across a plane',
                        command=run_split_blend_shapes)

menu = PluginMenu()
def initializePlugin(mobject):
    menu.add_menu_items()

def uninitializePlugin(mobject):
    menu.remove_menu_items()

