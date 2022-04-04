#ifndef WindowsHelpers_h
#define WindowsHelpers_h

// Due to cross-braindamage between C++17 and Windows headers, this needs to
// be included before any "using namespace std".
#include <windows.h>

#include "Helpers.h"
using namespace std;

namespace Helpers
{

class HResultException: public exception
{
public:
    HResultException(HRESULT hr_, string caller);

    static string formatMessage(HRESULT hr, string caller);

    HRESULT hr;
};

}

#endif
