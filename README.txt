XXX
- add a UI
  allow dragging in a source and destination mesh and selecting blend shape deformers
  show a list to allow choosing shapes
  checkbox to choose whether to connect weights

Automatic blend shape retargetting

This allows taking a blend shape on one mesh, and wrapping it to another mesh.

For example, a corrective blend shape on the elbow may need to affect the shirt as well.
This allows sculpting a corrective shape on the elbow, and then automatically creating
a matching blend shape on the shirt.

This can also be used to transfer blend shapes between similar meshes.  For example, you
may have separated head and body meshes with blend shapes on the head, and you want to
combine them into a whole body mesh but keep the blend shapes from the head.  You can merge
the meshes, add a blend shape deformer to the new mesh, then transfer the blend shapes
across.

This works by creating a temporary wrap deformer from the body to the shirt, enabling the
blend shape, and applying the resulting change to the shirt as a blend shape.  This avoids
the need to use a live wrap deformer, which can be very slow and which can't be exported.

Usage
-----

Create a blendShape deformer on the destination node if one doesn't exist.

Select the destination blendShape node, eg. the shirt's, then select the source blendShape
node, eg. the body's.  (Maya doesn't make this convenient.  Select each mesh, expand the
blendShape in the channel box, then add to the node editor, and then you can select the
blendShapes there.  Alternatively, disable "DAG Objects Only" in the outliner, and select
them from the outliner.) 

In the channel box, select one or more blend shapes on the source to be applied, and run
the script.  A blend shape target will be created, and automatically connected to the source
blend shape's weight.

To update the blend shape later, just run the script again.  The existing blend shape target
will be updated.  Note that the targets must always have the same name, so if you rename
one, rename them both.
