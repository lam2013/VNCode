"""
Extension Type System for VNCode IDE.
Defines and manages different types of extensions with their specific handling.

EXTENSION METADATA FIELDS BY TYPE:

CODE_RUNNER Extension:
    Required fields:
    - type: "code-runner"
    - languages: List[str] - ["python", "c", "cpp", ...]
    - run_command: str - Command to execute code, e.g., "python {file}"
    
    Optional fields:
    - compile_command: str - For compiled languages, e.g., "gcc {file} -o {out}"
    - timeout: int - Timeout in seconds

LSP Extension:
    Required fields:
    - type: "lsp"
    - language: str - Target language, e.g., "python"
    - server_type: str - "tcp", "stdio", or "ws"
    
    Optional fields:
    - server_command: str - LSP server executable or node path
    - port: int - For TCP connections
    - debug: bool - Enable debug logging

LANGUAGE Extension:
    Required fields:
    - type: "language"
    - language_id: str - Unique language identifier
    - extensions: List[str] - File extensions, e.g., [".go", ".rs"]
    
    Optional fields:
    - grammar_path: str - Path to grammar file

SYNTAX_HIGHLIGHTER Extension:
    Required fields:
    - type: "syntax-highlighter"
    - languages: List[str] - Supported languages
    - theme_path: str - Path to highlight theme file
    
    Optional fields:
    - version: str - Theme version
"""

from enum import Enum
from typing import Dict, List, Optional
import json
import logging

logger = logging.getLogger('vncode')


class ExtensionType(Enum):
    """Supported extension types in VNCode."""
    CODE_RUNNER = "code-runner"  # Executes code (e.g., Code Runner)
    LSP = "lsp"  # Language Server Protocol (Python, C/C++, etc.)
    LANGUAGE = "language"  # Adds new language support
    SYNTAX_HIGHLIGHTER = "syntax-highlighter"  # Syntax highlighting only
    THEME = "theme"  # UI themes
    SNIPPET = "snippet"  # Code snippets
    FORMATTER = "formatter"  # Code formatting
    LINTER = "linter"  # Code linting
    DEBUGGER = "debugger"  # Debugging support
    TOOL = "tool"  # General tools/utilities


# Map from extension keywords/tags to types
TYPE_KEYWORDS = {
    ExtensionType.CODE_RUNNER: [
        "code runner", "code-runner", "run code", "executor",
        "runner", "execute", "execution"
    ],
    ExtensionType.LSP: [
        "lsp", "language server", "language-server",
        "intellisense", "autocomplete", "completion"
    ],
    ExtensionType.LANGUAGE: [
        "language", "support", "grammar", 
        "syntax", "programming"
    ],
    ExtensionType.SYNTAX_HIGHLIGHTER: [
        "syntax", "highlighting", "highlight", "syntax-highlighting"
    ],
    ExtensionType.THEME: [
        "theme", "color", "color-theme"
    ],
    ExtensionType.SNIPPET: [
        "snippet", "snippets"
    ],
    ExtensionType.FORMATTER: [
        "formatter", "format", "formatting", "prettier", "autopep8"
    ],
    ExtensionType.LINTER: [
        "linter", "lint", "analysis", "eslint", "pylint", "flake8"
    ],
    ExtensionType.DEBUGGER: [
        "debugger", "debug", "debugging"
    ],
    ExtensionType.TOOL: [
        "tool", "utility", "utilities", "extension pack"
    ]
}

# Common extension patterns
KNOWN_EXTENSIONS = {
    # Code Runners
    "frappucino.rst-exec": ExtensionType.CODE_RUNNER,
    "formulahendry.code-runner": ExtensionType.CODE_RUNNER,
    "ms-python.python": ExtensionType.LSP,  # Python LSP
    
    # LSP Extensions
    "ms-vscode.cpptools": ExtensionType.LSP,
    "ms-python.python": ExtensionType.LSP,
    "golang.go": ExtensionType.LSP,
    "rust-lang.rust-analyzer": ExtensionType.LSP,
    "vuejs.vetur": ExtensionType.LSP,
    "ms-vscode.vscode-typescript-next": ExtensionType.LSP,
    
    # Language Support
    "dotjoshjohnson.xml": ExtensionType.LANGUAGE,
    "ms-vscode.makefile-tools": ExtensionType.LANGUAGE,
    
    # Themes
    "dracula-theme.theme-dracula": ExtensionType.THEME,
    "zhuangtongfa.material-theme": ExtensionType.THEME,
    "github-github-theme.github-theme": ExtensionType.THEME,
    
    # Formatters
    "esbenp.prettier-vscode": ExtensionType.FORMATTER,
    "ms-python.black-formatter": ExtensionType.FORMATTER,
    
    # Linters
    "dbaeumer.vscode-eslint": ExtensionType.LINTER,
    "ms-python.pylint": ExtensionType.LINTER,
}

# Type descriptions for UI
TYPE_DESCRIPTIONS = {
    ExtensionType.CODE_RUNNER: "Run code directly in the editor",
    ExtensionType.LSP: "Language Server Protocol support with IntelliSense, autocomplete, and diagnostics",
    ExtensionType.LANGUAGE: "Support for additional programming languages",
    ExtensionType.SYNTAX_HIGHLIGHTER: "Syntax highlighting for code",
    ExtensionType.THEME: "IDE theme and color schemes",
    ExtensionType.SNIPPET: "Code snippets and templates",
    ExtensionType.FORMATTER: "Code formatting and beautification",
    ExtensionType.LINTER: "Code analysis and linting",
    ExtensionType.DEBUGGER: "Debugging support and tools",
    ExtensionType.TOOL: "General tools and utilities",
}

# Type colors for UI display
TYPE_COLORS = {
    ExtensionType.CODE_RUNNER: "#4CAF50",  # Green
    ExtensionType.LSP: "#2196F3",  # Blue
    ExtensionType.LANGUAGE: "#FF9800",  # Orange
    ExtensionType.SYNTAX_HIGHLIGHTER: "#9C27B0",  # Purple
    ExtensionType.THEME: "#E91E63",  # Pink
    ExtensionType.SNIPPET: "#00BCD4",  # Cyan
    ExtensionType.FORMATTER: "#8BC34A",  # Light Green
    ExtensionType.LINTER: "#FFC107",  # Amber
    ExtensionType.DEBUGGER: "#FF5722",  # Deep Orange
    ExtensionType.TOOL: "#607D8B",  # Blue Grey
}


def detect_extension_type(ext_info: dict) -> Optional[ExtensionType]:
    """
    Detect extension type from metadata.
    Returns ExtensionType or None if cannot be determined.
    """
    ext_id = f"{ext_info.get('namespace', '')}.{ext_info.get('name', '')}"
    
    # Check known extensions first
    if ext_id in KNOWN_EXTENSIONS:
        return KNOWN_EXTENSIONS[ext_id]
    
    # Check display name and description
    display_name = (ext_info.get('displayName') or '').lower()
    description = (ext_info.get('description') or '').lower()
    keywords = (ext_info.get('keywords') or '').lower()
    
    combined_text = f"{display_name} {description} {keywords}"
    
    # Score each type based on keyword matches
    scores = {}
    for ext_type, keywords_list in TYPE_KEYWORDS.items():
        score = sum(1 for kw in keywords_list if kw in combined_text)
        if score > 0:
            scores[ext_type] = score
    
    # Return the type with highest score
    if scores:
        return max(scores, key=scores.get)
    
    # Default to TOOL if no match
    return ExtensionType.TOOL


def get_type_display_name(ext_type: ExtensionType) -> str:
    """Get human-readable display name for extension type."""
    return ext_type.value.replace('-', ' ').title()


def get_type_description(ext_type: ExtensionType) -> str:
    """Get description for extension type."""
    return TYPE_DESCRIPTIONS.get(ext_type, "")


def get_type_color(ext_type: ExtensionType) -> str:
    """Get color for extension type badge."""
    return TYPE_COLORS.get(ext_type, "#999999")


class ExtensionTypeManager:
    """Manages extension types and their initialization."""
    
    def __init__(self):
        self.type_handlers = {}
        self._register_default_handlers()
    
    def _register_default_handlers(self):
        """Register default handlers for each type."""
        # Handlers are callables that take (extension_metadata, main_app)
        # They initialize and activate the extension
        
        self.type_handlers[ExtensionType.LSP] = self._handle_lsp_extension
        self.type_handlers[ExtensionType.CODE_RUNNER] = self._handle_code_runner
        self.type_handlers[ExtensionType.THEME] = self._handle_theme
        self.type_handlers[ExtensionType.SNIPPET] = self._handle_snippet
        self.type_handlers[ExtensionType.LANGUAGE] = self._handle_language
        self.type_handlers[ExtensionType.SYNTAX_HIGHLIGHTER] = self._handle_syntax_highlighter
        self.type_handlers[ExtensionType.FORMATTER] = self._handle_formatter
        self.type_handlers[ExtensionType.LINTER] = self._handle_linter
        self.type_handlers[ExtensionType.DEBUGGER] = self._handle_debugger
        self.type_handlers[ExtensionType.TOOL] = self._handle_tool
    
    def _handle_lsp_extension(self, metadata: dict, main_app=None):
        """Initialize LSP extension."""
        logger.info(f"Initializing LSP extension: {metadata.get('displayName')}")
        # This will be called by extension_manager when LSP extension is loaded
        # LSP extensions need to be started as language servers
        return True
    
    def _handle_code_runner(self, metadata: dict, main_app=None):
        """Initialize Code Runner extension."""
        logger.info(f"Initializing Code Runner extension: {metadata.get('displayName')}")
        # Register code runner in the main app
        if main_app and hasattr(main_app, 'register_code_runner'):
            main_app.register_code_runner(metadata)
        return True
    
    def _handle_theme(self, metadata: dict, main_app=None):
        """Initialize Theme extension."""
        logger.info(f"Initializing Theme: {metadata.get('displayName')}")
        # Theme contributions are handled separately
        return True
    
    def _handle_snippet(self, metadata: dict, main_app=None):
        """Initialize Snippet extension."""
        logger.info(f"Initializing Snippet extension: {metadata.get('displayName')}")
        # Snippets are loaded from contributions
        return True
    
    def _handle_language(self, metadata: dict, main_app=None):
        """Initialize Language Support extension."""
        logger.info(f"Initializing Language extension: {metadata.get('displayName')}")
        # Load grammar and language support
        return True
    
    def _handle_syntax_highlighter(self, metadata: dict, main_app=None):
        """Initialize Syntax Highlighter extension."""
        logger.info(f"Initializing Syntax Highlighter: {metadata.get('displayName')}")
        # This typically comes with language extensions
        return True
    
    def _handle_formatter(self, metadata: dict, main_app=None):
        """Initialize Formatter extension."""
        logger.info(f"Initializing Formatter: {metadata.get('displayName')}")
        # Register formatter in main app
        if main_app and hasattr(main_app, 'register_formatter'):
            main_app.register_formatter(metadata)
        return True
    
    def _handle_linter(self, metadata: dict, main_app=None):
        """Initialize Linter extension."""
        logger.info(f"Initializing Linter: {metadata.get('displayName')}")
        # Register linter in main app
        if main_app and hasattr(main_app, 'register_linter'):
            main_app.register_linter(metadata)
        return True
    
    def _handle_debugger(self, metadata: dict, main_app=None):
        """Initialize Debugger extension."""
        logger.info(f"Initializing Debugger: {metadata.get('displayName')}")
        # Register debugger in main app
        if main_app and hasattr(main_app, 'register_debugger'):
            main_app.register_debugger(metadata)
        return True
    
    def _handle_tool(self, metadata: dict, main_app=None):
        """Initialize Tool extension."""
        logger.info(f"Initializing Tool: {metadata.get('displayName')}")
        # General tool initialization
        return True
    
    def initialize_extension(self, ext_type: ExtensionType, metadata: dict, main_app=None) -> bool:
        """Initialize an extension based on its type."""
        handler = self.type_handlers.get(ext_type)
        if handler:
            try:
                return handler(metadata, main_app)
            except Exception as e:
                logger.error(f"Failed to initialize {ext_type.value} extension: {e}")
                return False
        logger.warning(f"No handler for extension type: {ext_type.value}")
        return False


# Global instance
_type_manager = None


def get_type_manager() -> ExtensionTypeManager:
    """Get or create global ExtensionTypeManager instance."""
    global _type_manager
    if _type_manager is None:
        _type_manager = ExtensionTypeManager()
    return _type_manager
