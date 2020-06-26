#include "Log.h"

namespace {
    bool debugging = false;
}

void Log::EnableDebugLogs(bool enable)
{
    debugging = enable;
}

#if defined(NO_MAYA)
// Simple stubs for test applications that don't run in Maya.
void Log::Debug(const std::string &s)
{
    if(!debugging)
        return;
    printf("%s\n", s.c_str());
}

void Log::Info(const std::string &s)
{
    printf("%s\n", s.c_str());
}

void Log::Warning(const std::string &s)
{
    printf("%s\n", s.c_str());
}

void Log::Error(const std::string &s)
{
    printf("%s\n", s.c_str());
}

#else
#include <maya/MGlobal.h>
#include <maya/MStreamUtils.h>

// Use the output window for noisy debug messages.  It's much faster
// than the script editor.
//
// "print" would be useful, to print to the script editor without making
// it a noisy info or warning, but oddly there doesn't seem to be any way
// to do that from native code.
void Log::Debug(const std::string &s)
{
    if(!debugging)
        return;
    MStreamUtils::stdOutStream() << s << "\n";
}

void Log::Info(const std::string &s)
{
    MGlobal::displayInfo(MString(s.c_str()));
}

void Log::Warning(const std::string &s)
{
    MGlobal::displayWarning(MString(s.c_str()));
}

void Log::Error(const std::string &s)
{
    MGlobal::displayError(MString(s.c_str()));
}

#endif
