"""
Core Module for VNCode IDE
Combines all core functionality:
- Extension Manager (extension_manager)
- Extension Type System (extension_types)
- Auto-Load Fragment (auto_load_fragment)
- Extension Hooks & Runtime System
- Undo/Redo System (undo_redo)
"""

import json
import os
import shutil
import zipfile
import logging
import re
from pathlib import Path
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple, Callable
from pathlib import Path
from copy import deepcopy

# Get logger
logger = logging.getLogger('vncode')

# Import API module for openvsx_api, C/C++, and C# LSP functions
try:
    import api as api_module
    HAS_CPP_LSP = True
    HAS_CCLS = True
    HAS_CSHARP_LSP = hasattr(api_module, "CSharpLspClient") if api_module else False
except ImportError:
    api_module = None
    HAS_CPP_LSP = False
    HAS_CCLS = False
    HAS_CSHARP_LSP = False


# ═══════════════════════════════════════════════════════════════════════════
# PART 0: Undo/Redo System
# ═══════════════════════════════════════════════════════════════════════════

class UndoRedoAction:
    """Represents a single action that can be undone/redone."""
    
    def __init__(self, name: str, undo_func: Callable, redo_func: Callable, data: Any = None):
        """
        Initialize an UndoRedoAction.
        
        Args:
            name: Description of the action (e.g., "Delete text", "Insert line")
            undo_func: Callable that undoes this action (takes data as argument)
            redo_func: Callable that redoes this action (takes data as argument)
            data: Any data needed to undo/redo this action
        """
        self.name = name
        self.undo_func = undo_func
        self.redo_func = redo_func
        self.data = deepcopy(data) if data is not None else None
    
    def undo(self):
        """Execute the undo action."""
        try:
            self.undo_func(self.data)
            return True
        except Exception as e:
            logger.error(f"Undo failed for '{self.name}': {e}")
            return False
    
    def redo(self):
        """Execute the redo action."""
        try:
            self.redo_func(self.data)
            return True
        except Exception as e:
            logger.error(f"Redo failed for '{self.name}': {e}")
            return False


class UndoRedoManager:
    """Manages undo/redo stack for editor operations."""
    
    def __init__(self, max_history: int = 100):
        """
        Initialize the UndoRedoManager.
        
        Args:
            max_history: Maximum number of actions to keep in history (default 100)
        """
        self.undo_stack: List[UndoRedoAction] = []
        self.redo_stack: List[UndoRedoAction] = []
        self.max_history = max_history
    
    def add_action(self, action: UndoRedoAction) -> None:
        """
        Add an action to the undo stack.
        Clears the redo stack when a new action is added.
        
        Args:
            action: UndoRedoAction to add
        """
        self.undo_stack.append(action)
        
        # Clear redo stack when new action is performed
        self.redo_stack.clear()
        
        # Limit history size
        if len(self.undo_stack) > self.max_history:
            self.undo_stack.pop(0)
        
        logger.debug(f"Added action: {action.name} (History: {len(self.undo_stack)})")
    
    def undo(self) -> bool:
        """
        Undo the last action.
        
        Returns:
            True if undo was successful, False otherwise
        """
        if not self.can_undo():
            logger.debug("Nothing to undo")
            return False
        
        action = self.undo_stack.pop()
        if action.undo():
            self.redo_stack.append(action)
            logger.info(f"Undone: {action.name}")
            return True
        else:
            # If undo failed, put action back
            self.undo_stack.append(action)
            return False
    
    def redo(self) -> bool:
        """
        Redo the last undone action.
        
        Returns:
            True if redo was successful, False otherwise
        """
        if not self.can_redo():
            logger.debug("Nothing to redo")
            return False
        
        action = self.redo_stack.pop()
        if action.redo():
            self.undo_stack.append(action)
            logger.info(f"Redone: {action.name}")
            return True
        else:
            # If redo failed, put action back
            self.redo_stack.append(action)
            return False
    
    def can_undo(self) -> bool:
        """Check if there are actions to undo."""
        return len(self.undo_stack) > 0
    
    def can_redo(self) -> bool:
        """Check if there are actions to redo."""
        return len(self.redo_stack) > 0
    
    def get_undo_action_name(self) -> Optional[str]:
        """Get the name of the action that would be undone."""
        if self.can_undo():
            return self.undo_stack[-1].name
        return None
    
    def get_redo_action_name(self) -> Optional[str]:
        """Get the name of the action that would be redone."""
        if self.can_redo():
            return self.redo_stack[-1].name
        return None
    
    def get_undo_stack_size(self) -> int:
        """Get the number of actions in undo stack."""
        return len(self.undo_stack)
    
    def get_redo_stack_size(self) -> int:
        """Get the number of actions in redo stack."""
        return len(self.redo_stack)
    
    def clear(self) -> None:
        """Clear both undo and redo stacks."""
        self.undo_stack.clear()
        self.redo_stack.clear()
        logger.debug("Undo/Redo history cleared")
    
    def get_history_info(self) -> Dict[str, Any]:
        """Get information about current undo/redo history."""
        return {
            "undo_count": len(self.undo_stack),
            "redo_count": len(self.redo_stack),
            "can_undo": self.can_undo(),
            "can_redo": self.can_redo(),
            "undo_action": self.get_undo_action_name(),
            "redo_action": self.get_redo_action_name(),
            "max_history": self.max_history,
        }


# Global undo/redo manager instance
_undo_redo_manager = None


def get_undo_redo_manager() -> UndoRedoManager:
    """Get or create global UndoRedoManager instance."""
    global _undo_redo_manager
    if _undo_redo_manager is None:
        _undo_redo_manager = UndoRedoManager()
    return _undo_redo_manager


def create_text_edit_action(old_text: str, new_text: str, position: int = 0) -> UndoRedoAction:
    """
    Create an UndoRedoAction for text editing (insert, delete, replace).
    
    Args:
        old_text: The original text before the change
        new_text: The new text after the change
        position: The position where the change occurred
        
    Returns:
        UndoRedoAction representing the text edit
    """
    def undo_edit(data):
        """Undo callback - replace with old text."""
        if hasattr(data, '_current_text'):
            data._current_text = old_text
    
    def redo_edit(data):
        """Redo callback - replace with new text."""
        if hasattr(data, '_current_text'):
            data._current_text = new_text
    
    action_name = f"Edit text at position {position}"
    return UndoRedoAction(action_name, undo_edit, redo_edit, {'old': old_text, 'new': new_text, 'pos': position})


def add_undo_action(name: str, undo_func: Callable, redo_func: Callable, data: Any = None) -> None:
    """
    Add an action to the global undo/redo manager.
    
    Args:
        name: Description of the action
        undo_func: Callable that undoes the action
        redo_func: Callable that redoes the action
        data: Any data needed for undo/redo
    """
    manager = get_undo_redo_manager()
    action = UndoRedoAction(name, undo_func, redo_func, data)
    manager.add_action(action)


def undo() -> bool:
    """Undo the last action."""
    manager = get_undo_redo_manager()
    return manager.undo()


def redo() -> bool:
    """Redo the last undone action."""
    manager = get_undo_redo_manager()
    return manager.redo()


def can_undo() -> bool:
    """Check if undo is available."""
    return get_undo_redo_manager().can_undo()


def can_redo() -> bool:
    """Check if redo is available."""
    return get_undo_redo_manager().can_redo()


# ═══════════════════════════════════════════════════════════════════════════
# PART 1: Extension Type System
# ═══════════════════════════════════════════════════════════════════════════

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
        "intellisense", "autocomplete", "completion",
        "c++", "c/c++", "cpp", "cpptools", "clangd", "clang",
        "cpp tools", "c++ language", "c++ lsp"
    ],
    ExtensionType.LANGUAGE: [
        "language", "support", "grammar", 
        "syntax", "programming", "c++", "c/c++", "cpp"
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
        "formatter", "format", "formatting", "prettier", "autopep8", "clangformat"
    ],
    ExtensionType.LINTER: [
        "linter", "lint", "analysis", "eslint", "pylint", "flake8", "clang-tidy"
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
    
    # LSP Extensions
    "ms-python.python": ExtensionType.LSP,  # Python LSP
    "ms-vscode.cpptools": ExtensionType.LSP,  # C/C++ LSP
    "ms-vscode.cpptools-extension-pack": ExtensionType.LSP,  # C/C++ Extension Pack
    "llvm-vs-code-extensions.vscode-clangd": ExtensionType.LSP,  # Clang-D for C/C++
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
        return True
    
    def _handle_code_runner(self, metadata: dict, main_app=None):
        """Initialize Code Runner extension."""
        logger.info(f"Initializing Code Runner extension: {metadata.get('displayName')}")
        if main_app and hasattr(main_app, 'register_code_runner'):
            main_app.register_code_runner(metadata)
        return True
    
    def _handle_theme(self, metadata: dict, main_app=None):
        """Initialize Theme extension."""
        logger.info(f"Initializing Theme: {metadata.get('displayName')}")
        return True
    
    def _handle_snippet(self, metadata: dict, main_app=None):
        """Initialize Snippet extension."""
        logger.info(f"Initializing Snippet extension: {metadata.get('displayName')}")
        return True
    
    def _handle_language(self, metadata: dict, main_app=None):
        """Initialize Language Support extension."""
        logger.info(f"Initializing Language extension: {metadata.get('displayName')}")
        return True
    
    def _handle_syntax_highlighter(self, metadata: dict, main_app=None):
        """Initialize Syntax Highlighter extension."""
        logger.info(f"Initializing Syntax Highlighter: {metadata.get('displayName')}")
        return True
    
    def _handle_formatter(self, metadata: dict, main_app=None):
        """Initialize Formatter extension."""
        logger.info(f"Initializing Formatter: {metadata.get('displayName')}")
        if main_app and hasattr(main_app, 'register_formatter'):
            main_app.register_formatter(metadata)
        return True
    
    def _handle_linter(self, metadata: dict, main_app=None):
        """Initialize Linter extension."""
        logger.info(f"Initializing Linter: {metadata.get('displayName')}")
        if main_app and hasattr(main_app, 'register_linter'):
            main_app.register_linter(metadata)
        return True
    
    def _handle_debugger(self, metadata: dict, main_app=None):
        """Initialize Debugger extension."""
        logger.info(f"Initializing Debugger: {metadata.get('displayName')}")
        if main_app and hasattr(main_app, 'register_debugger'):
            main_app.register_debugger(metadata)
        return True
    
    def _handle_tool(self, metadata: dict, main_app=None):
        """Initialize Tool extension."""
        logger.info(f"Initializing Tool: {metadata.get('displayName')}")
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


# ═══════════════════════════════════════════════════════════════════════════
# PART 2: Extension Manager
# ═══════════════════════════════════════════════════════════════════════════

def get_extensions_dir() -> Path:
    """Get extensions storage directory in %APPDATA%/VNCode/extensions/"""
    appdata = os.environ.get("APPDATA", "")
    if not appdata:
        appdata = str(Path.home() / "AppData" / "Roaming")
    ext_dir = Path(appdata) / "VNCode" / "extensions"
    ext_dir.mkdir(parents=True, exist_ok=True)
    return ext_dir


def get_cache_dir() -> Path:
    """Get icon cache directory."""
    appdata = os.environ.get("APPDATA", "")
    if not appdata:
        appdata = str(Path.home() / "AppData" / "Roaming")
    cache = Path(appdata) / "VNCode" / "cache" / "icons"
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def get_extension_id(namespace: str, name: str) -> str:
    """Generate extension ID: 'namespace.name'"""
    return f"{namespace}.{name}"


def get_extension_path(namespace: str, name: str) -> Path:
    """Get the install directory for an extension."""
    return get_extensions_dir() / get_extension_id(namespace, name)


def is_installed(namespace: str, name: str) -> bool:
    """Check if an extension is already installed."""
    ext_path = get_extension_path(namespace, name)
    return (ext_path / "metadata.json").exists()


def get_installed_version(namespace: str, name: str) -> Optional[str]:
    """Get the installed version of an extension, or None."""
    meta_path = get_extension_path(namespace, name) / "metadata.json"
    if meta_path.exists():
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("version")
        except Exception:
            pass
    return None


def list_installed() -> list:
    """List all installed extensions. Returns list of metadata dicts."""
    ext_dir = get_extensions_dir()
    installed = []
    if not ext_dir.exists():
        return installed

    for entry in ext_dir.iterdir():
        if entry.is_dir():
            meta_file = entry / "metadata.json"
            if meta_file.exists():
                try:
                    with open(meta_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        data["_install_path"] = str(entry)
                        installed.append(data)
                except Exception as e:
                    logger.error(f"Failed to read {meta_file}: {e}")
    return installed


def install_extension(ext_info: dict, progress_callback=None) -> bool:
    """
    Download and install an extension.
    ext_info should contain: namespace, name, version, files.download, displayName, description, etc.
    Returns True on success.
    """
    namespace = ext_info.get("namespace", "")
    name = ext_info.get("name", "")
    version = ext_info.get("version", "")
    download_url = ext_info.get("files", {}).get("download", "")

    if not all([namespace, name, download_url]):
        logger.error("Missing required extension info")
        return False

    ext_id = get_extension_id(namespace, name)
    ext_path = get_extension_path(namespace, name)

    # Clean previous install if exists
    if ext_path.exists():
        shutil.rmtree(ext_path, ignore_errors=True)

    ext_path.mkdir(parents=True, exist_ok=True)

    # Download .vsix
    vsix_path = ext_path / f"{ext_id}-{version}.vsix"
    logger.info(f"Downloading {ext_id} v{version}...")

    if not api_module or not api_module.download_file(download_url, str(vsix_path), progress_callback):
        shutil.rmtree(ext_path, ignore_errors=True)
        return False

    # Extract .vsix (it's a ZIP file)
    logger.info(f"Extracting {ext_id}...")
    try:
        extract_dir = ext_path / "extracted"
        with zipfile.ZipFile(str(vsix_path), "r") as zf:
            zf.extractall(str(extract_dir))
    except Exception as e:
        logger.error(f"Extract failed: {e}")
        shutil.rmtree(ext_path, ignore_errors=True)
        return False

    # Parse package.json from the extracted extension
    package_json = _find_package_json(extract_dir)
    contributions = {}
    if package_json:
        contributions = _parse_contributions(package_json, extract_dir)

    # Detect extension type
    ext_type = None
    ext_type_obj = detect_extension_type(ext_info)
    ext_type = ext_type_obj.value if ext_type_obj else None
    
    # Save metadata
    metadata = {
        "id": ext_id,
        "namespace": namespace,
        "name": name,
        "displayName": ext_info.get("displayName", name),
        "description": ext_info.get("description", ""),
        "version": version,
        "icon_url": ext_info.get("files", {}).get("icon", ""),
        "download_url": download_url,
        "contributions": contributions,
        "type": ext_type,
    }

    with open(ext_path / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    # Delete .vsix to save space (we already extracted it)
    try:
        vsix_path.unlink()
    except OSError:
        pass

    logger.info(f"Installed {ext_id} v{version} successfully!")
    return True


def uninstall_extension(namespace: str, name: str) -> bool:
    """Uninstall an extension by removing its directory."""
    ext_path = get_extension_path(namespace, name)
    if ext_path.exists():
        try:
            shutil.rmtree(ext_path)
            logger.info(f"Uninstalled {get_extension_id(namespace, name)}")
            return True
        except Exception as e:
            logger.error(f"Uninstall failed: {e}")
            return False
    return True


def _find_package_json(extract_dir: Path) -> Optional[dict]:
    """Find and parse package.json inside extracted .vsix."""
    candidates = [
        extract_dir / "extension" / "package.json",
        extract_dir / "package.json",
    ]
    for p in candidates:
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to parse {p}: {e}")
    
    # Search recursively as fallback
    for p in extract_dir.rglob("package.json"):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "contributes" in data or "name" in data:
                    return data
        except Exception:
            continue
    return None


def _parse_contributions(package_json: dict, extract_dir: Path) -> dict:
    """
    Parse the 'contributes' section of package.json.
    Extract useful contributions: themes, snippets, languages, grammars, commands, etc.
    """
    contributes = package_json.get("contributes", {})
    result = {}

    # --- Themes ---
    themes = contributes.get("themes", [])
    parsed_themes = []
    for theme in themes:
        label = theme.get("label", theme.get("id", "Unknown Theme"))
        theme_path = theme.get("path", "")
        ui_theme = theme.get("uiTheme", "vs-dark")

        if theme_path:
            abs_path = _resolve_extension_path(extract_dir, theme_path)
            if abs_path and abs_path.exists():
                parsed_themes.append({
                    "label": label,
                    "path": str(abs_path),
                    "uiTheme": ui_theme,
                })
    if parsed_themes:
        result["themes"] = parsed_themes

    # --- Snippets ---
    snippets = contributes.get("snippets", [])
    parsed_snippets = []
    for snippet in snippets:
        language = snippet.get("language", "")
        snippet_path = snippet.get("path", "")
        if snippet_path:
            abs_path = _resolve_extension_path(extract_dir, snippet_path)
            if abs_path and abs_path.exists():
                parsed_snippets.append({
                    "language": language,
                    "path": str(abs_path),
                })
    if parsed_snippets:
        result["snippets"] = parsed_snippets

    # --- Commands ---
    commands = contributes.get("commands", [])
    parsed_commands = []
    for cmd in commands:
        cmd_info = {
            "command": cmd.get("command", ""),
            "title": cmd.get("title", ""),
            "category": cmd.get("category", ""),
            "description": cmd.get("description", ""),
            "when": cmd.get("when", ""),
            "keybinding": cmd.get("keybinding", ""),
        }
        if cmd_info["command"]:
            parsed_commands.append(cmd_info)
    if parsed_commands:
        result["commands"] = parsed_commands

    # --- Languages ---
    languages = contributes.get("languages", [])
    parsed_langs = []
    for lang in languages:
        lang_info = {
            "id": lang.get("id", ""),
            "aliases": lang.get("aliases", []),
            "extensions": lang.get("extensions", []),
        }
        if lang_info["id"]:
            parsed_langs.append(lang_info)
    if parsed_langs:
        result["languages"] = parsed_langs

    # --- Grammars (TextMate) ---
    grammars = contributes.get("grammars", [])
    parsed_grammars = []
    for gram in grammars:
        scope = gram.get("scopeName", "")
        grammar_path = gram.get("path", "")
        language = gram.get("language", "")
        if grammar_path:
            abs_path = _resolve_extension_path(extract_dir, grammar_path)
            if abs_path and abs_path.exists():
                parsed_grammars.append({
                    "scopeName": scope,
                    "language": language,
                    "path": str(abs_path),
                })
    if parsed_grammars:
        result["grammars"] = parsed_grammars

    # --- Debuggers ---
    debuggers = contributes.get("debuggers", [])
    if debuggers:
        result["debuggers"] = debuggers

    # --- Keybindings ---
    keybindings = contributes.get("keybindings", [])
    if keybindings:
        result["keybindings"] = keybindings

    return result


def _resolve_extension_path(extract_dir: Path, relative_path: str) -> Optional[Path]:
    """Resolve a relative path from package.json to an absolute path."""
    candidates = [
        extract_dir / "extension" / relative_path.lstrip("./"),
        extract_dir / relative_path.lstrip("./"),
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


def load_theme(theme_path: str) -> Optional[dict]:
    """
    Load a VS Code color theme file (.json with comments support).
    Returns a dict with 'colors' and 'tokenColors'.
    """
    if not os.path.exists(theme_path):
        return None
    try:
        with open(theme_path, "r", encoding="utf-8") as f:
            content = f.read()
        content = re.sub(r'(?<!:)//.*?$', '', content, flags=re.MULTILINE)
        content = re.sub(r',\s*([}\]])', r'\1', content)
        return json.loads(content)
    except Exception as e:
        logger.error(f"Failed to load theme {theme_path}: {e}")
        return None


def load_snippets(snippet_path: str) -> Optional[dict]:
    """
    Load a VS Code snippets file.
    Returns dict of {name: {prefix, body, description}}.
    """
    if not os.path.exists(snippet_path):
        return None
    try:
        with open(snippet_path, "r", encoding="utf-8") as f:
            content = f.read()
        content = re.sub(r'(?<!:)//.*?$', '', content, flags=re.MULTILINE)
        content = re.sub(r',\s*([}\]])', r'\1', content)
        return json.loads(content)
    except Exception as e:
        logger.error(f"Failed to load snippets {snippet_path}: {e}")
        return None


def get_theme_colors(theme_data: dict) -> dict:
    """
    Extract editor colors from a VS Code theme.
    Returns a dict mapping VNCode style properties to colors.
    """
    if not theme_data:
        return {}

    colors = theme_data.get("colors", {})
    token_colors = theme_data.get("tokenColors", [])

    result = {
        "editor.background": colors.get("editor.background", ""),
        "editor.foreground": colors.get("editor.foreground", ""),
        "editor.selectionBackground": colors.get("editor.selectionBackground", ""),
        "editorLineNumber.foreground": colors.get("editorLineNumber.foreground", ""),
        "sideBar.background": colors.get("sideBar.background", ""),
        "statusBar.background": colors.get("statusBar.background", ""),
        "tab.activeBackground": colors.get("tab.activeBackground", ""),
        "tab.inactiveBackground": colors.get("tab.inactiveBackground", ""),
        "titleBar.activeBackground": colors.get("titleBar.activeBackground", ""),
        "menu.background": colors.get("activityBar.background", ""),
    }

    # Parse token colors for syntax highlighting
    syntax_colors = {}
    for tc in token_colors:
        scope = tc.get("scope", "")
        settings = tc.get("settings", {})
        fg = settings.get("foreground", "")

        if isinstance(scope, list):
            scopes = scope
        elif isinstance(scope, str):
            scopes = [s.strip() for s in scope.split(",")]
        else:
            continue

        for s in scopes:
            if fg:
                if "keyword" in s:
                    syntax_colors["keyword"] = fg
                elif "string" in s:
                    syntax_colors["string"] = fg
                elif "comment" in s:
                    syntax_colors["comment"] = fg
                elif "variable" in s or "identifier" in s:
                    syntax_colors["variable"] = fg
                elif "entity.name.function" in s:
                    syntax_colors["function"] = fg
                elif "entity.name.class" in s or "entity.name.type" in s:
                    syntax_colors["class"] = fg
                elif "constant.numeric" in s:
                    syntax_colors["number"] = fg
                elif "constant" in s:
                    syntax_colors["constant"] = fg

    result["syntax"] = syntax_colors
    return result


def get_snippet_completions(snippet_data: dict) -> list:
    """
    Convert VS Code snippet format to VNCode completion items.
    Returns list of (prefix, body_text, description).
    """
    if not snippet_data:
        return []

    completions = []
    for name, snippet in snippet_data.items():
        prefix = snippet.get("prefix", "")
        body = snippet.get("body", [])
        description = snippet.get("description", name)

        if isinstance(prefix, list):
            prefixes = prefix
        else:
            prefixes = [prefix] if prefix else []

        if isinstance(body, list):
            body_text = "\n".join(body)
        else:
            body_text = str(body)

        # Clean VS Code placeholders
        body_text = re.sub(r'\$\{\d+:([^}]*)\}', r'\1', body_text)
        body_text = re.sub(r'\$\{\d+\}', '', body_text)
        body_text = re.sub(r'\$\d+', '', body_text)

        for p in prefixes:
            if p:
                completions.append((p, body_text, description))

    return completions


def get_default_theme(metadata: dict) -> Optional[dict]:
    """
    Get the default (first) theme from an extension's metadata.
    
    Args:
        metadata: Extension metadata dict with contributions
        
    Returns:
        Theme info dict with 'label', 'path', 'uiTheme' if found, else None
    """
    contributions = metadata.get("contributions", {})
    themes = contributions.get("themes", [])
    
    if themes:
        return themes[0]
    return None


def get_default_theme_colors(metadata: dict) -> Optional[dict]:
    """
    Load and extract colors from the default theme of an extension.
    
    Args:
        metadata: Extension metadata dict
        
    Returns:
        Color dict from get_theme_colors(), or None if no theme/colors found
    """
    theme_info = get_default_theme(metadata)
    if not theme_info:
        return None
    
    theme_path = theme_info.get("path", "")
    if not theme_path:
        return None
    
    theme_data = load_theme(theme_path)
    if theme_data:
        return get_theme_colors(theme_data)
    return None


# ═══════════════════════════════════════════════════════════════════════════
# PART 3: Extension Auto-Load System
# ═══════════════════════════════════════════════════════════════════════════

def auto_load_extensions() -> list:
    """
    Return list of all installed extensions with their metadata.
    Perfect for auto-loading extensions on VNCode startup.
    
    Returns:
        List of extension metadata dicts, each containing:
        - id, namespace, name, displayName, description, version
        - contributions: themes, snippets, languages, grammars
        - _install_path: full directory path
    """
    return list_installed()


def initialize_extensions(extensions: list, main_app=None) -> dict:
    """
    Initialize extensions based on their type.
    
    Args:
        extensions: List of extension metadata dicts from auto_load_extensions()
        main_app: Reference to main VNCode app (optional, for type-specific init)
    
    Returns:
        Dict with initialization results
    """
    if not extensions:
        return {"initialized": 0, "failed": 0, "by_type": {}}
    
    results = {
        "initialized": 0,
        "failed": 0,
        "by_type": {}
    }
    
    type_manager = get_type_manager()
    
    for ext_metadata in extensions:
        try:
            ext_type_str = ext_metadata.get("type")
            if not ext_type_str:
                continue
            
            try:
                ext_type = ExtensionType(ext_type_str)
            except ValueError:
                logger.warning(f"Unknown extension type: {ext_type_str}")
                continue
            
            # Initialize the extension
            success = type_manager.initialize_extension(
                ext_type, 
                ext_metadata, 
                main_app
            )
            
            if success:
                results["initialized"] += 1
                type_name = ext_type_str
                results["by_type"][type_name] = results["by_type"].get(type_name, 0) + 1
                logger.info(f"Initialized {ext_type_str}: {ext_metadata.get('displayName')}")
            else:
                results["failed"] += 1
                logger.warning(f"Failed to initialize: {ext_metadata.get('displayName')}")
                
        except Exception as e:
            results["failed"] += 1
            logger.error(f"Extension init error: {e}")
    
    logger.info(f"Extension initialization summary: {results}")
    return results


# ═══════════════════════════════════════════════════════════════════════════
# PART 4: Extension Runtime Hook System
# ═══════════════════════════════════════════════════════════════════════════

class ExtensionHooks:
    """Manages extension hooks for Code Runner, LSP, and Syntax Highlighting."""
    
    def __init__(self):
        self.code_runner_extensions = []
        self.lsp_extensions = {}
        self.highlighter_extensions = {}
        self.completions_providers = []
    
    def register_code_runner(self, metadata: dict):
        """Register a code-runner extension."""
        self.code_runner_extensions.append(metadata)
        logger.info(f"Registered code runner: {metadata.get('displayName')}")
    
    def register_lsp_extension(self, language: str, metadata: dict):
        """Register an LSP extension for a specific language."""
        self.lsp_extensions[language] = metadata
        logger.info(f"Registered LSP for {language}: {metadata.get('displayName')}")
    
    def register_highlighter_extension(self, language: str, metadata: dict):
        """Register a syntax highlighter extension for a specific language."""
        self.highlighter_extensions[language] = metadata
        logger.info(f"Registered highlighter for {language}: {metadata.get('displayName')}")
    
    def register_completions_provider(self, provider_func):
        """Register a custom completions provider function."""
        self.completions_providers.append(provider_func)
        logger.info(f"Registered completions provider")
    
    def get_code_runner_extensions(self) -> list:
        """Get all registered code runner extensions."""
        return self.code_runner_extensions.copy()
    
    def get_lsp_for_language(self, language: str) -> Optional[dict]:
        """Get LSP extension for a specific language."""
        return self.lsp_extensions.get(language)
    
    def get_highlighter_for_language(self, language: str) -> Optional[dict]:
        """Get highlighter extension for a specific language."""
        return self.highlighter_extensions.get(language)
    
    def get_all_lsp_extensions(self) -> dict:
        """Get all registered LSP extensions."""
        return self.lsp_extensions.copy()
    
    def get_all_highlighter_extensions(self) -> dict:
        """Get all registered highlighter extensions."""
        return self.highlighter_extensions.copy()
    
    def get_completions_from_providers(self, prefix: str, language: str = "") -> list:
        """Get completions from all registered providers."""
        completions = []
        for provider in self.completions_providers:
            try:
                items = provider(prefix, language)
                if items:
                    completions.extend(items)
            except Exception as e:
                logger.error(f"Completions provider error: {e}")
        return completions


# Global hooks instance
_extension_hooks = None


def get_extension_hooks() -> ExtensionHooks:
    """Get or create global ExtensionHooks instance."""
    global _extension_hooks
    if _extension_hooks is None:
        _extension_hooks = ExtensionHooks()
    return _extension_hooks


def apply_extension_hooks(extensions: list):
    """
    Apply all extension hooks for code runners, LSP, and highlighters.
    Should be called after loading extensions.
    
    Args:
        extensions: List of extension metadata dicts from auto_load_extensions()
    """
    hooks = get_extension_hooks()
    
    for ext in extensions:
        ext_type = ext.get("type")
        if not ext_type:
            continue
        
        try:
            # Code Runner extension
            if ext_type == ExtensionType.CODE_RUNNER.value:
                hooks.register_code_runner(ext)
                
                # Extract completions from code runner if available
                contributions = ext.get("contributions", {})
                snippets_list = contributions.get("snippets", [])
                if snippets_list:
                    for snippet_info in snippets_list:
                        snippet_data = load_snippets(snippet_info.get("path", ""))
                        if snippet_data:
                            completions = get_snippet_completions(snippet_data)
                            hooks.register_completions_provider(
                                lambda p, l, c=completions: [comp for comp in c if comp[0].startswith(p)]
                            )
            
            # LSP extension
            elif ext_type == ExtensionType.LSP.value:
                contributions = ext.get("contributions", {})
                languages = contributions.get("languages", [])
                
                for lang_info in languages:
                    lang_id = lang_info.get("id", "")
                    if lang_id:
                        hooks.register_lsp_extension(lang_id, ext)
                        logger.info(f"LSP hook registered for {lang_id}")
            
            # Syntax Highlighter extension
            elif ext_type == ExtensionType.SYNTAX_HIGHLIGHTER.value or ext_type == "language":
                contributions = ext.get("contributions", {})
                languages = contributions.get("languages", [])
                grammars = contributions.get("grammars", [])
                
                for lang_info in languages:
                    lang_id = lang_info.get("id", "")
                    if lang_id:
                        hooks.register_highlighter_extension(lang_id, ext)
                        logger.info(f"Highlighter hook registered for {lang_id}")
                
                for gram_info in grammars:
                    lang = gram_info.get("language", "")
                    if lang:
                        hooks.register_highlighter_extension(lang, ext)
            
            # Snippet extension
            elif ext_type == ExtensionType.SNIPPET.value:
                contributions = ext.get("contributions", {})
                snippets_list = contributions.get("snippets", [])
                
                for snippet_info in snippets_list:
                    snippet_data = load_snippets(snippet_info.get("path", ""))
                    if snippet_data:
                        completions = get_snippet_completions(snippet_data)
                        lang = snippet_info.get("language", "")
                        
                        hooks.register_completions_provider(
                            lambda p, l, c=completions, target_lang=lang: 
                                [comp for comp in c if comp[0].startswith(p) and (not target_lang or l == target_lang)]
                        )
        
        except Exception as e:
            logger.error(f"Failed to apply hook for {ext.get('id')}: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# ADVANCED LSP & Syntax Suggestion System
# ═══════════════════════════════════════════════════════════════════════════

class SyntaxIntelligence:
    """Advanced syntax intelligence for smart code completions."""
    
    # Built-in type definitions for C/C++,python,C#
    BUILTIN_TYPES = {
        "cpp": {
            "std": {
                "string": ["append", "length", "substr", "find", "replace", "c_str"],
                "vector": ["push_back", "pop_back", "size", "clear", "begin", "end"],
                "map": ["insert", "find", "erase", "size", "clear", "count"],
                "set": ["insert", "find", "erase", "size", "clear", "count"],
                "cout": ["operator<<"],
                "cin": ["operator>>"],
                "endl": [],
            },
            "printf": [],
            "scanf": [],
            "malloc": [],
            "free": [],
            "strlen": [],
            "strcpy": [],
            "strcat": [],
        },
        "c": {
            "printf": [],
            "scanf": [],
            "malloc": [],
            "free": [],
            "strlen": [],
            "strcpy": [],
            "strcat": [],
            "FILE": ["fopen", "fclose", "fread", "fwrite"],
        },
        "python": {
            "str": ["append", "upper", "lower", "split", "join", "replace", "find", "strip"],
            "list": ["append", "pop", "remove", "clear", "sort", "reverse", "extend"],
            "dict": ["keys", "values", "items", "get", "pop", "clear", "update"],
            "set": ["add", "remove", "clear", "union", "intersection"],
            "print": [],
            "len": [],
            "range": [],
        },
        "c#":{},
    }
    
    # Trigger characters for context-aware completion
    TRIGGER_CHARS = {
        ".": "member_access",      # obj.member
        "(": "function_params",    # func(
        "{": "block_start",        # { ... }
        "[": "array_access",       # arr[
        ":": "scope_resolution",   # :: or type hints
        "->": "pointer_member",    # ptr->member
    }
    
    def __init__(self):
        self.type_definitions = {}
    
    def register_type_definition(self, language: str, type_name: str, members: List[str]):
        """Register a custom type definition."""
        if language not in self.type_definitions:
            self.type_definitions[language] = {}
        self.type_definitions[language][type_name] = members
    
    def get_member_suggestions(self, language: str, object_name: str) -> List[str]:
        """
        Get member suggestions for an object.
        
        Args:
            language: Programming language
            object_name: Name of the object (e.g., "std::string", "vector")
            
        Returns:
            List of member names
        """
        # Use C/C++ LSP for C/C++ languages
        if HAS_CPP_LSP and language in ["cpp", "c++", "c", "cc"] and api_module:
            provider = api_module.get_cpp_provider()
            members = provider.get_member_completions(object_name)
            return [m[0] for m in members]
        
        # Check custom definitions first
        if language in self.type_definitions:
            if object_name in self.type_definitions[language]:
                return self.type_definitions[language][object_name].copy()
        
        # Check built-in types
        if language in self.BUILTIN_TYPES:
            builtin = self.BUILTIN_TYPES[language]
            if object_name in builtin:
                return builtin[object_name].copy()
        
        return []
    
    def get_function_params_placeholder(self, language: str, func_name: str) -> str:
        """Get function parameter placeholder."""
        params_map = {
            "cpp": {
                "printf": "(format, ...)",
                "scanf": "(format, ...)",
                "strlen": "(str)",
                "strcpy": "(dest, src)",
                "malloc": "(size)",
                "free": "(ptr)",
            },
            "c": {
                "printf": "(format, ...)",
                "scanf": "(format, ...)",
                "strlen": "(str)",
                "strcpy": "(dest, src)",
                "malloc": "(size)",
                "free": "(ptr)",
            },
            "python": {
                "print": "(*args, **kwargs)",
                "len": "(obj)",
                "range": "(start, stop, step)",
                "str": "(obj)",
                "int": "(obj)",
                "float": "(obj)",
            }
        }
        
        if language in params_map and func_name in params_map[language]:
            return params_map[language][func_name]
        return "(...)"
    
    def extract_context(self, code: str, cursor_pos: int) -> Dict[str, Any]:
        """
        Extract context from code at cursor position.
        
        Args:
            code: Source code
            cursor_pos: Cursor position in code
            
        Returns:
            Dict with context info: trigger_char, object_name, prefix, etc.
        """
        if cursor_pos <= 0 or cursor_pos > len(code):
            return {"trigger_char": None, "object_name": "", "prefix": ""}
        
        context = {
            "trigger_char": None,
            "object_name": "",
            "prefix": "",
            "line": "",
            "position_in_line": 0,
        }
        
        # Get the line containing cursor
        lines = code[:cursor_pos].split('\n')
        context["line"] = lines[-1]
        context["position_in_line"] = len(lines[-1])
        
        # Check last character
        if cursor_pos > 0:
            last_char = code[cursor_pos - 1]
            if last_char in self.TRIGGER_CHARS:
                context["trigger_char"] = last_char
        
        # Extract object name before "." or "->"
        line_before_cursor = context["line"]
        
        # Member access after "."
        if "." in line_before_cursor:
            parts = line_before_cursor.rsplit(".", 1)
            if len(parts) == 2:
                obj_part = parts[0].strip().split()[-1] if parts[0].strip() else ""
                context["object_name"] = obj_part
                context["trigger_char"] = "."
        
        # Pointer member access after "->"
        if "->" in line_before_cursor:
            parts = line_before_cursor.rsplit("->", 1)
            if len(parts) == 2:
                obj_part = parts[0].strip().split()[-1] if parts[0].strip() else ""
                context["object_name"] = obj_part
                context["trigger_char"] = "->"
        
        # Get prefix (for filtering)
        last_space = max(
            line_before_cursor.rfind(" "),
            line_before_cursor.rfind("("),
            line_before_cursor.rfind(","),
        )
        context["prefix"] = line_before_cursor[last_space + 1:].strip()
        
        return context


# Global syntax intelligence instance
_syntax_intelligence = None


def get_syntax_intelligence() -> SyntaxIntelligence:
    """Get or create global SyntaxIntelligence instance."""
    global _syntax_intelligence
    if _syntax_intelligence is None:
        _syntax_intelligence = SyntaxIntelligence()
    return _syntax_intelligence


def get_smart_suggestions(language: str, code: str, cursor_pos: int, file_path: str = "") -> Dict[str, List[str]]:
    """
    Get smart code suggestions based on context.
    Uses CCLS (MaskRay's C/C++ Language Server) if available, otherwise falls back to local provider.
    
    Args:
        language: Programming language
        code: Source code
        cursor_pos: Cursor position in code
        file_path: Path to the file (optional, for CCLS)
        
    Returns:
        Dict with different suggestion types:
        - members: object members/attributes
        - functions: available functions
        - keywords: language keywords
        - snippets: code snippets
    """
    intel = get_syntax_intelligence()
    context = intel.extract_context(code, cursor_pos)
    
    suggestions = {
        "members": [],
        "functions": [],
        "keywords": [],
        "snippets": [],
        "context": context,
    }
    
    # Special handling for C# with CSharpLspClient
    if HAS_CSHARP_LSP and language in ["csharp", "c#"] and file_path and api_module:
        try:
            client = api_module.get_csharp_client()
            
            # Auto-start if disconnected or error
            if client.status in [api_module.CSharpConnectionStatus.DISCONNECTED, api_module.CSharpConnectionStatus.ERROR]:
                logger.info("Auto-starting C# LSP server...")
                client.start()
                
            if client.status == api_module.CSharpConnectionStatus.CONNECTED:
                lines_before = code[:cursor_pos].split('\n')
                line = len(lines_before) - 1
                character = len(lines_before[-1])
                
                csharp_completions = client.get_completions(file_path, line, character, code)
                
                if csharp_completions:
                    for item in csharp_completions:
                        label = item.get("label", "")
                        kind = item.get("kind", 0)
                        
                        if kind in [2, 3, 4]:  # Method, Function, Constructor
                            suggestions["functions"].append(label)
                        elif kind in [5, 6, 10, 20, 21, 23]:  # Field, Variable, Property, EnumMember, Constant, Event
                            suggestions["members"].append(label)
                        elif kind == 15:  # Snippet
                            suggestions["snippets"].append(label)
                        else:
                            suggestions["keywords"].append(label)
                            
                    logger.info(f"Got {len(csharp_completions)} completions from C# LSP")
                    return suggestions
        except Exception as e:
            logger.debug(f"C# LSP completion failed: {e}, falling back to local provider")

    # Special handling for C/C++ with CCLS
    if HAS_CCLS and language in ["cpp", "c++", "c", "cc"] and file_path and api_module:
        try:
            client = api_module.get_ccls_client()
            
            # Only use CCLS if connected
            if client.status == api_module.CclsConnectionStatus.CONNECTED:
                # Convert cursor position to line and character
                lines_before = code[:cursor_pos].split('\n')
                line = len(lines_before) - 1
                character = len(lines_before[-1])
                
                # Get completions from CCLS
                ccls_completions = client.get_completions(file_path, line, character)
                
                if ccls_completions:
                    suggestions["functions"] = [
                        c.get("label", c.get("sortText", "")) 
                        for c in ccls_completions
                    ]
                    logger.info(f"Got {len(ccls_completions)} completions from CCLS")
                    return suggestions
        
        except Exception as e:
            logger.debug(f"CCLS completion failed: {e}, falling back to local provider")
    
    # Get member suggestions if after "." or "->"
    if context["trigger_char"] in [".", "->"]:
        object_name = context["object_name"]
        if object_name:
            members = intel.get_member_suggestions(language, object_name)
            suggestions["members"] = [m for m in members if m.startswith(context["prefix"])]
    
    # Special handling for C/C++
    if HAS_CPP_LSP and language in ["cpp", "c++", "c", "cc"] and api_module:
        cpp_provider = api_module.get_cpp_provider()
        
        # Get C/C++ specific completions
        cpp_completions = cpp_provider.get_completions_for_prefix(context["prefix"], code)
        suggestions["functions"] = [c[0] for c in cpp_completions]
        
        # Get code snippets
        for snippet_name, snippet_code in cpp_provider.COMMON_PATTERNS.items():
            if snippet_name.startswith(context["prefix"]):
                suggestions["snippets"].append(snippet_name)
    else:
        # Get LSP suggestions as fallback
        hooks = get_extension_hooks()
        lsp_suggestions = hooks.get_completions_from_providers(context["prefix"], language)
        
        if context["trigger_char"] == "(":
            # Function parameter suggestions
            func_params = intel.get_function_params_placeholder(language, context["object_name"])
            suggestions["functions"] = [func_params]
        else:
            suggestions["functions"] = lsp_suggestions
    
    return suggestions


def get_lsp_suggestions(language: str, prefix: str = "", code: str = "", cursor_pos: int = 0, file_path: str = "") -> list:
    """
    Get autocomplete suggestions from LSP extension for a language.
    Supports CCLS (MaskRay's C/C++ Language Server) for real semantic analysis!
    
    Args:
        language: Programming language (e.g., "python", "cpp", "c")
        prefix: Text prefix to filter suggestions
        code: Full source code (optional, for context analysis)
        cursor_pos: Cursor position in code (optional, for context analysis)
        file_path: Path to file (optional, for CCLS)
        
    Returns:
        List of suggestion strings
    """
    hooks = get_extension_hooks()
    
    # Special handling for C# with CSharpLspClient (real language server)
    if HAS_CSHARP_LSP and language in ["csharp", "c#"] and file_path and api_module:
        try:
            client = api_module.get_csharp_client()
            
            # Auto-start if disconnected or error
            if client.status in [api_module.CSharpConnectionStatus.DISCONNECTED, api_module.CSharpConnectionStatus.ERROR]:
                logger.info("Auto-starting C# LSP server...")
                client.start()
                
            if client.status == api_module.CSharpConnectionStatus.CONNECTED:
                # If code context is provided, use context-aware suggestions
                if code and cursor_pos > 0:
                    smart_sugg = get_smart_suggestions(language, code, cursor_pos, file_path)
                    all_suggestions = (
                        smart_sugg["members"] +
                        smart_sugg["functions"] +
                        smart_sugg["snippets"]
                    )
                    if all_suggestions:
                        return all_suggestions
                
                # Fallback: Get completions at position
                lines_before = code[:cursor_pos].split('\n') if code else [""]
                line = len(lines_before) - 1
                character = len(lines_before[-1])
                
                completions = client.get_completions(file_path, line, character, code)
                return [
                    c.get("label", c.get("sortText", "")) 
                    for c in completions
                ][:20]  # Limit results
        
        except Exception as e:
            logger.debug(f"C# LSP error: {e}, falling back to local provider")

    # Special handling for C/C++ with CCLS (real language server)
    if HAS_CCLS and language in ["cpp", "c++", "c", "cc"] and file_path and api_module:
        try:
            client = api_module.get_ccls_client()
            
            # Only use CCLS if connected
            if client.status == api_module.CclsConnectionStatus.CONNECTED:
                # If code context is provided, use context-aware suggestions
                if code and cursor_pos > 0:
                    smart_sugg = get_smart_suggestions(language, code, cursor_pos, file_path)
                    all_suggestions = (
                        smart_sugg["members"] +
                        smart_sugg["functions"] +
                        smart_sugg["snippets"]
                    )
                    if all_suggestions:
                        return all_suggestions
                
                # Fallback: Get completions at position
                lines_before = code[:cursor_pos].split('\n') if code else [""]
                line = len(lines_before) - 1
                character = len(lines_before[-1])
                
                completions = client.get_completions(file_path, line, character)
                return [
                    c.get("label", c.get("sortText", "")) 
                    for c in completions
                ][:20]  # Limit results
        
        except Exception as e:
            logger.debug(f"CCLS error: {e}, falling back to local provider")
    
    # Special handling for C/C++ with local provider
    if HAS_CPP_LSP and language in ["cpp", "c++", "c", "cc"] and api_module:
        cpp_provider = api_module.get_cpp_provider()
        
        # If code context is provided, use context-aware suggestions
        if code and cursor_pos > 0:
            smart_sugg = get_smart_suggestions(language, code, cursor_pos, file_path)
            all_suggestions = (
                smart_sugg["members"] +
                smart_sugg["functions"] +
                smart_sugg["snippets"]
            )
            if all_suggestions:
                return all_suggestions
        
        # Fallback to prefix-based completion
        completions = cpp_provider.get_completions_for_prefix(prefix)
        return [c[0] for c in completions]
    
    # If code context is provided, use smart suggestions
    if code and cursor_pos > 0:
        smart_sugg = get_smart_suggestions(language, code, cursor_pos, file_path)
        
        # Combine all suggestions
        all_suggestions = (
            smart_sugg["members"] +
            smart_sugg["functions"] +
            smart_sugg["keywords"]
        )
        
        if all_suggestions:
            return all_suggestions
    
    # Fallback: Check if LSP extension is registered for this language
    lsp_ext = hooks.get_lsp_for_language(language)
    if lsp_ext:
        logger.info(f"Using LSP for {language}: {lsp_ext.get('displayName')}")
        
        # Return completions from snippets in LSP extension
        contributions = lsp_ext.get("contributions", {})
        snippets = contributions.get("snippets", [])
        if snippets:
            all_completions = []
            for snippet_info in snippets:
                snippet_data = load_snippets(snippet_info.get("path", ""))
                if snippet_data:
                    completions = get_snippet_completions(snippet_data)
                    all_completions.extend([c[0] for c in completions])
            return [s for s in all_completions if s.startswith(prefix)] if prefix else all_completions
    
    # Get from other completion providers
    return hooks.get_completions_from_providers(prefix, language)


def start_csharp_lsp(server_path: str = "csharp-ls", project_root: str = ".") -> bool:
    """Start C# LSP server."""
    if HAS_CSHARP_LSP and api_module:
        return api_module.start_csharp_lsp(server_path, project_root)
    return False


def stop_csharp_lsp() -> None:
    """Stop C# LSP server."""
    if HAS_CSHARP_LSP and api_module:
        api_module.stop_csharp_lsp()


def start_ccls(ccls_path: str = "ccls", project_root: str = ".") -> bool:
    """Start CCLS C/C++ LSP server."""
    if HAS_CCLS and api_module:
        return api_module.start_ccls(ccls_path, project_root)
    return False


def stop_ccls() -> None:
    """Stop CCLS C/C++ LSP server."""
    if HAS_CCLS and api_module:
        api_module.stop_ccls()
