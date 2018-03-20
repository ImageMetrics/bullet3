"""
This script will build a Third Party for our Bullet fork. It takes three arguments and some options:
Arg 0: Either 'ios' or 'osx'
Arg 1: The directory to where the ThirdParty.xml and .zip file should be placed
Arg 2: The name of the third party (e.g. Bullet-2.86.1-iOS-XCode92-static-Oz-NoDebugDraw)

Option -b, --bitcode: Add it if you want to enable bitcode
Option -s --size_optimized: Add it if you want to use the Oz flag for optimizing Release builds

The script works by creating a temporary working directory. It operates differently if you it is building for iOS vs OSX

For iOS:
In the working directory, it will run Cmake multiple times to produce workspaces to build the device, simulator, and
simulator64 builds of the library. It will then run xcodebuild on each of those cmake outputs. It then extracts the
built .a files from all of the slices and copies them into the lib directory that will get zipped up. However these are
thing libs and so their architecture name tacked on to them so they can be identified and merged into a fat library
using lipo, before being deleted.

For OSX:
In the working directory, it will run Cmake to produce a workspace for building Bullet for macOS. Since there is only
a single slices (x86_64), it just builds this single project and takes these built libs and puts them in the final
lib directory as is.

It then copies the headers into the include directory that will get zipped up.

After that, it zips up the directory which has the libs and headers, creates a third party xml for it, and then copies
those to the output directory
"""

import optparse
import os
from os import path
import shutil
import subprocess
import sys
import tempfile

_IOS_DEPLOYMENT_TARGET = '8.0'
_OSX_DEPLOYMENT_TARGET = '10.12'

class BulletBuilder(object):
  def __init__(self, target_platform, output_dir, third_party_name,
               enable_bitcode=False, size_optimized=False):
    """
    Constructor. Just sets values and creates some directories
    :param target_platform: Should be either ios or osx
    :param output_dir: Where the final third party lib and xml should get copied to
    :param third_party_name: The full name of the third party (e.g. Bullet-2.86.1-OSX-XCode92-static-Oz-NoDebugDraw)
    :param enable_bitcode: True if we should enable bitcode (ios only)
    :param size_optimized: True to set the Release C/CXX flags to -Oz
    """

    self.target_platform = target_platform
    self.output_dir = output_dir
    self.third_party_name = third_party_name
    self.enable_bitcode = enable_bitcode
    self.size_optimized = size_optimized

    # The Bullet source code directory
    self.source_dir = path.dirname(path.realpath(__file__))

    # Temporary directory to work out of
    # self.working_dir = '/var/folders/1_/7g2r266157q4v0tmppwd0x8m0000gn/T/tmpTrKNE8'
    self.working_dir = tempfile.mkdtemp()

    # Directory that will get zipped up, in the working directory
    self.third_party_dir = path.join(self.working_dir, self.third_party_name)

    # Include and lib directories in the third party directory
    self.third_party_include_dir = path.join(self.third_party_dir, 'include')
    self.third_party_libs_dir = path.join(self.third_party_dir, 'lib')

    # Full paths to the zip and xml in the working directory which we'll copy to the output directory
    self.third_party_zip = self.third_party_dir + '.zip'
    self.third_party_xml = self.third_party_dir + '.ThirdParty.xml'

    print 'Platform:', self.target_platform
    print 'Source directory:', self.source_dir
    print 'Output directory:', self.output_dir
    print 'Working directory:', self.working_dir

  @property
  def ios(self):
    """
    Convenience property to determine if target platform is iOS
    :return: True if target platform is iOS
    """
    return self.target_platform.lower() == 'ios'

  @property
  def osx(self):
    """
    Convenience property to determine if target platform is OSX
    :return: True if target platform is OSX
    """
    return self.target_platform.lower() == 'osx'

  def build(self):
    """
    Main entry point for building and creating the third party
    :return: None
    """
    if not path.exists(self.third_party_dir):
      os.makedirs(self.third_party_dir)

    # Run CMake, xcodebuild and then extract the built libs. If we're on iOS, we have to create fat libs using lipo
    # from all of the individual architectures
    if self.ios:
      lib_names = self._build_device_config()
      self._build_simulator_config()
      self._build_simulator64_config()
      self._create_fat_libs(lib_names)
    else:
      self._build_osx_config()

    # Copy header files to their final location
    self._copy_headers()

    # Create and copy the third party files.
    self._zip_third_party_dir()
    self._write_third_party_xml()
    self._copy_to_output_dir()

    # Clean up
    shutil.rmtree(self.working_dir)

  def _build_device_config(self):
    """
    Builds the config for iOS that produces the armv7, armv7s, and arm64 libs
    :return: List of lib names i.e. $(lib_name).a
    """
    build_dir = self._run_cmake('OS')
    self._run_xcodebuild(build_dir, 'iphoneos')
    return self._extract_libs(build_dir, ['armv7', 'armv7s', 'arm64'])

  def _build_simulator_config(self):
    """
    Builds the config for iOS that produces the i386 libs
    :return: List of lib names i.e. $(lib_name).a
    """
    build_dir = self._run_cmake('SIMULATOR')
    self._run_xcodebuild(build_dir, 'iphonesimulator')
    return self._extract_libs(build_dir, ['i386'])

  def _build_simulator64_config(self):
    """
    Builds the config for iOS that produces the x86_64 libs
    :return: List of lib names i.e. $(lib_name).a
    """
    build_dir = self._run_cmake('SIMULATOR64')
    self._run_xcodebuild(build_dir, 'iphonesimulator')
    return self._extract_libs(build_dir, ['x86_64'])

  def _build_osx_config(self):
    """
    Builds the config for OSX that produces the x86_64 libs
    :return: List of lib names i.e. $(lib_name).a
    """
    build_dir = self._run_cmake('OSX')
    self._run_xcodebuild(build_dir, 'ignored')
    return self._extract_libs(build_dir, [''])

  def _create_fat_libs(self, lib_names):
    """
    Should be called for iOS only since it's specifically looking for mobile architectures.

    In the lib directory should already be the libs for the individual architectures). It will create fat libs
    for each
    :param lib_names: List of lib names: i.e.  $(lib_name).a
    :return: None
    """
    print 'Creating fat libs...'

    # At this point, everything in the lib folder is a slice with the arch appended to the file name. These are just
    # temporary files which we'll mash together into one, so before we mash them into the same directory, get the list
    # of the files in the lib folder so we can delete them after we've mashed them
    thin_libs = os.listdir(self.third_party_libs_dir)

    # For each lib name passed in, use lipo to create fat libs from all of the individual architectures of that lib
    for lib_name in lib_names:
      input_files = [lib_name + arch for arch in ['armv7', 'armv7s', 'arm64', 'i386', 'x86_64']]

      args = ['lipo', '-create']
      args.extend(input_files)
      args.append('-output')
      args.append(lib_name)
      subprocess.check_call(args, cwd=self.third_party_libs_dir)

    # Clean up the thin libs
    for lib_name in thin_libs:
      os.remove(path.join(self.third_party_libs_dir, lib_name))

  def _copy_headers(self):
    """
    Just copies .h and .hpp files from the src directory into the final include directory
    :return: None
    """
    print 'Copying headers...'
    def ignore_func(src, names):
      ignored = []
      for file_name in names:
        full_path = path.join(src, file_name)
        if path.isdir(full_path):
          continue
        if path.splitext(file_name)[1] not in ['.h', '.hpp']:
          ignored.append(file_name)
      return ignored

    source = path.join(self.source_dir, 'src')
    target = self.third_party_include_dir
    shutil.copytree(source, target, ignore=ignore_func)

  def _zip_third_party_dir(self):
    """
    Zips up the third party directory
    :return: None
    """
    print 'Zipping third party directory...'
    args = ['zip', '-r', self.third_party_zip, self.third_party_name]
    subprocess.check_call(args, cwd=self.working_dir)

  def _write_third_party_xml(self):
    """
    Writes the ThirdParty.xml file
    :return:
    """
    print 'Writing third party xml...'
    contents = '''<ThirdPartyLib name="Bullet" archive="{}">
  <IncludePaths>
    <IncludePath path="${{Lib}}/include" />
  </IncludePaths>

  <Libraries>
    <Library name="${{Lib}}/lib/libBullet2FileLoader.a" />
    <Library name="${{Lib}}/lib/libBullet3Collision.a" />
    <Library name="${{Lib}}/lib/libBullet3Common.a" />
    <Library name="${{Lib}}/lib/libBullet3Dynamics.a" />
    <Library name="${{Lib}}/lib/libBullet3Geometry.a" />
    <Library name="${{Lib}}/lib/libBullet3OpenCL_clew.a" />
    <Library name="${{Lib}}/lib/libBulletCollision.a" />
    <Library name="${{Lib}}/lib/libBulletDynamics.a" />
    <Library name="${{Lib}}/lib/libBulletInverseDynamics.a" />
    <Library name="${{Lib}}/lib/libBulletSoftBody.a" />
    <Library name="${{Lib}}/lib/libLinearMath.a" />
  </Libraries>
</ThirdPartyLib>
'''.format(self.third_party_name)

    with open(self.third_party_xml, 'wt') as f:
      f.write(contents)

  def _copy_to_output_dir(self):
    """
    Just copies the ThirdParty.xml and .zip file to the output directory
    :return: None
    """
    print 'Copying third party files to output directory...'
    shutil.copy2(self.third_party_zip, self.output_dir)
    shutil.copy2(self.third_party_xml, self.output_dir)

  def _run_cmake(self, platform):
    """
    Run CMake for the given platform. Sets defines in Cmake to not build extras, demos, or unit tests. Also honors the
    enable_bitcode and size_optimizations values. Uses lowest common denominators for IOS/MACOS deployment targets so
    that we don't get annoying errors when linking
    :param platform: one of the following OS, SIMULATOR, or SIMULATOR64, which are
    defined in the ios.toolchain.cmake file
    :return: None
    """
    args = list()
    args.append('cmake')
    args.append('-G')
    args.append('Xcode')
    args.append('--build')
    args.append(self.source_dir)

    # Add the iOS toolchain
    if self.ios:
      args.append('-DCMAKE_TOOLCHAIN_FILE={}'.format(path.join(self.source_dir, 'ios.toolchain.cmake')))

    # Exclude things we don't want built
    args.append('-DBUILD_EXTRAS=0')
    args.append('-DBUILD_OPENGL3_DEMOS=0')
    args.append('-DBUILD_BULLET2_DEMOS=0')
    args.append('-DBUILD_CPU_DEMOS=0')
    args.append('-DBUILD_UNIT_TESTS=0')

    # Compiler flags
    if self.size_optimized:
      args.append('-DCMAKE_C_FLAGS_RELEASE=-Oz -DNDEBUG')
      args.append('-DCMAKE_CXX_FLAGS_RELEASE=-Oz -DNDEBUG')

    # Other Xcode specific flags
    if self.ios:
      args.append('-DENABLE_BITCODE={}'.format('1' if self.enable_bitcode else '0'))
      args.append('-DIOS_DEPLOYMENT_TARGET={}'.format(_IOS_DEPLOYMENT_TARGET))

      # And the platform that we're building
      args.append('-DIOS_PLATFORM={}'.format(platform))
    else:
      args.append('-DCMAKE_OSX_DEPLOYMENT_TARGET={}'.format(_OSX_DEPLOYMENT_TARGET))

    build_dir = path.join(self.working_dir, platform)
    if not os.path.exists(build_dir):
      os.makedirs(build_dir)
    subprocess.check_call(args, cwd=build_dir)

    return build_dir

  def _run_xcodebuild(self, build_dir, sdk):
    """
    Runs xcode build in on the project in build_dir
    :param build_dir: Directory where Cmake was generating files to
    :param sdk: Either iphoneos or iphonesimulator. Only used if we're building for iOS and not for OSX
    :return: None
    """
    args = list()
    args.append('xcodebuild')
    args.append('-project')
    args.append(path.join(build_dir, 'BULLET_PHYSICS.xcodeproj'))
    args.append('-scheme')
    args.append('install')
    args.append('-configuration')
    args.append('Release')
    if self.ios:
      args.append('-sdk')
      args.append(sdk)
    args.append('build')

    subprocess.check_call(args, cwd=build_dir)

  def _extract_libs(self, build_dir, archs):
    """
    A bit of a complicated method since xcodebuild does things differently depending on whether there are multiple
    architectures that are being built. If there are multiple architectures, xcodebuild puts each single arch slice next
    to all of the other object files (it also puts the final fat lib it creates in the Release-${platform} folder, but
    it's silly to run lipo to extract the thin slices from there when they are already on disk). So when there are
    multiple arches, look for the .a files in the Release-${platform} folder, tack on the name of the arch to the file
    name (e.g. libSomeLibName.aarchName).

    If there is only one arch and no fat lib to create, look for the .a in the  Release-${platform} folder, (or just
    Release for OSX builds) and copy them. On OSX, since there is no fat library to create, pass in [''] for the archs
    parameter
    :param build_dir: Cmake output directory, where the xcodeproj should be found
    :param archs: List of valid architectures. Pass in [''] on OSX so an empty arch name is tacked on to the lib names
    :return: None
    """

    if not os.path.exists(self.third_party_libs_dir):
      os.makedirs(self.third_party_libs_dir)

    libs_names = []
    for root, _, files in os.walk(build_dir):
      arch_name = path.basename(root)

      if len(archs) > 1:
        if arch_name not in archs:
          continue
      else:
        if self.ios:
          if arch_name == 'Release-iphonesimulator':
            arch_name = archs[0]
          else:
            continue
        else:
          if arch_name == 'Release':
            arch_name = archs[0]
          else:
            continue

      for file_name in files:
        if path.splitext(file_name)[1] != '.a':
          continue

        # Add it to the list of lib names
        libs_names.append(file_name)

        # Copy it to the libs dir, with the arch name tacked on
        shutil.copy2(path.join(root, file_name), path.join(self.third_party_libs_dir, file_name + arch_name))

    return libs_names

def main():
  parser = optparse.OptionParser()
  parser.add_option("-b", "--bitcode",
                    dest="enable_bitcode",
                    default=False,
                    action="store_true")
  parser.add_option("-s", "--size_optimized",
                    dest="size_optimized",
                    default=False,
                    action="store_true")
  options, args = parser.parse_args(sys.argv[1:])
  if len(args) != 3:
    print 'ERROR: Three arguments required: [ios|osx] output_dir third_party_name'
    sys.exit(1)

  builder =  BulletBuilder(args[0], args[1], args[2], options.enable_bitcode, options.size_optimized)
  builder.build()

if __name__ == "__main__":
  main()
