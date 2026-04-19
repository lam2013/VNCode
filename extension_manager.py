"""
Extension Manager for VNCode IDE.
Handles downloading, extracting .vsix files, parsing package.json,
and loading extension contributions (themes, snippets, grammars).
"""

import json
import os
import shutil
import zipfile
import logging
from pathlib import Path
from typing import Optional

import openvsx_api

try:
    from run import logger
except ImportError:
    logger = logging.getLogger('vncode')

# Import extension types
try:
    from extension_types import detect_extension_type, ExtensionType
except ImportError:
    ExtensionType = None
    detect_extension_type = None


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

    if not openvsx_api.download_file(download_url, str(vsix_path), progress_callback):
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
    if detect_extension_type:
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
        "type": ext_type,  # NEW: Extension type
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
    # .vsix structure: extension/package.json
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
    # Try extension/ subdirectory first (standard .vsix layout)
    candidates = [
        extract_dir / "extension" / relative_path.lstrip("./"),
        extract_dir / relative_path.lstrip("./"),
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]  # Return first candidate even if not exists yet


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
        import re
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

        import re
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

        # Clean VS Code placeholders: ${1:text} → text, $0 → ""
        import re
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
        return themes[0]  # Return first (default) theme
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
        Dict with initialization results:
        {
            "initialized": N,
            "failed": N,
            "by_type": {"lsp": N, "theme": N, ...}
        }
    """
    if not extensions:
        return {"initialized": 0, "failed": 0, "by_type": {}}
    
    results = {
        "initialized": 0,
        "failed": 0,
        "by_type": {}
    }
    
    # Import extension type manager
    try:
        from extension_types import get_type_manager, ExtensionType
    except ImportError:
        logger.warning("Extension type system not available")
        return results
    
    type_manager = get_type_manager()
    
    for ext_metadata in extensions:
        try:
            ext_type_str = ext_metadata.get("type")
            if not ext_type_str:
                continue
            
            # Convert string type to ExtensionType enum
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


# ============================================================================
# Extension Runtime Hook System
# ============================================================================
# Allows extensions to hook into VNCode's editor functionality at runtime

class ExtensionHooks:
    """Manages extension hooks for Code Runner, LSP, and Syntax Highlighting."""
    
    def __init__(self):
        self.code_runner_extensions = []  # List of code-runner type extensions
        self.lsp_extensions = {}  # Dict of language -> LSP extension
        self.highlighter_extensions = {}  # Dict of language -> highlighter rules
        self.completions_providers = []  # List of completion providers
    
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
    
    try:
        from extension_types import ExtensionType
    except ImportError:
        logger.warning("Extension types not available for hooks")
        return
    
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
                    # Create completions provider from snippets
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
                
                # For each language this LSP supports
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
                
                # Register highlighter for each language
                for lang_info in languages:
                    lang_id = lang_info.get("id", "")
                    if lang_id:
                        hooks.register_highlighter_extension(lang_id, ext)
                        logger.info(f"Highlighter hook registered for {lang_id}")
                
                # Also register for grammar scopes
                for gram_info in grammars:
                    lang = gram_info.get("language", "")
                    if lang:
                        hooks.register_highlighter_extension(lang, ext)
            
            # Snippet extension
            elif ext_type == ExtensionType.SNIPPET.value if hasattr(ExtensionType, 'SNIPPET') else False:
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


def get_lsp_suggestions(language: str, prefix: str = "") -> list:
    """
    Get autocomplete suggestions from LSP extension for a language.
    Falls back to default suggestions if no LSP extension found.
    
    Args:
        language: Programming language (e.g., "python", "cpp")
        prefix: Text prefix to filter suggestions
        
    Returns:
        List of suggestion strings
    """
    hooks = get_extension_hooks()
    
    # Check if LSP extension is registered for this language
    lsp_ext = hooks.get_lsp_for_language(language)
    if lsp_ext:
        # For now, return empty as we'd need actual LSP communication
        # In future, this would call LSP server for real completions
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
