//! Computer control: look at the screen and use the mouse and keyboard (desktop only). Modelled on
//! DeepSeek Harness' computer-use: the model gets a screenshot, answers in coordinates of that picture,
//! and the device translates them to the real screen. The device is driven by the tools the system
//! already has, so nothing is bundled: `screencapture` and `cliclick` on macOS, `xdotool` on X11,
//! `ydotool` on Wayland, and `grim`, `spectacle`, `gnome-screenshot`, `scrot` or ImageMagick to look.
//! When a needed tool is missing the result says which one to install.
//!
//! Everything here blocks (a command may take a moment); the host runs it off the app's thread.
//! Each call is a separate action the permission levels gate; the screenshot is a look, the rest act.

use super::agent::Outcome;
use serde_json::Value;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::Mutex;

/// The widest screenshot sent to the model; wider ones are scaled down (and made JPEG) to stay small.
const MAX_WIDTH: u32 = 1280;
/// The longest base64 picture the Meo API takes.
const MAX_CHARS: usize = 1_400_000;

/// How the last screenshot maps to the real screen: a click at `(x, y)` in the picture lands at
/// `(x * screen_w / shot_w, y * screen_h / shot_h)`.
#[derive(Clone, Copy, Debug, PartialEq)]
struct Geometry {
    shot_w: u32,
    shot_h: u32,
    screen_w: u32,
    screen_h: u32,
}

static LAST: Mutex<Option<Geometry>> = Mutex::new(None);

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Platform {
    Mac,
    X11,
    Wayland,
}

impl Platform {
    pub fn detect() -> Self {
        if cfg!(target_os = "macos") {
            Platform::Mac
        } else if std::env::var_os("WAYLAND_DISPLAY").is_some() {
            Platform::Wayland
        } else {
            Platform::X11
        }
    }
}

/// Where commands are looked up: the process's PATH, or another one (tests).
#[derive(Clone, Debug, Default)]
pub struct Env {
    pub path: Option<String>,
}

impl Env {
    fn find(&self, name: &str) -> Option<PathBuf> {
        let path = self.path.clone().or_else(|| std::env::var("PATH").ok())?;
        std::env::split_paths(&path).map(|d| d.join(name)).find(|p| p.is_file())
    }

    fn has(&self, name: &str) -> bool {
        self.find(name).is_some()
    }

    fn run(&self, name: &str, args: &[&str]) -> Result<String, String> {
        let program = self.find(name).ok_or_else(|| format!("{name} is not installed"))?;
        let out = Command::new(program)
            .args(args)
            .stdin(Stdio::null())
            .output()
            .map_err(|e| format!("cannot run {name}: {e}"))?;
        if out.status.success() {
            Ok(String::from_utf8_lossy(&out.stdout).trim().to_owned())
        } else {
            let why = String::from_utf8_lossy(&out.stderr);
            Err(format!("{name} failed: {}", why.trim().chars().take(300).collect::<String>()))
        }
    }
}

fn png_size(bytes: &[u8]) -> Option<(u32, u32)> {
    (bytes.len() > 24 && bytes.starts_with(&[0x89, b'P', b'N', b'G']))
        .then(|| (u32::from_be_bytes(bytes[16..20].try_into().unwrap()), u32::from_be_bytes(bytes[20..24].try_into().unwrap())))
}

/// The size of the real screen in the units the pointer uses.
fn screen_size(env: &Env, platform: Platform) -> Option<(u32, u32)> {
    match platform {
        Platform::Mac => {
            // "0, 0, 1512, 982"
            let text = env.run("osascript", &["-e", "tell application \"Finder\" to get bounds of window of desktop"]).ok()?;
            let n: Vec<u32> = text.split(',').filter_map(|p| p.trim().parse().ok()).collect();
            (n.len() == 4).then(|| (n[2].saturating_sub(n[0]), n[3].saturating_sub(n[1])))
        }
        Platform::X11 => {
            let text = env.run("xdotool", &["getdisplaygeometry"]).ok()?;
            let mut it = text.split_whitespace().filter_map(|p| p.parse().ok());
            Some((it.next()?, it.next()?))
        }
        Platform::Wayland => None,
    }
}

fn capture(env: &Env, platform: Platform, file: &Path) -> Result<(), String> {
    let f = file.to_str().ok_or("bad path")?;
    let tried: Vec<(&str, Vec<&str>)> = match platform {
        Platform::Mac => vec![("screencapture", vec!["-x", "-t", "png", f])],
        Platform::Wayland => vec![("grim", vec![f]), ("spectacle", vec!["-b", "-n", "-o", f]), ("gnome-screenshot", vec!["-f", f])],
        Platform::X11 => vec![("scrot", vec!["-o", f]), ("import", vec!["-window", "root", f]), ("spectacle", vec!["-b", "-n", "-o", f]), ("gnome-screenshot", vec!["-f", f])],
    };
    let mut last_error = None;
    for (name, args) in &tried {
        if env.has(name) {
            match env.run(name, args) {
                Ok(_) if file.is_file() => return Ok(()),
                Ok(_) => last_error = Some(format!("{name} made no picture")),
                Err(e) => last_error = Some(e),
            }
        }
    }
    Err(last_error.unwrap_or_else(|| {
        let names: Vec<&str> = tried.iter().map(|t| t.0).collect();
        format!("no screenshot tool is installed; install one of: {}", names.join(", "))
    }))
}

fn screenshot(env: &Env, platform: Platform) -> Outcome {
    let file = std::env::temp_dir().join(format!("meo-shot-{}-{}.png", std::process::id(), super::now_secs()));
    if let Err(e) = capture(env, platform, &file) {
        return Outcome::fail(e);
    }
    let bytes = std::fs::read(&file).unwrap_or_default();
    let _ = std::fs::remove_file(&file);
    let Some((orig_w, orig_h)) = png_size(&bytes) else {
        return Outcome::fail("the screenshot tool did not make a PNG");
    };
    // Smaller and as JPEG when the screen is wide, so the picture stays within what the API takes.
    let (mime, data, shot_w, shot_h) = if orig_w > MAX_WIDTH {
        match shrink(&bytes) {
            Ok((jpeg, w, h)) => ("image/jpeg", jpeg, w, h),
            Err(e) => return Outcome::fail(e),
        }
    } else {
        ("image/png", bytes, orig_w, orig_h)
    };
    use base64::{engine::general_purpose::STANDARD, Engine};
    let encoded = STANDARD.encode(&data);
    if encoded.len() > MAX_CHARS {
        return Outcome::fail("the screenshot is too large to send even after scaling it down");
    }
    // A retina Mac's picture has twice the pixels of the pointer's space: the real screen size tells.
    let (screen_w, screen_h) = screen_size(env, platform).unwrap_or((orig_w, orig_h));
    if let Ok(mut last) = LAST.lock() {
        *last = Some(Geometry { shot_w, shot_h, screen_w, screen_h });
    }
    Outcome::done(format!(
        "Screenshot {shot_w}x{shot_h}. Give coordinates for the other computer tools as pixels of this picture (0,0 is the top left)."
    ))
    .with_images(vec![(mime.to_owned(), encoded)])
}

fn shrink(png: &[u8]) -> Result<(Vec<u8>, u32, u32), String> {
    let picture = image::load_from_memory(png).map_err(|e| format!("cannot read the screenshot: {e}"))?;
    let scaled = picture.resize(MAX_WIDTH, MAX_WIDTH * 4, image::imageops::FilterType::Triangle).to_rgb8();
    let (w, h) = (scaled.width(), scaled.height());
    let mut out = Vec::new();
    image::codecs::jpeg::JpegEncoder::new_with_quality(&mut out, 70)
        .encode_image(&scaled)
        .map_err(|e| format!("cannot encode the screenshot: {e}"))?;
    Ok((out, w, h))
}

/// A point of the last screenshot as a point of the real screen.
fn to_screen(x: f64, y: f64) -> Result<(i64, i64), String> {
    let g = LAST.lock().ok().and_then(|l| *l).ok_or("take a screenshot first: coordinates are pixels of it")?;
    if x < 0.0 || y < 0.0 || x > f64::from(g.shot_w) || y > f64::from(g.shot_h) {
        return Err(format!("({x}, {y}) is outside the screenshot, which is {}x{}", g.shot_w, g.shot_h));
    }
    Ok(((x * f64::from(g.screen_w) / f64::from(g.shot_w)).round() as i64, (y * f64::from(g.screen_h) / f64::from(g.shot_h)).round() as i64))
}

fn num(args: &Value, key: &str) -> Result<f64, String> {
    args[key].as_f64().ok_or_else(|| format!("needs a number \"{key}\""))
}

fn point(args: &Value) -> Result<(i64, i64), String> {
    to_screen(num(args, "x")?, num(args, "y")?)
}

/// The key names the model may use, as each tool spells them.
fn key_name(platform: Platform, key: &str) -> Option<String> {
    let k = key.trim().to_lowercase();
    if k.is_empty() {
        return None;
    }
    let named = |mac: &str, x11: &str| Some(if platform == Platform::Mac { mac } else { x11 }.to_owned());
    match k.as_str() {
        "enter" | "return" => named("return", "Return"),
        "esc" | "escape" => named("esc", "Escape"),
        "tab" => named("tab", "Tab"),
        "space" => named("space", "space"),
        "backspace" => named("delete", "BackSpace"),
        "delete" => named("fwd-delete", "Delete"),
        "up" => named("arrow-up", "Up"),
        "down" => named("arrow-down", "Down"),
        "left" => named("arrow-left", "Left"),
        "right" => named("arrow-right", "Right"),
        "pageup" | "page_up" => named("page-up", "Prior"),
        "pagedown" | "page_down" => named("page-down", "Next"),
        "home" => named("home", "Home"),
        "end" => named("end", "End"),
        "ctrl" | "control" => named("ctrl", "ctrl"),
        "shift" => named("shift", "shift"),
        "alt" | "option" => named("alt", "alt"),
        "cmd" | "command" | "super" | "meta" | "win" => named("cmd", "super"),
        s if s.len() == 1 && s.chars().all(|c| c.is_ascii_alphanumeric()) => Some(s.to_owned()),
        s if s.starts_with('f') && s[1..].parse::<u8>().is_ok_and(|n| (1..=12).contains(&n)) => Some(s.to_owned()),
        _ => None,
    }
}

/// Linux input event codes for ydotool (a US layout).
fn evdev(key: &str) -> Option<u32> {
    const LETTERS: &str = "qwertyuiop";
    const HOME_ROW: &str = "asdfghjkl";
    const BOTTOM: &str = "zxcvbnm";
    let k = key.to_lowercase();
    Some(match k.as_str() {
        "enter" | "return" => 28, "esc" | "escape" => 1, "tab" => 15, "space" => 57, "backspace" => 14, "delete" => 111,
        "up" => 103, "down" => 108, "left" => 105, "right" => 106, "pageup" | "page_up" => 104, "pagedown" | "page_down" => 109,
        "home" => 102, "end" => 107, "ctrl" | "control" => 29, "shift" => 42, "alt" | "option" => 56,
        "cmd" | "command" | "super" | "meta" | "win" => 125,
        "0" => 11,
        s if s.len() == 1 => {
            let c = s.chars().next()?;
            if let Some(i) = LETTERS.find(c) {
                16 + i as u32
            } else if let Some(i) = HOME_ROW.find(c) {
                30 + i as u32
            } else if let Some(i) = BOTTOM.find(c) {
                44 + i as u32
            } else if c.is_ascii_digit() {
                1 + c.to_digit(10)?
            } else {
                return None;
            }
        }
        s if s.starts_with('f') => 58 + s[1..].parse::<u32>().ok().filter(|n| (1..=10).contains(n))? - 1,
        _ => return None,
    })
}

/// A key or a combination such as `ctrl+c`, as the arguments of the platform's tool.
fn press(env: &Env, platform: Platform, combo: &str) -> Result<(), String> {
    let parts: Vec<&str> = combo.split('+').map(str::trim).filter(|p| !p.is_empty()).collect();
    if parts.is_empty() {
        return Err("press_key needs a key such as enter, tab, ctrl+c".to_owned());
    }
    match platform {
        Platform::Mac => {
            let names: Vec<String> = parts.iter().map(|p| key_name(platform, p).ok_or(format!("unknown key \"{p}\""))).collect::<Result<_, _>>()?;
            let (last, mods) = names.split_last().ok_or("no key")?;
            let mut args: Vec<String> = mods.iter().map(|m| format!("kd:{m}")).collect();
            args.push(if last.len() == 1 { format!("t:{last}") } else { format!("kp:{last}") });
            args.extend(mods.iter().rev().map(|m| format!("ku:{m}")));
            env.run("cliclick", &args.iter().map(String::as_str).collect::<Vec<_>>()).map(|_| ())
        }
        Platform::X11 => {
            let names: Vec<String> = parts.iter().map(|p| key_name(platform, p).ok_or(format!("unknown key \"{p}\""))).collect::<Result<_, _>>()?;
            env.run("xdotool", &["key", "--", &names.join("+")]).map(|_| ())
        }
        Platform::Wayland => {
            let codes: Vec<u32> = parts.iter().map(|p| evdev(p).ok_or(format!("unknown key \"{p}\""))).collect::<Result<_, _>>()?;
            let mut args: Vec<String> = vec!["key".to_owned()];
            args.extend(codes.iter().map(|c| format!("{c}:1")));
            args.extend(codes.iter().rev().map(|c| format!("{c}:0")));
            env.run("ydotool", &args.iter().map(String::as_str).collect::<Vec<_>>()).map(|_| ())
        }
    }
}

fn click(env: &Env, platform: Platform, x: i64, y: i64, button: &str, times: u8) -> Result<(), String> {
    let button = match button {
        "" | "left" => "left",
        "right" => "right",
        "middle" => "middle",
        other => return Err(format!("button is left, right or middle, not \"{other}\"")),
    };
    match platform {
        Platform::Mac => {
            if button == "middle" {
                return Err("cliclick cannot press the middle button".to_owned());
            }
            let verb = match (button, times) {
                ("right", _) => "rc",
                (_, 2) => "dc",
                _ => "c",
            };
            env.run("cliclick", &[&format!("{verb}:{x},{y}")]).map(|_| ())
        }
        Platform::X11 => {
            let code = match button { "left" => "1", "middle" => "2", _ => "3" };
            let (xs, ys) = (x.to_string(), y.to_string());
            let mut args = vec!["mousemove", xs.as_str(), ys.as_str(), "click"];
            if times == 2 {
                args.extend(["--repeat", "2", "--delay", "80"]);
            }
            args.push(code);
            env.run("xdotool", &args).map(|_| ())
        }
        Platform::Wayland => {
            let (xs, ys) = (x.to_string(), y.to_string());
            env.run("ydotool", &["mousemove", "--absolute", "-x", &xs, "-y", &ys])?;
            let code = match button { "left" => "0xC0", "right" => "0xC1", _ => "0xC2" };
            for _ in 0..times {
                env.run("ydotool", &["click", code])?;
            }
            Ok(())
        }
    }
}

fn need_input_tool(env: &Env, platform: Platform) -> Result<(), String> {
    let (tool, hint) = match platform {
        Platform::Mac => ("cliclick", "brew install cliclick (and allow it under System Settings > Privacy & Security > Accessibility)"),
        Platform::X11 => ("xdotool", "install xdotool with your package manager"),
        Platform::Wayland => ("ydotool", "install ydotool and start its ydotoold service (it needs access to /dev/uinput)"),
    };
    if env.has(tool) { Ok(()) } else { Err(format!("{tool} is not installed: {hint}")) }
}

/// Runs one computer tool: `computer_screenshot`, `computer_click`, `computer_double_click`, `computer_move`,
/// `computer_type`, `computer_key`, `computer_scroll` or `computer_drag`.
pub fn run(action: &str, args: &Value) -> Outcome {
    run_with(&Env::default(), Platform::detect(), action, args)
}

pub fn run_with(env: &Env, platform: Platform, action: &str, args: &Value) -> Outcome {
    if action == "computer_screenshot" {
        return screenshot(env, platform);
    }
    if let Err(e) = need_input_tool(env, platform) {
        return Outcome::fail(e);
    }
    let result: Result<String, String> = (|| match action {
        "computer_click" | "computer_double_click" => {
            let (x, y) = point(args)?;
            let times = if action == "computer_double_click" { 2 } else { 1 };
            click(env, platform, x, y, args["button"].as_str().unwrap_or("left"), times)?;
            Ok(format!("Clicked at ({x}, {y}). Take a screenshot to see the result."))
        }
        "computer_move" => {
            let (x, y) = point(args)?;
            match platform {
                Platform::Mac => env.run("cliclick", &[&format!("m:{x},{y}")])?,
                Platform::X11 => env.run("xdotool", &["mousemove", &x.to_string(), &y.to_string()])?,
                Platform::Wayland => env.run("ydotool", &["mousemove", "--absolute", "-x", &x.to_string(), "-y", &y.to_string()])?,
            };
            Ok(format!("Moved the pointer to ({x}, {y})."))
        }
        "computer_type" => {
            let text = args["text"].as_str().filter(|t| !t.is_empty()).ok_or("computer_type needs the \"text\"")?;
            if text.chars().count() > 2000 {
                return Err("type at most 2000 characters at a time".to_owned());
            }
            match platform {
                Platform::Mac => env.run("cliclick", &[&format!("t:{text}")])?,
                Platform::X11 => env.run("xdotool", &["type", "--delay", "20", "--", text])?,
                Platform::Wayland => env.run("ydotool", &["type", "--", text])?,
            };
            Ok(format!("Typed {} characters.", text.chars().count()))
        }
        "computer_key" => {
            let key = args["key"].as_str().ok_or("computer_key needs the \"key\", such as enter or ctrl+c")?;
            press(env, platform, key)?;
            Ok(format!("Pressed {key}."))
        }
        "computer_scroll" => {
            let (x, y) = point(args)?;
            let amount = args["amount"].as_i64().unwrap_or(3).clamp(1, 30);
            let down = args["direction"].as_str().unwrap_or("down") != "up";
            match platform {
                Platform::X11 => {
                    env.run("xdotool", &["mousemove", &x.to_string(), &y.to_string()])?;
                    env.run("xdotool", &["click", "--repeat", &amount.to_string(), if down { "5" } else { "4" }])?;
                }
                _ => {
                    // No wheel in cliclick or ydotool's simple form: the pointer goes there and the page keys scroll.
                    click(env, platform, x, y, "left", 1)?;
                    for _ in 0..amount.min(10) {
                        press(env, platform, if down { "pagedown" } else { "pageup" })?;
                    }
                }
            }
            Ok(format!("Scrolled {} by {amount}.", if down { "down" } else { "up" }))
        }
        "computer_drag" => {
            let (x1, y1) = to_screen(num(args, "x")?, num(args, "y")?)?;
            let (x2, y2) = to_screen(num(args, "to_x")?, num(args, "to_y")?)?;
            match platform {
                Platform::Mac => { env.run("cliclick", &[&format!("dd:{x1},{y1}"), &format!("du:{x2},{y2}")])?; }
                Platform::X11 => { env.run("xdotool", &["mousemove", &x1.to_string(), &y1.to_string(), "mousedown", "1", "mousemove", &x2.to_string(), &y2.to_string(), "mouseup", "1"])?; }
                Platform::Wayland => return Err("dragging is not supported with ydotool here".to_owned()),
            }
            Ok(format!("Dragged from ({x1}, {y1}) to ({x2}, {y2})."))
        }
        other => Err(format!("unknown computer tool \"{other}\"")),
    })();
    match result {
        Ok(t) => Outcome::done(t),
        Err(e) => Outcome::fail(e),
    }
}

#[cfg(all(test, unix))]
mod tests {
    use super::*;
    use serde_json::json;
    use std::os::unix::fs::PermissionsExt;

    /// A folder of shell scripts standing in for the system tools; each one appends its arguments to `log`.
    struct Shims {
        dir: PathBuf,
    }

    impl Shims {
        fn new(tag: &str) -> Self {
            let dir = std::env::temp_dir().join(format!("meo-shims-{tag}-{}", std::process::id()));
            std::fs::create_dir_all(&dir).unwrap();
            Self { dir }
        }
        fn tool(&self, name: &str, body: &str) -> &Self {
            let file = self.dir.join(name);
            std::fs::write(&file, format!("#!/bin/sh\n{body}\n")).unwrap();
            std::fs::set_permissions(&file, std::fs::Permissions::from_mode(0o755)).unwrap();
            self
        }
        fn logging(&self, name: &str) -> &Self {
            let log = self.dir.join("log");
            self.tool(name, &format!("echo \"{name} $*\" >> {}", log.display()))
        }
        fn env(&self) -> Env {
            Env { path: Some(self.dir.display().to_string()) }
        }
        fn log(&self) -> String {
            std::fs::read_to_string(self.dir.join("log")).unwrap_or_default()
        }
    }

    impl Drop for Shims {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.dir);
        }
    }

    /// A PNG header for a picture of this size (only the header is read before scaling).
    fn png(w: u32, h: u32) -> Vec<u8> {
        let img = image::RgbImage::new(w, h);
        let mut out = Vec::new();
        image::codecs::png::PngEncoder::new(&mut out).write_image(img.as_raw(), w, h, image::ExtendedColorType::Rgb8).unwrap();
        out
    }
    use image::ImageEncoder;

    fn set_last(g: Option<Geometry>) {
        *LAST.lock().unwrap() = g;
    }

    /// The tests share the last-screenshot slot, so they run one at a time.
    static ONE_AT_A_TIME: Mutex<()> = Mutex::new(());

    #[test]
    fn a_screenshot_is_scaled_down_and_clicks_land_on_the_real_screen() {
        let _one = ONE_AT_A_TIME.lock().unwrap_or_else(|e| e.into_inner());
        let s = Shims::new("x11");
        let shot = s.dir.join("fixture.png");
        std::fs::write(&shot, png(2560, 1600)).unwrap();
        s.tool("scrot", &format!("for last; do :; done; cp {} \"$last\"", shot.display()));
        s.tool("xdotool", &format!("if [ \"$1\" = getdisplaygeometry ]; then echo '1280 800'; else echo \"xdotool $*\" >> {}; fi", s.dir.join("log").display()));
        let env = s.env();
        let out = run_with(&env, Platform::X11, "computer_screenshot", &json!({}));
        assert!(out.ok, "{}", out.text);
        assert!(out.text.contains("Screenshot 1280x800"), "{}", out.text);
        assert_eq!(out.images.len(), 1);
        assert_eq!(out.images[0].0, "image/jpeg", "a wide screen is sent as a smaller JPEG");
        // (640, 400) in the 1280x800 picture is (640, 400) on the 1280x800 screen.
        let click = run_with(&env, Platform::X11, "computer_click", &json!({ "x": 640, "y": 400 }));
        assert!(click.ok, "{}", click.text);
        assert!(s.log().contains("xdotool mousemove 640 400 click 1"), "{}", s.log());
        let right = run_with(&env, Platform::X11, "computer_double_click", &json!({ "x": 100, "y": 50, "button": "right" }));
        assert!(right.ok);
        assert!(s.log().contains("mousemove 100 50 click --repeat 2 --delay 80 3"), "{}", s.log());
        let off = run_with(&env, Platform::X11, "computer_click", &json!({ "x": 5000, "y": 10 }));
        assert!(!off.ok && off.text.contains("outside the screenshot"), "{}", off.text);
    }

    #[test]
    fn a_retina_picture_is_mapped_to_the_pointer_space_on_a_mac() {
        let _one = ONE_AT_A_TIME.lock().unwrap_or_else(|e| e.into_inner());
        let s = Shims::new("mac");
        let shot = s.dir.join("fixture.png");
        std::fs::write(&shot, png(1000, 600)).unwrap();
        s.tool("screencapture", &format!("for last; do :; done; cp {} \"$last\"", shot.display()));
        s.tool("osascript", "echo '0, 0, 500, 300'");
        s.logging("cliclick");
        let env = s.env();
        let out = run_with(&env, Platform::Mac, "computer_screenshot", &json!({}));
        assert!(out.ok && out.images[0].0 == "image/png", "{}", out.text);
        let click = run_with(&env, Platform::Mac, "computer_click", &json!({ "x": 500, "y": 300 }));
        assert!(click.ok, "{}", click.text);
        assert!(s.log().contains("cliclick c:250,150"), "the picture has twice the pixels: {}", s.log());
        assert!(run_with(&env, Platform::Mac, "computer_type", &json!({ "text": "hello" })).ok);
        assert!(run_with(&env, Platform::Mac, "computer_key", &json!({ "key": "cmd+c" })).ok);
        assert!(s.log().contains("cliclick t:hello") && s.log().contains("cliclick kd:cmd t:c ku:cmd"), "{}", s.log());
        assert!(run_with(&env, Platform::Mac, "computer_key", &json!({ "key": "enter" })).ok);
        assert!(s.log().contains("kp:return"), "{}", s.log());
    }

    #[test]
    fn a_missing_tool_says_what_to_install_and_bad_input_is_explained() {
        let _one = ONE_AT_A_TIME.lock().unwrap_or_else(|e| e.into_inner());
        let s = Shims::new("none");
        let env = s.env();
        let shot = run_with(&env, Platform::X11, "computer_screenshot", &json!({}));
        assert!(!shot.ok && shot.text.contains("install one of: scrot"), "{}", shot.text);
        let click = run_with(&env, Platform::X11, "computer_click", &json!({ "x": 1, "y": 1 }));
        assert!(!click.ok && click.text.contains("xdotool is not installed"), "{}", click.text);
        let mac = run_with(&env, Platform::Mac, "computer_click", &json!({ "x": 1, "y": 1 }));
        assert!(mac.text.contains("brew install cliclick"), "{}", mac.text);
        s.logging("xdotool");
        set_last(None);
        let early = run_with(&env, Platform::X11, "computer_click", &json!({ "x": 1, "y": 1 }));
        assert!(!early.ok && early.text.contains("take a screenshot first"), "{}", early.text);
        set_last(Some(Geometry { shot_w: 100, shot_h: 100, screen_w: 100, screen_h: 100 }));
        assert!(run_with(&env, Platform::X11, "computer_key", &json!({ "key": "ctrl+nonsense" })).text.contains("unknown key"));
        assert!(run_with(&env, Platform::X11, "computer_type", &json!({})).text.contains("needs the \"text\""));
        assert!(run_with(&env, Platform::X11, "computer_teleport", &json!({})).text.contains("unknown computer tool"));
        assert!(run_with(&env, Platform::X11, "computer_click", &json!({ "x": 1, "y": 1, "button": "side" })).text.contains("left, right or middle"));
    }

    #[test]
    fn wayland_uses_ydotool_with_key_codes() {
        let _one = ONE_AT_A_TIME.lock().unwrap_or_else(|e| e.into_inner());
        let s = Shims::new("wl");
        s.logging("ydotool");
        set_last(Some(Geometry { shot_w: 100, shot_h: 100, screen_w: 200, screen_h: 200 }));
        let env = s.env();
        assert!(run_with(&env, Platform::Wayland, "computer_click", &json!({ "x": 10, "y": 20 })).ok);
        assert!(run_with(&env, Platform::Wayland, "computer_key", &json!({ "key": "ctrl+c" })).ok);
        let log = s.log();
        assert!(log.contains("ydotool mousemove --absolute -x 20 -y 40") && log.contains("ydotool click 0xC0"), "{log}");
        assert!(log.contains("ydotool key 29:1 46:1 46:0 29:0"), "{log}");
    }
}
