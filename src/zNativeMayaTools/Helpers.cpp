// Simple helpers that aren't specific to Maya.

#include "Helpers.h"

#include <stdarg.h>
#include <stdio.h>
#include <wchar.h>
#include <fstream>
#include <exception>
#include <vector>

using namespace std;

string Helpers::vssprintf(const char *fmt, va_list va)
{
    va_list va2 = va;
    int size = vsnprintf(nullptr, 0, fmt, va2);
    auto buf = (char *) alloca(size + 1);
    vsnprintf(buf, size + 1, fmt, va);
    return string(buf, size);
}

string Helpers::ssprintf(const char *fmt, ...)
{
    va_list va;
    va_start(va, fmt);
    return vssprintf(fmt, va);
}

wstring Helpers::vssprintf(const wchar_t *fmt, va_list va)
{
    va_list va2 = va;
    int size = _vsnwprintf(nullptr, 0, fmt, va2);
    auto buf = (wchar_t *) alloca((size + 1)*sizeof(wchar_t));
    _vsnwprintf(buf, size + 1, fmt, va);
    return wstring(buf, size);
}

wstring Helpers::ssprintf(const wchar_t *fmt, ...)
{
    va_list va;
    va_start(va, fmt);
    return vssprintf(fmt, va);
}

bool Helpers::endsWith(const wstring &s, const wstring &suffix)
{
    if(s.size() < suffix.size())
        return false;
    return s.compare(s.size() - suffix.size(), suffix.size(), suffix) == 0;
}

void Helpers::split(const string &source, char delimitor, vector<string> &result)
{
    result.clear();
    if(source.empty())
        return;

    size_t startpos = 0;

    do {
        size_t pos;
        pos = source.find(delimitor, startpos);
        if(pos == source.npos)
            pos = source.size();

        if(pos-startpos > 0)
        {
            const string AddRString = source.substr(startpos, pos-startpos);
            result.push_back(AddRString);
        }

        startpos = pos+1;
    } while (startpos <= source.size());
}

string Helpers::basename(const string &path)
{
    size_t slash = path.find_last_of("/\\");
    if(slash == string::npos)
        return path;
    else
        return path.substr(slash + 1);
}

wstring Helpers::basename(const wstring &path)
{
    size_t slash = path.find_last_of(L"/\\");
    if(slash == string::npos)
        return path;
    else
        return path.substr(slash + 1);
}

wstring Helpers::dirname(const wstring &path)
{
    size_t slash = path.find_last_of(L"/\\");
    if(slash == wstring::npos)
        return path;
    else
        return path.substr(0, slash);
}

string Helpers::extension(const string &path)
{
    size_t pos = path.rfind('.');
    if(pos == string::npos)
        return "";

    return path.substr(pos+1);
}

wstring Helpers::extension(const wstring &path)
{
    size_t pos = path.rfind(L'.');
    if(pos == wstring::npos)
        return L"";

    return path.substr(pos+1);
}

void Helpers::replaceString(string &s, const string &src, const string &dst)
{
    if(src.empty())
        return;

    size_t pos = 0;
    while(1)
    {
        pos = s.find(src, pos);
        if(pos == string::npos)
            break;

        s.replace(s.begin()+pos, s.begin()+pos+src.size(), dst.begin(), dst.end());
        pos += dst.size();
    }
}

string Helpers::lowercase(const string &s)
{
    string result = s;
    for(char &c: result)
        c = tolower(c);
    return result;
}

wstring Helpers::lowercase(const wstring &s)
{
    wstring result = s;
    for(wchar_t &c: result)
        c = towlower(c);
    return result;
}

#include <windows.h>
string Helpers::getWinError(int err)
{
    if(err == -1)
        err = GetLastError();

    char *buf = NULL;
    if(!FormatMessageA(FORMAT_MESSAGE_FROM_SYSTEM | FORMAT_MESSAGE_ALLOCATE_BUFFER, 0, err, 0, (LPSTR) &buf, 0, NULL))
        return "Error retrieving error";

    string result(buf);
    LocalFree(buf);

    // Why does FormatMessage put newlines at the end of error messages?
    while(result.size() > 1 && (result[result.size()-1] == '\r' || result[result.size()-1] == '\n'))
        result.erase(result.size()-1);

    return result;
}

wstring Helpers::getThisDLLPath()
{
    HMODULE handle = NULL;
    if(!GetModuleHandleExW(
        GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | 
        GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
        (LPWSTR) getThisDLLPath, &handle))
    {
        throw exception((string("GetModuleHandleExW failed: ") + getWinError()).c_str());
    }

    wchar_t path[MAX_PATH*2];
    if(!GetModuleFileNameW(handle, path, sizeof(path)))
    {
        throw exception((string("GetModuleFileNameW failed: ") + getWinError()).c_str());
    }

    return path;
}

std::wstring Helpers::getTopPluginPath()
{
    wstring dllPath = getThisDLLPath();
    if(dllPath.empty())
        return L"";

    // dllPath should be dir/plug-ins/bin/version/plugin.mll.  Remove the last four
    // components to get to the install directory.
    for(int i = 0; i < 4; ++i)
        dllPath = dirname(dllPath);
    return dllPath;
}

string Helpers::wstringToString(const wstring &s)
{
    // Get the size.
    int size = WideCharToMultiByte(CP_ACP,
        0,
        s.data(), (int) s.size(),
        NULL, 0,
        0, NULL);

    string result(size, 0);
    WideCharToMultiByte(CP_ACP,
        0,
        s.data(), (int) s.size(),
        const_cast<char *>(result.data()), size,
        0, NULL);
    return result;
}

wstring Helpers::stringToWstring(const string &s)
{
    // Get the size.
    int size = MultiByteToWideChar(CP_ACP,
        0,
        s.data(), (int) s.size(),
        NULL, 0);

    wstring result(size, 0);
    MultiByteToWideChar(CP_ACP,
        0,
        s.data(), (int) s.size(),
        const_cast<wchar_t *>(result.data()), size);
    return result;
}

void Helpers::getFilesInDirectory(wstring path, vector<wstring> &filenames, bool includePath)
{
    //    if(path.size() > 0 && path.Right(1) == "/")
    //        path.erase(path.size() - 1);

    WIN32_FIND_DATAW fd;
    HANDLE hFind = FindFirstFileW((path + L"/*").c_str(), &fd);
    if( hFind == INVALID_HANDLE_VALUE )
        return;

    do {
        if(!wcscmp(fd.cFileName, L".") || !wcscmp(fd.cFileName, L".."))
            continue;

        wstring filename = fd.cFileName;
        if(includePath)
            filename = path + L"/" + filename;

        filenames.push_back(filename);
    } while(FindNextFile(hFind, &fd));
    FindClose(hFind);
}

double Helpers::getTime()
{
#if 1
    static LARGE_INTEGER freq = {0};
    if(freq.QuadPart == 0)
        QueryPerformanceFrequency(&freq);

    LARGE_INTEGER cnt;
    QueryPerformanceCounter(&cnt);

    return cnt.QuadPart / double(freq.QuadPart);
#else
    return GetTickCount() / 1000.0;
#endif
}

std::wstring Helpers::getTempPath()
{
    wchar_t tempPath[MAX_PATH+1];
    int length = GetTempPathW(MAX_PATH+1, tempPath);
    return wstring(tempPath, length);
}

string Helpers::readFile(wstring path)
{
    try {
        ifstream f;
        f.exceptions(std::ifstream::failbit | std::ifstream::badbit);
        f.open(path, ios::in | ios::binary);
        f.seekg(0, ios_base::end);
        int size = (int) f.tellg();
        f.seekg(0, ios_base::beg);

        string result(size, 0);
        f.read((char *) result.data(), size);
        return result;
    } catch(ifstream::failure e) {
        throw StringException(ssprintf("Error reading %s: %s", wstringToString(path).c_str(), strerror(errno)));
    }
}

void Helpers::writeFile(wstring path, string data)
{
    ofstream f(path, ios::out | ios::binary |  ios::trunc);
    f.write(data.data(), data.size());
    f.flush();
    if(!f)
        throw exception((string("Couldn't write ") + wstringToString(path)).c_str());
}

string Helpers::SubstituteString(string filenamePattern, map<string,string> replacements)
{
    for(auto it: replacements)
    {
        string keyword = lowercase(it.first);
        string lowercasePattern = string("<") + lowercase(keyword) + ">";
        while(1)
        {
            size_t pos = lowercase(filenamePattern).find(lowercasePattern);
            if(pos == string::npos)
                break;

            string newPattern;
            newPattern += filenamePattern.substr(0, pos); // string before the keyword
            newPattern += it.second;
            newPattern += filenamePattern.substr(pos + lowercasePattern.size()); // string after the keyword
            filenamePattern = newPattern;
        }
    }

    return filenamePattern;
}

float Helpers::linearToSRGB(float value)
{
    if(value > 0.0031308f)
        return 1.055f * (powf(value, (1.0f / 2.4f))) - 0.055f;
    else
        return 12.92f * value;
}

double Helpers::getFileModificationTime(wstring path)
{
    HANDLE file = CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL);
    if(file == INVALID_HANDLE_VALUE)
        return 0;

    FILETIME writeTime;
    bool result = GetFileTime(file, nullptr, nullptr, &writeTime);
    CloseHandle(file);
    if(!result)
        return 0;

    uint64_t ticks = uint64_t(writeTime.dwHighDateTime) << 32 | writeTime.dwLowDateTime;
    return ticks / 100000000.0;
}

string Helpers::escapeMel(const string &s)
{
    string result;
    for(char c: s)
    {
        if(c == '"')
            result.append("\\\"");
        else if(c == '\\')
            result.append("\\\\");
        else if(c == '\n')
            result.append("\\n");
        else if(c == '\t')
            result.append("\\t");
        else
            result.append(1, c);
    }

    return result;
}

Helpers::HResultException::HResultException(HRESULT hr_, std::string caller):
    exception(formatMessage(hr_, caller).c_str()),
    hr(hr_)
{
}

string Helpers::HResultException::formatMessage(HRESULT hr, std::string caller)
{
    string result = Helpers::getWinError(hr);
    if(!caller.empty())
        result = caller + ": " + result;
    return result;
}
