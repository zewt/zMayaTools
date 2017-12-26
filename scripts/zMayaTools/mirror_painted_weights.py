from pymel import core as pm
from maya import cmds
import os, sys, time
from zMayaTools import kdtree, maya_helpers, maya_logging
reload(maya_helpers)

from zMayaTools.ui import painted_weights_ui
reload(painted_weights_ui)

log = maya_logging.get_log()

class UI(maya_helpers.OptionsBox):
    title = 'Mirror Painted Weights'

    def __init__(self):
        super(UI, self).__init__()

    def options_box_setup(self):
        self.optvars.add('zMirrorPaintedWeightsAxis', 'int', 2) # default to YZ
        self.optvars.add('zMirrorPaintedWeightsDirection', 'int', 1) # default to positive to negative
        self.optvars.add('zMirrorPaintedWeightsSurfaceAssociation', 'int', 1) # default to closest point

        self.option_box = pm.columnLayout(adjustableColumn=1)
        parent = self.option_box

        def deformer_node_changed(unused=None):
            self.shape_list.refresh()

            deformer = self.deformer_list.get_selected_deformer()
            self.blend_shape_target_list.refresh(deformer)

            self.refresh_enabled_blend_shape_target_list(self.blend_shape_target_list, self.deformer_list.get_selected_deformer())

        pm.optionMenuGrp('mpwDeformerList', label='Deformer:', cc=deformer_node_changed)
        self.deformer_list = painted_weights_ui.DeformerList('mpwDeformerList')

        pm.optionMenuGrp('mpwBlendShapeTargets', label='Blend shape target:')
        self.blend_shape_target_list = painted_weights_ui.BlendShapeTargetList('mpwBlendShapeTargets', self.deformer_list)
        self.blend_shape_target_list.set_all_text('All')

        pm.optionMenuGrp('mpwTargetList', label='Shape:')
        self.shape_list = painted_weights_ui.DeformerShapeList('mpwTargetList', self.deformer_list)

        pm.separator()

        pm.radioButtonGrp('mpwAxis',
                label='Mirror across:',
                numberOfRadioButtons=3, label1='XY', label2='YZ', label3='XZ')
        pm.checkBoxGrp('mpwDirection', label='Direction:', label1='Positive to negative', numberOfCheckBoxes=1)

        pm.separator()

        pm.radioButtonGrp('mpwSurfaceAssociation1',
                select=True,
                numberOfRadioButtons=1,
                label='Surface Association:',
                label1='Closest point on surface')

        pm.radioButtonGrp('mpwSurfaceAssociation2',
                numberOfRadioButtons=1,
                label1='Ray cast',
                shareCollection='mpwSurfaceAssociation1')

        pm.radioButtonGrp('mpwSurfaceAssociation3',
                numberOfRadioButtons=1,
                label1='Closest component',
                shareCollection='mpwSurfaceAssociation1')

        pm.separator()

        deformer_nodes = pm.ls(type=['wire', 'blendShape', 'weightGeometryFilter', 'skinCluster'])
        for node in deformer_nodes:
            pm.menuItem(parent='mpwDeformerList|OptionMenu', label=node)

        deformer_node_changed()

    def option_box_save(self):
        self.optvars['zMirrorPaintedWeightsAxis'] = pm.radioButtonGrp('mpwAxis', q=True, select=True)
        self.optvars['zMirrorPaintedWeightsDirection'] = pm.checkBoxGrp('mpwDirection', q=True, value1=True)
        self.optvars['zMirrorPaintedWeightsSurfaceAssociation'] = self.get_selected_surface_association_idx()

    def option_box_load(self):
        pm.radioButtonGrp('mpwAxis', edit=True, select=self.optvars['zMirrorPaintedWeightsAxis'])
        pm.checkBoxGrp('mpwDirection', edit=True, value1=self.optvars['zMirrorPaintedWeightsDirection'])
        pm.radioButtonGrp('mpwSurfaceAssociation%i' % self.optvars['zMirrorPaintedWeightsSurfaceAssociation'], e=True, select=True)

    def _get_selected_shape(self):
        """
        Return the selected shape, and its index in the deformer's output.
        """
        return self.shape_list.get_selected_shape()

    def refresh_enabled_blend_shape_target_list(self, blend_shape_target_list, deformer):
        # Only enable this for blendShape deformers.
        enable_list = isinstance(deformer, pm.nodetypes.BlendShape)
        pm.optionMenuGrp(blend_shape_target_list.control_name, edit=True, enable=enable_list)

    def option_box_apply(self):
        pm.setParent(self.option_box)

        deformer = self.deformer_list.get_selected_deformer()
        shape, deformer_shape_idx = self._get_selected_shape()

        axis = pm.radioButtonGrp('mpwAxis', q=True, select=True)
        positive_to_negative = pm.checkBoxGrp('mpwDirection', q=True, value1=True)

        axes = {
            1: 'XY', # XY
            2: 'YZ', # YZ
            3: 'XZ' # XZ
        }

        axis_of_symmetry = axes[axis]

        # Find the selected surface association mode, and map it to a copySkinWeights argument.
        surface_association = self.get_selected_surface_association_idx()
        surface_association_modes = {
            1: 'closestPoint',
            2: 'rayCast',
            3: 'closestComponent',
        }
        surface_association = surface_association_modes[surface_association]

        # Duplicate the shape.
        shape_copy = pm.duplicate(shape)[0].getShape()

        # Create a temporary joint, and skin the shape to it.  Disable weight normalization,
        # or weights will get forced to 1 since we only have one joint.
        temporary_joint = pm.createNode('joint')
        skin_cluster = pm.skinCluster([shape_copy, temporary_joint], removeUnusedInfluence=False, normalizeWeights=False)

        # Disable the skinCluster.  We're using it to transfer data, and we don't want it
        # to influence the temporary mesh.
        skin_cluster.attr('envelope').set(0)

        try:
            attrs_to_map = self.get_selected_attrs()

            for attr in attrs_to_map:
                if not maya_helpers.copy_weights_to_skincluster(attr, skin_cluster, shape_copy):
                    log.warning('Input has no deformer weights: %s', attr)
                    continue
            
                copy_options = {
                    'sourceSkin': skin_cluster,
                    'destinationSkin': skin_cluster,
                    'mirrorMode': axis_of_symmetry,
                    'surfaceAssociation': surface_association,

                    # Always use one-to-one joint association, since we're always copying the
                    # two temporary joints.
                    'influenceAssociation': 'oneToOne',
                }
                if not positive_to_negative:
                    copy_options['mirrorInverse'] = True

                pm.copySkinWeights(**copy_options)
 
                # Read the copied weights out of the skinCluster and copy them to the output attribute.
                copied_weights = list(skin_cluster.getWeights(shape_copy, 0))

                weight_path = str(attr)
                for index, value in enumerate(copied_weights):
                    cmds.setAttr('%s[%i]' % (weight_path, index), value)
                
        finally:
            # Clean up our temporary nodes.
            pm.delete(shape_copy.getTransform())
            pm.delete(temporary_joint)

    def get_selected_attrs(self):
        """
        Get the selected attributes.

        For most deformers, this is just the painted weight attribute.  For blendShapes, this
        can be multiple attributes including blend shape target weights.
        """
        deformer = self.deformer_list.get_selected_deformer()
        shape, deformer_shape_idx = self._get_selected_shape()

        # Find the attributes we're mirroring.
        if not isinstance(deformer, pm.nodetypes.BlendShape):
            # Other things are weightGeometryFilters, eg. delta mush and tension deformers.
            # These only have a single paintable attribute.
            input_target = deformer.attr('weightList').elementByLogicalIndex(deformer_shape_idx)
            weights = input_target.attr('weights')
            return [weights]

        # Get the selection from the blend shape target dropdown.
        selected_target = self.blend_shape_target_list.get_selected_target()

        # Loop over each available selection, and see if we should add it to the output.
        input_target = deformer.attr('it').elementByLogicalIndex(deformer_shape_idx)
        attrs_to_map = []
        for target in self.blend_shape_target_list.blend_shape_map.values():
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

    def get_selected_surface_association_idx(self):
        for i in xrange(1,4):
            if pm.radioButtonGrp('mpwSurfaceAssociation%i' % i, q=True, select=True):
                return i

        return 1

