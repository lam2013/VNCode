# C# LSP Language Server Integration Guide

## Overview

VNCode now supports C# Language Server Protocol (LSP) integration using **`csharp-ls`** or **`OmniSharp`**. 

This integration provides:
- ✅ Real semantic code analysis (class/struct fields, methods, events)
- ✅ Auto-complete suggestions with type details
- ✅ Hover documentation and method signatures
- ✅ Definition navigation (jump to code definition)
- ✅ Full support for modern .NET C# codebases

---

## Installation

### 1. Install C# Language Server (`csharp-ls`)

We highly recommend **`csharp-ls`** as it is lightweight, extremely fast, and installs natively as a dotnet global tool.

#### Prerequisites:
Make sure you have the .NET Core SDK installed. You can check by running:
```powershell
dotnet --version
```

#### Install via NuGet / dotnet tools:
```powershell
dotnet tool install -g csharp-ls
```

### 2. Verify Installation

```powershell
csharp-ls --version
```

> [!NOTE]
> The VNCode client will automatically check your default global dotnet tools directory (`%USERPROFILE%\.dotnet\tools\csharp-ls`) on Windows, so you do not need to manually configure your system PATH.

---

## VNCode API Usage

### 1. Starting the C# LSP Server

```python
from core import start_csharp_lsp

# Start with default 'csharp-ls'
success = start_csharp_lsp(server_path="csharp-ls", project_root=".")
if success:
    print("C# LSP is up and running!")
```

To use OmniSharp instead:
```python
# Start with OmniSharp (assumes OmniSharp.exe is on your PATH or provided as absolute path)
start_csharp_lsp(server_path="OmniSharp", project_root=".")
```

### 2. Request Autocomplete Suggestions

Suggestions will be fetched from the C# LSP client automatically when you invoke `get_lsp_suggestions`:

```python
from core import get_lsp_suggestions

suggestions = get_lsp_suggestions(
    language="c#",
    prefix="My",
    code="class Program { void Main() { string MyVar = \"Hello\"; My } }",
    cursor_pos=59,
    file_path="Program.cs"
)
print(suggestions)
```

### 3. Retrieve Type Hover Information

```python
from core import api_module

client = api_module.get_csharp_client()
if client.status.value == "connected":
    hover_info = client.get_hover_info(
        file_path="Program.cs",
        line=10,
        character=15
    )
    print(hover_info)
```

### 4. Jump to Definition

```python
definition = client.get_definition(
    file_path="Program.cs",
    line=10,
    character=15
)
if definition:
    print(f"Defined at: {definition['uri']} line {definition['range']['start']['line']}")
```

### 5. Stopping the Server

```python
from core import stop_csharp_lsp
stop_csharp_lsp()
```

---

## Troubleshooting

1. **Server Fails to Start**
   - Ensure the command `dotnet --version` runs successfully.
   - Run `dotnet tool list -g` to verify `csharp-ls` is installed.
   - If `csharp-ls` is installed but not starting, check if `%USERPROFILE%\.dotnet\tools` exists on your system.

2. **No Suggestions Returned**
   - Autocomplete works best inside a valid C# project context (containing a `.csproj` or `.sln` file).
   - Ensure you pass a valid `file_path` ending with `.cs` (such as `Program.cs`) because the language server determines compilation contexts using the file extension.
