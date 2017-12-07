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

Installation
------------

In your Maya scripts directory, eg. **Documents\maya\2018\scripts**, create userSetup.mel if
necessary, and add:

    python "execfile('C:/Users/me/Documents/maya/zBlendShapeRetargetting/zBlendShapeRetargetting.py')";

supplying the correct path.

Usage
-----

Create a blendShape deformer on the destination node if one doesn't exist.

Run Deform > Edit Blend Shape > Retarget Blend Shapes.  Select the source and destination
blendShape nodes, and then select one or more blend shape targets in the list to be
retargetted.

Optionally, check "Connect weights to source".  If this is selected, the new blend shape
targets will be connected to the old ones, so they'll change together.

To update the blend shape later, just run the script again.  The existing blend shape target
will be updated.  Note that the targets must always have the same name, so if you rename
one, rename them both.

