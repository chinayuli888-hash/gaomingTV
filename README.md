# 高明 TV 构建补丁

本仓库提供高明 TV 的 Smali 补丁和构建工具。脚本根据基础 APK 的 SHA-256 选择对应补丁。1.6.0 基包构建 1.6.2，1.6.1 基包构建 1.6.8。

## 1.6.10 软件更新界面

- 软件更新弹窗显示当前版本和版本代码，提供「返回」与「自动升级」。有待完成的安装时，主按钮显示「继续安装」。
- 手机图标、Android TV 横幅和应用名称使用 `1.6.10`，版本代码为 `17`。
- 使用 `scripts/build_release_2026-11-26.py` 生成未签名 APK 时，传入上版构建说明中的 1.6.8 底包，以及 `--version 1.6.10`、`--apktool-jar` 和 `--android-platform-jar`。可用 `--help` 查看完整参数。

## 1.6.9 桌面版本号

- 手机桌面图标和 Android TV 横幅显示 `1.6.9`，应用名称显示为「高明TV 1.6.9」。清单版本代码为 `16`。
- 「设置 → 软件更新」显示当前版本。点「自动升级」会检查 [GitHub Releases](https://github.com/chinayuli888-hash/tv/releases)，选择匹配已安装版本签名的 APK，完成校验后交给 Android 安装。安装授权与确认按系统提示操作。
- 使用 [1.6.7 重建脚本](scripts/rebuild_from_167_2026-11-26.py)生成已知 SHA-256 的 1.6.8 未签名底包，再运行 `python scripts/build_release_2026-11-26.py --base-apk <底包> --android-build-tools <Build Tools 目录> --output <输出 APK>`。版本号由脚本写入清单、图标和横幅。脚本需要 Pillow 10.1 或以上版本。
- 发布正式包使用 GitHub 标签 `v1.6.9` 和附件名 `gaoming-tv-1.6.9.apk`。原测试签名用户需匹配同一测试证书的 `gaoming-tv-1.6.9-test.apk`。本地文件名可附加日期。

## 1.6.8 央视 13 播放失败回退

央视 13 的原线路和重连尝试全部失败后，可选择「打开千寻」，再在千寻中选择央视 13。也可选择「打开央视网」查看官方直播页面。Android 11 及以上通过包可见性声明检查千寻的桌面启动入口。

## 1.6.7 手机、平板和电视

- 安装包最低支持 Android 4.4（API 19）。手机和平板随系统旋转设置切换横竖屏，竖屏频道指南按可用宽度调整。未设置过画面比例时，竖屏按视频的原始比例播放。电视保持横屏。
- Android 4.4 系统支持 TLS 1.2 时，直播、网址节目单导入和更新检查会启用它，继续使用系统证书和主机名校验。

## 1.6.6 启动修复

- 修复播放器错误处理分支中的寄存器类型错误，避免 Android 在启动时拒绝加载播放器。

## 1.6.5 公网播放和软件更新

- 「公网线路」使用新版节目单及手动导入的备用源，跳过原内置运营商源。多线路启动等待延长至 14 秒，明确播放错误仍会立即换线路。最终失败时显示可用的 Media3 错误码。
- CGTN 纪录新增腾讯 CDN 线路，和原有阿里 CDN 线路可相互备份。CGTN 英语也有两条公网线路，其他公网频道各一条。
- 「设置 → 软件更新」显示当前版本及版本代码。点「自动升级」会检查 [GitHub Releases](https://github.com/chinayuli888-hash/tv/releases)，下载新版并校验包名、版本和签名，再交给系统安装。需要安装授权或确认时，按电视提示操作。[Android 安装行为](https://developer.android.com/reference/android/content/pm/PackageInstaller.SessionParams#setRequireUserAction(int))
- 发布更新时，以 `v1.6.6` 这样的标签正式发布。签名正式包命名为 `gaoming-tv-1.6.6.apk`。同一测试签名的测试包命名为 `gaoming-tv-1.6.6-test.apk`。两类更新各自使用对应证书。

## 1.6.4 公网线路

- 频道指南里增加「公网线路」，包含 16 个频道和 17 条可用线路。同一频道有公网源和原有源时，默认先尝试公网源。可通过「换线路」手动选择，或者让播放器自动切换。
- [公网 M3U 清单](playlists/public-network.m3u)随 APK 打包。1.6.3 也可在「设置 → 频道源 → 粘贴频道列表」导入它。此操作会替换之前手动导入的主清单。
- 本清单中的媒体由各电视台提供。云端验证了直播媒体序列和片段读取。CGTN 和广州综合的清单与视频分片已从中国电信及中国联通探针读取，电视上的长时间播放还需验证。[CGTN 测量](https://api.globalping.io/v1/measurements/2VbRIj10pA2IV6nkJ00021YsO) · [广州综合测量](https://api.globalping.io/v1/measurements/29APErVl2HrQPFMgw00021YsP)

## 1.6.3 频道整理

- 在「设置 → 频道整理」编辑隐藏名单，每行一个完整频道名。默认隐藏「每日推荐」「好物严选」「乐享生活」。移除名单中的名称并保存可以恢复该频道。
- 在同一个菜单开启「按节目类型分类」。常见频道可归入央视、卫视、体育、少儿或影视组。关闭该选项可恢复原分类。无法识别的频道沿用原分组。
- 用「频道源」导入更多频道，用「备用频道源」为已有频道补充线路。跨运营商播放取决于所导入线路的可达性。

## 1.6.2 播放改动

- 首次默认采用 SurfaceView 直出。用户已保存的输出设置继续生效，仍可从原有菜单选择「流畅优先」或「全屏兼容」。
- 对齐 AndroidX Media3 1.4.1 的默认播放配置，起播和重新缓冲的门槛分别为 2.5 秒和 5 秒。备用线路的等待时间也相应调整。
- Android 14 及以上的 SurfaceView 生命周期跟随窗口挂载。R1 的自动输出入口和刷新率设置继续可用。

## 本地构建

准备 Python 3.10 或以上版本、Git、JDK 21、Apktool 3.0.3 和 Android SDK Build-Tools 36.0.0。构建 1.6.8 还需同一 SDK 中的 Android 35 平台。平台单独安装时，可通过 `--android-platform-jar` 指定 `android.jar`。

在本机准备与下列 SHA-256 一致的基础 APK。脚本以内容校验，文件名可自定。

| 基础版本 | 目标版本 | 基础 APK 的 SHA-256 |
| --- | --- | --- |
| 1.6.1 | 1.6.8 | `8ff5e011e06cba4430fe4c6731262896a8fb1727b6ebac59d5932d9fced4c47f` |
| 1.6.0 | 1.6.2 | `49b015bb950cf540a31d7b94dfeaa047d66f2b09b10400e1c853d35a50d1e87e` |

构建一个已对齐的未签名 APK。请将命令里的文件路径换成本机路径。

```sh
mkdir -p build
python3 scripts/rebuild.py \
  --base-apk /path/to/gaoming-tv-1.6.1.apk \
  --apktool-jar /path/to/apktool_3.0.3.jar \
  --android-build-tools "$ANDROID_SDK_ROOT/build-tools/36.0.0" \
  --output build/gaoming-tv-1.6.8-unsigned.apk
```

要生成可安装的 APK，在同一构建命令中指定新的输出文件名，并添加 `--keystore`、`--key-alias` 和 `--keystore-password-file`。密钥密码与密钥库密码不同时，再添加 `--key-password-file`。密码文件和密钥库请放在仓库目录外。覆盖安装需要与设备上已安装版本匹配的签名证书。

## 继续维护

- [patches/1.6.2.patch](patches/1.6.2.patch) 保存播放输出偏好、SurfaceView 创建、缓冲及备用线路等待的改动，可以直接审阅差异。
- [patches/1.6.3-from-1.6.1.patch](patches/1.6.3-from-1.6.1.patch) 在 1.6.1 基包上应用播放改动并接入频道整理。[ChannelPolicy.java](channel-policy/src/cn/gaoming/tv/ChannelPolicy.java) 实现频道过滤、分类和编辑界面。
- [patches/1.6.4-network.patch](patches/1.6.4-network.patch) 将公网源接入内置目录。[NetworkChannels.java](channel-policy/src/cn/gaoming/tv/NetworkChannels.java) 复用原解析与合并逻辑，为匹配的频道提升公网线路优先级。
- [patches/1.6.5-update.patch](patches/1.6.5-update.patch) 接入设置菜单、安装权限回调和公网播放分组。[GitHubUpdate.java](channel-policy/src/cn/gaoming/tv/GitHubUpdate.java) 读取发布、校验安装包并提交给系统安装器。
- [patches/1.6.7-devices.patch](patches/1.6.7-devices.patch) 接入设备布局和旧版系统 TLS 设置。[DeviceLayout.java](channel-policy/src/cn/gaoming/tv/DeviceLayout.java) · [LegacyTls.java](channel-policy/src/cn/gaoming/tv/LegacyTls.java)
- [scripts/rebuild.py](scripts/rebuild.py) 解包基础 APK、应用补丁、重新组装 DEX、更新版本字段并打包。可运行 `python3 scripts/rebuild.py --help` 查看参数。
- 修改播放逻辑时，在本机用 Apktool 解包基础 APK，在解包目录应用补丁后编辑 Smali，再把相对于基础 APK 的改动更新到补丁文件。发布下一版时同步更新脚本中的版本名和版本号。

## 许可证

本仓库新增的补丁和构建工具采用 [Apache License 2.0](LICENSE)。基础 APK 及其组件继续适用各自的许可。AndroidX Media3 的许可证与源码见官方项目。[AndroidX Media3 1.4.1](https://github.com/androidx/media/tree/1.4.1)
