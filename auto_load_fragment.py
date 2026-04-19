# ─────────────────────────────────────────
# Auto-Load Extensions on VNCode Startup
# ─────────────────────────────────────────

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
    Perfect for auto-loading on VNCode startup.
    
    Returns:
        List of extension metadata dicts, each containing:
        - id, namespace, name, displayName, description, version
        - contributions: themes, snippets, languages, grammars
        - _install_path: full directory path
    """
    return list_installed()
