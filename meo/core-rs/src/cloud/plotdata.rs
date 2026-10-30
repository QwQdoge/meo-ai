//! Graphs and charts for the clients that draw natively (desktop, Android): an answer's `plot` and `chart` fenced
//! blocks become plain geometry and data here, so a client only has to draw lines, points, bars and slices.
//! (The web client draws them itself from the same text, with the same grammar.)
//!
//! Expressions go through a small recursive-descent parser into an AST that is evaluated directly: nothing is ever
//! executed, unknown names are errors and size limits keep a runaway answer cheap.

use serde_json::{json, Value};

const MAX_LEN: usize = 200;
const MAX_TOKENS: usize = 160;
const MAX_DEPTH: usize = 40;
const MAX_CURVES: usize = 8;

#[derive(Debug, Clone)]
enum Ast {
    Num(f64),
    Var,
    Neg(Box<Ast>),
    Bin(char, Box<Ast>, Box<Ast>),
    Call(&'static str, Vec<Ast>),
}

#[derive(Debug, Clone, PartialEq)]
enum Tok {
    Num(f64),
    Id(String),
    Op(char),
}

const FUNCTIONS: [&str; 27] = [
    "sin", "cos", "tan", "asin", "acos", "atan", "arcsin", "arccos", "arctan", "sinh", "cosh",
    "tanh", "sqrt", "cbrt", "abs", "ln", "log", "log10", "log2", "exp", "floor", "ceil", "round",
    "sign", "min", "max", "pow",
];

fn apply(name: &str, a: &[f64]) -> f64 {
    let x = a.first().copied().unwrap_or(f64::NAN);
    let y = a.get(1).copied().unwrap_or(f64::NAN);
    match name {
        "sin" => x.sin(),
        "cos" => x.cos(),
        "tan" => x.tan(),
        "asin" | "arcsin" => x.asin(),
        "acos" | "arccos" => x.acos(),
        "atan" | "arctan" => x.atan(),
        "sinh" => x.sinh(),
        "cosh" => x.cosh(),
        "tanh" => x.tanh(),
        "sqrt" => x.sqrt(),
        "cbrt" => x.cbrt(),
        "abs" => x.abs(),
        "ln" => x.ln(),
        "log" | "log10" => x.log10(),
        "log2" => x.log2(),
        "exp" => x.exp(),
        "floor" => x.floor(),
        "ceil" => x.ceil(),
        "round" => x.round(),
        "sign" => {
            if x == 0.0 {
                0.0
            } else {
                x.signum()
            }
        }
        "min" => a.iter().copied().fold(f64::INFINITY, f64::min),
        "max" => a.iter().copied().fold(f64::NEG_INFINITY, f64::max),
        "pow" => x.powf(y),
        _ => f64::NAN,
    }
}

fn tokenize(src: &str) -> Result<Vec<Tok>, String> {
    let text: String = src
        .replace('π', " pi ")
        .replace(['·', '×'], "*")
        .replace(['−', '–'], "-")
        .replace('÷', "/")
        .replace('²', "^2")
        .replace('³', "^3")
        .replace('√', " sqrt ");
    let chars: Vec<char> = text.chars().collect();
    let mut tokens = Vec::new();
    let mut i = 0;
    while i < chars.len() {
        let c = chars[i];
        if c.is_whitespace() {
            i += 1;
        } else if c.is_ascii_digit()
            || (c == '.' && chars.get(i + 1).is_some_and(|d| d.is_ascii_digit()))
        {
            let start = i;
            while i < chars.len() && (chars[i].is_ascii_digit() || chars[i] == '.') {
                i += 1;
            }
            // an exponent only when digits follow ("2e3"); otherwise "2e" is 2 times e
            if i < chars.len() && (chars[i] == 'e' || chars[i] == 'E') {
                let mut j = i + 1;
                if j < chars.len() && (chars[j] == '+' || chars[j] == '-') {
                    j += 1;
                }
                if j < chars.len() && chars[j].is_ascii_digit() {
                    while j < chars.len() && chars[j].is_ascii_digit() {
                        j += 1;
                    }
                    i = j;
                }
            }
            let literal: String = chars[start..i].iter().collect();
            tokens.push(Tok::Num(
                literal
                    .parse::<f64>()
                    .map_err(|_| format!("bad number \"{literal}\""))?,
            ));
        } else if c.is_ascii_alphabetic() || c == '_' {
            let start = i;
            while i < chars.len() && (chars[i].is_ascii_alphanumeric() || chars[i] == '_') {
                i += 1;
            }
            tokens.push(Tok::Id(
                chars[start..i].iter().collect::<String>().to_lowercase(),
            ));
        } else if "+-*/^(),".contains(c) {
            tokens.push(Tok::Op(c));
            i += 1;
        } else {
            return Err(format!("unexpected \"{c}\""));
        }
        if tokens.len() > MAX_TOKENS {
            return Err("expression too long".into());
        }
    }
    Ok(tokens)
}

struct Parser<'a> {
    tokens: Vec<Tok>,
    pos: usize,
    vars: &'a [&'a str],
}

impl Parser<'_> {
    fn is_op(&self, c: char) -> bool {
        self.tokens.get(self.pos) == Some(&Tok::Op(c))
    }
    fn starts_primary(&self) -> bool {
        matches!(
            self.tokens.get(self.pos),
            Some(Tok::Num(_) | Tok::Id(_)) | Some(Tok::Op('('))
        )
    }
    fn expression(&mut self, depth: usize) -> Result<Ast, String> {
        if depth > MAX_DEPTH {
            return Err("expression too deep".into());
        }
        let mut left = self.term(depth)?;
        while self.is_op('+') || self.is_op('-') {
            let op = if self.is_op('+') { '+' } else { '-' };
            self.pos += 1;
            let right = self.term(depth)?;
            left = Ast::Bin(op, Box::new(left), Box::new(right));
        }
        Ok(left)
    }
    fn term(&mut self, depth: usize) -> Result<Ast, String> {
        let mut left = self.unary(depth)?;
        loop {
            if self.is_op('*') || self.is_op('/') {
                let op = if self.is_op('*') { '*' } else { '/' };
                self.pos += 1;
                let right = self.unary(depth)?;
                left = Ast::Bin(op, Box::new(left), Box::new(right));
            } else if self.starts_primary() {
                // implicit multiplication: 2x, 2(x+1), (x+1)(x-1)
                let right = self.unary(depth)?;
                left = Ast::Bin('*', Box::new(left), Box::new(right));
            } else {
                return Ok(left);
            }
        }
    }
    fn unary(&mut self, depth: usize) -> Result<Ast, String> {
        if depth > MAX_DEPTH {
            return Err("expression too deep".into());
        }
        if self.is_op('-') {
            self.pos += 1;
            return Ok(Ast::Neg(Box::new(self.unary(depth + 1)?)));
        }
        if self.is_op('+') {
            self.pos += 1;
            return self.unary(depth + 1);
        }
        self.power(depth)
    }
    fn power(&mut self, depth: usize) -> Result<Ast, String> {
        let base = self.primary(depth)?;
        if self.is_op('^') {
            self.pos += 1;
            let exponent = self.unary(depth + 1)?; // right-associative; 2^-3 works
            return Ok(Ast::Bin('^', Box::new(base), Box::new(exponent)));
        }
        Ok(base)
    }
    fn primary(&mut self, depth: usize) -> Result<Ast, String> {
        let token = self.tokens.get(self.pos).cloned().ok_or("unexpected end")?;
        self.pos += 1;
        match token {
            Tok::Num(v) => Ok(Ast::Num(v)),
            Tok::Op('(') => {
                let inner = self.expression(depth + 1)?;
                if !self.is_op(')') {
                    return Err("missing \")\"".into());
                }
                self.pos += 1;
                Ok(inner)
            }
            Tok::Id(name) => {
                if let Some(function) = FUNCTIONS.iter().find(|f| **f == name) {
                    let args = if self.is_op('(') {
                        self.pos += 1;
                        let mut args = vec![self.expression(depth + 1)?];
                        while self.is_op(',') {
                            self.pos += 1;
                            args.push(self.expression(depth + 1)?);
                        }
                        if !self.is_op(')') {
                            return Err("missing \")\"".into());
                        }
                        self.pos += 1;
                        args
                    } else if self.starts_primary() {
                        vec![self.power(depth + 1)?] // "sin x", "sqrt 2x" apply to the next factor
                    } else {
                        return Err(format!("{name} needs an argument"));
                    };
                    return Ok(Ast::Call(function, args));
                }
                if self.vars.contains(&name.as_str()) {
                    return Ok(Ast::Var);
                }
                match name.as_str() {
                    "pi" => Ok(Ast::Num(std::f64::consts::PI)),
                    "e" => Ok(Ast::Num(std::f64::consts::E)),
                    "tau" => Ok(Ast::Num(std::f64::consts::TAU)),
                    _ => Err(format!("unknown name \"{name}\"")),
                }
            }
            Tok::Op(c) => Err(format!("unexpected \"{c}\"")),
        }
    }
}

/// A compiled expression in one variable.
#[derive(Debug, Clone)]
pub struct Expr(Ast);

impl Expr {
    pub fn eval(&self, x: f64) -> f64 {
        fn go(ast: &Ast, x: f64) -> f64 {
            match ast {
                Ast::Num(v) => *v,
                Ast::Var => x,
                Ast::Neg(a) => -go(a, x),
                Ast::Bin(op, a, b) => {
                    let (l, r) = (go(a, x), go(b, x));
                    match op {
                        '+' => l + r,
                        '-' => l - r,
                        '*' => l * r,
                        '/' => l / r,
                        _ => l.powf(r),
                    }
                }
                Ast::Call(name, args) => {
                    let values: Vec<f64> = args.iter().map(|a| go(a, x)).collect();
                    apply(name, &values)
                }
            }
        }
        go(&self.0, x)
    }
}

/// Compile `src`; every name in `vars` stands for the same input number.
pub fn compile(src: &str, vars: &[&str]) -> Result<Expr, String> {
    if src.trim().is_empty() {
        return Err("empty expression".into());
    }
    if src.chars().count() > MAX_LEN {
        return Err("expression too long".into());
    }
    let mut parser = Parser {
        tokens: tokenize(src)?,
        pos: 0,
        vars,
    };
    let ast = parser.expression(0)?;
    if let Some(token) = parser.tokens.get(parser.pos) {
        return Err(match token {
            Tok::Op(c) => format!("unexpected \"{c}\""),
            Tok::Num(v) => format!("unexpected \"{v}\""),
            Tok::Id(s) => format!("unexpected \"{s}\""),
        });
    }
    Ok(Expr(ast))
}

fn constant(src: &str) -> Result<f64, String> {
    let v = compile(src, &[])?.eval(0.0);
    if v.is_finite() {
        Ok(v)
    } else {
        Err(format!("\"{}\" is not a number", src.trim()))
    }
}

fn parse_range(text: &str) -> Result<(f64, f64), String> {
    let parts: Vec<&str> = text.split("..").collect();
    if parts.len() != 2 {
        return Err("a range looks like -5..5".into());
    }
    let (a, b) = (constant(parts[0])?, constant(parts[1])?);
    if a < b {
        Ok((a, b))
    } else {
        Err("the range must increase".into())
    }
}

/// Split at a separator that is not inside parentheses.
fn split_top(text: &str, separator: char) -> Vec<&str> {
    let mut parts = Vec::new();
    let (mut depth, mut start) = (0i32, 0usize);
    for (i, c) in text.char_indices() {
        match c {
            '(' => depth += 1,
            ')' => depth -= 1,
            c if c == separator && depth == 0 => {
                parts.push(&text[start..i]);
                start = i + c.len_utf8();
            }
            _ => {}
        }
    }
    parts.push(&text[start..]);
    parts
}

enum Curve {
    Fn {
        label: String,
        f: Expr,
    },
    Polar {
        label: String,
        r: Expr,
    },
    Param {
        label: String,
        fx: Expr,
        fy: Expr,
        t: (f64, f64),
    },
    VLine {
        label: String,
        x: f64,
    },
    Points {
        label: String,
        points: Vec<(f64, f64)>,
    },
}

struct Plot {
    title: String,
    x: Option<(f64, f64)>,
    y: Option<(f64, f64)>,
    curves: Vec<Curve>,
    errors: Vec<String>,
}

fn key_value<'a>(line: &'a str, keys: &[&str]) -> Option<&'a str> {
    let (key, value) = line.split_once(':')?;
    let key = key.trim().to_lowercase();
    keys.iter().any(|k| *k == key).then(|| value.trim())
}

fn parse_points(text: &str) -> Result<Vec<(f64, f64)>, String> {
    let mut points = Vec::new();
    let mut rest = text;
    while let Some(open) = rest.find('(') {
        let mut depth = 0i32;
        let mut close = None;
        for (i, c) in rest[open..].char_indices() {
            match c {
                '(' => depth += 1,
                ')' => {
                    depth -= 1;
                    if depth == 0 {
                        close = Some(open + i);
                        break;
                    }
                }
                _ => {}
            }
        }
        let close = close.ok_or("points look like (1,2) (3,5)")?;
        let pair = split_top(&rest[open + 1..close], ',');
        if pair.len() != 2 {
            return Err("points look like (1,2) (3,5)".into());
        }
        points.push((constant(pair[0])?, constant(pair[1])?));
        if points.len() >= 100 {
            break;
        }
        rest = &rest[close + 1..];
    }
    if points.is_empty() {
        Err("points look like (1,2) (3,5)".into())
    } else {
        Ok(points)
    }
}

fn parse_curve(line: &str) -> Result<Curve, String> {
    let label = line.to_owned();
    if let Some(value) = key_value(line, &["point", "points"]) {
        return Ok(Curve::Points {
            label,
            points: parse_points(value)?,
        });
    }
    if line.starts_with('(') {
        // (cos(t), sin(t)) for t in 0..2pi
        let mut depth = 0i32;
        let mut close = None;
        for (i, c) in line.char_indices() {
            match c {
                '(' => depth += 1,
                ')' => {
                    depth -= 1;
                    if depth == 0 {
                        close = Some(i);
                        break;
                    }
                }
                _ => {}
            }
        }
        if let Some(close) = close {
            let pair = split_top(&line[1..close], ',');
            let rest = line[close + 1..]
                .trim()
                .trim_start_matches([',', ';'])
                .trim();
            let rest = rest.strip_prefix("for ").unwrap_or(rest).trim();
            if pair.len() == 2 {
                if let Some(after_t) = rest.strip_prefix('t') {
                    let range = after_t.trim_start();
                    let range = range
                        .strip_prefix("in ")
                        .or_else(|| range.strip_prefix(':'))
                        .or_else(|| range.strip_prefix('='))
                        .ok_or("write the range as: t in 0..2pi")?;
                    return Ok(Curve::Param {
                        label,
                        fx: compile(pair[0], &["t"])?,
                        fy: compile(pair[1], &["t"])?,
                        t: parse_range(range)?,
                    });
                }
            }
        }
    }
    match line.split_once('=') {
        Some((lhs, rhs)) => {
            let lhs = lhs.trim().to_lowercase();
            let lhs = lhs.replace(' ', "");
            match lhs.as_str() {
                "y" | "f" | "g" | "h" | "f(x)" | "g(x)" | "h(x)" | "y(x)" => Ok(Curve::Fn {
                    label,
                    f: compile(rhs, &["x"])?,
                }),
                "r" | "r(theta)" | "r(t)" | "r(θ)" => Ok(Curve::Polar {
                    label,
                    r: compile(rhs, &["theta", "t"])?,
                }),
                "x" => Ok(Curve::VLine {
                    label,
                    x: constant(rhs)?,
                }),
                _ => Err("could not read this line".into()),
            }
        }
        None => Ok(Curve::Fn {
            label: format!("y = {line}"),
            f: compile(line, &["x"])?,
        }),
    }
}

fn parse_plot(text: &str) -> Plot {
    let mut plot = Plot {
        title: String::new(),
        x: None,
        y: None,
        curves: Vec::new(),
        errors: Vec::new(),
    };
    for (index, raw) in text.lines().enumerate() {
        let line = raw.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        let result: Result<(), String> = (|| {
            if let Some(v) = key_value(line, &["title"]) {
                plot.title = v.chars().take(120).collect();
            } else if let Some(v) = key_value(line, &["x", "xrange"]) {
                plot.x = Some(parse_range(v)?);
            } else if let Some(v) = key_value(line, &["y", "yrange"]) {
                plot.y = Some(parse_range(v)?);
            } else if plot.curves.len() >= MAX_CURVES {
                return Err(format!("at most {MAX_CURVES} curves"));
            } else {
                plot.curves.push(parse_curve(line)?);
            }
            Ok(())
        })();
        if let Err(message) = result {
            plot.errors
                .push(format!("Line {}: {} ({})", index + 1, line, message));
        }
    }
    plot
}

type Line = Vec<[f64; 2]>;

/// Split a sampled curve wherever it is undefined or jumps across the view (tan, 1/x).
fn polylines(points: Vec<[f64; 2]>, jump: f64) -> Vec<Line> {
    let mut out: Vec<Line> = Vec::new();
    let mut current: Line = Vec::new();
    let mut previous: Option<[f64; 2]> = None;
    for p in points {
        if !p[0].is_finite() || !p[1].is_finite() {
            if current.len() > 1 {
                out.push(std::mem::take(&mut current));
            }
            current.clear();
            previous = None;
            continue;
        }
        if let Some(q) = previous {
            if (p[1] - q[1]).abs() > jump {
                if current.len() > 1 {
                    out.push(std::mem::take(&mut current));
                }
                current.clear();
            }
        }
        current.push(p);
        previous = Some(p);
    }
    if current.len() > 1 {
        out.push(current);
    }
    out
}

fn sample_fn(f: &Expr, x0: f64, x1: f64, y0: f64, y1: f64, n: usize) -> Vec<Line> {
    let points = (0..=n)
        .map(|i| {
            let x = x0 + (x1 - x0) * i as f64 / n as f64;
            [x, f.eval(x)]
        })
        .collect();
    polylines(points, (y1 - y0) * 1.5)
}

fn sample_param(fx: &Expr, fy: &Expr, t0: f64, t1: f64, n: usize) -> Vec<Line> {
    let points = (0..=n)
        .map(|i| {
            let t = t0 + (t1 - t0) * i as f64 / n as f64;
            [fx.eval(t), fy.eval(t)]
        })
        .collect();
    polylines(points, f64::INFINITY)
}

fn sample_polar(r: &Expr, n: usize) -> Vec<Line> {
    let points = (0..=n)
        .map(|i| {
            let theta = std::f64::consts::TAU * i as f64 / n as f64;
            let radius = r.eval(theta);
            [radius * theta.cos(), radius * theta.sin()]
        })
        .collect();
    polylines(points, f64::INFINITY)
}

/// "Nice" tick values (1, 2 or 5 times a power of ten) inside [min, max].
pub fn nice_ticks(min: f64, max: f64, target: f64) -> Vec<f64> {
    let span = max - min;
    if span.is_nan() || span <= 0.0 || !span.is_finite() {
        return Vec::new();
    }
    let raw = span / target;
    let magnitude = 10f64.powf(raw.log10().floor());
    let step = [1.0, 2.0, 5.0, 10.0]
        .iter()
        .map(|m| m * magnitude)
        .find(|s| *s >= raw)
        .unwrap_or(10.0 * magnitude);
    let mut ticks = Vec::new();
    let mut v = (min / step).ceil() * step;
    while v <= max + step * 1e-9 && ticks.len() < 60 {
        ticks.push(round(v));
        v += step;
    }
    ticks
}

fn round(v: f64) -> f64 {
    (v * 10_000.0).round() / 10_000.0
}

fn auto_view(plot: &Plot) -> ((f64, f64), (f64, f64)) {
    let x = plot.x.unwrap_or((-10.0, 10.0));
    let (mut xs, mut ys) = (Vec::new(), Vec::new());
    for curve in &plot.curves {
        match curve {
            Curve::Fn { f, .. } => {
                for i in 0..=200 {
                    let y = f.eval(x.0 + (x.1 - x.0) * i as f64 / 200.0);
                    if y.is_finite() && y.abs() < 1e6 {
                        ys.push(y);
                    }
                }
            }
            Curve::Param { fx, fy, t, .. } => {
                for line in sample_param(fx, fy, t.0, t.1, 200) {
                    for p in line {
                        xs.push(p[0]);
                        ys.push(p[1]);
                    }
                }
            }
            Curve::Polar { r, .. } => {
                for line in sample_polar(r, 200) {
                    for p in line {
                        xs.push(p[0]);
                        ys.push(p[1]);
                    }
                }
            }
            Curve::Points { points, .. } => {
                for p in points {
                    xs.push(p.0);
                    ys.push(p.1);
                }
            }
            Curve::VLine { .. } => {}
        }
    }
    let mut x_view = x;
    if plot.x.is_none() && !xs.is_empty() {
        let lo = xs.iter().copied().fold(f64::INFINITY, f64::min);
        let hi = xs.iter().copied().fold(f64::NEG_INFINITY, f64::max);
        if hi > lo {
            let pad = (hi - lo) * 0.1;
            x_view = (lo - pad, hi + pad);
        }
    }
    let y_view = plot.y.unwrap_or_else(|| {
        if ys.is_empty() {
            return (-10.0, 10.0);
        }
        ys.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
        let at = |q: f64| ys[((q * (ys.len() - 1) as f64).floor() as usize).min(ys.len() - 1)];
        let (mut lo, mut hi) = (at(0.02), at(0.98));
        if hi.is_nan() || hi <= lo {
            lo -= 1.0;
            hi += 1.0;
        }
        let pad = (hi - lo) * 0.12;
        (lo - pad, hi + pad)
    });
    (x_view, y_view)
}

fn line_json(lines: Vec<Line>) -> Value {
    json!(lines
        .into_iter()
        .map(|l| l
            .into_iter()
            .map(|p| [round(p[0]), round(p[1])])
            .collect::<Vec<_>>())
        .collect::<Vec<_>>())
}

/// The block a client draws for a ```plot fence, or `None` when no curve could be read (the fence stays code).
pub fn plot_block(body: &str, fallback: &str) -> Option<Value> {
    let plot = parse_plot(body);
    if plot.curves.is_empty() {
        return None;
    }
    let (x, y) = auto_view(&plot);
    let curves: Vec<Value> = plot
        .curves
        .iter()
        .map(|curve| match curve {
            Curve::Fn { label, f } => json!({ "kind": "line", "label": label, "lines": line_json(sample_fn(f, x.0, x.1, y.0, y.1, 500)) }),
            Curve::Polar { label, r } => json!({ "kind": "line", "label": label, "lines": line_json(sample_polar(r, 900)) }),
            Curve::Param { label, fx, fy, t } => json!({ "kind": "line", "label": label, "lines": line_json(sample_param(fx, fy, t.0, t.1, 700)) }),
            Curve::VLine { label, x } => json!({ "kind": "vline", "label": label, "x": round(*x) }),
            Curve::Points { label, points } => json!({ "kind": "points", "label": label, "points": points.iter().map(|p| [round(p.0), round(p.1)]).collect::<Vec<_>>() }),
        })
        .collect();
    Some(json!({
        "type": "plot", "title": plot.title, "x": [round(x.0), round(x.1)], "y": [round(y.0), round(y.1)],
        "xticks": nice_ticks(x.0, x.1, 8.0), "yticks": nice_ticks(y.0, y.1, 6.0),
        "curves": curves, "errors": plot.errors, "text": fallback,
    }))
}

/// The block a client draws for a ```chart fence (JSON: type, labels, series), or `None` when it is not valid.
pub fn chart_block(body: &str, fallback: &str) -> Option<Value> {
    let value: Value = serde_json::from_str(body).ok()?;
    let kind = value["type"]
        .as_str()
        .filter(|k| ["bar", "line", "pie"].contains(k))?;
    let labels: Vec<String> = value["labels"]
        .as_array()?
        .iter()
        .take(50)
        .map(|l| {
            l.as_str()
                .map_or_else(|| l.to_string(), str::to_owned)
                .chars()
                .take(40)
                .collect()
        })
        .collect();
    if labels.is_empty() {
        return None;
    }
    let mut series = Vec::new();
    for (index, s) in value["series"].as_array()?.iter().take(6).enumerate() {
        let data: Vec<f64> = s["data"]
            .as_array()?
            .iter()
            .take(labels.len())
            .map(|n| n.as_f64().filter(|v| v.is_finite() && v.abs() <= 1e12))
            .collect::<Option<_>>()?;
        let name: String = s["name"]
            .as_str()
            .map_or_else(|| format!("Series {}", index + 1), str::to_owned)
            .chars()
            .take(40)
            .collect();
        series.push(json!({ "name": name, "data": data }));
    }
    if series.is_empty() {
        return None;
    }
    let all: Vec<f64> = series
        .iter()
        .flat_map(|s| {
            s["data"]
                .as_array()
                .unwrap()
                .iter()
                .filter_map(Value::as_f64)
        })
        .collect();
    let (min, max) = (
        all.iter().copied().fold(0.0, f64::min),
        all.iter().copied().fold(0.0, f64::max),
    );
    if kind == "pie" {
        let data: Vec<f64> = series[0]["data"]
            .as_array()
            .unwrap()
            .iter()
            .filter_map(Value::as_f64)
            .collect();
        if data.iter().any(|v| *v < 0.0) || data.iter().sum::<f64>() <= 0.0 {
            return None;
        }
        series.truncate(1);
    }
    let max = if max > min { max } else { min + 1.0 };
    Some(json!({
        "type": "chart", "kind": kind, "title": value["title"].as_str().unwrap_or_default().chars().take(120).collect::<String>(),
        "labels": labels, "series": series, "min": min, "max": max, "ticks": nice_ticks(min, max, 6.0), "text": fallback,
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn at(src: &str, x: f64) -> f64 {
        compile(src, &["x"]).unwrap().eval(x)
    }

    #[test]
    fn precedence_and_implicit_multiplication() {
        assert_eq!(at("-x^2", 2.0), -4.0);
        assert_eq!(at("2^3^2", 0.0), 512.0);
        assert_eq!(at("2^-1", 0.0), 0.5);
        assert_eq!(at("10 - 4 - 3", 0.0), 3.0);
        assert_eq!(at("2x + 1", 3.0), 7.0);
        assert_eq!(at("2(x + 1)", 3.0), 8.0);
        assert_eq!(at("(x + 1)(x - 1)", 3.0), 8.0);
        assert!((at("sin(pi/2)", 0.0) - 1.0).abs() < 1e-12);
        assert!((at("sin x", std::f64::consts::FRAC_PI_2) - 1.0).abs() < 1e-12);
        assert_eq!(at("x²", 3.0), 9.0);
        assert_eq!(at("max(x, 3)", 5.0), 5.0);
    }

    #[test]
    fn only_numbers_and_known_names_are_ever_read() {
        for bad in [
            "foo",
            "constructor",
            "process.exit()",
            "x.y",
            "alert(1)",
            "sin(",
            "(1+2",
            "1 +",
            "",
            "1;2",
            "`x`",
        ] {
            assert!(compile(bad, &["x"]).is_err(), "{bad}");
        }
        assert!(compile(&"a".repeat(300), &["x"]).is_err());
        assert!(compile(&format!("{}1{}", "(".repeat(60), ")".repeat(60)), &["x"]).is_err());
    }

    #[test]
    fn a_plot_block_becomes_geometry() {
        let block = plot_block("title: Demo\nx: -6..6\ny = x^2 / 6 - 2\n3sin(x)\nx = 1\nr = 1 + cos(theta)\n(cos(t), sin(t)) for t in 0..2pi\npoints: (1,2) (3, 5)\ny = foo(x)", "```plot\n```").unwrap();
        assert_eq!(block["type"], "plot");
        assert_eq!(block["title"], "Demo");
        assert_eq!(block["x"], json!([-6.0, 6.0]));
        let kinds: Vec<&str> = block["curves"]
            .as_array()
            .unwrap()
            .iter()
            .map(|c| c["kind"].as_str().unwrap())
            .collect();
        assert_eq!(kinds, ["line", "line", "vline", "line", "line", "points"]);
        assert_eq!(block["errors"].as_array().unwrap().len(), 1);
        assert!(block["errors"][0].as_str().unwrap().starts_with("Line 9:"));
        assert!(!block["curves"][0]["lines"][0]
            .as_array()
            .unwrap()
            .is_empty());
        assert_eq!(block["text"], "```plot\n```");
    }

    #[test]
    fn nothing_readable_stays_a_code_block() {
        assert!(plot_block("title: only a title", "").is_none());
        assert!(plot_block("y = foo(x)", "").is_none());
    }

    #[test]
    fn curves_split_where_undefined_and_views_fit() {
        let lines = sample_fn(
            &compile("tan(x)", &["x"]).unwrap(),
            -6.0,
            6.0,
            -5.0,
            5.0,
            700,
        );
        assert!(lines.len() >= 3);
        let root = sample_fn(
            &compile("sqrt(x)", &["x"]).unwrap(),
            -4.0,
            4.0,
            -1.0,
            3.0,
            700,
        );
        assert_eq!(root.len(), 1);
        assert!(root[0][0][0] >= 0.0);
        assert_eq!(
            nice_ticks(0.0, 10.0, 5.0),
            vec![0.0, 2.0, 4.0, 6.0, 8.0, 10.0]
        );
        assert_eq!(nice_ticks(-1.0, 1.0, 4.0), vec![-1.0, -0.5, 0.0, 0.5, 1.0]);
        assert!(nice_ticks(5.0, 5.0, 8.0).is_empty());
        let plot = parse_plot("y = x^2\nx: -5..5");
        let (x, y) = auto_view(&plot);
        assert_eq!(x, (-5.0, 5.0));
        assert!(y.0 <= 0.0 && y.1 >= 24.0);
    }

    #[test]
    fn at_most_eight_curves() {
        let text: String = (0..10).map(|i| format!("y = x + {i}\n")).collect();
        let block = plot_block(&text, "").unwrap();
        assert_eq!(block["curves"].as_array().unwrap().len(), 8);
        assert_eq!(block["errors"].as_array().unwrap().len(), 2);
    }

    #[test]
    fn chart_blocks_are_validated_and_bounded() {
        let ok = chart_block(
            r#"{"type":"bar","title":"T","labels":["a","b"],"series":[{"name":"s","data":[1,2]}]}"#,
            "f",
        )
        .unwrap();
        assert_eq!(ok["kind"], "bar");
        assert_eq!(ok["max"], 2.0);
        assert!(chart_block(
            r#"{"type":"pie","labels":["a","b"],"series":[{"data":[1,3]}]}"#,
            ""
        )
        .is_some());
        for bad in [
            "not json",
            "[]",
            r#"{"type":"radar"}"#,
            r#"{"type":"bar","labels":[],"series":[]}"#,
            r#"{"type":"bar","labels":["a"],"series":[{"data":["x"]}]}"#,
            r#"{"type":"pie","labels":["a"],"series":[{"data":[-1]}]}"#,
            r#"{"type":"line","labels":["a"],"series":[{"data":[1e30]}]}"#,
        ] {
            assert!(chart_block(bad, "").is_none(), "{bad}");
        }
    }
}
