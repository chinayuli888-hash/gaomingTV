import SwiftUI
import AVKit
import UniformTypeIdentifiers

private let gold = Color(red: 1, green: 0.80, blue: 0.40)
private let graphite = Color(red: 0.071, green: 0.086, blue: 0.098)
private let surface = Color(red: 0.105, green: 0.125, blue: 0.137)

@MainActor
struct ContentView: View {
    @StateObject private var playback = PlaybackController()
    @Environment(\.scenePhase) private var scenePhase
    @State private var guide = ChannelGuide([])
    private var channels: [Channel] { guide.channels }
    @State private var pickerVisible = false
    @State private var errorText: String?
    @State private var fullScreen = false

    var body: some View {
        GeometryReader { proxy in
            VStack(alignment: .leading, spacing: 0) {
                header.padding(.horizontal, 20).padding(.vertical, 8)
                Divider()
                if proxy.size.width >= 680 {
                    HStack(alignment: .top, spacing: 0) {
                        ScrollView {
                            LazyVStack(alignment: .leading, spacing: 4) {
                                guideRows(onSelect: playback.select)
                            }.padding(16)
                        }.frame(width: min(320, proxy.size.width * 0.32))
                        Divider()
                        ScrollView { playerPane.padding(20) }
                    }
                } else {
                    ScrollViewReader { scroll in
                        ScrollView {
                            LazyVStack(alignment: .leading, spacing: 4) {
                                playerPane.padding(.bottom, 18).id(GuideAnchor.player)
                                guideRows { channel in
                                    playback.select(channel)
                                    scroll.scrollTo(GuideAnchor.player, anchor: .top)
                                }
                            }.padding(16)
                        }
                    }
                }
            }.frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
        .background(graphite.ignoresSafeArea())
        .preferredColorScheme(.dark)
        .tint(gold)
        .task {
            guard channels.isEmpty else { return }
            do {
                guide = ChannelGuide(try await ChannelCatalog.load())
                if let first = channels.first { playback.select(first) }
            } catch {
                errorText = error.localizedDescription
            }
        }
        .onChange(of: scenePhase) { newPhase in
            if newPhase == .background { playback.pause() }
        }
        .fileImporter(isPresented: $pickerVisible,
                      allowedContentTypes: [.plainText, UTType(filenameExtension: "m3u") ?? .data,
                                            UTType(filenameExtension: "m3u8") ?? .data]) { result in
            do {
                let update = try ChannelCatalog.importFile(result.get())
                guide = ChannelGuide(update.channels)
                if let imported = channels.first(where: { $0.id == update.firstImportedID }) {
                    playback.select(imported)
                }
            } catch {
                let taskError = error as NSError
                if taskError.domain != NSCocoaErrorDomain || taskError.code != NSUserCancelledError {
                    errorText = error.localizedDescription
                }
            }
        }
        .alert("频道清单", isPresented: Binding(get: { errorText != nil }, set: { if !$0 { errorText = nil } })) {
            Button("好", role: .cancel) {}
        } message: {
            Text(errorText ?? "")
        }
        .fullScreenCover(isPresented: $fullScreen) {
            ZStack(alignment: .topTrailing) {
                Color.black.ignoresSafeArea()
                VStack(spacing: 0) {
                    PlayerSurface(player: playback.player)
                    controls.padding(.horizontal, 20).padding(.bottom, 8)
                }
                Button { fullScreen = false } label: {
                    Image(systemName: "xmark.circle.fill").font(.title).padding(12)
                }
                .accessibilityLabel("关闭全屏")
                .foregroundColor(.white)
            }.preferredColorScheme(.dark)
        }
    }

    private var header: some View {
        HStack(spacing: 9) {
            Image("BrandMark").resizable().scaledToFit().frame(width: 34, height: 34)
                .accessibilityHidden(true)
            Text("高明TV").font(.title2.weight(.bold))
            Spacer()
            Button {
                pickerVisible = true
            } label: {
                Image(systemName: "square.and.arrow.down").frame(width: 44, height: 44)
            }
            .accessibilityLabel("导入频道清单")
        }
    }

    private var playerPane: some View {
        VStack(alignment: .leading, spacing: 14) {
            ZStack {
                Color.black
                if !fullScreen { PlayerSurface(player: playback.player) }
                if playback.phase == .connecting {
                    ProgressView().tint(gold).accessibilityHidden(true)
                        .allowsHitTesting(false)
                }
                if playback.phase == .failed {
                    Image(systemName: "antenna.radiowaves.left.and.right.slash")
                        .font(.largeTitle).foregroundColor(.secondary).accessibilityHidden(true)
                }
            }
            .aspectRatio(16 / 9, contentMode: .fit)
            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(alignment: .bottomTrailing) {
                if playback.selectedChannel != nil {
                    Button { fullScreen = true } label: {
                        Image(systemName: "arrow.up.left.and.arrow.down.right")
                            .frame(width: 40, height: 40)
                            .background(.black.opacity(0.5), in: Circle())
                    }
                    .accessibilityLabel("全屏播放")
                    .foregroundColor(.white)
                    .padding(6)
                }
            }
            HStack(alignment: .firstTextBaseline) {
                Text(playback.selectedChannel?.name ?? "选择频道")
                    .font(.title2.weight(.bold))
                    .accessibilityIdentifier("playback.channel")
                Spacer()
                phaseLabel
            }
            controls
        }
    }

    private var controls: some View {
        HStack(spacing: 10) {
            if let selected = playback.selectedChannel {
                if playback.phase == .failed {
                    Button {
                        playback.retry()
                    } label: {
                        Label("重试", systemImage: "arrow.clockwise")
                    }
                    .accessibilityIdentifier("playback.retry")
                } else {
                    Button {
                        if playback.phase == .paused { playback.resume() } else { playback.pause() }
                    } label: {
                        Image(systemName: playback.phase == .paused ? "play.fill" : "pause.fill")
                            .frame(width: 40, height: 44)
                    }
                    .accessibilityLabel(playback.phase == .paused ? "继续播放" : "暂停播放")
                }
                Text("线路 \(playback.routeIndex + 1)/\(selected.routes.count)")
                    .font(.subheadline.monospacedDigit())
                    .foregroundColor(.secondary)
                    .accessibilityIdentifier("playback.route")
                if selected.routes.count > 1 {
                    Button {
                        playback.nextRoute()
                    } label: {
                        Label("换线路", systemImage: "arrow.triangle.2.circlepath")
                    }
                    .accessibilityIdentifier("playback.nextRoute")
                }
                Spacer(minLength: 0)
                if channels.count > 1 {
                    Button { stepChannel(-1) } label: {
                        Image(systemName: "backward.end.fill").frame(width: 38, height: 44)
                    }.accessibilityLabel("上一频道")
                    Button { stepChannel(1) } label: {
                        Image(systemName: "forward.end.fill").frame(width: 38, height: 44)
                    }.accessibilityLabel("下一频道")
                }
            }
        }
        .font(.subheadline.weight(.semibold))
        .buttonStyle(.plain)
        .foregroundColor(gold)
        .frame(minHeight: 44)
    }

    private func stepChannel(_ distance: Int) {
        guard let current = channels.firstIndex(where: { $0.id == playback.selectedChannel?.id }) else { return }
        let index = (current + distance + channels.count) % channels.count
        playback.select(channels[index])
    }

    private var phaseLabel: some View {
        let status: (text: String, value: String, color: Color)
        switch playback.phase {
        case .idle: status = ("待播放", "idle", .secondary)
        case .connecting: status = ("连接中", "connecting", gold)
        case .playing: status = ("正在播放", "playing", .green)
        case .paused: status = ("已暂停", "paused", .secondary)
        case .failed: status = ("线路不可用", "failed", .orange)
        }
        return HStack(spacing: 6) {
            Circle().fill(status.color).frame(width: 7, height: 7)
            Text(status.text)
        }
        .font(.caption.weight(.medium))
        .foregroundColor(.secondary)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(status.text)
        .accessibilityValue(status.value)
        .accessibilityIdentifier("playback.phase")
    }

    @ViewBuilder
    private func guideRows(onSelect: @escaping (Channel) -> Void) -> some View {
        Text("频道").font(.title3.weight(.semibold)).accessibilityAddTraits(.isHeader)
        ForEach(guide.groups) { group in
            Section {
                ForEach(group.channels) { channel in
                    channelRow(channel, onSelect: onSelect)
                }
            } header: {
                Text(group.id).font(.caption.weight(.medium)).foregroundColor(.secondary)
                    .padding(.top, 12).accessibilityAddTraits(.isHeader)
            }
        }
    }

    private func channelRow(_ channel: Channel, onSelect: @escaping (Channel) -> Void) -> some View {
        let selected = channel.id == playback.selectedChannel?.id
        return Button {
            onSelect(channel)
        } label: {
            HStack(spacing: 12) {
                RoundedRectangle(cornerRadius: 2)
                    .fill(selected ? gold : .clear).frame(width: 3, height: 22)
                Text(channel.name).font(.body.weight(selected ? .semibold : .regular))
                Spacer()
                if channel.routes.count > 1 {
                    Text("\(channel.routes.count) 条线路").font(.caption).foregroundColor(.secondary)
                }
                Image(systemName: selected ? "circle.inset.filled" : "chevron.right")
                    .font(.caption).foregroundColor(selected ? gold : .secondary)
            }
            .padding(.trailing, 12)
            .frame(minHeight: 46)
            .background(selected ? gold.opacity(0.10) : surface, in: RoundedRectangle(cornerRadius: 8))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(channel.name)
        .accessibilityAddTraits(selected ? .isSelected : [])
        .accessibilityIdentifier("channel.\(channel.name)")
    }
}

private enum GuideAnchor: Hashable {
    case player
}

private struct ChannelGuide {
    struct Group: Identifiable {
        let id: String
        var channels: [Channel]
    }

    let channels: [Channel]
    let groups: [Group]

    init(_ channels: [Channel]) {
        self.channels = channels
        var groups: [Group] = []
        var indexes: [String: Int] = [:]
        for channel in channels {
            if let index = indexes[channel.group] {
                groups[index].channels.append(channel)
            } else {
                indexes[channel.group] = groups.count
                groups.append(Group(id: channel.group, channels: [channel]))
            }
        }
        self.groups = groups
    }
}

private struct PlayerSurface: UIViewControllerRepresentable {
    let player: AVPlayer

    func makeUIViewController(context: Context) -> AVPlayerViewController {
        let view = AVPlayerViewController()
        view.showsPlaybackControls = false
        view.videoGravity = .resizeAspect
        view.player = player
        return view
    }

    func updateUIViewController(_ controller: AVPlayerViewController, context: Context) {
        if controller.player !== player { controller.player = player }
    }

    static func dismantleUIViewController(_ controller: AVPlayerViewController, coordinator: ()) {
        controller.player = nil
    }
}
