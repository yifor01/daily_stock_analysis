# -*- coding: utf-8 -*-
"""
===================================
格式化工具模組
===================================

提供各種內容格式化工具函式，用於將通用格式轉換為平臺特定格式。
"""

import re
from typing import List

import markdown2

TRUNCATION_SUFFIX = "\n\n...(本段內容過長已截斷)"
PAGE_MARKER_PREFIX = f"\n\n📄"
PAGE_MARKER_SAFE_BYTES = 16 # "\n\n📄 9999/9999"
PAGE_MARKER_SAFE_LEN = 13   # "\n\n📄 9999/9999"
MIN_MAX_WORDS = 10
MIN_MAX_BYTES = 40

# Unicode code point ranges for special characters.
_SPECIAL_CHAR_RANGE = (0x10000, 0xFFFFF)
_SPECIAL_CHAR_REGEX = re.compile(r'[\U00010000-\U000FFFFF]')


def _page_marker(i: int, total: int) -> str:
    return f"{PAGE_MARKER_PREFIX} {i+1}/{total}"


def _is_special_char(c: str) -> bool:
    """判斷字元是否為特殊字元
    
    Args:
        c: 字元
        
    Returns:
        True 如果字元為特殊字元，False 否則
    """
    if len(c) != 1:
        return False
    cp = ord(c)
    return _SPECIAL_CHAR_RANGE[0] <= cp <= _SPECIAL_CHAR_RANGE[1]


def _count_special_chars(s: str) -> int:
    """
    計算字串中的特殊字元數量
    
    Args:
        s: 字串
    """
    # reg find all (0x10000, 0xFFFFF)
    match = _SPECIAL_CHAR_REGEX.findall(s)
    return len(match)


def _effective_len(s: str, special_char_len: int = 2) -> int:
    """
    計算字串的有效長度
    
    Args:
        s: 字串
        special_char_len: 每個特殊字元的長度，預設為 2
        
    Returns:
        s 的有效長度
    """
    n = len(s)
    n += _count_special_chars(s) * (special_char_len - 1)
    return n


def _slice_at_effective_len(s: str, effective_len: int, special_char_len: int = 2) -> tuple[str, str]:
    """
    按有效長度分割字串
    
    Args:
        s: 字串
        effective_len: 有效長度
        special_char_len: 每個特殊字元的長度，預設為 2
        
    Returns:
        分割後的前、後部分字串
    """
    if _effective_len(s, special_char_len) <= effective_len:
        return s, ""
    
    s_ = s[:effective_len]
    n_special_chars = _count_special_chars(s_)
    residual_lens = n_special_chars * (special_char_len - 1) + len(s_) - effective_len
    while residual_lens > 0:
        residual_lens -= special_char_len if _is_special_char(s_[-1]) else 1
        s_ = s_[:-1]
    return s_, s[len(s_):]


def markdown_to_html_document(markdown_text: str) -> str:
    """
    Convert Markdown to a complete HTML document (for email, md2img, etc.).

    Uses markdown2 with table and code block support, wraps with inline CSS
    for compact, readable layout. Reused by notification email and md2img.

    Args:
        markdown_text: Raw Markdown content.

    Returns:
        Full HTML document string with DOCTYPE, head, and body.
    """
    html_content = markdown2.markdown(
        markdown_text,
        extras=["tables", "fenced-code-blocks", "break-on-newline", "cuddled-lists"],
    )

    css_style = """
            body {
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
                line-height: 1.5;
                color: #24292e;
                font-size: 14px;
                padding: 15px;
                max-width: 900px;
                margin: 0 auto;
            }
            h1 {
                font-size: 20px;
                border-bottom: 1px solid #eaecef;
                padding-bottom: 0.3em;
                margin-top: 1.2em;
                margin-bottom: 0.8em;
                color: #0366d6;
            }
            h2 {
                font-size: 18px;
                border-bottom: 1px solid #eaecef;
                padding-bottom: 0.3em;
                margin-top: 1.0em;
                margin-bottom: 0.6em;
            }
            h3 {
                font-size: 16px;
                margin-top: 0.8em;
                margin-bottom: 0.4em;
            }
            p {
                margin-top: 0;
                margin-bottom: 8px;
            }
            table {
                border-collapse: collapse;
                width: 100%;
                margin: 12px 0;
                display: block;
                overflow-x: auto;
                font-size: 13px;
            }
            th, td {
                border: 1px solid #dfe2e5;
                padding: 6px 10px;
                text-align: left;
            }
            th {
                background-color: #f6f8fa;
                font-weight: 600;
            }
            tr:nth-child(2n) {
                background-color: #f8f8f8;
            }
            tr:hover {
                background-color: #f1f8ff;
            }
            blockquote {
                color: #6a737d;
                border-left: 0.25em solid #dfe2e5;
                padding: 0 1em;
                margin: 0 0 10px 0;
            }
            code {
                padding: 0.2em 0.4em;
                margin: 0;
                font-size: 85%;
                background-color: rgba(27,31,35,0.05);
                border-radius: 3px;
                font-family: SFMono-Regular, Consolas, "Liberation Mono", Menlo, monospace;
            }
            pre {
                padding: 12px;
                overflow: auto;
                line-height: 1.45;
                background-color: #f6f8fa;
                border-radius: 3px;
                margin-bottom: 10px;
            }
            hr {
                height: 0.25em;
                padding: 0;
                margin: 16px 0;
                background-color: #e1e4e8;
                border: 0;
            }
            ul, ol {
                padding-left: 20px;
                margin-bottom: 10px;
            }
            li {
                margin: 2px 0;
            }
        """

    return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                {css_style}
            </style>
        </head>
        <body>
            {html_content}
        </body>
        </html>
        """


def markdown_to_plain_text(markdown_text: str) -> str:
    """
    將 Markdown 轉換為純文字
    
    移除 Markdown 格式標記，保留可讀性
    """
    text = markdown_text
    
    # 移除標題標記 # ## ###
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    
    # 移除加粗 **text** -> text
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    
    # 移除斜體 *text* -> text
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    
    # 移除引用 > text -> text
    text = re.sub(r'^>\s+', '', text, flags=re.MULTILINE)
    
    # 移除列表標記 - item -> item
    text = re.sub(r'^[-*]\s+', '• ', text, flags=re.MULTILINE)
    
    # 移除分隔線 ---
    text = re.sub(r'^---+$', '────────', text, flags=re.MULTILINE)
    
    # 移除表格語法 |---|---|
    text = re.sub(r'\|[-:]+\|[-:|\s]+\|', '', text)
    text = re.sub(r'^\|(.+)\|$', r'\1', text, flags=re.MULTILINE)
    
    # 清理多餘空行
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()


def _bytes(s: str) -> int:
    return len(s.encode('utf-8'))


def _chunk_by_max_bytes(content: str, max_bytes: int) -> List[str]:
    if _bytes(content) <= max_bytes:
        return [content]
    if max_bytes < MIN_MAX_BYTES:
        raise ValueError(f"max_bytes={max_bytes} < {MIN_MAX_BYTES}, 可能陷入無限遞迴。")
    
    sections: List[str] = []
    suffix = TRUNCATION_SUFFIX
    effective_max_bytes = max_bytes - _bytes(suffix)
    if effective_max_bytes <= 0:
        effective_max_bytes = max_bytes
        suffix = ""
        
    while True:
        chunk, content = slice_at_max_bytes(content, effective_max_bytes)
        if content.strip() != "":
            sections.append(chunk + suffix)
        else:
            # 最後一段了，直接新增並離開迴圈
            sections.append(chunk)
            break
    return sections


def chunk_content_by_max_bytes(content: str, max_bytes: int, add_page_marker: bool = False) -> List[str]:
    """
    按位元組數智慧分割訊息內容
    
    Args:
        content: 完整訊息內容
        max_bytes: 單條訊息最大位元組數
        add_page_marker: 是否新增分頁標記
        
    Returns:
        分割後的區塊列表
    """
    def _chunk(content: str, max_bytes: int) -> List[str]:
        # 優先按分隔線/標題分割，保證分頁自然
        if max_bytes < MIN_MAX_BYTES:
            raise ValueError(f"max_bytes={max_bytes} < {MIN_MAX_BYTES}, 可能陷入無限遞迴。")
        
        if _bytes(content) <= max_bytes:
            return [content]
        
        sections, separator = _chunk_by_separators(content)
        if separator == "" and len(sections) == 1:
            # 無法智慧分割，則強制按字數分割
            return _chunk_by_max_bytes(content, max_bytes)
        
        chunks: List[str] = []
        current_chunk: List[str] = []
        current_bytes = 0
        separator_bytes = _bytes(separator) if separator else 0
        effective_max_bytes = max_bytes - separator_bytes

        for section in sections:
            section += separator
            section_bytes = _bytes(section)
            
            # 如果單個 section 就超長，需要強制截斷
            if section_bytes > effective_max_bytes:
                # 先儲存當前積累的內容
                if current_chunk:
                    chunks.append("".join(current_chunk))
                    current_chunk = []
                    current_bytes = 0

                # 強制按位元組截斷，避免整段被截斷丟失
                section_chunks = _chunk(
                    section[:-separator_bytes], effective_max_bytes
                )
                section_chunks[-1] = section_chunks[-1] + separator
                chunks.extend(section_chunks)
                continue

            # 檢查加入後是否超長
            if current_bytes + section_bytes > effective_max_bytes:
                # 儲存當前塊，開始新塊
                if current_chunk:
                    chunks.append("".join(current_chunk))
                current_chunk = [section]
                current_bytes = section_bytes
            else:
                current_chunk.append(section)
                current_bytes += section_bytes
                
        # 新增最後一塊
        if current_chunk:
            chunks.append("".join(current_chunk))
            
        # 移除最後一個塊的分割符
        if (chunks and 
            len(chunks[-1]) > separator_bytes and 
            chunks[-1][-separator_bytes:] == separator
        ):
            chunks[-1] = chunks[-1][:-separator_bytes]
        
        return chunks
    
    if add_page_marker:
        max_bytes = max_bytes - PAGE_MARKER_SAFE_BYTES
    
    chunks = _chunk(content, max_bytes)
    if add_page_marker:
        total_chunks = len(chunks)
        for i, chunk in enumerate(chunks):
            chunks[i] = chunk + _page_marker(i, total_chunks)
    return chunks


def slice_at_max_bytes(text: str, max_bytes: int) -> str:
    """
    按位元組數截斷字串，確保不會在多位元組字元中間截斷

    Args:
        text: 要截斷的字串
        max_bytes: 最大位元組數

    Returns:
        截斷後的字串
    """
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text, ""

    # 從最大位元組數開始向前查詢，找到完整的 UTF-8 字元邊界
    truncated = encoded[:max_bytes]
    while truncated and (truncated[-1] & 0xC0) == 0x80:
        truncated = truncated[:-1]

    truncated = truncated.decode('utf-8', errors='ignore')
    return truncated, text[len(truncated):]


def format_feishu_markdown(content: str) -> str:
    """
    將通用 Markdown 轉換為飛書 lark_md 更友好的格式
    
    轉換規則：
    - 飛書不支援 Markdown 標題（# / ## / ###），用加粗代替
    - 引用塊使用字首替代
    - 分隔線統一為細線
    - 表格轉換為條目列表
    
    Args:
        content: 原始 Markdown 內容
        
    Returns:
        轉換後的飛書 Markdown 格式內容
        
    Example:
        >>> markdown = "# 標題\\n> 引用\\n| 列1 | 列2 |"
        >>> formatted = format_feishu_markdown(markdown)
        >>> print(formatted)
        **標題**
        💬 引用
        • 列1：值1 | 列2：值2
    """
    def _flush_table_rows(buffer: List[str], output: List[str]) -> None:
        """將表格緩衝區中的行轉換為飛書格式"""
        if not buffer:
            return

        def _parse_row(row: str) -> List[str]:
            """解析表格行，提取單元格"""
            cells = [c.strip() for c in row.strip().strip('|').split('|')]
            return [c for c in cells if c]

        rows = []
        for raw in buffer:
            # 跳過分隔行（如 |---|---|）
            if re.match(r'^\s*\|?\s*[:-]+\s*(\|\s*[:-]+\s*)+\|?\s*$', raw):
                continue
            parsed = _parse_row(raw)
            if parsed:
                rows.append(parsed)

        if not rows:
            return

        header = rows[0]
        data_rows = rows[1:] if len(rows) > 1 else []
        for row in data_rows:
            pairs = []
            for idx, cell in enumerate(row):
                key = header[idx] if idx < len(header) else f"列{idx + 1}"
                pairs.append(f"{key}：{cell}")
            output.append(f"• {' | '.join(pairs)}")

    lines = []
    table_buffer: List[str] = []

    for raw_line in content.splitlines():
        line = raw_line.rstrip()

        # 處理表格行
        if line.strip().startswith('|'):
            table_buffer.append(line)
            continue

        # 重新整理表格緩衝區
        if table_buffer:
            _flush_table_rows(table_buffer, lines)
            table_buffer = []

        # 轉換標題（# ## ### 等）
        if re.match(r'^#{1,6}\s+', line):
            title = re.sub(r'^#{1,6}\s+', '', line).strip()
            line = f"**{title}**" if title else ""
        # 轉換引用塊
        elif line.startswith('> '):
            quote = line[2:].strip()
            line = f"💬 {quote}" if quote else ""
        # 轉換分隔線
        elif line.strip() == '---':
            line = '────────'
        # 轉換列表項
        elif line.startswith('- '):
            line = f"• {line[2:].strip()}"

        lines.append(line)

    # 處理末尾的表格
    if table_buffer:
        _flush_table_rows(table_buffer, lines)

    return "\n".join(lines).strip()


def _chunk_by_separators(content: str) -> tuple[list[str], str]:
    """
    透過分割線等特殊字元將訊息內容分割為多個區塊
    
    Args:
        content: 完整訊息內容
        
    Returns:
        sections: 分割後的區塊列表
        separator: 區塊之間的分隔符，None 表示無法分割
    """
    # 智慧分割：優先按 "---" 分隔（股票之間的分隔線）
    # 其次嘗試各級標題分割
    if "\n---\n" in content:
        sections = content.split("\n---\n")
        separator = "\n---\n"
    elif "\n# " in content:
        # 按 # 分割 (相容一級標題)
        parts = content.split("\n## ")
        sections = [parts[0]] + [f"## {p}" for p in parts[1:]]
        separator = "\n"
    elif "\n## " in content:
        # 按 ## 分割 (相容二級標題)
        parts = content.split("\n## ")
        sections = [parts[0]] + [f"## {p}" for p in parts[1:]]
        separator = "\n"
    elif "\n### " in content:
        # 按 ### 分割
        parts = content.split("\n### ")
        sections = [parts[0]] + [f"### {p}" for p in parts[1:]]
        separator = "\n"
    elif "\n**" in content:
        # 按 ** 加粗標題分割 (相容 AI 未輸出標準 Markdown 標題的情況)
        parts = content.split("\n**")
        sections = [parts[0]] + [f"**{p}" for p in parts[1:]]
        separator = "\n"
    elif "\n" in content:
        # 按 \n 分割
        sections = content.split("\n")
        separator = "\n"
    else:
        return [content], ""
    return sections, separator


def _chunk_by_max_words(content: str, max_words: int, special_char_len: int = 2) -> list[str]:
    """
    按字數分割訊息內容
    
    Args:
        content: 完整訊息內容
        max_words: 單條訊息最大字數
        special_char_len: 每個特殊字元的長度，預設為 2
        
    Returns:
        分割後的區塊列表
    """
    if _effective_len(content, special_char_len) <= max_words:
        return [content]
    if max_words < MIN_MAX_WORDS:
        raise ValueError(
            f"max_words={max_words} < {MIN_MAX_WORDS}, 可能陷入無限遞迴。"
        )

    sections = []
    suffix = TRUNCATION_SUFFIX
    effective_max_words = max_words - len(suffix)  # 預留字尾，避免邊界超限
    if effective_max_words <= 0:
        effective_max_words = max_words
        suffix = ""

    while True:
        chunk, content = _slice_at_effective_len(content, effective_max_words, special_char_len)
        if content.strip() != "":
            sections.append(chunk + suffix)
        else:
            # 最後一段了，直接新增並離開迴圈
            sections.append(chunk)
            break
    return sections


def chunk_content_by_max_words(
    content: str, 
    max_words: int, 
    special_char_len: int = 2,
    add_page_marker: bool = False
    ) -> list[str]:
    """
    按字數智慧分割訊息內容
    
    Args:
        content: 完整訊息內容
        max_words: 單條訊息最大字數
        special_char_len: 每個特殊字元的長度，預設為 2
        add_page_marker: 是否新增分頁標記
        
    Returns:
        分割後的區塊列表
    """
    def _chunk(content: str, max_words: int, special_char_len: int = 2) -> list[str]:
        if max_words < MIN_MAX_WORDS:
            # Safe guard，避免無限遞迴
            # 理論上，max_words在每次遞迴中可以減小到無限小，但實際中不太可能發生，
            # 除非每次_chunk_by_separators都能成功返回分隔符，且max_words初始值太小。
            raise ValueError(f"max_words={max_words} < {MIN_MAX_WORDS}, 可能陷入無限遞迴。")
        
        if _effective_len(content, special_char_len) <= max_words:
            return [content]

        sections, separator = _chunk_by_separators(content)
        if separator == "" and len(sections) == 1:
            # 無法智慧分割，則強制按字數分割
            return _chunk_by_max_words(content, max_words, special_char_len)

        chunks = []
        current_chunk = []
        current_word_len = 0
        separator_len = len(separator) if separator else 0
        effective_max_words = max_words - separator_len # 預留分割符長度，避免邊界超限

        for section in sections:
            section += separator
            section_word_len = _effective_len(section, special_char_len)

            # 如果單個 section 就超長，需要強制截斷
            if section_word_len > max_words:
                # 先儲存當前積累的內容
                if current_chunk:
                    chunks.append("".join(current_chunk))

                # 強制截斷這個超長 section
                section_chunks = _chunk(
                    section[:-separator_len], effective_max_words, special_char_len
                    )
                section_chunks[-1] = section_chunks[-1] + separator
                chunks.extend(section_chunks)
                continue

            # 檢查加入後是否超長
            if current_word_len + section_word_len > max_words:
                # 儲存當前塊，開始新塊
                if current_chunk:
                    chunks.append("".join(current_chunk))
                current_chunk = [section]
                current_word_len = section_word_len
            else:
                current_chunk.append(section)
                current_word_len += section_word_len

        # 新增最後一塊
        if current_chunk:
            chunks.append("".join(current_chunk))

        # 移除最後一個塊的分割符
        if (chunks and
            len(chunks[-1]) > separator_len and
            chunks[-1][-separator_len:] == separator
        ):
            chunks[-1] = chunks[-1][:-separator_len]
        return chunks
    
    
    if add_page_marker:
        max_words = max_words - PAGE_MARKER_SAFE_LEN
    
    chunks = _chunk(content, max_words, special_char_len)
    if add_page_marker:
        total_chunks = len(chunks)
        for i, chunk in enumerate(chunks):
            chunks[i] = chunk + _page_marker(i, total_chunks)
    return chunks
