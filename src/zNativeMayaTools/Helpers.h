#ifndef Helpers_h
#define Helpers_h

#include <algorithm>
#include <map>
#include <string>
#include <vector>

#include <windows.h>

using namespace std;

namespace Helpers
{
string vssprintf(const char *fmt, va_list va);
string ssprintf(const char *fmt, ...);

wstring vssprintf(const wchar_t *fmt, va_list va);
wstring ssprintf(const wchar_t *fmt, ...);

bool endsWith(const wstring &s, const wstring &suffix);
void split(const string &source, char delimitor, vector<string> &result);
string basename(const string &path);
wstring basename(const wstring &path);
wstring dirname(const wstring &path);
string extension(const string &path); // filename.ext -> ext
wstring extension(const wstring &path); // filename.ext -> ext
void replaceString(string &s, const string &src, const string &dst);
void replaceString(wstring &s, const wstring &src, const wstring &dst);
string lowercase(const string &s);
wstring lowercase(const wstring &s);
string getWinError(int err = -1);
string escapeMel(const string &s);
wstring getThisDLLPath();
wstring getTopPluginPath();
string wstringToString(const wstring &s);
wstring stringToWstring(const string &s);
void getFilesInDirectory(wstring path, vector<wstring> &filenames, bool includePath=false);

// Get a global timer.  This currently uses GetTickCount, which is imprecise and
// has various issues, but it's only used occasionally for broad profiling.
double getTime();

// Return the user's temporary directory.
wstring getTempPath();

string readFile(wstring path);
void writeFile(wstring path, string data);
double getFileModificationTime(wstring path);

// Given a replacement map, eg. { "frame": 100 }, replace "<frame>" in filenamePattern
// with 100.
string SubstituteString(string filenamePattern, map<string,string> replacements);

float linearToSRGB(float value);


inline float scale(float x, float l1, float h1, float l2, float h2)
{
    return (x - l1) * (h2 - l2) / (h1 - l1) + l2;
}

inline double clamp(double x, double low, double high)
{
    return min(max(x, low), high);
}

inline float clamp(float x, float low, float high)
{
    return min(max(x, low), high);
}

// Like scale, but also clamp the result to the output range.
inline float scale_clamp(float x, float l1, float h1, float l2, float h2)
{
    x = scale(x, l1, h1, l2, h2);
    x = clamp(x, min(l2, h2), max(l2, h2));
    return x;
}

class HResultException: public exception
{
public:
    HResultException(HRESULT hr_, string caller);

    static string formatMessage(HRESULT hr, string caller);

    HRESULT hr;
};

class StringException: public exception
{
public:
    StringException(string s)
    {
        value = s;
    }

    const char *what() const { return value.c_str(); }
private:
    string value;
};
}

#endif
