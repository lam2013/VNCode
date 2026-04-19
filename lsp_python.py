#!/usr/bin/env python3
"""
Simple Python LSP Server - Provides Python syntax suggestions only
Communicates via stdin/stdout using JSON-RPC protocol
"""

import json
import sys
import re
from typing import Any, Dict, List, Optional

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


def main():
    server = PythonLSPServer()
    server.run()


if __name__ == "__main__":
    main()
