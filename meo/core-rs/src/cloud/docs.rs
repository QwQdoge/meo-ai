//! Documents for every client: the text of PDF, Word, Excel, PowerPoint and RTF files the user
//! attaches, and the Word / Excel / text files the assistant hands back. Clients only pick or save
//! bytes; reading and writing the formats lives here so the web, desktop, Android and the runner
//! behave the same.

use std::io::{Cursor, Read, Write};

const MAX_TEXT: usize = 400_000;

/// File extensions [`extract_text`] reads (besides plain text and pictures, which have their own path).
pub const DOCUMENT_EXTENSIONS: [&str; 5] = ["pdf", "docx", "xlsx", "pptx", "rtf"];

fn extension(name: &str) -> String {
    name.rsplit_once('.')
        .map(|(_, e)| e.to_lowercase())
        .unwrap_or_default()
}

/// Trailing spaces off every line and no more than one blank line in a row (PDF layout leaves both).
fn tidy(text: &str) -> String {
    let mut out = String::new();
    let mut blank = 0;
    for line in text.lines() {
        let line = line.trim_end();
        if line.is_empty() {
            blank += 1;
            if blank > 1 {
                continue;
            }
        } else {
            blank = 0;
        }
        out.push_str(line);
        out.push('\n');
    }
    out.trim().to_owned()
}

fn clip(mut text: String) -> String {
    if text.chars().count() > MAX_TEXT {
        text = text.chars().take(MAX_TEXT).collect::<String>() + "\n(text cut)";
    }
    text
}

fn decode(s: &str) -> String {
    s.replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", "\"")
        .replace("&apos;", "'")
        .replace("&amp;", "&")
}

fn encode(s: &str) -> String {
    s.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
}

/// Text of an XML part: tags are dropped, paragraph ends and breaks become newlines.
fn xml_text(xml: &str) -> String {
    let mut out = String::new();
    let mut rest = xml;
    while let Some(start) = rest.find('<') {
        out.push_str(&rest[..start]);
        let Some(end) = rest[start..].find('>') else {
            break;
        };
        let tag = &rest[start + 1..start + end];
        if tag == "/w:p" || tag == "/a:p" || tag.starts_with("w:br") {
            out.push('\n');
        } else if tag.starts_with("w:tab") {
            out.push('\t');
        }
        rest = &rest[start + end + 1..];
    }
    out.push_str(rest);
    decode(&out)
}

/// The slices between `<open ...>` / `<open>` and `</open>` (tags that nest in themselves are not supported).
fn elements<'a>(xml: &'a str, open: &str) -> Vec<(&'a str, &'a str)> {
    let close = format!("</{open}>");
    let mut found = Vec::new();
    let mut rest = xml;
    let (a, b) = (format!("<{open} "), format!("<{open}>"));
    loop {
        let start = match (rest.find(&a), rest.find(&b)) {
            (Some(x), Some(y)) => x.min(y),
            (Some(x), None) | (None, Some(x)) => x,
            (None, None) => break,
        };
        let after = &rest[start..];
        let Some(tag_end) = after.find('>') else {
            break;
        };
        let attrs = &after[open.len() + 1..tag_end];
        if let Some(stripped) = attrs.strip_suffix('/') {
            found.push((stripped, ""));
            rest = &after[tag_end + 1..];
            continue;
        }
        let body = &after[tag_end + 1..];
        let Some(stop) = body.find(&close) else { break };
        found.push((attrs, &body[..stop]));
        rest = &body[stop + close.len()..];
    }
    found
}

fn attr<'a>(attrs: &'a str, name: &str) -> Option<&'a str> {
    let key = format!("{name}=\"");
    let at = attrs.find(&key)? + key.len();
    attrs[at..].split('"').next()
}

fn zip_text(archive: &mut zip::ZipArchive<Cursor<&[u8]>>, name: &str) -> Option<String> {
    let mut file = archive.by_name(name).ok()?;
    let mut text = String::new();
    file.read_to_string(&mut text).ok()?;
    Some(text)
}

fn numbered(archive: &zip::ZipArchive<Cursor<&[u8]>>, prefix: &str) -> Vec<String> {
    let mut names: Vec<(u32, String)> = archive
        .file_names()
        .filter(|n| n.starts_with(prefix) && n.ends_with(".xml"))
        .filter_map(|n| {
            let digits: String = n[prefix.len()..]
                .chars()
                .take_while(char::is_ascii_digit)
                .collect();
            digits.parse().ok().map(|i| (i, n.to_owned()))
        })
        .collect();
    names.sort();
    names.into_iter().map(|(_, n)| n).collect()
}

fn csv_cell(v: &str) -> String {
    if v.contains(['"', ',', '\n']) {
        format!("\"{}\"", v.replace('"', "\"\""))
    } else {
        v.to_owned()
    }
}

fn xlsx_text(archive: &mut zip::ZipArchive<Cursor<&[u8]>>) -> String {
    let shared: Vec<String> = zip_text(archive, "xl/sharedStrings.xml")
        .map(|x| {
            elements(&x, "si")
                .into_iter()
                .map(|(_, body)| {
                    decode(
                        &elements(body, "t")
                            .iter()
                            .map(|(_, t)| *t)
                            .collect::<String>(),
                    )
                })
                .collect()
        })
        .unwrap_or_default();
    let names: Vec<String> = zip_text(archive, "xl/workbook.xml")
        .map(|x| {
            elements(&x, "sheet")
                .iter()
                .filter_map(|(a, _)| attr(a, "name").map(decode))
                .collect()
        })
        .unwrap_or_default();
    let mut out = Vec::new();
    for (i, sheet) in numbered(archive, "xl/worksheets/sheet")
        .into_iter()
        .enumerate()
    {
        let Some(xml) = zip_text(archive, &sheet) else {
            continue;
        };
        let rows: Vec<String> = elements(&xml, "row")
            .into_iter()
            .map(|(_, row)| {
                elements(row, "c")
                    .into_iter()
                    .map(|(attrs, body)| {
                        let value = elements(body, "v").first().map(|(_, v)| *v).unwrap_or("");
                        if attr(attrs, "t") == Some("s") {
                            csv_cell(
                                value
                                    .parse::<usize>()
                                    .ok()
                                    .and_then(|n| shared.get(n))
                                    .map_or("", String::as_str),
                            )
                        } else if attr(attrs, "t") == Some("inlineStr") {
                            csv_cell(&decode(
                                &elements(body, "t")
                                    .iter()
                                    .map(|(_, t)| *t)
                                    .collect::<String>(),
                            ))
                        } else {
                            csv_cell(&decode(value))
                        }
                    })
                    .collect::<Vec<_>>()
                    .join(",")
            })
            .collect();
        out.push(format!(
            "--- sheet {} (CSV) ---\n{}",
            names.get(i).cloned().unwrap_or_else(|| (i + 1).to_string()),
            rows.join("\n")
        ));
    }
    out.join("\n\n")
}

fn rtf_text(bytes: &[u8]) -> String {
    let source = String::from_utf8_lossy(bytes);
    let mut out = String::new();
    let mut chars = source.chars().peekable();
    while let Some(c) = chars.next() {
        match c {
            '{' | '}' => {}
            '\\' => {
                let mut word = String::new();
                while let Some(&n) = chars.peek() {
                    if n.is_ascii_alphabetic() {
                        word.push(n);
                        chars.next();
                    } else {
                        break;
                    }
                }
                while let Some(&n) = chars.peek() {
                    if n.is_ascii_digit() || n == '-' {
                        chars.next();
                    } else {
                        break;
                    }
                }
                if chars.peek() == Some(&' ') {
                    chars.next();
                }
                if word == "par" || word == "pard" {
                    out.push('\n');
                }
                if word.is_empty() {
                    chars.next();
                }
            }
            _ => out.push(c),
        }
    }
    out
}

/// The text of a document, or an error the user can read.
pub fn extract_text(name: &str, bytes: &[u8]) -> Result<String, String> {
    let ext = extension(name);
    let text = match ext.as_str() {
        "pdf" => {
            let doc =
                lopdf::Document::load_mem(bytes).map_err(|_| format!("Could not read {name}."))?;
            let mut pages = Vec::new();
            for (n, _) in doc.get_pages() {
                pages.push(format!(
                    "--- page {n} ---\n{}",
                    doc.extract_text(&[n]).unwrap_or_default()
                ));
            }
            pages.join("\n\n")
        }
        "docx" | "xlsx" | "pptx" => {
            let mut archive = zip::ZipArchive::new(Cursor::new(bytes))
                .map_err(|_| format!("Could not read {name}."))?;
            match ext.as_str() {
                "docx" => {
                    xml_text(&zip_text(&mut archive, "word/document.xml").unwrap_or_default())
                }
                "pptx" => numbered(&archive, "ppt/slides/slide")
                    .into_iter()
                    .enumerate()
                    .map(|(i, n)| {
                        format!(
                            "--- slide {} ---\n{}",
                            i + 1,
                            xml_text(&zip_text(&mut archive, &n).unwrap_or_default()).trim()
                        )
                    })
                    .collect::<Vec<_>>()
                    .join("\n\n"),
                _ => xlsx_text(&mut archive),
            }
        }
        "rtf" => rtf_text(bytes),
        _ => return Err(format!("{name}: this file type is not supported yet.")),
    };
    if text.trim().is_empty() {
        return Err(format!("No text found in {name} (scanned pages need OCR)."));
    }
    Ok(clip(tidy(&text)))
}

// ---- writing ---------------------------------------------------------------------------------------

fn paragraphs(markdown: &str) -> String {
    let clean = |t: &str| encode(&t.replace("**", "").replace('`', ""));
    markdown
        .lines()
        .map(|raw| {
            let line = raw.trim_end();
            let level = line.chars().take_while(|c| *c == '#').count();
            if (1..=3).contains(&level) && line[level..].starts_with(' ') {
                let size = [40, 32, 28][level - 1];
                format!("<w:p><w:r><w:rPr><w:b/><w:sz w:val=\"{size}\"/></w:rPr><w:t xml:space=\"preserve\">{}</w:t></w:r></w:p>", clean(line[level..].trim()))
            } else if let Some(item) = line.trim_start().strip_prefix("- ").or_else(|| line.trim_start().strip_prefix("* ")) {
                format!("<w:p><w:pPr><w:ind w:left=\"360\"/></w:pPr><w:r><w:t xml:space=\"preserve\">• {}</w:t></w:r></w:p>", clean(item))
            } else {
                format!("<w:p><w:r><w:t xml:space=\"preserve\">{}</w:t></w:r></w:p>", clean(line))
            }
        })
        .collect()
}

fn csv_rows(text: &str) -> Vec<Vec<String>> {
    let (mut rows, mut row, mut cell, mut quoted) = (Vec::new(), Vec::new(), String::new(), false);
    let mut chars = text.chars().peekable();
    while let Some(c) = chars.next() {
        if quoted {
            if c == '"' && chars.peek() == Some(&'"') {
                cell.push('"');
                chars.next();
            } else if c == '"' {
                quoted = false
            } else {
                cell.push(c)
            }
        } else if c == '"' {
            quoted = true
        } else if c == ',' {
            row.push(std::mem::take(&mut cell))
        } else if c == '\n' || c == '\r' {
            if c == '\r' && chars.peek() == Some(&'\n') {
                chars.next();
            }
            row.push(std::mem::take(&mut cell));
            rows.push(std::mem::take(&mut row));
        } else {
            cell.push(c)
        }
    }
    if !cell.is_empty() || !row.is_empty() {
        row.push(cell);
        rows.push(row);
    }
    rows
}

fn column(n: usize) -> String {
    let (mut s, mut x) = (String::new(), n + 1);
    while x > 0 {
        s.insert(0, (b'A' + ((x - 1) % 26) as u8) as char);
        x = (x - 1) / 26;
    }
    s
}

fn zip_of(parts: &[(&str, String)]) -> Vec<u8> {
    let mut writer = zip::ZipWriter::new(Cursor::new(Vec::new()));
    let options = zip::write::SimpleFileOptions::default();
    for (name, body) in parts {
        if writer.start_file(*name, options).is_ok() {
            let _ = writer.write_all(body.as_bytes());
        }
    }
    writer.finish().map(Cursor::into_inner).unwrap_or_default()
}

const XML: &str = "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>";

fn docx_bytes(markdown: &str) -> Vec<u8> {
    zip_of(&[
        ("[Content_Types].xml", format!("{XML}<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\"><Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/><Default Extension=\"xml\" ContentType=\"application/xml\"/><Override PartName=\"/word/document.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml\"/></Types>")),
        ("_rels/.rels", format!("{XML}<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"><Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" Target=\"word/document.xml\"/></Relationships>")),
        ("word/document.xml", format!("{XML}<w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\"><w:body>{}</w:body></w:document>", paragraphs(markdown))),
    ])
}

fn xlsx_bytes(csv: &str) -> Vec<u8> {
    let rows: String = csv_rows(csv)
        .iter()
        .enumerate()
        .map(|(r, row)| {
            let cells: String = row
                .iter()
                .enumerate()
                .map(|(c, v)| {
                    let at = format!("{}{}", column(c), r + 1);
                    match v.parse::<f64>() {
                        Ok(n) if !v.is_empty() && n.is_finite() && !(v.len() > 1 && v.starts_with('0') && !v.starts_with("0.")) => format!("<c r=\"{at}\"><v>{v}</v></c>"),
                        _ => format!("<c r=\"{at}\" t=\"inlineStr\"><is><t xml:space=\"preserve\">{}</t></is></c>", encode(v)),
                    }
                })
                .collect();
            format!("<row r=\"{}\">{cells}</row>", r + 1)
        })
        .collect();
    zip_of(&[
        ("[Content_Types].xml", format!("{XML}<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\"><Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/><Default Extension=\"xml\" ContentType=\"application/xml\"/><Override PartName=\"/xl/workbook.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml\"/><Override PartName=\"/xl/worksheets/sheet1.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml\"/></Types>")),
        ("_rels/.rels", format!("{XML}<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"><Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" Target=\"xl/workbook.xml\"/></Relationships>")),
        ("xl/workbook.xml", format!("{XML}<workbook xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\"><sheets><sheet name=\"Sheet1\" sheetId=\"1\" r:id=\"rId1\"/></sheets></workbook>")),
        ("xl/_rels/workbook.xml.rels", format!("{XML}<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"><Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet\" Target=\"worksheets/sheet1.xml\"/></Relationships>")),
        ("xl/worksheets/sheet1.xml", format!("{XML}<worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\"><sheetData>{rows}</sheetData></worksheet>")),
    ])
}

/// The bytes of a file the assistant wrote: `.docx` is built from Markdown, `.xlsx` from CSV,
/// anything else is saved as the text it is.
pub fn build_file(name: &str, content: &str) -> Vec<u8> {
    match extension(name).as_str() {
        "docx" => docx_bytes(content),
        "xlsx" => xlsx_bytes(content),
        _ => content.as_bytes().to_vec(),
    }
}

/// A file name that is safe to save: no folders, no control or reserved characters.
pub fn safe_name(name: &str) -> String {
    let cleaned: String = name
        .chars()
        .map(|c| {
            if c.is_control() || "\\/:*?\"<>|".contains(c) {
                '_'
            } else {
                c
            }
        })
        .take(120)
        .collect();
    let cleaned = cleaned.trim().trim_start_matches('.').to_owned();
    if cleaned.is_empty() {
        "file.txt".to_owned()
    } else {
        cleaned
    }
}

/// Human kind and size for the file card.
pub fn describe(name: &str, bytes: usize) -> String {
    match extension(name).as_str() {
        "docx" => "Word document".to_owned(),
        "xlsx" => "Excel workbook".to_owned(),
        _ => format!("{:.1} KB", bytes as f64 / 1024.0),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn word_and_excel_files_round_trip_through_the_reader() {
        let doc = build_file("a.docx", "# 标题\n\n正文 **粗体** & <b>\n- 要点一");
        let text = extract_text("a.docx", &doc).unwrap();
        assert!(
            text.contains("标题") && text.contains("正文 粗体 & <b>") && text.contains("• 要点一"),
            "{text}"
        );
        let sheet = build_file("b.xlsx", "name,score\nAlice,3\n\"Bob, Jr.\",4.5\n");
        assert_eq!(
            extract_text("b.xlsx", &sheet).unwrap(),
            "--- sheet Sheet1 (CSV) ---\nname,score\nAlice,3\n\"Bob, Jr.\",4.5"
        );
    }

    #[test]
    fn unsupported_empty_and_unsafe_names_are_handled() {
        assert!(extract_text("x.exe", b"MZ").is_err());
        assert!(extract_text("x.docx", b"not a zip").is_err());
        assert_eq!(safe_name("../a/b:c.md"), "_a_b_c.md");
        assert_eq!(safe_name(""), "file.txt");
        assert_eq!(build_file("n.md", "hi"), b"hi");
    }

    #[test]
    fn rtf_text_is_recovered() {
        assert_eq!(
            extract_text("a.rtf", b"{\\rtf1\\ansi Hello\\par World}")
                .unwrap()
                .trim(),
            "Hello\nWorld"
        );
    }
}
