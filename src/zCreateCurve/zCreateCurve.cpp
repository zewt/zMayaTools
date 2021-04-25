// This takes an array of transforms, and outputs a curve.

#include <zNativeMayaTools/MStatusHandler.h>
#include <zNativeMayaTools/Log.h>
#include <zNativeMayaTools/Helpers.h>
#include <zNativeMayaTools/MayaUtils.h>

#include <maya/MGlobal.h>
#include <maya/MMatrix.h>
#include <maya/MPointArray.h>
#include <maya/MDoubleArray.h>
#include <maya/MPlugArray.h>
#include <maya/MFnCompoundAttribute.h>
#include <maya/MFnMatrixAttribute.h>
#include <maya/MFnTypedAttribute.h>
#include <maya/MFnNumericAttribute.h>
#include <maya/MFnNurbsCurve.h>
#include <maya/MFnNurbsCurveData.h>
#include <maya/MFnPlugin.h>
#include <maya/MPxNode.h>

#include <algorithm>
#include <string>
#include <unordered_set>
using namespace std;
using namespace Helpers;

namespace CurveAttrs
{
    // Whether to create a CV or EP curve.
    //
    // Note that periodic EP curves don't seem to be fully supported unless at least
    // 5 EPs are provided.  At degree 3 they're predictable and always meet the EPs,
    // even with only 4 EPs, but other degrees randomly fail or don't actually match
    // the input.  This only happens for periodic EP curves.  To avoid this, use degree
    // 3, or provide at least 5 EPs.
    MObject epCurve;

    // The degree of the curve.
    MObject degree;
    MObject periodic;

    // The parameter range for CV curves.  This isn't used by EP curves.
    MObject parameterRange;

    MObject inputTransforms;
    MObject outputCurve;
}

class zCreateCurve: public MPxNode
{
public:
    static MTypeId id;

    static void *creator() { return new zCreateCurve(); }
    static MStatus initialize();
    MStatus compute(const MPlug &plug, MDataBlock &dataBlock) override;
    MStatus computeCurve(MDataBlock &dataBlock, MObject outputCurve);
    MStatus createPlaceholderCurve(MObject outputCurve);
};

MTypeId zCreateCurve::id(0x1344D1);

MStatus zCreateCurve::initialize()
{
    MStatusHandler status;
    MFnMatrixAttribute matAttr;
    MFnTypedAttribute typedAttr;
    MFnNumericAttribute nAttr;
    MFnCompoundAttribute cmpAttr;

    CurveAttrs::epCurve = nAttr.create("epCurve", "epCurve", MFnNumericData::kBoolean, 0, status("nAttr.create"));
    nAttr.setReadable(false);
    nAttr.setWritable(true);
    nAttr.setKeyable(true);

    CurveAttrs::degree = nAttr.create("degree", "deg", MFnNumericData::kInt, 3, status("nAttr.create"));
    nAttr.setReadable(false);
    nAttr.setWritable(true);
    nAttr.setKeyable(true);
    nAttr.setMin(1);
    nAttr.setMax(50);
    nAttr.setSoftMax(10);

    CurveAttrs::periodic = nAttr.create("periodic", "periodic", MFnNumericData::kBoolean, 0, status("nAttr.create"));
    nAttr.setReadable(false);
    nAttr.setWritable(true);
    nAttr.setKeyable(true);

    CurveAttrs::parameterRange = nAttr.create("parameterRange", "parameterRange", MFnNumericData::kFloat, 1.0f, status("nAttr.create"));
    nAttr.setReadable(false);
    nAttr.setWritable(true);
    nAttr.setKeyable(true);
    nAttr.setMin(0.0001f); // prevent division by zero
    nAttr.setSoftMin(1); // cleaner UI sliders
    nAttr.setSoftMax(10);
    *status("addAttribute") = addAttribute(CurveAttrs::parameterRange);

    // A compound for all basic settings, to allow connecting all settings for nodes with one connection.
    MObject settings = cmpAttr.create("settings", "settings");
    *status("addAttribute") = cmpAttr.addChild(CurveAttrs::epCurve);
    *status("addAttribute") = cmpAttr.addChild(CurveAttrs::degree);
    *status("addAttribute") = cmpAttr.addChild(CurveAttrs::periodic);
    *status("addAttribute") = cmpAttr.addChild(CurveAttrs::parameterRange);
    *status("addAttribute") = addAttribute(settings);

    // input
    CurveAttrs::inputTransforms = matAttr.create("input", "i", MFnMatrixAttribute::kDouble, status("matrixAttr.create"));
    matAttr.setDisconnectBehavior(MFnAttribute::kDelete);
    matAttr.setReadable(false);
    matAttr.setWritable(true);
    matAttr.setArray(true);
    matAttr.setKeyable(true);
    *status("addAttribute") = addAttribute(CurveAttrs::inputTransforms);

    // outputCurve
    CurveAttrs::outputCurve = typedAttr.create("outputCurve", "oc", MFnData::kNurbsCurve, MObject::kNullObj, status("typedAttr.create"));
    typedAttr.setReadable(true);
    typedAttr.setWritable(false);
    *status("addAttribute") = addAttribute(CurveAttrs::outputCurve);

    attributeAffects(CurveAttrs::epCurve, CurveAttrs::outputCurve);
    attributeAffects(CurveAttrs::degree, CurveAttrs::outputCurve);
    attributeAffects(CurveAttrs::periodic, CurveAttrs::outputCurve);
    attributeAffects(CurveAttrs::parameterRange, CurveAttrs::outputCurve);
    attributeAffects(CurveAttrs::inputTransforms, CurveAttrs::outputCurve);
    attributeAffects(settings, CurveAttrs::outputCurve);

    status.perror();
    return status.get();
}

MStatus zCreateCurve::compute(const MPlug &plug, MDataBlock &dataBlock)
{
    MStatusHandler status;

    // outputCurve
    if(plug == CurveAttrs::outputCurve && plug.isArray())
    {
        for(int i = 0; i < (int) plug.numConnectedElements(); i++)
        {
            MPlug curvePlug = plug.connectionByPhysicalIndex(i);
            *status("compute") = compute(curvePlug, dataBlock);
        }
        if(status.perror())
            return status.get();

        dataBlock.outputArrayValue(plug).setClean();
        return MStatus::kSuccess;
    }

    // outputCurve
    if(plug == CurveAttrs::outputCurve)
    {
        // If a curve object doesn't already exist, create one.
        MDataHandle outputCurveHandle = dataBlock.outputValue(plug, status("dataBlock.outputValue"));
        MObject outputCurve = outputCurveHandle.asNurbsCurve();
        if(outputCurve.isNull())
            outputCurve = MFnNurbsCurveData().create();

        *status("computeCurve") = computeCurve(dataBlock, outputCurve);
        if(status.perror())
            return status.get();

        *status("outputCurveHandle.set") = outputCurveHandle.set(outputCurve);
        outputCurveHandle.setClean();
        status.perror();
        return status.get();
    }

    return MPxNode::compute(plug, dataBlock);
}

// Compute the curve, outputting the resulting curve to outputCurve.
//
// On error, create a dummy curve.  If we don't output a curve, accessing the object with
// MFnNurbsCurve in the future will fail.
MStatus zCreateCurve::computeCurve(MDataBlock &dataBlock, MObject outputCurve)
{
    MStatusHandler status;

    if(status.perror())
        return status.get();

    MArrayDataHandle inputTransformsHandle = dataBlock.inputArrayValue(CurveAttrs::inputTransforms);

    // Create an MPointArray of the world-space positions of each of the input transforms.
    // Note that we iterate physical elements, so if elements are missing, we'll just skip
    // over them.
    MPointArray cvs;
    int count = inputTransformsHandle.elementCount();
    for(int i = 0; i < count; ++i)
    {
        *status("inputTransformsHandle.jumpToElement") = inputTransformsHandle.jumpToArrayElement(i);
        MDataHandle transformHandle = inputTransformsHandle.inputValue(status("inputTransformsHandle.inputValue"));
        MMatrix mat = transformHandle.asMatrix();
        cvs.append(MPoint(mat(3,0), mat(3,1), mat(3,2)));
    }

    // If we don't have at least 2 CVs, we don't have enough to create a curve.  Create a
    // dummy curve without returning an error.
    if(cvs.length() < 2)
        return createPlaceholderCurve(outputCurve);

    int degree = dataBlock.inputValue(CurveAttrs::degree).asInt();
    bool periodic = dataBlock.inputValue(CurveAttrs::periodic).asBool();
    bool epCurve = dataBlock.inputValue(CurveAttrs::epCurve).asBool();

    if(epCurve)
    {
        // EP curves can crash if degree is too high.
        degree = min(degree, 10);

        // Periodic EP curves just duplicate the first EP at the end.
        if(periodic && cvs.length() >= 1)
            cvs.append(cvs[0]);

        // Create the EP curve.
        MFnNurbsCurve curve;
        curve.createWithEditPoints(cvs,
            degree,
            periodic? MFnNurbsCurve::kPeriodic:MFnNurbsCurve::kOpen,
            false /* create2D */,
            false /* createRational */,
            // periodic EP curves fail if uniformParam isn't true.
            true /* uniformParam */,
            outputCurve,
            status("MFnNurbsCurve::createWithEditPoints"));
            // Log::Info(ssprintf("Degree: %i CVs: %i Periodic: %i", degree, cvs.length(), periodic));
            // for(int i = 0; i < cvs.length(); ++i)
                // Log::Info(ssprintf("(%.1f, %.1f, %.1f)", cvs[i].x, cvs[i].y, cvs[i].z));
        status.perror();
        return status.get();
    }

    // If we have 4 CVs, we can create up to a degree 3 curve.  If we have 2 CVs, we can create
    // a degree 1 curve (a line).  If we try to create a higher degree curve than we have CVs
    // for, it'll either create a dummy linear curve or fail, so clamp it.
    degree = min(degree, int(cvs.length())-1);

    if(periodic)
    {
        // Periodic CV curves duplicate the first degree CVs at the end, and must have at
        // least 2*degree+1 CVs including the duplicates, or degree+1 before the duplicates.
        // If we don't have enough CVs, just create an open curve.
        if(int(cvs.length()) >= degree+1)
        {
            for(int i = 0; i < degree; ++i)
                cvs.append(cvs[i]);
        }
        else
            periodic = false;
    }

    int numSpans = cvs.length() - degree;
    int numKnots = numSpans + 2*degree - 1;

    MDoubleArray knots;
    if(periodic)
    {
        // If degree is 3, we're adding two negative knots at the beginning, then
        // degree knots, then two extra knots at the end, eg.
        // -2 -1 +0 +1 +2 +3 +4
        // -----          -----
        int cnt = numKnots - 2*(degree-1) - 1;
        for(int i = 0; i < numKnots; ++i)
        {
            // If degree 3, start at -2, eg. -2 -1 0 1 2 ...
            //
            // Note that it's important that this be a double and not a float.  Maya checks that
            // periodic curves are periodic and uses an epsilon value so small that if we use
            // float, creating the curve will randomly fail.
            int knotIdx = i - degree+1;
            double knot = double(knotIdx) / cnt;
            knots.append(knot);
        }
    }
    else
    {
        // We're creating an open curve, with the start and end of the curve pinned to the
        // first and last CVs.
        //
        // If we're creating a curve of degree 3, we add 2 knots to the beginning and 2 knots
        // to the end, with the same value as the outside knot.  With 5 CVs (2 spans), the knots
        // are:
        // 0 0 0 0.5 1 1 1
        for(int i = 0; i < degree-1; ++i)
            knots.append(0);

        int cnt = numKnots - 2*(degree-1) - 1;
        for(int i = 0; i <= cnt; ++i)
        {
            double knot = double(i) / cnt;
            knots.append(knot);
        }

        for(int i = 0; i < degree-1; ++i)
            knots.append(1);
    }

    // If the parameter range isn't 0-1, scale the knots.  This is usually 1.
    float parameterRange = dataBlock.inputValue(CurveAttrs::parameterRange).asFloat();
    if(parameterRange != 1.0f)
    {
        for(int i = 0; i < int(knots.length()); ++i)
            knots[i] *= parameterRange;
    }

    /* Log::Info(ssprintf("Degree: %i CVs: %i Knots: %i Periodic: %i", degree, cvs.length(), knots.length(), periodic));
    for(int i = 0; i < knots.length(); ++i)
        Log::Info(ssprintf("- %f", knots[i]));
    for(int i = 0; i < cvs.length(); ++i)
        Log::Info(ssprintf("(%.1f, %.1f, %.1f)", cvs[i].x, cvs[i].y, cvs[i].z)); */

    // Create the curve.
    MFnNurbsCurve curve;
    curve.create(cvs, knots, degree, periodic? MFnNurbsCurve::kPeriodic:MFnNurbsCurve::kOpen,
        false /* create2D */, false /* createRational */, outputCurve,
        status("MFnNurbsCurve::create"));


    // If we failed for any other reason, create a placeholder.
    if(status.perror())
        return createPlaceholderCurve(outputCurve);

    return status.get();
}

// Create a valid empty curve.
MStatus zCreateCurve::createPlaceholderCurve(MObject outputCurve)
{
    MStatusHandler status;

    MPointArray cvs(2);
    MDoubleArray knots;
    knots.append(0);
    knots.append(1);

    MFnNurbsCurve curve;
    curve.create(cvs, knots, 1, MFnNurbsCurve::kOpen,
        false /* create2D */, false /* createRational */, outputCurve,
        status("MFnNurbsCurve::create"));
    status.perror();
    return status.get();
}

MStatus initializePluginInternal(MObject obj)
{
    MFnPlugin plugin(obj);

    MStatusHandler status;
    *status("zCreateCurve") = plugin.registerNode("zCreateCurve", zCreateCurve::id,
        zCreateCurve::creator, zCreateCurve::initialize);

    *status("PluginMenu.register_from_plugin") = MGlobal::executePythonCommand(MString(
        "from zMayaTools import zCreateCurve; zCreateCurve.menu.register_from_plugin('" + plugin.name() + "')"));

    if(status.perror())
    {
        uninitializePlugin(obj);
        return status.get();
    }

    return MStatus::kSuccess;
}

MStatus initializePlugin(MObject obj)
{
    try {
        return initializePluginInternal(obj);
    } catch(exception &e) {
        Log::Error(e.what());
        uninitializePlugin(obj);
        return MStatus::kFailure;
    }
}

MStatus uninitializePlugin(MObject obj)
{
    MFnPlugin plugin( obj );

    MStatus status = plugin.deregisterNode(zCreateCurve::id);
    if(!status)
        status.perror("deregisterNode");

    return status;
}
