# 高明 TV 模拟器测试

在装有 Xcode 16 或以上版本的 Mac 上安装一个同时包含 iPhone、iPad 机型的 iOS 模拟器运行时。在仓库根目录执行以下命令。可用 `DEVELOPER_DIR` 选择具体的 Xcode。

```bash
bash ios/ci/test-simulators.sh "$PWD/build/ios-test-$(date +%Y%m%d-%H%M%S)"
```

脚本先用 Release 配置为真机架构编译一次，并检查测试使用的本地网络设置只出现在 Debug 配置。随后在 Xcode 列出的 iPhone 和 iPad 模拟器上依次执行同一套 UI 测试。输出目录包含模拟器型号和系统版本、构建日志、每台模拟器的 `.xcresult`、截图和本地 HTTP 请求记录。再次运行时请选择新的输出目录。

如需在 Xcode 中单步调试，可在仓库根目录运行 `python3 ios/ci/serve_fixtures.py`，打开 `ios/GaomingTV.xcodeproj`，选择 `GaomingTV` 方案和模拟器，按 ⌘U。测试服务器仅监听本机的 8765 端口。

## 验证范围

- 蓝色和绿色画面均是随测试提交的 60 秒 H.264 合成片段，封装为 HLS/fMP4。每个片段约 8 KB，无外部频道依赖。
- UI 测试检查首条线路返回 404 后第二条线路进入实际播放、切换频道后继续播放、所有线路失败时出现重试入口，以及失败后能够换到可播频道。服务器日志单独核对两份媒体片段已送达。
- 另一项测试从随包的 `playlists/public-network.m3u` 载入频道，检查频道列表在横竖屏均可见。公网频道实际播放效果需要在目标运营商网络验证。
- 本测试流程不需要 Apple 账号。真机安装需要团队签名和设备授权，提交 TestFlight 或 App Store 则需要相应的 Apple Developer Program 团队和 App Store Connect 权限。
