@echo off

rem Get the "Documents" directory.
FOR /F "tokens=2* delims= " %%A IN ('REG QUERY "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders" /v "Personal"') DO SET Documents=%%B
set OUTPUT=%Documents%\maya\modules\zMayaTools.mod
set INSTALL_DIR=%cd%

rem Create the global modules directory if it doesn't exist.
if not exist %Documents%\maya\modules mkdir %Documents%\maya\modules

rem Create the .mod file in the user's Maya modules directory.
echo + zMayaTools 1.0 %INSTALL_DIR% > "%OUTPUT%"
echo MAYA_CUSTOM_TEMPLATE_PATH +:= scripts/NETemplates >> "%OUTPUT%"
echo. >> "%OUTPUT%"

rem For binary modules, create a module for each version, including a bunch of versions that don't
rem exist yet.  This way, when users update for future versions, they won't always need to rerun
rem install.bat.  This creates a bunch of noise in the module file, but that's not intended to be
rem edited by hand.  This would be a lot nicer if Maya modules allowed substitutions in paths.
rem
rem These entries have a different module name (zMayaTools-bin) than the entry above, since Maya will
rem only load entries from the first matching entry.
rem
rem Linux and Mac systems would use "linux-version" and "mac-version".  This is a batch file that
rem will only work on Windows, so there's no point including those here.
for %%v in (2018 2019 2020 2021 2022 2023 2024 2025 2026 2027 2028 2029) do (
    echo + MAYAVERSION:%%v PLATFORM:win64 zMayaTools-bin 1.0 %INSTALL_DIR%\plug-ins\bin\win64-%%v >> "%OUTPUT%"
    echo plug-ins: . >> "%OUTPUT%"
    echo. >> "%OUTPUT%"
)

echo Installed
pause
