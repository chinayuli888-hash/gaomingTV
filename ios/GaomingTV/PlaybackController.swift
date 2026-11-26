import AVFoundation
import Combine
import Foundation

enum PlaybackPhase: Equatable {
    case idle, connecting, playing, paused, failed
}

@MainActor
final class PlaybackController: ObservableObject {
    let player = AVPlayer()

    @Published private(set) var selectedChannel: Channel?
    @Published private(set) var routeIndex = 0
    @Published private(set) var phase: PlaybackPhase = .idle

    private let startupTimeout: TimeInterval = 15
    private let stallTimeout: TimeInterval = 10
    private var remainingRoutes = 0
    private var statusObservation: NSKeyValueObservation?
    private var notifications: [NSObjectProtocol] = []
    private var watchdog: Task<Void, Never>?

    init() {
        // AVPlayer activates the session when playback starts.
        try? AVAudioSession.sharedInstance().setCategory(.playback, mode: .moviePlayback)
    }

    func select(_ channel: Channel) {
        selectedChannel = channel
        startCycle(at: 0)
    }

    func retry() {
        guard selectedChannel != nil else { return }
        startCycle(at: 0)
    }

    func nextRoute() {
        guard let channel = selectedChannel, !channel.routes.isEmpty else { return }
        startCycle(at: (routeIndex + 1) % channel.routes.count)
    }

    func pause() {
        guard player.currentItem != nil else { return }
        phase = .paused
        watchdog?.cancel()
        watchdog = nil
        player.pause()
    }

    func resume() {
        guard phase == .paused, let item = player.currentItem else { return }
        phase = .connecting
        if item.status == .failed {
            advance(after: item)
        } else {
            watchProgress(of: item)
            player.play()
        }
    }

    private func startCycle(at index: Int) {
        remainingRoutes = selectedChannel?.routes.count ?? 0
        playRoute(at: index)
    }

    private func playRoute(at index: Int) {
        detachItem()
        routeIndex = index
        guard let routes = selectedChannel?.routes, routes.indices.contains(index) else {
            phase = .failed
            return
        }

        remainingRoutes -= 1
        phase = .connecting
        let item = AVPlayerItem(url: routes[index].url)
        player.replaceCurrentItem(with: item)
        statusObservation = item.observe(\.status, options: [.initial, .new]) { [weak self, weak item] _, _ in
            Task { @MainActor in
                guard let self, let item, item.status == .failed else { return }
                self.advance(after: item)
            }
        }

        for event in [AVPlayerItem.failedToPlayToEndTimeNotification, AVPlayerItem.didPlayToEndTimeNotification] {
            let token = NotificationCenter.default.addObserver(forName: event, object: item, queue: .main) {
                [weak self, weak item] _ in
                Task { @MainActor in
                    guard let self, let item else { return }
                    self.advance(after: item)
                }
            }
            notifications.append(token)
        }
        let interruption = NotificationCenter.default.addObserver(
            forName: AVAudioSession.interruptionNotification, object: AVAudioSession.sharedInstance(), queue: .main
        ) { [weak self, weak item] note in
            guard let type = note.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt,
                  type == AVAudioSession.InterruptionType.began.rawValue else { return }
            Task { @MainActor in
                guard let self, let item, self.player.currentItem === item else { return }
                self.pause()
            }
        }
        notifications.append(interruption)

        watchProgress(of: item)
        player.play()
    }

    private func advance(after item: AVPlayerItem) {
        // KVO, notifications and a timeout can all report the same failure, even after a channel switch.
        guard player.currentItem === item, phase != .paused else { return }
        if remainingRoutes > 0, let channel = selectedChannel {
            playRoute(at: (routeIndex + 1) % channel.routes.count)
        } else {
            detachItem()
            phase = .failed
        }
    }

    private func watchProgress(of item: AVPlayerItem) {
        watchdog?.cancel()
        watchdog = Task { @MainActor [weak self, weak item] in
            var lastProgress = ProcessInfo.processInfo.systemUptime
            var previousTime: Double?
            var hasPlayed = false
            while !Task.isCancelled {
                do {
                    try await Task.sleep(nanoseconds: 500_000_000)
                } catch {
                    return
                }
                guard !Task.isCancelled, let self, let item, self.player.currentItem === item else { return }
                let now = ProcessInfo.processInfo.systemUptime
                let time = item.currentTime().seconds
                let transport = self.player.timeControlStatus
                if transport == .playing, time.isFinite, let previousTime, abs(time - previousTime) > 0.05 {
                    hasPlayed = true
                    lastProgress = now
                    if self.phase != .playing { self.phase = .playing }
                } else if self.phase == .playing,
                          transport == .waitingToPlayAtSpecifiedRate || now - lastProgress > 1.5 {
                    self.phase = .connecting
                }
                previousTime = time.isFinite ? time : nil
                // Repeated buffer/status notifications cannot extend a stalled route's deadline.
                if now - lastProgress >= (hasPlayed ? self.stallTimeout : self.startupTimeout) {
                    self.advance(after: item)
                    return
                }
            }
        }
    }

    private func detachItem() {
        watchdog?.cancel()
        watchdog = nil
        statusObservation?.invalidate()
        statusObservation = nil
        for token in notifications { NotificationCenter.default.removeObserver(token) }
        notifications.removeAll()
        player.pause()
        player.replaceCurrentItem(with: nil)
    }

    deinit {
        watchdog?.cancel()
        statusObservation?.invalidate()
        for token in notifications { NotificationCenter.default.removeObserver(token) }
    }
}
