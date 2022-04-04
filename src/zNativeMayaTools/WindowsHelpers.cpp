#include "WindowsHelpers.h"

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
