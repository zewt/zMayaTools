from pymel import core as pm
from maya import cmds
import os, sys, time
from zMayaTools import kdtree, maya_helpers, maya_logging, vertex_mapping

log = maya_logging.get_log()

# This only supports deformed meshes, and not NURBS surfaces or curves.
# This only supports "closest component" matching, and should be used with cleanly mirrored meshes.
def mirror_attribute_with_map(weights, index_mapping):
    # PyMel prints a "Could not create desired MFn" every time we read a weight.  To avoid spamming this thousands of times,
    # read all of the weights at once.  This is probably faster anyway.
    existing_indices = weights.getArrayIndices()
    existing_values = weights.get()
    existing_values = {index: value for index, value in zip(existing_indices, existing_values)}

    # Copy all values that we didn't match, so they retain their old values.
    new_values = {}
    for existing_index, value in existing_values.items():
        if existing_index in index_mapping:
            continue
        new_values[existing_index] = value
    
    for dst, src in index_mapping.items():
        # If there's no value in the source, don't create one at the destination.
        if src not in existing_values:
            continue
        value = existing_values.get(src)
        new_values[dst] = value

    # Set any indices that we're not going to set to 1.  This is silly.  How do you simply clear an array attribute?
    weight_path = str(weights)
    for existing_index in existing_values.keys():
        if existing_index in new_values:
            continue

        # Use cmds to avoid "Could not create desired MFn" spam.
        cmds.setAttr('%s[%i]' % (weight_path, existing_index), 1)

    for index, value in new_values.items():
        cmds.setAttr('%s[%i]' % (weight_path, index), value)

def mirror_paintable_weights(deformer, deformer_index, axis_of_symmetry, positive_to_negative, threshold=0.01):
    """
    """
    shape = deformer.outputShapeAtIndex(deformer_index)
    
    index_mapping, unmapped_dst_vertices = vertex_symmetry.make_vertex_symmetry_map(shape, threshold=0.01,
            axis_of_symmetry=axis_of_symmetry, positive_to_negative=positive_to_negative)

    if unmapped_dst_vertices:
        log.warning('Warning: unmapped vertices: %s', ' '.join(str(idx) for idx in unmapped_dst_vertices))
    if not index_mapping:
        log.error('No symmetric vertices were matched')
        return
        
    weights = deformer.attr('weightList').elementByLogicalIndex(deformer_index).attr('weights')
    mirror_attribute_with_map(weights, index_mapping)

class UI(maya_helpers.OptionsBox):
    title = 'Mirror Painted Weights'

    def __init__(self):
        super(UI, self).__init__()

    def options_box_setup(self):
        self.optvars.add('zMirrorPaintedWeightsAxis', 'int', 2) # default to YZ
        self.optvars.add('zMirrorPaintedWeightsDirection', 'int', 1) # default to positive to negative
        self.optvars.add('zMirrorPaintedWeightsThreshold', 'float', 0.02)

        self.option_box = pm.columnLayout(adjustableColumn=1)
        parent = self.option_box

        def deformer_node_changed(unused=None):
            self.fill_output_shape_list()
            self.fill_blend_shape_target_list()

        deformer_nodes = pm.ls(type=['wire', 'blendShape', 'weightGeometryFilter', 'skinCluster'])
        pm.optionMenuGrp('mpwDeformerList', label='Deformer:', cc=deformer_node_changed)

        for node in deformer_nodes:
            pm.menuItem(parent='mpwDeformerList|OptionMenu', label=node)

        pm.optionMenuGrp('mpwBlendShapeTargets', label='Blend shape target:')

        pm.optionMenuGrp('mpwTargetList', label='Shape:')
        self.fill_output_shape_list()
        deformer_node_changed()

        pm.separator()

        pm.radioButtonGrp('mpwAxis',
                label='Mirror across:',
                numberOfRadioButtons=3, label1='XY', label2='YZ', label3='XZ')
        pm.checkBoxGrp('mpwDirection', label='Direction:', label1='Positive to negative', numberOfCheckBoxes=1)
        pm.floatSliderGrp('mpwThreshold', label='Vertex matching threshold', field=True, v=0.01, min=0, max=.1, fieldMinValue=0, fieldMaxValue=1000)

    def _get_selected_deformer(self):
        deformer = pm.optionMenuGrp('mpwDeformerList', q=True, v=True)
        if not deformer:
            return None
        deformers = pm.ls(deformer)
        if not deformers:
            return None
        return deformers[0]

    def option_box_save(self):
        self.optvars['zMirrorPaintedWeightsAxis'] = pm.radioButtonGrp('mpwAxis', q=True, select=True)
        self.optvars['zMirrorPaintedWeightsDirection'] = pm.checkBoxGrp('mpwDirection', q=True, value1=True)
        self.optvars['zMirrorPaintedWeightsThreshold'] = pm.floatSliderGrp('mpwThreshold', q=True, v=True)

    def option_box_load(self):
        pm.radioButtonGrp('mpwAxis', edit=True, select=self.optvars['zMirrorPaintedWeightsAxis'])
        pm.checkBoxGrp('mpwDirection', edit=True, value1=self.optvars['zMirrorPaintedWeightsDirection'])
        pm.floatSliderGrp('mpwThreshold', edit=True, v=self.optvars['zMirrorPaintedWeightsThreshold'])
        
    def fill_output_shape_list(self):
        # Clear the existing target list.
        for item in pm.optionMenu('mpwTargetList|OptionMenu', q=True, itemListLong=True):
            pm.deleteUI(item)

        # Get the names of the outputs of the selected deformer.
        value = pm.optionMenuGrp('mpwDeformerList', q=True, v=True)
        if not value:
            return
        nodes = pm.ls(value)
        if not nodes:
            return
        node = nodes[0]

        # Make a list of output shapes for this deformer.
        self.deformer_output_shapes = []
        for deformed_idx in xrange(node.numOutputConnections()):
            try:
                output_shape = node.outputShapeAtIndex(deformed_idx)
            except RuntimeError:
                # This fails with RuntimeError if we query an index that isn't connected, which can happen if you
                # create a deformer for three shapes and then delete the second one.
                continue

            self.deformer_output_shapes.append((output_shape, deformed_idx))
            pm.menuItem(label=output_shape.getParent().name(), parent='mpwTargetList|OptionMenu')

    def fill_blend_shape_target_list(self):
        """
        If a blendShape is selected, populate the list of targets.
        """
        deformer = self._get_selected_deformer()
        is_blend_shape_deformer = isinstance(deformer, pm.nodetypes.BlendShape)
        pm.optionMenuGrp('mpwBlendShapeTargets', edit=True, enable=is_blend_shape_deformer)

        for item in pm.optionMenu('mpwBlendShapeTargets|OptionMenu', q=True, itemListLong=True):
            pm.deleteUI(item)

        # The blend shape array is sparse, so keep a mapping from list indices to blend
        # shape weight indices.  Note that for some reason, these are 1-based.
        self.src_blend_shape_map = {}

        if not is_blend_shape_deformer:
            return

        def add_target(name, shape_id):
            pm.menuItem(label=name, parent='mpwBlendShapeTargets|OptionMenu')
            idx = pm.optionMenuGrp('mpwBlendShapeTargets', q=True, numberOfItems=True)
            self.src_blend_shape_map[idx] = shape_id

        add_target('All', '(all)')
        add_target('Main deformer weights', '(main)')

        # Add the blend shape targets in the source blend shape to the list.
        for idx, weight in enumerate(deformer.attr('weight')):
            add_target('Target: ' + pm.aliasAttr(weight, q=True), weight)

    def _get_selected_shape(self):
        """
        Return the selected shape, and its index in the deformer's output.
        """
        shape_idx = pm.optionMenuGrp('mpwTargetList', q=True, select=True) - 1
        shape, deformer_shape_idx = self.deformer_output_shapes[shape_idx]
        return shape, deformer_shape_idx

    def option_box_apply(self):
        pm.setParent(self.option_box)

        deformer = self._get_selected_deformer()
        shape, deformer_shape_idx = self._get_selected_shape()

        axis = pm.radioButtonGrp('mpwAxis', q=True, select=True)
        positive_to_negative = pm.checkBoxGrp('mpwDirection', q=True, value1=True)
        threshold = pm.floatSliderGrp('mpwThreshold', q=True, v=True)

        axes = {
            1: 'z', # XY
            2: 'x', # YZ
            3: 'y' # XZ
        }

        axis_of_symmetry = axes[axis]

        # Get the shape we're updating weights for.
        shape = deformer.outputShapeAtIndex(deformer_shape_idx)
        
        # Make a symmetry mapping for the shape.
        index_mapping, unmapped_dst_vertices = vertex_mapping.make_vertex_symmetry_map(shape, threshold=0.01,
                axis_of_symmetry=axis_of_symmetry, positive_to_negative=positive_to_negative)

        if unmapped_dst_vertices:
            log.warning('Warning: unmapped vertices: %s', ' '.join(str(idx) for idx in unmapped_dst_vertices))
        if not index_mapping:
            log.error('No symmetric vertices were matched')
            return
            
        attrs_to_map = self.get_selected_attrs()

        for attr in attrs_to_map:
            mirror_attribute_with_map(attr, index_mapping)

    def get_selected_attrs(self):
        """
        Get the selected attributes.

        For most deformers, this is just the painted weight attribute.  For blendShapes, this
        can be multiple attributes including blend shape target weights.
        """
        deformer = self._get_selected_deformer()
        shape, deformer_shape_idx = self._get_selected_shape()

        # Find the attributes we're mirroring.
        if not isinstance(deformer, pm.nodetypes.BlendShape):
            # Other things are weightGeometryFilters, eg. delta mush and tension deformers.
            # These only have a single paintable attribute.
            input_target = deformer.attr('weightList').elementByLogicalIndex(deformer_shape_idx)
            weights = input_target.attr('weights')
            return [weights]

        # Get the selection from the blend shape target dropdown.
        selected_target_idx = pm.optionMenuGrp('mpwBlendShapeTargets', q=True, select=True)
        selected_target = self.src_blend_shape_map[selected_target_idx]

        # Loop over each available selection, and see if we should add it to the output.
        input_target = deformer.attr('it').elementByLogicalIndex(deformer_shape_idx)
        attrs_to_map = []
        for target in self.src_blend_shape_map.values():
            if target == '(all)':
                continue

            # If the user didn't select "all", and this isn't the item he selected, skip it.
            if selected_target != '(all)' and target != selected_target:
                continue

            if target == '(main)':
                # The first entry in the target list is the weights on the blendShape deformer
                # itself, which is the first entry in the "Target" list in the blend shape painting
                # tool.
                attrs_to_map.append(input_target.attr('bw'))
                continue

            # The rest are weights for individual blend shape targets.
            index = target.index()
            input_target_group = input_target.attr('itg').elementByLogicalIndex(index)
            attrs_to_map.append(input_target_group.attr('targetWeights'))

        return attrs_to_map

