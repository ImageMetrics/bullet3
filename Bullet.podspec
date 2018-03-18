#
# Be sure to run `pod lib lint Bullet.podspec' to ensure this is a
# valid spec before submitting.
#
# Any lines starting with a # are optional, but their use is encouraged
# To learn more about a Podspec see http://guides.cocoapods.org/syntax/podspec.html
#

Pod::Spec.new do |s|
  s.name             = 'Bullet'
  s.version          = '2.86.1+NoDebugDrawTag2'
  s.summary          = 'Image Metrics fork of Bullet repo'
  s.description      = <<-DESC
Image Metrics fork of Bullet repo
                       DESC

  s.homepage         = 'https://github.com/ImageMetrics/bullet3'
  s.license          = { :type => 'MIT', :file => 'LICENSE' }
  s.author           = { 'Dario Ahdoot' => 'dario@image-metrics.com' }
  s.source           = { :git => 'https://github.com/ImageMetrics/bullet3.git', :tag => s.version.to_s }
  # s.social_media_url = 'https://twitter.com/<TWITTER_USERNAME>'

  s.ios.deployment_target = '8.0'
  s.osx.deployment_target  = '10.8'

  s.source_files = 'src/**/*.{h,hpp,c,cpp}', 'Extras/**/*.{h,hpp,c,cpp}'

  # s.public_header_files = 'Pod/Classes/**/*.h'
  # s.frameworks = 'UIKit', 'MapKit'
  # s.dependency 'AFNetworking', '~> 2.3'
end
