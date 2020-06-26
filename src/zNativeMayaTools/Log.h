#ifndef Log_h
#define Log_h

#include <string>

namespace Log
{
    // Enable or disable Log::Debug.
    void EnableDebugLogs(bool enable);
    void Debug(const std::string &s);
    void Info(const std::string &s);
    void Warning(const std::string &s);
    void Error(const std::string &s);
}

#endif
