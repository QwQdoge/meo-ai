//! Reading what the models of a multi-call answer say. The prompts come from Meo API
//! (`/v1/ai/orchestration`); this only turns replies into data, defensively: a model that ignores
//! the format must never break a chat (a bad router reply means "answer directly").

use serde_json::Value;

/// How many model calls a thinking level may add to one answer, for chat and for work.
pub fn max_steps(level: &str, work: bool) -> usize {
    match (level, work) {
        ("high", false) => 3,
        ("max", false) => 5,
        ("medium", true) => 3,
        ("high", true) => 6,
        ("max", true) => 10,
        ("low", true) => 1,
        _ => 0,
    }
}

/// The first `{ ... }` of a reply that parses as JSON (replies may carry prose or code fences).
pub fn first_json(text: &str) -> Option<Value> {
    let start = text.find('{')?;
    let (mut depth, mut in_string, mut escaped) = (0i32, false, false);
    for (i, c) in text[start..].char_indices() {
        if in_string {
            match (escaped, c) {
                (true, _) => escaped = false,
                (false, '\\') => escaped = true,
                (false, '"') => in_string = false,
                _ => {}
            }
        } else {
            match c {
                '"' => in_string = true,
                '{' => depth += 1,
                '}' => {
                    depth -= 1;
                    if depth == 0 {
                        return serde_json::from_str(&text[start..start + i + 1]).ok();
                    }
                }
                _ => {}
            }
        }
    }
    None
}

#[derive(Debug, Clone, PartialEq, Default)]
pub struct Step {
    pub title: String,
    pub role: String,
    pub search: String,
}

#[derive(Debug, Clone, PartialEq, Default)]
pub struct Decision {
    pub route: String,
    pub reason: String,
    pub steps: Vec<Step>,
}

const ROUTES: [&str; 8] = [
    "default",
    "fast",
    "thinking",
    "vision",
    "image",
    "image_edit",
    "video",
    "agent",
];

fn line(value: &Value, max: usize) -> String {
    value
        .as_str()
        .unwrap_or_default()
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
        .chars()
        .take(max)
        .collect()
}

pub fn parse_route(text: &str, max_steps: usize) -> Decision {
    let object = first_json(text).unwrap_or(Value::Null);
    let allowed = |v: &Value| v.as_str().filter(|r| ROUTES.contains(r)).map(str::to_owned);
    let route = allowed(&object["route"]).unwrap_or_else(|| "default".into());
    let steps = object["steps"]
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(|s| {
            let title = line(&s["title"], 160);
            (!title.is_empty()).then(|| Step {
                title,
                role: allowed(&s["role"]).unwrap_or_else(|| route.clone()),
                search: line(&s["search"], 200),
            })
        })
        .take(max_steps)
        .collect();
    Decision {
        route,
        reason: line(&object["reason"], 200),
        steps,
    }
}

/// `DID: ...` and `RESULT: ...` of a step report; an unformatted reply becomes the result.
pub fn parse_report(text: &str) -> (String, String) {
    let find = |tag: &str| -> Option<usize> { text.find(tag) };
    let (did, result) = (find("DID:"), find("RESULT:"));
    match (did, result) {
        (Some(d), Some(r)) if d < r => (
            text[d + 4..r].trim().to_owned(),
            text[r + 7..].trim().to_owned(),
        ),
        (None, Some(r)) => (String::new(), text[r + 7..].trim().to_owned()),
        (Some(d), None) => (text[d + 4..].trim().to_owned(), String::new()),
        _ => (String::new(), text.trim().to_owned()),
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct Judgement {
    pub score: u32,
    pub verdict: String,
    pub suggestion: String,
}

/// A judge's reply: the JSON asked for, or a bare number / "score: 87" from a model (a `jev` model, say)
/// that does not follow the format.
pub fn parse_judgement(text: &str) -> Option<Judgement> {
    let object = first_json(text).unwrap_or(Value::Null);
    let mut score = object["score"].as_f64();
    if score.is_none() {
        let lower = text.to_lowercase();
        for tag in ["score", "rating", "得分", "分数"] {
            if let Some(i) = lower.find(tag) {
                let digits: String = lower[i + tag.len()..]
                    .chars()
                    .skip_while(|c| !c.is_ascii_digit())
                    .take_while(|c| c.is_ascii_digit() || *c == '.')
                    .collect();
                if let Ok(v) = digits.parse::<f64>() {
                    score = Some(v);
                    break;
                }
            }
        }
    }
    if score.is_none() {
        let t = text.trim().trim_end_matches("/100").trim();
        score = t.parse::<f64>().ok();
    }
    let mut score = score?;
    if score <= 1.0 && score.fract() != 0.0 {
        score *= 100.0;
    }
    let score = score.round().clamp(0.0, 100.0) as u32;
    let verdict = match object["verdict"].as_str() {
        Some(v @ ("pass" | "revise" | "fail")) => v.to_owned(),
        _ if score >= 80 => "pass".into(),
        _ if score >= 50 => "revise".into(),
        _ => "fail".into(),
    };
    Some(Judgement {
        score,
        verdict,
        suggestion: line(&object["suggestion"], 300),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn steps_per_level_grow_and_work_gets_more_than_chat() {
        assert_eq!(max_steps("low", false), 0);
        assert_eq!(max_steps("medium", false), 0);
        assert_eq!(max_steps("high", false), 3);
        assert_eq!(max_steps("max", false), 5);
        assert!(max_steps("high", true) > max_steps("high", false));
        assert!(max_steps("max", true) > max_steps("max", false));
    }

    #[test]
    fn route_replies_survive_prose_fences_and_nonsense() {
        let d = parse_route("```json\n{\"route\":\"thinking\",\"reason\":\"hard\",\"steps\":[{\"title\":\"A\"},{\"title\":\"B\",\"role\":\"fast\",\"search\":\"q\"},{\"title\":\"C\"}]}\n```", 2);
        assert_eq!(d.route, "thinking");
        assert_eq!(d.steps.len(), 2);
        assert_eq!(
            d.steps[0].role, "thinking",
            "a step without a role uses the route"
        );
        assert_eq!(d.steps[1].search, "q");
        assert_eq!(parse_route("I think fast", 3).route, "default");
        assert_eq!(parse_route("{\"route\":\"rm -rf\"}", 3).route, "default");
        assert!(
            parse_route("{\"route\":\"fast\",\"steps\":[{\"title\":\"x\"}]}", 0)
                .steps
                .is_empty()
        );
    }

    #[test]
    fn step_reports_split_into_what_was_done_and_the_result() {
        let (did, result) = parse_report("DID: searched twice\nRESULT: Citus fits best");
        assert_eq!(
            (did.as_str(), result.as_str()),
            ("searched twice", "Citus fits best")
        );
        assert_eq!(parse_report("just text").1, "just text");
        assert_eq!(parse_report("RESULT: only").1, "only");
    }

    #[test]
    fn judgements_accept_json_bare_numbers_and_loose_scores() {
        assert_eq!(
            parse_judgement("{\"score\": 91, \"verdict\": \"pass\", \"suggestion\": \"\"}")
                .unwrap()
                .score,
            91
        );
        assert_eq!(parse_judgement("87").unwrap().score, 87);
        assert_eq!(
            parse_judgement("Score: 42/100 because").unwrap().verdict,
            "fail"
        );
        assert_eq!(parse_judgement("0.73").unwrap().score, 73);
        assert_eq!(parse_judgement("{\"score\": 140}").unwrap().score, 100);
        assert!(parse_judgement("no number").is_none());
    }
}
