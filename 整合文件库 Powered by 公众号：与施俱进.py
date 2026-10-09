import os
import sys
import json
import time
import shutil
import zipfile
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, messagebox, filedialog, simpledialog
from datetime import datetime
import traceback
import functools
import re
import subprocess
import importlib
import importlib.util


# ============================================================
#              支持库自动安装（全自动，不询问）
# ============================================================

SUPPORT_PACKAGES = [
    {"import": "tkinterdnd2", "pip": "tkinterdnd2", "desc": "跨窗口文件拖拽支持"},
    {"import": "PIL",         "pip": "Pillow",     "desc": "图片预览支持"},
]


def _is_module_available(module_name):
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ValueError, ModuleNotFoundError):
        return False


def _pip_install(package_name, timeout=300):
    python_exe = sys.executable or "python3"
    commands = [
        [python_exe, "-m", "pip", "install", "--upgrade", package_name],
        [python_exe, "-m", "pip", "install", "--user", "--upgrade", package_name],
        [python_exe, "-m", "pip", "install", "--upgrade",
         "-i", "https://pypi.tuna.tsinghua.edu.cn/simple",
         "--trusted-host", "pypi.tuna.tsinghua.edu.cn",
         package_name],
    ]
    last_err = ""
    for cmd in commands:
        try:
            kwargs = {"capture_output": True, "text": True, "timeout": timeout}
            if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            proc = subprocess.run(cmd, **kwargs)
            if proc.returncode == 0:
                return True, ""
            out = ((proc.stderr or "") + "\n" + (proc.stdout or "")).strip()
            last_err = out[-600:] if out else f"返回码 {proc.returncode}"
        except subprocess.TimeoutExpired:
            last_err = f"安装 {package_name} 超时（>{timeout} 秒）"
        except FileNotFoundError:
            return False, "未找到 Python 可执行文件（sys.executable）"
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
    return False, last_err


def install_missing_support_libs(ask=True, parent=None):
    missing = [p for p in SUPPORT_PACKAGES if not _is_module_available(p["import"])]
    if not missing:
        return 0, [], []

    progress = None
    status_var = None

    def _set_status(text):
        if status_var is not None and progress is not None:
            try:
                status_var.set(text)
                progress.update_idletasks()
            except Exception:
                pass

    try:
        if parent is not None:
            progress = tk.Toplevel(parent)
            progress.transient(parent)
            progress.grab_set()
        else:
            progress = tk.Tk()
        progress.title("正在自动安装支持库")
        progress.geometry("470x180")
        progress.resizable(False, False)
        try:
            progress.attributes("-topmost", True)
        except Exception:
            pass

        tk.Label(progress, text="检测到缺失的支持库，正在自动安装…",
                 font=("Arial", 11, "bold")).pack(pady=(14, 4))
        missing_txt = "、".join(p["pip"] for p in missing)
        tk.Label(progress, text=f"待安装：{missing_txt}",
                 fg="#555").pack(pady=(0, 4))
        status_var = tk.StringVar(value="准备中…")
        tk.Label(progress, textvariable=status_var, fg="#333").pack(pady=2)
        pbar = ttk.Progressbar(progress, mode="indeterminate", length=410)
        pbar.pack(pady=10)
        pbar.start(15)
        progress.update_idletasks()
    except Exception:
        try:
            log_error(f"创建安装进度窗口失败: {traceback.format_exc()}")
        except Exception:
            pass
        progress = None
        status_var = None

    installed_count = 0
    failed = []
    try:
        for idx, pkg in enumerate(missing, 1):
            _set_status(f"[{idx}/{len(missing)}] 正在安装 {pkg['pip']} …")
            ok, err = _pip_install(pkg["pip"])
            if ok:
                installed_count += 1
            else:
                failed.append((pkg["pip"], err))
        _set_status("安装完成，正在刷新缓存…")
    finally:
        if progress is not None:
            try:
                progress.destroy()
            except Exception:
                pass

    try:
        importlib.invalidate_caches()
    except Exception:
        pass

    return installed_count, failed, [p["pip"] for p in missing]


# ---------- 可选依赖：延迟导入 ----------
DND_AVAILABLE = False
TkinterDnD = None
DND_FILES = None


def _try_import_optional_libs():
    global DND_AVAILABLE, TkinterDnD, DND_FILES
    try:
        from tkinterdnd2 import DND_FILES as _dnd_files, TkinterDnD as _tkdnd
        DND_AVAILABLE = True
        TkinterDnD = _tkdnd
        DND_FILES = _dnd_files
    except ImportError:
        DND_AVAILABLE = False
        TkinterDnD = None
        DND_FILES = None


_try_import_optional_libs()


# ---------------------------- 错误日志 ----------------------------
ERROR_LOG = "error.log"


def log_error(msg):
    try:
        with open(ERROR_LOG, 'a', encoding='utf-8') as f:
            f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {msg}\n")
            f.write("="*50 + "\n")
    except Exception:
        pass


# ---------------------------- 配置 ----------------------------
CONFIG_FILE = "bid_library_config.json"

# 备用库名（用户取消选择时用当前目录下的此文件夹名）
LIBRARY_FALLBACK_NAME = "MyLibrary"

DEFAULT_COLUMNS = [
    {"id": "path",        "title": "路径",     "width": 250, "builtin": True,  "wrap": True,  "align": "left"},
    {"id": "version",     "title": "版本",     "width": 80,  "builtin": True,  "wrap": False, "align": "center"},
    {"id": "price",       "title": "价格",     "width": 100, "builtin": True,  "wrap": False, "align": "right"},
    {"id": "update_time", "title": "更新时间", "width": 150, "builtin": True,  "wrap": False, "align": "center"},
]

DEFAULT_ROW_HEIGHT = 24
DEFAULT_GEOMETRY = "1300x800"


# ---------------------------- 自然排序 ----------------------------
def natural_sort_key(s):
    if s is None:
        s = ""
    s = str(s).lower()
    parts = re.split(r'(\d+)', s)
    key = []
    for p in parts:
        if p == "":
            continue
        if p.isdigit():
            key.append((0, int(p)))
        else:
            key.append((1, p))
    return key


# ---------------------------- 数据模型 ----------------------------
class Node:
    def __init__(self, name, parent=None, children=None, remark="",
                 create_time=None, update_time=None, version="1.0",
                 price="", history_versions=None, extra_fields=None,
                 editable_fields=None):
        self.name = name
        self.parent = parent
        self.children = children if children is not None else []
        self.remark = remark
        self.path = None
        self.create_time = create_time or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.update_time = update_time or self.create_time
        self.version = version
        self.price = price
        self.history_versions = history_versions if history_versions is not None else []
        self.extra_fields = extra_fields if extra_fields is not None else {}
        self.editable_fields = editable_fields

    def set_path(self, base_path):
        if self.parent is None:
            self.path = base_path
        else:
            self.path = os.path.join(self.parent.path, self.name)
        for child in self.children:
            child.parent = self
            child.set_path(self.path)

    def to_dict(self):
        return {
            "name": self.name,
            "children": [child.to_dict() for child in self.children],
            "remark": self.remark,
            "create_time": self.create_time,
            "update_time": self.update_time,
            "version": self.version,
            "price": self.price,
            "history_versions": self.history_versions,
            "extra_fields": self.extra_fields,
            "editable_fields": self.editable_fields,
        }

    @classmethod
    def from_dict(cls, data, parent=None):
        node = cls(
            name=data["name"], parent=parent,
            remark=data.get("remark", ""),
            create_time=data.get("create_time", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            update_time=data.get("update_time", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            version=data.get("version", "1.0"),
            price=data.get("price", ""),
            history_versions=data.get("history_versions", []),
            extra_fields=data.get("extra_fields", {}) or {},
            editable_fields=data.get("editable_fields", None),
        )
        for child_data in data.get("children", []):
            child = cls.from_dict(child_data, node)
            node.children.append(child)
        return node

    def _normalize_name(self, name):
        if not name:
            return ""
        return re.sub(r'[\.\s]+$', '', name).strip().lower()

    def find_child(self, name):
        target = self._normalize_name(name)
        for child in self.children:
            if self._normalize_name(child.name) == target:
                return child
        return None

    def add_child(self, node):
        self.children.append(node)
        node.parent = self
        if self.path:
            node.path = os.path.join(self.path, node.name)
            os.makedirs(node.path, exist_ok=True)
        return node

    def remove_child(self, child):
        if child in self.children:
            self.children.remove(child)
            if child.path and os.path.exists(child.path):
                shutil.rmtree(child.path)
            return True
        return False

    def move_to(self, new_parent):
        old_parent = self.parent
        if old_parent:
            old_parent.children.remove(self)
        new_parent.children.append(self)
        self.parent = new_parent
        old_path = self.path
        if old_path and os.path.exists(old_path):
            new_path = os.path.join(new_parent.path, self.name)
            if os.path.exists(new_path):
                base, ext = os.path.splitext(self.name)
                counter = 1
                while os.path.exists(os.path.join(new_parent.path, f"{base}_{counter}{ext}")):
                    counter += 1
                new_name = f"{base}_{counter}{ext}"
                new_path = os.path.join(new_parent.path, new_name)
                self.name = new_name
            shutil.move(old_path, new_path)
            self.path = new_path
        else:
            self.path = os.path.join(new_parent.path, self.name)
        self._update_children_paths()
        return True

    def rename(self, new_name):
        old_path = self.path
        if old_path and os.path.exists(old_path):
            new_path = os.path.join(os.path.dirname(old_path), new_name)
            os.rename(old_path, new_path)
            self.path = new_path
        self.name = new_name
        self._update_children_paths()
        return True

    def _update_children_paths(self):
        for child in self.children:
            child.path = os.path.join(self.path, child.name)
            child._update_children_paths()

    def get_leaf_nodes(self):
        if not self.children:
            return [self]
        leaves = []
        for child in self.children:
            leaves.extend(child.get_leaf_nodes())
        return leaves

    def find_by_path(self, path):
        if self.path == path:
            return self
        for child in self.children:
            result = child.find_by_path(path)
            if result:
                return result
        return None

    def get_all_nodes(self):
        nodes = [self]
        for child in self.children:
            nodes.extend(child.get_all_nodes())
        return nodes

    def get_all_file_paths(self):
        if not self.path or not os.path.exists(self.path):
            return []
        files = []
        for item in os.listdir(self.path):
            full = os.path.join(self.path, item)
            if os.path.isfile(full):
                files.append(full)
        return files

    def is_ancestor_of(self, other):
        cur = other.parent
        while cur:
            if cur == self:
                return True
            cur = cur.parent
        return False

    def update_version(self, new_version=None, remark=""):
        history_entry = {
            "version": self.version,
            "update_time": self.update_time,
            "remark": remark
        }
        self.history_versions.append(history_entry)
        if new_version is None:
            try:
                base = float(self.version) if self.version.replace('.', '').isdigit() else 1.0
                new_version = f"{base + 0.1:.1f}"
            except:
                new_version = "1.1"
        self.version = new_version
        self.update_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return True

    def get_history_versions(self):
        return self.history_versions


# ---------------------------- 主应用程序 ----------------------------
class BidLibraryApp:
    def __init__(self, root):
        self.root = root
        self.root.title("整合文件库 Powered by 公众号：与施俱进")
        self.root.geometry(DEFAULT_GEOMETRY)

        self.root_node = None
        self.base_dir = None
        self.current_selected = None
        self.copied_node_data = None
        self.copied_node_name = None
        self.copied_node_path = None
        self.filter_keyword = tk.StringVar()
        self.filter_history = []
        self.display_nodes = None

        self.columns_config = [dict(c) for c in DEFAULT_COLUMNS]
        self._path_col_index = 0
        self.sort_column = None
        self.sort_reverse = False

        self._iid_to_path = {}
        self._path_to_iid = {}
        self._iid_to_file = {}
        self._iid_counter = 0

        self.row_height = DEFAULT_ROW_HEIGHT
        self.style = ttk.Style()

        self.auto_wrap = False
        self.max_wrap_lines = 2
        self._wrap_font = None
        self._wrap_recompute_after_id = None

        self.show_files = True

        self._col_drag_source_id = None
        self._col_drag_active = False
        self._col_drag_start_x = 0
        self._last_col_drag_time = 0

        self._drag_source_item = None
        self._drag_source_path = None
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._dragging_node = False
        self._drop_target = None
        self._drop_position = None
        self._drop_indicator_item = None
        self._drop_indicator_old_tags = None

        self._drop_hover_item = None
        self._drop_hover_old_tags = None
        self._dnd_active = False
        self._cached_drop_data = ""

        self.ui_state = None
        self._ui_ready = False

        self.create_menu()
        self.create_widgets()
        self.load_or_init_data()
        self._ensure_column_attr_defaults()
        self._apply_row_height()
        self._rebuild_tree_columns()
        self._apply_saved_ui_state()
        self._ui_ready = True

        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        self.tree.bind("<Double-1>", self.on_double_click)
        self.tree.bind("<Delete>", self.on_delete_key)
        self.tree.bind("<<TreeviewOpen>>", self.on_tree_open)
        self.create_context_menu()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        if DND_AVAILABLE:
            self.setup_drag_drop()

        self.root.after(200, self._auto_sync_on_startup)

    # ==================== ★ 显示文件开关 ====================
    def toggle_show_files(self):
        self.show_files = not self.show_files
        try:
            self._show_files_var.set(self.show_files)
        except Exception:
            pass
        expanded = self._collect_expanded_paths()
        self.populate_tree(keep_expanded=True, expanded_paths_override=expanded)
        self.save_config()
        state = "开启" if self.show_files else "关闭"
        self.status_var.set(f"文件显示已{state}（{'展开节点可看到磁盘文件' if self.show_files else '仅显示节点'}）")

    # ==================== 备注弹窗 ====================
    def open_remark_dialog(self):
        node = self.current_selected
        if not node:
            messagebox.showwarning("未选中", "请先在树中选中一个节点")
            return
        dlg = tk.Toplevel(self.root)
        dlg.title(f"节点备注 - {node.name}")
        dlg.geometry("520x400")
        dlg.transient(self.root)
        dlg.grab_set()
        ttk.Label(dlg, text=f"节点：{node.name}", font=('Arial', 10, 'bold')).pack(anchor="w", padx=12, pady=(10, 2))
        ttk.Label(dlg, text=f"路径：{node.path or '(无)'}", foreground="#666").pack(anchor="w", padx=12, pady=(0, 8))
        ttk.Label(dlg, text="备注内容（标签/说明）：").pack(anchor="w", padx=12)
        text_frame = ttk.Frame(dlg)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)
        text_widget = tk.Text(text_frame, wrap=tk.WORD)
        scroll = ttk.Scrollbar(text_frame, orient="vertical", command=text_widget.yview)
        text_widget.configure(yscrollcommand=scroll.set)
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        text_widget.insert("1.0", node.remark or "")
        text_widget.focus_set()

        def do_save():
            new_remark = text_widget.get("1.0", tk.END).strip()
            node.remark = new_remark
            node.update_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.save_config()
            self._update_tree_node(node)
            self.status_var.set(f"备注已保存: {new_remark[:30]}{'...' if len(new_remark)>30 else ''}")
            dlg.destroy()

        def do_clear():
            text_widget.delete("1.0", tk.END)
            text_widget.focus_set()

        btn_frame = ttk.Frame(dlg)
        btn_frame.pack(fill=tk.X, padx=12, pady=(6, 12))
        ttk.Button(btn_frame, text="💾 保存", command=do_save).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btn_frame, text="取消", command=dlg.destroy).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btn_frame, text="🗑 清空", command=do_clear).pack(side=tk.LEFT, padx=4)

        try:
            dlg.update_idletasks()
            px = self.root.winfo_x() + (self.root.winfo_width() - 520) // 2
            py = self.root.winfo_y() + (self.root.winfo_height() - 400) // 2
            dlg.geometry(f"+{max(0, px)}+{max(0, py)}")
        except Exception:
            pass

    # ==================== 文件节点 ====================
    def _insert_files_under(self, parent_iid, node):
        if not self.show_files:
            return
        if not node.path or not os.path.exists(node.path):
            return
        try:
            files = []
            with os.scandir(node.path) as it:
                for e in it:
                    if e.is_file(follow_symlinks=False):
                        files.append(e.name)
            files.sort(key=natural_sort_key)
        except (PermissionError, OSError):
            return
        for fname in files:
            file_path = os.path.join(node.path, fname)
            self._iid_counter += 1
            iid = f"f{self._iid_counter}"
            self._iid_to_file[iid] = file_path
            try:
                self.tree.insert(
                    parent_iid, "end", iid=iid,
                    text=f"📄 {fname}",
                    values=tuple("" for _ in self.columns_config),
                    tags=("file_node",)
                )
            except Exception:
                pass

    def _clear_file_children(self, parent_iid):
        for c in list(self.tree.get_children(parent_iid)):
            if c in self._iid_to_file:
                self._iid_to_file.pop(c, None)
                try:
                    self.tree.delete(c)
                except Exception:
                    pass

    def on_tree_open(self, event):
        if not self.show_files:
            try:
                item = self.tree.focus()
                if item and item not in self._iid_to_file:
                    self._clear_file_children(item)
            except Exception:
                pass
            return
        item = self.tree.focus()
        if not item or item in self._iid_to_file:
            return
        self._clear_file_children(item)
        path = self._get_item_path(item)
        if not path:
            return
        node = self.root_node.find_by_path(path) if self.root_node else None
        if node:
            self._insert_files_under(item, node)

    def _open_file_with_system(self, file_path):
        if not os.path.exists(file_path):
            messagebox.showerror("错误", "文件不存在")
            return
        try:
            if os.name == 'nt':
                os.startfile(file_path)
            else:
                _sp = subprocess
                _sp.Popen(['xdg-open', file_path])
        except Exception as e:
            log_error(f"打开文件失败: {traceback.format_exc()}")
            messagebox.showerror("打开失败", str(e))

    # ==================== 进度窗口 ====================
    def _create_progress_window(self, title):
        win = tk.Toplevel(self.root)
        win.title(title)
        win.geometry("440x140")
        win.transient(self.root)
        win.grab_set()
        win.resizable(False, False)
        try:
            self.root.update_idletasks()
            px = self.root.winfo_x() + (self.root.winfo_width() - 440) // 2
            py = self.root.winfo_y() + (self.root.winfo_height() - 140) // 2
            win.geometry(f"+{max(0, px)}+{max(0, py)}")
        except Exception:
            pass
        ttk.Label(win, text=title, font=('Arial', 11, 'bold')).pack(pady=(14, 6))
        msg_var = tk.StringVar(value="准备中...")
        ttk.Label(win, textvariable=msg_var, foreground="#333").pack(pady=4)
        pbar = ttk.Progressbar(win, mode='indeterminate', length=380)
        pbar.pack(pady=10)
        pbar.start(15)
        win._msg_var = msg_var
        win._pbar = pbar
        win.update_idletasks()
        return win

    def _update_progress(self, win, text):
        try:
            win._msg_var.set(text)
            win.update_idletasks()
        except Exception:
            pass

    # ==================== 打开库 ====================
    def change_library_path(self):
        new_dir = filedialog.askdirectory(title="选择库根目录")
        if not new_dir:
            return
        if not os.path.isdir(new_dir):
            messagebox.showerror("错误", f"文件夹不存在：{new_dir}")
            return
        new_dir = os.path.normpath(new_dir)
        progress_win = self._create_progress_window("正在打开文件夹")
        stats = {"added": 0, "removed": 0, "renamed": 0, "files": 0}
        total_nodes = 0
        error_happened = False
        error_msg = ""
        try:
            self._ui_ready = False
            config_path = os.path.join(new_dir, CONFIG_FILE)
            if os.path.exists(config_path):
                self._update_progress(progress_win, "加载配置文件...")
                with open(config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.base_dir = new_dir
                root_dict = data.get("tree", {})
                if root_dict:
                    self.root_node = Node.from_dict(root_dict)
                    self.root_node.set_path(self.base_dir)
                else:
                    self.root_node = Node(os.path.basename(new_dir) or "Library")
                    self.root_node.set_path(self.base_dir)
                cols = data.get("columns")
                if cols:
                    self.columns_config = cols
                rh = data.get("row_height")
                if rh:
                    try:
                        self.row_height = int(rh)
                    except Exception:
                        pass
                self.auto_wrap = bool(data.get("auto_wrap", False))
                mwl = data.get("max_wrap_lines", 2)
                try:
                    self.max_wrap_lines = max(1, min(5, int(mwl)))
                except Exception:
                    self.max_wrap_lines = 2
                self.show_files = bool(data.get("show_files", True))
                try:
                    self._show_files_var.set(self.show_files)
                except Exception:
                    pass
                try:
                    self._auto_wrap_var.set(self.auto_wrap)
                except Exception:
                    pass
                self._ensure_column_attr_defaults()
                self.ui_state = data.get("ui_state", None)
                geom = data.get("window_geometry")
                if geom:
                    try:
                        self.root.geometry(geom)
                    except Exception:
                        pass
            else:
                self._update_progress(progress_win, "从磁盘构建结构...")
                self.base_dir = new_dir
                root_name = os.path.basename(new_dir.rstrip(os.sep)) or "Library"
                self.root_node = Node(root_name)
                self.root_node.set_path(self.base_dir)
                self.ui_state = None
                self._ensure_column_attr_defaults()
            self.display_nodes = None
            self.filter_keyword.set("")
            self._update_progress(progress_win, "扫描所有子文件夹及文件...")
            self._recursive_sync_tree(self.root_node, self.base_dir, stats, is_startup=True, count_files=True)
            self._update_progress(progress_win, "渲染界面...")
            self._rebuild_tree_columns()
            self._apply_row_height()
            self._apply_saved_ui_state()
            self.save_config()
            total_nodes = self._count_nodes(self.root_node)
        except Exception as e:
            error_happened = True
            error_msg = str(e)
            log_error(f"打开库失败: {traceback.format_exc()}")
        finally:
            try:
                progress_win.destroy()
            except Exception:
                pass
            self._ui_ready = True
        if error_happened:
            messagebox.showerror("打开失败", f"无法打开文件夹：\n{error_msg}")
            return
        self.status_var.set(f"已打开库：{self.base_dir}  |  节点 {total_nodes}  ·  文件 {stats['files']}")
        msg_lines = [
            f"库根目录：{self.base_dir}", "",
            f"节点总数：{total_nodes}", f"文件总数：{stats['files']}", "",
            "扫描结果：",
            f"  • 新增节点：{stats['added']} 个",
            f"  • 名称更新：{stats['renamed']} 个",
            f"  • 清理无效：{stats['removed']} 个",
        ]
        messagebox.showinfo("打开成功", "\n".join(msg_lines))

    # ==================== 展开/折叠 ====================
    def _count_nodes(self, n):
        cnt = 1
        for c in n.children:
            cnt += self._count_nodes(c)
        return cnt

    def expand_to_level(self, level):
        if not self.root_node:
            return
        if level < 1:
            level = 1
        if level > 20:
            level = 20
        total = self._count_nodes(self.root_node)
        if total > 5000:
            if not messagebox.askyesno("确认", f"树中共有 {total} 个节点，展开到第 {level} 级可能需要几秒钟，确定继续？"):
                return
        expanded_paths = set()
        def collect(node, depth):
            if depth < level:
                if node.path:
                    expanded_paths.add(node.path)
                for child in node.children:
                    collect(child, depth + 1)
        collect(self.root_node, 0)
        self.populate_tree(keep_expanded=True, expanded_paths_override=expanded_paths)
        self.status_var.set(f"已展开到第 {level} 级（共 {len(expanded_paths)} 个节点展开）")

    def expand_all(self):
        if not self.root_node:
            return
        total = self._count_nodes(self.root_node)
        if total > 5000:
            if not messagebox.askyesno("确认", f"树中共有 {total} 个节点，全部展开可能需要几秒钟，确定继续？"):
                return
        expanded_paths = set()
        def collect(node):
            if node.path:
                expanded_paths.add(node.path)
            for child in node.children:
                collect(child)
        collect(self.root_node)
        self.populate_tree(keep_expanded=True, expanded_paths_override=expanded_paths)
        self.status_var.set(f"已全部展开（共 {len(expanded_paths)} 个节点）")

    def collapse_all(self):
        if not self.root_node:
            return
        self.populate_tree(keep_expanded=True, expanded_paths_override=set())
        self.status_var.set("已全部折叠（仅显示根节点）")

    def _expand_by_input(self, event=None):
        try:
            val = self._level_entry_var.get().strip()
        except Exception:
            return
        if not val:
            messagebox.showinfo("提示", "请输入要展开到的层级数字（如 1、2、3…）")
            return
        try:
            lvl = int(val)
        except ValueError:
            messagebox.showerror("错误", f"请输入有效整数，当前输入：{val}")
            return
        if lvl < 1 or lvl > 20:
            messagebox.showerror("错误", "层级范围：1 ~ 20")
            return
        self.expand_to_level(lvl)

    def _collapse_by_input(self, event=None):
        try:
            val = self._level_entry_var.get().strip()
        except Exception:
            return
        if not val:
            messagebox.showinfo("提示", "请输入要折叠到的层级数字（0 表示全部折叠）")
            return
        try:
            lvl = int(val)
        except ValueError:
            messagebox.showerror("错误", f"请输入有效整数，当前输入：{val}")
            return
        if lvl < 0 or lvl > 20:
            messagebox.showerror("错误", "层级范围：0 ~ 20（0 表示全部折叠）")
            return
        if lvl == 0:
            self.collapse_all()
            return
        self.expand_to_level(lvl)

    def _create_expand_bar(self):
        bar = ttk.Frame(self.root, relief=tk.RAISED, borderwidth=1)
        bar.pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Label(bar, text="展开/折叠:", font=('Arial', 9, 'bold')).pack(side=tk.LEFT, padx=(10, 6))
        for lvl in range(1, 6):
            ttk.Button(bar, text=f"第{lvl}级", width=7,
                       command=lambda L=lvl: self.expand_to_level(L)).pack(side=tk.LEFT, padx=2, pady=3)
        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6, pady=3)
        ttk.Label(bar, text="输入层级:").pack(side=tk.LEFT, padx=(4, 2))
        self._level_entry_var = tk.StringVar()
        self._level_entry = ttk.Entry(bar, textvariable=self._level_entry_var, width=5)
        self._level_entry.pack(side=tk.LEFT, padx=2)
        self._level_entry.bind("<Return>", self._expand_by_input)
        ttk.Button(bar, text="展开", width=6, command=self._expand_by_input).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="折叠到", width=7, command=self._collapse_by_input).pack(side=tk.LEFT, padx=2)
        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6, pady=3)
        ttk.Button(bar, text="📂 全部展开", width=12, command=self.expand_all).pack(side=tk.LEFT, padx=2, pady=3)
        ttk.Button(bar, text="📁 全部折叠", width=12, command=self.collapse_all).pack(side=tk.LEFT, padx=2, pady=3)
        ttk.Label(bar, text="（输入数字后回车或点「展开」，可展开到第 N 级）", foreground="#666").pack(side=tk.LEFT, padx=10)

    # ==================== 列属性默认值补全 ====================
    def _ensure_column_attr_defaults(self):
        for c in self.columns_config:
            if "wrap" not in c:
                c["wrap"] = (c["id"] == "path")
            if "align" not in c:
                cid = c["id"]
                if cid == "price":
                    c["align"] = "right"
                elif cid in ("version", "update_time"):
                    c["align"] = "center"
                else:
                    c["align"] = "left"

    def _align_to_anchor(self, align):
        return {"left": "w", "center": "center", "right": "e"}.get(align, "w")

    # ==================== 换行核心 ====================
    def _get_wrap_font(self):
        if self._wrap_font is None:
            try:
                self._wrap_font = tkfont.nametofont("TkDefaultFont")
            except Exception:
                self._wrap_font = tkfont.Font()
        return self._wrap_font

    def _wrap_text_to_width(self, text, pixel_width, max_lines):
        if not text:
            return ""
        text = str(text)
        if pixel_width <= 0:
            return text
        font = self._get_wrap_font()
        max_lines = max(1, int(max_lines))
        result_lines = []
        for para in text.split("\n"):
            if not para:
                result_lines.append("")
                continue
            current = ""
            current_w = 0
            for ch in para:
                ch_w = font.measure(ch)
                if current and current_w + ch_w > pixel_width:
                    result_lines.append(current)
                    current = ch
                    current_w = ch_w
                else:
                    current += ch
                    current_w += ch_w
            if current:
                result_lines.append(current)
        if len(result_lines) > max_lines:
            result_lines = result_lines[:max_lines]
            if result_lines:
                last = result_lines[-1]
                ellipsis_w = font.measure("…")
                while last and font.measure(last) + ellipsis_w > pixel_width:
                    last = last[:-1]
                result_lines[-1] = last + "…"
        return "\n".join(result_lines)

    def _get_cell_wrapped_value(self, node, col):
        raw = self._get_cell_value(node, col["id"])
        if not raw:
            return ""
        if not col.get("wrap", False):
            return raw
        w = col.get("width", 120)
        try:
            w = int(self.tree.column(col["id"], "width"))
        except Exception:
            pass
        usable = max(40, w - 16)
        return self._wrap_text_to_width(raw, usable, self.max_wrap_lines)

    def _compute_and_apply_wrapped_rowheight(self):
        if not self.auto_wrap:
            try:
                self.style.configure("Treeview", rowheight=self.row_height)
            except Exception:
                pass
            return
        wrap_cols = [c for c in self.columns_config if c.get("wrap", False)]
        if not wrap_cols:
            try:
                self.style.configure("Treeview", rowheight=self.row_height)
            except Exception:
                pass
            return
        max_lines = 1
        max_cap = max(1, int(self.max_wrap_lines))
        nodes_to_check = []
        if self.root_node:
            if self.display_nodes is not None:
                def collect_visible(n):
                    if n.path in self.display_nodes:
                        nodes_to_check.append(n)
                    for c in n.children:
                        collect_visible(c)
                collect_visible(self.root_node)
            else:
                nodes_to_check = self.root_node.get_all_nodes()
        col_widths = {}
        for c in wrap_cols:
            try:
                col_widths[c["id"]] = max(40, int(self.tree.column(c["id"], "width")) - 16)
            except Exception:
                col_widths[c["id"]] = max(40, c.get("width", 120) - 16)
        for node in nodes_to_check:
            for c in wrap_cols:
                raw = self._get_cell_value(node, c["id"])
                if not raw:
                    continue
                usable = col_widths.get(c["id"], 120)
                rough = len(str(raw)) * 8
                if rough <= usable:
                    continue
                wrapped = self._wrap_text_to_width(raw, usable, max_cap)
                lines = wrapped.count("\n") + 1
                if lines > max_lines:
                    max_lines = lines
                    if max_lines >= max_cap:
                        break
            if max_lines >= max_cap:
                break
        new_h = self.row_height * max_lines
        try:
            self.style.configure("Treeview", rowheight=new_h)
        except Exception:
            log_error(f"设置换行行高失败: {traceback.format_exc()}")

    def toggle_auto_wrap(self):
        self.auto_wrap = not self.auto_wrap
        try:
            self._auto_wrap_var.set(self.auto_wrap)
        except Exception:
            pass
        expanded = self._collect_expanded_paths()
        self.populate_tree(keep_expanded=True, expanded_paths_override=expanded)
        self.save_config()
        state = "开启" if self.auto_wrap else "关闭"
        self.status_var.set(f"自动换行已{state}（最大 {self.max_wrap_lines} 行）")

    def set_max_wrap_lines(self):
        current = int(self.max_wrap_lines)
        result = simpledialog.askinteger(
            "最大换行行数",
            f"请输入每个单元格最多显示的行数（1 ~ 5）：\n\n当前：{current}",
            initialvalue=current, minvalue=1, maxvalue=5, parent=self.root)
        if result is None:
            return
        self.max_wrap_lines = int(result)
        if self.auto_wrap:
            expanded = self._collect_expanded_paths()
            self.populate_tree(keep_expanded=True, expanded_paths_override=expanded)
        self.save_config()
        self.status_var.set(f"最大换行行数已设置为 {self.max_wrap_lines}")

    def _schedule_wrap_recompute(self):
        if not self.auto_wrap:
            return
        if self._wrap_recompute_after_id is not None:
            try:
                self.root.after_cancel(self._wrap_recompute_after_id)
            except Exception:
                pass
        self._wrap_recompute_after_id = self.root.after(600, self._do_wrap_recompute)

    def _do_wrap_recompute(self):
        self._wrap_recompute_after_id = None
        try:
            expanded = self._collect_expanded_paths()
            self.populate_tree(keep_expanded=True, expanded_paths_override=expanded)
        except Exception:
            log_error(f"换行重算失败: {traceback.format_exc()}")

    def _apply_row_height(self):
        if self.auto_wrap:
            self._compute_and_apply_wrapped_rowheight()
        else:
            try:
                self.style.configure("Treeview", rowheight=self.row_height)
            except Exception:
                log_error(f"应用行高失败: {traceback.format_exc()}")

    def adjust_row_height(self):
        current = int(self.row_height)
        result = simpledialog.askinteger(
            "调整行高（含图标大小）",
            f"请输入行高像素值（20 ~ 80）：\n\n当前行高：{current}",
            initialvalue=current, minvalue=20, maxvalue=80, parent=self.root)
        if result is None:
            return
        self.row_height = int(result)
        self._apply_row_height()
        if self.auto_wrap:
            expanded = self._collect_expanded_paths()
            self.populate_tree(keep_expanded=True, expanded_paths_override=expanded)
        self.save_config()
        self.status_var.set(f"行高已调整为 {self.row_height} 像素")

    def _sync_current_column_widths(self):
        if not hasattr(self, "tree"):
            return
        try:
            current_cols = self.tree.cget("columns")
            if isinstance(current_cols, str):
                current_cols = [current_cols]
            else:
                current_cols = list(current_cols)
        except Exception:
            return
        if not current_cols:
            return
        for c in self.columns_config:
            cid = c["id"]
            if cid not in current_cols:
                continue
            try:
                w = self.tree.column(cid, "width")
                if w:
                    c["width"] = int(w)
            except Exception:
                pass

    # ==================== 列右键操作 ====================
    def _get_column_index(self, col_id):
        for i, c in enumerate(self.columns_config):
            if c["id"] == col_id:
                return i
        return -1

    def _generate_unique_column_id(self, name):
        existing_ids = {c["id"] for c in self.columns_config}
        base_id = "custom_" + re.sub(r'\W+', '_', name)
        new_id = base_id
        i = 1
        while new_id in existing_ids:
            new_id = f"{base_id}_{i}"
            i += 1
        return new_id

    def _refresh_after_column_change(self):
        expanded = self._collect_expanded_paths()
        self._rebuild_tree_columns()
        self.populate_tree(keep_expanded=True, expanded_paths_override=expanded)
        self.save_config()

    def rename_column_by_id(self, col_id):
        idx = self._get_column_index(col_id)
        if idx < 0:
            return
        col = self.columns_config[idx]
        new_name = simpledialog.askstring("重命名列",
            f"请输入新的列名：\n\n当前列名：{col['title']}",
            initialvalue=col["title"], parent=self.root)
        if not new_name:
            return
        new_name = new_name.strip()
        if not new_name:
            return
        for i, c in enumerate(self.columns_config):
            if i != idx and c["title"] == new_name:
                messagebox.showerror("错误", f"列名 '{new_name}' 已存在")
                return
        col["title"] = new_name
        self._refresh_after_column_change()
        self.status_var.set(f"列已重命名为 '{new_name}'")

    def insert_column_relative(self, col_id, position):
        idx = self._get_column_index(col_id)
        if idx < 0:
            return
        ref_title = self.columns_config[idx]["title"]
        side = "左" if position == "left" else "右"
        name = simpledialog.askstring("插入新列",
            f"将在「{ref_title}」{side}侧插入新列。\n\n请输入新列名称：", parent=self.root)
        if not name:
            return
        name = name.strip()
        if not name:
            return
        for c in self.columns_config:
            if c["title"] == name:
                messagebox.showerror("错误", f"列名 '{name}' 已存在")
                return
        new_id = self._generate_unique_column_id(name)
        new_col = {"id": new_id, "title": name, "width": 120, "builtin": False, "wrap": True, "align": "left"}
        insert_at = idx if position == "left" else idx + 1
        self.columns_config.insert(insert_at, new_col)
        self._refresh_after_column_change()
        self.status_var.set(f"已在「{ref_title}」{side}侧插入新列 '{name}'")

    def move_column_by_id(self, col_id, direction):
        idx = self._get_column_index(col_id)
        if idx < 0:
            return
        new_idx = idx + direction
        if new_idx < 0 or new_idx >= len(self.columns_config):
            return
        self.columns_config[idx], self.columns_config[new_idx] = self.columns_config[new_idx], self.columns_config[idx]
        self._refresh_after_column_change()
        title = self.columns_config[new_idx]["title"]
        self.status_var.set(f"列 '{title}' 已{'左移' if direction < 0 else '右移'}一列")

    def delete_column_by_id(self, col_id):
        idx = self._get_column_index(col_id)
        if idx < 0:
            return
        col = self.columns_config[idx]
        is_builtin = bool(col.get("builtin"))
        title = col["title"]
        data_count = 0
        if self.root_node:
            for node in self.root_node.get_all_nodes():
                if node.extra_fields.get(col_id, ""):
                    data_count += 1
        if is_builtin:
            special_hint = ""
            if col_id == "path":
                special_hint = ("\n• 提示：本程序使用内部标识定位节点，"
                                "删除「路径」列后，节点管理、文件操作、导入导出等"
                                "功能均不受影响。\n")
            elif col_id == "version":
                special_hint = "\n• 提示：删除后节点版本号仍保存在配置文件中。\n"
            elif col_id == "price":
                special_hint = "\n• 提示：删除后节点价格仍保存在配置文件中。\n"
            elif col_id == "update_time":
                special_hint = "\n• 提示：删除后节点更新时间仍保存在配置文件中。\n"
            warning_msg = (
                f"⚠ 您正在删除内置列「{title}」\n\n"
                f"删除后：\n"
                f"  • 树视图中不再显示该列\n"
                f"  • 节点编辑器中的对应输入框会消失\n"
                f"  • 已填入该列的节点数据仍保留在配置文件中\n"
                f"{special_hint}\n确定要删除内置列「{title}」吗？"
            )
            if not messagebox.askyesno("⚠ 删除内置列确认", warning_msg):
                return
        else:
            msg = f"确定删除列「{title}」吗？"
            if data_count:
                msg += (f"\n\n注意：该列已有 {data_count} 个节点填过数据。\n"
                        f"删除后树中不再显示该列，但节点数据仍保留在配置文件里。")
            if not messagebox.askyesno("确认删除", msg):
                return
        del self.columns_config[idx]
        self._refresh_after_column_change()
        self.status_var.set(f"已删除列 '{title}'")

    def _show_column_context_menu(self, event, col_id):
        idx = self._get_column_index(col_id)
        if idx < 0:
            return
        col = self.columns_config[idx]
        is_first = idx == 0
        is_last = idx == len(self.columns_config) - 1
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label=f"重命名「{col['title']}」…", command=lambda: self.rename_column_by_id(col_id))
        menu.add_separator()
        menu.add_command(label="在其左侧插入新列…", command=lambda: self.insert_column_relative(col_id, "left"))
        menu.add_command(label="在其右侧插入新列…", command=lambda: self.insert_column_relative(col_id, "right"))
        menu.add_separator()
        menu.add_command(label="← 左移一列", command=lambda: self.move_column_by_id(col_id, -1),
                         state="disabled" if is_first else "normal")
        menu.add_command(label="右移一列 →", command=lambda: self.move_column_by_id(col_id, 1),
                         state="disabled" if is_last else "normal")
        menu.add_separator()
        wrap_label = "关闭自动断行" if col.get("wrap", False) else "开启自动断行"
        menu.add_command(label=wrap_label, command=lambda: self._quick_toggle_wrap(col_id))
        align_menu = tk.Menu(menu, tearoff=0)
        align_menu.add_command(label="靠左", command=lambda: self._quick_set_align(col_id, "left"))
        align_menu.add_command(label="居中", command=lambda: self._quick_set_align(col_id, "center"))
        align_menu.add_command(label="靠右", command=lambda: self._quick_set_align(col_id, "right"))
        menu.add_cascade(label="对齐方式", menu=align_menu)
        menu.add_separator()
        menu.add_command(label="🗑 删除此列", command=lambda: self.delete_column_by_id(col_id))
        menu.add_separator()
        menu.add_command(label="⚙ 管理所有列…", command=self.manage_columns)
        menu.post(event.x_root, event.y_root)

    def _quick_toggle_wrap(self, col_id):
        idx = self._get_column_index(col_id)
        if idx < 0:
            return
        col = self.columns_config[idx]
        col["wrap"] = not col.get("wrap", False)
        self._refresh_after_column_change()
        state = "开启" if col["wrap"] else "关闭"
        self.status_var.set(f"列「{col['title']}」自动断行已{state}")

    def _quick_set_align(self, col_id, align):
        idx = self._get_column_index(col_id)
        if idx < 0:
            return
        col = self.columns_config[idx]
        col["align"] = align
        self._refresh_after_column_change()
        cn = {"left": "靠左", "center": "居中", "right": "靠右"}[align]
        self.status_var.set(f"列「{col['title']}」对齐方式已设置为「{cn}」")

    # ==================== 启动异步同步 ====================
    def _auto_sync_on_startup(self):
        if not self.root_node or not self.base_dir or not os.path.exists(self.base_dir):
            return
        self.status_var.set("正在后台同步磁盘文件夹…")
        self.root.update_idletasks()
        try:
            stats = {"added": 0, "removed": 0, "renamed": 0, "files": 0}
            self._recursive_sync_tree(self.root_node, self.base_dir, stats, is_startup=True, count_files=False)
            if stats["added"] or stats["removed"] or stats["renamed"]:
                self.save_config()
                expanded = self._collect_expanded_paths()
                self.populate_tree(keep_expanded=True, expanded_paths_override=expanded)
                self.status_var.set(
                    f"自动同步完成：新增 {stats['added']} · 改名 {stats['renamed']} · 清理 {stats['removed']}"
                )
            else:
                self.status_var.set(f"磁盘与树一致，无需同步（根目录: {self.base_dir}）")
        except Exception as e:
            log_error(f"启动同步失败: {traceback.format_exc()}")
            self.status_var.set("同步失败，请查看 error.log")

    def _recursive_sync_tree(self, parent_node, disk_path, stats, is_startup=False, count_files=False):
        try:
            with os.scandir(disk_path) as it:
                disk_dirs = []
                for e in it:
                    if e.name.startswith('.'):
                        continue
                    if e.is_dir(follow_symlinks=False):
                        disk_dirs.append((e.name, e.path))
                    elif count_files and e.is_file(follow_symlinks=False):
                        stats["files"] += 1
        except (PermissionError, OSError):
            return
        disk_map = {}
        for real_name, full_path in disk_dirs:
            norm = parent_node._normalize_name(real_name)
            disk_map[norm] = (real_name, full_path)
        child_map = {parent_node._normalize_name(c.name): c for c in parent_node.children}
        if is_startup:
            to_remove = []
            for child in parent_node.children:
                norm = parent_node._normalize_name(child.name)
                if norm not in disk_map:
                    to_remove.append(child)
            for child in to_remove:
                parent_node.children.remove(child)
                stats["removed"] += 1
        for norm, (real_name, full_path) in disk_map.items():
            existing = child_map.get(norm)
            if existing:
                if existing.name != real_name:
                    existing.name = real_name
                    existing.path = full_path
                    existing._update_children_paths()
                    stats["renamed"] += 1
                self._recursive_sync_tree(existing, full_path, stats, is_startup, count_files)
            else:
                new_child = Node(real_name)
                new_child.parent = parent_node
                new_child.path = full_path
                parent_node.children.append(new_child)
                stats["added"] += 1
                self._recursive_sync_tree(new_child, full_path, stats, is_startup, count_files)

    # ---------------------------- 菜单栏 ----------------------------
    def create_menu(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="文件", menu=file_menu)
        file_menu.add_command(label="打开库（选择文件夹并读取全部内容）", command=self.change_library_path)
        file_menu.add_command(label="同步磁盘文件夹", command=self.sync_disk_folders)
        file_menu.add_command(label="递归同步子文件夹", command=self.sync_subfolders_recursive)
        file_menu.add_separator()
        file_menu.add_command(label="导出所选节点…", command=self.export_selected_nodes)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self.on_closing)

        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="视图", menu=view_menu)
        view_menu.add_command(label="刷新", command=self.refresh_tree)
        view_menu.add_separator()
        expand_menu = tk.Menu(view_menu, tearoff=0)
        for lvl in range(1, 11):
            expand_menu.add_command(label=f"展开到第 {lvl} 级",
                                    command=lambda L=lvl: self.expand_to_level(L))
        expand_menu.add_separator()
        expand_menu.add_command(label="全部展开", command=self.expand_all)
        expand_menu.add_command(label="全部折叠", command=self.collapse_all)
        view_menu.add_cascade(label="展开/折叠", menu=expand_menu)
        view_menu.add_separator()
        view_menu.add_command(label="管理列…", command=self.manage_columns)
        view_menu.add_command(label="恢复默认列", command=self.reset_columns)
        view_menu.add_separator()
        view_menu.add_command(label="调整行高（含图标大小）…", command=self.adjust_row_height)
        view_menu.add_separator()
        self._show_files_var = tk.BooleanVar(value=self.show_files)
        view_menu.add_checkbutton(
            label="显示文件（磁盘文件作为子项）",
            variable=self._show_files_var,
            command=self.toggle_show_files
        )
        view_menu.add_separator()
        self._auto_wrap_var = tk.BooleanVar(value=self.auto_wrap)
        view_menu.add_checkbutton(label="自动换行（按列宽）", variable=self._auto_wrap_var, command=self.toggle_auto_wrap)
        view_menu.add_command(label="最大换行行数…", command=self.set_max_wrap_lines)

        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="帮助", menu=help_menu)
        help_menu.add_command(label="操作说明", command=self.show_drag_help)
        help_menu.add_separator()
        help_menu.add_command(label="🔧 安装/更新支持库…", command=self.install_support_libs_manual)

    def show_drag_help(self):
        messagebox.showinfo(
            "操作说明",
            "【★ 首次启动】\n"
            "  首次启动会弹窗让您选择「库根目录」：\n"
            "  • 选中的文件夹即成为您的文件库根目录\n"
            "  • 该文件夹下已有的所有子文件夹会被自动扫描为节点\n"
            "  • 程序不再自动创建任何默认模板\n"
            "  • 之后可通过「文件 → 打开库」随时切换根目录\n\n"
            "【★ 显示文件开关】\n"
            "  视图 → ☑ 显示文件（磁盘文件作为子项）\n\n"
            "【★ 拖拽文件（跨窗口）】\n"
            "  从资源管理器拖文件/文件夹到树中任意节点\n\n"
            "【★ 节点备注】\n"
            "  右上角「📝 备注」按钮或右键菜单\n\n"
            "【★ 展开/折叠】\n"
            "  状态栏上方工具条：一键展开/折叠到指定层级\n\n"
            "【★ 支持库自动安装】\n"
            "  启动时自动检测 tkinterdnd2 / Pillow，缺失则自动安装\n"
            "  帮助菜单 → 🔧 安装/更新支持库…  可随时手动补装\n\n"
            "【★ 窗口/列宽记忆】\n"
            "  关闭时自动保存窗口大小、位置、列宽"
        )

    # ==================== 支持库手动安装 ====================
    def install_support_libs_manual(self):
        missing = [p for p in SUPPORT_PACKAGES if not _is_module_available(p["import"])]

        if not missing:
            lines = [f"  • {p['pip']}：✅ 已安装（{p['desc']}）" for p in SUPPORT_PACKAGES]
            messagebox.showinfo(
                "支持库状态",
                "所有支持库均已安装：\n\n" + "\n".join(lines) +
                "\n\n如需更新版本，可在命令行执行：\n"
                "    pip install --upgrade tkinterdnd2 Pillow"
            )
            return

        installed, failed, _ = install_missing_support_libs(ask=False, parent=self.root)

        if installed > 0:
            _try_import_optional_libs()
            msg = f"✅ 已成功安装 {installed} 个支持库。\n\n"
            msg += "📌 建议重启程序，以便所有功能（尤其是跨窗口拖拽）完全生效。"
            if failed:
                msg += "\n\n⚠ 以下支持库安装失败：\n" + \
                       "\n".join(f"  • {n}：{e}" for n, e in failed)
            messagebox.showinfo("安装完成", msg)
        elif failed:
            detail = "\n".join(f"  • {n}：{e}" for n, e in failed)
            messagebox.showerror(
                "安装失败",
                f"以下支持库安装失败：\n\n{detail}\n\n"
                "您可以手动在命令行执行：\n"
                "    pip install tkinterdnd2 Pillow\n\n"
                "或使用国内镜像加速：\n"
                "    pip install -i https://pypi.tuna.tsinghua.edu.cn/simple tkinterdnd2 Pillow"
            )

    # ---------------------------- 列管理对话框 ----------------------------
    def _rebuild_tree_columns(self):
        if not hasattr(self, "tree"):
            return
        self._sync_current_column_widths()
        col_ids = [c["id"] for c in self.columns_config]
        self.tree.configure(columns=col_ids, displaycolumns=col_ids)
        self.tree.heading("#0", text="名称", command=lambda: self.on_column_click("#0"))
        self.tree.column("#0", width=200, minwidth=100, anchor="w")
        for c in self.columns_config:
            cid = c["id"]
            anchor = self._align_to_anchor(c.get("align", "left"))
            self.tree.heading(cid, text=c["title"], command=lambda x=cid: self.on_column_click(x))
            self.tree.column(cid, width=c.get("width", 120), minwidth=60, anchor=anchor)
        try:
            self._path_col_index = col_ids.index("path")
        except ValueError:
            self._path_col_index = 0

    def reset_columns(self):
        if not messagebox.askyesno("确认", "确定恢复为默认列？自定义列的数据会保留但不再显示。"):
            return
        expanded_paths = self._collect_expanded_paths()
        self.columns_config = [dict(c) for c in DEFAULT_COLUMNS]
        self._rebuild_tree_columns()
        self.populate_tree(keep_expanded=True, expanded_paths_override=expanded_paths)
        self.save_config()
        self.status_var.set("已恢复默认列（展开状态已保留）")

    def manage_columns(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("管理列")
        dialog.geometry("640x620")
        dialog.transient(self.root)
        dialog.grab_set()
        ttk.Label(dialog, text="选中下方任意列，可设置列名、自动断行、对齐方式；双击可重命名").pack(pady=5, anchor="w", padx=10)
        list_frame = ttk.Frame(dialog)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        listbox = tk.Listbox(list_frame, selectmode=tk.SINGLE, height=10)
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=listbox.yview)
        listbox.configure(yscrollcommand=scroll.set)
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        props_frame = ttk.LabelFrame(dialog, text="列属性（选中列后设置）")
        props_frame.pack(fill=tk.X, padx=10, pady=6)
        wrap_var = tk.BooleanVar(value=False)
        wrap_cb = ttk.Checkbutton(props_frame, text="自动断行（内容超过列宽时折行）", variable=wrap_var)
        wrap_cb.pack(anchor="w", padx=10, pady=(8, 4))
        align_frame = ttk.Frame(props_frame)
        align_frame.pack(anchor="w", padx=10, pady=4)
        ttk.Label(align_frame, text="对齐方式:").pack(side=tk.LEFT, padx=(0, 8))
        align_var = tk.StringVar(value="left")
        ttk.Radiobutton(align_frame, text="靠左", variable=align_var, value="left").pack(side=tk.LEFT, padx=4)
        ttk.Radiobutton(align_frame, text="居中", variable=align_var, value="center").pack(side=tk.LEFT, padx=4)
        ttk.Radiobutton(align_frame, text="靠右", variable=align_var, value="right").pack(side=tk.LEFT, padx=4)
        hint_label = ttk.Label(props_frame, text="", foreground="#666")
        hint_label.pack(anchor="w", padx=10, pady=(2, 8))
        current_col_id = {"value": None}

        def refresh_list():
            listbox.delete(0, tk.END)
            for c in self.columns_config:
                tag = " [内置]" if c.get("builtin") else ""
                wrap_mark = " ⏎" if c.get("wrap", False) else ""
                align_mark = {"left": "←", "center": "≡", "right": "→"}.get(c.get("align", "left"), "")
                listbox.insert(tk.END, f"{c['title']}{tag}  {wrap_mark}{align_mark}")

        def update_props_from_selection(event=None):
            sel = listbox.curselection()
            if not sel:
                current_col_id["value"] = None
                wrap_var.set(False)
                align_var.set("left")
                hint_label.config(text="")
                return
            idx = sel[0]
            col = self.columns_config[idx]
            current_col_id["value"] = col["id"]
            wrap_var.set(bool(col.get("wrap", False)))
            align_var.set(col.get("align", "left"))
            is_builtin = bool(col.get("builtin"))
            hint_label.config(text=f"内置列：{'是' if is_builtin else '否'}    列 id：{col['id']}")

        def apply_props_change():
            cid = current_col_id["value"]
            if not cid:
                return
            idx = self._get_column_index(cid)
            if idx < 0:
                return
            col = self.columns_config[idx]
            new_wrap = bool(wrap_var.get())
            new_align = align_var.get()
            changed = False
            if col.get("wrap", False) != new_wrap:
                col["wrap"] = new_wrap
                changed = True
            if col.get("align", "left") != new_align:
                col["align"] = new_align
                changed = True
            if changed:
                self._refresh_after_column_change()
                refresh_list()
                try:
                    listbox.selection_set(idx)
                except Exception:
                    pass

        wrap_cb.config(command=apply_props_change)
        for rb in align_frame.winfo_children():
            if isinstance(rb, ttk.Radiobutton):
                rb.config(command=apply_props_change)
        listbox.bind("<<ListboxSelect>>", update_props_from_selection)

        def apply_change():
            expanded_paths = self._collect_expanded_paths()
            self._rebuild_tree_columns()
            self.populate_tree(keep_expanded=True, expanded_paths_override=expanded_paths)
            self.save_config()
            refresh_list()

        def add_column():
            name = simpledialog.askstring("添加列", "请输入新列名称：", parent=dialog)
            if not name:
                return
            name = name.strip()
            if not name:
                return
            for c in self.columns_config:
                if c["title"] == name:
                    messagebox.showerror("错误", "列名已存在", parent=dialog)
                    return
            new_id = self._generate_unique_column_id(name)
            self.columns_config.append({"id": new_id, "title": name, "width": 120, "builtin": False, "wrap": True, "align": "left"})
            apply_change()
            listbox.selection_clear(0, tk.END)
            listbox.selection_set(len(self.columns_config) - 1)
            listbox.event_generate("<<ListboxSelect>>")

        def remove_column():
            sel = listbox.curselection()
            if not sel:
                return
            idx = sel[0]
            col = self.columns_config[idx]
            is_builtin = bool(col.get("builtin"))
            title = col["title"]
            if is_builtin:
                if not messagebox.askyesno("⚠ 删除内置列确认",
                    f"⚠ 您正在删除内置列「{title}」\n\n确定继续吗？", parent=dialog):
                    return
            else:
                if not messagebox.askyesno("确认", f"确定删除列 '{title}'？", parent=dialog):
                    return
            del self.columns_config[idx]
            apply_change()
            current_col_id["value"] = None
            wrap_var.set(False)
            align_var.set("left")
            hint_label.config(text="")

        def rename_column(event=None):
            sel = listbox.curselection()
            if not sel:
                return
            idx = sel[0]
            col = self.columns_config[idx]
            new_name = simpledialog.askstring("重命名列", "请输入新的列名：",
                initialvalue=col["title"], parent=dialog)
            if not new_name:
                return
            new_name = new_name.strip()
            if not new_name:
                return
            for i, c in enumerate(self.columns_config):
                if i != idx and c["title"] == new_name:
                    messagebox.showerror("错误", "列名已存在", parent=dialog)
                    return
            col["title"] = new_name
            apply_change()
            listbox.selection_set(idx)
            listbox.event_generate("<<ListboxSelect>>")

        def move_up():
            sel = listbox.curselection()
            if not sel or sel[0] == 0:
                return
            idx = sel[0]
            self.columns_config[idx-1], self.columns_config[idx] = self.columns_config[idx], self.columns_config[idx-1]
            apply_change()
            listbox.selection_set(idx-1)
            listbox.event_generate("<<ListboxSelect>>")

        def move_down():
            sel = listbox.curselection()
            if not sel or sel[0] >= len(self.columns_config) - 1:
                return
            idx = sel[0]
            self.columns_config[idx+1], self.columns_config[idx] = self.columns_config[idx], self.columns_config[idx+1]
            apply_change()
            listbox.selection_set(idx+1)
            listbox.event_generate("<<ListboxSelect>>")

        listbox.bind("<Double-Button-1>", rename_column)
        refresh_list()
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill=tk.X, pady=6)
        ttk.Button(btn_frame, text="添加列", command=add_column).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="删除列", command=remove_column).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="重命名", command=rename_column).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="上移", command=move_up).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="下移", command=move_down).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="关闭", command=dialog.destroy).pack(side=tk.RIGHT, padx=4)
        if self.columns_config:
            listbox.selection_set(0)
            update_props_from_selection()

    # ---------------------------- 单元格取值 ----------------------------
    def _get_cell_value(self, node, col_id):
        if col_id == "path":
            return node.path or ""
        elif col_id == "version":
            return node.version
        elif col_id == "price":
            return node.price
        elif col_id == "update_time":
            return node.update_time
        else:
            return node.extra_fields.get(col_id, "")

    def _get_node_values(self, node):
        if not node.path:
            return tuple("" for _ in self.columns_config)
        if not self.auto_wrap:
            return tuple(self._get_cell_value(node, c["id"]) for c in self.columns_config)
        return tuple(self._get_cell_wrapped_value(node, c) for c in self.columns_config)

    def _get_item_path(self, item):
        return self._iid_to_path.get(item, "")

    def _collect_expanded_paths(self, parent="", result=None):
        if result is None:
            result = set()
        try:
            children = self.tree.get_children(parent)
        except Exception:
            return result
        for item in children:
            try:
                if self.tree.item(item, "open"):
                    path = self._get_item_path(item)
                    if path:
                        result.add(path)
            except Exception:
                pass
            self._collect_expanded_paths(item, result)
        return result

    # ==================== UI 状态保存与恢复 ====================
    def _capture_ui_state(self):
        if not self._ui_ready or not hasattr(self, "tree"):
            return None
        try:
            items = self.tree.get_children()
        except Exception:
            return None
        if not items:
            return None
        try:
            state = {
                "expanded_paths": list(self._collect_expanded_paths()),
                "selected_paths": [],
                "column_widths": {},
                "scroll_y": 0.0,
            }
            for it in self.tree.selection():
                if it in self._iid_to_file:
                    continue
                p = self._get_item_path(it)
                if p:
                    state["selected_paths"].append(p)
            for c in self.columns_config:
                cid = c["id"]
                try:
                    w = self.tree.column(cid, "width")
                    if w:
                        w = int(w)
                        state["column_widths"][cid] = w
                        c["width"] = w
                except Exception:
                    pass
            try:
                yv = self.tree.yview()
                if yv:
                    state["scroll_y"] = float(yv[0])
            except Exception:
                pass
            return state
        except Exception:
            return None

    def _restore_ui_state(self, state):
        if not state:
            return
        try:
            for path in state.get("selected_paths", []):
                item = self._path_to_iid.get(path)
                if item and self.tree.exists(item):
                    self.tree.selection_add(item)
        except Exception:
            pass
        try:
            y = state.get("scroll_y", 0)
            if y and 0 <= y < 1:
                self.tree.yview_moveto(y)
        except Exception:
            pass

    def _apply_saved_ui_state(self):
        if self.ui_state:
            expanded = set(self.ui_state.get("expanded_paths", []))
            self.populate_tree(keep_expanded=True, expanded_paths_override=expanded)
        else:
            self.populate_tree()
        self._restore_ui_state(self.ui_state)

    # ============================================================
    # 拖拽交互（内部节点拖拽）
    # ============================================================
    def _setup_drag_interactions(self):
        self.tree.bind("<ButtonPress-1>", self._on_tree_button_press, add="+")
        self.tree.bind("<B1-Motion>", self._on_tree_motion, add="+")
        self.tree.bind("<ButtonRelease-1>", self._on_tree_button_release, add="+")
        self.tree.bind("<Escape>", self._cancel_drag, add="+")
        self.tree.tag_configure("drop_before", background="#a8e6a3")
        self.tree.tag_configure("drop_after",  background="#a8e6a3")
        self.tree.tag_configure("drop_inside", background="#a6d4f0")
        self.tree.tag_configure("file_node", foreground="#666")
        self.tree.tag_configure("drop_hover", background="#ffe28a")
        self.tree.tag_configure("drop_invalid", background="#f0a8a8")

    def _column_id_from_identify(self, col_spec):
        if not col_spec:
            return None
        try:
            display_idx = int(col_spec[1:]) - 1
        except Exception:
            return None
        display_cols = self.tree.cget("displaycolumns")
        if isinstance(display_cols, str):
            if display_cols == "#all":
                col_ids = list(self.tree.cget("columns"))
            else:
                col_ids = [display_cols]
        else:
            col_ids = list(display_cols)
            if len(col_ids) == 1 and col_ids[0] == "#all":
                col_ids = list(self.tree.cget("columns"))
        if 0 <= display_idx < len(col_ids):
            return col_ids[display_idx]
        return None

    def _get_column_title(self, col_id):
        for c in self.columns_config:
            if c["id"] == col_id:
                return c["title"]
        return col_id

    def _on_tree_button_press(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region == "heading":
            self._drag_source_item = None
            self._dragging_node = False
            col = self.tree.identify_column(event.x)
            cid = self._column_id_from_identify(col)
            if cid:
                self._col_drag_source_id = cid
                self._col_drag_active = False
                self._col_drag_start_x = event.x
            return
        if region in ("tree", "cell"):
            self._col_drag_source_id = None
            self._col_drag_active = False
            item = self.tree.identify_row(event.y)
            if item and item not in self._iid_to_file:
                self._drag_source_item = item
                self._drag_source_path = self._get_item_path(item)
                self._drag_start_x = event.x
                self._drag_start_y = event.y
                self._dragging_node = False
            else:
                self._drag_source_item = None
                self._dragging_node = False
            return
        self._drag_source_item = None
        self._dragging_node = False
        self._col_drag_source_id = None
        self._col_drag_active = False

    def _on_tree_motion(self, event):
        if self._col_drag_source_id:
            if not self._col_drag_active:
                if abs(event.x - self._col_drag_start_x) > 5:
                    self._col_drag_active = True
            if self._col_drag_active:
                col = self.tree.identify_column(event.x)
                target_id = self._column_id_from_identify(col)
                if target_id and target_id != self._col_drag_source_id:
                    src_t = self._get_column_title(self._col_drag_source_id)
                    tgt_t = self._get_column_title(target_id)
                    self.status_var.set(f"🖱 拖动列「{src_t}」→ 目标列「{tgt_t}」，松开鼠标完成排序")
                else:
                    src_t = self._get_column_title(self._col_drag_source_id)
                    self.status_var.set(f"🖱 正在拖动列「{src_t}」…")
            return
        if self._drag_source_item:
            if not self._dragging_node:
                if (abs(event.x - self._drag_start_x) > 5 or
                        abs(event.y - self._drag_start_y) > 5):
                    self._dragging_node = True
            if self._dragging_node:
                self._update_node_drop_target(event)

    def _update_node_drop_target(self, event):
        target_item = self.tree.identify_row(event.y)
        if not target_item or target_item == self._drag_source_item:
            self._clear_drop_indicator()
            self._drop_target = None
            self._drop_position = None
            return
        if target_item in self._iid_to_file:
            self._clear_drop_indicator()
            self._drop_target = None
            self._drop_position = None
            return
        bbox = self.tree.bbox(target_item)
        if not bbox:
            self._clear_drop_indicator()
            self._drop_target = None
            self._drop_position = None
            return
        _, y, _, h = bbox
        rel = (event.y - y) / max(h, 1)
        if rel < 0.25:
            position = "before"
        elif rel > 0.75:
            position = "after"
        else:
            position = "inside"
        src_node = self.root_node.find_by_path(self._drag_source_path) if self._drag_source_path else None
        tgt_node = self.root_node.find_by_path(self._get_item_path(target_item))
        if src_node is None or tgt_node is None:
            self._clear_drop_indicator()
            self._drop_target = None
            self._drop_position = None
            return
        if src_node == tgt_node or src_node.is_ancestor_of(tgt_node):
            self._clear_drop_indicator()
            self._drop_target = None
            self._drop_position = None
            self.status_var.set("⚠ 不能把节点拖到自己的子孙下")
            return
        if position in ("before", "after") and tgt_node.parent is None:
            position = "inside"
        self._drop_target = target_item
        self._drop_position = position
        self._set_drop_indicator(target_item, position)

    def _set_drop_indicator(self, item, position):
        tag_map = {"before": "drop_before", "after": "drop_after", "inside": "drop_inside"}
        tag = tag_map.get(position)
        if not tag:
            return
        if self._drop_indicator_item and self._drop_indicator_item != item:
            self._restore_indicator_item()
        if self._drop_indicator_item != item:
            try:
                self._drop_indicator_old_tags = self.tree.item(item, "tags")
            except Exception:
                self._drop_indicator_old_tags = ()
        try:
            self.tree.item(item, tags=(tag,))
        except Exception:
            pass
        self._drop_indicator_item = item

    def _restore_indicator_item(self):
        if self._drop_indicator_item:
            try:
                if self.tree.exists(self._drop_indicator_item):
                    old = self._drop_indicator_old_tags or ()
                    self.tree.item(self._drop_indicator_item, tags=old)
            except Exception:
                pass
        self._drop_indicator_item = None
        self._drop_indicator_old_tags = None

    def _clear_drop_indicator(self):
        self._restore_indicator_item()

    def _set_drop_hover(self, item, valid=True):
        if self._drop_hover_item == item:
            if item is not None:
                tag = "drop_hover" if valid else "drop_invalid"
                old = self._drop_hover_old_tags or ()
                new_tags = tuple(t for t in old if t not in ("drop_hover", "drop_invalid"))
                try:
                    self.tree.item(item, tags=new_tags + (tag,))
                except Exception:
                    pass
            return
        self._clear_drop_hover()
        if not item or item in self._iid_to_file:
            return
        try:
            self._drop_hover_old_tags = self.tree.item(item, "tags")
        except Exception:
            self._drop_hover_old_tags = ()
        tag = "drop_hover" if valid else "drop_invalid"
        old = self._drop_hover_old_tags or ()
        new_tags = tuple(t for t in old if t not in ("drop_hover", "drop_invalid"))
        try:
            self.tree.item(item, tags=new_tags + (tag,))
        except Exception:
            pass
        self._drop_hover_item = item

    def _clear_drop_hover(self):
        if self._drop_hover_item:
            try:
                if self.tree.exists(self._drop_hover_item):
                    old = self._drop_hover_old_tags or ()
                    self.tree.item(self._drop_hover_item, tags=old)
            except Exception:
                pass
        self._drop_hover_item = None
        self._drop_hover_old_tags = None

    def _flash_node(self, item, times=3, interval=150):
        if not item or not self.tree.exists(item):
            return
        try:
            old_tags = self.tree.item(item, "tags")
        except Exception:
            old_tags = ()
        state = {"n": 0}

        def tick():
            if state["n"] >= times * 2:
                try:
                    self.tree.item(item, tags=old_tags)
                except Exception:
                    pass
                return
            try:
                if state["n"] % 2 == 0:
                    base = tuple(t for t in old_tags if t not in ("drop_hover", "drop_invalid"))
                    self.tree.item(item, tags=base + ("drop_hover",))
                else:
                    self.tree.item(item, tags=old_tags)
            except Exception:
                return
            state["n"] += 1
            self.root.after(interval, tick)

        tick()

    def _on_tree_button_release(self, event):
        if self._col_drag_source_id:
            source_id = self._col_drag_source_id
            was_active = self._col_drag_active
            self._col_drag_source_id = None
            self._col_drag_active = False
            if was_active:
                col = self.tree.identify_column(event.x)
                target_id = self._column_id_from_identify(col)
                if target_id and target_id != source_id:
                    self._reorder_columns(source_id, target_id)
                    self._last_col_drag_time = time.time()
                    return
                self.status_var.set("列拖拽已取消（未移动到有效目标列）")
            return
        if self._dragging_node and self._drop_target and self._drop_position:
            self._perform_node_move()
        self._clear_drop_indicator()
        self._drag_source_item = None
        self._drag_source_path = None
        self._dragging_node = False
        self._drop_target = None
        self._drop_position = None
        self.root.after(120, self._delayed_column_width_sync)

    def _delayed_column_width_sync(self):
        if not hasattr(self, "tree"):
            return
        changed = False
        try:
            current_cols = self.tree.cget("columns")
            if isinstance(current_cols, str):
                current_cols = [current_cols]
            else:
                current_cols = list(current_cols)
        except Exception:
            return
        for c in self.columns_config:
            cid = c["id"]
            if cid not in current_cols:
                continue
            try:
                w = self.tree.column(cid, "width")
                if w:
                    w = int(w)
                    if c.get("width") != w:
                        c["width"] = w
                        changed = True
            except Exception:
                pass
        if changed:
            self.save_config()
            self._schedule_wrap_recompute()

    def _cancel_drag(self, event=None):
        self._clear_drop_indicator()
        self._clear_drop_hover()
        self._drag_source_item = None
        self._dragging_node = False
        self._col_drag_source_id = None
        self._col_drag_active = False
        self._drop_target = None
        self._drop_position = None
        self.status_var.set("已取消拖拽")

    def _reorder_columns(self, source_id, target_id):
        ids = [c["id"] for c in self.columns_config]
        if source_id not in ids or target_id not in ids:
            return
        expanded_paths = self._collect_expanded_paths()
        src_idx = ids.index(source_id)
        item = self.columns_config.pop(src_idx)
        ids2 = [c["id"] for c in self.columns_config]
        tgt_idx2 = ids2.index(target_id)
        self.columns_config.insert(tgt_idx2, item)
        self._rebuild_tree_columns()
        self.populate_tree(keep_expanded=True, expanded_paths_override=expanded_paths)
        self.save_config()
        src_t = self._get_column_title(source_id)
        tgt_t = self._get_column_title(target_id)
        self.status_var.set(f"列顺序已调整：'{src_t}' 移动到 '{tgt_t}' 前（展开状态已保留）")

    def _perform_node_move(self):
        src_node = self.root_node.find_by_path(self._drag_source_path) if self._drag_source_path else None
        tgt_path = self._get_item_path(self._drop_target) if self._drop_target else ""
        tgt_node = self.root_node.find_by_path(tgt_path) if tgt_path else None
        if src_node is None or tgt_node is None:
            return
        if src_node == tgt_node or src_node.is_ancestor_of(tgt_node):
            return
        position = self._drop_position
        try:
            if position == "inside":
                new_parent = tgt_node
                if src_node.parent == new_parent:
                    new_parent.children.remove(src_node)
                    new_parent.children.append(src_node)
                    self._reindex_children_paths(new_parent)
                else:
                    src_node.move_to(new_parent)
            else:
                new_parent = tgt_node.parent
                if new_parent is None:
                    return
                if src_node.parent == new_parent:
                    new_parent.children.remove(src_node)
                    tgt_idx = new_parent.children.index(tgt_node)
                    if position == "after":
                        tgt_idx += 1
                    new_parent.children.insert(tgt_idx, src_node)
                else:
                    src_node.move_to(new_parent)
                    new_parent.children.remove(src_node)
                    tgt_idx = new_parent.children.index(tgt_node)
                    if position == "after":
                        tgt_idx += 1
                    new_parent.children.insert(tgt_idx, src_node)
                    self._reindex_children_paths(new_parent)
            self.save_config()
            self.populate_tree(keep_expanded=True)
            self.select_tree_item_by_path(src_node.path)
            self.status_var.set(f"节点 '{src_node.name}' 已移动到 '{tgt_node.name}' 的 {position} 位置")
        except Exception as e:
            log_error(f"节点拖拽移动失败: {traceback.format_exc()}")
            messagebox.showerror("移动失败", str(e))

    def _reindex_children_paths(self, node):
        for child in node.children:
            child.path = os.path.join(node.path, child.name)
            child._update_children_paths()

    # ---------------------------- 同步功能 ----------------------------
    def sync_disk_folders(self):
        if not self.root_node:
            messagebox.showerror("错误", "根节点未初始化")
            return
        if not self.base_dir or not os.path.exists(self.base_dir):
            messagebox.showerror("错误", "库根目录不存在")
            return
        try:
            stats = {"added": 0, "removed": 0, "renamed": 0, "files": 0}
            self._recursive_sync_tree(self.root_node, self.base_dir, stats, is_startup=True, count_files=True)
            if stats["added"] or stats["removed"] or stats["renamed"]:
                self.save_config()
                expanded = self._collect_expanded_paths()
                self.populate_tree(keep_expanded=True, expanded_paths_override=expanded)
            self.status_var.set(f"同步完成：新增 {stats['added']} · 改名 {stats['renamed']} · 清理 {stats['removed']}")
            messagebox.showinfo("同步完成",
                f"新增节点：{stats['added']} 个\n"
                f"名称更新：{stats['renamed']} 个\n"
                f"清理无效节点：{stats['removed']} 个\n"
                f"文件总数：{stats['files']} 个")
        except Exception as e:
            log_error(f"同步失败: {traceback.format_exc()}")
            messagebox.showerror("同步失败", str(e))

    def sync_subfolders_recursive(self, node=None):
        if node is None:
            node = self.get_selected_node()
            if not node:
                return
        if not node.path or not os.path.exists(node.path):
            messagebox.showerror("错误", f"节点 '{node.name}' 的磁盘路径不存在")
            return
        if not messagebox.askyesno("确认", f"将递归同步节点 '{node.name}' 下的所有子文件夹到树中，确定继续？"):
            return
        try:
            stats = {"added": 0, "removed": 0, "renamed": 0, "files": 0}
            self._recursive_sync_tree(node, node.path, stats, is_startup=True, count_files=True)
            self.save_config()
            expanded = self._collect_expanded_paths()
            self.populate_tree(keep_expanded=True, expanded_paths_override=expanded)
            self.status_var.set(f"递归同步完成：新增 {stats['added']} · 改名 {stats['renamed']} · 清理 {stats['removed']}")
            messagebox.showinfo("同步完成",
                f"节点 '{node.name}' 递归同步完成：\n"
                f"新增：{stats['added']} 个\n"
                f"改名：{stats['renamed']} 个\n"
                f"清理：{stats['removed']} 个\n"
                f"文件：{stats['files']} 个")
        except Exception as e:
            log_error(f"递归同步失败: {traceback.format_exc()}")
            messagebox.showerror("同步失败", str(e))

    # ==================== 跨窗口拖拽 ====================
    def setup_drag_drop(self):
        try:
            self.tree.drop_target_register(DND_FILES)
        except Exception as e:
            log_error(f"drop_target_register 失败: {e}")
            self.status_var.set(f"⚠ 拖拽注册失败：{e}")
            return
        self.tree.dnd_bind('<<DropEnter>>', self.on_drop_enter)
        self.tree.dnd_bind('<<DropPosition>>', self.on_drop_position)
        self.tree.dnd_bind('<<DropLeave>>', self.on_drop_leave)
        self.tree.dnd_bind('<<Drop>>', self.on_drop)
        self.status_var.set("提示：拖拽文件/文件夹到树中任意节点，行将变淡黄色")

    def _get_pointer_in_tree(self):
        try:
            px = self.root.winfo_pointerx()
            py = self.root.winfo_pointery()
            tx = self.tree.winfo_rootx()
            ty = self.tree.winfo_rooty()
            return px - tx, py - ty
        except Exception:
            return None, None

    def _resolve_hover_target(self):
        if not self.tree or not self.root_node:
            return None, None
        rx, ry = self._get_pointer_in_tree()
        if rx is None:
            return None, None
        try:
            tw = self.tree.winfo_width()
            th = self.tree.winfo_height()
            if rx < 0 or ry < 0 or rx > tw or ry > th:
                return None, None
        except Exception:
            pass
        try:
            item = self.tree.identify_row(ry)
        except Exception:
            return None, None
        if not item or item in self._iid_to_file:
            return None, None
        path = self._get_item_path(item)
        if not path:
            return None, None
        node = self.root_node.find_by_path(path)
        if not node:
            return None, None
        return item, node

    def on_drop_enter(self, event):
        self._dnd_active = True
        try:
            if event.data:
                self._cached_drop_data = event.data
        except Exception:
            pass
        item, node = self._resolve_hover_target()
        if item and node:
            self._set_drop_hover(item, valid=True)
            self.status_var.set(f"🎯 即将拖放到：{node.name}")
        else:
            self._clear_drop_hover()
            self.status_var.set("🎯 拖拽已进入，请将鼠标移到目标节点行上")

    def on_drop_position(self, event):
        if not self._dnd_active:
            self._dnd_active = True
        try:
            if event.data:
                self._cached_drop_data = event.data
        except Exception:
            pass
        item, node = self._resolve_hover_target()
        if item and node:
            self._set_drop_hover(item, valid=True)
            self.status_var.set(f"🎯 即将拖放到：{node.name}")
        else:
            self._clear_drop_hover()
            sel = self.current_selected
            if sel:
                self.status_var.set(f"🎯 鼠标不在节点行上，将放入当前选中节点：{sel.name}")
            else:
                self.status_var.set("🎯 请将鼠标悬停到目标节点行上")

    def on_drop_leave(self, event):
        self._dnd_active = False
        self._cached_drop_data = ""
        self._clear_drop_hover()
        self.status_var.set("拖拽已离开树视图")

    def _parse_drop_data(self, raw_data):
        if not raw_data:
            return []
        data = str(raw_data)
        if not data.strip():
            return []

        candidate = data.strip()
        if candidate.startswith('{') and candidate.endswith('}'):
            candidate = candidate[1:-1]
        candidate = candidate.strip().strip('"').strip("'")
        if candidate and '\n' not in candidate and '{' not in candidate and '}' not in candidate:
            try:
                p = os.path.normpath(candidate)
                if os.path.exists(p):
                    return [p]
            except Exception:
                pass

        candidates = []
        try:
            from tkinterdnd2 import splitlist
            r = splitlist(data)
            if r:
                candidates = list(r)
        except Exception:
            candidates = []

        if not candidates:
            try:
                r = self.root.tk.splitlist(data)
                if r:
                    candidates = list(r)
            except Exception:
                candidates = []

        if not candidates:
            candidates = self._manual_parse_drop(data)

        files = []
        seen = set()
        for c in candidates:
            if not c:
                continue
            p = os.path.normpath(str(c).strip())
            if not p or p in seen:
                continue
            seen.add(p)
            if os.path.exists(p):
                files.append(p)

        if not files:
            c2 = data.strip()
            if c2.startswith('{') and c2.endswith('}'):
                c2 = c2[1:-1]
            c2 = c2.strip().strip('"').strip("'")
            try:
                p = os.path.normpath(c2)
                if os.path.exists(p):
                    return [p]
            except Exception:
                pass

        return files

    def _manual_parse_drop(self, data):
        files = []
        i = 0
        n = len(data)
        while i < n:
            while i < n and data[i] in ' \t\r\n':
                i += 1
            if i >= n:
                break
            if data[i] == '{':
                j = data.find('}', i + 1)
                if j == -1:
                    files.append(data[i+1:])
                    break
                files.append(data[i+1:j])
                i = j + 1
            else:
                j = i
                while j < n and data[j] not in ' \t\r\n':
                    j += 1
                files.append(data[i:j])
                i = j
        return files

    def _ask_copy_or_move(self, count, target_name):
        dlg = tk.Toplevel(self.root)
        dlg.title("拖拽操作")
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.resizable(False, False)
        ttk.Label(dlg, text=f"拖入 {count} 个项目", font=('Arial', 11, 'bold')).pack(padx=24, pady=(16, 4))
        ttk.Label(dlg, text=f"目标节点：{target_name}", foreground="#555").pack(padx=24, pady=(0, 12))
        ttk.Label(dlg, text="请选择操作方式：").pack(padx=24, pady=(0, 8))
        result = {"value": None}

        def pick(v):
            result["value"] = v
            dlg.destroy()

        btn_frame = ttk.Frame(dlg)
        btn_frame.pack(pady=(0, 8))
        ttk.Button(btn_frame, text="📋 复制（保留源文件）", width=22,
                   command=lambda: pick("copy")).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="✂️ 移动（删除源文件）", width=22,
                   command=lambda: pick("move")).pack(side=tk.LEFT, padx=4)
        ttk.Button(dlg, text="取消", command=lambda: pick(None)).pack(pady=(0, 12))
        try:
            dlg.update_idletasks()
            px = self.root.winfo_x() + (self.root.winfo_width() - dlg.winfo_width()) // 2
            py = self.root.winfo_y() + (self.root.winfo_height() - dlg.winfo_height()) // 2
            dlg.geometry(f"+{max(0, px)}+{max(0, py)}")
        except Exception:
            pass
        dlg.wait_window()
        return result["value"]

    def on_drop(self, event):
        self._clear_drop_hover()
        self._clear_drop_indicator()
        self._dnd_active = False

        if not DND_AVAILABLE:
            return

        data = ""
        try:
            if event.data:
                data = event.data
        except Exception:
            data = ""
        if not data:
            data = getattr(self, "_cached_drop_data", "") or ""
        if not data:
            try:
                data = event.data or ""
            except Exception:
                data = ""
        self._cached_drop_data = ""

        if not data:
            messagebox.showwarning(
                "拖拽失败",
                "未能读取到拖拽数据，请重试。\n\n"
                "若一直失败，可尝试：\n"
                "  • 一次拖入多个文件\n"
                "  • 使用「上传文件」按钮\n"
                "  • 以普通用户权限运行本程序")
            return

        item, node = self._resolve_hover_target()
        if not node:
            node = self.get_selected_node()
        if not node:
            messagebox.showwarning("未选中",
                "请将文件/文件夹拖到树中的某个节点上，\n或先选中一个目标节点再拖拽。")
            return
        if not node.path:
            messagebox.showerror("错误", "目标节点路径无效")
            return

        files = self._parse_drop_data(data)
        if not files:
            log_error(f"拖拽数据解析为空。原始数据={data!r}")
            messagebox.showwarning(
                "解析失败",
                f"未能从拖拽数据中解析到有效文件。\n\n"
                f"原始数据：{data[:200]}")
            return

        target_iid = self._path_to_iid.get(node.path)
        if target_iid:
            self._flash_node(target_iid, times=3, interval=180)

        action = self._ask_copy_or_move(len(files), node.name)
        if action is None:
            return
        is_move = (action == "move")

        dest_dir = node.path
        os.makedirs(dest_dir, exist_ok=True)
        dest_dir_abs = os.path.abspath(dest_dir)
        imported = []
        failed = []

        for src in files:
            base = os.path.basename(src)
            src_abs = os.path.abspath(src)
            if is_move:
                if src_abs == dest_dir_abs or dest_dir_abs.startswith(src_abs + os.sep):
                    failed.append(f"{base}：不能移动到自己或自己的子目录下")
                    continue
                if os.path.dirname(src_abs) == dest_dir_abs:
                    failed.append(f"{base}：已在目标目录中")
                    continue
            dest = os.path.join(dest_dir, base)
            if os.path.exists(dest):
                if os.path.isdir(src):
                    bn, ext = os.path.splitext(base)
                    counter = 1
                    while os.path.exists(os.path.join(dest_dir, f"{bn}_{counter}{ext}")):
                        counter += 1
                    dest = os.path.join(dest_dir, f"{bn}_{counter}{ext}")
                else:
                    try:
                        versions_dir = os.path.join(dest_dir, "versions")
                        os.makedirs(versions_dir, exist_ok=True)
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        name, ext = os.path.splitext(base)
                        old_ver = os.path.join(versions_dir, f"{name}_{timestamp}{ext}")
                        shutil.move(dest, old_ver)
                    except Exception:
                        pass
            try:
                if os.path.isdir(src):
                    if is_move:
                        shutil.move(src, dest)
                    else:
                        shutil.copytree(src, dest)
                else:
                    if is_move:
                        shutil.move(src, dest)
                    else:
                        shutil.copy2(src, dest)
                imported.append(base)
            except Exception as e:
                log_error(f"拖拽失败: {traceback.format_exc()}")
                failed.append(f"{base}：{e}")

        if imported:
            action_name = "移动" if is_move else "复制"
            self.status_var.set(f"{action_name} {len(imported)} 个项目 → 节点 '{node.name}'")
            expanded = self._collect_expanded_paths()
            self.populate_tree(keep_expanded=True, expanded_paths_override=expanded)
            try:
                iid = self._path_to_iid.get(node.path)
                if iid:
                    self.tree.item(iid, open=True)
                    self.on_tree_open(None)
                    self.tree.see(iid)
            except Exception:
                pass
            if failed:
                messagebox.showwarning("部分失败", "\n".join(failed[:10]))
        else:
            if failed:
                messagebox.showerror("失败", "\n".join(failed[:10]))

    # ---------------------------- 界面 ----------------------------
    def create_widgets(self):
        top_bar = ttk.Frame(self.root)
        top_bar.pack(side=tk.TOP, fill=tk.X, padx=5, pady=(4, 0))
        ttk.Label(top_bar, text="").pack(side=tk.LEFT, expand=True)
        ttk.Button(top_bar, text="📝 备注", width=12,
                   command=self.open_remark_dialog).pack(side=tk.RIGHT, padx=4)

        main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        left_frame = ttk.Frame(main_paned)
        main_paned.add(left_frame, weight=1)

        toolbar_notebook = ttk.Notebook(left_frame)
        toolbar_notebook.pack(fill=tk.X, pady=2)
        groups = {
            "基本编辑": ["新增节点", "删除节点", "编辑节点", "字段设置", "更新版本"],
            "复制粘贴": ["复制节点", "粘贴节点"],
            "文件操作": ["上传文件", "预览文件", "打开文件夹", "查看版本"],
            "高级工具": ["批量加节点", "导入结构", "从文件夹导入", "递归同步子文件夹",
                       "导出结构", "导出所选", "文件校验"]
        }
        for group_name, btn_texts in groups.items():
            frame = ttk.Frame(toolbar_notebook)
            toolbar_notebook.add(frame, text=group_name)
            for text in btn_texts:
                cmd = self.get_command(text)
                if cmd:
                    btn = ttk.Button(frame, text=text, command=cmd)
                    btn.pack(side=tk.LEFT, padx=2, pady=2)

        filter_frame = ttk.Frame(left_frame)
        filter_frame.pack(fill=tk.X, pady=2)
        ttk.Label(filter_frame, text="筛选:").pack(side=tk.LEFT, padx=2)
        self.filter_combo = ttk.Combobox(filter_frame, textvariable=self.filter_keyword, width=30, values=[])
        self.filter_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        self.filter_combo.bind("<Return>", lambda e: self.apply_filter())
        self.filter_combo.bind("<<ComboboxSelected>>", lambda e: self.apply_filter())
        ttk.Button(filter_frame, text="应用筛选", command=self.apply_filter).pack(side=tk.LEFT, padx=2)
        ttk.Button(filter_frame, text="重置筛选", command=self.reset_filter).pack(side=tk.LEFT, padx=2)

        tree_frame = ttk.Frame(left_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        col_ids = [c["id"] for c in self.columns_config]
        self.tree = ttk.Treeview(tree_frame, columns=col_ids, selectmode='extended', show="tree headings")
        self._rebuild_tree_columns()

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)

        self._setup_drag_interactions()

        self.status_var = tk.StringVar()
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        self._create_expand_bar()
        self.status_var.set("提示：拖拽文件到树中节点，行会变淡黄色以确认目标")

    def get_command(self, btn_text):
        mapping = {
            "新增节点": self.add_node, "删除节点": self.delete_node,
            "编辑节点": self.edit_node, "字段设置": self.edit_node_field_settings,
            "更新版本": self.update_version, "复制节点": self.copy_node,
            "粘贴节点": self.paste_node, "批量加节点": self.batch_add_nodes,
            "导入结构": self.import_structure, "从文件夹导入": self.import_from_folder,
            "递归同步子文件夹": self.sync_subfolders_recursive,
            "导出结构": self.export_structure, "导出所选": self.export_selected_nodes,
            "文件校验": self.validate_files, "上传文件": self.upload_files,
            "预览文件": self.preview_file, "打开文件夹": self.open_folder,
            "查看版本": self.view_versions,
        }
        return mapping.get(btn_text)

    # ---------------------------- 右键菜单 ----------------------------
    def create_context_menu(self):
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="📝 备注…", command=self.open_remark_dialog)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="新增节点", command=self.add_node)
        self.context_menu.add_command(label="删除节点", command=self.delete_node)
        self.context_menu.add_command(label="编辑节点", command=self.edit_node)
        self.context_menu.add_command(label="字段设置…", command=self.edit_node_field_settings)
        self.context_menu.add_command(label="更新版本", command=self.update_version)
        self.context_menu.add_command(label="复制节点", command=self.copy_node)
        self.context_menu.add_command(label="粘贴节点", command=self.paste_node)
        self.context_menu.add_command(label="批量加节点", command=self.batch_add_nodes)
        self.context_menu.add_command(label="上传文件", command=self.upload_files)
        self.context_menu.add_command(label="预览文件", command=self.preview_file)
        self.context_menu.add_command(label="查看版本", command=self.view_versions)
        self.context_menu.add_command(label="打开文件夹", command=self.open_folder)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="导入结构", command=self.import_structure)
        self.context_menu.add_command(label="从文件夹导入", command=self.import_from_folder)
        self.context_menu.add_command(label="递归同步子文件夹", command=self.sync_subfolders_recursive)
        self.context_menu.add_command(label="导出结构", command=self.export_structure)
        self.context_menu.add_command(label="导出所选节点…", command=self.export_selected_nodes)
        self.context_menu.add_command(label="文件校验", command=self.validate_files)
        self.context_menu.add_command(label="查看历史版本", command=self.view_history_versions)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="管理列…", command=self.manage_columns)
        self.tree.bind("<Button-3>", self.show_context_menu)

    def show_context_menu(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region == "heading":
            col_spec = self.tree.identify_column(event.x)
            cid = self._column_id_from_identify(col_spec)
            if cid:
                self._show_column_context_menu(event, cid)
            return
        item = self.tree.identify_row(event.y)
        if item:
            if item not in self.tree.selection():
                self.tree.selection_set(item)
        self.context_menu.post(event.x_root, event.y_root)

    def on_delete_key(self, event):
        self.delete_node()

    # ---------------------------- 筛选相关 ----------------------------
    def apply_filter(self):
        keyword = self.filter_keyword.get().strip()
        if not keyword:
            self.display_nodes = None
            expanded = self._collect_expanded_paths()
            self.populate_tree(keep_expanded=True, expanded_paths_override=expanded)
            self.status_var.set("筛选已清除，显示全部节点")
            return
        raw_parts = re.split(r'[\s,;，；]+', keyword)
        keywords = [p.lower() for p in raw_parts if p]
        if not keywords:
            self.display_nodes = None
            self.populate_tree(keep_expanded=True)
            return
        matched_nodes = []
        def collect(node):
            name_lower = node.name.lower()
            if all(k in name_lower for k in keywords):
                matched_nodes.append(node)
            for child in node.children:
                collect(child)
        collect(self.root_node)
        self.display_nodes = set()
        for node in matched_nodes:
            cur = node
            while cur:
                if cur.path:
                    self.display_nodes.add(cur.path)
                cur = cur.parent
        expanded = set(self.display_nodes)
        if keyword not in self.filter_history:
            self.filter_history.insert(0, keyword)
            if len(self.filter_history) > 20:
                self.filter_history = self.filter_history[:20]
        else:
            self.filter_history.remove(keyword)
            self.filter_history.insert(0, keyword)
        try:
            self.filter_combo['values'] = self.filter_history
        except Exception:
            pass
        self.populate_tree(keep_expanded=True, expanded_paths_override=expanded)
        if matched_nodes:
            self.status_var.set(f"筛选: '{keyword}'  共找到 {len(matched_nodes)} 个匹配节点")
        else:
            self.status_var.set(f"筛选: '{keyword}'  未找到任何匹配节点")

    def reset_filter(self):
        self.filter_keyword.set("")
        self.display_nodes = None
        expanded = self._collect_expanded_paths()
        self.populate_tree(keep_expanded=True, expanded_paths_override=expanded)
        self.status_var.set("筛选已重置，显示全部节点")

    # ---------------------------- 树填充 ----------------------------
    def populate_tree(self, node=None, parent_id="", keep_expanded=True,
                      expanded_paths_override=None):
        self._drop_indicator_item = None
        self._drop_indicator_old_tags = None
        self._drop_hover_item = None
        self._drop_hover_old_tags = None
        if expanded_paths_override is not None:
            expanded_paths = set(expanded_paths_override)
        else:
            expanded_paths = set()
            if keep_expanded:
                expanded_paths = self._collect_expanded_paths()
        if node is None:
            node = self.root_node
        if not parent_id:
            for item in self.tree.get_children():
                self.tree.delete(item)
            self._iid_to_path = {}
            self._path_to_iid = {}
            self._iid_to_file = {}
            self._iid_counter = 0

        def insert_node(n, p_id):
            if self.display_nodes is not None and n.path not in self.display_nodes:
                return
            values = self._get_node_values(n)
            self._iid_counter += 1
            iid = f"n{self._iid_counter}"
            if n.path:
                self._iid_to_path[iid] = n.path
                self._path_to_iid[n.path] = iid
            item_id = self.tree.insert(p_id, "end", iid=iid, text=n.name, values=values)
            if n.path in expanded_paths:
                self.tree.item(item_id, open=True)
                self._insert_files_under(item_id, n)
            for child in n.children:
                insert_node(child, item_id)

        insert_node(node, parent_id)
        self._compute_and_apply_wrapped_rowheight()

    # ==================== 树增量更新 ====================
    def _find_tree_item_by_path(self, path, parent=""):
        item = self._path_to_iid.get(path)
        if item and self.tree.exists(item):
            return item
        return None

    def _add_tree_node(self, node, parent_item=None):
        if self.display_nodes is not None:
            self.populate_tree(keep_expanded=True)
            return
        if parent_item is None:
            parent_node = node.parent
            if parent_node is None:
                parent_item = ""
            else:
                parent_item = self._find_tree_item_by_path(parent_node.path)
                if parent_item is None:
                    self.populate_tree(keep_expanded=True)
                    return
        values = self._get_node_values(node)
        self._iid_counter += 1
        iid = f"n{self._iid_counter}"
        if node.path:
            self._iid_to_path[iid] = node.path
            self._path_to_iid[node.path] = iid
        item_id = self.tree.insert(parent_item, "end", iid=iid, text=node.name, values=values)
        for child in node.children:
            self._add_tree_node(child, item_id)
        self._compute_and_apply_wrapped_rowheight()

    def _delete_tree_node(self, node):
        if self.display_nodes is not None:
            self.populate_tree(keep_expanded=True)
            return
        item = self._path_to_iid.get(node.path)
        if item and self.tree.exists(item):
            self._iid_to_path.pop(item, None)
            self._path_to_iid.pop(node.path, None)
            self.tree.delete(item)

    def _update_tree_node(self, node, item_id=None):
        if self.display_nodes is not None:
            self.populate_tree(keep_expanded=True)
            return
        if item_id is None:
            item_id = self._find_tree_item_by_path(node.path)
        if item_id:
            values = self._get_node_values(node)
            self.tree.item(item_id, text=node.name, values=values)
            if self.auto_wrap:
                self._compute_and_apply_wrapped_rowheight()

    # ==================== 排序 ====================
    def on_column_click(self, col):
        if time.time() - self._last_col_drag_time < 0.5:
            return
        if self.sort_column == col:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = col
            self.sort_reverse = False
        self.sort_tree()

    def _get_sort_value(self, node, col):
        if col == "#0" or col == "名称":
            return node.name
        elif col == "path":
            return node.path or ""
        elif col == "version":
            try:
                return float(node.version)
            except Exception:
                return node.version
        elif col == "price":
            price_str = (node.price or "").strip()
            if price_str:
                nums = re.findall(r'[\d.]+', price_str)
                if nums:
                    try:
                        return float(nums[0])
                    except Exception:
                        pass
            return price_str
        elif col == "update_time":
            return node.update_time or ""
        else:
            val = node.extra_fields.get(col, "")
            if isinstance(val, str):
                s = val.strip()
                if s and re.fullmatch(r'-?\d+(\.\d+)?', s):
                    try:
                        return float(s)
                    except Exception:
                        pass
            return val

    def _compare_nodes(self, a, b):
        col = self.sort_column
        if col is None:
            return 0
        val_a = self._get_sort_value(a, col)
        val_b = self._get_sort_value(b, col)
        if isinstance(val_a, (int, float)) and isinstance(val_b, (int, float)):
            return (val_a > val_b) - (val_a < val_b)
        ka = natural_sort_key(val_a)
        kb = natural_sort_key(val_b)
        return (ka > kb) - (ka < kb)

    def sort_tree(self):
        if self.sort_column is None or self.root_node is None:
            return
        expanded_paths = self._collect_expanded_paths()
        def sort_node(node):
            if node.children:
                node.children.sort(key=functools.cmp_to_key(self._compare_nodes), reverse=self.sort_reverse)
                for child in node.children:
                    sort_node(child)
        sort_node(self.root_node)
        self.save_config()
        self.populate_tree(keep_expanded=True, expanded_paths_override=expanded_paths)
        self.status_var.set(
            f"已按列 '{self.sort_column}' 排序"
            f"{'（降序）' if self.sort_reverse else '（升序）'}"
            f"（自然排序 · 展开状态已保留）"
        )

    # ---------------------------- 数据加载与保存 ----------------------------
    def load_or_init_data(self):
        """加载已有配置；如果不存在，让用户选择库根目录进行初始化（不再创建默认模板）。"""
        config_path = CONFIG_FILE
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.base_dir = data.get("base_dir", os.getcwd())
                root_dict = data.get("tree", {})
                self.root_node = Node.from_dict(root_dict)
                self.root_node.set_path(self.base_dir)
                cols = data.get("columns")
                if cols:
                    self.columns_config = cols
                rh = data.get("row_height")
                if rh:
                    try:
                        self.row_height = int(rh)
                    except Exception:
                        pass
                self.auto_wrap = bool(data.get("auto_wrap", False))
                mwl = data.get("max_wrap_lines", 2)
                try:
                    self.max_wrap_lines = max(1, min(5, int(mwl)))
                except Exception:
                    self.max_wrap_lines = 2
                self.show_files = bool(data.get("show_files", True))
                try:
                    self._show_files_var.set(self.show_files)
                except Exception:
                    pass
                try:
                    self._auto_wrap_var.set(self.auto_wrap)
                except Exception:
                    pass
                self.ui_state = data.get("ui_state", None)
                geom = data.get("window_geometry")
                if geom:
                    try:
                        self.root.geometry(geom)
                    except Exception:
                        pass
                self.status_var.set(f"加载配置成功，根目录: {self.base_dir}")
                return
            except Exception as e:
                log_error(f"加载配置失败: {traceback.format_exc()}")
                messagebox.showerror("加载错误", f"加载配置文件失败：{e}\n将重新初始化。")

        # ---------- 首次启动：让用户选择库根目录（不再创建默认模板） ----------
        self._first_time_init()

    def _first_time_init(self):
        """首次启动：弹窗让用户选择库根目录。"""
        try:
            self.status_var.set("首次启动：请选择库根目录…")
            self.root.update_idletasks()
        except Exception:
            pass

        # 弹窗让用户选择
        selected = filedialog.askdirectory(
            title="首次启动 — 请选择库根目录（该文件夹下所有子文件夹会被扫描为节点）",
            mustexist=True,
        )
        if not selected:
            # 用户取消 → 使用当前工作目录下的 MyLibrary 作为空库
            self.base_dir = os.path.join(os.getcwd(), LIBRARY_FALLBACK_NAME)
            try:
                os.makedirs(self.base_dir, exist_ok=True)
            except Exception as e:
                log_error(f"创建默认库目录失败: {traceback.format_exc()}")
                messagebox.showerror("错误", f"无法创建库目录 {self.base_dir}：{e}")
                sys.exit(1)
        else:
            self.base_dir = os.path.normpath(selected)

        # 创建空根节点（名称为所选文件夹名，无任何默认子结构）
        root_name = os.path.basename(self.base_dir.rstrip(os.sep)) or "Library"
        self.root_node = Node(root_name)
        self.root_node.set_path(self.base_dir)

        # 扫描磁盘上已有的子文件夹（作为初始树结构）
        try:
            stats = {"added": 0, "removed": 0, "renamed": 0, "files": 0}
            self._recursive_sync_tree(
                self.root_node, self.base_dir, stats,
                is_startup=True, count_files=False,
            )
        except Exception:
            log_error(f"首次初始化扫描失败: {traceback.format_exc()}")

        self.ui_state = None
        self.save_config()
        self.status_var.set(f"初始化完成，根目录: {self.base_dir}")

    def save_config(self):
        try:
            self._sync_current_column_widths()
            try:
                win_geom = self.root.geometry()
            except Exception:
                win_geom = DEFAULT_GEOMETRY
            data = {
                "base_dir": self.base_dir,
                "tree": self.root_node.to_dict() if self.root_node else {},
                "columns": self.columns_config,
                "row_height": self.row_height,
                "auto_wrap": self.auto_wrap,
                "max_wrap_lines": self.max_wrap_lines,
                "show_files": self.show_files,
                "window_geometry": win_geom,
            }
            ui = self._capture_ui_state()
            if ui is not None:
                data["ui_state"] = ui
            else:
                try:
                    if os.path.exists(CONFIG_FILE):
                        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                            old = json.load(f)
                        if isinstance(old, dict) and "ui_state" in old:
                            data["ui_state"] = old["ui_state"]
                except Exception:
                    pass
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log_error(f"保存配置失败: {traceback.format_exc()}")
            messagebox.showerror("保存失败", f"无法保存配置文件：{e}")

    # ---------------------------- 节点选择 ----------------------------
    def on_tree_select(self, event):
        sel = self.tree.selection()
        if sel:
            item = sel[0]
            if item in self._iid_to_file:
                self.current_selected = None
                fp = self._iid_to_file[item]
                self.status_var.set(f"📄 {fp}（双击打开）")
                return
            path = self._get_item_path(item)
            self.current_selected = self.root_node.find_by_path(path) if path else None
        else:
            self.current_selected = None

    def on_double_click(self, event):
        item = self.tree.identify_row(event.y)
        if item and item in self._iid_to_file:
            self._open_file_with_system(self._iid_to_file[item])
            return
        self.open_folder()

    def refresh_tree(self):
        self.populate_tree()
        self.status_var.set("树已刷新")

    def get_selected_node(self):
        sel = self.tree.selection()
        if sel and sel[0] in self._iid_to_file:
            messagebox.showwarning("提示", "当前选中的是文件，请选中文件夹节点")
            return None
        if not self.current_selected:
            messagebox.showwarning("未选中", "请先选中一个节点")
            return None
        return self.current_selected

    # ---------------------------- 删除 ----------------------------
    def delete_node(self):
        selected_items = self.tree.selection()
        if not selected_items:
            messagebox.showwarning("未选中", "请先选择要删除的节点（可多选）")
            return
        nodes_to_delete = []
        items_to_delete = []
        seen_paths = set()
        for item in selected_items:
            if item in self._iid_to_file:
                continue
            path = self._get_item_path(item)
            if not path or path in seen_paths:
                continue
            seen_paths.add(path)
            node = self.root_node.find_by_path(path)
            if node is None:
                continue
            if node == self.root_node:
                messagebox.showerror("错误", f"根节点 '{node.name}' 不可删除")
                return
            nodes_to_delete.append(node)
            items_to_delete.append(item)
        if not nodes_to_delete:
            return
        names = [f"  • {node.name}" for node in nodes_to_delete]
        msg = f"确定要删除以下 {len(nodes_to_delete)} 个节点及其所有子节点吗？\n\n" + "\n".join(names) + "\n\n磁盘上的对应文件夹也将被永久删除！"
        if not messagebox.askyesno("确认删除", msg):
            return
        failed = []
        for node in nodes_to_delete:
            parent = node.parent
            if parent:
                try:
                    parent.remove_child(node)
                except Exception:
                    log_error(f"删除节点 {node.name} 失败: {traceback.format_exc()}")
                    failed.append(node.name)
        self.save_config()
        if self.display_nodes is None:
            for item in reversed(items_to_delete):
                try:
                    if self.tree.exists(item):
                        p = self._iid_to_path.pop(item, None)
                        if p:
                            self._path_to_iid.pop(p, None)
                        self.tree.delete(item)
                except tk.TclError:
                    pass
        else:
            self.populate_tree(keep_expanded=True)
        self.tree.selection_remove(*selected_items)
        self.current_selected = None
        if failed:
            self.status_var.set(f"删除完成，成功 {len(nodes_to_delete)-len(failed)} 个，失败 {len(failed)} 个")
        else:
            self.status_var.set(f"已删除 {len(nodes_to_delete)} 个节点")
            messagebox.showinfo("删除成功", f"已成功删除 {len(nodes_to_delete)} 个节点")

    # ---------------------------- 编辑节点 ----------------------------
    def edit_node(self):
        node = self.get_selected_node()
        if not node:
            return
        item_id = None
        if self.display_nodes is None:
            item_id = self._find_tree_item_by_path(node.path)

        dialog = tk.Toplevel(self.root)
        dialog.title(f"编辑节点 - {node.name}")
        dialog.geometry("580x680")
        dialog.transient(self.root)
        top_bar = ttk.Frame(dialog)
        top_bar.pack(fill=tk.X, padx=8, pady=6)
        info_var = tk.StringVar()
        ttk.Label(top_bar, textvariable=info_var, foreground="#666").pack(side=tk.LEFT)
        ttk.Button(top_bar, text="字段设置…",
                   command=lambda: self._open_field_settings(dialog, node, render_fields, info_var)).pack(side=tk.RIGHT)
        container = ttk.Frame(dialog)
        container.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        canvas = tk.Canvas(container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        content_frame = ttk.Frame(canvas)
        content_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=content_frame, anchor="nw", width=530)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        content_frame.columnconfigure(1, weight=1)
        field_widgets = {}

        def get_visible_fields():
            if node.editable_fields is None:
                fields = ["name", "version", "price"]
                for c in self.columns_config:
                    if not c.get("builtin"):
                        fields.append(c["id"])
                fields.append("remark")
                return fields
            else:
                result = ["name"]
                for f in node.editable_fields:
                    if f != "name":
                        result.append(f)
                return result

        def render_fields():
            for w in content_frame.winfo_children():
                w.destroy()
            field_widgets.clear()
            info_var.set("字段模式：全部字段" if node.editable_fields is None
                         else f"字段模式：自定义（{len(node.editable_fields)} 个字段）")
            visible = get_visible_fields()
            row = 0
            col_title_map = {c["id"]: c["title"] for c in self.columns_config}
            for field_id in visible:
                if field_id == "name":
                    ttk.Label(content_frame, text="名称:").grid(row=row, column=0, sticky=tk.W, padx=5, pady=5)
                    var = tk.StringVar(value=node.name)
                    ttk.Entry(content_frame, textvariable=var, width=38).grid(row=row, column=1, sticky="ew", padx=5, pady=5)
                    field_widgets["name"] = ("entry", var); row += 1
                elif field_id == "version":
                    ttk.Label(content_frame, text="版本:").grid(row=row, column=0, sticky=tk.W, padx=5, pady=5)
                    var = tk.StringVar(value=node.version)
                    ttk.Entry(content_frame, textvariable=var, width=38).grid(row=row, column=1, sticky="ew", padx=5, pady=5)
                    field_widgets["version"] = ("entry", var); row += 1
                elif field_id == "price":
                    ttk.Label(content_frame, text="价格:").grid(row=row, column=0, sticky=tk.W, padx=5, pady=5)
                    var = tk.StringVar(value=node.price)
                    ttk.Entry(content_frame, textvariable=var, width=38).grid(row=row, column=1, sticky="ew", padx=5, pady=5)
                    field_widgets["price"] = ("entry", var); row += 1
                elif field_id == "remark":
                    ttk.Label(content_frame, text="备注:").grid(row=row, column=0, sticky=tk.NW, padx=5, pady=5)
                    t = tk.Text(content_frame, height=5, width=38, wrap=tk.WORD)
                    t.insert("1.0", node.remark)
                    t.grid(row=row, column=1, sticky="ew", padx=5, pady=5)
                    field_widgets["remark"] = ("text", t); row += 1
                else:
                    title = col_title_map.get(field_id, field_id)
                    ttk.Label(content_frame, text=f"{title}:").grid(row=row, column=0, sticky=tk.W, padx=5, pady=5)
                    var = tk.StringVar(value=node.extra_fields.get(field_id, ""))
                    ttk.Entry(content_frame, textvariable=var, width=38).grid(row=row, column=1, sticky="ew", padx=5, pady=5)
                    field_widgets[field_id] = ("entry", var); row += 1
            ttk.Separator(content_frame, orient="horizontal").grid(row=row, column=0, columnspan=2, sticky="ew", pady=8)
            row += 1
            ttk.Label(content_frame, text="创建时间:", foreground="gray").grid(row=row, column=0, sticky=tk.W, padx=5, pady=2)
            ttk.Label(content_frame, text=node.create_time, foreground="gray").grid(row=row, column=1, sticky=tk.W, padx=5, pady=2)
            row += 1
            ttk.Label(content_frame, text="更新时间:", foreground="gray").grid(row=row, column=0, sticky=tk.W, padx=5, pady=2)
            ttk.Label(content_frame, text=node.update_time, foreground="gray").grid(row=row, column=1, sticky=tk.W, padx=5, pady=2)
            row += 1
            ttk.Label(content_frame, text="树路径:", foreground="gray").grid(row=row, column=0, sticky=tk.NW, padx=5, pady=2)
            ttk.Label(content_frame, text=node.path or "", foreground="gray", wraplength=380, justify=tk.LEFT).grid(row=row, column=1, sticky=tk.W, padx=5, pady=2)

        def save_changes():
            new_name = node.name
            if "name" in field_widgets:
                new_name = field_widgets["name"][1].get().strip()
            if not new_name:
                messagebox.showwarning("警告", "名称不能为空")
                return
            if new_name != node.name:
                parent = node.parent
                if parent and parent.find_child(new_name):
                    messagebox.showerror("错误", f"同级已存在节点 '{new_name}'")
                    return
                try:
                    node.rename(new_name)
                except Exception as e:
                    messagebox.showerror("重命名失败", str(e))
                    return
            if "version" in field_widgets:
                node.version = field_widgets["version"][1].get().strip() or "1.0"
            if "price" in field_widgets:
                node.price = field_widgets["price"][1].get().strip()
            if "remark" in field_widgets:
                node.remark = field_widgets["remark"][1].get("1.0", tk.END).strip()
            for field_id, (kind, var) in field_widgets.items():
                if field_id in ("name", "version", "price", "remark"):
                    continue
                node.extra_fields[field_id] = var.get().strip()
            node.update_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if self.display_nodes is None and item_id is not None:
                self.tree.item(item_id, text=node.name, values=self._get_node_values(node))
                if self.auto_wrap:
                    self._compute_and_apply_wrapped_rowheight()
            else:
                self.populate_tree(keep_expanded=True)
            self.save_config()
            self.status_var.set(f"节点 '{node.name}' 已更新")
            dialog.destroy()

        render_fields()
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill=tk.X, pady=10)
        ttk.Button(btn_frame, text="保存", command=save_changes).pack(side=tk.RIGHT, padx=8)
        ttk.Button(btn_frame, text="取消", command=dialog.destroy).pack(side=tk.RIGHT, padx=8)

    # ---------------------------- 字段设置 ----------------------------
    def _open_field_settings(self, parent_dialog, node, on_apply_callback, info_var=None):
        dlg = tk.Toplevel(parent_dialog)
        dlg.title(f"字段设置 - {node.name}")
        dlg.geometry("440x580")
        dlg.transient(parent_dialog)
        dlg.grab_set()
        ttk.Label(dlg, text="勾选本节点编辑对话框中要显示的字段（名称始终显示）：", wraplength=400).pack(anchor="w", padx=10, pady=8)
        mode_var = tk.StringVar(value="all" if node.editable_fields is None else "custom")
        mode_frame = ttk.LabelFrame(dlg, text="模式")
        mode_frame.pack(fill=tk.X, padx=10, pady=4)
        ttk.Radiobutton(mode_frame, text="显示全部字段", variable=mode_var, value="all").pack(anchor="w", padx=6, pady=2)
        ttk.Radiobutton(mode_frame, text="自定义字段（勾选下方字段）", variable=mode_var, value="custom").pack(anchor="w", padx=6, pady=2)
        list_frame = ttk.LabelFrame(dlg, text="字段列表")
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)
        builtin_fields = [("name", "名称（必选）"), ("version", "版本"), ("price", "价格"), ("remark", "备注")]
        custom_fields = [(c["id"], c["title"]) for c in self.columns_config if not c.get("builtin")]
        all_fields = builtin_fields + custom_fields
        field_vars = {}
        for field_id, title in all_fields:
            var = tk.BooleanVar()
            if field_id == "name":
                var.set(True)
                cb = ttk.Checkbutton(list_frame, text=title, variable=var, state="disabled")
            else:
                if node.editable_fields is None:
                    var.set(True)
                else:
                    var.set(field_id in node.editable_fields)
                cb = ttk.Checkbutton(list_frame, text=title, variable=var)
            cb.pack(anchor="w", padx=8, pady=2)
            field_vars[field_id] = var
        scope_var = tk.StringVar(value="self")
        scope_frame = ttk.LabelFrame(dlg, text="应用范围")
        scope_frame.pack(fill=tk.X, padx=10, pady=4)
        ttk.Radiobutton(scope_frame, text="仅当前节点", variable=scope_var, value="self").pack(anchor="w", padx=6, pady=2)
        ttk.Radiobutton(scope_frame, text="当前节点及其所有子节点", variable=scope_var, value="subtree").pack(anchor="w", padx=6, pady=2)

        def apply():
            if mode_var.get() == "all":
                new_editable = None
            else:
                selected = [fid for fid, v in field_vars.items() if v.get() and fid != "name"]
                new_editable = selected
            def apply_to(n):
                n.editable_fields = list(new_editable) if new_editable is not None else None
                for ch in n.children:
                    apply_to(ch)
            if scope_var.get() == "subtree":
                apply_to(node)
            else:
                node.editable_fields = list(new_editable) if new_editable is not None else None
            self.save_config()
            dlg.destroy()
            on_apply_callback()
            if info_var is not None:
                info_var.set("字段模式：全部字段" if node.editable_fields is None
                             else f"字段模式：自定义（{len(node.editable_fields)} 个字段）")
            self.status_var.set(f"节点 '{node.name}' 的字段设置已更新")

        btn_frame = ttk.Frame(dlg)
        btn_frame.pack(fill=tk.X, pady=8)
        ttk.Button(btn_frame, text="确定", command=apply).pack(side=tk.RIGHT, padx=8)
        ttk.Button(btn_frame, text="取消", command=dlg.destroy).pack(side=tk.RIGHT, padx=8)

    def edit_node_field_settings(self):
        node = self.get_selected_node()
        if not node:
            return
        dlg = tk.Toplevel(self.root)
        dlg.title(f"字段设置 - {node.name}")
        dlg.withdraw()
        self._open_field_settings(dlg, node, lambda: None, info_var=None)
        dlg.destroy()
        self.status_var.set(f"节点 '{node.name}' 的字段设置已更新")

    # ---------------------------- 更新版本 ----------------------------
    def update_version(self):
        node = self.get_selected_node()
        if not node:
            return
        remark = simpledialog.askstring("更新版本", f"当前版本: {node.version}\n请输入本次更新的备注（可选）：")
        if remark is None:
            return
        try:
            base = float(node.version) if node.version.replace('.', '').isdigit() else 1.0
            new_version = f"{base + 0.1:.1f}"
        except Exception:
            new_version = "1.1"
        node.update_version(new_version, remark)
        self.save_config()
        self._update_tree_node(node)
        self.status_var.set(f"版本已更新: {node.version}")
        messagebox.showinfo("版本更新", f"新版本: {node.version}\n备注: {remark}")

    # ---------------------------- 查看历史版本 ----------------------------
    def view_history_versions(self):
        node = self.get_selected_node()
        if not node:
            return
        history = node.get_history_versions()
        if not history:
            messagebox.showinfo("历史版本", "该节点暂无历史版本记录")
            return
        win = tk.Toplevel(self.root)
        win.title(f"历史版本 - {node.name}")
        win.geometry("500x400")
        listbox = tk.Listbox(win, selectmode=tk.SINGLE)
        listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        for entry in reversed(history):
            text = f"版本 {entry['version']} 于 {entry['update_time']} 备注: {entry.get('remark', '')}"
            listbox.insert(tk.END, text)
        ttk.Button(win, text="关闭", command=win.destroy).pack(pady=5)

    # ---------------------------- 从文件夹导入 ----------------------------
    def import_from_folder(self):
        parent = self.get_selected_node()
        if not parent:
            return
        folder_path = filedialog.askdirectory(title="选择要导入的文件夹（将扫描其子文件夹结构）")
        if not folder_path:
            return
        root_name = simpledialog.askstring("导入设置", "请输入导入节点的根名称（默认为文件夹名）：",
                                           initialvalue=os.path.basename(folder_path))
        if not root_name:
            root_name = os.path.basename(folder_path)
        if parent.find_child(root_name):
            base = root_name
            counter = 1
            while parent.find_child(f"{base}_{counter}"):
                counter += 1
            root_name = f"{base}_{counter}"

        def build_node_from_dir(dir_path, parent_node):
            node = Node(os.path.basename(dir_path))
            parent_node.add_child(node)
            try:
                for item in os.listdir(dir_path):
                    full = os.path.join(dir_path, item)
                    if os.path.isdir(full):
                        build_node_from_dir(full, node)
            except Exception:
                log_error(f"扫描文件夹失败: {traceback.format_exc()}")
                return node
            return node

        try:
            root_node = Node(root_name)
            parent.add_child(root_node)
            root_node.set_path(parent.path)
            for item in os.listdir(folder_path):
                full = os.path.join(folder_path, item)
                if os.path.isdir(full):
                    build_node_from_dir(full, root_node)
            self.save_config()
            self.populate_tree(keep_expanded=True)
            self.status_var.set(f"已从文件夹导入结构，根节点: {root_node.name}")
            messagebox.showinfo("导入成功", f"已成功从 {folder_path} 导入子文件夹结构，根节点为 '{root_node.name}'")
        except Exception as e:
            log_error(f"从文件夹导入失败: {traceback.format_exc()}")
            messagebox.showerror("导入失败", str(e))

    # ==================== 导出所选节点 ====================
    def _get_selected_top_nodes(self):
        if not self.root_node:
            return []
        selected_items = self.tree.selection()
        if not selected_items:
            return []
        nodes = []
        seen_paths = set()
        for item in selected_items:
            if item in self._iid_to_file:
                continue
            path = self._get_item_path(item)
            if not path or path in seen_paths:
                continue
            seen_paths.add(path)
            node = self.root_node.find_by_path(path)
            if node:
                nodes.append(node)
        top_nodes = []
        for node in nodes:
            has_ancestor = False
            for other in nodes:
                if other != node and other.is_ancestor_of(node):
                    has_ancestor = True
                    break
            if not has_ancestor:
                top_nodes.append(node)
        return top_nodes

    def export_selected_nodes(self):
        top_nodes = self._get_selected_top_nodes()
        if not top_nodes:
            messagebox.showwarning("未选中", "请先在树中选中要导出的节点（可按住 Ctrl / Shift 多选）")
            return
        dlg = tk.Toplevel(self.root)
        dlg.title("导出所选节点")
        dlg.geometry("660x560")
        dlg.transient(self.root)
        dlg.grab_set()
        ttk.Label(dlg, text=f"即将导出以下 {len(top_nodes)} 个顶层节点（包含所有子节点）：",
                  font=('Arial', 10, 'bold')).pack(anchor="w", padx=10, pady=(10, 4))
        list_frame = ttk.Frame(dlg)
        list_frame.pack(fill=tk.X, padx=10, pady=4)
        listbox = tk.Listbox(list_frame, height=6, activestyle="none")
        sb = ttk.Scrollbar(list_frame, orient="vertical", command=listbox.yview)
        listbox.configure(yscrollcommand=sb.set)
        listbox.pack(side=tk.LEFT, fill=tk.X, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        for n in top_nodes:
            listbox.insert(tk.END, f"  {n.name}    [{n.path}]")
        mode_frame = ttk.LabelFrame(dlg, text="导出方式")
        mode_frame.pack(fill=tk.X, padx=10, pady=6)
        mode_var = tk.StringVar(value="files")
        ttk.Radiobutton(mode_frame, text="① 复制完整文件到文件夹（保留内部目录结构）", variable=mode_var, value="files").pack(anchor="w", padx=6, pady=3)
        ttk.Radiobutton(mode_frame, text="② 打包为 ZIP 压缩包（保留内部目录结构）", variable=mode_var, value="zip").pack(anchor="w", padx=6, pady=3)
        ttk.Radiobutton(mode_frame, text="③ 生成目录结构清单（TXT，便于查看/打印）", variable=mode_var, value="txt").pack(anchor="w", padx=6, pady=3)
        ttk.Radiobutton(mode_frame, text="④ 生成结构数据（JSON，可再次导入本程序）", variable=mode_var, value="json").pack(anchor="w", padx=6, pady=3)
        path_frame = ttk.LabelFrame(dlg, text="目标位置")
        path_frame.pack(fill=tk.X, padx=10, pady=6)
        target_var = tk.StringVar()
        ttk.Entry(path_frame, textvariable=target_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6, pady=6)

        def browse():
            mode = mode_var.get()
            if mode == "files":
                d = filedialog.askdirectory(title="选择导出目标文件夹", parent=dlg)
                if d:
                    target_var.set(d)
            elif mode == "zip":
                f = filedialog.asksaveasfilename(parent=dlg, defaultextension=".zip",
                    filetypes=[("ZIP 压缩包", "*.zip"), ("所有文件", "*.*")],
                    title="保存 ZIP 压缩包", initialfile="导出节点.zip")
                if f:
                    target_var.set(f)
            elif mode == "txt":
                f = filedialog.asksaveasfilename(parent=dlg, defaultextension=".txt",
                    filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
                    title="保存结构清单", initialfile="导出结构清单.txt")
                if f:
                    target_var.set(f)
            else:
                f = filedialog.asksaveasfilename(parent=dlg, defaultextension=".json",
                    filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
                    title="保存结构数据", initialfile="导出结构数据.json")
                if f:
                    target_var.set(f)

        ttk.Button(path_frame, text="浏览…", command=browse).pack(side=tk.RIGHT, padx=6, pady=6)
        btn_frame = ttk.Frame(dlg)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)

        def do_export():
            mode = mode_var.get()
            target = target_var.get().strip()
            if not target:
                messagebox.showwarning("提示", "请先选择目标位置（点击『浏览…』）", parent=dlg)
                return
            try:
                if mode == "files":
                    self._export_nodes_as_files(top_nodes, target)
                elif mode == "zip":
                    self._export_nodes_as_zip(top_nodes, target)
                elif mode == "txt":
                    self._export_nodes_as_txt(top_nodes, target)
                else:
                    self._export_nodes_as_json(top_nodes, target)
            except Exception as e:
                log_error(f"导出所选节点失败: {traceback.format_exc()}")
                messagebox.showerror("导出失败", str(e), parent=dlg)
                return
            dlg.destroy()

        ttk.Button(btn_frame, text="导出", command=do_export).pack(side=tk.RIGHT, padx=6)
        ttk.Button(btn_frame, text="取消", command=dlg.destroy).pack(side=tk.RIGHT, padx=6)

    def _export_nodes_as_files(self, nodes, target_dir):
        os.makedirs(target_dir, exist_ok=True)
        total_files = 0
        exported = []
        skipped = []
        for node in nodes:
            base_name = node.name
            dest = os.path.join(target_dir, base_name)
            counter = 1
            while os.path.exists(dest):
                dest = os.path.join(target_dir, f"{base_name}_{counter}")
                counter += 1
            if node.path and os.path.exists(node.path):
                shutil.copytree(node.path, dest)
                for _root, _dirs, files in os.walk(dest):
                    total_files += len(files)
                exported.append(os.path.basename(dest))
            else:
                os.makedirs(dest, exist_ok=True)
                def create_dirs(n, base):
                    for child in n.children:
                        sub = os.path.join(base, child.name)
                        os.makedirs(sub, exist_ok=True)
                        create_dirs(child, sub)
                create_dirs(node, dest)
                skipped.append(node.name)
                exported.append(os.path.basename(dest) + "（空）")
        msg = f"已导出 {len(exported)} 个顶层节点到:\n{target_dir}\n\n共复制文件：{total_files} 个"
        if skipped:
            msg += f"\n\n注意：以下节点在磁盘上无对应文件夹，仅创建了空目录结构：\n  " + "\n  ".join(skipped)
        self.status_var.set(f"已导出 {len(exported)} 个节点到 {target_dir}")
        messagebox.showinfo("导出成功", msg)

    def _export_nodes_as_zip(self, nodes, zip_path):
        if not zip_path.lower().endswith(".zip"):
            zip_path += ".zip"
        total_files = 0
        used_roots = set()
        exported = []
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for node in nodes:
                base_name = node.name
                arc_root = base_name
                counter = 1
                while arc_root in used_roots:
                    arc_root = f"{base_name}_{counter}"
                    counter += 1
                used_roots.add(arc_root)
                if node.path and os.path.exists(node.path):
                    for root, _dirs, files in os.walk(node.path):
                        for f in files:
                            full = os.path.join(root, f)
                            rel = os.path.relpath(full, node.path)
                            arc = arc_root + "/" + rel.replace("\\", "/")
                            zf.write(full, arc)
                            total_files += 1
                    exported.append(arc_root)
                else:
                    zf.writestr(arc_root + "/", "")
                    exported.append(arc_root + "（空）")
        self.status_var.set(f"已打包 {len(exported)} 个节点到 {zip_path}")
        messagebox.showinfo("导出成功", f"已打包 {len(exported)} 个顶层节点到:\n{zip_path}\n\n共 {total_files} 个文件。")

    def _export_nodes_as_txt(self, nodes, file_path):
        lines = []
        lines.append("投标文件库 - 所选节点结构导出")
        lines.append(f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("=" * 70)
        lines.append("")
        custom_cols = [(c["id"], c["title"]) for c in self.columns_config if not c.get("builtin")]

        def gen(n, indent=0):
            prefix = "  " * indent
            lines.append(f"{prefix}├── {n.name}")
            if n.path:
                lines.append(f"{prefix}│    路径: {n.path}")
            if n.version:
                lines.append(f"{prefix}│    版本: {n.version}")
            if n.price:
                lines.append(f"{prefix}│    价格: {n.price}")
            if n.remark:
                lines.append(f"{prefix}│    备注: {n.remark}")
            for cid, ctitle in custom_cols:
                val = n.extra_fields.get(cid, "")
                if val:
                    lines.append(f"{prefix}│    {ctitle}: {val}")
            if n.path and os.path.exists(n.path):
                try:
                    for f in sorted(os.listdir(n.path)):
                        full = os.path.join(n.path, f)
                        if os.path.isfile(full):
                            lines.append(f"{prefix}│    📄 {f}")
                except Exception:
                    pass
            for child in n.children:
                gen(child, indent + 1)

        for i, n in enumerate(nodes):
            lines.append(f"【节点 {i + 1}】")
            gen(n)
            lines.append("")
            lines.append("-" * 70)
            lines.append("")
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines))
        self.status_var.set(f"结构清单已保存至 {file_path}")
        messagebox.showinfo("导出成功", f"结构清单已保存至:\n{file_path}")

    def _export_nodes_as_json(self, nodes, file_path):
        data = {
            "export_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source": self.base_dir,
            "columns": self.columns_config,
            "nodes": [n.to_dict() for n in nodes],
        }
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self.status_var.set(f"结构数据已保存至 {file_path}")
        messagebox.showinfo("导出成功",
            f"结构数据已保存至:\n{file_path}\n\n提示：可用『导入结构』按钮把此文件重新导入到其他库。")

    # ---------------------------- 其它 ----------------------------
    def add_node(self):
        node = self.get_selected_node()
        if not node:
            return
        new_name = simpledialog.askstring("新增节点", "请输入新节点名称：")
        if not new_name:
            return
        if node.find_child(new_name):
            messagebox.showerror("错误", f"子节点 '{new_name}' 已存在")
            return
        try:
            new_node = Node(new_name)
            if node.editable_fields is not None:
                new_node.editable_fields = list(node.editable_fields)
            node.add_child(new_node)
            self.save_config()
            self._add_tree_node(new_node)
            self.status_var.set(f"已新增节点: {new_name}")
        except Exception as e:
            log_error(f"新增节点失败: {traceback.format_exc()}")
            messagebox.showerror("错误", str(e))

    def copy_node(self):
        node = self.get_selected_node()
        if not node:
            return
        if node == self.root_node:
            messagebox.showerror("错误", "不能复制根节点")
            return
        self.copied_node_data = node.to_dict()
        self.copied_node_name = node.name
        self.copied_node_path = node.path
        self.status_var.set(f"已复制节点: {node.name} (路径: {node.path})")
        messagebox.showinfo("复制成功", f"已复制节点 '{node.name}' 及其所有子节点和文件。\n请选择目标父节点，点击「粘贴节点」。")

    def paste_node(self):
        if not self.copied_node_data:
            messagebox.showwarning("未复制", "请先复制一个节点")
            return
        target = self.get_selected_node()
        if not target:
            return
        if self.copied_node_path and target.path and target.path.startswith(self.copied_node_path):
            messagebox.showerror("错误", "不能将节点粘贴到其自身的子节点下")
            return
        new_node = Node.from_dict(self.copied_node_data)
        base_name = new_node.name
        if target.find_child(base_name):
            counter = 1
            while target.find_child(f"{base_name}_{counter}"):
                counter += 1
            new_node.name = f"{base_name}_{counter}"
        target.add_child(new_node)
        new_node.set_path(target.path)
        if self.copied_node_path and os.path.exists(self.copied_node_path):
            src = self.copied_node_path
            dst = new_node.path
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
        else:
            os.makedirs(new_node.path, exist_ok=True)
        self.save_config()
        self._add_tree_node(new_node)
        self.status_var.set(f"已粘贴节点: {new_node.name} (含全部文件)")
        messagebox.showinfo("粘贴成功", f"节点 '{new_node.name}' 及其全部文件已复制到目标位置。")

    def batch_add_nodes(self):
        parent = self.get_selected_node()
        if not parent:
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("批量添加节点")
        dialog.geometry("400x300")
        ttk.Label(dialog, text="请输入节点名称（每行一个）：").pack(pady=5)
        text_widget = tk.Text(dialog, height=15, width=50)
        text_widget.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)
        scroll = ttk.Scrollbar(text_widget)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        text_widget.config(yscrollcommand=scroll.set)
        scroll.config(command=text_widget.yview)

        def confirm():
            content = text_widget.get("1.0", tk.END).strip()
            if not content:
                return
            lines = [line.strip() for line in content.splitlines() if line.strip()]
            if not lines:
                return
            added = []
            for name in lines:
                base = name
                if parent.find_child(base):
                    counter = 1
                    while parent.find_child(f"{base}_{counter}"):
                        counter += 1
                    final_name = f"{base}_{counter}"
                else:
                    final_name = base
                new_node = Node(final_name)
                if parent.editable_fields is not None:
                    new_node.editable_fields = list(parent.editable_fields)
                parent.add_child(new_node)
                added.append(new_node)
            self.save_config()
            for new_node in added:
                self._add_tree_node(new_node)
            dialog.destroy()
            self.status_var.set(f"批量添加成功，共 {len(added)} 个节点")
            messagebox.showinfo("批量添加", f"成功添加 {len(added)} 个节点")

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="确认添加", command=confirm).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="取消", command=dialog.destroy).pack(side=tk.LEFT, padx=5)

    def import_structure(self):
        file_path = filedialog.askopenfilename(title="选择结构文件 (JSON)",
            filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")])
        if not file_path:
            return
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            node_dicts = []
            if isinstance(data, dict) and isinstance(data.get("nodes"), list):
                node_dicts = data["nodes"]
                new_name_prefix = simpledialog.askstring("导入结构",
                    "请输入导入节点的父级前缀（可留空表示沿用原节点名）：", initialvalue="")
            else:
                root_dict = data.get("tree", data) if isinstance(data, dict) else data
                new_name = simpledialog.askstring("导入结构",
                    "请输入新节点的名称（将作为导入树的父节点）：", initialvalue="导入的结构")
                if not new_name:
                    return
                node_dicts = [root_dict]
                new_name_prefix = new_name
            if not node_dicts:
                raise ValueError("文件中没有可导入的节点数据")
            imported_count = 0
            for nd in node_dicts:
                imported_node = Node.from_dict(nd)
                if new_name_prefix:
                    imported_node.name = f"{new_name_prefix}_{imported_node.name}"
                if self.root_node.find_child(imported_node.name):
                    base = imported_node.name
                    counter = 1
                    while self.root_node.find_child(f"{base}_{counter}"):
                        counter += 1
                    imported_node.name = f"{base}_{counter}"
                self.root_node.add_child(imported_node)
                imported_node.set_path(self.root_node.path)
                imported_count += 1
            self.save_config()
            self.populate_tree(keep_expanded=True)
            self.status_var.set(f"已导入 {imported_count} 个节点")
            messagebox.showinfo("导入成功", f"已成功导入 {imported_count} 个节点到库根目录下。")
        except Exception as e:
            log_error(f"导入结构失败: {traceback.format_exc()}")
            messagebox.showerror("导入失败", str(e))

    def export_structure(self):
        if not self.root_node:
            return
        file_path = filedialog.asksaveasfilename(defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")], title="导出目录结构")
        if not file_path:
            return
        def generate_text(node, indent=0):
            lines = []
            prefix = "  " * indent
            lines.append(f"{prefix}├── {node.name} (路径: {node.path})")
            files = node.get_all_file_paths()
            for f in files:
                lines.append(f"{prefix}│   📄 {os.path.basename(f)}")
            for child in node.children:
                lines.extend(generate_text(child, indent+1))
            return lines
        lines = generate_text(self.root_node)
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write("投标文件库目录结构\n")
                f.write("="*50 + "\n")
                f.write("\n".join(lines))
            self.status_var.set(f"目录结构已导出至: {file_path}")
            messagebox.showinfo("导出成功", f"结构已保存至 {file_path}")
        except Exception as e:
            log_error(f"导出结构失败: {traceback.format_exc()}")
            messagebox.showerror("导出失败", str(e))

    def upload_files(self):
        node = self.get_selected_node()
        if not node:
            return
        if not node.path:
            messagebox.showerror("错误", "节点路径无效")
            return
        files = filedialog.askopenfilenames(title="选择要上传的文件")
        if not files:
            return
        dest_dir = node.path
        os.makedirs(dest_dir, exist_ok=True)
        imported = []
        for f in files:
            base = os.path.basename(f)
            dest = os.path.join(dest_dir, base)
            try:
                if os.path.exists(dest):
                    versions_dir = os.path.join(dest_dir, "versions")
                    os.makedirs(versions_dir, exist_ok=True)
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    name, ext = os.path.splitext(base)
                    old_ver = os.path.join(versions_dir, f"{name}_{timestamp}{ext}")
                    shutil.move(dest, old_ver)
                shutil.copy2(f, dest)
                imported.append(base)
            except Exception as e:
                log_error(f"上传文件失败: {traceback.format_exc()}")
                messagebox.showerror("复制失败", f"复制 {f} 失败：{e}")
        if imported:
            self.status_var.set(f"已上传 {len(imported)} 个文件: {', '.join(imported)}")
            self.refresh_tree()

    def preview_file(self):
        node = self.get_selected_node()
        if not node:
            return
        if not node.path or not os.path.exists(node.path):
            messagebox.showerror("错误", "节点路径无效或不存在")
            return
        file_path = filedialog.askopenfilename(title="选择要预览的文件",
            initialdir=node.path, filetypes=[("所有文件", "*.*")])
        if not file_path:
            return
        self.show_preview_window(file_path)

    def show_preview_window(self, file_path):
        if not os.path.exists(file_path):
            messagebox.showerror("错误", "文件不存在")
            return
        ext = os.path.splitext(file_path)[1].lower()
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        size_str = f"{file_size} 字节" if file_size < 1024 else f"{file_size/1024:.2f} KB"
        preview_win = tk.Toplevel(self.root)
        preview_win.title(f"预览 - {file_name}")
        preview_win.geometry("800x600")
        info_frame = ttk.Frame(preview_win)
        info_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(info_frame, text=f"文件名: {file_name}", font=('Arial', 10, 'bold')).pack(side=tk.LEFT, padx=5)
        ttk.Label(info_frame, text=f"大小: {size_str}").pack(side=tk.LEFT, padx=20)
        text_exts = {'.txt', '.py', '.json', '.xml', '.csv', '.log', '.md', '.ini', '.cfg', '.conf', '.js', '.html', '.css', '.sql', '.sh', '.bat', '.ps1'}
        image_exts = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico'}
        if ext in text_exts:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except UnicodeDecodeError:
                try:
                    with open(file_path, 'r', encoding='gbk') as f:
                        content = f.read()
                except Exception:
                    content = "⚠️ 无法解码文件内容（可能为二进制文件）"
            except Exception as e:
                content = f"读取文件失败: {e}"
            text_frame = ttk.Frame(preview_win)
            text_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            text_widget = tk.Text(text_frame, wrap=tk.NONE)
            text_widget.insert(tk.END, content)
            text_widget.config(state=tk.DISABLED)
            h_scroll = ttk.Scrollbar(text_frame, orient=tk.HORIZONTAL, command=text_widget.xview)
            v_scroll = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=text_widget.yview)
            text_widget.configure(xscrollcommand=h_scroll.set, yscrollcommand=v_scroll.set)
            h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
            v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
            text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        elif ext in image_exts:
            try:
                from PIL import Image, ImageTk
                img = Image.open(file_path)
                img.thumbnail((750, 500), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                img_frame = ttk.Frame(preview_win)
                img_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
                label = ttk.Label(img_frame, image=photo)
                label.image = photo
                label.pack(expand=True)
            except ImportError:
                msg = ("图片预览需要 Pillow 库。\n\n"
                       "请通过菜单『帮助 → 🔧 安装/更新支持库…』自动安装，\n"
                       "或手动执行: pip install Pillow")
                ttk.Label(preview_win, text=msg, wraplength=600).pack(pady=20)
            except Exception as e:
                messagebox.showerror("预览失败", f"无法加载图片: {e}")
                preview_win.destroy()
                return
        else:
            msg = f"暂不支持预览此类型文件（扩展名: {ext if ext else '无'}）。\n您可以使用以下方式查看："
            ttk.Label(preview_win, text=msg, wraplength=600, justify=tk.LEFT).pack(pady=20)
            btn_frame = ttk.Frame(preview_win)
            btn_frame.pack(pady=10)
            def open_with_system():
                try:
                    if os.name == 'nt':
                        os.startfile(file_path)
                    else:
                        _sp = subprocess
                        _sp.Popen(['xdg-open', file_path])
                except Exception as e:
                    messagebox.showerror("打开失败", str(e))
            ttk.Button(btn_frame, text="用系统默认程序打开", command=open_with_system).pack(side=tk.LEFT, padx=5)
            ttk.Button(btn_frame, text="关闭", command=preview_win.destroy).pack(side=tk.LEFT, padx=5)

    def view_versions(self):
        node = self.get_selected_node()
        if not node:
            return
        versions_dir = os.path.join(node.path, "versions") if node.path else None
        if not versions_dir or not os.path.exists(versions_dir):
            messagebox.showinfo("版本历史", "该节点暂无版本历史（versions 文件夹不存在）")
            return
        files = [f for f in os.listdir(versions_dir) if os.path.isfile(os.path.join(versions_dir, f))]
        if not files:
            messagebox.showinfo("版本历史", "versions 文件夹为空")
            return
        ver_win = tk.Toplevel(self.root)
        ver_win.title(f"版本历史 - {node.name}")
        ver_win.geometry("500x300")
        listbox = tk.Listbox(ver_win, selectmode=tk.SINGLE)
        listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        for f in sorted(files):
            listbox.insert(tk.END, f)
        def open_selected():
            sel = listbox.curselection()
            if sel:
                fname = listbox.get(sel[0])
                full = os.path.join(versions_dir, fname)
                try:
                    if os.name == 'nt':
                        os.startfile(full)
                    else:
                        _sp = subprocess
                        _sp.Popen(['xdg-open', full])
                except Exception as e:
                    log_error(f"打开版本文件失败: {traceback.format_exc()}")
                    messagebox.showerror("打开失败", str(e))
        def delete_selected():
            sel = listbox.curselection()
            if sel:
                fname = listbox.get(sel[0])
                if messagebox.askyesno("确认删除", f"确定删除版本文件 {fname} 吗？"):
                    full = os.path.join(versions_dir, fname)
                    try:
                        os.remove(full)
                        listbox.delete(sel[0])
                        self.status_var.set(f"已删除版本: {fname}")
                    except Exception as e:
                        log_error(f"删除版本文件失败: {traceback.format_exc()}")
                        messagebox.showerror("删除失败", str(e))
        btn_frame = ttk.Frame(ver_win)
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="打开", command=open_selected).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="删除", command=delete_selected).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="关闭", command=ver_win.destroy).pack(side=tk.RIGHT, padx=5)

    def open_folder(self):
        node = self.get_selected_node()
        if not node:
            return
        path = node.path
        if not path or not os.path.exists(path):
            messagebox.showerror("路径不存在", f"路径 {path} 不存在")
            return
        try:
            if os.name == 'nt':
                os.startfile(path)
            else:
                _sp = subprocess
                _sp.Popen(['xdg-open', path])
        except Exception as e:
            log_error(f"打开文件夹失败: {traceback.format_exc()}")
            messagebox.showerror("打开失败", f"无法打开文件夹：{e}")

    def select_tree_item_by_path(self, path):
        item = self._path_to_iid.get(path)
        if item and self.tree.exists(item):
            self.tree.selection_set(item)
            self.tree.focus(item)
            self.tree.see(item)

    def validate_files(self):
        if not self.root_node:
            return
        leaves = self.root_node.get_leaf_nodes()
        missing = []
        for leaf in leaves:
            if not leaf.path or not os.path.exists(leaf.path):
                missing.append(leaf)
                continue
            files = [f for f in os.listdir(leaf.path) if os.path.isfile(os.path.join(leaf.path, f))]
            if not files:
                missing.append(leaf)
        if not missing:
            messagebox.showinfo("文件校验", "所有文件类型节点均包含至少一个文件，校验通过！")
            self.status_var.set("文件校验通过")
            return
        report = "以下节点缺少文件（缺失文件类型）：\n\n"
        for node in missing:
            report += f"  • {node.name} (路径: {node.path})\n"
        if messagebox.askyesno("校验未通过", f"发现 {len(missing)} 个缺失文件的节点。\n是否保存详细报告？"):
            file_path = filedialog.asksaveasfilename(defaultextension=".txt",
                filetypes=[("文本文件", "*.txt")], title="保存校验报告")
            if file_path:
                try:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(report)
                    self.status_var.set(f"校验报告已保存至 {file_path}")
                except Exception as e:
                    log_error(f"保存校验报告失败: {traceback.format_exc()}")
                    messagebox.showerror("保存失败", str(e))
        else:
            messagebox.showwarning("缺失文件", report)
            self.status_var.set(f"校验完成，{len(missing)} 个节点缺失文件")

    def on_closing(self):
        try:
            self._clear_drop_hover()
            self._clear_drop_indicator()
        except Exception:
            pass
        try:
            self._sync_current_column_widths()
        except Exception:
            pass
        self.save_config()
        self.root.destroy()


# ---------------------------- 启动入口 ----------------------------
if __name__ == "__main__":
    # ============ 步骤 1：自动检测并静默安装缺失的支持库 ============
    try:
        print("[支持库] 正在检测 tkinterdnd2 / Pillow …")
        _installed_count, _failed_installs, _missing = install_missing_support_libs(ask=False)
        if _installed_count > 0:
            _try_import_optional_libs()
            print(f"[支持库] 已自动安装 {_installed_count} 个支持库。")
        if _failed_installs:
            detail = "\n".join(f"  • {name}：{err}" for name, err in _failed_installs)
            print(f"[支持库] 部分安装失败：\n{detail}")
            try:
                messagebox.showwarning(
                    "部分支持库安装失败",
                    "以下支持库自动安装失败：\n\n"
                    f"{detail}\n\n"
                    "程序仍可继续运行，但对应功能将不可用。\n\n"
                    "您也可以手动在命令行执行：\n"
                    "    pip install tkinterdnd2 Pillow"
                )
            except Exception:
                pass
        if not _missing:
            print("[支持库] 全部支持库已就绪。")
    except Exception:
        try:
            log_error(f"支持库自动安装流程异常: {traceback.format_exc()}")
        except Exception:
            pass

    # ============ 步骤 2：启动主程序 ============
    try:
        if DND_AVAILABLE:
            try:
                root = TkinterDnD.Tk()
                print("[DND] 使用 TkinterDnD.Tk() 启动，跨窗口拖拽已启用")
            except Exception as e:
                print(f"[DND] TkinterDnD.Tk() 失败：{e}，回退到 tk.Tk()")
                root = tk.Tk()
        else:
            root = tk.Tk()
            print("提示: 未安装 tkinterdnd2，跨窗口拖拽功能不可用。")
            print("      可通过菜单『帮助 → 🔧 安装/更新支持库…』自动安装，")
            print("      或手动执行: pip install tkinterdnd2")

        app = BidLibraryApp(root)
        root.mainloop()
    except Exception as e:
        error_msg = f"程序运行异常：{traceback.format_exc()}"
        try:
            log_error(error_msg)
        except Exception:
            pass
        try:
            messagebox.showerror(
                "致命错误",
                f"程序发生错误，请查看 {ERROR_LOG} 文件。\n错误摘要：{str(e)}"
            )
        except Exception:
            pass
        sys.exit(1)