# 高明 TV 1.6.2

高明 TV 1.6.2 的播放改动和构建工具。以指定的高明 TV 1.6.0 APK 为基础，应用 Smali 补丁后可重新生成 1.6.2。界面、遥控操作、频道列表和原有画幅选项沿用基础版本。

## 这一版的改动

- 首次默认采用 SurfaceView 直出。用户已保存的输出设置继续生效，仍可从原有菜单选择「流畅优先」或「全屏兼容」。
- 对齐 AndroidX Media3 1.4.1 的默认播放配置，起播和重新缓冲的门槛分别为 2.5 秒和 5 秒。备用线路的等待时间也相应调整。
- Android 14 及以上的 SurfaceView 生命周期跟随窗口挂载。R1 的自动输出入口和刷新率设置继续可用。

## 本地构建

准备 Python 3.10 或以上版本、Git、Java 21、Apktool 3.0.3 和 Android SDK Build-Tools 36.0.0。

在本机准备与下列 SHA-256 一致的高明 TV 1.6.0 APK。脚本会校验文件内容，文件名可自定。

```text
49b015bb950cf540a31d7b94dfeaa047d66f2b09b10400e1c853d35a50d1e87e
```

构建一个已对齐的未签名 APK。请将命令里的文件路径换成本机路径。

```sh
mkdir -p build
python3 scripts/rebuild.py \
  --base-apk /path/to/gaoming-tv-1.6.0.apk \
  --apktool-jar /path/to/apktool_3.0.3.jar \
  --android-build-tools "$ANDROID_SDK_ROOT/build-tools/36.0.0" \
  --output build/gaoming-tv-1.6.2-unsigned.apk
```

要生成可安装的 APK，在同一构建命令中指定新的输出文件名，并添加 `--keystore`、`--key-alias` 和 `--keystore-password-file`。密钥密码与密钥库密码不同时，再添加 `--key-password-file`。密码文件和密钥库请放在仓库目录外。覆盖安装需要与设备上已安装版本匹配的签名证书。

## 继续维护

- [patches/1.6.2.patch](patches/1.6.2.patch) 保存播放输出偏好、SurfaceView 创建、缓冲及备用线路等待的改动，可以直接审阅差异。
- [scripts/rebuild.py](scripts/rebuild.py) 解包基础 APK、应用补丁、重新组装 DEX、更新版本字段并打包。可运行 `python3 scripts/rebuild.py --help` 查看参数。
- 修改播放逻辑时，在本机用 Apktool 解包基础 APK，在解包目录应用补丁后编辑 Smali，再把相对于基础 APK 的改动更新到补丁文件。发布下一版时同步更新脚本中的版本名和版本号。

## 许可证

本仓库新增的补丁和构建工具采用 [Apache License 2.0](LICENSE)。基础 APK 及其组件继续适用各自的许可。AndroidX Media3 的许可证与源码见官方项目。[AndroidX Media3 1.4.1](https://github.com/androidx/media/tree/1.4.1)
