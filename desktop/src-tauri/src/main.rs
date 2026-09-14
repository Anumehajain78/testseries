// Without this a console window opens behind the examination window on
// Windows — a candidate cannot reach it while the window is on top, but it
// appears in the taskbar and survives the examination client, which is one
// more thing on the screen that should not be there.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    exam_lab_client_lib::run()
}
