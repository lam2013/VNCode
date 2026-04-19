"""
Extension Integration Helpers for VNCode IDE.
Provides functions to integrate extension hooks into editor features.
"""

import logging
from typing import List, Tuple, Optional

logger = logging.getLogger('vncode')


def get_lsp_aware_suggestions(language: str, prefix: str = "", extension_hooks=None, text: str = "", line: int = 0, character: int = 0) -> List[str]:
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
                    from extension_manager import load_snippets, get_snippet_completions
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
    import os
    import json
    
    if not os.path.exists(grammar_path):
        logger.warning(f"Grammar file not found: {grammar_path}")
        return None
    
    try:
        if grammar_path.endswith('.json'):
            with open(grammar_path, 'r', encoding='utf-8') as f:
                # Remove comments
                import re
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
        import re
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
    import re
    
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
        import re
        from PyQt5.QtGui import QColor, QTextCharFormat, QFont
        
        # Get keywords from LSP contributions if available
        contributions = lsp_ext.get("contributions", {})
        
        # For now, just log that LSP is being used
        # In future: could parse LSP server capabilities from extension
        logger.info(f"Detected LSP extension for {lang}: {lsp_ext.get('displayName')}")
        
        return True
    
    except Exception as e:
        logger.error(f"Failed to apply LSP keywords: {e}")
        return False


class PythonLSPProvider:
    """Direct Python LSP suggestions provider (no subprocess)"""
    
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
    
    PYTHON_MODULES = [
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
        "contextlib", "abc", "atexit", "traceback", "site"
    ]
    
    @staticmethod
    def get_suggestions(text: str, line: int, character: int) -> list:
        """
        Get Python syntax suggestions.
        
        Args:
            text: Full document text
            line: Line number (0-based)
            character: Character position (0-based)
            
        Returns:
            List of suggestion strings
        """
        try:
            # Get the current line
            lines = text.split('\n')
            if line >= len(lines):
                return []
            
            current_line_text = lines[line]
            if character > len(current_line_text):
                character = len(current_line_text)
            
            # Extract the word being typed
            word_start = character
            while word_start > 0 and (current_line_text[word_start - 1].isalnum() or current_line_text[word_start - 1] == '_'):
                word_start -= 1
            
            word_being_typed = current_line_text[word_start:character]
            
            # If word is empty, return empty suggestions
            if not word_being_typed:
                return []
            
            # Collect all suggestions
            all_items = (
                PythonLSPProvider.PYTHON_KEYWORDS +
                PythonLSPProvider.PYTHON_BUILTINS +
                PythonLSPProvider.PYTHON_MODULES
            )
            
            # Filter suggestions - match from beginning of word
            suggestions = []
            seen = set()
            word_lower = word_being_typed.lower()
            
            for item in all_items:
                item_lower = item.lower()
                if item_lower.startswith(word_lower):
                    if item_lower not in seen:
                        suggestions.append(item)
                        seen.add(item_lower)
            
            # Sort by length and alphabetically
            suggestions.sort(key=lambda x: (len(x), x.lower()))
            
            return suggestions[:50]  # Limit to 50 suggestions
            
        except Exception as e:
            logger.debug(f"Error getting Python suggestions: {e}")
            return []


# Old subprocess-based client (kept for reference, no longer used)
class PythonLSPClient:
    """Legacy: Direct Python LSP suggestions provider (no subprocess)"""
    
    def __init__(self, lsp_script_path: str = None):
        """Initialize (legacy - now just uses PythonLSPProvider)"""
        self.initialized = True
    
    def get_completions(self, text: str, line: int, character: int) -> list:
        """Get completions using PythonLSPProvider"""
        return PythonLSPProvider.get_suggestions(text, line, character)
    
    def stop(self):
        """Stop (no-op for direct provider)"""
        pass


# Global LSP client instance (now using direct provider)
_python_lsp_client = None

def get_python_lsp_client() -> PythonLSPClient:
    """Get or create Python LSP client."""
    global _python_lsp_client
    if not _python_lsp_client:
        _python_lsp_client = PythonLSPClient()
    return _python_lsp_client


def get_python_lsp_suggestions(text: str, line: int, character: int) -> list:
    """
    Get Python syntax suggestions using direct provider.
    
    Args:
        text: Full document text
        line: Current line number
        character: Current character position
        
    Returns:
        List of suggestion strings
    """
    try:
        return PythonLSPProvider.get_suggestions(text, line, character)
    except Exception as e:
        logger.debug(f"Error getting Python LSP suggestions: {e}")
        return []


__all__ = [
    'get_lsp_aware_suggestions',
    'get_syntax_highlighter_for_language', 
    'load_textmate_grammar',
    'apply_textmate_grammar_to_highlighter',
    'apply_lsp_keywords_to_syntax',
    'PythonLSPClient',
    'get_python_lsp_client',
    'get_python_lsp_suggestions'
]
