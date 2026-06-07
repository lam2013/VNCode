# VNCode LSP & Syntax Intelligence - Usage Guide

## Tổng quan

VNCode giờ đây hỗ trợ các tính năng nâng cao:
1. **Smart Syntax Suggestions** - Gợi ý thông minh dựa trên ngữ cảnh
2. **LSP Integration** - Tích hợp Language Server Protocol
3. **C/C++ Completion** - Hoàn thành code C/C++ với STL library
4. **Undo/Redo System** - Hệ thống undo/redo cho mọi hành động

---

## 1. Smart Syntax Suggestions

### 1.1 Gợi ý sau dấu chấm (.)

Gợi ý các thành viên (members) của object sau dấu ".":

```cpp
#include <string>
using namespace std;

int main() {
    string msg = "Hello";
    msg.  // <-- Gợi ý: append, length, substr, find, replace, c_str, ...
}
```

**API:**
```python
from core import get_smart_suggestions

code = 'string msg = "Hello";\nmsg.'
suggestions = get_smart_suggestions("cpp", code, len(code))
print(suggestions["members"])  # ['append', 'length', 'substr', ...]
```

### 1.2 Gợi ý sau dấu ngoặc đơn (())

Gợi ý tham số hàm:

```cpp
printf(  // <-- Gợi ý: (format, ...)
scanf(   // <-- Gợi ý: (format, ...)
```

**API:**
```python
suggestions = get_smart_suggestions("cpp", code, cursor_pos)
print(suggestions["functions"])  # Danh sách gợi ý hàm
```

### 1.3 Gợi ý sau dấu mũi tên (->)

Gợi ý members cho con trỏ:

```cpp
std::string* ptr = new std::string("test");
ptr->  // <-- Gợi ý: append, length, substr, ...
```

### 1.4 Phân tích ngữ cảnh

```python
from core import get_syntax_intelligence

intel = get_syntax_intelligence()
context = intel.extract_context(code, cursor_pos)

# Trả về:
# {
#     "trigger_char": ".",      # Ký tự kích hoạt
#     "object_name": "msg",     # Tên object
#     "prefix": "su",           # Prefix hiện tại
#     "line": "msg.su",         # Dòng hiện tại
#     "position_in_line": 7     # Vị trí trong dòng
# }
```

---

## 2. LSP Integration

### 2.1 Tích hợp với Extension LSP

VNCode tự động phát hiện các extension LSP:

```python
from core import get_extension_hooks, apply_extension_hooks

hooks = get_extension_hooks()

# Lấy LSP extension cho một ngôn ngữ
lsp_cpp = hooks.get_lsp_for_language("cpp")
print(lsp_cpp["displayName"])  # e.g., "C/C++ Tools"

# Lấy tất cả LSP extensions
all_lsp = hooks.get_all_lsp_extensions()
```

### 2.2 Đăng ký LSP extension tùy chỉnh

```python
from core import get_extension_hooks

hooks = get_extension_hooks()

# Metadata của extension
lsp_metadata = {
    "id": "custom.lsp",
    "displayName": "My Custom LSP",
    "contributions": {
        "snippets": [
            {"path": "snippets/python.json"}
        ]
    }
}

hooks.register_lsp_extension("python", lsp_metadata)
```

---

## 3. C/C++ LSP Support

### 3.1 Built-in C/C++ Completions

Hệ thống tự động gợi ý hàm, type từ:
- **C Standard Library**: printf, scanf, malloc, free, strlen, ...
- **C++ STL**: std::string, std::vector, std::map, std::set, ...
- **STL Methods**: append, push_back, find, insert, ...

```python
from cpp_lsp import get_cpp_provider

provider = get_cpp_provider()

# Lấy completions cho prefix
completions = provider.get_completions_for_prefix("printf")
# Trả về: [("printf", "C stdlib from <stdio>"), ...]

# Lấy members của type
members = provider.get_member_completions("std::vector")
# Trả về: [("push_back", "Member of std::vector"), ...]

# Lấy include suggestions
includes = provider.get_include_suggestions("io")
# Trả về: ["iostream"]

# Lấy code snippet
snippet = provider.get_code_snippet("for_loop")
# Trả về: "for (int i = 0; i < n; i++) { ... }"
```

### 3.2 Đăng ký User-defined Types

Đăng ký các type tùy chỉnh để có completions:

```python
from cpp_lsp import get_cpp_provider

provider = get_cpp_provider()

# Đăng ký struct/class
provider.register_user_type("Person", ["name", "age", "email"])

# Bây giờ get_member_completions sẽ trả về các member này
members = provider.get_member_completions("Person")
# [("name", "User-defined member of Person"), ...]
```

### 3.3 Lấy Function Signatures

```python
provider = get_cpp_provider()

sig = provider.get_function_signature("printf")
# Trả về: 'printf(const char* format, ...)'

sig = provider.get_function_signature("std::cout")
# Trả về: 'operator<<(ostream& cout, const T& value)'
```

---

## 4. Undo/Redo System

### 4.1 Thêm hành động Undo/Redo

```python
from core import add_undo_action, undo, redo

def undo_insert(data):
    print(f"Removing: {data['text']}")

def redo_insert(data):
    print(f"Adding: {data['text']}")

add_undo_action(
    "Insert function declaration",
    undo_insert,
    redo_insert,
    {"text": "void myFunction() { }"}
)
```

### 4.2 Thực hiện Undo/Redo

```python
from core import undo, redo, can_undo, can_redo

# Kiểm tra khả năng
if can_undo():
    undo()

if can_redo():
    redo()
```

### 4.3 Lấy thông tin History

```python
from core import get_undo_redo_manager

manager = get_undo_redo_manager()

info = manager.get_history_info()
# {
#     "undo_count": 5,
#     "redo_count": 2,
#     "can_undo": True,
#     "can_redo": True,
#     "undo_action": "Insert function declaration",
#     "redo_action": "Insert variable",
#     "max_history": 100
# }
```

### 4.4 Text Edit Action Helper

```python
from core import create_text_edit_action

action = create_text_edit_action(
    old_text="printf(\"old\");",
    new_text="printf(\"new\");",
    position=15
)
manager.add_action(action)
```

---

## 5. Combined Usage Examples

### 5.1 Ví dụ: Auto-completion cho C++ code

```python
from core import get_lsp_suggestions

# Khi người dùng gõ: "std::str"
suggestions = get_lsp_suggestions("cpp", prefix="std::str")
# Gợi ý: ["std::string", ...]

# Khi người dùng gõ "msg." sau khai báo "string msg"
code = """
#include <string>
std::string msg = "Hello";
msg.
"""
suggestions = get_lsp_suggestions(
    "cpp",
    code=code,
    cursor_pos=len(code)
)
# Gợi ý: ["append", "find", "length", "substr", ...]
```

### 5.2 Ví dụ: Track code changes with Undo/Redo

```python
from core import add_undo_action, undo, redo, can_undo

class CodeEditor:
    def __init__(self):
        self.content = ""
    
    def insert_text(self, text, position):
        """Insert text at position."""
        old_content = self.content
        new_content = self.content[:position] + text + self.content[position:]
        
        def undo_func(data):
            self.content = data["old"]
        
        def redo_func(data):
            self.content = data["new"]
        
        add_undo_action(
            f"Insert '{text}'",
            undo_func,
            redo_func,
            {"old": old_content, "new": new_content}
        )
        
        self.content = new_content
    
    def undo_last_change(self):
        """Undo last change."""
        if can_undo():
            undo()

# Usage
editor = CodeEditor()
editor.insert_text("#include <stdio.h>", 0)
editor.insert_text("\nint main() { }", 17)
editor.undo_last_change()  # Removes the main function
```

### 5.3 Ví dụ: Smart IDE Assistant

```python
from core import get_smart_suggestions, get_lsp_suggestions

class SmartAssistant:
    def get_suggestions(self, language, code, cursor_pos):
        """Get intelligent suggestions based on context."""
        
        # Try smart suggestions first (context-aware)
        smart = get_smart_suggestions(language, code, cursor_pos)
        
        if smart["members"]:
            return smart["members"], "Members"
        
        if smart["functions"]:
            return smart["functions"], "Functions"
        
        # Fallback to prefix-based
        prefix = code[max(code.rfind(" "), cursor_pos-10):cursor_pos]
        lsp = get_lsp_suggestions(language, prefix)
        
        return lsp, "Completions"

# Usage
assistant = SmartAssistant()
sugg, type_name = assistant.get_suggestions("cpp", code, cursor_pos)
print(f"{type_name}: {sugg}")
```

---

## 6. Configuration

### 6.1 Custom Type Definitions

```python
from core import get_syntax_intelligence

intel = get_syntax_intelligence()

# Thêm type definition tùy chỉnh
intel.register_type_definition(
    "cpp",
    "MyClass",
    ["getData", "setData", "process", "cleanup"]
)

# Bây giờ completions sẽ include các method này
members = intel.get_member_suggestions("cpp", "MyClass")
```

### 6.2 C++ Standard Version

```python
from cpp_lsp import get_cpp_provider, CppStandard

# Tạo provider với C++20 standard
provider = get_cpp_provider(CppStandard.CXX20)
```

### 6.3 Max Undo History Size

```python
from core import get_undo_redo_manager, UndoRedoManager

# Tạo manager với max 50 actions (default 100)
manager = UndoRedoManager(max_history=50)
```

---

## 7. API Reference

### Core Functions

| Function | Purpose |
|----------|---------|
| `get_lsp_suggestions(language, prefix, code, cursor_pos)` | Lấy gợi ý LSP |
| `get_smart_suggestions(language, code, cursor_pos)` | Lấy gợi ý thông minh |
| `get_syntax_intelligence()` | Lấy SyntaxIntelligence instance |
| `add_undo_action(name, undo_func, redo_func, data)` | Thêm hành động undo |
| `undo()` / `redo()` | Thực hiện undo/redo |
| `can_undo()` / `can_redo()` | Kiểm tra khả năng |

### C++ LSP Functions

| Function | Purpose |
|----------|---------|
| `get_cpp_completions(prefix, context)` | Lấy C++ completions |
| `get_cpp_members(type_name)` | Lấy type members |
| `get_cpp_provider(cpp_standard)` | Lấy C++ provider instance |

---

## 8. Troubleshooting

### Issue: Completions không xuất hiện

1. Kiểm tra language code chính xác (e.g., "cpp" không phải "c++")
2. Đảm bảo LSP extension đã được load: `hooks.get_lsp_for_language("cpp")`
3. Xác minh code syntax đúng

### Issue: Members không được gợi ý

1. Kiểm tra object_name được trích xuất đúng: `intel.extract_context(code, pos)`
2. Đảm bảo type được đăng ký: `provider.register_user_type(type_name, members)`
3. Kiểm tra trigger character: ".", "->", hay "("

### Issue: Undo không hoạt động

1. Đảm bảo action được thêm: `can_undo()` return True
2. Kiểm tra undo callback không raise exception
3. Xác minh data được pass đúng vào action

---

## 9. Examples

Xem file `lsp_demo.py` để có các ví dụ chi tiết:

```bash
python lsp_demo.py
```

Chạy demo để xem tất cả tính năng hoạt động!
