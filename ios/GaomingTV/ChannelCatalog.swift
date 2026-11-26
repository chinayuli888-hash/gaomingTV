import Foundation

struct StreamRoute: Identifiable, Equatable {
    var id: String { url.absoluteString }
    let url: URL
}

struct Channel: Identifiable, Equatable {
    let id: String
    let name: String
    let group: String
    var routes: [StreamRoute]
}

enum CatalogError: LocalizedError {
    case missingResource, notUTF8, tooLarge, noChannels, fixtureUnavailable

    var errorDescription: String? {
        switch self {
        case .missingResource: return "没有找到内置频道清单。"
        case .notUTF8: return "请导入 UTF-8 编码的 M3U 或 TXT 文件。"
        case .tooLarge: return "频道清单超过 2 MB，请缩小文件后重试。"
        case .noChannels: return "清单中没有可用的 HTTPS 频道线路。"
        case .fixtureUnavailable: return "未能读取本地测试频道清单。"
        }
    }
}

enum ChannelCatalog {
    private static let byteLimit = 2 * 1024 * 1024

    static func load() async throws -> [Channel] {
        #if DEBUG
        if let raw = ProcessInfo.processInfo.environment["GAOMING_TEST_CATALOG_URL"] {
            guard let url = URL(string: raw), isLoopback(url),
                  ["http", "https"].contains(url.scheme?.lowercased() ?? "") else {
                throw CatalogError.fixtureUnavailable
            }
            var request = URLRequest(url: url)
            request.timeoutInterval = 12
            request.cachePolicy = .reloadIgnoringLocalCacheData
            let (data, response) = try await URLSession.shared.data(for: request)
            guard (response as? HTTPURLResponse)?.statusCode == 200 else { throw CatalogError.fixtureUnavailable }
            return try parse(data, allowLoopback: true)
        }
        #endif
        let bundled = try bundledChannels()
        let file = try savedPlaylist()
        guard FileManager.default.fileExists(atPath: file.path) else { return bundled }
        let custom = try parse(read(file))
        return merging(custom, into: bundled)
    }

    static func importFile(_ url: URL) throws -> (channels: [Channel], firstImportedID: String) {
        let scoped = url.startAccessingSecurityScopedResource()
        defer { if scoped { url.stopAccessingSecurityScopedResource() } }
        let data = try read(url)
        let imported = try parse(data)
        let combined = merging(imported, into: try bundledChannels())
        let file = try savedPlaylist()
        try FileManager.default.createDirectory(at: file.deletingLastPathComponent(), withIntermediateDirectories: true)
        try data.write(to: file, options: [.atomic])
        return (combined, imported[0].id)
    }

    private static func read(_ url: URL) throws -> Data {
        let file = try FileHandle(forReadingFrom: url)
        defer { try? file.close() }
        let data = try file.read(upToCount: byteLimit + 1) ?? Data()
        guard data.count <= byteLimit else { throw CatalogError.tooLarge }
        return data
    }

    private static func bundledChannels() throws -> [Channel] {
        guard let file = Bundle.main.url(forResource: "public-network", withExtension: "m3u") else {
            throw CatalogError.missingResource
        }
        return try parse(read(file))
    }

    private static func savedPlaylist() throws -> URL {
        try FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil,
                                    create: false).appendingPathComponent("ImportedChannels.m3u")
    }

    private static func isLoopback(_ url: URL) -> Bool {
        ["localhost", "127.0.0.1", "::1", "[::1]"].contains(url.host?.lowercased() ?? "")
    }

    private static func mediaURL(_ text: String, allowLoopback: Bool) -> URL? {
        guard let url = URL(string: text), let host = url.host, !host.isEmpty,
              url.user == nil, url.password == nil else { return nil }
        if url.scheme?.lowercased() == "https" { return url }
        #if DEBUG
        if allowLoopback && url.scheme?.lowercased() == "http" && isLoopback(url) { return url }
        #endif
        return nil
    }

    static func parse(_ data: Data, allowLoopback: Bool = false) throws -> [Channel] {
        guard data.count <= byteLimit else { throw CatalogError.tooLarge }
        guard let text = String(data: data, encoding: .utf8) else { throw CatalogError.notUTF8 }
        var entries: [Channel] = []
        var pending: (name: String, group: String)?
        var group = "自定义"
        let groups = try NSRegularExpression(pattern: #"\bgroup-title\s*=\s*"([^"]+)""#, options: .caseInsensitive)

        for raw in text.split(whereSeparator: { $0.isNewline }) {
            let line = String(raw).trimmingCharacters(in: .whitespacesAndNewlines)
                           .trimmingCharacters(in: CharacterSet(charactersIn: "\u{FEFF}"))
            if line.isEmpty { continue }
            if line.uppercased().hasPrefix("#EXTINF:") {
                pending = nil
                guard let comma = line.lastIndex(of: ",") else { continue }
                let name = String(line[line.index(after: comma)...]).trimmingCharacters(in: .whitespaces)
                var entryGroup = group
                let range = NSRange(line.startIndex..<comma, in: line)
                if let match = groups.firstMatch(in: line, range: range),
                   let bounds = Range(match.range(at: 1), in: line) { entryGroup = String(line[bounds]) }
                pending = (name, entryGroup)
                continue
            }
            if line.hasPrefix("#") { continue }

            let name: String
            let entryGroup: String
            let address: String
            if let details = pending {
                pending = nil
                (name, entryGroup, address) = (details.name, details.group, line)
            } else {
                guard let comma = line.firstIndex(of: ",") else { continue }
                name = String(line[..<comma]).trimmingCharacters(in: .whitespaces)
                address = String(line[line.index(after: comma)...]).trimmingCharacters(in: .whitespaces)
                if address.lowercased() == "#genre#" {
                    if !name.isEmpty { group = name }
                    continue
                }
                entryGroup = group
            }
            guard !name.isEmpty, let url = mediaURL(address, allowLoopback: allowLoopback) else { continue }
            entries.append(Channel(id: name, name: name, group: entryGroup, routes: [StreamRoute(url: url)]))
        }
        let channels = merging(entries, into: [])
        guard !channels.isEmpty else { throw CatalogError.noChannels }
        return channels
    }

    private static func merging(_ extra: [Channel], into base: [Channel]) -> [Channel] {
        var result = base
        var positions = Dictionary(uniqueKeysWithValues: base.indices.map { (base[$0].id, $0) })
        var seen = base.map { Set($0.routes.map(\.id)) }
        for channel in extra {
            if let index = positions[channel.id] {
                for route in channel.routes where seen[index].insert(route.id).inserted {
                    result[index].routes.append(route)
                }
            } else {
                positions[channel.id] = result.count
                result.append(channel)
                seen.append(Set(channel.routes.map(\.id)))
            }
        }
        return result
    }
}
