#ifndef MayaUtils_h
#define MayaUtils_h

#include <map>
#include <memory>
#include <set>
#include <string>
#include <vector>
#include <functional>

#include <maya/MDagPath.h>
#include <maya/MPlug.h>
#include <maya/MShaderManager.h>
#include <maya/MViewport2Renderer.h>
#include <maya/MMessage.h>
#include <maya/MTime.h>
#include <maya/MFnDependencyNode.h>

#include "Helpers.h"
#include "Log.h"

class CommonSamplerStates;
class MObjectArray;

namespace MayaUtils
{
    bool findObjectFromPath(MDagPath &dag, string path);

    // Find all plugin nodes in the scene with the given type ID.
    void findPluginNodesByTypeId(const set<uint32_t> &ids, MObjectArray &result);

    void DecodeDepthFromD24X8(
        const uint32_t *data, int size,
        double nearClip, double farClip,
        vector<float> &result);

    // Convert from MStringArray to a standard vector<string>  MString and
    // MStringArray are too much of a pain (contents invisible in the debugger,
    // no C++ iteration support, etc).
    vector<string> MStringArrayToVector(const MStringArray &value);
    set<string> MStringArrayToSet(const MStringArray &value);

    // Return a unique name (since plugin load) starting with prefix.
    string MakeUniqueName(string prefix);

    // Add all incoming connections to the given array plug to result.
    void getIncomingArrayConnections(const MPlug &plug, vector<MObject> &result);

    // Given a dagPath to a mesh, return its object ID, either as an .objectId
    // integer attribute or in an Arnold .aiUserOptions attribute.
    int GetMeshObjectId(const MDagPath &dagPath);

    // Return the viewport distance covered by moving 1cm at a distance of 1cm
    // from the camera.
    float CalculateViewportScale(const MFrameContext *context);

    // Given an MTime unit, return its value as a fraction.
    void TimeUnitToRational(MTime::Unit unit, int &numerator, int &denominator);

    // Call func on idle using MGlobal::executeTaskOnIdle.
    void runOnIdle(function<void()> func);

    // Return the number of bytes/pixel for the given raster format.  Return -1 for
    // compressed formats and formats with less than one byte per pixel.
    int bytesPerPixelForRasterFormat(MHWRender::MRasterFormat format);

    inline MVector vectorProject(const MVector &v1, const MVector &v2)
    {
        return v2 * (v1*v2) / (v2*v2);
    }

    inline MVector vectorReject(const MVector &v1, const MVector &v2)
    {
        return v1 - vectorProject(v1, v2);
    }

    // Given an MObject pointing to an instance of an MPxNode, return the MPxNode.
    template<typename T>
    T *getNodeFromMObject(MObject &node)
    {
        if(node.isNull())
            return nullptr;

        MFnDependencyNode depNode(node);
        MStatus status;
        MPxNode *optionsNodePtr = depNode.userNode(&status);
        if(status.error() || optionsNodePtr == nullptr)
            return nullptr;

        T *result = dynamic_cast<T *>(optionsNodePtr);
        if(result == nullptr)
        {
            Log::Error(Helpers::ssprintf("Unexpected node: %s", depNode.name().asChar()));
            return nullptr;
        }
        return result;
    }
}

// Define some missing STL handlers for MObject.
namespace std
{
    // Compare two MObjects.  This allows them to be used as keys in std::map.
    template<>
    struct less<MObject>
    {
        size_t operator()(const MObject &lhs, const MObject &rhs) const;
    };

    // A hash for MObject.  This allows them to be used as keys in std::unordered_map.
    template<>
    struct hash<MObject>
    {
        size_t operator()(const MObject &obj) const;
    };
}

// Remove a callback when destroyed.
struct CallbackId
{
    CallbackId(MCallbackId id_): id(id_) { }

    ~CallbackId()
    {
        MMessage::removeCallback(id);
    }

private:
    CallbackId &operator=(const CallbackId &rhs);
    CallbackId(const CallbackId &cpy);
    const MCallbackId id;
};

// Maya doesn't unload plugins before exiting.  This is actually a big problem.  Plugin static
// resources will be unloaded on exit, which will deallocate things like textures, and since Maya
// has already shut those down, this often causes crashes on exit.  If Maya isn't going to unload
// plugins, it should exit with _exit() rather than exit(), so static deinitialization is skipped.
//
// There are also problems with callbacks like add3dViewDestroyMsgCallback: it gets sent on exit
// after the viewport is uninitialized.
//
// There's no way to query whether Maya is shutting down, either.  We have to listen to kMayaExiting
// to find out.
namespace MayaExiting
{
    // Return true if Maya is shutting down.
    bool isExiting();

    // Install and uninstall the listener.
    void install();
    void uninstall();
};

#endif
