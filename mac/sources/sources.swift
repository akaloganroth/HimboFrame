// Gathers the things worth knowing and writes each as one line of text into
// ~/Library/Caches/quiet/. The Kindle script just reads those files.
//
//   next.txt      the next timed event in the coming 36 hours
//   now.txt       the event happening now (empty when there is none)
//   messages.txt  unread Messages, as a count (empty when there are none)
//
// It runs as its own background job so macOS ties the permissions to this one
// small program: calendar access (asked once) and, for Messages only, Full
// Disk Access (granted by hand in System Settings). Anything it cannot read is
// written as an empty file, never a guess.
import EventKit
import Foundation
import SQLite3

let folder = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Caches/quiet")
try? FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
func write(_ name: String, _ text: String) {
    try? text.write(to: folder.appendingPathComponent(name), atomically: true, encoding: .utf8)
}

// ---- calendar
let store = EKEventStore()
let wait = DispatchSemaphore(value: 0)
var allowed = false
if #available(macOS 14.0, *) {
    store.requestFullAccessToEvents { ok, _ in allowed = ok; wait.signal() }
} else {
    store.requestAccess(to: .event) { ok, _ in allowed = ok; wait.signal() }
}
_ = wait.wait(timeout: .now() + 120)

var next = "", current = ""
if allowed {
    let now = Date()
    let events = store.events(matching: store.predicateForEvents(
            withStart: now.addingTimeInterval(-12 * 3600), end: now.addingTimeInterval(36 * 3600), calendars: nil))
        .filter { !$0.isAllDay && $0.status != .canceled }
        .sorted { $0.startDate < $1.startDate }
    let clock = DateFormatter()
    clock.dateFormat = "h:mm a"
    if let e = events.first(where: { $0.startDate <= now && $0.endDate > now }) {
        current = "\(e.title ?? "Busy") · until \(clock.string(from: e.endDate))"
    }
    if let e = events.first(where: { $0.startDate > now }) {
        let day = Calendar.current.isDateInToday(e.startDate) ? "" : "tomorrow "
        next = "\(e.title ?? "Busy") · \(day)\(clock.string(from: e.startDate))"
    }
}
write("next.txt", next)
write("now.txt", current)

// ---- messages: how many unread, from how many conversations. No contents.
var messages = ""
var db: OpaquePointer?
let path = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Messages/chat.db").path
if sqlite3_open_v2(path, &db, SQLITE_OPEN_READONLY, nil) == SQLITE_OK {
    let sql = """
        select count(*), count(distinct handle_id) from message
        where is_read = 0 and is_from_me = 0 and item_type = 0
          and date > (strftime('%s','now','-7 days') - 978307200) * 1000000000
        """
    var query: OpaquePointer?
    if sqlite3_prepare_v2(db, sql, -1, &query, nil) == SQLITE_OK, sqlite3_step(query) == SQLITE_ROW {
        let count = sqlite3_column_int(query, 0), people = sqlite3_column_int(query, 1)
        if count > 0 {
            messages = "\(count) unread from \(people) \(people == 1 ? "person" : "people")"
        }
    }
    sqlite3_finalize(query)
}
sqlite3_close(db)
write("messages.txt", messages)
