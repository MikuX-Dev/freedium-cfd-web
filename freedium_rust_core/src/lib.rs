use pyo3::prelude::*;
use pyo3::types::PyDict;

/// Minimal escaping for code blocks - only escape backticks.
#[pyfunction]
fn escape_markdown_minimal(text: &str) -> String {
    text.replace("`", "\\`")
}

/// Normalize smart quotes to standard ASCII quotes.
#[pyfunction]
fn normalize_quotes(text: &str) -> String {
    if text.is_empty() {
        return text.to_string();
    }
    text.replace('\u{201c}', "\"")
        .replace('\u{201d}', "\"")
        .replace('\u{2018}', "'")
        .replace('\u{2019}', "'")
}

/// Unescape markdown special characters in URLs.
#[pyfunction]
fn unescape_markdown_url(url: &str) -> String {
    if url.is_empty() {
        return url.to_string();
    }
    let mut res = url
        .replace("\\)", ")")
        .replace("\\(", "(")
        .replace("\\[", "[")
        .replace("\\]", "]");
    if res.ends_with('\\') {
        res.pop();
    }
    res
}

#[derive(Debug, Clone)]
struct MarkupSpan {
    start: usize,
    end: usize,
    prefix: String,
    suffix: String,
}

fn utf16_to_python_pos(text: &str, utf16_pos: usize) -> usize {
    if utf16_pos == 0 {
        return 0;
    }
    let mut current_utf16 = 0;
    for (i, c) in text.chars().enumerate() {
        if current_utf16 >= utf16_pos {
            return i;
        }
        current_utf16 += c.len_utf16();
    }
    text.chars().count()
}

fn split_overlapping(spans: Vec<MarkupSpan>) -> Vec<MarkupSpan> {
    if spans.is_empty() {
        return vec![];
    }
    let mut events = Vec::new();
    for (idx, span) in spans.iter().enumerate() {
        events.push((span.start, 0, idx));
        events.push((span.end, 1, idx));
    }
    events.sort_by(|a, b| {
        if a.0 != b.0 {
            a.0.cmp(&b.0)
        } else {
            a.1.cmp(&b.1)
        }
    });

    let mut result = Vec::new();
    let mut active_indices: Vec<usize> = Vec::new();
    let mut prev_pos = 0;

    for (pos, event_type, idx) in events {
        if !active_indices.is_empty() && pos > prev_pos {
            let mut prefix = String::new();
            let mut suffix = String::new();
            for &active_idx in &active_indices {
                prefix.push_str(&spans[active_idx].prefix);
            }
            for &active_idx in active_indices.iter().rev() {
                suffix.push_str(&spans[active_idx].suffix);
            }
            result.push(MarkupSpan {
                start: prev_pos,
                end: pos,
                prefix,
                suffix,
            });
        }
        if event_type == 0 {
            active_indices.push(idx);
        } else {
            if let Some(pos_in_vec) = active_indices.iter().position(|&x| x == idx) {
                active_indices.remove(pos_in_vec);
            }
        }
        prev_pos = pos;
    }
    result
}

#[pyfunction]
#[pyo3(signature = (text, markups, is_code=false))]
fn process_markups(text: &str, markups: Vec<Bound<'_, PyDict>>, is_code: bool) -> String {
    let mut markup_ranges = Vec::new();
    
    // We work on chars instead of bytes.
    let chars: Vec<char> = text.chars().collect();
    
    for markup in markups {
        let markup_type: String = match markup.get_item("type") {
            Ok(Some(v)) => v.extract().unwrap_or_default(),
            _ => continue,
        };
        if markup_type.is_empty() {
            continue;
        }

        let start_utf16: usize = match markup.get_item("start") {
            Ok(Some(v)) => v.extract().unwrap_or(0),
            _ => 0,
        };
        let end_utf16: usize = match markup.get_item("end") {
            Ok(Some(v)) => v.extract().unwrap_or(0),
            _ => 0,
        };

        let mut start = utf16_to_python_pos(text, start_utf16);
        let mut end = utf16_to_python_pos(text, end_utf16);
        
        if start > chars.len() { start = chars.len(); }
        if end > chars.len() { end = chars.len(); }
        if start >= end { continue; }

        if markup_type == "STRONG" || markup_type == "EM" || markup_type == "CODE" {
            let mut leading_ws = 0;
            for &c in chars[start..end].iter() {
                if c.is_whitespace() { leading_ws += 1; } else { break; }
            }
            let mut trailing_ws = 0;
            for &c in chars[start..end].iter().rev() {
                if c.is_whitespace() { trailing_ws += 1; } else { break; }
            }
            start += leading_ws;
            if end >= trailing_ws { end -= trailing_ws; }
            if start >= end { continue; }
            
            let trimmed_text = &chars[start..end];
            if !trimmed_text.iter().any(|c| c.is_alphanumeric()) {
                continue;
            }
        }

        if markup_type == "STRONG" {
            markup_ranges.push((start, end, markup_type, MarkupSpan { start, end, prefix: "**".to_string(), suffix: "**".to_string() }));
        } else if markup_type == "EM" {
            markup_ranges.push((start, end, markup_type, MarkupSpan { start, end, prefix: "_".to_string(), suffix: "_".to_string() }));
        } else if markup_type == "CODE" {
            markup_ranges.push((start, end, markup_type, MarkupSpan { start, end, prefix: "`".to_string(), suffix: "`".to_string() }));
        } else if markup_type == "A" {
            let anchor_type: String = match markup.get_item("anchorType") {
                Ok(Some(v)) => v.extract().unwrap_or_default(),
                _ => String::new(),
            };
            if anchor_type == "LINK" {
                let href: String = match markup.get_item("href") {
                    Ok(Some(v)) => v.extract().unwrap_or_default(),
                    _ => String::new(),
                };
                let href = unescape_markdown_url(&href);
                markup_ranges.push((start, end, markup_type, MarkupSpan { start, end, prefix: "[".to_string(), suffix: format!("]({})", href) }));
            } else if anchor_type == "USER" {
                let user_id: String = match markup.get_item("userId") {
                    Ok(Some(v)) => v.extract().unwrap_or_default(),
                    _ => String::new(),
                };
                let url = format!("https://medium.com/u/{}", user_id);
                markup_ranges.push((start, end, markup_type, MarkupSpan { start, end, prefix: "[".to_string(), suffix: format!("]({})", url) }));
            }
        } else if markup_type == "HIGHLIGHT" {
            // Synthetic type injected from the post's separate `highlights`
            // array. Raw-HTML <mark> wrapper (frontend allowlists <mark>).
            // start/end already clamped above; no priority filtering — a
            // highlight may overlap any markup, split_overlapping nests them.
            markup_ranges.push((start, end, markup_type, MarkupSpan { start, end, prefix: "<mark class=\"bg-emerald-300 dark:bg-emerald-700 dark:text-white\">".to_string(), suffix: "</mark>".to_string() }));
        }
    }

    let mut link_ranges = Vec::new();
    let mut code_ranges = Vec::new();
    for (start, end, mtype, _) in &markup_ranges {
        if mtype == "A" { link_ranges.push((*start, *end)); }
        if mtype == "CODE" { code_ranges.push((*start, *end)); }
    }

    fn overlaps(s1: usize, e1: usize, s2: usize, e2: usize) -> bool {
        s1 < e2 && s2 < e1
    }

    let mut final_spans = Vec::new();
    for (start, end, mtype, span) in markup_ranges {
        if mtype == "CODE" && link_ranges.contains(&(start, end)) { continue; }
        if (mtype == "EM" || mtype == "STRONG") && code_ranges.contains(&(start, end)) { continue; }
        if mtype == "EM" || mtype == "STRONG" {
            let mut skip = false;
            for (ls, le) in &link_ranges {
                if overlaps(start, end, *ls, *le) { skip = true; break; }
            }
            if !skip {
                for (cs, ce) in &code_ranges {
                    if overlaps(start, end, *cs, *ce) { skip = true; break; }
                }
            }
            if skip { continue; }
        }
        final_spans.push(span);
    }

    if final_spans.is_empty() {
        if is_code { return escape_markdown_minimal(text); }
        return text.to_string();
    }

    let processed_spans = split_overlapping(final_spans);

    let mut result = String::new();
    let mut last_end = 0;

    for span in processed_spans {
        if span.start > last_end {
            let segment: String = chars[last_end..span.start].iter().collect();
            if is_code { result.push_str(&escape_markdown_minimal(&segment)); }
            else { result.push_str(&segment); }
        }
        let segment_text: String = chars[span.start..span.end].iter().collect();
        let formatted = if is_code { escape_markdown_minimal(&segment_text) } else { segment_text };
        result.push_str(&span.prefix);
        result.push_str(&formatted);
        result.push_str(&span.suffix);
        last_end = span.end;
    }
    
    if last_end < chars.len() {
        let segment: String = chars[last_end..].iter().collect();
        if is_code { result.push_str(&escape_markdown_minimal(&segment)); }
        else { result.push_str(&segment); }
    }

    result
}

#[pymodule]
fn freedium_rust_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(escape_markdown_minimal, m)?)?;
    m.add_function(wrap_pyfunction!(normalize_quotes, m)?)?;
    m.add_function(wrap_pyfunction!(unescape_markdown_url, m)?)?;
    m.add_function(wrap_pyfunction!(process_markups, m)?)?;
    Ok(())
}
