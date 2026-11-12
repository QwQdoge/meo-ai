//! Scheduled tasks: a prompt that Meo sends by itself later, once or on a rhythm. Modelled on DeepSeek
//! Harness' host-wide schedule: tasks are stored apart from any chat, have a typed timing (`after`,
//! `at`, `every`, `daily`, `weekly`, `cron`), a delivery target (a new chat each time, or one chat),
//! and are delivered by one timer while the app runs. A delivery missed while the app was closed is
//! coalesced: it is delivered once, then the next future occurrence is scheduled. Wall-clock rules use
//! the UTC offset the device reported, so no time-zone database is needed.
//!
//! Nothing here reads the clock: callers pass `now` (unix seconds), which keeps it testable.

use serde::{Deserialize, Serialize};
use serde_json::Value;

/// The shortest repeat and the shortest gap between two deliveries of one task.
pub const MIN_GAP_SECS: u64 = 60;
pub const MAX_TASKS: usize = 50;
/// Longest wait for an `after` delay or the first `every` (a year).
const MAX_SPAN: u64 = 366 * 86_400;

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum Timing {
    /// Once, this many seconds after it was created.
    After { secs: u64 },
    /// Once, at a fixed instant (unix seconds).
    At { at: i64 },
    /// Every so many seconds, aligned to the moment it was created.
    Every { secs: u64 },
    /// Every day at a local time (minutes after midnight).
    Daily { minute: u32 },
    /// On some weekdays (1 = Monday ... 7 = Sunday) at a local time.
    Weekly { minute: u32, days: Vec<u8> },
    /// Five-field cron (minute hour day-of-month month day-of-week), in local time.
    Cron { expr: String },
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Task {
    pub id: String,
    pub title: String,
    pub prompt: String,
    pub timing: Timing,
    /// Minutes east of UTC when the task was made; wall-clock timings use it.
    pub offset_min: i32,
    /// `new`: a new chat each time. `session`: always the same chat (made by the first delivery).
    pub target: String,
    pub conversation: Option<String>,
    pub active: bool,
    pub ended: bool,
    /// Next delivery (unix seconds), when active and not ended.
    pub next: Option<i64>,
    pub anchor: i64,
    pub created: i64,
    pub last: Option<i64>,
    pub deliveries: u32,
}

// ---- civil time ----------------------------------------------------------------------------------

/// Days since 1970-01-01 for a civil date (Howard Hinnant's algorithm).
fn days_from_civil(y: i64, m: i64, d: i64) -> i64 {
    let y = if m <= 2 { y - 1 } else { y };
    let era = y.div_euclid(400);
    let yoe = y - era * 400;
    let doy = (153 * (if m > 2 { m - 3 } else { m + 9 }) + 2) / 5 + d - 1;
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    era * 146_097 + doe - 719_468
}

fn civil_from_days(z: i64) -> (i64, i64, i64) {
    let z = z + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let y = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    (if m <= 2 { y + 1 } else { y }, m, d)
}

/// ISO weekday of a day number: 1 = Monday ... 7 = Sunday.
fn weekday(day: i64) -> u8 {
    // 1970-01-01 was a Thursday (4).
    ((day + 3).rem_euclid(7) + 1) as u8
}

/// The local wall clock of `unix` at `offset_min`: (day number, minute of day).
fn local(unix: i64, offset_min: i32) -> (i64, u32) {
    let t = unix + i64::from(offset_min) * 60;
    (t.div_euclid(86_400), (t.rem_euclid(86_400) / 60) as u32)
}

fn unix_of(day: i64, minute: u32, offset_min: i32) -> i64 {
    day * 86_400 + i64::from(minute) * 60 - i64::from(offset_min) * 60
}

/// `2026-11-12T09:30[:00][.fff](Z|+08:00)` as unix seconds. The offset is required: "9am" alone is ambiguous.
pub fn parse_instant(text: &str) -> Result<i64, String> {
    let bad = || format!("\"{text}\" is not a time like 2026-11-12T09:30:00+08:00 (the offset or Z is required)");
    let t = text.trim();
    let (date, rest) = t.split_once(['T', 't', ' ']).ok_or_else(bad)?;
    let mut d = date.split('-');
    let (y, m, day) = (
        d.next().and_then(|v| v.parse::<i64>().ok()).ok_or_else(bad)?,
        d.next().and_then(|v| v.parse::<i64>().ok()).ok_or_else(bad)?,
        d.next().and_then(|v| v.parse::<i64>().ok()).ok_or_else(bad)?,
    );
    if !(1..=12).contains(&m) || !(1..=31).contains(&day) || !(1970..=9999).contains(&y) {
        return Err(bad());
    }
    let split = rest.find(['Z', 'z', '+', '-']).ok_or_else(bad)?;
    let (clock, zone) = rest.split_at(split);
    let mut c = clock.split(':');
    let hour = c.next().and_then(|v| v.parse::<i64>().ok()).ok_or_else(bad)?;
    let min = c.next().and_then(|v| v.parse::<i64>().ok()).ok_or_else(bad)?;
    let sec = c.next().map_or(Some(0), |v| v.split('.').next().and_then(|s| s.parse::<i64>().ok())).ok_or_else(bad)?;
    if !(0..24).contains(&hour) || !(0..60).contains(&min) || !(0..60).contains(&sec) {
        return Err(bad());
    }
    let offset = if zone.eq_ignore_ascii_case("z") {
        0
    } else {
        let sign = if zone.starts_with('-') { -1 } else { 1 };
        let body = &zone[1..];
        let (h, mm) = body.split_once(':').unwrap_or((body, "0"));
        sign * (h.parse::<i64>().map_err(|_| bad())? * 60 + mm.parse::<i64>().map_err(|_| bad())?)
    };
    // A day that does not exist (31 February) would silently roll over.
    let days = days_from_civil(y, m, day);
    if civil_from_days(days) != (y, m, day) {
        return Err(bad());
    }
    Ok(days * 86_400 + hour * 3600 + min * 60 + sec - offset * 60)
}

fn parse_clock(text: &str) -> Result<u32, String> {
    let bad = || format!("\"{text}\" is not a time of day like 09:30");
    let (h, m) = text.trim().split_once(':').ok_or_else(bad)?;
    let (h, m) = (h.parse::<u32>().map_err(|_| bad())?, m.split(':').next().unwrap_or("0").parse::<u32>().map_err(|_| bad())?);
    if h > 23 || m > 59 {
        return Err(bad());
    }
    Ok(h * 60 + m)
}

fn clock_text(minute: u32) -> String {
    format!("{:02}:{:02}", minute / 60, minute % 60)
}

// ---- cron ----------------------------------------------------------------------------------------

struct Cron {
    minute: Vec<bool>,
    hour: Vec<bool>,
    dom: Vec<bool>,
    month: Vec<bool>,
    dow: Vec<bool>,
    dom_star: bool,
    dow_star: bool,
}

fn cron_field(text: &str, lo: u32, hi: u32, name: &str) -> Result<Vec<bool>, String> {
    let mut set = vec![false; (hi + 1) as usize];
    for part in text.split(',') {
        let (range, step) = match part.split_once('/') {
            Some((r, s)) => (r, s.parse::<u32>().ok().filter(|s| *s > 0).ok_or(format!("bad step in {name}: {part}"))?),
            None => (part, 1),
        };
        let (from, to) = if range == "*" {
            (lo, hi)
        } else if let Some((a, b)) = range.split_once('-') {
            (
                a.parse::<u32>().map_err(|_| format!("bad {name}: {part}"))?,
                b.parse::<u32>().map_err(|_| format!("bad {name}: {part}"))?,
            )
        } else {
            let v = range.parse::<u32>().map_err(|_| format!("bad {name}: {part}"))?;
            // "5/2" (a value with a step) is not accepted, as in DeepSeek's cron subset.
            if part.contains('/') {
                return Err(format!("a step needs * or a range in {name}: {part}"));
            }
            (v, v)
        };
        if from < lo || to > hi || from > to {
            return Err(format!("{name} must be between {lo} and {hi}: {part}"));
        }
        let mut v = from;
        while v <= to {
            set[v as usize] = true;
            v += step;
        }
    }
    Ok(set)
}

fn parse_cron(expr: &str) -> Result<Cron, String> {
    let f: Vec<&str> = expr.split_whitespace().collect();
    if f.len() != 5 {
        return Err("a cron expression has five fields: minute hour day-of-month month day-of-week".to_owned());
    }
    // Sunday is 0 or 7.
    let mut dow = cron_field(f[4], 0, 7, "day-of-week")?;
    if dow[7] {
        dow[0] = true;
    }
    dow.truncate(7);
    Ok(Cron {
        minute: cron_field(f[0], 0, 59, "minute")?,
        hour: cron_field(f[1], 0, 23, "hour")?,
        dom: cron_field(f[2], 1, 31, "day-of-month")?,
        month: cron_field(f[3], 1, 12, "month")?,
        dow,
        dom_star: f[2].starts_with('*'),
        dow_star: f[4].starts_with('*'),
    })
}

impl Cron {
    fn day_matches(&self, day: i64) -> bool {
        let (_, m, d) = civil_from_days(day);
        let wd = weekday(day) % 7; // Sunday = 0
        if !self.month[m as usize] {
            return false;
        }
        let by_dom = self.dom[d as usize];
        let by_dow = self.dow[wd as usize];
        // Vixie rule: when both day fields are restricted, either may match.
        if !self.dom_star && !self.dow_star { by_dom || by_dow } else { by_dom && by_dow }
    }
}

// ---- timing --------------------------------------------------------------------------------------

/// What the model (or the user) wrote: `{"kind":"daily","time":"09:30"}` and the like.
pub fn parse_timing(value: &Value, now: i64) -> Result<Timing, String> {
    let kind = value["kind"].as_str().ok_or("timing needs a \"kind\": after, at, every, daily, weekly or cron")?;
    let secs = |key: &str| value[key].as_u64().filter(|s| *s > 0).ok_or(format!("{kind} needs a positive \"{key}\""));
    match kind {
        "after" => {
            let s = secs("after_seconds")?;
            if s > MAX_SPAN {
                return Err("after_seconds is longer than a year".to_owned());
            }
            Ok(Timing::After { secs: s })
        }
        "at" => {
            let at = value["at"].as_str().ok_or("at needs \"at\" as a time with an offset, like 2026-11-12T09:30:00+08:00")?;
            let at = parse_instant(at)?;
            if at <= now {
                return Err("that time has passed; at needs a time in the future".to_owned());
            }
            Ok(Timing::At { at })
        }
        "every" => {
            let s = secs("every_seconds")?;
            if s < MIN_GAP_SECS {
                return Err(format!("every_seconds must be at least {MIN_GAP_SECS}"));
            }
            if s > MAX_SPAN {
                return Err("every_seconds is longer than a year".to_owned());
            }
            Ok(Timing::Every { secs: s })
        }
        "daily" => Ok(Timing::Daily { minute: parse_clock(value["time"].as_str().ok_or("daily needs \"time\" like 09:30")?)? }),
        "weekly" => {
            let minute = parse_clock(value["time"].as_str().ok_or("weekly needs \"time\" like 09:30")?)?;
            let mut days: Vec<u8> = value["weekdays"]
                .as_array()
                .ok_or("weekly needs \"weekdays\": numbers 1 (Monday) to 7 (Sunday)")?
                .iter()
                .filter_map(|d| d.as_u64().filter(|d| (1..=7).contains(d)).map(|d| d as u8))
                .collect();
            days.sort_unstable();
            days.dedup();
            if days.is_empty() {
                return Err("weekly needs at least one weekday from 1 (Monday) to 7 (Sunday)".to_owned());
            }
            Ok(Timing::Weekly { minute, days })
        }
        "cron" => {
            let expr = value["expression"].as_str().ok_or("cron needs \"expression\" with five fields")?;
            parse_cron(expr)?;
            Ok(Timing::Cron { expr: expr.split_whitespace().collect::<Vec<_>>().join(" ") })
        }
        other => Err(format!("unknown timing kind \"{other}\"; use after, at, every, daily, weekly or cron")),
    }
}

/// The first occurrence strictly after `after`, for a timing that is wall-clock based or repeating.
fn next_after(timing: &Timing, after: i64, offset_min: i32, anchor: i64) -> Option<i64> {
    match timing {
        Timing::After { .. } | Timing::At { .. } => None,
        Timing::Every { secs } => {
            let s = *secs as i64;
            Some(anchor + ((after - anchor).div_euclid(s) + 1) * s)
        }
        Timing::Daily { minute } => {
            let (day, now_min) = local(after, offset_min);
            let day = if now_min < *minute { day } else { day + 1 };
            Some(unix_of(day, *minute, offset_min))
        }
        Timing::Weekly { minute, days } => {
            let (day, now_min) = local(after, offset_min);
            (0..8).map(|i| day + i).find_map(|d| {
                let ok = days.contains(&weekday(d)) && (d > day || now_min < *minute);
                ok.then(|| unix_of(d, *minute, offset_min))
            })
        }
        Timing::Cron { expr } => {
            let cron = parse_cron(expr).ok()?;
            let (day, now_min) = local(after, offset_min);
            for d in day..day + 366 * 5 {
                if !cron.day_matches(d) {
                    continue;
                }
                let from = if d == day { now_min + 1 } else { 0 };
                for h in (from / 60)..24 {
                    if !cron.hour[h as usize] {
                        continue;
                    }
                    let start = if d == day && h == from / 60 { from % 60 } else { 0 };
                    if let Some(m) = (start..60).find(|m| cron.minute[*m as usize]) {
                        return Some(unix_of(d, h * 60 + m, offset_min));
                    }
                }
            }
            None
        }
    }
}

/// When a task first fires, counted from `now` (its creation, or the moment it is resumed or changed).
pub fn first_occurrence(timing: &Timing, now: i64, offset_min: i32) -> Result<i64, String> {
    match timing {
        Timing::After { secs } => Ok(now + *secs as i64),
        Timing::At { at } if *at > now => Ok(*at),
        Timing::At { .. } => Err("that time has passed".to_owned()),
        Timing::Every { secs } => Ok(now + *secs as i64),
        other => next_after(other, now, offset_min, now).ok_or("that rule never fires".to_owned()),
    }
}

impl Task {
    pub fn new(id: String, title: String, prompt: String, timing: Timing, target: &str, offset_min: i32, now: i64) -> Result<Self, String> {
        let next = first_occurrence(&timing, now, offset_min)?;
        Ok(Self {
            id,
            title,
            prompt,
            timing,
            offset_min,
            target: if target == "session" { "session".into() } else { "new".into() },
            conversation: None,
            active: true,
            ended: false,
            next: Some(next),
            anchor: now,
            created: now,
            last: None,
            deliveries: 0,
        })
    }

    pub fn due(&self, now: i64) -> bool {
        self.active && !self.ended && self.next.is_some_and(|n| n <= now)
    }

    /// Called when a delivery happened: coalesces everything missed, then picks the next future time
    /// (a one-shot ends).
    pub fn delivered(&mut self, now: i64) {
        self.last = Some(now);
        self.deliveries += 1;
        match next_after(&self.timing, now, self.offset_min, self.anchor) {
            Some(n) => self.next = Some(n),
            None => {
                self.next = None;
                self.ended = true;
            }
        }
    }

    /// Resuming (or changing the timing of) a task schedules a future time again; an ended one-shot
    /// needs new timing first.
    pub fn arm(&mut self, now: i64) -> Result<(), String> {
        self.anchor = now;
        self.next = Some(first_occurrence(&self.timing, now, self.offset_min)?);
        self.ended = false;
        Ok(())
    }

    pub fn timing_text(&self) -> String {
        match &self.timing {
            Timing::After { secs } => format!("once, {} after it was made", span(*secs)),
            Timing::At { at } => format!("once, at {}", stamp(*at, self.offset_min)),
            Timing::Every { secs } => format!("every {}", span(*secs)),
            Timing::Daily { minute } => format!("every day at {}", clock_text(*minute)),
            Timing::Weekly { minute, days } => {
                const NAMES: [&str; 7] = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
                let list: Vec<&str> = days.iter().map(|d| NAMES[(*d - 1) as usize]).collect();
                format!("{} at {}", list.join(", "), clock_text(*minute))
            }
            Timing::Cron { expr } => format!("cron {expr}"),
        }
    }

    pub fn status_text(&self, now: i64) -> String {
        if self.ended {
            "ended".to_owned()
        } else if !self.active {
            "paused".to_owned()
        } else {
            match self.next {
                Some(n) if n <= now => "due".to_owned(),
                Some(n) => format!("next {}", stamp(n, self.offset_min)),
                None => "active".to_owned(),
            }
        }
    }
}

/// `2026-11-12 09:30` in the task's local time.
pub fn stamp(unix: i64, offset_min: i32) -> String {
    let (day, minute) = local(unix, offset_min);
    let (y, m, d) = civil_from_days(day);
    format!("{y:04}-{m:02}-{d:02} {}", clock_text(minute))
}

/// `Thursday 2026-11-12 15:04 UTC+08:00`: what the model is told the time is (see `clock_note` in the app).
pub fn now_text(unix: i64, offset_min: i32) -> String {
    const DAYS: [&str; 7] = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
    let (day, _) = local(unix, offset_min);
    let sign = if offset_min < 0 { '-' } else { '+' };
    let o = offset_min.abs();
    format!("{} {} UTC{sign}{:02}:{:02}", DAYS[(weekday(day) - 1) as usize], stamp(unix, offset_min), o / 60, o % 60)
}

fn span(secs: u64) -> String {
    match secs {
        s if s % 86_400 == 0 => format!("{} day(s)", s / 86_400),
        s if s % 3600 == 0 => format!("{} hour(s)", s / 3600),
        s if s % 60 == 0 => format!("{} minute(s)", s / 60),
        s => format!("{s} seconds"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    // 2026-11-12 (a Thursday) 00:00:00 UTC.
    const DAY: i64 = 1_794_441_600;

    #[test]
    fn civil_dates_round_trip_and_weekdays_are_iso() {
        assert_eq!(civil_from_days(DAY / 86_400), (2026, 11, 12));
        assert_eq!(days_from_civil(1970, 1, 1), 0);
        assert_eq!(weekday(DAY / 86_400), 4, "2026-11-12 is a Thursday");
        assert_eq!(weekday(0), 4, "1970-01-01 was a Thursday");
    }

    #[test]
    fn an_instant_needs_an_offset_and_a_real_date() {
        assert_eq!(parse_instant("2026-11-12T08:00:00+08:00").unwrap(), DAY);
        assert_eq!(parse_instant("2026-11-12T00:00:00Z").unwrap(), DAY);
        assert_eq!(parse_instant("2026-11-11T19:00:00-05:00").unwrap(), DAY);
        assert!(parse_instant("2026-11-12T08:00:00").unwrap_err().contains("offset"));
        assert!(parse_instant("2026-02-31T08:00:00Z").is_err(), "no 31 February");
        assert!(parse_instant("tomorrow").is_err());
    }

    #[test]
    fn timing_input_is_checked() {
        let now = DAY;
        assert!(matches!(parse_timing(&json!({"kind":"after","after_seconds":30}), now), Ok(Timing::After { secs: 30 })));
        assert!(parse_timing(&json!({"kind":"every","every_seconds":30}), now).unwrap_err().contains("at least 60"));
        assert!(parse_timing(&json!({"kind":"at","at":"2020-01-01T00:00:00Z"}), now).unwrap_err().contains("passed"));
        assert!(parse_timing(&json!({"kind":"daily","time":"25:00"}), now).is_err());
        assert!(parse_timing(&json!({"kind":"weekly","time":"09:00","weekdays":[]}), now).is_err());
        assert!(parse_timing(&json!({"kind":"cron","expression":"* * *"}), now).unwrap_err().contains("five fields"));
        assert!(parse_timing(&json!({"kind":"cron","expression":"5/2 * * * *"}), now).is_err(), "a value with a step is refused");
        assert!(parse_timing(&json!({"kind":"hourly"}), now).unwrap_err().contains("unknown"));
        assert_eq!(
            parse_timing(&json!({"kind":"weekly","time":"09:00","weekdays":[5,1,1]}), now).unwrap(),
            Timing::Weekly { minute: 540, days: vec![1, 5] }
        );
    }

    #[test]
    fn daily_uses_the_devices_local_time() {
        // 09:00 in UTC+8 is 01:00 UTC. At 00:30 UTC (08:30 local) the next one is today.
        let t = Timing::Daily { minute: 540 };
        assert_eq!(next_after(&t, DAY + 1800, 480, 0), Some(DAY + 3600));
        // After it, the next is tomorrow.
        assert_eq!(next_after(&t, DAY + 3600, 480, 0), Some(DAY + 86_400 + 3600));
    }

    #[test]
    fn weekly_picks_the_next_listed_weekday() {
        // Thursday 2026-11-12 10:00 UTC; Mondays and Fridays at 09:00 UTC.
        let t = Timing::Weekly { minute: 540, days: vec![1, 5] };
        let friday = DAY + 86_400 + 9 * 3600;
        assert_eq!(next_after(&t, DAY + 10 * 3600, 0, 0), Some(friday));
        // Friday 09:00 itself is not "after" Friday 09:00: the next is Monday.
        assert_eq!(next_after(&t, friday, 0, 0), Some(DAY + 4 * 86_400 + 9 * 3600));
    }

    #[test]
    fn every_stays_aligned_to_its_anchor_and_coalesces_downtime() {
        let t = Timing::Every { secs: 600 };
        let anchor = DAY;
        // The app was closed for 35 minutes: one delivery, then the next aligned time.
        assert_eq!(next_after(&t, anchor + 2100, 0, anchor), Some(anchor + 2400));
    }

    #[test]
    fn cron_matches_ranges_steps_lists_and_vixie_day_rules() {
        let t = Timing::Cron { expr: "*/15 9-10 * * 1-5".into() };
        // Thursday 09:07 UTC -> 09:15.
        assert_eq!(next_after(&t, DAY + 9 * 3600 + 7 * 60, 0, 0), Some(DAY + 9 * 3600 + 15 * 60));
        // Thursday 10:46 -> Friday 09:00.
        assert_eq!(next_after(&t, DAY + 10 * 3600 + 46 * 60, 0, 0), Some(DAY + 86_400 + 9 * 3600));
        // Friday 10:46 -> Monday 09:00 (the weekend is skipped).
        assert_eq!(next_after(&t, DAY + 86_400 + 10 * 3600 + 46 * 60, 0, 0), Some(DAY + 4 * 86_400 + 9 * 3600));
        // Both day fields restricted: the 13th OR a Monday.
        let either = Timing::Cron { expr: "0 0 13 * 1".into() };
        assert_eq!(next_after(&either, DAY, 0, 0), Some(DAY + 86_400), "the 13th is tomorrow");
        // Sunday is 0 or 7.
        let sun = Timing::Cron { expr: "0 12 * * 7".into() };
        assert_eq!(next_after(&sun, DAY, 0, 0), Some(DAY + 3 * 86_400 + 12 * 3600));
    }

    #[test]
    fn a_one_shot_fires_once_then_ends_and_a_repeating_task_moves_on() {
        let mut once = Task::new("s1".into(), "t".into(), "p".into(), Timing::After { secs: 120 }, "new", 0, DAY).unwrap();
        assert!(!once.due(DAY + 119));
        assert!(once.due(DAY + 120));
        once.delivered(DAY + 130);
        assert!(once.ended && once.next.is_none() && once.deliveries == 1);
        assert!(!once.due(DAY + 99_999));
        assert!(once.arm(DAY + 200).is_ok(), "arming again schedules it afresh");
        assert!(once.due(DAY + 400));

        let mut daily = Task::new("s2".into(), "t".into(), "p".into(), Timing::Daily { minute: 60 }, "session", 0, DAY).unwrap();
        assert_eq!(daily.target, "session");
        let first = daily.next.unwrap();
        daily.delivered(first + 5);
        assert_eq!(daily.next, Some(first + 86_400));
        assert!(!daily.ended);
    }

    #[test]
    fn text_for_the_list_is_readable() {
        let t = Task::new("s1".into(), "Report".into(), "p".into(), Timing::Weekly { minute: 570, days: vec![1, 3] }, "new", 480, DAY).unwrap();
        assert_eq!(t.timing_text(), "Mon, Wed at 09:30");
        assert!(t.status_text(DAY).starts_with("next 2026-11-1"));
        assert_eq!(stamp(DAY, 480), "2026-11-12 08:00");
        assert_eq!(now_text(DAY, 480), "Thursday 2026-11-12 08:00 UTC+08:00");
        assert_eq!(now_text(DAY, -330), "Wednesday 2026-11-11 18:30 UTC-05:30");
    }
}
