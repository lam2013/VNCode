"""
API Module for VNCode IDE
Combines all API-related functionality:
- Open VSX Registry API Client (openvsx_api)
- Python LSP Server (lsp_python)
- Extension Integration Helpers (extension_integration)
"""

# ═══════════════════════════════════════════════════════════════════════════
# PART 1: Open VSX Registry API Client
# ═══════════════════════════════════════════════════════════════════════════

import json
import urllib.request
import urllib.parse
import urllib.error
import ssl
import os
import logging
import hashlib
import re
import sys
import subprocess
import threading
import time
import queue
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple, Callable
from enum import Enum

BASE_URL = "https://open-vsx.org/api"

# Get logger
logger = logging.getLogger('vncode')

# Reusable SSL context with certificate verification disabled
# (Windows Python often lacks proper CA certificates)
_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE


def _get_json(url: str, timeout: int = 15) -> Optional[dict]:
    """GET a URL and parse JSON response. Returns None on error."""
    try:
        req = urllib.request.Request(url, headers={
            "Accept": "application/json",
            "User-Agent": "VNCode-IDE/1.1"
        })
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx) as resp:
            data = resp.read()
            return json.loads(data.decode("utf-8"))
    except Exception as e:
        logger.error(f"GET {url} failed: {e}")
        return None


def search_extensions(query: str, offset: int = 0, size: int = 20,
                      sort_by: str = "relevance", sort_order: str = "desc",
                      category: str = "") -> Optional[dict]:
    """
    Search extensions on Open VSX.
    Returns {"offset", "totalSize", "extensions": [...]}.
    
    Note: OpenVSX API may not support all sort options. Use with caution.
    """
    params = {
        "query": query,
        "size": size,
        "offset": offset,
    }
    
    # Only add sort parameters if they are supported
    if sort_by in ["relevance"]:  # Add more as discovered
        params["sortBy"] = sort_by
        params["sortOrder"] = sort_order
    
    # Add category to query if specified
    if category and category != "all":
        if query.strip():
            params["query"] = f"{query} {category}"
        else:
            params["query"] = category
    
    url = f"{BASE_URL}/-/search?{urllib.parse.urlencode(params)}"
    return _get_json(url)


def get_extension_detail(namespace: str, name: str) -> Optional[dict]:
    """Get detailed info about a specific extension."""
    url = f"{BASE_URL}/{namespace}/{name}"
    return _get_json(url)


def get_extension_version(namespace: str, name: str, version: str) -> Optional[dict]:
    """Get info about a specific version of an extension."""
    url = f"{BASE_URL}/{namespace}/{name}/{version}"
    return _get_json(url)


def download_file(url: str, save_path: str, progress_callback=None) -> bool:
    """
    Download a file from URL to save_path.
    progress_callback(bytes_downloaded, total_bytes) is called periodically.
    Returns True on success.
    """
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "VNCode-IDE/1.1"
        })
        with urllib.request.urlopen(req, timeout=60, context=_ssl_ctx) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            os.makedirs(os.path.dirname(save_path), exist_ok=True)

            downloaded = 0
            chunk_size = 8192

            with open(save_path, "wb") as f:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback:
                        progress_callback(downloaded, total)

        return True
    except Exception as e:
        logger.error(f"Download {url} failed: {e}")
        # Clean up partial file
        try:
            if os.path.exists(save_path):
                os.remove(save_path)
        except OSError:
            pass
        return False


def download_icon(icon_url: str, cache_dir: str) -> Optional[str]:
    """
    Download an extension icon to cache. Returns local path or None.
    Uses URL hash as filename to avoid re-downloading.
    """
    if not icon_url:
        return None

    url_hash = hashlib.md5(icon_url.encode()).hexdigest()
    ext = ".png"
    if ".svg" in icon_url.lower():
        ext = ".svg"
    elif ".jpg" in icon_url.lower() or ".jpeg" in icon_url.lower():
        ext = ".jpg"

    cache_path = os.path.join(cache_dir, f"icon_{url_hash}{ext}")
    if os.path.exists(cache_path):
        return cache_path

    if download_file(icon_url, cache_path):
        return cache_path
    return None


def format_download_count(count: int) -> str:
    """Format download count: 38559674 → '38.6M'"""
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    elif count >= 1_000:
        return f"{count / 1_000:.1f}K"
    return str(count)


def get_featured_extensions(size: int = 10) -> Optional[list]:
    """
    Get featured/popular extensions.
    Returns list of extension dicts.
    """
    # Search for popular extensions without query
    result = search_extensions("", size=size, sort_by="downloads", sort_order="desc")
    if result and "extensions" in result:
        return result["extensions"]
    return None


def check_extension_updates(namespace: str, name: str, current_version: str) -> Optional[dict]:
    """
    Check if there's a newer version of an extension available.
    Returns the latest extension info if update available, None otherwise.
    """
    # Get latest version info
    latest = get_extension_detail(namespace, name)
    if latest and latest.get("version") != current_version:
        return latest
    return None


# ═══════════════════════════════════════════════════════════════════════════
# PART 2: Extension Integration Helpers
# ═══════════════════════════════════════════════════════════════════════════

def get_lsp_aware_suggestions(language: str, prefix: str = "", extension_hooks=None, 
                              text: str = "", line: int = 0, character: int = 0) -> List[str]:
    """
    Get autocomplete suggestions considering LSP extensions first.
    Falls back to default SYNTAX_INFO if no LSP extension found.
    
    Args:
        language: Programming language (python, cpp, c, etc.)
        prefix: Text prefix to filter suggestions
        extension_hooks: ExtensionHooks instance, or None to use default
        text: Full document text (for LSP server)
        line: Current line number (for LSP server)
        character: Current character position (for LSP server)
        
    Returns:
        List of suggestion strings
    """
    suggestions = []
    
    # For Python: try Python LSP server first
    if language and language.lower() == "python":
        try:
            lsp_suggestions = get_python_lsp_suggestions(text, line, character)
            if lsp_suggestions:
                logger.debug(f"Got {len(lsp_suggestions)} suggestions from Python LSP")
                suggestions.extend(lsp_suggestions)
        except Exception as e:
            logger.debug(f"Python LSP failed: {e}")
    
    # Try to get from LSP extension
    if extension_hooks:
        try:
            lsp_ext = extension_hooks.get_lsp_for_language(language)
            if lsp_ext:
                logger.debug(f"Using LSP extension for {language}")
                contributions = lsp_ext.get("contributions", {})
                
                # Get snippets from LSP extension
                snippets = contributions.get("snippets", [])
                if snippets:
                    # Import here to avoid circular dependency
                    from core import load_snippets, get_snippet_completions
                    for snippet_info in snippets:
                        snippet_data = load_snippets(snippet_info.get("path", ""))
                        if snippet_data:
                            completions = get_snippet_completions(snippet_data)
                            suggestions.extend([c[0] for c in completions])
                
                # Also get from completions providers
                completions = extension_hooks.get_completions_from_providers(prefix, language)
                suggestions.extend([c[0] if isinstance(c, tuple) else c for c in completions])
        except Exception as e:
            logger.debug(f"Extension LSP error: {e}")
    
    # Filter by prefix
    if prefix:
        suggestions = [s for s in suggestions if s.lower().startswith(prefix.lower())]
    
    # Remove duplicates while preserving order
    seen = set()
    filtered = []
    for s in suggestions:
        if s.lower() not in seen:
            seen.add(s.lower())
            filtered.append(s)
    
    return filtered


def get_syntax_highlighter_for_language(language: str, extension_hooks=None):
    """
    Get syntax highlighter extension (grammar/rules) for a language.
    
    Args:
        language: Programming language (python, cpp, etc.)
        extension_hooks: ExtensionHooks instance
        
    Returns:
        Extension metadata dict if found, else None
    """
    if not extension_hooks:
        return None
    
    try:
        highlighter = extension_hooks.get_highlighter_for_language(language)
        if highlighter:
            logger.debug(f"Found highlighter extension for {language}")
            return highlighter
    except Exception as e:
        logger.error(f"Error getting highlighter: {e}")
    
    return None


def load_textmate_grammar(grammar_path: str) -> Optional[dict]:
    """
    Load a TextMate grammar file (JSON format).
    
    Args:
        grammar_path: Path to grammar file (.json or .plist)
        
    Returns:
        Grammar dict, or None if failed to load
    """
    if not os.path.exists(grammar_path):
        logger.warning(f"Grammar file not found: {grammar_path}")
        return None
    
    try:
        if grammar_path.endswith('.json'):
            with open(grammar_path, 'r', encoding='utf-8') as f:
                # Remove comments
                content = f.read()
                content = re.sub(r'(?<!:)//.*?$', '', content, flags=re.MULTILINE)
                content = re.sub(r',\s*([}\]])', r'\1', content)
                return json.loads(content)
        
        elif grammar_path.endswith('.plist'):
            # For plist support, would need additional library
            logger.warning(f"Plist grammar not yet supported: {grammar_path}")
            return None
            
    except Exception as e:
        logger.error(f"Failed to load grammar {grammar_path}: {e}")
    
    return None


def apply_textmate_grammar_to_highlighter(highlighter, grammar: dict, lang: str):
    """
    Apply TextMate grammar rules to a QSyntaxHighlighter.
    
    Args:
        highlighter: CodeHighlighter instance
        grammar: Grammar dict (from load_textmate_grammar)
        lang: Language name for logging
        
    Returns:
        True if applied successfully, False otherwise
    """
    if not grammar:
        return False
    
    try:
        from PyQt5.QtGui import QColor, QTextCharFormat, QFont
        
        # Extract patterns from grammar
        patterns = grammar.get("patterns", [])
        repository = grammar.get("repository", {})
        
        # Clear existing rules and add grammar-based rules
        highlighter.highlighting_rules = []
        
        # Create format mapping for common scopes
        scope_formats = {
            "keyword": _create_format("#569cd6", bold=True),  # blue keywords
            "string": _create_format("#ce9178"),              # orange strings
            "comment": _create_format("#6a9955"),             # green comments
            "function": _create_format("#dcdcaa"),            # yellow functions
            "variable": _create_format("#ffffff"),            # white variables
            "number": _create_format("#b5cea8"),              # light green numbers
            "constant": _create_format("#4ec9b0"),            # cyan constants
            "operator": _create_format("#d4d4d4"),            # white operators
        }
        
        # Process grammar patterns
        for pattern in patterns:
            if isinstance(pattern, dict):
                _process_grammar_pattern(pattern, highlighter, scope_formats)
        
        logger.info(f"Applied TextMate grammar to {lang} highlighter")
        return True
    
    except Exception as e:
        logger.error(f"Failed to apply grammar: {e}")
        return False


def _create_format(color: str, bold: bool = False, italic: bool = False):
    """Helper to create QTextCharFormat."""
    from PyQt5.QtGui import QTextCharFormat, QColor, QFont
    fmt = QTextCharFormat()
    fmt.setForeground(QColor(color))
    if bold:
        fmt.setFontWeight(QFont.Bold)
    if italic:
        fmt.setFontItalic(True)
    return fmt


def _process_grammar_pattern(pattern: dict, highlighter, scope_formats: dict):
    """
    Process a single grammar pattern and add to highlighter.
    
    Args:
        pattern: Pattern dict from grammar
        highlighter: CodeHighlighter instance
        scope_formats: Dict mapping scope names to QTextCharFormat
    """
    if isinstance(pattern, str) and pattern.startswith("include "):
        # Handle includes - for now skip
        return
    
    if not isinstance(pattern, dict):
        return
    
    match = pattern.get("match")
    name = pattern.get("name", "")
    captures = pattern.get("captures", {})
    begin = pattern.get("begin")
    end = pattern.get("end")
    
    # Determine format from scope name
    fmt = _get_format_from_scope(name, scope_formats)
    
    # Simple match pattern
    if match:
        try:
            pattern_obj = re.compile(match)
            highlighter.highlighting_rules.append((pattern_obj, fmt))
        except Exception as e:
            logger.debug(f"Invalid regex pattern: {e}")
    
    # Begin-end pattern (like multi-line strings/comments)
    elif begin and end:
        # Simplified: just match the begin part
        try:
            pattern_obj = re.compile(begin)
            highlighter.highlighting_rules.append((pattern_obj, fmt))
        except Exception as e:
            logger.debug(f"Invalid regex pattern: {e}")


def _get_format_from_scope(scope_name: str, scope_formats: dict):
    """
    Get QTextCharFormat based on TextMate scope name.
    
    Args:
        scope_name: TextMate scope (e.g., "keyword.control", "string.quoted")
        scope_formats: Dict mapping scope prefixes to QTextCharFormat
        
    Returns:
        QTextCharFormat for the scope
    """
    from PyQt5.QtGui import QTextCharFormat, QColor
    
    if not scope_name:
        return QTextCharFormat()
    
    # Check for matching scope prefixes
    for scope_prefix, fmt in scope_formats.items():
        if scope_prefix in scope_name.lower():
            return fmt
    
    # Default format
    default_fmt = QTextCharFormat()
    default_fmt.setForeground(QColor("#d4d4d4"))
    return default_fmt


def apply_lsp_keywords_to_syntax(highlighter, lsp_ext: dict, lang: str):
    """
    Extract keywords/symbols from LSP extension and apply to highlighter.
    
    Args:
        highlighter: CodeHighlighter instance
        lsp_ext: LSP extension metadata
        lang: Language name
        
    Returns:
        True if applied successfully
    """
    try:
        # Get keywords from LSP contributions if available
        contributions = lsp_ext.get("contributions", {})
        
        # For now, just log that LSP is being used
        # In future: could parse LSP server capabilities from extension
        logger.info(f"Detected LSP extension for {lang}: {lsp_ext.get('displayName')}")
        
        return True
    except Exception as e:
        logger.error(f"Failed to apply LSP keywords: {e}")
        return False


def get_python_lsp_suggestions(text: str, line: int, character: int) -> List[str]:
    """
    Get Python autocomplete suggestions from Python LSP data.
    
    Args:
        text: Full document text
        line: Current line number
        character: Character position on line
        
    Returns:
        List of suggestion strings
    """
    # Use Python keywords and built-ins
    suggestions = PYTHON_KEYWORDS + PYTHON_BUILTINS + PYTHON_COMMON_MODULES
    return suggestions


# ═══════════════════════════════════════════════════════════════════════════
# PART 3: Python LSP Server
# ═══════════════════════════════════════════════════════════════════════════

# Python keywords and built-ins for suggestions
PYTHON_KEYWORDS = [
    "False", "None", "True", "and", "as", "assert", "async", "await",
    "break", "class", "continue", "def", "del", "elif", "else", "except",
    "finally", "for", "from", "global", "if", "import", "in", "is",
    "lambda", "nonlocal", "not", "or", "pass", "raise", "return", "try",
    "while", "with", "yield"
]

PYTHON_BUILTINS = [
    "abs", "all", "any", "ascii", "bin", "bool", "breakpoint", "bytearray",
    "bytes", "callable", "chr", "classmethod", "compile", "complex",
    "delattr", "dict", "dir", "divmod", "enumerate", "eval", "exec",
    "filter", "float", "format", "frozenset", "getattr", "globals",
    "hasattr", "hash", "help", "hex", "id", "input", "int", "isinstance",
    "issubclass", "iter", "len", "list", "locals", "map", "max",
    "memoryview", "min", "next", "object", "oct", "open", "ord", "pow",
    "print", "property", "range", "repr", "reversed", "round", "set",
    "setattr", "slice", "sorted", "staticmethod", "str", "sum", "super",
    "tuple", "type", "vars", "zip"
]

PYTHON_COMMON_MODULES = [
    "os", "sys", "re", "json", "math", "random", "datetime", "time",
    "collections", "itertools", "functools", "operator", "string",
    "io", "pickle", "shelve", "dbm", "sqlite3", "csv", "configparser",
    "hashlib", "hmac", "secrets", "urllib", "http", "ftplib", "poplib",
    "imaplib", "smtplib", "uuid", "socketserver", "xmlrpc", "ipaddress",
    "argparse", "logging", "getpass", "curses", "platform", "errno",
    "unittest", "doctest", "pdb", "cProfile", "timeit", "tracemalloc",
    "gc", "weakref", "types", "copy", "pprint", "enum", "numbers",
    "cmath", "statistics", "decimal", "fractions", "pathlib", "tempfile",
    "glob", "fnmatch", "linecache", "shutil", "gzip", "bz2", "lzma",
    "zipfile", "tarfile", "zlib", "array", "struct", "codecs", "encodings",
    "stringprep", "readline", "rlcompleter", "ast", "symtable", "token",
    "keyword", "tokenize", "inspect", "importlib", "traceback", "warnings",
    "contextlib", "abc", "atexit", "traceback", "site", "fpectl",
]


class PythonLSPServer:
    """Python Language Server Protocol implementation"""
    
    def __init__(self):
        self.initialized = False
        self.message_id = 0
        
    def read_message(self) -> Optional[Dict[str, Any]]:
        """Read a JSON-RPC message from stdin"""
        try:
            while True:
                line = sys.stdin.readline()
                if not line:
                    return None
                if line.startswith("Content-Length:"):
                    content_length = int(line.split(":")[1].strip())
                    sys.stdin.readline()  # Read empty line
                    content = sys.stdin.read(content_length)
                    return json.loads(content)
        except Exception as e:
            self.log(f"Error reading message: {e}")
            return None
    
    def send_message(self, message: Dict[str, Any]) -> None:
        """Send a JSON-RPC message to stdout"""
        try:
            content = json.dumps(message)
            sys.stdout.write(f"Content-Length: {len(content)}\r\n\r\n{content}")
            sys.stdout.flush()
        except Exception as e:
            self.log(f"Error sending message: {e}")
    
    def log(self, message: str) -> None:
        """Log a message to stderr for debugging"""
        try:
            sys.stderr.write(f"[LSP-Python] {message}\n")
            sys.stderr.flush()
        except:
            pass
    
    def handle_initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle initialize request"""
        self.initialized = True
        return {
            "capabilities": {
                "completionProvider": {
                    "resolveProvider": False,
                    "triggerCharacters": ["."]
                },
                "textDocumentSync": 1,  # FULL
                "hoverProvider": True,
            }
        }
    
    def get_suggestions(self, word: str = "") -> List[Dict[str, Any]]:
        """Get Python suggestions based on partial word"""
        suggestions = []
        all_items = PYTHON_KEYWORDS + PYTHON_BUILTINS + PYTHON_COMMON_MODULES
        
        # Filter based on what user typed
        word_lower = word.lower()
        for item in all_items:
            if item.lower().startswith(word_lower):
                # Determine kind and detail
                if item in PYTHON_KEYWORDS:
                    kind = 14  # Keyword
                    detail = "Python keyword"
                elif item in PYTHON_BUILTINS:
                    kind = 6  # Function
                    detail = "Python built-in"
                else:
                    kind = 9  # Module
                    detail = "Python module"
                
                suggestions.append({
                    "label": item,
                    "kind": kind,
                    "detail": detail,
                    "sortText": item,
                })
        
        # Sort by match quality (exact prefix match first)
        suggestions.sort(key=lambda x: (len(x["label"]), x["label"]))
        return suggestions[:50]  # Limit to 50 suggestions
    
    def extract_word_at_position(self, text: str, line: int, character: int) -> str:
        """Extract the word being typed at the cursor position"""
        lines = text.split("\n")
        if line >= len(lines):
            return ""
        
        line_text = lines[line]
        if character > len(line_text):
            character = len(line_text)
        
        # Extract word (alphanumeric + underscore)
        word_start = character
        while word_start > 0 and (line_text[word_start - 1].isalnum() or line_text[word_start - 1] == "_"):
            word_start -= 1
        
        return line_text[word_start:character]
    
    def handle_completion(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle completion/autocomplete request"""
        text_document = params.get("textDocument", {})
        position = params.get("position", {})
        
        # Get file content (if available in params)
        text = params.get("textDocumentContent", "")
        line = position.get("line", 0)
        character = position.get("character", 0)
        
        # Extract the word being typed
        word = self.extract_word_at_position(text, line, character)
        
        # Get suggestions
        items = self.get_suggestions(word)
        
        return {
            "isIncomplete": False,
            "items": items
        }
    
    def handle_method(self, method: str, params: Dict[str, Any]) -> Any:
        """Route method calls to appropriate handlers"""
        if method == "initialize":
            return self.handle_initialize(params)
        elif method == "textDocument/completion":
            return self.handle_completion(params)
        elif method == "initialized":
            return {}
        elif method == "shutdown":
            return None
        else:
            return None
    
    def run(self) -> None:
        """Main server loop"""
        self.log("Python LSP Server started")
        
        while True:
            message = self.read_message()
            if not message:
                break
            
            method = message.get("method")
            msg_id = message.get("id")
            params = message.get("params", {})
            
            self.log(f"Received: {method}")
            
            # Handle request
            try:
                result = self.handle_method(method, params)
                
                # Send response if this is a request (has id)
                if msg_id is not None:
                    response = {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "result": result
                    }
                    self.send_message(response)
            except Exception as e:
                self.log(f"Error handling {method}: {e}")
                if msg_id is not None:
                    response = {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "error": {
                            "code": -32603,
                            "message": str(e)
                        }
                    }
                    self.send_message(response)
            
            # Exit on shutdown
            if method == "shutdown":
                break
        
        self.log("Python LSP Server stopped")


def lsp_main():
    """Main entry point for LSP server"""
    server = PythonLSPServer()
    server.run()


# ═══════════════════════════════════════════════════════════════════════════
# PART 4: C/C++ LSP Support (cpp_lsp)
# ═══════════════════════════════════════════════════════════════════════════

class CppStandard(Enum):
    """C++ standard versions."""
    C89 = "C89"
    C99 = "C99"
    C11 = "C11"
    C17 = "C17"
    CXX98 = "C++98"
    CXX11 = "C++11"
    CXX14 = "C++14"
    CXX17 = "C++17"
    CXX20 = "C++20"


class CppCompletionProvider:
    """Provides C/C++ code completions and suggestions."""
    
    # Standard C library functions
    C_STDLIB = {
        "stdio": ["printf", "scanf", "fprintf", "fscanf", "fopen", "fclose", "fread", "fwrite"],
        "stdlib": ["malloc", "free", "calloc", "realloc", "atoi", "atof", "rand", "srand"],
        "string": ["strlen", "strcpy", "strcat", "strcmp", "strncpy", "strtok"],
        "math": ["sin", "cos", "tan", "sqrt", "pow", "log", "exp", "fabs"],
        "ctype": ["isalpha", "isdigit", "isalnum", "isspace", "toupper", "tolower"],
        "time": ["time", "clock", "difftime", "mktime"],
    }
    
    # Standard C++ library (STL)
    CXX_STDLIB = {
        "iostream": ["std::cout", "std::cin", "std::cerr", "std::endl", "std::getline"],
        "string": {
            "std::string": [
                "append", "assign", "at", "back", "begin", "c_str", "capacity", 
                "clear", "compare", "copy", "data", "empty", "end", "erase", 
                "find", "find_first_of", "find_last_of", "insert", "length", 
                "max_size", "push_back", "replace", "resize", "rfind", 
                "size", "substr", "swap"
            ]
        },
        "vector": {
            "std::vector": [
                "assign", "at", "back", "begin", "capacity", "clear", 
                "data", "emplace", "emplace_back", "empty", "end", "erase", 
                "front", "insert", "max_size", "pop_back", "push_back", 
                "rbegin", "rend", "reserve", "resize", "shrink_to_fit", "size", "swap"
            ]
        },
        "map": {
            "std::map": [
                "at", "begin", "capacity", "clear", "count", "emplace", 
                "empty", "end", "erase", "find", "insert", "lower_bound", 
                "max_size", "rbegin", "rend", "size", "swap", "upper_bound"
            ]
        },
        "set": {
            "std::set": [
                "begin", "clear", "count", "emplace", "empty", "end", 
                "erase", "find", "insert", "lower_bound", "max_size", 
                "rbegin", "rend", "size", "swap", "upper_bound"
            ]
        },
        "algorithm": [
            "std::sort", "std::find", "std::reverse", "std::copy", 
            "std::unique", "std::count", "std::binary_search",
            "std::max_element", "std::min_element", "std::for_each"
        ],
        "memory": [
            "std::unique_ptr", "std::shared_ptr", "std::make_unique", 
            "std::make_shared", "std::get_deleter"
        ],
    }
    
    # Common variable/type declarations
    COMMON_PATTERNS = {
        "for_loop": "for (int i = 0; i < n; i++) {\n    // code\n}",
        "while_loop": "while (condition) {\n    // code\n}",
        "if_statement": "if (condition) {\n    // code\n} else {\n    // code\n}",
        "function_def": "void functionName(int param) {\n    // code\n}",
        "struct_def": "struct StructName {\n    int member;\n};",
        "class_def": "class ClassName {\npublic:\n    void method();\nprivate:\n    int member;\n};",
    }
    
    def __init__(self, cpp_standard: CppStandard = CppStandard.CXX17):
        """
        Initialize C++ completion provider.
        
        Args:
            cpp_standard: Target C++ standard version
        """
        self.cpp_standard = cpp_standard
        self.user_types: Dict[str, List[str]] = {}
    
    def get_completions_for_prefix(self, prefix: str, context: str = "") -> List[Tuple[str, str]]:
        """
        Get completions for a given prefix.
        
        Args:
            prefix: Completion prefix (e.g., "std::st" -> std::string)
            context: Additional context (e.g., after ".")
            
        Returns:
            List of (completion, description) tuples
        """
        completions = []
        prefix_lower = prefix.lower()
        
        # Check C stdlib
        for header, funcs in self.C_STDLIB.items():
            for func in funcs:
                if func.lower().startswith(prefix_lower):
                    completions.append((func, f"C stdlib from <{header}>"))
        
        # Check C++ stdlib
        for header, items in self.CXX_STDLIB.items():
            if isinstance(items, dict):
                # Nested (type -> members)
                for type_name, members in items.items():
                    if type_name.lower().startswith(prefix_lower):
                        completions.append((type_name, f"Type from <{header}>"))
                    for member in members:
                        if member.lower().startswith(prefix_lower):
                            completions.append((member, f"Member of {type_name}"))
            else:
                # List of functions
                for item in items:
                    if item.lower().startswith(prefix_lower):
                        completions.append((item, f"Function from <{header}>"))
        
        # Check patterns
        for pattern_name in self.COMMON_PATTERNS:
            if pattern_name.lower().startswith(prefix_lower):
                completions.append((pattern_name, "Code snippet"))
        
        return completions
    
    def get_member_completions(self, type_name: str) -> List[Tuple[str, str]]:
        """
        Get member/method completions for a type.
        
        Args:
            type_name: Type name (e.g., "std::string", "vector")
            
        Returns:
            List of (member_name, description) tuples
        """
        completions = []
        
        # Normalize type name
        type_name_normalized = type_name.replace("std::", "")
        
        # Check C++ stdlib
        for header, items in self.CXX_STDLIB.items():
            if isinstance(items, dict):
                for std_type, members in items.items():
                    # Match with or without "std::" prefix
                    if std_type.replace("std::", "") == type_name_normalized:
                        for member in members:
                            completions.append((member, f"Member of {type_name}"))
        
        # Check user-defined types
        if type_name in self.user_types:
            for member in self.user_types[type_name]:
                completions.append((member, f"User-defined member of {type_name}"))
        
        return completions
    
    def register_user_type(self, type_name: str, members: List[str]) -> None:
        """
        Register a user-defined type and its members.
        
        Args:
            type_name: Name of the type (class or struct)
            members: List of member names
        """
        self.user_types[type_name] = members
        logger.info(f"Registered user type: {type_name} with {len(members)} members")
    
    def get_include_suggestions(self, prefix: str) -> List[str]:
        """
        Get include file suggestions.
        
        Args:
            prefix: Partial include name
            
        Returns:
            List of include file suggestions
        """
        all_headers = set()
        all_headers.update(self.C_STDLIB.keys())
        all_headers.update(self.CXX_STDLIB.keys())
        
        prefix_lower = prefix.lower()
        return sorted([h for h in all_headers if h.lower().startswith(prefix_lower)])
    
    def get_code_snippet(self, snippet_name: str) -> Optional[str]:
        """
        Get a code snippet.
        
        Args:
            snippet_name: Name of the snippet
            
        Returns:
            Code snippet string or None
        """
        return self.COMMON_PATTERNS.get(snippet_name)
    
    def get_function_signature(self, func_name: str) -> Optional[str]:
        """
        Get function signature/parameters.
        
        Args:
            func_name: Function name
            
        Returns:
            Function signature or None
        """
        signatures = {
            # C stdlib
            "printf": 'printf(const char* format, ...)',
            "scanf": 'scanf(const char* format, ...)',
            "malloc": 'malloc(size_t size)',
            "free": 'free(void* ptr)',
            "strlen": 'strlen(const char* s)',
            "strcpy": 'strcpy(char* dest, const char* src)',
            "strcat": 'strcat(char* dest, const char* src)',
            
            # C++ iostream
            "std::cout": 'operator<<(ostream& cout, const T& value)',
            "std::cin": 'operator>>(istream& cin, T& value)',
            "std::getline": 'std::getline(istream& is, string& str)',
            
            # STL algorithms
            "std::sort": 'std::sort(first, last[, cmp])',
            "std::find": 'std::find(first, last, value)',
            "std::copy": 'std::copy(first, last, d_first)',
        }
        return signatures.get(func_name)


# Global C++ provider instance
_cpp_provider = None


def get_cpp_provider(cpp_standard: CppStandard = CppStandard.CXX17) -> CppCompletionProvider:
    """Get or create global C++ completion provider."""
    global _cpp_provider
    if _cpp_provider is None:
        _cpp_provider = CppCompletionProvider(cpp_standard)
    return _cpp_provider


def get_cpp_completions(prefix: str, context: str = "") -> List[Tuple[str, str]]:
    """
    Convenience function to get C++ completions.
    
    Args:
        prefix: Completion prefix
        context: Additional context
        
    Returns:
        List of (completion, description) tuples
    """
    provider = get_cpp_provider()
    return provider.get_completions_for_prefix(prefix, context)


def get_cpp_members(type_name: str) -> List[Tuple[str, str]]:
    """
    Convenience function to get C++ type members.
    
    Args:
        type_name: Type name
        
    Returns:
        List of (member_name, description) tuples
    """
    provider = get_cpp_provider()
    return provider.get_member_completions(type_name)


# ═══════════════════════════════════════════════════════════════════════════
# PART 5: CCLS Integration (ccls_client)
# ═══════════════════════════════════════════════════════════════════════════

class CclsConnectionStatus(Enum):
    """CCLS connection status."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


class LspMessage:
    """Represents an LSP message."""
    
    def __init__(self, method: str, params: Optional[Dict] = None, msg_id: Optional[int] = None, result: Optional[Any] = None):
        self.method = method
        self.params = params or {}
        self.id = msg_id
        self.result = result
    
    def to_json_rpc(self) -> str:
        """Convert to JSON-RPC format."""
        message = {
            "jsonrpc": "2.0",
            "method": self.method,
        }
        if self.id is not None:
            message["id"] = self.id
        if self.params:
            message["params"] = self.params
        
        content = json.dumps(message)
        return f"Content-Length: {len(content)}\r\n\r\n{content}"


class CclsClient:
    """Client for CCLS Language Server."""
    
    def __init__(self, ccls_path: str = "ccls", project_root: str = "."):
        """
        Initialize CCLS client.
        
        Args:
            ccls_path: Path to CCLS executable (default: "ccls" - uses system PATH)
            project_root: Root directory of the C/C++ project
        """
        self.ccls_path = ccls_path
        self.project_root = project_root
        self.status = CclsConnectionStatus.DISCONNECTED
        
        self.process: Optional[subprocess.Popen] = None
        self.msg_id = 0
        self.pending_requests: Dict[int, queue.Queue] = {}
        self.response_thread: Optional[threading.Thread] = None
        
        self.initialized = False
        self.capabilities: Dict[str, Any] = {}
        
        # Callbacks for notifications
        self.notification_handlers: Dict[str, Callable] = {}
    
    def start(self) -> bool:
        """
        Start the CCLS process.
        
        Returns:
            True if started successfully, False otherwise
        """
        if self.status != CclsConnectionStatus.DISCONNECTED:
            logger.warning(f"CCLS already in state: {self.status.value}")
            return False
        
        try:
            self.status = CclsConnectionStatus.CONNECTING
            logger.info(f"Starting CCLS from: {self.ccls_path}")
            
            self.process = subprocess.Popen(
                [self.ccls_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            
            # Start response reading thread
            self.response_thread = threading.Thread(target=self._read_responses, daemon=True)
            self.response_thread.start()
            
            # Initialize
            if self.initialize():
                self.status = CclsConnectionStatus.CONNECTED
                logger.info("CCLS connected and initialized")
                return True
            else:
                self.stop()
                return False
        
        except Exception as e:
            logger.error(f"Failed to start CCLS: {e}")
            self.status = CclsConnectionStatus.ERROR
            return False
    
    def stop(self) -> None:
        """Stop the CCLS process."""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except Exception as e:
                logger.error(f"Error stopping CCLS: {e}")
                try:
                    self.process.kill()
                except:
                    pass
            finally:
                self.process = None
        
        self.status = CclsConnectionStatus.DISCONNECTED
        logger.info("CCLS stopped")
    
    def initialize(self) -> bool:
        """Initialize CCLS with project info."""
        try:
            params = {
                "processId": None,
                "rootPath": str(Path(self.project_root).absolute()),
                "rootUri": f"file://{Path(self.project_root).absolute()}",
                "capabilities": {
                    "textDocument": {
                        "completion": {
                            "completionItem": {
                                "snippetSupport": True,
                                "resolveSupport": {
                                    "properties": ["documentation", "detail"]
                                }
                            }
                        },
                        "definition": {},
                        "references": {},
                        "hover": {}
                    }
                }
            }
            
            response = self.send_request("initialize", params)
            
            if response and "result" in response:
                self.initialized = True
                self.capabilities = response["result"].get("capabilities", {})
                logger.info("CCLS initialized successfully")
                return True
            
            return False
        
        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            return False
    
    def send_request(self, method: str, params: Dict[str, Any], timeout: float = 5.0) -> Optional[Dict]:
        """
        Send a request and wait for response.
        
        Args:
            method: LSP method name
            params: Method parameters
            timeout: Response timeout in seconds
            
        Returns:
            Response dict or None if timeout
        """
        if self.status != CclsConnectionStatus.CONNECTED:
            logger.warning(f"CCLS not connected: {self.status.value}")
            return None
        
        try:
            self.msg_id += 1
            msg_id = self.msg_id
            
            # Create queue for response
            response_queue: queue.Queue = queue.Queue()
            self.pending_requests[msg_id] = response_queue
            
            # Send message
            message = LspMessage(method, params, msg_id)
            self.process.stdin.write(message.to_json_rpc())
            self.process.stdin.flush()
            
            # Wait for response
            try:
                response = response_queue.get(timeout=timeout)
                return response
            except queue.Empty:
                logger.warning(f"Request {method} timed out")
                return None
        
        except Exception as e:
            logger.error(f"Error sending request: {e}")
            return None
        
        finally:
            self.pending_requests.pop(msg_id, None)
    
    def send_notification(self, method: str, params: Dict[str, Any]) -> None:
        """Send a notification (no response expected)."""
        if self.status != CclsConnectionStatus.CONNECTED:
            return
        
        try:
            message = LspMessage(method, params)
            self.process.stdin.write(message.to_json_rpc())
            self.process.stdin.flush()
        
        except Exception as e:
            logger.error(f"Error sending notification: {e}")
    
    def _read_responses(self) -> None:
        """Read responses from CCLS process."""
        try:
            while self.process and self.process.stdout:
                # Read headers
                headers = {}
                while True:
                    line = self.process.stdout.readline()
                    if not line:
                        return
                    
                    line = line.rstrip('\r\n')
                    if not line:
                        break
                    
                    if ':' in line:
                        key, value = line.split(':', 1)
                        headers[key.strip()] = value.strip()
                
                # Read content
                content_length = int(headers.get('Content-Length', 0))
                if content_length == 0:
                    continue
                
                content = self.process.stdout.read(content_length)
                if not content:
                    return
                
                # Parse JSON
                try:
                    message = json.loads(content)
                    self._handle_message(message)
                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error: {e}")
        
        except Exception as e:
            logger.error(f"Error in response reader: {e}")
        
        finally:
            self.status = CclsConnectionStatus.DISCONNECTED
    
    def _handle_message(self, message: Dict) -> None:
        """Handle incoming message from CCLS."""
        if "id" in message and message["id"] in self.pending_requests:
            # Response to our request
            self.pending_requests[message["id"]].put(message)
        
        elif "method" in message:
            # Notification from server
            method = message["method"]
            params = message.get("params", {})
            
            if method in self.notification_handlers:
                try:
                    self.notification_handlers[method](params)
                except Exception as e:
                    logger.error(f"Error handling notification {method}: {e}")
    
    def register_notification_handler(self, method: str, handler: Callable) -> None:
        """Register a handler for server notifications."""
        self.notification_handlers[method] = handler
    
    def get_completions(self, file_path: str, line: int, character: int) -> List[Dict[str, Any]]:
        """
        Get code completions at position.
        
        Args:
            file_path: Path to file
            line: Line number (0-indexed)
            character: Character position (0-indexed)
            
        Returns:
            List of completion items
        """
        params = {
            "textDocument": {"uri": self._path_to_uri(file_path)},
            "position": {"line": line, "character": character}
        }
        
        response = self.send_request("textDocument/completion", params)
        
        if response and "result" in response:
            items = response["result"]
            if isinstance(items, dict):
                items = items.get("items", [])
            return items or []
        
        return []
    
    def get_definition(self, file_path: str, line: int, character: int) -> Optional[Dict[str, Any]]:
        """
        Get definition location.
        
        Args:
            file_path: Path to file
            line: Line number (0-indexed)
            character: Character position (0-indexed)
            
        Returns:
            Location dict or None
        """
        params = {
            "textDocument": {"uri": self._path_to_uri(file_path)},
            "position": {"line": line, "character": character}
        }
        
        response = self.send_request("textDocument/definition", params)
        
        if response and "result" in response:
            result = response["result"]
            if isinstance(result, list) and result:
                return result[0]
            return result
        
        return None
    
    def get_hover_info(self, file_path: str, line: int, character: int) -> Optional[str]:
        """
        Get hover information.
        
        Args:
            file_path: Path to file
            line: Line number (0-indexed)
            character: Character position (0-indexed)
            
        Returns:
            Hover content or None
        """
        params = {
            "textDocument": {"uri": self._path_to_uri(file_path)},
            "position": {"line": line, "character": character}
        }
        
        response = self.send_request("textDocument/hover", params)
        
        if response and "result" in response:
            result = response["result"]
            if result:
                content = result.get("contents", "")
                if isinstance(content, dict):
                    content = content.get("value", "")
                return content
        
        return None
    
    def open_document(self, file_path: str, content: str) -> None:
        """Notify CCLS that a document was opened."""
        params = {
            "textDocument": {
                "uri": self._path_to_uri(file_path),
                "languageId": self._get_language_id(file_path),
                "version": 1,
                "text": content
            }
        }
        self.send_notification("textDocument/didOpen", params)
    
    def change_document(self, file_path: str, changes: List[Dict]) -> None:
        """Notify CCLS of document changes."""
        params = {
            "textDocument": {"uri": self._path_to_uri(file_path), "version": 2},
            "contentChanges": changes
        }
        self.send_notification("textDocument/didChange", params)
    
    def close_document(self, file_path: str) -> None:
        """Notify CCLS that a document was closed."""
        params = {
            "textDocument": {"uri": self._path_to_uri(file_path)}
        }
        self.send_notification("textDocument/didClose", params)
    
    @staticmethod
    def _path_to_uri(file_path: str) -> str:
        """Convert file path to file URI."""
        path = Path(file_path).absolute()
        return f"file://{path}"
    
    @staticmethod
    def _get_language_id(file_path: str) -> str:
        """Get language ID from file extension."""
        ext = Path(file_path).suffix.lower()
        mapping = {
            '.c': 'c',
            '.h': 'c',
            '.cpp': 'cpp',
            '.cc': 'cpp',
            '.cxx': 'cpp',
            '.hpp': 'cpp',
            '.hh': 'cpp',
            '.m': 'objective-c',
            '.mm': 'objective-cpp',
        }
        return mapping.get(ext, 'cpp')


# Global CCLS client instance
_ccls_client: Optional[CclsClient] = None


def get_ccls_client(ccls_path: str = "ccls", project_root: str = ".") -> CclsClient:
    """Get or create global CCLS client."""
    global _ccls_client
    if _ccls_client is None:
        _ccls_client = CclsClient(ccls_path, project_root)
    return _ccls_client


def start_ccls(ccls_path: str = "ccls", project_root: str = ".") -> bool:
    """Start CCLS server."""
    client = get_ccls_client(ccls_path, project_root)
    return client.start()


def stop_ccls() -> None:
    """Stop CCLS server."""
    global _ccls_client
    if _ccls_client:
        _ccls_client.stop()
        _ccls_client = None


def get_ccls_completions(file_path: str, line: int, character: int) -> List[Dict[str, Any]]:
    """Get completions from CCLS."""
    client = get_ccls_client()
    if client.status == CclsConnectionStatus.CONNECTED:
        return client.get_completions(file_path, line, character)
    return []


def get_ccls_definition(file_path: str, line: int, character: int) -> Optional[Dict[str, Any]]:
    """Get definition from CCLS."""
    client = get_ccls_client()
    if client.status == CclsConnectionStatus.CONNECTED:
        return client.get_definition(file_path, line, character)
    return None


def get_ccls_hover(file_path: str, line: int, character: int) -> Optional[str]:
    """Get hover info from CCLS."""
    client = get_ccls_client()
    if client.status == CclsConnectionStatus.CONNECTED:
        return client.get_hover_info(file_path, line, character)
    return None


if __name__ == "__main__":
    lsp_main()
