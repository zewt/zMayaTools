from pymel import core as pm

# This has UI widgets shared between the copy and mirror deformer weight tools.
class DeformerList(object):
    def __init__(self, control_name):
        self.control_name = control_name

    def get_selected_deformer(self):
        deformer = pm.optionMenuGrp(self.control_name, q=True, v=True)
        if not deformer:
            return None
        deformers = pm.ls(deformer)
        if not deformers:
            return None
        return deformers[0]

class DeformerShapeList(object):
    def __init__(self, control_name, deformer_control):
        self.control_name = control_name
        self.deformer_control = deformer_control

    def refresh(self):
        # Clear the existing target list.
        for item in pm.optionMenu(self.control_name + '|OptionMenu', q=True, itemListLong=True):
            pm.deleteUI(item)

        # Get the names of the outputs of the selected deformer.
        value = pm.optionMenuGrp(self.deformer_control.control_name, q=True, v=True)
        if not value:
            return
        nodes = pm.ls(value)
        if not nodes:
            return
        node = nodes[0]

        # Make a list of output shapes for this deformer.
        self.shapes = []
        for deformed_idx in xrange(node.numOutputConnections()):
            try:
                output_shape = node.outputShapeAtIndex(deformed_idx)
            except RuntimeError:
                # This fails with RuntimeError if we query an index that isn't connected, which can happen if you
                # create a deformer for three shapes and then delete the second one.
                continue

            self.shapes.append((output_shape, deformed_idx))
            pm.menuItem(label=output_shape.getParent().name(), parent=self.control_name + '|OptionMenu')

    def get_selected_shape(self):
        """
        Return the selected shape, and its index in the deformer's output.
        """
        shape_idx = pm.optionMenuGrp(self.control_name, q=True, select=True) - 1
        shape, deformer_shape_idx = self.shapes[shape_idx]
        return shape, deformer_shape_idx

class BlendShapeTargetList(object):
    def __init__(self, control_name, deformer_control):
        self.control_name = control_name
        self.deformer_control = deformer_control
        self.blend_shape_map = {}
        self.all_item = None
        self.all_text = None
   
    def set_all_text(self, text):
        """
        Set the text of the "All" item.  If this isn't called, All won't be added.
        """
        self.all_text = text

    def refresh(self, deformer):
        """
        If a blendShape is selected, populate the list of targets.
        """
        for item in pm.optionMenu(self.control_name + '|OptionMenu', q=True, itemListLong=True):
            pm.deleteUI(item)
            self.all_item = None

        # The blend shape array is sparse, so keep a mapping from list indices to blend
        # shape weight indices.  Note that for some reason, these are 1-based.
        self.blend_shape_map.clear()

        if not isinstance(deformer, pm.nodetypes.BlendShape):
            return

        def add_target(name, shape_id):
            item = pm.menuItem(label=name, parent=self.control_name + '|OptionMenu')
            idx = pm.optionMenuGrp(self.control_name, q=True, numberOfItems=True)
            self.blend_shape_map[idx] = shape_id
            return item

        if self.all_text is not None:
            self.all_item = add_target(self.all_text, '(all)')
            
        add_target('Main deformer weights', '(main)')

        # Add the blend shape targets in the source blend shape to the list.
        for idx, weight in enumerate(deformer.attr('weight')):
            add_target('Target: ' + pm.aliasAttr(weight, q=True), weight)

    def enable_all(self, value):
        if self.all_item is None:
            return

        pm.menuItem(self.all_item, edit=True, enable=value)

        if not value and self.get_selected_target():
            # The "All" entry is being disabled, but it's selected.  Select a different item
            # if possible.
            if pm.optionMenuGrp(self.control_name, q=True, numberOfItems=True) > 1:
                pm.optionMenuGrp(self.control_name, edit=True, select=2)
    
    def get_selected_target(self):
        selected_target_idx = pm.optionMenuGrp(self.control_name, q=True, select=True)
        return self.blend_shape_map[selected_target_idx]

