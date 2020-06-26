#ifndef MStatusHandler_h
#define MStatusHandler_h

#include <maya/MStatus.h>
#include <exception>
#include <string>

class MStatusHandler;

class MStatusHandlerInstance
{
public:
    MStatusHandlerInstance(std::string errorString_, MStatusHandler *handler_);
    ~MStatusHandlerInstance();
    operator MStatus*();

private:
    friend class MStatusHandler;
    std::string errorString;
    MStatus status;
    MStatusHandler *handler;
};

class MStatusException: public std::exception
{
public:
    MStatusException(MStatus status_, std::string what): std::exception(what.c_str())
    {
        status = status_;
    }

    MStatus status;
};

class MStatusHandler
{
public:
    // Return the current MStatus.
    MStatus get() const;

    // If any errors occurred, print the first and return true.  Otherwise,
    // return false.
    bool perror() const;

    // If any errors occurred, throw an exception.
    void throwErrors() const;

    // Return true if MStatus isn't kSuccess.
    bool error() const;

    // If any errors occurred, return the first.
    std::string getError() const;

    // Return an MStatusHandlerInstance to handle a single error call.
    MStatusHandlerInstance operator()(std::string name);

private:
    friend class MStatusHandlerInstance;

    // This is called when an MStatusHandlerInstance goes out of scope.
    // Record any error.
    void instanceFinished(const MStatusHandlerInstance *accum);

    MStatus status;
    std::string errorString;
};

#endif