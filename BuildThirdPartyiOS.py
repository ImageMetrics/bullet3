import optparse
import os
from os import path
import shutil
import subprocess
import sys
import tempfile

class BulletBuilder(object):
  def __init__(self):
    parser = optparse.OptionParser()
    parser.add_option("-b", "--bitcode",
                      dest="enable_bitcode",
                      default=False,
                      action="store_true")
    parser.add_option("-s", "--size_optimized",
                      dest="size_optimized",
                      default=False,
                      action="store_true")
    (self.options, args) = parser.parse_args(sys.argv[1:])
    if len(args) != 2:
      print 'ERROR: Two arguments required: output_dir, third_party_name'
      sys.exit(1)

    self.source_dir = path.dirname(path.realpath(__file__))
    self.output_dir = args[0]
    self.third_party_name = args[1]
    self.third_party_dir = path.join(self.output_dir, self.third_party_name)
    self.third_party_include_dir = path.join(self.third_party_dir, 'include')
    self.third_party_libs_dir = path.join(self.third_party_dir, 'lib')
    self.third_party_zip = self.third_party_dir + '.zip'
    self.third_party_xml = self.third_party_dir + '.ThirdParty.xml'

    # Temporary directory to work out of
    # self.working_dir = '/private/var/folders/1_/7g2r266157q4v0tmppwd0x8m0000gn/T/tmptPIEyN'
    self.working_dir = tempfile.mkdtemp()
    self.working_libs_dir = path.join(self.working_dir, 'lib')

    if path.exists(self.output_dir):
      shutil.rmtree(self.output_dir)
    os.makedirs(self.output_dir)
    os.makedirs(self.third_party_dir)

    print 'Source directory:', self.source_dir
    print 'Output directory:', self.output_dir
    print 'Working directory:', self.working_dir
    print 'Third Party Zip:', self.third_party_zip
    print 'Third Party XML:', self.third_party_xml

  def build(self):
    lib_names = self._build_device_config()
    self._build_simulator_config()
    self._build_simulator64_config()
    self._create_fat_libs(lib_names)

    self._copy_headers()
    self._copy_libs()

    self._zip_third_party_dir()
    self._write_third_party_xml()

    # shutil.rmtree(self.working_dir)
  #
  def _build_device_config(self):
    build_dir = self._run_cmake('OS')
    self._run_xcodebuild(build_dir, 'iphoneos')
    return self._extract_libs(build_dir, ['armv7', 'armv7s', 'arm64'])

  def _build_simulator_config(self):
    build_dir = self._run_cmake('SIMULATOR')
    self._run_xcodebuild(build_dir, 'iphonesimulator')
    return self._extract_libs(build_dir, ['i386'])

  def _build_simulator64_config(self):
    build_dir = self._run_cmake('SIMULATOR64')
    self._run_xcodebuild(build_dir, 'iphonesimulator')
    return self._extract_libs(build_dir, ['x86_64'])

  def _create_fat_libs(self, lib_names):
    # At this point, everything in the lib folder is a slice with the arch appended to the file name. These are just
    # temporary files which we'll mash together into one, so before we mash them into the same directory, get the list
    # of the files in the lib folder so we can delete them after we've mashed them
    thin_libs = os.listdir(self.working_libs_dir)

    for lib_name in lib_names:
      input_files = [lib_name + arch for arch in ['armv7', 'armv7s', 'arm64', 'i386', 'x86_64']]

      args = ['lipo', '-create']
      args.extend(input_files)
      args.append('-output')
      args.append(lib_name)
      subprocess.check_call(args, cwd=self.working_libs_dir)

    # Clean up the thin libs
    for lib_name in thin_libs:
      os.remove(path.join(self.working_libs_dir, lib_name))

  def _copy_headers(self):
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

  def _copy_libs(self):
    shutil.copytree(self.working_libs_dir, self.third_party_libs_dir)

  def _zip_third_party_dir(self):
    args = ['zip', '-r', self.third_party_zip, self.third_party_name]
    subprocess.check_call(args, cwd=self.output_dir)

  def _write_third_party_xml(self):
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

  def _run_cmake(self, platform):
    args = list()
    args.append('cmake')
    args.append('-G')
    args.append('Xcode')
    args.append('--build')
    args.append(self.source_dir)

    # Add the iOS toolchain
    args.append('-DCMAKE_TOOLCHAIN_FILE={}'.format(path.join(self.source_dir, 'ios.toolchain.cmake')))

    # Exclude things we don't want built
    args.append('-DBUILD_OPENGL3_DEMOS=0')
    args.append('-DBUILD_BULLET2_DEMOS=0')
    args.append('-DBUILD_CPU_DEMOS=0')
    args.append('-DBUILD_UNIT_TESTS=0')

    # Compiler flags
    if self.options.size_optimized:
      args.append('-DCMAKE_C_FLAGS_RELEASE=-Oz -DNDEBUG')
      args.append('-DCMAKE_CXX_FLAGS_RELEASE=-Oz -DNDEBUG')

    # Other Xcode specific flags
    args.append('-DENABLE_BITCODE={}'.format('1' if self.options.enable_bitcode else '0'))
    args.append('-DIOS_DEPLOYMENT_TARGET=8.0')

    # And the platform that we're building
    args.append('-DIOS_PLATFORM={}'.format(platform))

    build_dir = path.join(self.working_dir, platform)
    if not os.path.exists(build_dir):
      os.makedirs(build_dir)
    subprocess.check_call(args, cwd=build_dir)

    return build_dir

  def _run_xcodebuild(self, build_dir, sdk):
    args = list()
    args.append('xcodebuild')
    args.append('-project')
    args.append(path.join(build_dir, 'BULLET_PHYSICS.xcodeproj'))
    args.append('-scheme')
    args.append('install')
    args.append('-configuration')
    args.append('Release')
    args.append('-sdk')
    args.append(sdk)
    args.append('build')

    subprocess.check_call(args, cwd=build_dir)

  def _extract_libs(self, build_dir, archs):

    if not os.path.exists(self.working_libs_dir):
      os.makedirs(self.working_libs_dir)

    libs_names = []
    for root, _, files in os.walk(build_dir):
      arch_name = path.basename(root)

      if len(archs) > 1:
        if arch_name not in archs:
          continue
      else:
        if arch_name == 'Release-iphonesimulator':
          arch_name = archs[0]
        else:
          continue

      for file_name in files:
        if path.splitext(file_name)[1] != '.a':
          continue

        # Add it to the list of lib names
        libs_names.append(file_name)

        # Copy it to the libs dir, with the arch name tacked on
        shutil.copy2(path.join(root, file_name), path.join(self.working_libs_dir, file_name + arch_name))

    return libs_names

if __name__ == "__main__":
  builder =  BulletBuilder()
  builder.build()
