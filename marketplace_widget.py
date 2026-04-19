"""
Marketplace Widget for VNCode IDE.
Provides a PyQt5 UI to browse, search, install and manage extensions from Open VSX Registry.
"""

from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
import os
import logging

import openvsx_api
import extension_manager

try:
    from run import logger
except ImportError:
    logger = logging.getLogger('vncode')

class UpdateCheckWorker(QThread):
    """Background thread for checking extension updates."""
    updates_found = pyqtSignal(list)  # list of (namespace, name, current_ver, latest_info)

    def __init__(self, installed_extensions):
        super().__init__()
        self.installed_extensions = installed_extensions

    def run(self):
        updates = []
        for meta in self.installed_extensions:
            namespace = meta.get("namespace", "")
            name = meta.get("name", "")
            current_ver = meta.get("version", "")
            
            latest_info = openvsx_api.check_extension_updates(namespace, name, current_ver)
            if latest_info:
                updates.append((namespace, name, current_ver, latest_info))
        
        self.updates_found.emit(updates)

class SearchWorker(QThread):
    """Background thread for searching extensions."""
    results_ready = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, query, offset=0, size=15, sort_by="relevance", sort_order="desc", category=""):
        super().__init__()
        self.query = query
        self.offset = offset
        self.size = size
        self.sort_by = sort_by
        self.sort_order = sort_order
        self.category = category

    def run(self):
        try:
            data = openvsx_api.search_extensions(
                self.query, self.offset, self.size, 
                self.sort_by, self.sort_order, self.category
            )
            if data:
                self.results_ready.emit(data)
            else:
                self.error_occurred.emit("Không thể kết nối đến Open VSX Registry.")
        except Exception as e:
            self.error_occurred.emit(str(e))

class InstallWorker(QThread):
    """Background thread for installing an extension."""
    progress = pyqtSignal(int, int)  # downloaded, total
    finished = pyqtSignal(bool, str)  # success, message

    def __init__(self, ext_info):
        super().__init__()
        self.ext_info = ext_info

    def run(self):
        try:
            def on_progress(downloaded, total):
                self.progress.emit(downloaded, total)

            success = extension_manager.install_extension(self.ext_info, on_progress)
            if success:
                name = self.ext_info.get("displayName", self.ext_info.get("name", ""))
                self.finished.emit(True, f"Đã cài đặt {name} thành công!")
            else:
                self.finished.emit(False, "Cài đặt thất bại.")
        except Exception as e:
            self.finished.emit(False, str(e))

class IconLoader(QThread):
    """Background thread for loading extension icons."""
    icon_ready = pyqtSignal(str, str)  # ext_id, local_path

    def __init__(self, ext_id, icon_url):
        super().__init__()
        self.ext_id = ext_id
        self.icon_url = icon_url

    def run(self):
        cache_dir = str(extension_manager.get_cache_dir())
        path = openvsx_api.download_icon(self.icon_url, cache_dir)
        if path:
            self.icon_ready.emit(self.ext_id, path)

class ExtensionCard(QFrame):
    """A single extension card in the results list."""
    install_clicked = pyqtSignal(dict)  # ext_info
    uninstall_clicked = pyqtSignal(str, str)  # namespace, name

    def __init__(self, ext_info: dict, parent=None):
        super().__init__(parent)
        self.ext_info = ext_info
        self.namespace = ext_info.get("namespace", "")
        self.name = ext_info.get("name", "")
        self.ext_id = f"{self.namespace}.{self.name}"

        self.setObjectName("extensionCard")
        self.setStyleSheet("""
            #extensionCard {
                background-color: #252526;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                padding: 0px;
                margin: 2px 0px;
            }
            #extensionCard:hover {
                border-color: #007acc;
                background-color: #2a2d2e;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        # Icon
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(48, 48)
        self.icon_label.setStyleSheet("""
            background-color: #3c3c3c; 
            border-radius: 6px;
            border: none;
        """)
        self.icon_label.setAlignment(Qt.AlignCenter)

        # Default icon placeholder
        self.icon_label.setText("PKG")
        self.icon_label.setStyleSheet("""
            background-color: #3c3c3c; 
            border-radius: 6px; 
            font-size: 16px;
            border: none;
        """)
        layout.addWidget(self.icon_label)

        # Info section
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        # Title row
        title_row = QHBoxLayout()
        title_row.setSpacing(6)

        display_name = ext_info.get("displayName", self.name)
        title_label = QLabel(display_name)
        title_label.setStyleSheet("color: #ffffff; font-size: 14px; font-weight: bold; border: none;")
        title_row.addWidget(title_label)

        # Rating
        rating = ext_info.get("averageRating", 0)
        if rating and rating > 0:
            rating_label = QLabel(f"⭐ {rating:.1f}")
            rating_label.setStyleSheet("color: #e2b93d; font-size: 11px; border: none;")
            title_row.addWidget(rating_label)

        title_row.addStretch()
        info_layout.addLayout(title_row)

        # Namespace + version
        version = ext_info.get("version", "")
        meta_text = f"{self.namespace}"
        if version:
            meta_text += f" · v{version}"
        meta_label = QLabel(meta_text)
        meta_label.setStyleSheet("color: #858585; font-size: 11px; border: none;")
        info_layout.addWidget(meta_label)

        # Extension type badge (NEW)
        ext_type = ext_info.get("type")
        if ext_type:
            try:
                from extension_types import (
                    ExtensionType, get_type_display_name, 
                    get_type_color, get_type_description
                )
                ext_type_obj = ExtensionType(ext_type)
                type_badge_layout = QHBoxLayout()
                type_badge_layout.setSpacing(4)
                
                type_display = get_type_display_name(ext_type_obj)
                type_color = get_type_color(ext_type_obj)
                type_desc = get_type_description(ext_type_obj)
                
                type_badge = QLabel(f"● {type_display}")
                type_badge.setStyleSheet(f"color: {type_color}; font-size: 10px; border: none; font-weight: bold;")
                type_badge.setToolTip(type_desc)
                type_badge_layout.addWidget(type_badge)
                type_badge_layout.addStretch()
                
                info_layout.addLayout(type_badge_layout)
            except Exception:
                pass  # Skip if extension_types not available

        # Description
        desc = ext_info.get("description", "")
        if len(desc) > 100:
            desc = desc[:97] + "..."
        desc_label = QLabel(desc)
        desc_label.setStyleSheet("color: #b0b0b0; font-size: 12px; border: none;")
        desc_label.setWordWrap(True)
        info_layout.addWidget(desc_label)

        # Download count
        dl_count = ext_info.get("downloadCount", 0)
        if dl_count:
            dl_label = QLabel(f"📥 {openvsx_api.format_download_count(dl_count)}")
            dl_label.setStyleSheet("color: #6e9e6e; font-size: 11px; border: none;")
            info_layout.addWidget(dl_label)

        layout.addLayout(info_layout, 1)

        # Action button
        btn_layout = QVBoxLayout()
        btn_layout.setAlignment(Qt.AlignCenter)

        installed = extension_manager.is_installed(self.namespace, self.name)
        installed_ver = extension_manager.get_installed_version(self.namespace, self.name)

        if installed:
            if installed_ver and version and installed_ver != version:
                # Update available
                self.action_btn = QPushButton("Update")
                self.action_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #0e7a0d;
                        color: #ffffff;
                        border: none;
                        padding: 6px 16px;
                        border-radius: 3px;
                        font-size: 12px;
                        font-weight: bold;
                    }
                    QPushButton:hover { background-color: #12961c; }
                    QPushButton:pressed { background-color: #0a5e0a; }
                """)
                self.action_btn.clicked.connect(lambda: self.install_clicked.emit(self.ext_info))
            else:
                self.action_btn = QPushButton("Uninstall")
                self.action_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #5a1d1d;
                        color: #e8a0a0;
                        border: 1px solid #6e3030;
                        padding: 6px 12px;
                        border-radius: 3px;
                        font-size: 12px;
                    }
                    QPushButton:hover { background-color: #7a2d2d; border-color: #8e4040; }
                    QPushButton:pressed { background-color: #4a1515; }
                """)
                self.action_btn.clicked.connect(
                    lambda: self.uninstall_clicked.emit(self.namespace, self.name))
        else:
            self.action_btn = QPushButton("Install")
            self.action_btn.setStyleSheet("""
                QPushButton {
                    background-color: #0e639c;
                    color: #ffffff;
                    border: none;
                    padding: 6px 16px;
                    border-radius: 3px;
                    font-size: 12px;
                    font-weight: bold;
                }
                QPushButton:hover { background-color: #1177bb; }
                QPushButton:pressed { background-color: #094771; }
            """)
            self.action_btn.clicked.connect(lambda: self.install_clicked.emit(self.ext_info))

        btn_layout.addWidget(self.action_btn)
        layout.addLayout(btn_layout)

    def set_icon(self, pixmap: QPixmap):
        """Set the extension icon from a loaded pixmap."""
        scaled = pixmap.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.icon_label.setPixmap(scaled)
        self.icon_label.setText("")
        self.icon_label.setStyleSheet("""
            background-color: transparent; 
            border-radius: 6px;
            border: none;
        """)

# ─────────────────────────────────────────
# Main Marketplace Widget
# ─────────────────────────────────────────

class MarketplaceWidget(QWidget):
    """
    Full marketplace panel with search, results, pagination, and installed tab.
    Designed to be added to the extension_tabs area of VNCode.
    """
    theme_changed = pyqtSignal(dict)  # Emitted when user applies a theme
    snippets_loaded = pyqtSignal(str, list)  # language, completions

    def __init__(self, parent=None):
        super().__init__(parent)
        self._workers = []  # Keep references to prevent GC
        self._icon_loaders = []
        self._current_query = ""
        self._current_offset = 0
        self._page_size = 15
        self._total_results = 0
        self._current_sort_by = "relevance"
        self._current_sort_order = "desc"
        self._current_category = ""

        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # === Tab bar: Search / Installed ===
        self.tab_bar = QTabWidget()

        self.tab_bar.setStyleSheet("""
            QTabWidget::pane {
                border: none;
                background-color: #1e1e1e;
            }
            QTabBar::tab {
                background-color: #2d2d2d;
                color: #969696;
                padding: 6px 20px;
                border: none;
                border-right: 1px solid #252526;
                font-size: 12px;
            }
            QTabBar::tab:selected {
                background-color: #1e1e1e;
                color: #ffffff;
                border-bottom: 2px solid #007acc;
            }
            QTabBar::tab:hover:!selected {
                background-color: #383838;
            }
        """)

        # --- Search Tab ---
        search_tab = QWidget()
        search_layout = QVBoxLayout(search_tab)
        search_layout.setContentsMargins(8, 8, 8, 8)
        search_layout.setSpacing(6)

        # Search bar
        search_bar_layout = QHBoxLayout()
        search_bar_layout.setSpacing(4)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search extensions on Open VSX...")

        self.search_input.setStyleSheet("""
            QLineEdit {
                background-color: #3c3c3c;
                color: #d4d4d4;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 8px 12px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border-color: #007acc;
            }
        """)

        self.search_input.returnPressed.connect(self._do_search)
        search_bar_layout.addWidget(self.search_input, 1)

        # Category filter
        self.category_combo = QComboBox()
        self.category_combo.addItem("All Categories", "")
        self.category_combo.addItem("🚀 Code Runners", "code-runner")
        self.category_combo.addItem("🔤 LSP/IntelliSense", "lsp language-server")
        self.category_combo.addItem("💬 Languages", "language python javascript java")
        self.category_combo.addItem("✨ Syntax Highlighting", "syntax-highlighter highlight")
        self.category_combo.addItem("🎨 Themes", "theme")
        self.category_combo.addItem("📑 Snippets", "snippet")
        self.category_combo.addItem("🔧 Formatters", "formatter prettier autopep8")
        self.category_combo.addItem("🔍 Linters", "linter lint eslint pylint")
        self.category_combo.addItem("🐛 Debuggers", "debugger debug")
        self.category_combo.addItem("🛠️ Tools", "tool utility")
        self.category_combo.setStyleSheet("""
            QComboBox {
                background-color: #3c3c3c;
                color: #d4d4d4;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 12px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 4px solid #d4d4d4;
                margin-right: 8px;
            }
        """)
        self.category_combo.currentIndexChanged.connect(self._on_category_changed)
        search_bar_layout.addWidget(self.category_combo)

        # Sort options
        self.sort_combo = QComboBox()
        self.sort_combo.addItem("Relevance", "relevance")
        self.sort_combo.addItem("Rating", "rating")
        self.sort_combo.addItem("Downloads", "downloads")
        self.sort_combo.addItem("Name", "name")
        self.sort_combo.addItem("Newest", "timestamp")
        self.sort_combo.setStyleSheet(self.category_combo.styleSheet())
        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        search_bar_layout.addWidget(self.sort_combo)

        search_btn = QPushButton("Search")
        search_btn.setFixedHeight(36)
        search_btn.setStyleSheet("""
            QPushButton {
                background-color: #0e639c;
                color: #ffffff;
                border: none;
                padding: 0px 20px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #1177bb; }
            QPushButton:pressed { background-color: #094771; }
        """)
        search_btn.clicked.connect(self._do_search)
        search_bar_layout.addWidget(search_btn)

        # Clear search button
        clear_btn = QPushButton("Clear")
        clear_btn.setFixedSize(60, 36)
        clear_btn.setToolTip("Clear search and show featured extensions")
        clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #3c3c3c;
                color: #d4d4d4;
                border: 1px solid #555555;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #4a4a4a; }
        """)
        clear_btn.clicked.connect(self._clear_search)
        search_bar_layout.addWidget(clear_btn)

        search_layout.addLayout(search_bar_layout)

        # Status / loading
        self.status_label = QLabel("Nhap tu khoa de tim kiem...")
        self.status_label.setStyleSheet("color: #858585; font-size: 12px; padding: 4px 0px; border: none;")
        search_layout.addWidget(self.status_label)

        # Progress bar (hidden by default)
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #3c3c3c;
                border: none;
                border-radius: 2px;
                height: 3px;
                text-align: center;
                color: transparent;
            }
            QProgressBar::chunk {
                background-color: #007acc;
                border-radius: 2px;
            }
        """)
        self.progress_bar.setFixedHeight(3)
        self.progress_bar.hide()
        search_layout.addWidget(self.progress_bar)

        # Results list (scrollable)
        self.results_scroll = QScrollArea()
        self.results_scroll.setWidgetResizable(True)
        self.results_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.results_scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: #1e1e1e;
            }
            QWidget#resultsContainer {
                background-color: #1e1e1e;
            }
        """)

        self.results_container = QWidget()
        self.results_container.setObjectName("resultsContainer")
        self.results_layout = QVBoxLayout(self.results_container)
        self.results_layout.setContentsMargins(0, 0, 0, 0)
        self.results_layout.setSpacing(4)
        self.results_layout.addStretch()
        self.results_scroll.setWidget(self.results_container)

        search_layout.addWidget(self.results_scroll, 1)

        # Pagination
        pag_layout = QHBoxLayout()
        pag_layout.setSpacing(8)

        self.prev_btn = QPushButton("Truoc")
        self.prev_btn.setEnabled(False)
        self.prev_btn.setStyleSheet(self._pagination_btn_style())
        self.prev_btn.clicked.connect(self._prev_page)
        pag_layout.addWidget(self.prev_btn)

        pag_layout.addStretch()

        self.page_label = QLabel("")
        self.page_label.setStyleSheet("color: #858585; font-size: 12px; border: none;")
        pag_layout.addWidget(self.page_label)

        pag_layout.addStretch()

        self.next_btn = QPushButton("Sau")
        self.next_btn.setEnabled(False)
        self.next_btn.setStyleSheet(self._pagination_btn_style())
        self.next_btn.clicked.connect(self._next_page)
        pag_layout.addWidget(self.next_btn)

        search_layout.addLayout(pag_layout)
        self.tab_bar.addTab(search_tab, "Marketplace")

        # --- Installed Tab ---
        installed_tab = QWidget()
        installed_layout = QVBoxLayout(installed_tab)
        installed_layout.setContentsMargins(8, 8, 8, 8)
        installed_layout.setSpacing(6)

        installed_header = QHBoxLayout()
        inst_title = QLabel("Extensions da cai dat")
        inst_title.setStyleSheet("color: #ffffff; font-size: 14px; font-weight: bold; border: none;")
        installed_header.addWidget(inst_title)
        installed_header.addStretch()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #3c3c3c;
                color: #d4d4d4;
                border: 1px solid #555555;
                padding: 4px 12px;
                border-radius: 3px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #4a4a4a; }
        """)
        refresh_btn.clicked.connect(self._refresh_installed)
        installed_header.addWidget(refresh_btn)

        installed_layout.addLayout(installed_header)

        self.installed_scroll = QScrollArea()
        self.installed_scroll.setWidgetResizable(True)
        self.installed_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.installed_scroll.setStyleSheet("""
            QScrollArea { border: none; background-color: #1e1e1e; }
            QWidget#installedContainer { background-color: #1e1e1e; }
        """)

        self.installed_container = QWidget()
        self.installed_container.setObjectName("installedContainer")
        self.installed_layout = QVBoxLayout(self.installed_container)
        self.installed_layout.setContentsMargins(0, 0, 0, 0)
        self.installed_layout.setSpacing(4)
        self.installed_layout.addStretch()
        self.installed_scroll.setWidget(self.installed_container)

        installed_layout.addWidget(self.installed_scroll, 1)
        self.tab_bar.addTab(installed_tab, "Da cai dat")

        main_layout.addWidget(self.tab_bar)
        self.setLayout(main_layout)

        # Load installed on init
        QTimer.singleShot(100, self._refresh_installed)
        QTimer.singleShot(200, self._load_featured)

    def _clear_search(self):
        """Clear search and show featured extensions."""
        self.search_input.clear()
        self._current_query = ""
        self._current_offset = 0
        self.category_combo.setCurrentIndex(0)  # Reset to "All Categories"
        self.sort_combo.setCurrentIndex(0)  # Reset to "Relevance"
        self._current_category = ""
        self._current_sort_by = "relevance"
        self._current_sort_order = "desc"
        self._load_featured()

    def _load_featured(self):
        """Load featured extensions for initial display."""
        if not self._current_query and not self._current_category:
            self._execute_featured_search()

    def _execute_featured_search(self):
        """Load featured/popular extensions."""
        self.status_label.setText("Dang tai extensions noi bat...")
        self.status_label.setStyleSheet("color: #007acc; font-size: 12px; padding: 4px 0px; border: none;")
        self.progress_bar.setRange(0, 0)
        self.progress_bar.show()

        # Use search worker with empty query but downloads sort
        worker = SearchWorker("", 0, self._page_size, "downloads", "desc", "")
        worker.results_ready.connect(self._on_featured_results)
        worker.error_occurred.connect(self._on_search_error)
        worker.finished.connect(lambda: self._cleanup_worker(worker))
        self._workers.append(worker)
        worker.start()

    def _on_featured_results(self, data):
        self.progress_bar.hide()
        extensions = data.get("extensions", [])
        self._total_results = data.get("totalSize", 0)

        # Clear previous results
        self._clear_results()

        if not extensions:
            self.status_label.setText("Khong the tai extensions noi bat.")
            self.status_label.setStyleSheet("color: #858585; font-size: 12px; padding: 4px 0px; border: none;")
            return

        # Update status
        self.status_label.setText(f"Extensions noi bat ({len(extensions)} hient hi) - tim kiem de kham pha them!")
        self.status_label.setStyleSheet("color: #858585; font-size: 12px; padding: 4px 0px; border: none;")

        # Create cards (same as search results)
        for ext in extensions:
            card = ExtensionCard(ext)
            card.install_clicked.connect(self._install_extension)
            card.uninstall_clicked.connect(self._uninstall_extension)

            # Insert before the stretch
            self.results_layout.insertWidget(self.results_layout.count() - 1, card)

            # Load icon
            icon_url = ext.get("files", {}).get("icon", "")
            if icon_url:
                ext_id = f"{ext.get('namespace', '')}.{ext.get('name', '')}"
                loader = IconLoader(ext_id, icon_url)
                loader.icon_ready.connect(lambda eid, path, c=card, cid=ext_id:
                                          self._set_card_icon(c, cid, eid, path))
                loader.finished.connect(lambda: self._cleanup_icon_loader(loader))
                self._icon_loaders.append(loader)
                loader.start()

        # No pagination for featured
        self.page_label.setText("")
        self.prev_btn.setEnabled(False)
        self.next_btn.setEnabled(False)

    def _pagination_btn_style(self):
        return """
            QPushButton {
                background-color: #3c3c3c;
                color: #d4d4d4;
                border: 1px solid #555555;
                padding: 4px 14px;
                border-radius: 3px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #4a4a4a; }
            QPushButton:disabled { color: #555555; background-color: #2d2d2d; border-color: #3c3c3c; }
        """

    def _on_category_changed(self):
        """Handle category filter change."""
        self._current_category = self.category_combo.currentData()
        if self._current_query or self._current_category:
            self._current_offset = 0
            self._execute_search()

    def _on_sort_changed(self):
        """Handle sort option change."""
        sort_data = self.sort_combo.currentData()
        if sort_data == "rating":
            self._current_sort_by = "relevance"  # Fallback since rating sort may not be supported
            self._current_sort_order = "desc"
        elif sort_data == "downloads":
            self._current_sort_by = "relevance"  # Fallback
            self._current_sort_order = "desc"
        elif sort_data == "name":
            self._current_sort_by = "relevance"  # Fallback
            self._current_sort_order = "asc"
        elif sort_data == "timestamp":
            self._current_sort_by = "relevance"  # Fallback
            self._current_sort_order = "desc"
        else:  # relevance
            self._current_sort_by = "relevance"
            self._current_sort_order = "desc"
        
        if self._current_query or self._current_category:
            self._current_offset = 0
            self._execute_search()

    def _do_search(self):
        query = self.search_input.text().strip()
        self._current_query = query
        self._current_offset = 0
        self._execute_search()

    def _execute_search(self):
        self.status_label.setText("Dang tim kiem...")
        self.status_label.setStyleSheet("color: #007acc; font-size: 12px; padding: 4px 0px; border: none;")
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.progress_bar.show()
        self.prev_btn.setEnabled(False)
        self.next_btn.setEnabled(False)

        worker = SearchWorker(
            self._current_query, self._current_offset, self._page_size,
            self._current_sort_by, self._current_sort_order, self._current_category
        )
        worker.results_ready.connect(self._on_search_results)
        worker.error_occurred.connect(self._on_search_error)
        worker.finished.connect(lambda: self._cleanup_worker(worker))
        self._workers.append(worker)
        worker.start()

    def _on_search_results(self, data):
        self.progress_bar.hide()
        extensions = data.get("extensions", [])
        self._total_results = data.get("totalSize", 0)

        # Clear previous results
        self._clear_results()

        if not extensions:
            self.status_label.setText("Khong tim thay extension nao. Thu tu khoa khac hoac chon danh muc khac.")
            self.status_label.setStyleSheet("color: #858585; font-size: 12px; padding: 4px 0px; border: none;")
            return

        # Update status
        start = self._current_offset + 1
        end = min(self._current_offset + len(extensions), self._total_results)
        self.status_label.setText(
            f"Hien thi {start}-{end} / {self._total_results} ket qua cho \"{self._current_query}\""
        )
        self.status_label.setStyleSheet("color: #858585; font-size: 12px; padding: 4px 0px; border: none;")

        # Create cards
        for ext in extensions:
            card = ExtensionCard(ext)
            card.install_clicked.connect(self._install_extension)
            card.uninstall_clicked.connect(self._uninstall_extension)

            # Insert before the stretch
            self.results_layout.insertWidget(self.results_layout.count() - 1, card)

            # Load icon
            icon_url = ext.get("files", {}).get("icon", "")
            if icon_url:
                ext_id = f"{ext.get('namespace', '')}.{ext.get('name', '')}"
                loader = IconLoader(ext_id, icon_url)
                loader.icon_ready.connect(lambda eid, path, c=card, cid=ext_id:
                                          self._set_card_icon(c, cid, eid, path))
                loader.finished.connect(lambda: self._cleanup_icon_loader(loader))
                self._icon_loaders.append(loader)
                loader.start()

        # Update pagination
        self._update_pagination()

    def _set_card_icon(self, card, card_ext_id, loaded_ext_id, path):
        """Set icon on the correct card."""
        if card_ext_id == loaded_ext_id and os.path.exists(path):
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                card.set_icon(pixmap)

    def _on_search_error(self, error_msg):
        self.progress_bar.hide()
        self.status_label.setText(f"Loi: {error_msg}")
        self.status_label.setStyleSheet("color: #f44747; font-size: 12px; padding: 4px 0px; border: none;")

    def _clear_results(self):
        while self.results_layout.count() > 1:  # Keep the stretch
            item = self.results_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    # ─────────────────────────────────────
    # Pagination
    # ─────────────────────────────────────

    def _update_pagination(self):
        if self._total_results <= 0:
            self.page_label.setText("")
            self.prev_btn.setEnabled(False)
            self.next_btn.setEnabled(False)
            return

        current_page = (self._current_offset // self._page_size) + 1
        total_pages = max(1, (self._total_results + self._page_size - 1) // self._page_size)

        self.page_label.setText(f"Trang {current_page} / {total_pages}")
        self.prev_btn.setEnabled(self._current_offset > 0)
        self.next_btn.setEnabled(self._current_offset + self._page_size < self._total_results)

    def _prev_page(self):
        self._current_offset = max(0, self._current_offset - self._page_size)
        self._execute_search()

    def _next_page(self):
        self._current_offset += self._page_size
        self._execute_search()

    # ─────────────────────────────────────
    # Install / Uninstall
    # ─────────────────────────────────────

    def _install_extension(self, ext_info):
        name = ext_info.get("displayName", ext_info.get("name", ""))
        self.status_label.setText(f"Dang tai {name}...")
        self.status_label.setStyleSheet("color: #007acc; font-size: 12px; padding: 4px 0px; border: none;")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.show()

        worker = InstallWorker(ext_info)
        worker.progress.connect(self._on_install_progress)
        worker.finished.connect(self._on_install_finished)
        worker.finished.connect(lambda: self._cleanup_worker(worker))
        self._workers.append(worker)
        worker.start()

    def _on_install_progress(self, downloaded, total):
        if total > 0:
            pct = int(downloaded * 100 / total)
            self.progress_bar.setValue(pct)
        else:
            self.progress_bar.setRange(0, 0)  # Indeterminate

    def _on_install_finished(self, success, message):
        self.progress_bar.hide()
        if success:
            self.status_label.setText(f"Da cai dat {message}")
            self.status_label.setStyleSheet("color: #6e9e6e; font-size: 12px; padding: 4px 0px; border: none;")
            # Refresh to update install/uninstall buttons
            if self._current_query:
                self._execute_search()
            self._refresh_installed()
            # Load contributions from newly installed extension
            self._load_latest_extension_contributions()
        else:
            self.status_label.setText(f"Loi: {message}")
            self.status_label.setStyleSheet("color: #f44747; font-size: 12px; padding: 4px 0px; border: none;")

    def _uninstall_extension(self, namespace, name):
        display = f"{namespace}.{name}"
        reply = QMessageBox.question(
            self, "Xác nhận gỡ cài đặt",
            f"Bạn có chắc muốn gỡ cài đặt {display}?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            success = extension_manager.uninstall_extension(namespace, name)
            if success:
                self.status_label.setText(f"Da go cai dat {display}")
                self.status_label.setStyleSheet("color: #6e9e6e; font-size: 12px; padding: 4px 0px; border: none;")
                if self._current_query:
                    self._execute_search()
                self._refresh_installed()
            else:
                self.status_label.setText(f"Khong the go cai dat {display}")
                self.status_label.setStyleSheet("color: #f44747; font-size: 12px; padding: 4px 0px; border: none;")

    # ─────────────────────────────────────
    # Installed Tab
    # ─────────────────────────────────────

    def _refresh_installed(self):
        # Clear
        while self.installed_layout.count() > 1:
            item = self.installed_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        installed = extension_manager.list_installed()

        if not installed:
            empty_label = QLabel("Chưa có extension nào được cài đặt.")
            empty_label.setStyleSheet("color: #858585; font-size: 13px; padding: 20px; border: none;")
            empty_label.setAlignment(Qt.AlignCenter)
            self.installed_layout.insertWidget(0, empty_label)
            return

        for meta in installed:
            # Build ext_info compatible dict
            ext_info = {
                "namespace": meta.get("namespace", ""),
                "name": meta.get("name", ""),
                "displayName": meta.get("displayName", ""),
                "description": meta.get("description", ""),
                "version": meta.get("version", ""),
                "files": {"icon": meta.get("icon_url", "")},
            }
            card = self._create_installed_card(meta, ext_info)
            self.installed_layout.insertWidget(self.installed_layout.count() - 1, card)

            # Load icon for installed card
            icon_url = ext_info.get("files", {}).get("icon", "")
            if icon_url:
                ext_id = f"{ext_info.get('namespace', '')}.{ext_info.get('name', '')}"
                loader = IconLoader(ext_id, icon_url)
                # Reuse _set_card_icon logic - need to ensure it works for both card types
                loader.icon_ready.connect(lambda eid, path, c=card: self._set_installed_card_icon(c, path))
                loader.finished.connect(lambda: self._cleanup_icon_loader(loader))
                self._icon_loaders.append(loader)
                loader.start()

        # Check for updates
        self._check_for_updates(installed)

    def _check_for_updates(self, installed_extensions):
        """Check for updates to installed extensions."""
        if not installed_extensions:
            return

        worker = UpdateCheckWorker(installed_extensions)
        worker.updates_found.connect(self._on_updates_found)
        worker.finished.connect(lambda: self._cleanup_worker(worker))
        self._workers.append(worker)
        worker.start()

    def _on_updates_found(self, updates):
        """Handle found updates - update UI to show update buttons."""
        if not updates:
            return

        # Find cards that have updates available and modify them
        for i in range(self.installed_layout.count()):
            item = self.installed_layout.itemAt(i)
            if item and item.widget():
                card = item.widget()
                if hasattr(card, '_update_btn'):  # Already has update button
                    continue
                
                # Check if this card corresponds to an extension with update
                for namespace, name, current_ver, latest_info in updates:
                    card_ns = getattr(card, '_namespace', '')
                    card_name = getattr(card, '_name', '')
                    if card_ns == namespace and card_name == name:
                        # Add update button to this card
                        self._add_update_button_to_card(card, latest_info)
                        break

    def _add_update_button_to_card(self, card, latest_info):
        """Add an update button to an installed extension card."""
        if hasattr(card, '_update_btn'):
            return  # Already has update button

        # Find the button layout
        layout = card.layout()
        if not layout or layout.count() < 2:
            return

        btn_layout_item = layout.itemAt(2)  # Should be the button layout
        if not btn_layout_item or not btn_layout_item.layout():
            return

        btn_layout = btn_layout_item.layout()
        
        # Create update button
        update_btn = QPushButton("Update")
        update_btn.setStyleSheet("""
            QPushButton {
                background-color: #0e7a0d;
                color: #ffffff;
                border: none;
                padding: 4px 10px;
                border-radius: 3px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #12961c; }
        """)
        
        latest_ver = latest_info.get("version", "")
        update_btn.clicked.connect(lambda checked, ns=card._namespace, nm=card._name, info=latest_info: 
                                   self._update_extension(ns, nm, info))
        
        # Insert at the top of button layout
        btn_layout.insertWidget(0, update_btn)
        card._update_btn = update_btn  # Mark as having update button

    def _update_extension(self, namespace, name, latest_info):
        """Update an installed extension to the latest version."""
        display = f"{namespace}.{name}"
        latest_ver = latest_info.get("version", "")
        
        reply = QMessageBox.question(
            self, "Xác nhận cập nhật",
            f"Bạn có muốn cập nhật {display} lên phiên bản {latest_ver}?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # Use the install process for update
            self._install_extension(latest_info)

    def _create_installed_card(self, meta, ext_info):
        """Create a card for an installed extension with extra actions."""
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #252526;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                margin: 2px 0px;
            }
            QFrame:hover {
                border-color: #007acc;
            }
        """)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        # Store extension info for update checking
        card._namespace = meta.get("namespace", "")
        card._name = meta.get("name", "")

        # Icon placeholder
        icon_label = QLabel("PKG")
        icon_label.setFixedSize(40, 40)
        icon_label.setStyleSheet("font-size: 16px; border: none; background: #3c3c3c; border-radius: 4px;")
        icon_label.setAlignment(Qt.AlignCenter)
        card._icon_label = icon_label # Store reference for later
        layout.addWidget(icon_label)

        # Info
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        name_label = QLabel(meta.get("displayName", meta.get("name", "")))
        name_label.setStyleSheet("color: #ffffff; font-size: 13px; font-weight: bold; border: none;")
        info_layout.addWidget(name_label)

        ver_label = QLabel(f"{meta.get('namespace', '')} · v{meta.get('version', '')}")
        ver_label.setStyleSheet("color: #858585; font-size: 11px; border: none;")
        info_layout.addWidget(ver_label)

        # Show contributions
        contributions = meta.get("contributions", {})
        contrib_parts = []
        if "themes" in contributions:
            contrib_parts.append(f"Theme: {len(contributions['themes'])}")
        if "snippets" in contributions:
            contrib_parts.append(f"Snippet: {len(contributions['snippets'])}")
        if "grammars" in contributions:
            contrib_parts.append(f"Grammar: {len(contributions['grammars'])}")
        if "languages" in contributions:
            contrib_parts.append(f"Lang: {len(contributions['languages'])}")
        if "commands" in contributions:
            contrib_parts.append(f"Cmd: {len(contributions['commands'])}")
        if "keybindings" in contributions:
            contrib_parts.append(f"Keys: {len(contributions['keybindings'])}")
        if "debuggers" in contributions:
            contrib_parts.append(f"Debug: {len(contributions['debuggers'])}")

        if contrib_parts:
            contrib_label = QLabel(" · ".join(contrib_parts))
            contrib_label.setStyleSheet("color: #569cd6; font-size: 11px; border: none;")
            info_layout.addWidget(contrib_label)

        layout.addLayout(info_layout, 1)

        # Action buttons
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(4)

        # Apply theme button (if has themes)
        if "themes" in contributions and contributions["themes"]:
            theme_btn = QPushButton("Ap dung Theme")
            theme_btn.setStyleSheet("""
                QPushButton {
                    background-color: #2d5a2d;
                    color: #a0e0a0;
                    border: none;
                    padding: 4px 10px;
                    border-radius: 3px;
                    font-size: 11px;
                }
                QPushButton:hover { background-color: #3d7a3d; }
            """)
            theme_btn.clicked.connect(lambda checked, m=meta: self._apply_theme(m))
            btn_layout.addWidget(theme_btn)

        # Uninstall
        unsub_btn = QPushButton("Gỡ cài đặt")
        unsub_btn.setStyleSheet("""
            QPushButton {
                background-color: #5a1d1d;
                color: #e8a0a0;
                border: 1px solid #6e3030;
                padding: 4px 10px;
                border-radius: 3px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #7a2d2d; }
        """)
        ns = meta.get("namespace", "")
        nm = meta.get("name", "")
        unsub_btn.clicked.connect(lambda checked, a=ns, b=nm: self._uninstall_extension(a, b))
        btn_layout.addWidget(unsub_btn)

        # View Details button
        detail_btn = QPushButton("Chi tiết")
        detail_btn.setStyleSheet("""
            QPushButton {
                background-color: #3c3c3c;
                color: #d4d4d4;
                border: none;
                padding: 4px 10px;
                border-radius: 3px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #4a4a4a; }
        """)
        detail_btn.clicked.connect(lambda checked, m=meta: self._show_extension_details(m))
        btn_layout.addWidget(detail_btn)

        layout.addLayout(btn_layout)
        return card

    def _set_installed_card_icon(self, card, path):
        """Helper to set icon on an installed extension card."""
        if os.path.exists(path) and hasattr(card, "_icon_label"):
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                card._icon_label.setPixmap(scaled)
                card._icon_label.setText("")
                card._icon_label.setStyleSheet("background: transparent; border: none;")

    def _show_extension_details(self, meta):
        """Show a dialog with extension details and README."""
        namespace = meta.get("namespace", "")
        name = meta.get("name", "")
        display_name = meta.get("displayName", name)
        
        from pathlib import Path
        ext_path = Path(extension_manager.get_extension_path(namespace, name))
        readme_path = None
        
        # Look for README.md in extracted folder
        for p in ext_path.rglob("README.md"):
            readme_path = p
            break
        
        content = ""
        if readme_path and readme_path.exists():
            try:
                content = readme_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                content = "Could not read README.md"
        else:
            content = meta.get("description", "Không có thông tin chi tiết.")

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Chi tiết Extension: {display_name}")
        dialog.resize(600, 500)
        dialog.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4;")
        
        dlg_layout = QVBoxLayout(dialog)
        
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setPlainText(content)
        text_edit.setStyleSheet("""
            QTextEdit { 
                background-color: #252526; 
                border: 1px solid #3c3c3c; 
                padding: 10px; 
                font-family: 'Segoe UI', sans-serif;
                font-size: 13px;
            }
        """)
        dlg_layout.addWidget(text_edit)
        
        close_btn = QPushButton("Đóng")
        close_btn.clicked.connect(dialog.accept)
        dlg_layout.addWidget(close_btn, 0, Qt.AlignRight)
        
        dialog.exec_()

    # ─────────────────────────────────────
    # Extension Contributions Loading
    # ─────────────────────────────────────

    def _apply_theme(self, meta):
        """Let user choose and apply a theme from an installed extension."""
        contributions = meta.get("contributions", {})
        themes = contributions.get("themes", [])
        if not themes:
            return

        if len(themes) == 1:
            theme_info = themes[0]
        else:
            # Let user choose
            items = [t.get("label", "Unknown") for t in themes]
            item, ok = QInputDialog.getItem(
                self, "Chọn Theme",
                f"Extension {meta.get('displayName', '')} có {len(themes)} themes:",
                items, 0, False
            )
            if not ok:
                return
            idx = items.index(item)
            theme_info = themes[idx]

        theme_data = extension_manager.load_theme(theme_info.get("path", ""))
        if theme_data:
            colors = extension_manager.get_theme_colors(theme_data)
            self.theme_changed.emit(colors)
            self.status_label.setText(f"Da ap dung theme: {theme_info.get('label', '')}")
            self.status_label.setStyleSheet("color: #6e9e6e; font-size: 12px; padding: 4px 0px; border: none;")
        else:
            self.status_label.setText(f"Khong the tai theme.")
            self.status_label.setStyleSheet("color: #f44747; font-size: 12px; padding: 4px 0px; border: none;")

    def _load_latest_extension_contributions(self):
        """Load contributions from all installed extensions."""
        installed = extension_manager.list_installed()
        for meta in installed:
            contributions = meta.get("contributions", {})

            # Load snippets
            for snippet_info in contributions.get("snippets", []):
                lang = snippet_info.get("language", "")
                snippet_path = snippet_info.get("path", "")
                if lang and snippet_path:
                    snippet_data = extension_manager.load_snippets(snippet_path)
                    if snippet_data:
                        completions = extension_manager.get_snippet_completions(snippet_data)
                        if completions:
                            self.snippets_loaded.emit(lang, completions)

    def load_all_contributions(self):
        """Load all contributions from installed extensions on startup."""
        # Load snippets from all extensions
        self._load_latest_extension_contributions()
        # Auto-apply theme from first extension with a theme
        self.auto_apply_default_themes()

    def auto_apply_default_themes(self):
        """
        Automatically apply the default theme from the first theme-enabled extension.
        Called on VNCode startup to integrate extensions into the IDE.
        """
        installed = extension_manager.list_installed()
        for meta in installed:
            # Get the first extension with a theme and apply it
            theme_colors = extension_manager.get_default_theme_colors(meta)
            if theme_colors:
                logger.info(f"Auto-applying default theme from {meta.get('displayName', 'Unknown')}")
                self.theme_changed.emit(theme_colors)
                break  # Apply only the first theme found

    # ─────────────────────────────────────
    # Cleanup
    # ─────────────────────────────────────

    def _cleanup_worker(self, worker):
        if worker in self._workers:
            self._workers.remove(worker)

    def _cleanup_icon_loader(self, loader):
        if loader in self._icon_loaders:
            self._icon_loaders.remove(loader)

    def get_current_file_path(self):
        """Helper to get current file from parent window if needed."""
        main = self.window()
        if hasattr(main, "current_file"):
            return main.current_file
        return None
