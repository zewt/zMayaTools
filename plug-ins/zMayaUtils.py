import os
from pymel import core as pm
from maya import OpenMaya as om
from zMayaTools.menus import Menu

from zMayaTools import maya_logging
log = maya_logging.get_log()

# Only import hide_output_window in Windows.
if os.name == 'nt':
    from zMayaTools import hide_output_window
    reload(hide_output_window)

class PluginMenu(Menu):
    def add_menu_items(self):
        menu = 'MayaWindow|mainRigSkeletonsMenu'

        # Make sure the menu is built.
        pm.mel.eval('ChaSkeletonsMenu "%s";' % menu)

        def run_eye_rig(unused):
            from zMayaTools.rigging import eye_rig
            eye_rig.create_eye_rig()
        eye_rig = self.add_menu_item('zMayaTools_EyeRig', label='Eye Rig', parent=menu, insertAfter='hikWindowItem',
                command=run_eye_rig)

        def validate_character(unused):
            from zMayaTools import validate_character
            reload(validate_character)
            validate_character.UI().run()

        eye_rig = self.add_menu_item('zMayaTools_ValidateCharacter', label='Validate Character', parent=menu, insertAfter=eye_rig,
                command=validate_character)

        for menu in ['mainDeformMenu', 'mainRigDeformationsMenu']:
            # Make sure the menu is built.
            pm.mel.eval('ChaDeformationsMenu "MayaWindow|%s";' % menu)

            # Add "Mirror Weights" in the "Weights" section at the bottom of the Deform menu.
            menu_items = pm.menu(menu, q=True, ia=True)
            mirror_weights = self.find_item_by_name(menu_items, 'Mirror Deformer Weights')

            def run_copy_painted_weights(unused):
                from zMayaTools import copy_painted_weights
                reload(copy_painted_weights)
                ui = copy_painted_weights.UI()
                ui.run()

            self.add_menu_item('zMayaTools_CopyWeights_%s' % menu, label='Copy Deformer Weights', parent=menu,
                    annotation='Copy painted weights from one mesh to another',
                    insertAfter=menu_items[mirror_weights],
                    command=run_copy_painted_weights)
            
            # Find the "Edit" section in the Deform menu, then find the "Blend Shape" submenu inside
            # that section.
            menu_items = pm.menu(menu, q=True, ia=True)
            section = self.find_menu_section_by_name(menu_items, 'Edit')
            submenu = self.find_submenu_by_name(section, 'Blend Shape', default=menu)
                
            def run_blend_shape_retargetting(unused):
                from zMayaTools import blend_shape_retargetting
                blend_shape_retargetting.UI().run()

            self.add_menu_item('zBlendShapeRetargetting_%s' % menu, label='Retarget Blend Shapes', parent=submenu,
                    command=run_blend_shape_retargetting)

            def run_split_blend_shapes(unused):
                from zMayaTools import split_blend_shapes
                split_blend_shapes.UI().run()

            self.add_menu_item('zSplitBlendShape_%s' % menu, label='Split Blend Shape', parent=submenu,
                    annotation='Split a blend shape across a plane',
                    command=run_split_blend_shapes)

        # Add the "Hide Output Window" menu item.
        self.add_hide_output_window()

    def add_hide_output_window(self):
        # Add "Show Output Window" at the end of the Windows menu.
        if os.name != 'nt':
            return

        # Activate the user's current preference.
        hide_output_window.refresh_visibility()

        def refresh_menu_item():
            label = 'Show Output Window' if hide_output_window.is_hidden() else 'Hide Output Window'
            pm.menuItem(self.menu_item, e=True, label=label)

        def toggle_output_window(unused):
            hide_output_window.toggle()
            refresh_menu_item()

        pm.mel.eval('buildDeferredMenus')
        self.menu_item = self.add_menu_item('zHideOutputWindow', parent='mainWindowMenu', command=toggle_output_window)
        refresh_menu_item()

menu = PluginMenu()
def initializePlugin(mobject):
    if om.MGlobal.mayaState() != om.MGlobal.kInteractive:
        return

    menu.add_menu_items()

def uninitializePlugin(mobject):
    menu.remove_menu_items()

