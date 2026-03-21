from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
import sys
import os
import json
import importlib.util
import shutil
from pathlib import *
from list_module import *
from fill_module import *
import re
from collections import defaultdict

SYNTAX_INFO = {
    # Dùng cho panel gợi ý cú pháp ở dưới (syntax_view)
    # Giá trị là chuỗi các keyword, cách nhau bởi dấu phẩy.
    "python": ", ".join(sorted(KEYWORDS)),
    # Gợi ý đơn giản cho C/C++
    "c": ", ".join(C_CPP_VARIBLE_SYNTAX),
    "c++": ", ".join(C_CPP_VARIBLE_SYNTAX),
}


print("2025 VNCORE LAB(alias of Nguyễn Trường Lâm)")

def resource_path(relative_path):
    """Trả về đường dẫn tuyệt đối đến resource, hoạt động cả khi chạy script lẫn khi build exe (PyInstaller)."""
    base = getattr(sys, '_MEIPASS', Path(__file__).parent)
    return (Path(base) / relative_path).as_posix()

class RenameDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Rename File")
        self.setFixedSize(400, 150)
        
        layout = QVBoxLayout(self)
        
        self.label = QLabel("Enter new file name:")
        layout.addWidget(self.label)
        
        self.line_edit = QLineEdit()
        layout.addWidget(self.line_edit)
        
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)
    
    def get_new_name(self):
        return self.line_edit.text()

class Main(QMainWindow):
    # Keyword sets — chỉ cần cho C/C++ vì các ngôn ngữ khác đã dùng LSP
    LANG_KEYWORDS = {
        'cpp': {
            'if', 'else', 'for', 'while', 'do', 'switch', 'case', 'default', 'break', 'continue',
            'return', 'struct', 'class', 'union', 'enum', 'public', 'private', 'protected',
            'new', 'delete', 'const', 'static', 'extern',
            'inline', 'namespace', 'using', 'template', 'typename', 'decltype',
            'typedef', 'sizeof', 'volatile', 'register', 'goto',
        },
    }
    
    def _get_lang_from_ext(self, ext: str) -> str:
        """Map file extension to language key for keyword filtering."""
        ext_map = {
            '.c': 'cpp', '.cpp': 'cpp', '.cc': 'cpp', '.h': 'cpp', '.hpp': 'cpp',
            '.py': 'python',
            '.java': 'java',
            '.js': 'javascript', '.jsx': 'javascript', '.ts': 'javascript', '.tsx': 'javascript',
            '.go': 'go',
            '.rs': 'rust',
        }
        return ext_map.get(ext, '')

    def get_buffer_symbols(self, text: str, cursor_pos: int = 0, prefix: str = "", lang: str = None) -> list[tuple[str, str]]:
        """Lấy tất cả identifier có trong file, phân loại theo scope, ưu tiên gần con trỏ"""
        if lang == "cpp" or lang == "c":
            return self.get_buffer_symbols_cpp(text, cursor_pos, prefix)
        symbols = defaultdict(set)  # type -> set[symbol]
        lines = text.splitlines()
        
        # Đảm bảo index dòng hợp lệ
        if cursor_pos > len(text): cursor_pos = len(text)
        current_line = text[:cursor_pos].count('\n')

        if lang == "python":
            import ast
            try:
                tree = ast.parse(text)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        symbols['function'].add(node.name)
                    elif isinstance(node, ast.ClassDef):
                        symbols['class'].add(node.name)
                        for body_item in node.body:
                            if isinstance(body_item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                symbols['method'].add(body_item.name)
                    elif isinstance(node, ast.Assign):
                        for t in node.targets:
                            if isinstance(t, ast.Name):
                                symbols['variable'].add(t.id)
                            elif isinstance(t, ast.Attribute):
                                symbols['variable'].add(t.attr)
                    elif isinstance(node, ast.AnnAssign):
                        if isinstance(node.target, ast.Name):
                            symbols['variable'].add(node.target.id)
                        elif isinstance(node.target, ast.Attribute):
                            symbols['variable'].add(node.target.attr)
                    elif isinstance(node, (ast.Import, ast.ImportFrom)):
                        for alias in node.names:
                            name = alias.asname or alias.name
                            if "." in name:
                                name = name.split(".")[-1]
                            symbols['import'].add(name)
            except Exception:
                pass # Fallback to regex if AST fails (e.g. syntax error while typing)

        if not symbols: # Nếu không phải python hoặc AST fail, dùng regex chung
            scope_level = 0
            in_class = False
            in_function = False
            for line_num, line in enumerate(lines):
                stripped = line.strip()
                if not stripped:
                    continue
                if lang in ["python", "nim", "yaml", "txt"]:
                    scope_level = (len(line) - len(line.lstrip())) // 4 # Ước lượng mỗi thụt lề 4 space
                else:
                    scope_level += line.count('{') - line.count('}')


                # Phát hiện class/struct/enum
                class_pat = r'^\s*(class|struct|enum)\s+([a-zA-Z_][a-zA-Z0-9_]*)'
                if re.match(class_pat, stripped):
                    match = re.search(class_pat, stripped)
                    if match:
                        name = match.group(2)
                        symbols['class/struct'].add(name)
                        in_class = True
                        continue

                # Phát hiện hàm / method
                func_pat = r'^\s*(?:[\w:]+\s+)?([a-zA-Z_][a-zA-Z0-9_]*)\s*\([^)]*\)\s*(const)?\s*\{?'
                if re.match(func_pat, stripped):
                    match = re.search(r'([a-zA-Z_][a-zA-Z0-9_]*)\s*\(', stripped)
                    if match:
                        name = match.group(1)
                        symbols['function'].add(name)
                        in_function = True
                        continue

                # Phát hiện biến (global / member / local / parameter)
                var_pat = r'(?:const\s+)?(?:unsigned\s+)?(?:\w+(?:\s*\*|\s*&)?\s+)+([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:=|[;,)])'
                matches = re.finditer(var_pat, line)
                for match in matches:
                    name = match.group(1)
                    if in_class and scope_level > 0:
                        symbols['member_var'].add(name)
                    elif scope_level == 0:
                        symbols['global_var'].add(name)
                    elif in_function:
                        symbols['local_var'].add(name)
                    else:
                        symbols['local_var'].add(name)

                # Parameter trong hàm (trong ngoặc)
                if '(' in line and ')' in line and in_function:
                    param_part = re.search(r'\(([^)]*)\)', line)
                    if param_part:
                        params = param_part.group(1)
                        param_matches = re.findall(r'(?:const\s+)?(?:\w+\s*\*?\s*&\s*)?([a-zA-Z_][a-zA-Z0-9_]*)', params)
                        for p in param_matches:
                            if p:
                                symbols['parameter'].add(p)

        kw_suggestions = []
        sym_suggestions = []
        
        # 1. Thêm Keywords từ ngôn ngữ
        if lang:
            kw_list = set()
            # Ưu tiên set chuẩn trong LANG_KEYWORDS
            if lang in self.LANG_KEYWORDS:
                kw_list.update(self.LANG_KEYWORDS[lang])
            # Thêm từ SYNTAX_INFO (dùng chung cho panel và suggest)
            if lang in SYNTAX_INFO:
                parts = SYNTAX_INFO[lang].split(",")
                kw_list.update([p.strip() for p in parts if p.strip()])
            
            # Map 'cpp' -> 'c' / 'c++' keywords nếu cần
            if lang == "cpp":
                for alt in ["c", "c++"]:
                    if alt in SYNTAX_INFO:
                        parts = SYNTAX_INFO[alt].split(",")
                        kw_list.update([p.strip() for p in parts if p.strip()])

            for kw in kw_list:
                if kw.lower().startswith(prefix.lower()):
                    kw_suggestions.append((kw, kw))

        # 2. Thêm Identifier từ buffer
        for typ, sym_set in symbols.items():
            for real_name in sym_set:
                if real_name.lower().startswith(prefix.lower()):
                    sym_suggestions.append((real_name, real_name))

        # Ưu tiên symbols (không phải keyword) gần con trỏ (±80 dòng)
        recent_lines = lines[max(0, current_line-80):current_line+80]
        recent_text = '\n'.join(recent_lines)
        recent_symbols = [s for s in sym_suggestions if s[0] in recent_text]

        # Kết hợp ưu tiên: Symbols gần -> Symbols khác -> Keywords, loại trùng, giới hạn
        final = list(dict.fromkeys(recent_symbols + sym_suggestions + kw_suggestions))[:40]
        return final


    def _resolve_python_local_import_files(self, current_file_path: str, text: str) -> list[str]:
        """
        Resolve local python imports to file paths (best-effort).
        Chỉ resolve trong cùng thư mục workspace hiện tại (folder chứa main.py và subfolder).
        """
        import ast

        if not current_file_path:
            return []
        base_dir = Path(current_file_path).resolve().parent

        try:
            tree = ast.parse(text)
        except Exception:
            return []

        resolved: list[str] = []

        def try_add(p: Path):
            try:
                p = p.resolve()
            except Exception:
                return
            if p.exists() and p.is_file() and p.suffix.lower() == ".py":
                resolved.append(p.as_posix())

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mod = (alias.name or "").strip()
                    if not mod or mod.startswith("."):
                        continue
                    # foo.bar -> foo/bar.py
                    p1 = base_dir / Path(*mod.split("."))
                    try_add(p1.with_suffix(".py"))
                    try_add(p1 / "__init__.py")
            elif isinstance(node, ast.ImportFrom):
                level = getattr(node, "level", 0) or 0
                mod = (node.module or "").strip()
                target_dir = base_dir
                for _ in range(level):
                    target_dir = target_dir.parent
                if mod:
                    p1 = target_dir / Path(*mod.split("."))
                    try_add(p1.with_suffix(".py"))
                    try_add(p1 / "__init__.py")

        # unique preserve order
        seen = set()
        out = []
        for p in resolved:
            if p not in seen and p != Path(current_file_path).resolve().as_posix():
                seen.add(p)
                out.append(p)
        return out
    def get_buffer_symbols_cpp(self, text: str, cursor_pos: int, prefix: str) -> list[tuple[str, str]]:
        """Phân loại và lấy tất cả symbols có trong file C/C++, ưu tiên theo ngữ cảnh con trỏ"""
        import re
        from collections import defaultdict

        symbols = defaultdict(set)  # type -> set[symbol]
        cpp_keywords = self.LANG_KEYWORDS.get('cpp', set())

        lines = text.splitlines()
        current_line = text[:cursor_pos].count('\n')  # dòng hiện tại của con trỏ

        in_class = False
        scope_level = 0
        in_function = False

        for line_num, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue

            # Theo dõi scope {}
            scope_level += line.count('{') - line.count('}')

            # Phát hiện class/struct
            if re.match(r'^\s*(class|struct)\s+([a-zA-Z_][a-zA-Z0-9_]*)', stripped):
                match = re.search(r'(class|struct)\s+([a-zA-Z_][a-zA-Z0-9_]*)', stripped)
                if match:
                    class_name = match.group(2)
                    symbols['class'].add(class_name)
                    in_class = True
                    continue

            # Phát hiện hàm / method
            func_pattern = r'^\s*(?:[\w:]+\s+)?([a-zA-Z_][a-zA-Z0-9_]*)\s*\([^)]*\)\s*(const)?\s*(?:::\s*[a-zA-Z_][a-zA-Z0-9_]*)*\s*\{?'
            if re.match(func_pattern, stripped):
                match = re.search(r'([a-zA-Z_][a-zA-Z0-9_]*)\s*\(', stripped)
                if match:
                    func_name = match.group(1)
                    symbols['function'].add(func_name)
                    in_function = True
                    continue

            # Phát hiện biến (global, member, local, parameter)
            var_pattern = r'(?:const\s+)?(?:unsigned\s+)?(?:\w+(?:\s*\*|\s*&)?\s+)+([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:=|[;,)])'
            matches = re.finditer(var_pattern, line)
            for match in matches:
                var_name = match.group(1)
                if in_class and scope_level > 0 and '{' in line:
                    symbols['member_var'].add(var_name)
                elif scope_level == 0:
                    symbols['global_var'].add(var_name)
                elif in_function:
                    symbols['local_var'].add(var_name)
                else:
                    symbols['local_var'].add(var_name)

            # Phát hiện parameter trong hàm (nằm trong dấu ngoặc)
            if '(' in line and ')' in line:
                param_part = re.search(r'\(([^)]*)\)', line)
                if param_part:
                    params = param_part.group(1)
                    param_matches = re.findall(r'(?:const\s+)?(?:\w+\s*\*?\s*&\s*)?([a-zA-Z_][a-zA-Z0-9_]*)', params)
                    for p in param_matches:
                        if p and p not in cpp_keywords:
                            symbols['parameter'].add(p)

            # Phát hiện include / using namespace (gợi ý tên header hoặc namespace)
            if '#include' in line:
                match = re.search(r'#include\s*[<"]?([^>"]+)[>"]?', line)
                if match:
                    header = match.group(1).split('/')[-1].split('.')[0]  # chỉ lấy tên file/header
                    symbols['include'].add(header)

            if 'using namespace' in line:
                match = re.search(r'using\s+namespace\s+([a-zA-Z_:]+);', line)
                if match:
                    ns = match.group(1)
                    symbols['namespace'].add(ns)

        # Lọc theo prefix
        kw_suggestions = []
        sym_suggestions = []
        
        # 1. Thêm Keywords
        for kw in cpp_keywords:
            if kw.lower().startswith(prefix.lower()):
                kw_suggestions.append((kw, kw))
        
        # Thêm từ SYNTAX_INFO cho c/c++
        for alt in ["c", "c++"]:
            if alt in SYNTAX_INFO:
                parts = SYNTAX_INFO[alt].split(",")
                for p in parts:
                    p = p.strip()
                    if p and p.lower().startswith(prefix.lower()):
                        kw_suggestions.append((p, p))

        # 2. Thêm Symbols
        for typ, sym_set in symbols.items():
            for s in sym_set:
                if s.lower().startswith(prefix.lower()):
                    sym_suggestions.append((s, s))

        # Ưu tiên symbols (không phải keyword) gần con trỏ (trong khoảng ±50 dòng)
        recent_lines = lines[max(0, current_line-50):current_line+50]
        recent_text = '\n'.join(recent_lines)
        recent_symbols = [s for s in sym_suggestions if s[0] in recent_text]

        # Kết hợp ưu tiên: Symbols gần -> Symbols khác -> Keywords, loại trùng
        final = list(dict.fromkeys(recent_symbols + sym_suggestions + kw_suggestions))

        return final[:40]

    def update_cursor_position(self):
        if self.tabFile.currentWidget():
            editor = self.tabFile.currentWidget()
            cursor = editor.textCursor()
            line = cursor.blockNumber() + 1
            col = cursor.columnNumber() + 1
            self.statusBar.showMessage(f"Ln: {line}, Col: {col}")

    def __init__(self):
        super().__init__()
        self.setWindowTitle("VNCode IDE")
        self._dir = Path(__file__).parent.as_posix()
        self.setWindowIcon(QIcon(resource_path("icon_VNCode.ico")))
        self.theme_color = "#1e1e1e"
        self.language = "vi"
        self.setStyleSheet(f"""
        /* === Main Window === */
        QMainWindow, QWidget {{
            background-color: {self.theme_color};
            color: #d4d4d4;
        }}

        /* === Menu Bar === */
        QMenuBar {{
            background-color: #3c3c3c;
            color: #d4d4d4;
            border-bottom: 1px solid #007acc;
            padding: 2px;
            font-size: 13px;
        }}
        QMenuBar::item {{
            background-color: transparent;
            padding: 4px 10px;
        }}
        QMenuBar::item:selected {{
            background-color: #094771;
        }}
        QMenu {{
            background-color: #252526;
            color: #d4d4d4;
            border: 1px solid #3c3c3c;
        }}
        QMenu::item:selected {{
            background-color: #094771;
        }}
        QMenu::separator {{
            height: 1px;
            background-color: #3c3c3c;
        }}

        /* === Tab Widget === */
        QTabWidget::pane {{
            border-top: 1px solid #007acc;
            background-color: #1e1e1e;
        }}
        QTabBar {{
            background-color: #252526;
        }}
        QTabBar::tab {{
            background-color: #2d2d2d;
            color: #969696;
            padding: 6px 40px 6px 20px;
            border: none;
            border-right: 1px solid #252526;
            font-size: 13px;
            min-width: 1px;
        }}
        QTabBar::tab:selected {{
            background-color: #1e1e1e;
            color: #ffffff;
            border-bottom: 2px solid #007acc;
        }}
        QTabBar::tab:hover:!selected {{
            background-color: #383838;
            color: #d4d4d4;
        }}
        QTabBar::close-button {{
            image: url({resource_path("close.svg")});
            subcontrol-position: right;
            padding: 2px;
        }}
        QTabBar::close-button:hover {{
            image: url({resource_path("close_hover.svg")});
            background-color: #c42b1c;
            border-radius: 2px;
        }}

        /* === Text Editor === */
        QTextEdit {{
            background-color: #1e1e1e;
            color: #d4d4d4;
            border: none;
            selection-background-color: #264f78;
            selection-color: #ffffff;
            font-size: 14px;
            padding: 8px;
        }}

        /* === Scrollbar === */
        QScrollBar:vertical {{
            background-color: #1e1e1e;
            width: 14px;
            border: none;
        }}
        QScrollBar::handle:vertical {{
            background-color: #424242;
            min-height: 30px;
            border-radius: 0px;
        }}
        QScrollBar::handle:vertical:hover {{
            background-color: #4f4f4f;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
        QScrollBar:horizontal {{
            background-color: #1e1e1e;
            height: 14px;
            border: none;
        }}
        QScrollBar::handle:horizontal {{
            background-color: #424242;
            min-width: 30px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background-color: #4f4f4f;
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0px;
        }}

        /* === MessageBox === */
        QMessageBox {{
            background-color: #252526;
            color: #d4d4d4;
        }}
        QPushButton {{
            background-color: #0e639c;
            color: #ffffff;
            border: none;
            padding: 5px 16px;
            font-size: 13px;
            border-radius: 2px;
        }}
        QPushButton:hover {{
            background-color: #1177bb;
        }}
        QPushButton:pressed {{
            background-color: #094771;
        }}

        /* === File Dialog === */
        QFileDialog {{
            background-color: #252526;
            color: #d4d4d4;
        }}
        """)
        self.resize(900, 650)
        self.last_current_text = ""
        self.current_file = None
        self.tab_file_paths = {}
        self.label = None
        self.syntax_view = None
        self.terminal_container = None
        self.terminal_tabs = None
        self.terminal_output = None
        self.process = None
        self.multi_processes = []
        self.ext_to_lang = {}
        self.extension_container = None
        self.extension_tabs = None
        self.syntax_timer = QTimer(self)
        self.syntax_timer.setSingleShot(True)
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.setStyleSheet("color: #d4d4d4; background-color: #252526;")
        for lang, exts in TYPE_FILE.items():
            for ext in exts:
                norm = ext.lower().lstrip(".")
                self.ext_to_lang[norm] = lang
                self.ext_to_lang[f".{norm}"] = lang
        self.syntax_timer.timeout.connect(self.update_syntax_panel)
        
        config = self._load_config()
        self.auto_save_enabled = config.get("auto_save", False)
        self.initUI()

    def show_console(self):
        if hasattr(self, 'terminal_tab') and self.terminal_tab is not None:
            self.extension_container.show()
            self.extension_tabs.setCurrentWidget(self.terminal_tab)
            return

        self.terminal_tab = QWidget()
        terminal_layout = QVBoxLayout(self.terminal_tab)
        terminal_layout.setContentsMargins(0, 0, 0, 0)
        terminal_layout.setSpacing(0)

        header = QWidget()
        header.setFixedHeight(24)
        header.setStyleSheet("background-color: #252526;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 0, 4, 0)
        header_layout.setSpacing(0)

        header_label = QLabel("Terminal")
        header_label.setStyleSheet("color: #d4d4d4; font-size: 12px;")
        header_layout.addWidget(header_label)
        header_layout.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #858585;
                border: none;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c42b1c;
                color: #ffffff;
                border-radius: 2px;
            }
        """)
        close_btn.clicked.connect(self.hide_console)
        header_layout.addWidget(close_btn)
        terminal_layout.addWidget(header)

        main_window = self
        class ConsoleWidget(QPlainTextEdit):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.setFont(QFont("Consolas", 11))
                self.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4; border: none; padding: 4px;")
                self._prompt_pos = 0  

            def append_output(self, text):
                self.moveCursor(QTextCursor.End)
                self.insertPlainText(text)
                self._prompt_pos = self.textCursor().position()
                self.moveCursor(QTextCursor.End)
                self.ensureCursorVisible()

            def keyPressEvent(self, event):
                cursor = self.textCursor()

                if cursor.position() < self._prompt_pos:
                    if event.key() not in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down,
                                           Qt.Key_Home, Qt.Key_End, Qt.Key_PageUp, Qt.Key_PageDown):
                        self.moveCursor(QTextCursor.End)

                if event.key() == Qt.Key_Backspace:
                    if cursor.position() <= self._prompt_pos:
                        return

                if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                    full_text = self.toPlainText()
                    input_text = full_text[self._prompt_pos:]
                    self.moveCursor(QTextCursor.End)
                    self.insertPlainText("\n")
                    self._prompt_pos = self.textCursor().position()

                    if main_window.process and main_window.process.state() == QProcess.Running:
                        main_window.process.write((input_text + "\n").encode("utf-8"))
                    return

                super().keyPressEvent(event)

        self.terminal_output = ConsoleWidget()
        terminal_layout.addWidget(self.terminal_output)

        self.extension_tabs.addTab(self.terminal_tab, "Terminal")
        self.extension_container.show()
        self.extension_tabs.setCurrentWidget(self.terminal_tab)

    def hide_console(self):
        """Ẩn panel terminal và dừng process nếu đang chạy."""
        self.stop_process()
        self.extension_container.hide()


    def initUI(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.mainlayout = QVBoxLayout(central_widget)
        self.mainlayout.setContentsMargins(0, 0, 0, 0)
        self.mainlayout.setSpacing(0)
        
        self.menubar = QMenuBar(self)
        self.file_menu = self.menubar.addMenu("File")
        self.run_menu = self.menubar.addMenu("Run")
        self.settings_menu = self.menubar.addMenu("Settings")
        self.help_menu = self.menubar.addMenu("Help")
        self.about_action = self.help_menu.addAction("About")
        self.multicore_action = self.help_menu.addAction("Run Multi-core")
        self.open_action = self.file_menu.addAction("Open")
        self.new_action = self.file_menu.addAction("New")
        self.save_action = self.file_menu.addAction("Save")
        self.save_as_action = self.file_menu.addAction("Save As")
        self.rename_action = self.file_menu.addAction("Rename")
        self.delete_action = self.file_menu.addAction("Delete")
        self.exit_action = self.file_menu.addAction("Exit")
        self.run_action = self.run_menu.addAction("Run Current File")
        self.settings_action = self.settings_menu.addAction("Preferences")
        self.console_action = self.run_menu.addAction("Console")

        self.console_action.triggered.connect(self.show_console)
        self.open_action.triggered.connect(self.open_file)
        self.new_action.triggered.connect(self.new_file)
        self.save_action.triggered.connect(self.save_file)
        self.save_as_action.triggered.connect(self.save_as_file)
        self.delete_action.triggered.connect(self.delete_file)
        self.exit_action.triggered.connect(self.exit_app)
        self.about_action.triggered.connect(self.about_app)
        self.rename_action.triggered.connect(self.rename_file)
        
        self.file_menu.addSeparator()
        self.auto_save_action = self.file_menu.addAction("Auto Save")
        self.auto_save_action.setCheckable(True)
        self.auto_save_action.setChecked(self.auto_save_enabled)
        self.auto_save_action.triggered.connect(self.toggle_auto_save)
        self.file_menu.addSeparator()
        
        self.run_action.triggered.connect(self.run_current_file)
        self.settings_action.triggered.connect(self.open_settings)
        self.multicore_action.triggered.connect(self.run_multicore)
        
        self.tabFile = QTabWidget(self)
        self.tabFile.setTabsClosable(True)
        self.tabFile.setDocumentMode(True)
        self.tabFile.setElideMode(Qt.ElideNone)
        self.tabFile.tabCloseRequested.connect(self.close_tab)
        self.tabFile.currentChanged.connect(self.on_tab_changed)
        
        tab_bar = self.tabFile.tabBar()
        tab_bar.setExpanding(False)
        tab_bar.setElideMode(Qt.ElideNone)
        tab_bar.setUsesScrollButtons(True)
        
        self.mainlayout.addWidget(self.menubar, 0)
        self.mainlayout.addWidget(self.tabFile, 1)

        self.syntax_view = QListWidget(self)
        self.syntax_view.setFixedHeight(120)
        self.syntax_view.hide()
        self.syntax_view.itemDoubleClicked.connect(self.insert_syntax_from_list)
        self.mainlayout.addWidget(self.syntax_view, 0)

        self.extension_container = QWidget(self)
        ext_layout = QVBoxLayout(self.extension_container)
        ext_layout.setContentsMargins(0, 0, 0, 0)
        ext_layout.setSpacing(2)
        self.extension_tabs = QTabWidget(self.extension_container)
        ext_layout.addWidget(self.extension_tabs)
        self.extension_container.setFixedHeight(200)
        self.extension_container.hide()
        self.mainlayout.addWidget(self.extension_container, 0)
        
        self.make_json_file()
        self.check_no_file()
        self.auto_open_file_recent()
        self.auto_check_current_file_used()

        

    def create_editor(self, file_path=None, content=""):
        class LineNumberArea(QWidget):
            def __init__(self, editor):
                super().__init__(editor)
                self.editor = editor
                self.editor.blockCountChanged.connect(self.update_width)
                self.editor.updateRequest.connect(self.update_on_scroll)
                self.update_width()

            def sizeHint(self):
                return QSize(self.get_width(), 0)

            def get_width(self):
                digits = len(str(max(1, self.editor.document().blockCount())))
                space = 8 + self.editor.fontMetrics().horizontalAdvance('9') * digits
                return space

            def update_width(self, *args):
                width = self.get_width()
                self.editor.setViewportMargins(width, 0, 0, 0)

            def update_on_scroll(self, rect, scroll):
                if scroll:
                    self.scroll(0, scroll)
                else:
                    self.update(0, rect.y(), self.width(), rect.height())
                if rect.contains(self.editor.viewport().rect()):
                    self.update_width()

            def paintEvent(self, event):
                painter = QPainter(self)
                painter.fillRect(event.rect(), QColor("#1e1e1e"))

                block = self.editor.document().findBlock(self.editor.firstVisibleBlock().position())
                block_number = block.blockNumber()
                top = int(self.editor.blockBoundingGeometry(block).translated(self.editor.contentOffset()).top())
                bottom = top + int(self.editor.blockBoundingRect(block).height())

                while block.isValid() and top <= event.rect().bottom():
                    if block.isVisible() and bottom >= event.rect().top():
                        number = str(block_number + 1)
                        painter.setPen(QColor("#858585"))
                        painter.drawText(0, top, self.width() - 5, self.editor.fontMetrics().height(),
                                         Qt.AlignRight | Qt.AlignVCenter, number)
                    block = block.next()
                    top = bottom
                    bottom = top + int(self.editor.blockBoundingRect(block).height())
                    block_number += 1
        class CodeHighlighter(QSyntaxHighlighter):
            def __init__(self, parent=None, lang=""):
                super().__init__(parent)
                self.lang = lang
                self.highlighting_rules = []

                # Format cho các loại
                keyword_format = QTextCharFormat()
                keyword_format.setForeground(QColor("#569cd6"))  # xanh dương
                keyword_format.setFontWeight(QFont.Bold)

                function_format = QTextCharFormat()
                function_format.setForeground(QColor("#dcdcaa")) # vàng nhạt cho hàm

                class_format = QTextCharFormat()
                class_format.setForeground(QColor("#4ec9b0")) # xanh ngọc cho class

                number_format = QTextCharFormat()
                number_format.setForeground(QColor("#b5cea8")) # xanh lơ cho số

                string_format = QTextCharFormat()
                string_format.setForeground(QColor("#ce9178"))  # cam

                comment_format = QTextCharFormat()
                comment_format.setForeground(QColor("#6a9955"))  # xanh lá đậm cho chú thích

                brace_format = QTextCharFormat()
                brace_format.setForeground(QColor("#ffd700"))  # vàng cho ngoặc

                identifier_format = QTextCharFormat()
                identifier_format.setForeground(QColor("#ffffff"))  # xanh lá/sáng (biến chung)

                escape_format = QTextCharFormat()
                escape_format.setForeground(QColor("#d7ba7d"))  # vàng đậm cho escape sequence

                # ========================================================
                # Thứ tự các rule RẤT QUAN TRỌNG:
                # Trong QSyntaxHighlighter, rule được add sau sẽ GHI ĐÈ
                # lên màu của các rule trước nếu trùng vị trí chữ.
                # ========================================================

                # 1. Identifier chung & Số (Mức ưu tiên thấp nhất)
                self.highlighting_rules.append((re.compile(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b'), identifier_format))
                self.highlighting_rules.append((re.compile(r'\b\d+(\.\d+)?\b'), number_format))
                # import
                
                # 2. Class (Thường viết hoa chữ cái đầu)
                self.highlighting_rules.append((re.compile(r'\b[A-Z][a-zA-Z0-9_]*\b'), class_format))

                # 3. Function (Từ theo sau bởi dấu ngoặc mở)
                self.highlighting_rules.append((re.compile(r'\b[a-zA-Z_][a-zA-Z0-9_]*(?=\s*\()'), function_format))

                # 4. Từ khóa (Sẽ đè lên các Identifier ở trên để nó không bị nhầm thành màu biến)
                keywords = [
                    'if', 'else', 'for', 'while', 'do', 'switch', 'case', 'return', 'class', 'struct',
                    'int', 'float', 'double', 'char', 'void', 'bool', 'const', 'static', 'public', 'private',
                    'def', 'import', 'from', 'as', 'True', 'False', 'None', 'print', 'in', 'elif'
                ]
                for word in keywords:
                    pattern = r'\b' + word + r'\b'
                    self.highlighting_rules.append((re.compile(pattern), keyword_format))

                # 5. Dấu ngoặc (Braces)
                self.highlighting_rules.append((re.compile(r'[\{\}\[\]\(\)]'), brace_format))

                # 6. String Prefix (f, r, b, u)
                self.highlighting_rules.append((re.compile(r'\b[fFrRbBuU]+(?=["\'])'), keyword_format))

                # 6.1 String
                self.highlighting_rules.append((re.compile(r'"[^"\\]*(\\.[^"\\]*)*"'), string_format))
                self.highlighting_rules.append((re.compile(r"'[^'\\]*(\\.[^'\\]*)*'"), string_format))
                self.highlighting_rules.append((re.compile(r'#include\s*(<[^>]+>)'), string_format, 1))
                self.highlighting_rules.append((re.compile(r'#include'), keyword_format))

                # 6.2 F-String Post-Processing
                self.highlighting_rules.append((re.compile(r'f"[^"\\]*(\\.[^"\\]*)*"', re.IGNORECASE), "f-string"))
                self.highlighting_rules.append((re.compile(r"f'[^'\\]*(\\.[^'\\]*)*'", re.IGNORECASE), "f-string"))

                # 6.3 Escape sequences
                self.highlighting_rules.append((re.compile(r'\\[\\\'"nrtvfa0-7xUu]'), escape_format))

                self.highlighting_rules.append((re.compile(r'//.*'), comment_format))
                self.highlighting_rules.append((re.compile(r'/\*.*?\*/', re.DOTALL), comment_format))
                if self.lang in ['python', 'nim', 'yaml', 'sh', 'bash', 'rb']:
                    self.highlighting_rules.append((re.compile(r'#.*'), comment_format))

            def highlightBlock(self, text):
                for rule in self.highlighting_rules:
                    pattern = rule[0]
                    text_format = rule[1]
                    group_idx = rule[2] if len(rule) > 2 else 0
                    
                    if text_format == "f-string":
                        for match in pattern.finditer(text):
                            s_start = match.start()
                            s_end = match.end()
                            inside_str = text[s_start:s_end]
                            for m2 in re.finditer(r'(?<!\{)\{([^{}]+)\}(?!\})', inside_str):
                                brace_start = s_start + m2.start()
                                brace_end = s_start + m2.end()
                                inner_text = m2.group(1)
                                inner_start = s_start + m2.start(1)
                                
                                self.setFormat(brace_start, 1, brace_format)
                                self.setFormat(brace_end - 1, 1, brace_format)
                                
                                for inner_rule in self.highlighting_rules:
                                    i_pattern = inner_rule[0]
                                    i_format = inner_rule[1]
                                    i_group = inner_rule[2] if len(inner_rule) > 2 else 0
                                    
                                    if i_format in [string_format, comment_format, "f-string"]:
                                        continue
                                        
                                    for m3 in i_pattern.finditer(inner_text):
                                        if i_group > 0 and m3.group(i_group) is not None:
                                            self.setFormat(inner_start + m3.start(i_group), m3.end(i_group) - m3.start(i_group), i_format)
                                        else:
                                            self.setFormat(inner_start + m3.start(), m3.end() - m3.start(), i_format)
                    else:
                        for match in pattern.finditer(text):
                            if group_idx > 0:
                                if match.group(group_idx) is not None:
                                    self.setFormat(match.start(group_idx), match.end(group_idx) - match.start(group_idx), text_format)
                            else:
                                self.setFormat(match.start(), match.end() - match.start(), text_format)
        class CustomEditor(QPlainTextEdit):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.setFont(QFont("Consolas", 11))
                self.setTabStopDistance(QFontMetricsF(self.font()).horizontalAdvance(' ') * 4)
                self.completer = None
                self.init_completer()
                self.auto_pairs = {
                    '"': '"',
                    "'": "'",
                    "(": ")",
                    "[": "]",
                    "{": "}",
                }

            def resizeEvent(self, event):
                super().resizeEvent(event)
                if hasattr(self, 'line_number_area') and self.line_number_area is not None:
                    cr = self.contentsRect()
                    self.line_number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area.get_width(), cr.height()))

            def init_completer(self):
                self.completer = QCompleter(self)
                self.completer.setCaseSensitivity(Qt.CaseInsensitive)
                self.completer.setFilterMode(Qt.MatchStartsWith)
                self.completer.setCompletionMode(QCompleter.PopupCompletion)
                self.completer.setModelSorting(QCompleter.CaseInsensitivelySortedModel)
                self.completer.setWidget(self)
                self.completer.activated.connect(self.insert_completion)

                popup = self.completer.popup()
                popup.setStyleSheet("""
                    QAbstractItemView {
                        background-color: #252526;
                        color: #d4d4d4;
                        selection-background-color: #094771;
                        selection-color: white;
                        border: 1px solid #007acc;
                        min-width: 220px;
                        font-family: Consolas;
                        font-size: 13px;
                    }
                """)

            def text_under_cursor(self):
                tc = self.textCursor()
                tc.select(tc.WordUnderCursor)
                return tc.selectedText()
            
            def insert_completion(self, completion):
                popup = self.completer.popup()
                index = popup.currentIndex()
                real_name = index.data(Qt.UserRole)

                if not real_name:
                    real_name = completion.split(' ')[0]

                tc = self.textCursor()
                tc.movePosition(tc.MoveOperation.Left, tc.MoveMode.MoveAnchor, len(self.completer.completionPrefix() or ""))
                tc.select(tc.WordUnderCursor)
                tc.removeSelectedText()
                tc.insertText(real_name)
                self.setTextCursor(tc)

                if popup.isVisible():
                    popup.hide()

            def keyPressEvent(self, event):
                key = event.text()
                key_code = event.key()

                if key in self.auto_pairs:
                    tc = self.textCursor()
                    tc.insertText(key + self.auto_pairs[key])
                    tc.movePosition(tc.MoveOperation.Left, tc.MoveMode.MoveAnchor, 1)  
                    self.setTextCursor(tc)
                    QTimer.singleShot(50, self.trigger_completion)
                    event.accept()
                    return

                if key in self.auto_pairs.values():
                    tc = self.textCursor()
                    next_char = self.toPlainText()[tc.position():tc.position()+1]
                    if next_char == key:
                        tc.movePosition(tc.MoveOperation.Right, tc.MoveMode.MoveAnchor, 1)
                        self.setTextCursor(tc)
                        event.accept()
                        return

                if self.completer and self.completer.popup().isVisible():
                    if key_code in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Tab):
                        index = self.completer.popup().currentIndex()
                        if index.isValid():
                            self.insert_completion(index.data(Qt.DisplayRole))
                        else:
                            self.insert_completion(self.completer.currentCompletion())
                        event.accept()
                        return
                    if key_code == Qt.Key_Escape:
                        self.completer.popup().hide()
                        event.accept()
                        return
                    if key_code in (Qt.Key_Up, Qt.Key_Down):
                        super().keyPressEvent(event)
                        return

                if key_code in (Qt.Key_Return, Qt.Key_Enter):
                    tc = self.textCursor()
                    current_line = tc.block().text()
                    prefix_text = current_line[:tc.positionInBlock()]
                    
                    if prefix_text.strip():
                        indent = len(current_line) - len(current_line.lstrip())
                        indent_str = current_line[:indent]
                        
                        last_char = prefix_text.strip()[-1]
                        
                        ext = os.path.splitext(self.property("file_path") or "")[1].lower()
                        lang = self.window()._get_lang_from_ext(ext)
                        
                        if lang in ['python', 'nim'] and last_char == ':':
                            super().keyPressEvent(event)
                            self.insertPlainText(indent_str + "    ")
                            return
                            
                        elif lang in ['cpp', 'c', 'java', 'js', 'javascript', 'csharp', 'php'] and last_char == '{':
                            super().keyPressEvent(event)
                            self.insertPlainText(indent_str + "    ")
                            
                            full_text_after = self.toPlainText()[tc.position():]
                            if '}' not in full_text_after.split('\n')[0]: 
                                tc2 = self.textCursor()
                                pos_before_close = tc2.position()
                                self.insertPlainText("\n" + indent_str + "}")
                                tc2.setPosition(pos_before_close)
                                self.setTextCursor(tc2)
                            return
                        
                        else:
                            super().keyPressEvent(event)
                            self.insertPlainText(indent_str)
                            return
                    else:
                        super().keyPressEvent(event)
                        return

                super().keyPressEvent(event)

                lang = self.window()._get_lang_from_ext(os.path.splitext(self.property("file_path") or "")[1].lower())
                if lang in ["cpp", "c"]:
                    trigger_chars = ['"', "'", '(', '[', '{', '<', '.', '_', ' ', ':', '-', '=']
                else:
                    trigger_chars = ['"', "'", '(', '[', '{', '<', '.', '_', ' ', '-', '=']
                if event.text() in trigger_chars or event.text().isalnum() or key_code == Qt.Key_Backspace:
                    QTimer.singleShot(50, self.trigger_completion)

            def trigger_completion(self):
                prefix = self.text_under_cursor().strip()
                lang = self.window()._get_lang_from_ext(os.path.splitext(self.property("file_path") or "")[1].lower())
                
                if not prefix and self.toPlainText():
                    tc = self.textCursor()
                    if tc.position() > 0:
                        prev_char = self.toPlainText()[tc.position()-1]
                        if prev_char not in ['(', '[', '{', '<', ' ', '.', ':', '=']:
                            if self.completer.popup().isVisible():
                                self.completer.popup().hide()
                            return
                        if lang in ["cpp", "c"]:
                            if prev_char not in ['(', '[', '{', '<', ' ', '.', '=']:
                                if self.completer.popup().isVisible():
                                    self.completer.popup().hide()
                                return
                            
                elif not prefix:
                    if self.completer.popup().isVisible():
                        self.completer.popup().hide()
                    return

                cursor = self.textCursor()
                cursor_pos = cursor.position()
                full_text = self.toPlainText()
                
                ext = os.path.splitext(self.property("file_path") or "")[1].lower()
                lang = self.window()._get_lang_from_ext(ext)

                suggestions = self.window().get_buffer_symbols(full_text, cursor_pos, prefix, lang)

                if suggestions:
                    model = QStandardItemModel(self)
                    for real_name, display in suggestions:
                        item = QStandardItem(display)
                        item.setData(real_name, Qt.UserRole)  
                        model.appendRow(item)

                    self.completer.setModel(model)
                    self.completer.setCompletionPrefix(prefix)

                    rect = self.cursorRect()
                    rect.translate(0, self.fontMetrics().height() + 4)
                    rect.setWidth(250)

                    self.completer.complete(rect)
                    popup = self.completer.popup()
                    popup.raise_()
                    popup.activateWindow()
                    popup.show()
                else:
                    if self.completer.popup().isVisible():
                        self.completer.popup().hide()
            
        editor = CustomEditor()
        editor.setPlainText(content)
        if file_path:
            editor.setProperty("file_path", os.path.abspath(file_path))
        
        editor.textChanged.connect(self.on_editor_text_changed)

        editor.line_number_area = LineNumberArea(editor)

        ext = os.path.splitext(file_path)[1].lower() if file_path else ""
        lang = self._get_lang_from_ext(ext)
        editor.highlighter = CodeHighlighter(editor.document(), lang)

        editor.textChanged.connect(lambda: self.auto_save_specific_editor(editor))
        editor.textChanged.connect(self.on_text_changed_for_syntax)
        editor.cursorPositionChanged.connect(self.on_cursor_activity)
        editor.cursorPositionChanged.connect(self.update_cursor_position)
        
        return editor
    def on_tab_changed(self, index):
        if index >= 0:
            self.editor = self.tabFile.widget(index)
            self.current_file = self.editor.property("file_path")
            if self.editor:
                self.last_current_text = self.editor.toPlainText()
                if self.syntax_timer:
                    self.syntax_timer.start(100)
        else:
            self.editor = None
            self.current_file = None
            if self.syntax_view:
                self.syntax_view.clear()
                self.syntax_view.hide()
        self.update_cursor_position()
        
    def _load_config(self):
        path_json = self.get_json_path()
        config = {"file_used": {}, "theme_color": self.theme_color, "language": self.language}
        if not path_json.exists() or path_json.stat().st_size == 0:
            return config
        try:
            with open(path_json, "r", encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict):
                    config.update(data)
                    if "file_used" not in config or config["file_used"] is None:
                        config["file_used"] = {}
                return config
        except (json.JSONDecodeError, Exception) as e:
            print(f"Config load error: {e}")
            return config

    def _save_config(self, config):
        try:
            path_json = self.get_json_path()
            with open(path_json, "w", encoding='utf-8') as f:
                json.dump(config, f, indent=4)
        except Exception as e:
            print(f"Config save error: {e}")

    def make_json_file(self):
        config = self._load_config()
        if "file_used" not in config:
            config["file_used"] = {}
        if "theme_color" in config:
            self.theme_color = config["theme_color"]
        else:
            config["theme_color"] = self.theme_color
        if "language" in config:
            self.language = config["language"]
        else:
            config["language"] = self.language
        self.setStyleSheet(self.styleSheet().replace("#1e1e1e", self.theme_color))
        self._save_config(config)

    

    
    

    def rename_file(self):
        idx = self.tabFile.currentIndex()
        if idx < 0:
            QMessageBox.warning(self, "Lỗi", "Chưa có tab nào để đổi tên.")
            return

        editor = self.tabFile.widget(idx)
        old_path = editor.property("file_path")
        
        if not old_path or not os.path.exists(old_path):
            QMessageBox.warning(self, "Lỗi", "Chỉ có thể đổi tên file đã được lưu trên đĩa.")
            return

        rename_dialog = RenameDialog(self)
        rename_dialog.line_edit.setText(os.path.basename(old_path))
        
        if rename_dialog.exec_() == QDialog.Accepted:
            new_name = rename_dialog.get_new_name()
            if not new_name:
                return
            
            old_dir = os.path.dirname(old_path)
            new_path = os.path.join(old_dir, new_name)
            
            if os.path.exists(new_path):
                QMessageBox.warning(self, "Lỗi", "Tên file đã tồn tại.")
                return
            
            try:
                os.rename(old_path, new_path)
                
                editor.setProperty("file_path", new_path)
                self.tabFile.setTabText(idx, new_name)
                
                config = self._load_config()
                if old_path in config.get("file_used", {}):
                    del config["file_used"][old_path]
                config["file_used"][new_path] = new_name
                self._save_config(config)
                
                QMessageBox.information(self, "Thành công", f"Đã đổi tên file thành {new_name}")
            except Exception as e:
                QMessageBox.critical(self, "Lỗi", f"Không thể đổi tên file: {str(e)}")

    def toggle_auto_save(self, checked):
        self.auto_save_enabled = checked
        config = self._load_config()
        config["auto_save"] = checked
        self._save_config(config)
        print(f"Auto-save is now {'ON' if checked else 'OFF'}")

    def about_app(self):
        if self.language == "en":
            text = "VNCode IDE\nVersion 1.0\nAuthor: Nguyễn Trường Lâm\nEmail: nguyenvannghia1952tg@gmail.com\nteam: VNCore Lab"
        else:
            text = "VNCode IDE\nPhiên bản 1.0\nTác giả: Nguyễn Trường Lâm\nEmail: nguyenvannghia1952tg@gmail.com\nteam: VNCore Lab"
        QMessageBox.information(self, "About VNCode", text)

    def find_file_path(self, file_name):
        search_dir = os.path.dirname(os.path.abspath(__file__))
        for root, dirs, files in os.walk(search_dir):
            for f in files:
                if f == file_name:
                    return os.path.join(root, f)
        return None

    def on_editor_text_changed(self):
        """Triggered mỗi khi bất kỳ editor nào thay đổi nội dung"""
        if self.auto_save_enabled:
            # Lưu ngay lập tức theo yêu cầu của người dùng
            self.auto_save_trigger()

    def auto_save_trigger(self):
        """Thực thi việc save tự động"""
        editor = self.tabFile.currentWidget()
        if editor:
            self.auto_save_specific_editor(editor)

    def auto_save_specific_editor(self, editor):
        file_path = editor.property("file_path")
        if not file_path or not os.path.exists(file_path):
            return
            
        text = editor.toPlainText()
        try:
            # Chỉ lưu nếu thực sự có thay đổi (tùy chọn, ở đây lưu luôn cho chắc)
            with open(file_path, "w", encoding='utf-8') as f:
                f.write(text)
        
        except Exception as e:
            print(f"Auto-save error: {e}")

    def on_cursor_activity(self):
        if self.syntax_view:
            self.syntax_view.hide()

    def on_text_changed_for_syntax(self):
        if self.syntax_view:
            self.syntax_view.hide()
        if self.syntax_timer:
            self.syntax_timer.start(1000)

    def update_syntax_panel(self):
        if not self.syntax_view:
            return
        editor = self.tabFile.currentWidget()
        if not editor:
            self.syntax_view.clear()
            self.syntax_view.hide()
            return
        file_path = editor.property("file_path")
        lang = None
        if file_path:
            ext = os.path.splitext(str(file_path))[1].lower()
            lang = self.ext_to_lang.get(ext)
        if not lang:
            self.syntax_view.clear()
            self.syntax_view.hide()
            return
        info = SYNTAX_INFO.get(lang, "")
        if not info:
            self.syntax_view.clear()
            self.syntax_view.hide()
            return

        # Lấy từ hiện tại tại vị trí cursor
        cursor = editor.textCursor()
        cursor.select(QTextCursor.WordUnderCursor)
        current_word = cursor.selectedText().strip()

        # Lọc keywords
        parts = info.split(",")
        keywords = [p.strip() for p in parts if p.strip()]

        if current_word:
            filtered = [k for k in keywords if current_word.lower() in k.lower()]
        else:
            filtered = keywords

        self.syntax_view.clear()
        if current_word:
            self.syntax_view.addItem(f"\U0001f50d Tìm: '{current_word}' — Ngôn ngữ: {lang}")
        else:
            self.syntax_view.addItem(f"Ngôn ngữ: {lang}")

        if filtered:
            for k in filtered:
                self.syntax_view.addItem(k)
        else:
            self.syntax_view.addItem("(Không tìm thấy cú pháp phù hợp)")

        self.syntax_view.show()

    def insert_syntax_from_list(self, item):
        text = item.text()
        if text.startswith("Ngôn ngữ:") or text.startswith("\U0001f50d") or text.startswith("(Không tìm"):
            return
        editor = self.tabFile.currentWidget()
        if not editor:
            return
        cursor = editor.textCursor()
        if not text.endswith(" "):
            text = text + " "
        cursor.insertText(text)
        editor.setTextCursor(cursor)


    def close_tab(self, index):
        editor = self.tabFile.widget(index)
        file_path = editor.property("file_path")
        
        self.tabFile.removeTab(index)
        
        if file_path:
            config = self._load_config()
            abs_path = os.path.abspath(file_path)
            if abs_path in config.get("file_used", {}):
                del config["file_used"][abs_path]
                self._save_config(config)
        
        self.check_no_file()



    def auto_open_file_recent(self):
        config = self._load_config()
        opened_any = False
        for file_path, file_name in config.get("file_used", {}).items():
            if os.path.exists(file_path):
                try:
                    with open(file_path, "r", encoding='utf-8') as f:
                        content = f.read()
                    editor = self.create_editor(file_path, content)
                    
                    self.tabFile.addTab(editor, file_name)
                    
                    opened_any = True
                except Exception as e:
                    print(f"Error opening recent file {file_path}: {e}")
        
        if opened_any:
            self.tabFile.setCurrentIndex(0)
        
        
        self.check_no_file()

    def delete_file(self):
        idx = self.tabFile.currentIndex()
        if idx < 0:
            return

        editor = self.tabFile.widget(idx)
        file_path = editor.property("file_path")
        
        if not file_path:
            self.close_tab(idx)
            return
        msg = QMessageBox(self)
        msg.setWindowTitle("Xác nhận xóa")
        msg.setText(f"Bạn có chắc chắn muốn xóa vĩnh viễn file này?\n{file_path}")
        msg.setIcon(QMessageBox.Warning)
        yes_btn = msg.addButton("Xóa", QMessageBox.YesRole)
        no_btn = msg.addButton("Hủy", QMessageBox.NoRole)
        msg.exec_()

        if msg.clickedButton() == yes_btn:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                self.close_tab(idx)
            except Exception as e:
                QMessageBox.critical(self, "Lỗi", f"Không thể xóa file:\n{str(e)}")

    def create_terminal_widget(self):
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.terminal_tabs = QTabWidget(container)
        self.terminal_output = QTextEdit(container)
        self.terminal_output.setReadOnly(True)
        layout.addWidget(self.terminal_tabs, 0)
        layout.addWidget(self.terminal_output, 1)
        return container

    def ensure_terminal_tab(self, name):
        index = -1
        for i in range(self.terminal_tabs.count()):
            if self.terminal_tabs.tabText(i) == name:
                index = i
                break
        if index == -1:
            index = self.terminal_tabs.addTab(QWidget(), name)
        self.terminal_tabs.setCurrentIndex(index)

    def append_terminal_output(self, text):
        if not self.terminal_container:
            return
        self.terminal_container.show()
        self.terminal_output.append(text)

    def register_extension_widget(self, name, widget):
        if not self.extension_container or not self.extension_tabs:
            return
        index = -1
        for i in range(self.extension_tabs.count()):
            if self.extension_tabs.tabText(i) == name:
                index = i
                break
        if index == -1:
            index = self.extension_tabs.addTab(widget, name)
        else:
            self.extension_tabs.removeTab(index)
            index = self.extension_tabs.addTab(widget, name)
        self.extension_tabs.setCurrentIndex(index)
        self.extension_container.show()

    def _get_run_info(self, file_path):
        ext = os.path.splitext(str(file_path))[1].lower()
        lang = self.ext_to_lang.get(ext)
        if not lang:
            return None, None
        run_info = TYPE_FILE_RUN.get(lang)
        return lang, run_info

    def _start_process(self, program, args, on_output, on_finished):
        process = QProcess(self)
        process.setProgram(program)
        process.setArguments(args)
        process.setProcessChannelMode(QProcess.MergedChannels)
        process.readyReadStandardOutput.connect(on_output)
        process.readyReadStandardError.connect(on_output)
        process.finished.connect(on_finished)
        process.start()
        return process

    def run_current_file(self):
        if not self.tabFile.currentWidget():
            QMessageBox.warning(self, "Warning", "No file is open.")
            return

        editor = self.tabFile.currentWidget()
        file_path = editor.property("file_path")
        if not file_path:
            QMessageBox.warning(self, "Warning", "File chưa lưu. Save trước khi run.")
            return

        # Đảm bảo console đã được tạo và hiển thị
        self.show_console()

        # Xác định extension và lấy lệnh chạy
        ext = Path(file_path).suffix.lower()
        run_syntax = TYPE_RUN_SYNTAX.get(ext)
        if not run_syntax:
            QMessageBox.warning(self, "Warning", f"Không hỗ trợ chạy file '{ext}'.")
            return

        # Tính tên output cho compiled languages
        file_name_no_ext = Path(file_path).stem
        out_path = str(Path(file_path).parent / file_name_no_ext)
        if os.name == 'nt':
            out_path += '.exe'

        # Build danh sách args từ TYPE_RUN_SYNTAX
        args = [a.format(file=file_path, out=out_path) for a in run_syntax]
        program = args[0]
        program_args = args[1:]

        # Dừng process cũ nếu đang chạy
        if self.process and self.process.state() != QProcess.NotRunning:
            self.process.kill()
            self.process.waitForFinished(1000)

        # Env UTF-8 cho child process
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONIOENCODING", "utf-8")
        env.insert("PYTHONUTF8", "1")

        # Kiểm tra nếu là compiled language (có {out} trong syntax = cần compile rồi run)
        compiled_exts = ['.cpp', '.c', '.rs']
        if ext in compiled_exts:
            self.terminal_output.append_output(f"Compiling: {program} {' '.join(program_args)}\n")
            compile_proc = QProcess(self)
            compile_proc.setProcessEnvironment(env)
            compile_proc.setProcessChannelMode(QProcess.MergedChannels)
            compile_proc.readyReadStandardOutput.connect(self.on_process_output)
            compile_proc.readyReadStandardError.connect(self.on_process_output)
            self.process = compile_proc

            def on_compile_done(exit_code, exit_status):
                if exit_code != 0:
                    self.terminal_output.append_output("Compilation failed.\n")
                    self.process = None
                    return
                self.terminal_output.append_output(f"Running: {out_path}\n")
                run_proc = QProcess(self)
                run_proc.setProcessEnvironment(env)
                run_proc.setProcessChannelMode(QProcess.MergedChannels)
                run_proc.readyReadStandardOutput.connect(self.on_process_output)
                run_proc.readyReadStandardError.connect(self.on_process_output)
                run_proc.finished.connect(self.on_process_finished)
                self.process = run_proc
                run_proc.start(out_path)

            compile_proc.finished.connect(on_compile_done)
            compile_proc.start(program, program_args)
        else:
            # Interpreted language: run directly
            self.terminal_output.append_output(f"Running: {program} {' '.join(program_args)}\n")
            self.process = QProcess(self)
            self.process.setProcessEnvironment(env)
            self.process.setProcessChannelMode(QProcess.MergedChannels)
            self.process.readyReadStandardOutput.connect(self.on_process_output)
            self.process.readyReadStandardError.connect(self.on_process_output)
            self.process.finished.connect(self.on_process_finished)
            self.process.start(program, program_args)

    def on_process_output(self):
        if not self.process:
            return
        data = self.process.readAllStandardOutput().data()
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = data.decode("cp65001")
            except UnicodeDecodeError:
                text = data.decode("latin-1")
        if text:
            self.terminal_output.append_output(text.replace('\r', ''))

    def on_process_finished(self, exit_code, exit_status):
        self.terminal_output.append_output(f"\nProcess finished with exit code {exit_code}\n")
        self.process = None

    def stop_process(self):
        if self.process and self.process.state() == QProcess.Running:
            self.process.kill()
            self.terminal_output.append_output("\n[Stopped by user]\n")
            self.process = None

    def open_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open File", "", "All Files (*)")
        if not file_path:
            return

        abs_path = os.path.abspath(file_path)
        
        for i in range(self.tabFile.count()):
            widget = self.tabFile.widget(i)
            if widget.property("file_path") == abs_path:
                self.tabFile.setCurrentIndex(i)
                return

        try:
            with open(file_path, "r", encoding='utf-8') as f:
                content = f.read()
            
            file_name = os.path.basename(file_path)
            
            curr_idx = self.tabFile.currentIndex()
            if curr_idx >= 0:
                curr_editor = self.tabFile.currentWidget()
                if self.tabFile.tabText(curr_idx) == "Untitled" and not curr_editor.toPlainText():
                    curr_editor.setPlainText(content)
                    curr_editor.setProperty("file_path", abs_path)
                    self.tabFile.setTabText(curr_idx, file_name)
                    tab_index = curr_idx
                else:
                    editor = self.create_editor(file_path, content)
                    
                    tab_index = self.tabFile.addTab(editor, file_name)
            else:
                editor = self.create_editor(file_path, content)
                
                tab_index = self.tabFile.addTab(editor, file_name)
            
            self.tabFile.setCurrentIndex(tab_index)
            
            config = self._load_config()
            config["file_used"][abs_path] = file_name
            self._save_config(config)
            
            self.check_no_file()
        except Exception as e:
            print(f"Open file error: {e}")

    def get_json_path(self):
        return Path(__file__).resolve().parent / "config_VNCode.json"
    
    def check_no_file(self):
        if self.tabFile.count() == 0:
            if self.label is None:
                self.label = QLabel("Vui lòng chọn New hoặc Open để bắt đầu.")
                self.label.setAlignment(Qt.AlignCenter)
                self.label.setStyleSheet("color: #ac2222; font-size: 16px;")
                self.mainlayout.addWidget(self.label, 1)
            else:
                self.label.show()
        else:
            if self.label is not None:
                self.label.hide()
                
    def clean_label(self):
        if self.label:
            self.label.hide()
    
    def new_file(self):
        try:
            editor = self.create_editor(content="")
            tab_index = self.tabFile.addTab(editor, "Untitled")
            self.tabFile.setCurrentIndex(tab_index)
            self.check_no_file()
        except Exception as e:
            print(e)
    
    def save_file(self):
        idx = self.tabFile.currentIndex()
        if idx < 0:
            QMessageBox.warning(self, "Lỗi", "Chưa có file nào được mở để lưu.")
            return
            
        editor = self.tabFile.currentWidget()
        current_path = editor.property("file_path")
        
        try:
            if current_path:
                with open(current_path, "w", encoding='utf-8') as f:
                    f.write(editor.toPlainText())
            else:
                file_path, _ = QFileDialog.getSaveFileName(self, "Save File", "", self._build_save_filter())
                
                if file_path:
                    abs_path = os.path.abspath(file_path)
                    file_name = os.path.basename(file_path)
                    
                    with open(file_path, "w", encoding='utf-8') as f:
                        f.write(editor.toPlainText())
                    
                    editor.setProperty("file_path", abs_path)
                    self.tabFile.setTabText(idx, file_name)
                    
                    config = self._load_config()
                    config["file_used"][abs_path] = file_name
                    self._save_config(config)
                else:
                    return
            self.clean_label()
        except Exception as e:
            print(f"Save error: {e}")
    
    def save_as_file(self):
        idx = self.tabFile.currentIndex()
        if idx < 0:
            QMessageBox.warning(self, "Lỗi", "Chưa có file nào được mở để lưu.")
            return
            
        editor = self.tabFile.currentWidget()
        try:
            file_path, _ = QFileDialog.getSaveFileName(self, "Save as File", "", self._build_save_filter())
            if file_path:
                abs_path = os.path.abspath(file_path)
                file_name = os.path.basename(file_path)
                with open(file_path, "w", encoding='utf-8') as f:
                    f.write(editor.toPlainText())
                
                editor.setProperty("file_path", abs_path)
                self.tabFile.setTabText(idx, file_name)
                
                config = self._load_config()
                config["file_used"][abs_path] = file_name
                self._save_config(config)
        except Exception as e:
            print(f"Save As error: {e}")

    def _build_save_filter(self):
        parts = []
        for lang, exts in TYPE_FILE.items():
            ext_str = " ".join([f"*{e}" for e in exts])
            parts.append(f"{lang} Files ({ext_str})")
        parts.append("HTML Files (*.html)")
        parts.append("CSS Files (*.css)")
        parts.append("JavaScript Files (*.js)")
        parts.append("Markdown Files (*.md)")
        parts.append("All Files (*)")
        return ";;".join(parts)

    def exit_app(self):
        self.close()

    def open_settings(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Settings")
        layout = QVBoxLayout(dialog)
        color_label = QLabel("Theme color:", dialog)
        layout.addWidget(color_label)
        color_combo = QComboBox(dialog)
        color_combo.addItem("Dark", "#1e1e1e")
        color_combo.addItem("Blue", "#001f3f")
        current_index = 0
        for i in range(color_combo.count()):
            if color_combo.itemData(i) == self.theme_color:
                current_index = i
                break
        color_combo.setCurrentIndex(current_index)
        layout.addWidget(color_combo)
        lang_label = QLabel("Language:", dialog)
        layout.addWidget(lang_label)
        lang_combo = QComboBox(dialog)
        lang_combo.addItem("Tiếng Việt", "vi")
        lang_combo.addItem("English", "en")
        if self.language == "en":
            lang_combo.setCurrentIndex(1)
        else:
            lang_combo.setCurrentIndex(0)
        layout.addWidget(lang_combo)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, dialog)
        layout.addWidget(buttons)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        if dialog.exec_() == QDialog.Accepted:
            self.theme_color = color_combo.currentData()
            self.language = lang_combo.currentData()
            self.setStyleSheet(self.styleSheet().replace("#1e1e1e", self.theme_color))
            config = self._load_config()
            config["theme_color"] = self.theme_color
            config["language"] = self.language
            self._save_config(config)

    def run_multicore(self):
        file_path = self.get_current_file_path()
        if not file_path:
            QMessageBox.warning(self, "Lỗi", "Không có file nào đang được mở.")
            return
        lang, run_info = self._get_run_info(file_path)
        if not run_info:
            QMessageBox.warning(self, "Lỗi", f"Không hỗ trợ chạy đa nhân cho ngôn ngữ '{lang or 'unknown'}'.")
            return
        # Compiled languages cần compile trước
        if "run" in run_info:
            QMessageBox.warning(self, "Lỗi", f"Không hỗ trợ chạy đa nhân cho ngôn ngữ biên dịch ({lang}).")
            return
        count, ok = QInputDialog.getInt(self, "Run Multi-core", "Số tiến trình:", 2, 1, max(os.cpu_count() or 4, 2))
        if not ok or count <= 0:
            return
        self.ensure_terminal_tab("Multi-core")
        self.terminal_output.clear()
        self.terminal_container.show()
        for p in self.multi_processes:
            if p.state() != QProcess.NotRunning:
                p.kill()
        self.multi_processes = []

        out_path = os.path.splitext(str(file_path))[0]
        cmd = run_info["cmd"]
        args = [a.replace("{file}", str(file_path)).replace("{out}", out_path) for a in run_info["args"]]

        for i in range(count):
            process = QProcess(self)
            process.setProgram(cmd)
            process.setArguments(args)
            process.setProcessChannelMode(QProcess.MergedChannels)
            index = i
            def handle_output(idx=index, proc=process):
                data_out = proc.readAllStandardOutput().data().decode("utf-8", errors="ignore")
                data_err = proc.readAllStandardError().data().decode("utf-8", errors="ignore")
                text = ""
                if data_out:
                    text += f"[{idx}] {data_out}"
                if data_err:
                    text += f"[{idx}] {data_err}"
                if text:
                    self.append_terminal_output(text)
            process.readyReadStandardOutput.connect(handle_output)
            process.readyReadStandardError.connect(handle_output)
            def handle_finished(idx=index):
                self.append_terminal_output(f"Process {idx} finished.")
            process.finished.connect(handle_finished)
            self.multi_processes.append(process)
            process.start()

    
    
    def auto_check_current_file_used(self):
        config = self._load_config()
        file_used = config.get("file_used", {})
        valid_files = {path: name for path, name in file_used.items() if os.path.exists(path)}
        
        if len(valid_files) != len(file_used):
            config["file_used"] = valid_files
            self._save_config(config)


    def collect_symbols_from_project(self, current_file: str, ext: str, prefix: str, lang_key: str) -> list[str]:
        """
        Thu thập symbol từ các file khác trong cùng thư mục (và subfolder),
        giống cách Sublime Text quét toàn project để gợi ý.
        """
        try:
            if not current_file or not prefix:
                return []
            base = Path(current_file).resolve().parent
        except Exception:
            return []

        prefix_lower = prefix.lower()
        max_files = 80  # tránh quét quá nhiều file gây lag
        collected: list[str] = []
        visited = 0

        try:
            for p in base.rglob(f"*{ext}"):
                if not p.is_file():
                    continue
                try:
                    if p.resolve() == Path(current_file).resolve():
                        continue
                except Exception:
                    pass

                visited += 1
                if visited > max_files:
                    break

                try:
                    text = p.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue

                # Python: sử dụng get_buffer_symbols đã có AST
                if ext == ".py":
                    try:
                        buf_syms = self.get_buffer_symbols(text, lang="python", prefix=prefix)
                        # Lấy display_label (s[1]) để hiển thị trong list project symbols
                        collected.extend([s[1] for s in buf_syms if s[0].lower().startswith(prefix_lower)])
                    except Exception:
                        pass
                elif ext in [".c", ".cpp", ".cc", ".h", ".hpp"]:
                    try:
                        cpp_syms = self.get_buffer_symbols_cpp(text, len(text), prefix)
                        collected.extend([s[0] for s in cpp_syms if s[0].lower().startswith(prefix_lower)])
                    except Exception:
                        pass
                # Ngôn ngữ khác: dùng buffer_symbols chung
                else:
                    try:
                        buf_syms = self.get_buffer_symbols(text, lang=lang_key, prefix=prefix)
                        collected.extend([s for s in buf_syms if s[0].lower().startswith(prefix_lower)])
                    except Exception:
                        pass
        except Exception:
            return []

        # dedupe, giữ thứ tự
        seen = set()
        out: list[str] = []
        for s in collected:
            key = s.lower()
            if key not in seen:
                seen.add(key)
                out.append(s)
        return out
        
def run():
    app = QApplication(sys.argv)
    screen = Main()
    screen.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    run()

#2025 VNCORE LAB(alias of Nguyễn Trường Lâm)
#command build: pyinstaller --onedir --noconfirm --icon="icon_VNCode.ico" --add-data "fill_module.py;." --add-data "list_module.py;." --add-data "icon_VNCode.ico;." --add-data "close_hover.svg;." --add-data "close.svg;." run.py