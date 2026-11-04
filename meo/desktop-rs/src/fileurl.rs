//! A `file:` URL for a local path, correct on Windows too (no dependencies, so it can be tested alone:
//! `rustc --edition 2021 --test src/fileurl.rs`).
//!
//! `format!("file://{path}")` is only right for Unix paths, which start with `/`. A Windows path starts
//! with a drive letter, so `file://C:\Users\...` is not a valid URL: Qt reads `C:` as a host and reports
//! "QQmlApplicationEngine failed to load component ... Network error" with no window.

/// `/home/u/qml/Main.qml` → `file:///home/u/qml/Main.qml`;
/// `C:\Users\u\qml\Main.qml` → `file:///C:/Users/u/qml/Main.qml`. Spaces and non-ASCII are percent-encoded.
pub fn file_url(path: &str) -> String {
    let mut p = path.replace('\\', "/");
    // The extended-length prefix some Windows APIs add (`\\?\C:\...`).
    if let Some(rest) = p.strip_prefix("//?/") {
        p = rest.to_owned();
    }
    let mut out = String::from("file://");
    if !p.starts_with('/') {
        out.push('/');
    }
    for ch in p.chars() {
        if ch.is_ascii_alphanumeric() || "-._~/:".contains(ch) {
            out.push(ch);
        } else {
            let mut buf = [0u8; 4];
            for byte in ch.encode_utf8(&mut buf).bytes() {
                out.push_str(&format!("%{byte:02X}"));
            }
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::file_url;

    #[test]
    fn unix_paths_keep_their_leading_slash() {
        assert_eq!(file_url("/home/u/qml/Main.qml"), "file:///home/u/qml/Main.qml");
    }

    #[test]
    fn windows_paths_get_three_slashes_and_forward_slashes() {
        assert_eq!(
            file_url(r"C:\Users\Mingyue\AppData\Local\MeoAI\current\qml\Main.qml"),
            "file:///C:/Users/Mingyue/AppData/Local/MeoAI/current/qml/Main.qml"
        );
    }

    #[test]
    fn the_extended_length_prefix_is_dropped() {
        assert_eq!(file_url(r"\\?\C:\x\Main.qml"), "file:///C:/x/Main.qml");
    }

    #[test]
    fn spaces_and_non_ascii_are_percent_encoded() {
        assert_eq!(
            file_url(r"C:\Users\张三\Meo AI\Main.qml"),
            "file:///C:/Users/%E5%BC%A0%E4%B8%89/Meo%20AI/Main.qml"
        );
        assert_eq!(file_url("/tmp/a#b%c?d.qml"), "file:///tmp/a%23b%25c%3Fd.qml");
    }
}
