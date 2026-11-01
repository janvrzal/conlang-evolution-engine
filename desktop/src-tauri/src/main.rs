// Ve vydaném sestavení na Windows nechceme vedle okna konzoli.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    cee_desktop_lib::run()
}
