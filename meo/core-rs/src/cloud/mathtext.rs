//! LaTeX maths for the clients that draw natively (desktop, Android): they have no LaTeX engine, so formulas are written
//! out in Unicode (Greek letters, super/subscripts, fractions, roots, sums, integrals). What cannot be written that way
//! (matrices, exotic commands) stays as the original LaTeX, so nothing is lost. The web client typesets the real thing.

use std::borrow::Cow;

fn symbol(name: &str) -> Option<&'static str> {
    Some(match name {
        "alpha" => "α",
        "beta" => "β",
        "gamma" => "γ",
        "delta" => "δ",
        "epsilon" | "varepsilon" => "ε",
        "zeta" => "ζ",
        "eta" => "η",
        "theta" => "θ",
        "vartheta" => "ϑ",
        "iota" => "ι",
        "kappa" => "κ",
        "lambda" => "λ",
        "mu" => "μ",
        "nu" => "ν",
        "xi" => "ξ",
        "pi" => "π",
        "rho" => "ρ",
        "sigma" => "σ",
        "tau" => "τ",
        "upsilon" => "υ",
        "phi" | "varphi" => "φ",
        "chi" => "χ",
        "psi" => "ψ",
        "omega" => "ω",
        "Gamma" => "Γ",
        "Delta" => "Δ",
        "Theta" => "Θ",
        "Lambda" => "Λ",
        "Xi" => "Ξ",
        "Pi" => "Π",
        "Sigma" => "Σ",
        "Phi" => "Φ",
        "Psi" => "Ψ",
        "Omega" => "Ω",
        "times" => "×",
        "cdot" => "·",
        "pm" => "±",
        "mp" => "∓",
        "div" => "÷",
        "leq" | "le" => "≤",
        "geq" | "ge" => "≥",
        "neq" | "ne" => "≠",
        "approx" => "≈",
        "equiv" => "≡",
        "sim" => "∼",
        "propto" => "∝",
        "infty" => "∞",
        "partial" => "∂",
        "nabla" => "∇",
        "sum" => "∑",
        "prod" => "∏",
        "int" => "∫",
        "oint" => "∮",
        "to" | "rightarrow" => "→",
        "leftarrow" => "←",
        "Rightarrow" | "implies" => "⇒",
        "Leftarrow" => "⇐",
        "leftrightarrow" => "↔",
        "Leftrightarrow" | "iff" => "⇔",
        "mapsto" => "↦",
        "in" => "∈",
        "notin" => "∉",
        "subset" => "⊂",
        "subseteq" => "⊆",
        "supset" => "⊃",
        "cup" => "∪",
        "cap" => "∩",
        "emptyset" | "varnothing" => "∅",
        "forall" => "∀",
        "exists" => "∃",
        "neg" | "lnot" => "¬",
        "land" | "wedge" => "∧",
        "lor" | "vee" => "∨",
        "ldots" | "dots" => "…",
        "cdots" => "⋯",
        "angle" => "∠",
        "circ" => "∘",
        "degree" => "°",
        "hbar" => "ħ",
        "ell" => "ℓ",
        "Re" => "ℜ",
        "Im" => "ℑ",
        "langle" => "⟨",
        "rangle" => "⟩",
        "lfloor" => "⌊",
        "rfloor" => "⌋",
        "lceil" => "⌈",
        "rceil" => "⌉",
        "quad" | "qquad" => "  ",
        "prime" => "′",
        "perp" => "⊥",
        "parallel" => "∥",
        "ll" => "≪",
        "gg" => "≫",
        "sin" | "cos" | "tan" | "cot" | "sec" | "csc" | "log" | "ln" | "exp" | "lim" | "max"
        | "min" | "det" | "sup" | "inf" | "arcsin" | "arccos" | "arctan" | "sinh" | "cosh"
        | "tanh" | "gcd" | "deg" | "dim" | "ker" | "arg" => return None,
        _ => return None,
    })
}

fn sup_char(c: char) -> Option<char> {
    Some(match c {
        '0' => '⁰',
        '1' => '¹',
        '2' => '²',
        '3' => '³',
        '4' => '⁴',
        '5' => '⁵',
        '6' => '⁶',
        '7' => '⁷',
        '8' => '⁸',
        '9' => '⁹',
        '+' => '⁺',
        '-' | '−' => '⁻',
        '=' => '⁼',
        '(' => '⁽',
        ')' => '⁾',
        'a' => 'ᵃ',
        'b' => 'ᵇ',
        'c' => 'ᶜ',
        'd' => 'ᵈ',
        'e' => 'ᵉ',
        'f' => 'ᶠ',
        'g' => 'ᵍ',
        'h' => 'ʰ',
        'i' => 'ⁱ',
        'j' => 'ʲ',
        'k' => 'ᵏ',
        'l' => 'ˡ',
        'm' => 'ᵐ',
        'n' => 'ⁿ',
        'o' => 'ᵒ',
        'p' => 'ᵖ',
        'r' => 'ʳ',
        's' => 'ˢ',
        't' => 'ᵗ',
        'u' => 'ᵘ',
        'v' => 'ᵛ',
        'w' => 'ʷ',
        'x' => 'ˣ',
        'y' => 'ʸ',
        'z' => 'ᶻ',
        'T' => 'ᵀ',
        ' ' => ' ',
        _ => return None,
    })
}

fn sub_char(c: char) -> Option<char> {
    Some(match c {
        '0' => '₀',
        '1' => '₁',
        '2' => '₂',
        '3' => '₃',
        '4' => '₄',
        '5' => '₅',
        '6' => '₆',
        '7' => '₇',
        '8' => '₈',
        '9' => '₉',
        '+' => '₊',
        '-' | '−' => '₋',
        '=' => '₌',
        '(' => '₍',
        ')' => '₎',
        'a' => 'ₐ',
        'e' => 'ₑ',
        'h' => 'ₕ',
        'i' => 'ᵢ',
        'j' => 'ⱼ',
        'k' => 'ₖ',
        'l' => 'ₗ',
        'm' => 'ₘ',
        'n' => 'ₙ',
        'o' => 'ₒ',
        'p' => 'ₚ',
        'r' => 'ᵣ',
        's' => 'ₛ',
        't' => 'ₜ',
        'u' => 'ᵤ',
        'v' => 'ᵥ',
        'x' => 'ₓ',
        ' ' => ' ',
        _ => return None,
    })
}

fn script(inner: &str, up: bool) -> String {
    let mapped: Option<String> = inner
        .chars()
        .map(|c| if up { sup_char(c) } else { sub_char(c) })
        .collect();
    match mapped {
        Some(text) => text,
        None if inner.chars().count() <= 1 => format!("{}{inner}", if up { '^' } else { '_' }),
        None => format!("{}({inner})", if up { '^' } else { '_' }),
    }
}

fn fraction(a: &str, b: &str) -> String {
    let vulgar = match (a, b) {
        ("1", "2") => "½",
        ("1", "3") => "⅓",
        ("2", "3") => "⅔",
        ("1", "4") => "¼",
        ("3", "4") => "¾",
        ("1", "5") => "⅕",
        ("2", "5") => "⅖",
        ("3", "5") => "⅗",
        ("4", "5") => "⅘",
        ("1", "6") => "⅙",
        ("5", "6") => "⅚",
        ("1", "8") => "⅛",
        ("3", "8") => "⅜",
        ("5", "8") => "⅝",
        ("7", "8") => "⅞",
        _ => "",
    };
    if !vulgar.is_empty() {
        return vulgar.to_owned();
    }
    let simple = |s: &str| s.chars().count() <= 4 && s.chars().all(|c| c.is_alphanumeric());
    match (simple(a), simple(b)) {
        (true, true) => format!("{a}/{b}"),
        (true, false) => format!("{a}/({b})"),
        (false, true) => format!("({a})/{b}"),
        (false, false) => format!("({a})/({b})"),
    }
}

fn blackboard(inner: &str) -> String {
    inner
        .chars()
        .map(|c| match c {
            'R' => "ℝ".to_owned(),
            'N' => "ℕ".to_owned(),
            'Z' => "ℤ".to_owned(),
            'Q' => "ℚ".to_owned(),
            'C' => "ℂ".to_owned(),
            'P' => "ℙ".to_owned(),
            c => c.to_string(),
        })
        .collect()
}

struct Reader {
    chars: Vec<char>,
    pos: usize,
    depth: usize,
}

impl Reader {
    fn skip_space(&mut self) {
        while self.pos < self.chars.len() && self.chars[self.pos] == ' ' {
            self.pos += 1;
        }
    }
    /// The next argument: a {group}, a \command or a single character, as raw text.
    fn argument(&mut self) -> String {
        self.skip_space();
        let Some(&c) = self.chars.get(self.pos) else {
            return String::new();
        };
        if c == '{' {
            let (mut depth, start) = (0usize, self.pos + 1);
            while self.pos < self.chars.len() {
                match self.chars[self.pos] {
                    '{' => depth += 1,
                    '}' => {
                        depth -= 1;
                        if depth == 0 {
                            let inner: String = self.chars[start..self.pos].iter().collect();
                            self.pos += 1;
                            return inner;
                        }
                    }
                    _ => {}
                }
                self.pos += 1;
            }
            return self.chars[start..].iter().collect();
        }
        if c == '\\' {
            let start = self.pos;
            self.pos += 1;
            while self.pos < self.chars.len() && self.chars[self.pos].is_ascii_alphabetic() {
                self.pos += 1;
            }
            if self.pos == start + 1 && self.pos < self.chars.len() {
                self.pos += 1;
            }
            return self.chars[start..self.pos].iter().collect();
        }
        self.pos += 1;
        c.to_string()
    }
    fn command(&mut self) -> String {
        // after the backslash
        let start = self.pos;
        while self.pos < self.chars.len() && self.chars[self.pos].is_ascii_alphabetic() {
            self.pos += 1;
        }
        if self.pos == start && self.pos < self.chars.len() {
            self.pos += 1; // a symbol command: \, \; \{ ...
        }
        self.chars[start..self.pos].iter().collect()
    }
}

fn convert(src: &str, depth: usize) -> String {
    if depth > 12 {
        return src.to_owned();
    }
    let mut r = Reader {
        chars: src.chars().collect(),
        pos: 0,
        depth,
    };
    let mut out = String::new();
    while r.pos < r.chars.len() {
        let c = r.chars[r.pos];
        r.pos += 1;
        match c {
            '\\' => {
                let name = r.command();
                match name.as_str() {
                    "frac" | "dfrac" | "tfrac" => {
                        let (a, b) = (r.argument(), r.argument());
                        out.push_str(&fraction(&convert(&a, depth + 1), &convert(&b, depth + 1)));
                    }
                    "sqrt" => {
                        let mut index = String::new();
                        r.skip_space();
                        if r.chars.get(r.pos) == Some(&'[') {
                            if let Some(end) = r.chars[r.pos..].iter().position(|c| *c == ']') {
                                index = r.chars[r.pos + 1..r.pos + end].iter().collect();
                                r.pos += end + 1;
                            }
                        }
                        let body = convert(&r.argument(), depth + 1);
                        let simple = body.chars().count() <= 1
                            || body.chars().all(|c| c.is_alphanumeric())
                                && body.chars().count() <= 3;
                        let root = match index.as_str() {
                            "" | "2" => "√".to_owned(),
                            "3" => "∛".to_owned(),
                            "4" => "∜".to_owned(),
                            n => format!("{}√", script(n, true)),
                        };
                        out.push_str(&if simple {
                            format!("{root}{body}")
                        } else {
                            format!("{root}({body})")
                        });
                    }
                    "text" | "textbf" | "textit" | "mbox" | "mathrm" | "mathbf" | "mathit"
                    | "mathcal" | "mathsf" | "operatorname" | "boldsymbol" => {
                        out.push_str(&convert(&r.argument(), depth + 1));
                    }
                    "mathbb" => out.push_str(&blackboard(&r.argument())),
                    "left" | "right" | "big" | "Big" | "bigg" | "Bigg" => {
                        r.skip_space();
                        if r.chars.get(r.pos) == Some(&'.') {
                            r.pos += 1; // an invisible delimiter
                        }
                    }
                    "," | ";" | ":" | "!" | " " => out.push(' '),
                    "{" | "}" | "|" | "%" | "$" | "#" | "&" | "_" => out.push(if name == "|" {
                        '‖'
                    } else {
                        name.chars().next().unwrap()
                    }),
                    "\\" => out.push_str("; "),
                    other => match symbol(other) {
                        Some(s) => out.push_str(s),
                        None => {
                            out.push('\\');
                            out.push_str(other);
                        }
                    },
                }
            }
            '^' | '_' => {
                let inner = convert(&r.argument(), depth + 1);
                out.push_str(&script(&inner, c == '^'));
            }
            '{' | '}' => {}
            '~' => out.push(' '),
            c => out.push(c),
        }
    }
    let _ = r.depth;
    out
}

/// A formula written out in Unicode.
pub fn to_unicode(tex: &str) -> String {
    convert(tex.trim(), 0)
}

fn is_space(c: Option<char>) -> bool {
    c.is_none_or(|c| c.is_whitespace())
}

/// Pairs of `$` that form inline maths (pandoc's rule: an opening `$` is followed by a non-space, a closing one is preceded
/// by a non-space and not followed by a digit; a `$` that cannot close hands the open one back as plain text, so "$5 and
/// $10" is money).
fn dollar_pairs(chars: &[char]) -> Vec<(usize, usize)> {
    let (mut pairs, mut open) = (Vec::new(), None::<usize>);
    let mut i = 0;
    while i < chars.len() {
        match chars[i] {
            '\\' => i += 1,
            '$' if chars.get(i + 1) == Some(&'$') => i += 1,
            '$' => {
                let prev = if i == 0 { None } else { Some(chars[i - 1]) };
                let next = chars.get(i + 1).copied();
                match open {
                    Some(o) if !is_space(prev) && !next.is_some_and(|c| c.is_ascii_digit()) => {
                        pairs.push((o, i));
                        open = None;
                    }
                    _ => open = if is_space(next) { None } else { Some(i) },
                }
            }
            _ => {}
        }
        i += 1;
    }
    pairs
}

fn escape_markdown(text: &str) -> String {
    text.replace('*', "\\*").replace('_', "\\_")
}

fn convert_segment(segment: &str) -> String {
    let chars: Vec<char> = segment.chars().collect();
    let mut spans: Vec<(usize, usize, usize, usize)> = dollar_pairs(&chars)
        .into_iter()
        .map(|(o, c)| (o, c, 1, 1))
        .collect();
    let mut i = 0;
    while i + 1 < chars.len() {
        if chars[i] == '\\' && chars[i + 1] == '(' {
            if let Some(end) = (i + 2..chars.len().saturating_sub(1))
                .find(|&j| chars[j] == '\\' && chars[j + 1] == ')')
            {
                spans.push((i, end, 2, 2));
                i = end + 2;
                continue;
            }
        }
        i += 1;
    }
    if spans.is_empty() {
        return segment.to_owned();
    }
    spans.sort();
    let (mut out, mut at) = (String::new(), 0usize);
    for (open, close, open_len, close_len) in spans {
        if open < at {
            continue;
        }
        out.extend(&chars[at..open]);
        let tex: String = chars[open + open_len..close].iter().collect();
        out.push_str(&escape_markdown(&to_unicode(&tex)));
        at = close + close_len;
    }
    out.extend(&chars[at..]);
    out
}

/// Inline maths in one line of Markdown (not inside code) written out in Unicode; code spans are left alone.
pub fn convert_inline(line: &str) -> Cow<'_, str> {
    if !line.contains('$') && !line.contains("\\(") {
        return Cow::Borrowed(line);
    }
    let converted: String = line
        .split('`')
        .enumerate()
        .map(|(i, part)| {
            if i % 2 == 1 {
                format!("`{part}`")
            } else {
                convert_segment(part)
            }
        })
        .collect::<Vec<_>>()
        .join("");
    // split('`') dropped the backticks of the code spans; they were re-added above, so only the even parts are joined plain
    Cow::Owned(converted)
}

/// A formula standing alone: `$$ … $$` on one line, or a block opened by `$$` / `\[` and closed on a later line.
/// Returns the TeX and the index of the line after it.
pub fn display_math(lines: &[&str], i: usize) -> Option<(String, usize)> {
    let first = lines[i].trim();
    let (open, close) = if first.starts_with("$$") {
        ("$$", "$$")
    } else if first.starts_with("\\[") {
        ("\\[", "\\]")
    } else {
        return None;
    };
    let rest = &first[open.len()..];
    if let Some(inner) = rest.strip_suffix(close).filter(|s| !s.trim().is_empty()) {
        return Some((inner.trim().to_owned(), i + 1));
    }
    if !rest.trim().is_empty() && rest.contains(close) {
        return None; // text after the closing delimiter: leave it as a paragraph
    }
    let mut body = vec![rest.trim().to_owned()];
    for (j, line) in lines.iter().enumerate().skip(i + 1).take(40) {
        let t = line.trim();
        if let Some(before) = t.strip_suffix(close) {
            body.push(before.trim().to_owned());
            let tex = body
                .into_iter()
                .filter(|s| !s.is_empty())
                .collect::<Vec<_>>()
                .join(" ");
            return (!tex.is_empty()).then_some((tex, j + 1));
        }
        body.push(t.to_owned());
    }
    None // unclosed (still streaming): stays Markdown
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn common_formulas_read_naturally() {
        assert_eq!(to_unicode(r"\int_0^1 x^2\,dx = \frac13"), "∫₀¹ x² dx = ⅓");
        assert_eq!(to_unicode(r"\frac{a+b}{2}"), "(a+b)/2");
        assert_eq!(to_unicode(r"\sqrt{x^2+y^2}"), "√(x²+y²)");
        assert_eq!(
            to_unicode(r"\sum_{k=1}^{n} k = \frac{n(n+1)}{2}"),
            "∑ₖ₌₁ⁿ k = (n(n+1))/2"
        );
        assert_eq!(to_unicode(r"\alpha + \beta \leq \pi"), "α + β ≤ π");
        assert_eq!(to_unicode(r"e^{i\pi} + 1 = 0"), "e^(iπ) + 1 = 0");
        assert_eq!(to_unicode(r"a_{ij} \cdot b^{-1}"), "aᵢⱼ · b⁻¹");
        assert_eq!(
            to_unicode(r"\text{if } x > 0, x \in \mathbb{R}"),
            "if  x > 0, x ∈ ℝ"
        );
        assert_eq!(to_unicode(r"\left( \frac{1}{2} \right)"), "( ½ )");
        assert_eq!(to_unicode(r"\sqrt[3]{8}"), "∛8");
    }

    #[test]
    fn what_cannot_be_written_stays_latex() {
        assert!(to_unicode(r"\begin{pmatrix} 1 & 0 \\ 0 & 1 \end{pmatrix}").contains(r"\begin"));
        assert!(to_unicode(r"\weirdcommand{x}").contains(r"\weirdcommand"));
    }

    #[test]
    fn inline_maths_is_converted_and_money_is_not() {
        assert_eq!(
            convert_inline("Let $x^2$ be big and \\(a_1\\) small"),
            "Let x² be big and a₁ small"
        );
        assert_eq!(
            convert_inline("It costs $5 and $10."),
            "It costs $5 and $10."
        );
        assert_eq!(convert_inline("Pay $5 for $x$"), "Pay $5 for x");
        assert_eq!(
            convert_inline("Use `$x$` literally but $y$ is maths"),
            "Use `$x$` literally but y is maths"
        );
        assert_eq!(convert_inline("no maths here"), "no maths here");
        assert_eq!(convert_inline("$f_{max}$ and $a*b$"), "fₘₐₓ and a\\*b");
    }

    #[test]
    fn display_maths_is_found_alone_or_across_lines() {
        let one = ["$$ E = mc^2 $$", "after"];
        assert_eq!(display_math(&one, 0), Some(("E = mc^2".to_owned(), 1)));
        let many = ["$$", "\\int_0^1 x\\,dx", "= \\frac12", "$$", "after"];
        assert_eq!(
            display_math(&many, 0),
            Some(("\\int_0^1 x\\,dx = \\frac12".to_owned(), 4))
        );
        assert_eq!(
            display_math(&["\\[ a+b \\]"], 0),
            Some(("a+b".to_owned(), 1))
        );
        assert_eq!(display_math(&["$$", "x^2"], 0), None); // unclosed while streaming
        assert_eq!(display_math(&["costs $$5"], 0), None);
    }
}
