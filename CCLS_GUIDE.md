# CCLS (MaskRay) Language Server Integration Guide

## Overview

VNCode now supports **CCLS** - a high-performance C/C++/Objective-C language server by MaskRay.

CCLS provides:
- ✅ Real semantic analysis (not just pattern matching)
- ✅ Complete code completion with context awareness
- ✅ Symbol definitions and references
- ✅ Hover information
- ✅ Project-wide understanding
- ✅ Support for C89, C99, C11, C17, C++98, C++11, C++14, C++17, C++20, Objective-C

**Repository**: https://github.com/MaskRay/ccls

---

## Installation

### 1. Install CCLS

#### Windows (via Scoop or direct download):
```bash
# Using Scoop
scoop install ccls

# Or download from releases: https://github.com/MaskRay/ccls/releases
```

#### macOS (via Homebrew):
```bash
brew install ccls
```

#### Linux (Ubuntu/Debian):
```bash
sudo apt-get install ccls
# Or build from source: https://github.com/MaskRay/ccls/wiki/Build
```

#### Build from Source:
```bash
git clone https://github.com/MaskRay/ccls
cd ccls
cmake -H. -BRelease
cmake --build Release
sudo cmake --install Release
```

### 2. Verify Installation

```bash
ccls --version
```

---

## VNCode Setup

### Basic Setup

```python
from core import start_ccls, stop_ccls, get_lsp_suggestions

# Start CCLS server (automatically finds 'ccls' in PATH)
success = start_ccls()

if success:
    print("CCLS started successfully!")
    
    # Now get completions with CCLS
    suggestions = get_lsp_suggestions(
        language="cpp",
        code="std::vector<int> arr;\narr.",
        cursor_pos=40,
        file_path="/path/to/file.cpp"
    )
    print(f"Suggestions: {suggestions}")
else:
    print("Failed to start CCLS")
    print("Make sure 'ccls' is in your PATH")

# Stop when done
stop_ccls()
```

### Custom CCLS Path

If CCLS is not in your PATH:

```python
from core import start_ccls

# Specify custom path
start_ccls(ccls_path="/path/to/ccls/binary", project_root="/path/to/project")
```

---

## Usage Examples

### Example 1: Get Completions with CCLS

```python
from core import get_lsp_suggestions, start_ccls

# Start CCLS
start_ccls(project_root=".")

# Get completions after "std::vector<int> arr;"
code = """
#include <vector>
using namespace std;

int main() {
    vector<int> arr;
    arr.
}
"""

suggestions = get_lsp_suggestions(
    language="cpp",
    code=code,
    cursor_pos=code.index("arr.") + 4,
    file_path="main.cpp"
)

print("CCLS Completions:", suggestions)
# Output: ['push_back', 'pop_back', 'size', 'clear', 'insert', ...]
```

### Example 2: Get Definitions

```python
from ccls_client import get_ccls_client

client = get_ccls_client()

# Get where 'push_back' is defined
definition = client.get_definition(
    file_path="main.cpp",
    line=10,
    character=15
)

if definition:
    print(f"Defined at: {definition['uri']}:{definition['range']['start']['line']}")
```

### Example 3: Get Hover Information

```python
from ccls_client import get_ccls_client

client = get_ccls_client()

# Get hover info for type/function
hover_info = client.get_hover_info(
    file_path="main.cpp",
    line=10,
    character=15
)

print(f"Type: {hover_info}")
# Output: Signature and documentation
```

### Example 4: Track Document Changes

```python
from ccls_client import get_ccls_client

client = get_ccls_client()

# Open document
client.open_document("main.cpp", initial_content)

# Document changed
client.change_document(
    "main.cpp",
    [{"range": {...}, "text": "new code"}]
)

# Close document
client.close_document("main.cpp")
```

---

## IDE Integration

### Example: Smart Editor with CCLS

```python
from core import start_ccls, get_lsp_suggestions, get_syntax_intelligence

class SmartEditor:
    def __init__(self, project_root="."):
        self.project_root = project_root
        self.current_file = None
        self.content = ""
        
        # Start CCLS on init
        if not start_ccls(project_root=project_root):
            print("⚠️  CCLS failed to start, using local completions")
    
    def open_file(self, file_path, content):
        """Open a file."""
        self.current_file = file_path
        self.content = content
        
        # Notify CCLS
        from ccls_client import get_ccls_client
        client = get_ccls_client()
        if client.status.value == "connected":
            client.open_document(file_path, content)
    
    def get_completions(self, cursor_pos):
        """Get smart completions at cursor."""
        return get_lsp_suggestions(
            language="cpp",
            code=self.content,
            cursor_pos=cursor_pos,
            file_path=self.current_file
        )
    
    def analyze_context(self, cursor_pos):
        """Analyze code context."""
        intel = get_syntax_intelligence()
        return intel.extract_context(self.content, cursor_pos)


# Usage
editor = SmartEditor(project_root="/path/to/project")
editor.open_file("main.cpp", """
#include <vector>
std::vector<int> arr;
arr.
""")

suggestions = editor.get_completions(editor.content.index("arr.") + 4)
print(f"Completions: {suggestions}")

context = editor.analyze_context(editor.content.index("arr.") + 4)
print(f"Context: {context}")
```

---

## Configuration

### CCLS Project Configuration

Create a `.ccls` file in your project root:

```python
# .ccls (project configuration)
%h %{hpp,h,hh,hxx,h++}
%c %{c,cc,cpp,cxx,c++}

# Enable C++17
-std=c++17

# Add include paths
-I/path/to/includes
-I./include

# Compilation flags
-Wall
-O2
```

Or `.ccls-root`:

```
# Just marks the project root
```

### Initialize with Compilation Database

```python
from ccls_client import get_ccls_client

# If your project has compile_commands.json
client = get_ccls_client(project_root="/path/with/compile_commands.json")
```

---

## Fallback Behavior

If CCLS is not available or fails to connect:

1. VNCode automatically falls back to **local C/C++ provider** (cpp_lsp.py)
2. Still provides:
   - STL member completions (std::vector, std::string, etc.)
   - C library functions
   - Code snippets
   - Context-aware suggestions

```python
from core import get_lsp_suggestions

# Even if CCLS is down, you get completions:
suggestions = get_lsp_suggestions(
    language="cpp",
    prefix="printf",
)
# Returns: ["printf", "sprintf", "fprintf", ...]
```

---

## API Reference

### CCLS Client Functions

```python
from ccls_client import (
    get_ccls_client,
    start_ccls,
    stop_ccls,
    get_ccls_completions,
    get_ccls_definition,
    get_ccls_hover
)

# Start server
start_ccls(ccls_path="ccls", project_root=".")

# Get client instance
client = get_ccls_client()

# Check connection status
if client.status.value == "connected":
    print("CCLS ready!")

# Get completions
completions = get_ccls_completions(
    file_path="main.cpp",
    line=10,
    character=5
)

# Get definition
defn = get_ccls_definition(
    file_path="main.cpp",
    line=10,
    character=5
)

# Get hover info
hover = get_ccls_hover(
    file_path="main.cpp",
    line=10,
    character=5
)

# Stop server
stop_ccls()
```

### Core Integration Functions

```python
from core import get_lsp_suggestions, get_smart_suggestions

# Get suggestions (automatically uses CCLS if available)
suggestions = get_lsp_suggestions(
    language="cpp",
    prefix="std::",
    code=source_code,           # Optional
    cursor_pos=position,        # Optional
    file_path="file.cpp"        # Important for CCLS!
)

# Get context-aware suggestions
smart = get_smart_suggestions(
    language="cpp",
    code=source_code,
    cursor_pos=position,
    file_path="file.cpp"        # For CCLS
)
```

---

## Troubleshooting

### Issue: "CCLS not found"

**Solution**: Ensure CCLS is in your PATH or specify custom path:
```python
start_ccls(ccls_path="/full/path/to/ccls")
```

### Issue: "CCLS failed to initialize"

**Solution**: Check if your project has proper C/C++ configuration:
- Create `.ccls` or `.ccls-root` file in project root
- Or provide `compile_commands.json`

### Issue: Completions are empty

**Solution**: 
1. Ensure CCLS is connected: `client.status == "connected"`
2. Provide valid file_path to `get_lsp_suggestions()`
3. Check CCLS project configuration
4. Falls back to local provider if CCLS fails

### Issue: CCLS crashes

**Solution**:
- Update CCLS: `brew upgrade ccls` (or equivalent)
- Check CCLS logs: `ccls --log=verbose`
- Report issue: https://github.com/MaskRay/ccls/issues

---

## Performance Tips

1. **Use compile_commands.json** for faster analysis:
   ```bash
   # Generate from CMake
   cmake . -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
   ```

2. **Limit file size** - CCLS works best with smaller files

3. **Enable caching**:
   ```
   # In .ccls
   -cache=/tmp/ccls-cache
   ```

4. **Multiple threads**:
   ```
   # In .ccls
   -j=4
   ```

---

## Comparison: CCLS vs Local Provider

| Feature | CCLS | Local Provider |
|---------|------|----------------|
| Semantic Analysis | ✅ Full semantic | ⚠️ Pattern-based |
| STL Completions | ✅ Complete | ✅ Good |
| Context Awareness | ✅ Perfect | ✅ Basic |
| Project Understanding | ✅ Full | ❌ No |
| Symbol Navigation | ✅ Yes | ❌ No |
| Definition Jump | ✅ Yes | ❌ No |
| Hover Info | ✅ Yes | ❌ No |
| Memory Usage | ⚠️ High | ✅ Low |
| Startup Time | ⚠️ Slow | ✅ Fast |

---

## Next Steps

1. Install CCLS: https://github.com/MaskRay/ccls/wiki/Install
2. Configure your project (`.ccls` file)
3. Start using: `start_ccls()`
4. Enjoy real C/C++ LSP support! 🎉
