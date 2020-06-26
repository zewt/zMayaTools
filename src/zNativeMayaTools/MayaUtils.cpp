#include "MayaUtils.h"
#include "Log.h"
#include "Helpers.h"
#include "MStatusHandler.h"

#include <maya/MGlobal.h>
#include <maya/MFnDependencyNode.h>
#include <maya/MHWGeometry.h>
#include <maya/MIteratorType.h>
#include <maya/MItDependencyNodes.h>
#include <maya/MSceneMessage.h>
#include <maya/MSelectionList.h>
#include <maya/MObjectArray.h>
#include <maya/MPlugArray.h>

#if MAYA_API_VERSION < 20190000
#error zNativeMayaTools requires Maya 2019
#endif

using namespace std;
using namespace Helpers;

bool MayaUtils::findObjectFromPath(MDagPath &dag, string path)
{
    MSelectionList selection;
    selection.add(path.c_str());
    if(selection.length() == 0)
    {
        MGlobal::displayInfo("Output node not found");
        return false;
    }

    MStatus status = selection.getDagPath(0, dag);
    if(!status)
    {
        status.perror("getDagPath");
        return false;
    }

    return true;
}

// Find all plugin nodes in the scene with the given type ID.
void MayaUtils::findPluginNodesByTypeId(const set<uint32_t> &ids, MObjectArray &result)
{
    MStatusHandler status;

    MIteratorType itType;
    itType.setObjectType(MIteratorType::kMObject);
    itType.setFilterType(MFn::kPluginDependNode);

    MItDependencyNodes it(itType, status("MItDependencyNodes"));
    for( ; !it.isDone(); it.next())
    {
        MObject node = it.thisNode();
        MFnDependencyNode dep(node);
        uint32_t id = dep.typeId().id();
        if(ids.find(id) != ids.end())
            result.append(node);
    }

    status.throwErrors();
}

// Decode the depth component from a D24X8 or D24S8 buffer.
void MayaUtils::DecodeDepthFromD24X8(
    const uint32_t *data, int size,
    double nearClip, double farClip,
    vector<float> &result)
{
    result.resize(size, 0.0f);

    for(int i = 0; i < size; ++i)
    {
        uint32_t raw = data[i];

        double a = farClip / (farClip - nearClip);
        double b = farClip * nearClip / (nearClip - farClip);
        double value = b / (raw / double(0x1000000) - a);
        result[i] = float(value);
    }
}

vector<string> MayaUtils::MStringArrayToVector(const MStringArray &value)
{
    vector<string> result;
    for(unsigned int i = 0; i < value.length(); ++i)
    {
        const MString &s = value[i];
        result.emplace_back(s.asChar(), s.length());
    }

    return result;
}

set<string> MayaUtils::MStringArrayToSet(const MStringArray &value)
{
    set<string> result;
    for(unsigned int i = 0; i < value.length(); ++i)
    {
        const MString &s = value[i];
        result.emplace(s.asChar(), s.length());
    }

    return result;
}

string MayaUtils::MakeUniqueName(string prefix)
{
    static uint32_t sequence = 1;
    string result = prefix  + ssprintf("%i", sequence);
    sequence++;
    return result;
}

void MayaUtils::getIncomingArrayConnections(const MPlug &plug, vector<MObject> &result)
{
    int count = plug.numConnectedElements();

    MPlugArray connections;
    for(int i = 0; i < count; ++i)
    {
        MStatus status;
        MPlug connection = plug.connectionByPhysicalIndex(i, &status);
        if(status != MStatus::kSuccess)
            continue;

        connection.connectedTo(connections, true, false, &status);
        if(status != MStatus::kSuccess)
            continue;

        if(connections.length() > 0)
            result.push_back(connections[0].node());
    }
}

// Return the Arnold object ID on a mesh if it exists.  This is a string
// attribute for some reason: "id 1234".  We don't try to parse out anything
// else in the string, so this won't work if other things are also in there.
// Return -1 if we don't find anything.
static int GetMeshObjectIdArnold(const MDagPath &dagPath)
{
    MStatus status;
    MObject node = dagPath.node(&status);
    if(status.error())
        return -1;

    MFnDependencyNode depNode(node, &status);
    if(status.error())
        return -1;

    // getAttr .aiUserOptions
    MPlug objectIdPlug = depNode.findPlug("aiUserOptions", false, &status);
    if(status.error())
        return -1;

    MString objectIdString;
    status = objectIdPlug.getValue(objectIdString);
    if(status.error())
        return -1;

    int objectId = -1;
    sscanf(objectIdString.asChar(), "id %i", &objectId);
    return objectId;
}

static int GetMeshObjectIdNative(const MDagPath &dagPath)
{
    MStatus status;
    MObject node = dagPath.node(&status);
    if(status.error())
        return -1;

    MFnDependencyNode depNode(node, &status);
    if(status.error())
        return -1;

    MPlug objectIdPlug = depNode.findPlug("objectId", false, &status);
    if(status.error())
        return -1;

    int objectId = -1;
    status = objectIdPlug.getValue(objectId);
    if(status.error())
        return -1;

    return objectId;
}

int MayaUtils::GetMeshObjectId(const MDagPath &dagPath)
{
    int objectId = GetMeshObjectIdNative(dagPath);
    if(objectId != -1)
        return objectId;

    objectId = GetMeshObjectIdArnold(dagPath);
    if(objectId != -1)
        return objectId;

    return -1;
}

// Return the viewport distance covered by moving 1cm at a distance of 1cm
// from the camera.
float MayaUtils::CalculateViewportScale(const MFrameContext *context)
{
    MStatusHandler status;

    // One point directly in front of the camera, and a second one unit up-right.
    MPoint cameraSpaceReferencePos1(0,0,1);
    MPoint cameraSpaceReferencePos2 = cameraSpaceReferencePos1 + MVector(1,1,0);

    // Convert from camera space to NDC.
    MMatrix worldToNDC = context->getMatrix(MFrameContext::kProjectionMtx, status("getMatrix"));
    MPoint ndcReferencePos1 = cameraSpaceReferencePos1 * worldToNDC;
    MPoint ndcReferencePos2 = cameraSpaceReferencePos2 * worldToNDC;

    // Convert both positions to screen space.
    int width = 1, height = 1;
    int unused;
    *status("getViewportDimensions") = context->getViewportDimensions(unused, unused, width, height);
    if(status.perror())
        return 1;

    MVector screenSpace1(
        scale((float) ndcReferencePos1[0], -1.0f, +1.0f, 0.0f, float(width)),
        scale((float) ndcReferencePos1[1], -1.0f, +1.0f, float(height), 0.0f));
    MVector screenSpace2(
        scale((float) ndcReferencePos2[0], -1.0f, +1.0f, 0.0f, float(width)),
        scale((float) ndcReferencePos2[1], -1.0f, +1.0f, float(height), 0.0f));

    // The distance between these positions is the number of pixels crossed by moving
    // 1cm when at a distance of 1cm from the camera.
    MVector screenSpaceDistance = screenSpace2 - screenSpace1;

    // We assume square pixels, so just return X.
    return (float) screenSpaceDistance[0];
}

void MayaUtils::TimeUnitToRational(MTime::Unit unit, int &numerator, int &denominator)
{
    switch(unit)
    {
    case MTime::kHours:                numerator = 3600; denominator = 1; return;
    case MTime::kMinutes:              numerator = 60; denominator = 1; return;
    case MTime::kSeconds:              numerator = 1; denominator = 1; return;
    case MTime::kMilliseconds:         numerator = 1; denominator = 1000; return;
    case MTime::k15FPS:                numerator = 1; denominator = 15; return;
    case MTime::k24FPS:                numerator = 1; denominator = 24; return;
    case MTime::k25FPS:                numerator = 1; denominator = 25; return;
    case MTime::k30FPS:                numerator = 1; denominator = 30; return;
    case MTime::k48FPS:                numerator = 1; denominator = 48; return;
    case MTime::k50FPS:                numerator = 1; denominator = 50; return;
    case MTime::k60FPS:                numerator = 1; denominator = 60; return;
    case MTime::k2FPS:                 numerator = 1; denominator = 2; return;
    case MTime::k3FPS:                 numerator = 1; denominator = 3; return;
    case MTime::k4FPS:                 numerator = 1; denominator = 4; return;
    case MTime::k5FPS:                 numerator = 1; denominator = 5; return;
    case MTime::k6FPS:                 numerator = 1; denominator = 6; return;
    case MTime::k8FPS:                 numerator = 1; denominator = 8; return;
    case MTime::k10FPS:                numerator = 1; denominator = 10; return;
    case MTime::k12FPS:                numerator = 1; denominator = 12; return;
    case MTime::k16FPS:                numerator = 1; denominator = 16; return;
    case MTime::k20FPS:                numerator = 1; denominator = 20; return;
    case MTime::k40FPS:                numerator = 1; denominator = 40; return;
    case MTime::k75FPS:                numerator = 1; denominator = 75; return;
    case MTime::k80FPS:                numerator = 1; denominator = 80; return;
    case MTime::k100FPS:               numerator = 1; denominator = 100; return;
    case MTime::k120FPS:               numerator = 1; denominator = 120; return;
    case MTime::k125FPS:               numerator = 1; denominator = 125; return;
    case MTime::k150FPS:               numerator = 1; denominator = 150; return;
    case MTime::k200FPS:               numerator = 1; denominator = 200; return;
    case MTime::k240FPS:               numerator = 1; denominator = 240; return;
    case MTime::k250FPS:               numerator = 1; denominator = 250; return;
    case MTime::k300FPS:               numerator = 1; denominator = 300; return;
    case MTime::k375FPS:               numerator = 1; denominator = 375; return;
    case MTime::k400FPS:               numerator = 1; denominator = 400; return;
    case MTime::k500FPS:               numerator = 1; denominator = 500; return;
    case MTime::k600FPS:               numerator = 1; denominator = 600; return;
    case MTime::k750FPS:               numerator = 1; denominator = 750; return;
    case MTime::k1200FPS:              numerator = 1; denominator = 1200; return;
    case MTime::k1500FPS:              numerator = 1; denominator = 1500; return;
    case MTime::k2000FPS:              numerator = 1; denominator = 2000; return;
    case MTime::k3000FPS:              numerator = 1; denominator = 3000; return;
    case MTime::k6000FPS:              numerator = 1; denominator = 6000; return;
    case MTime::k23_976FPS:            numerator = 24000; denominator = 1001; return;
    case MTime::k29_97FPS:             numerator = 30000; denominator = 1001; return;
    case MTime::k29_97DF:              numerator = 30; denominator = 1; return;
    case MTime::k47_952FPS:            numerator = 48000; denominator = 1001; return;
    case MTime::k59_94FPS:             numerator = 60000; denominator = 1001; return;
    case MTime::k44100FPS:             numerator = 1; denominator = 44100; return;
    case MTime::k48000FPS:             numerator = 1; denominator = 48000; return;
    case MTime::k90FPS:                numerator = 1; denominator = 90; return;
    default:
        Log::Warning(ssprintf("Unknown time unit %i", unit));
        numerator = 1; denominator = 1; return;
    }
}

// Wrapper to call a function<void()> from a raw callback.
namespace PostCall
{
    struct PostCallCallback
    {
        function<void()> callback;
    };
    map<PostCallCallback*, shared_ptr<PostCallCallback>> postedCalls;

    static void call(void *data)
    {
        // Find the PostCallCallback.
        PostCallCallback *postCallPtr = (PostCallCallback *) data;
        auto it = postedCalls.find(postCallPtr);
        if(it == postedCalls.end())
            return;

        shared_ptr<PostCallCallback> postCall = it->second;
        postedCalls.erase(it);

        try {
            postCall->callback();
        } catch(exception e) {
            Log::Error(e.what());
        }
    }
}

void MayaUtils::runOnIdle(function<void()> callback)
{
    auto postCall = make_shared<PostCall::PostCallCallback>();
    postCall->callback = callback;
    PostCall::postedCalls[postCall.get()] = postCall;
    MGlobal::executeTaskOnIdle(PostCall::call, postCall.get());
}

namespace {
    // Return the internal implementation pointer for an MObject.
    //
    // This is used to implement comparing MObjects.  This isn't a "safe" operation
    // since it's accessing an internal API, but MObject hasn't changed significantly
    // in living memory, so it's safe enough.
    //
    // We're only using this for comparisons, so return it as an integer rather than
    // a pointer.
    //
    // We can't use MObjectHandle::objectHashCode, because that only returns a 32-bit
    // hash.  We need the 64-bit pointer value to guarantee that two values are never
    // the same for this to work with ordered sets.  It would be trivial for objectHashCode
    // to just return the pointer.
    const size_t getMObjectPointer(const MObject &obj)
    {
        const void **p = (const void **) &obj;
        return (size_t) p[0];
    }
}

size_t std::less<MObject>::operator()(const MObject &lhs, const MObject &rhs) const
{
    return getMObjectPointer(lhs) < getMObjectPointer(rhs);
}

size_t std::hash<MObject>::operator()(const MObject &obj) const
{
    return getMObjectPointer(obj);
}

int MayaUtils::bytesPerPixelForRasterFormat(MHWRender::MRasterFormat format)
{
    using namespace MHWRender;
    switch(format)
    {
    case kD24S8:
    case kD32_FLOAT:
        return 4;

    case kR24G8:
    case kR24X8:
        return 4;

    case kDXT1_UNORM:
    case kDXT1_UNORM_SRGB:
    case kDXT2_UNORM:
    case kDXT2_UNORM_SRGB:
    case kDXT2_UNORM_PREALPHA:
    case kDXT3_UNORM:
    case kDXT3_UNORM_SRGB:
    case kDXT3_UNORM_PREALPHA:
    case kDXT4_UNORM:
    case kDXT4_SNORM:
    case kDXT5_UNORM:
    case kDXT5_SNORM:
    case kBC6H_UF16:
    case kBC6H_SF16:
    case kBC7_UNORM:
    case kBC7_UNORM_SRGB:
        // Compressed formats aren't supported.
        return -1;

    case kR9G9B9E5_FLOAT:
        return 4;

        // 1-bit formats aren't supported.
    case kR1_UNORM:
        return -1;

    case kA8:
    case kR8_UNORM:
    case kR8_SNORM:
    case kR8_UINT:
    case kR8_SINT:
    case kL8:
        return 1;

    case kR16_FLOAT:
    case kR16_UNORM:
    case kR16_SNORM:
    case kR16_UINT:
    case kR16_SINT:
    case kL16:
    case kR8G8_UNORM:
    case kR8G8_SNORM:
    case kR8G8_UINT:
    case kR8G8_SINT:
    case kB5G5R5A1:
    case kB5G6R5:
        return 2;

    case kR32_FLOAT:
    case kR32_UINT:
    case kR32_SINT:
    case kR16G16_FLOAT:
    case kR16G16_UNORM:
    case kR16G16_SNORM:
    case kR16G16_UINT:
    case kR16G16_SINT:
    case kR8G8B8A8_UNORM:
    case kR8G8B8A8_SNORM:
    case kR8G8B8A8_UINT:
    case kR8G8B8A8_SINT:
    case kR10G10B10A2_UNORM:
    case kR10G10B10A2_UINT:
    case kB8G8R8A8:
    case kB8G8R8X8:
    case kR8G8B8X8:
    case kA8B8G8R8:
        return 4;

    case kR32G32_FLOAT:
    case kR32G32_UINT:
    case kR32G32_SINT:
    case kR16G16B16A16_FLOAT:
    case kR16G16B16A16_UNORM:
    case kR16G16B16A16_SNORM:
    case kR16G16B16A16_UINT:
    case kR16G16B16A16_SINT:
        return 8;

    case kR32G32B32_FLOAT:
    case kR32G32B32_UINT:
    case kR32G32B32_SINT:
        return 12;

    case kR32G32B32A32_FLOAT:
    case kR32G32B32A32_UINT:
    case kR32G32B32A32_SINT:
        return 16;
    default:
        return -1;
    }
}


namespace MayaExiting
{
    bool exiting = false;
    MCallbackId callbackId = 0;

    void mayaExiting(void *self)
    {
        exiting = true;
    }
}

bool MayaExiting::isExiting()
{
    return exiting;
}

void MayaExiting::install()
{
    callbackId = MSceneMessage::addCallback(MSceneMessage::kMayaExiting, mayaExiting, nullptr);
}

void MayaExiting::uninstall()
{
    if(!callbackId)
        return;

    MMessage::removeCallback(callbackId);
    callbackId = 0;
}
