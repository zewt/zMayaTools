#!/usr/bin/python
import subprocess, sys, os

# The directory containing Maya devkits.  For example,
#
#     F:/stuff/Maya_DEVKIT/2020/devkitBase
#     F:/stuff/Maya_DEVKIT/2022/devkitBase
maya_sdk_dir = 'F:/stuff/Maya_DEVKIT'

# The path to Visual Studio.
visual_studio_path = 'F:/applications/Visual Studio 2017'

# Visual Studio makes it obnoxiously hard to run their tools except from cmd.  The only way
# to set it up is to run a batch file, and since that always happens in a subshell, so we
# have to run vcvarsall and then pull out the environment variables it sets up.
def get_vc_vars():
    # The subshell won't fail if the file doesn't exist, so check first.
    vcvarsall = '%s/VC/Auxiliary/Build/vcvarsall.bat' % visual_studio_path
    if not os.path.exists(vcvarsall):
        print('Couldn\'t find Visual Studio in %s' % visual_studio_path)
        return None

    # Run vcvarsall, and then dump the resulting environment to stdout so we can read it.
    cmd = subprocess.Popen('cmd /q /d /c "%s" x64 & set' % vcvarsall, shell=False, universal_newlines=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    stdout, _ = cmd.communicate()
    cmd.wait()

    # Split the output of "set" into an environment variable list that we can pass to Popen.
    environ = {}
    lines = stdout.split('\n')
    for line in lines:
        if '=' not in line:
            continue
        key, value = line.split('=', 1)
#        print(key)
        environ[key] = value
    return environ

def go():
    environ = get_vc_vars()
    if not environ:
        return

    # Apply the changed path to this environment.  Passing an environment to subprocess.Popen will
    # apply the environment to the subprocess, but not for the path search.
    os.environ['Path'] = environ['Path']

    # Build each version that we have an SDK for.
    for version in '2018', '2019', '2020', '2022', '2023', '2024', '2025', '2026', '2027', '2028', '2029':
        maya_version_sdk = '%s/%s/devkitBase' % (maya_sdk_dir, version)
        if not os.path.exists(maya_version_sdk):
            continue

        print('\nBuilding for Maya version: %s' % version)

        build = subprocess.Popen(
        [
            'msbuild',
            '/m',
            '/property:MAYA_SDK=%s' % maya_version_sdk,
            '/property:MAYA_VER_PATH=%s/' % version,
            '/p:Configuration=Release',
            '/verbosity:minimal',
            '/maxcpucount',
#            '/t:Rebuild',
        ], env=environ)
        result = build.wait()

        # If the build failed, stop.  Don't keep building other versions and scroll the error off.
        if result != 0:
            print('Build failed')
            break
        
go()
