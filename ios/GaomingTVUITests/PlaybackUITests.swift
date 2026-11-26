import XCTest

final class PlaybackUITests: XCTestCase {
    @MainActor private lazy var app = XCUIApplication()

    override func setUpWithError() throws {
        continueAfterFailure = false
    }

    @MainActor private func element(_ id: String) -> XCUIElement {
        app.descendants(matching: .any).matching(identifier: id).firstMatch
    }

    @MainActor private func assertPlayback(_ phase: String, file: StaticString = #filePath, line: UInt = #line) {
        let status = element("playback.phase")
        let expected = NSPredicate(format: "exists == true AND value == %@", phase)
        let ready = XCTNSPredicateExpectation(predicate: expected, object: status)
        XCTAssertEqual(XCTWaiter.wait(for: [ready], timeout: 60), .completed,
                       "Expected \(phase)\n\(app.debugDescription)", file: file, line: line)
    }

    @MainActor private func capture(_ name: String) {
        let attachment = XCTAttachment(uniformTypeIdentifier: "public.png", name: name + ".png",
                                       payload: XCUIScreen.main.screenshot().pngRepresentation, userInfo: nil)
        attachment.lifetime = .keepAlways
        add(attachment)
    }

    @MainActor func testAutomaticFailoverAndChannelSwitch() {
        XCUIDevice.shared.orientation = .portrait
        app.launchEnvironment["GAOMING_TEST_CATALOG_URL"] = "http://localhost:8765/catalog.m3u"
        app.launch()

        assertPlayback("playing")
        XCTAssertEqual(element("playback.channel").label, "Test A")
        let route = element("playback.route").label.replacingOccurrences(of: " ", with: "")
        XCTAssertTrue(route.contains("2/2"), "Expected backup route, found \(route)")
        capture("fallback-playing")

        let next = element("channel.Test B")
        XCTAssertTrue(next.waitForExistence(timeout: 10))
        next.tap()
        XCTAssertEqual(element("playback.channel").label, "Test B")
        assertPlayback("playing")
        capture("channel-switch-playing")

        element("channel.Test Off").tap()
        assertPlayback("failed")
        XCTAssertTrue(element("playback.retry").exists)
        element("channel.Test B").tap()
        assertPlayback("playing")
    }

    @MainActor func testBundledCatalogAndLandscape() {
        XCUIDevice.shared.orientation = .portrait
        app.launch()
        let cgtn = element("channel.CGTN")
        XCTAssertTrue(cgtn.waitForExistence(timeout: 15), app.debugDescription)
        capture("bundled-catalog-portrait")
        XCUIDevice.shared.orientation = .landscapeLeft
        let deadline = Date().addingTimeInterval(15)
        while app.frame.width <= app.frame.height && Date() < deadline {
            RunLoop.current.run(until: Date().addingTimeInterval(0.2))
        }
        XCTAssertGreaterThan(app.frame.width, app.frame.height)
        XCTAssertTrue(cgtn.exists)
        capture("bundled-catalog-landscape")
    }
}
