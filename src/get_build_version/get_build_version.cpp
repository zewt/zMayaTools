// This is a trivial helper to get the version of Maya we're building for, since Windows
// doesn't have any usable scripting installed by default.
#include <stdio.h>
#include <maya/MTypes.h>

int main()
{
#if defined(MAYA_APP_VERSION)
    printf("%i", MAYA_APP_VERSION);
#elif defined(MAYA_API_VERSION)
    // 2018 and earlier don't have MAYA_APP_VERSION (2018), only MAYA_API_VERSION (20180600).
    printf("%i", MAYA_API_VERSION / 10000);
#endif
    return 0;
}
