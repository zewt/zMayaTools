// This makes it easier to concisely handle error returns from Maya APIs.
//
// MStatusHandler status;
// mayaCall(1, 2, 3, status("label"));
// *status("label2") = mayaCall2();
// if(status.error())
//     ; // one or more calls failed

#include "MStatusHandler.h"
#include "Helpers.h"
#include "Log.h"
using namespace std;
using namespace Helpers;

#include <maya/MString.h>

MStatus MStatusHandler::get() const
{
    return status;
}

bool MStatusHandler::perror() const
{
    if(status)
        return false;

    Log::Error(getError());

    return true;
}

string MStatusHandler::getError() const
{
    if(status)
        return "";

    // status.errorString() may be an error message.  If it's empty, just print our
    // errorMessage, which is the string we were given in operator().
    MString errorMessage = status.errorString();
    if(errorMessage.length() > 0)
        return ssprintf("%s: %s", errorString.c_str(), errorMessage.asChar());
    else
        return ssprintf("%s failed", errorString.c_str());
}

void MStatusHandler::throwErrors() const
{
    if(status)
        return;

    throw MStatusException(status, getError());
}

void MStatusHandler::instanceFinished(const MStatusHandlerInstance *accum)
{
    // If we already have an error, leave it alone.  Otherwise, store this
    // handler's error.
    if(status == MStatus::kSuccess && accum->status != MStatus::kSuccess)
    {
        status = accum->status;
        errorString = accum->errorString;
    }
}

bool MStatusHandler::error() const
{
    return status.error();
}

MStatusHandlerInstance MStatusHandler::operator()(string name) {
    return MStatusHandlerInstance(name, this);
};

MStatusHandlerInstance::MStatusHandlerInstance(string errorString_, MStatusHandler *handler_)
{
    errorString = errorString_;
    handler = handler_;
}

MStatusHandlerInstance::~MStatusHandlerInstance()
{
    handler->instanceFinished(this);
}

MStatusHandlerInstance::operator MStatus*() {
    return &status;
}

