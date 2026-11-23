import os
import sys
import threading
import time
import webbrowser
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image
import pystray
from pystray import MenuItem as item

from config_manager import load_config, save_config
from github_api import GitHubAPI
from git_engine import GitEngine, find_git_executable, install_git_via_winget, is_winget_available
import win_autostart

APP_VERSION = "v1.2.0"
APP_MUTEX_NAME = "GitSync_Desktop_App_Single_Instance_Mutex_Global"
APP_WINDOW_TITLE = "깃싱크 (GitSync) - 초간편 한글 GitHub 폴더 동기화"

def is_newer_version(remote_tag, current_ver):
    """원격 배포 버전이 현재 프로그램 버전보다 높은지 비교합니다."""
    try:
        def parse_v(v_str):
            cleaned = v_str.lower().lstrip("v").strip()
            return [int(x) for x in cleaned.split(".") if x.isdigit()]
        return parse_v(remote_tag) > parse_v(current_ver)
    except Exception:
        return False

# 기본 테마 설정
ctk.set_appearance_mode("System")  # System, Dark, Light
ctk.set_default_color_theme("blue")

# 디자인 테마 상수 (Modern SaaS & Apple Minimal Palette)
FONT_FAMILY = "Segoe UI"
COLOR_BG_LIGHT = "#f8fafc"
COLOR_BG_DARK = "#090d16"
CARD_BG = ("#ffffff", "#111827")
CARD_BORDER = ("#e2e8f0", "#1f2937")
INPUT_BG = ("#f8fafc", "#0b0f19")
INPUT_BORDER = ("#cbd5e1", "#374151")
ACCENT_PRIMARY = ("#3b82f6", "#2563eb")
ACCENT_PRIMARY_HOVER = ("#2563eb", "#1d4ed8")
ACCENT_GREEN = ("#10b981", "#059669")
ACCENT_GREEN_HOVER = ("#059669", "#047857")
SUB_BTN_BG = ("#f1f5f9", "#1f2937")
SUB_BTN_TEXT = ("#334155", "#e2e8f0")
SUB_BTN_BORDER = ("#cbd5e1", "#374151")
SUB_BTN_HOVER = ("#e2e8f0", "#374151")


class TokenGuideDialog(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("GitHub 개인 액세스 토큰 (비밀번호) 발급 가이드")
        self.geometry("620x520")
        self.resizable(False, False)
        self.attributes("-topmost", True)

        main_frame = ctk.CTkFrame(self, corner_radius=12)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        title_lbl = ctk.CTkLabel(
            main_frame,
            text="🔑 GitHub 토큰(비밀번호 대체키) 1분 발급 안내",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title_lbl.pack(pady=(15, 10))

        desc_lbl = ctk.CTkLabel(
            main_frame,
            text="GitHub은 2021년부터 계정 보안을 위해 일반 비밀번호 대신\n'개인 액세스 토큰(Personal Access Token)'을 사용하도록 변경되었습니다.\n아래 3단계만 따라 하시면 1분 안에 바로 발급받으실 수 있습니다!",
            font=ctk.CTkFont(size=13),
            justify="center"
        )
        desc_lbl.pack(pady=5)

        step_box = ctk.CTkFrame(main_frame, fg_color=("gray90", "gray17"), corner_radius=8)
        step_box.pack(fill="both", expand=True, padx=15, pady=15)

        steps_text = (
            "1. 아래 [토큰 생성 페이지 바로가기] 버튼을 클릭합니다.\n"
            "   (필요한 'repo' 저장소 권한이 자동으로 선택되어 열립니다.)\n\n"
            "2. 열린 브라우저 페이지 맨 아래로 스크롤하여 초록색\n"
            "   [Generate token] 버튼을 클릭합니다.\n\n"
            "3. 화면에 생성된 'ghp_' 로 시작하는 긴 토큰 문자열을 복사하여\n"
            "   프로그램의 [토큰 입력창]에 붙여넣으시면 끝납니다!"
        )
        steps_lbl = ctk.CTkLabel(
            step_box,
            text=steps_text,
            font=ctk.CTkFont(size=13),
            justify="left"
        )
        steps_lbl.pack(padx=20, pady=20, anchor="w")

        btn_row = ctk.CTkFrame(main_frame, fg_color="transparent")
        btn_row.pack(fill="x", pady=10)

        open_web_btn = ctk.CTkButton(
            btn_row,
            text="🌐 토큰 생성 페이지 바로가기 (웹 브라우저 열기)",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#2da44e",
            hover_color="#2c974b",
            height=38,
            command=self.open_token_page
        )
        open_web_btn.pack(side="left", expand=True, padx=10)

        close_btn = ctk.CTkButton(
            btn_row,
            text="닫기",
            width=80,
            height=38,
            fg_color="gray",
            hover_color="darkgray",
            command=self.destroy
        )
        close_btn.pack(side="right", padx=10)

    def open_token_page(self):
        url = "https://github.com/settings/tokens/new?description=GitSync_App&scopes=repo"
        webbrowser.open(url)


class NewRepoDialog(ctk.CTkToplevel):
    def __init__(self, parent, token, on_created_callback):
        super().__init__(parent)
        self.parent = parent
        self.token = token
        self.on_created_callback = on_created_callback

        self.title("새 GitHub 저장소 만들기")
        self.geometry("450x330")
        self.resizable(False, False)
        self.attributes("-topmost", True)

        frame = ctk.CTkFrame(self, corner_radius=10)
        frame.pack(fill="both", expand=True, padx=20, pady=20)

        title_lbl = ctk.CTkLabel(frame, text="➕ 새 GitHub 저장소(Repository) 생성", font=ctk.CTkFont(size=16, weight="bold"))
        title_lbl.pack(pady=(10, 15))

        # 저장소 이름
        ctk.CTkLabel(frame, text="저장소 이름 (영어/숫자/- 사용 권장):", anchor="w").pack(fill="x", padx=15, pady=(5, 2))
        self.name_entry = ctk.CTkEntry(frame, placeholder_text="예: my-folder, work-notes")
        self.name_entry.pack(fill="x", padx=15, pady=(0, 10))

        # 설명
        ctk.CTkLabel(frame, text="설명 (선택 사항):", anchor="w").pack(fill="x", padx=15, pady=(5, 2))
        self.desc_entry = ctk.CTkEntry(frame, placeholder_text="저장소에 대한 간단한 설명")
        self.desc_entry.pack(fill="x", padx=15, pady=(0, 10))

        # 공개 여부
        self.private_var = ctk.BooleanVar(value=True)
        self.private_chk = ctk.CTkCheckBox(frame, text="비공개(Private) 저장소로 만들기 (나만 보기)", variable=self.private_var)
        self.private_chk.pack(anchor="w", padx=15, pady=5)

        # 버튼들
        btn_row = ctk.CTkFrame(frame, fg_color="transparent")
        btn_row.pack(fill="x", pady=(20, 10), padx=15)

        self.create_btn = ctk.CTkButton(
            btn_row, text="저장소 만들기", fg_color="#2da44e", hover_color="#2c974b", command=self.create_repo
        )
        self.create_btn.pack(side="right", padx=5)

        cancel_btn = ctk.CTkButton(
            btn_row, text="취소", fg_color="gray", hover_color="darkgray", width=70, command=self.destroy
        )
        cancel_btn.pack(side="right", padx=5)

    def create_repo(self):
        name = self.name_entry.get().strip()
        if not name:
            messagebox.showwarning("입력 필요", "저장소 이름을 입력해주세요.")
            return

        desc = self.desc_entry.get().strip()
        is_private = self.private_var.get()

        self.create_btn.configure(state="disabled", text="생성 중...")

        def _task():
            ok, res = GitHubAPI.create_repository(self.token, name, desc, is_private)
            self.after(0, lambda: self._on_finish(ok, res))

        threading.Thread(target=_task, daemon=True).start()

    def _on_finish(self, ok, res):
        self.create_btn.configure(state="normal", text="저장소 만들기")
        if ok:
            messagebox.showinfo("성공", f"저장소 '{res['name']}'이(가) 성공적으로 생성되었습니다!")
            if self.on_created_callback:
                self.on_created_callback(res)
            self.destroy()
        else:
            messagebox.showerror("생성 실패", f"저장소 생성에 실패했습니다:\n{res}")


class LargeFileDialog(ctk.CTkToplevel):
    """GitHub 100MB 초과 파일 사전 감지 경고 및 원클릭 .gitignore 처리 다이얼로그"""
    def __init__(self, parent, large_files, on_ignore_and_continue, on_cancel):
        super().__init__(parent)
        self.large_files = large_files
        self.on_ignore_and_continue = on_ignore_and_continue
        self.on_cancel = on_cancel

        self.title("대용량 파일 감지 (GitHub 100MB 제한)")
        self.geometry("600x450")
        self.resizable(False, False)
        self.attributes("-topmost", True)

        frame = ctk.CTkFrame(self, corner_radius=12)
        frame.pack(fill="both", expand=True, padx=20, pady=20)

        title_lbl = ctk.CTkLabel(
            frame,
            text="⚠️ 100MB 초과 대용량 파일 감지",
            font=ctk.CTkFont(family=FONT_FAMILY, size=16, weight="bold"),
            text_color="#d97706"
        )
        title_lbl.pack(pady=(12, 6))

        desc_lbl = ctk.CTkLabel(
            frame,
            text="GitHub은 100MB 이상의 대용량 파일 업로드를 원천 차단합니다.\n해당 파일이 포함되면 업로드 오류가 발생하므로 제외(.gitignore 등록)를 권장합니다.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            justify="center",
            text_color=("#475569", "#cbd5e1")
        )
        desc_lbl.pack(pady=(0, 10))

        # 파일 목록 박스
        list_box = ctk.CTkTextbox(frame, height=200, font=ctk.CTkFont(family="Consolas", size=11))
        list_box.pack(fill="both", expand=True, padx=15, pady=5)
        for f in large_files:
            list_box.insert("end", f"• {f['rel_path']}  ({f['size_mb']} MB)\n")
        list_box.configure(state="disabled")

        btn_row = ctk.CTkFrame(frame, fg_color="transparent")
        btn_row.pack(fill="x", pady=(14, 8), padx=15)

        ignore_btn = ctk.CTkButton(
            btn_row,
            text="⚡ 위 파일들 제외(.gitignore 등록)하고 동기화 계속",
            height=38,
            corner_radius=8,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            fg_color="#059669",
            hover_color="#047857",
            command=self._confirm
        )
        ignore_btn.pack(side="left", expand=True, padx=(0, 6))

        cancel_btn = ctk.CTkButton(
            btn_row,
            text="동기화 취소",
            width=90,
            height=38,
            corner_radius=8,
            fg_color=SUB_BTN_BG,
            text_color=SUB_BTN_TEXT,
            border_width=1,
            border_color=SUB_BTN_BORDER,
            hover_color=SUB_BTN_HOVER,
            command=self._cancel
        )
        cancel_btn.pack(side="right")

    def _confirm(self):
        self.destroy()
        if self.on_ignore_and_continue:
            self.on_ignore_and_continue()

    def _cancel(self):
        self.destroy()
        if self.on_cancel:
            self.on_cancel()


class HistoryDialog(ctk.CTkToplevel):
    """과거 커밋 시점 히스토리 뷰어, ZIP 다운로드 및 롤백 복원 다이얼로그"""
    def __init__(self, parent, git_engine, folder_path):
        super().__init__(parent)
        self.parent = parent
        self.git_engine = git_engine
        self.folder_path = folder_path

        self.title("동기화 버전 히스토리 & 백업 복원")
        self.geometry("760x560")
        self.minsize(720, 520)
        self.attributes("-topmost", True)

        frame = ctk.CTkFrame(self, corner_radius=12)
        frame.pack(fill="both", expand=True, padx=20, pady=20)

        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(12, 4))

        ctk.CTkLabel(
            header,
            text="🕒 동기화 버전 히스토리 (과거 시점 복원)",
            font=ctk.CTkFont(family=FONT_FAMILY, size=16, weight="bold")
        ).pack(side="left")

        ctk.CTkLabel(
            frame,
            text="과거 동기화 시점을 선택하여 현재 폴더 손상 없이 ZIP 파일로 내려받거나, 현재 폴더를 되돌릴 수 있습니다.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color=("#64748b", "#94a3b8")
        ).pack(anchor="w", padx=16, pady=(0, 10))

        # 커밋 리스트박스 스크롤 프레임
        self.scroll_frame = ctk.CTkScrollableFrame(frame, corner_radius=8, height=310)
        self.scroll_frame.pack(fill="both", expand=True, padx=16, pady=5)

        self.selected_commit = None
        self.commit_radio_var = ctk.StringVar(value="")

        # 하단 액션 버튼 영역
        action_bar = ctk.CTkFrame(frame, fg_color="transparent")
        action_bar.pack(fill="x", padx=16, pady=(12, 10))

        self.info_lbl = ctk.CTkLabel(
            action_bar,
            text="목록에서 복원할 시점을 선택해주세요.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color=("#475569", "#cbd5e1")
        )
        self.info_lbl.pack(side="left")

        btn_box = ctk.CTkFrame(action_bar, fg_color="transparent")
        btn_box.pack(side="right")

        self.export_zip_btn = ctk.CTkButton(
            btn_box,
            text="📦 이 시점 파일들 ZIP 다운로드",
            height=36,
            corner_radius=8,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            fg_color=("#0969da", "#0969da"),
            hover_color=("#0860ca", "#0860ca"),
            state="disabled",
            command=self._export_zip
        )
        self.export_zip_btn.pack(side="left", padx=(0, 6))

        self.restore_btn = ctk.CTkButton(
            btn_box,
            text="⏪ 현재 폴더를 이 시점으로 되돌리기",
            height=36,
            corner_radius=8,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            fg_color=("#dc2626", "#b91c1c"),
            hover_color=("#b91c1c", "#991b1b"),
            state="disabled",
            command=self._restore_folder
        )
        self.restore_btn.pack(side="left")

        self._load_history()

    def _load_history(self):
        history = self.git_engine.get_commit_history(self.folder_path, limit=30)
        if not history:
            ctk.CTkLabel(
                self.scroll_frame,
                text="동기화 기록이 없습니다. (아직 커밋이 생성되지 않았습니다)",
                font=ctk.CTkFont(family=FONT_FAMILY, size=13)
            ).pack(pady=40)
            return

        for idx, item in enumerate(history):
            card = ctk.CTkFrame(
                self.scroll_frame,
                corner_radius=8,
                fg_color=("#f8fafc", "#0f172a"),
                border_width=1,
                border_color=("#e2e8f0", "#1e293b")
            )
            card.pack(fill="x", padx=4, pady=3)

            rb = ctk.CTkRadioButton(
                card,
                text="",
                value=item["hash"],
                variable=self.commit_radio_var,
                width=24,
                command=lambda h=item: self._on_select(h)
            )
            rb.pack(side="left", padx=(10, 5), pady=8)

            txt_box = ctk.CTkFrame(card, fg_color="transparent")
            txt_box.pack(side="left", fill="x", expand=True, padx=5, pady=6)

            title_row = ctk.CTkFrame(txt_box, fg_color="transparent")
            title_row.pack(fill="x")

            msg_lbl = ctk.CTkLabel(title_row, text=item["message"], font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"))
            msg_lbl.pack(side="left")

            meta_lbl = ctk.CTkLabel(
                txt_box,
                text=f"동기화 시각: {item['date']}  |  버전 ID: {item['short_hash']}",
                font=ctk.CTkFont(family=FONT_FAMILY, size=11),
                text_color="gray"
            )
            meta_lbl.pack(anchor="w")

            if idx == 0:
                rb.select()
                self._on_select(item)

    def _on_select(self, item):
        self.selected_commit = item
        self.info_lbl.configure(text=f"선택됨: [{item['short_hash']}] {item['date']}")
        self.export_zip_btn.configure(state="normal")
        self.restore_btn.configure(state="normal")

    def _export_zip(self):
        if not self.selected_commit:
            return
        clean_date = self.selected_commit['date'].replace('-', '').replace(' ', '_').replace(':', '')
        default_name = f"GitSync_백업_{clean_date}.zip"
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        zip_path = filedialog.asksaveasfilename(
            initialdir=desktop,
            initialfile=default_name,
            defaultextension=".zip",
            filetypes=[("ZIP 압축 파일", "*.zip")]
        )
        if not zip_path:
            return

        ok, out = self.git_engine.export_archive_at_commit(self.folder_path, self.selected_commit["hash"], zip_path)
        if ok:
            messagebox.showinfo("ZIP 저장 완료", f"선택한 시점의 모든 파일이 압축되어 저장되었습니다!\n\n저장 위치:\n{zip_path}")
        else:
            messagebox.showerror("추출 실패", f"ZIP 생성 중 오류:\n{out}")

    def _restore_folder(self):
        if not self.selected_commit:
            return
        ans = messagebox.askyesno(
            "시점 되돌리기 경고",
            f"선택한 시점({self.selected_commit['date']})으로 현재 폴더의 모든 파일을 되돌리시겠습니까?\n\n"
            f"※ 주의: 현재 폴더의 파일들이 해당 시점으로 복원됩니다."
        )
        if not ans:
            return

        ok, msg = self.git_engine.restore_to_commit(self.folder_path, self.selected_commit["hash"])
        if ok:
            messagebox.showinfo("복원 완료", "현재 폴더의 파일들이 선택한 시점으로 복원되었습니다.")
            self.destroy()
        else:
            messagebox.showerror("복원 실패", f"복원 중 오류:\n{msg}")


class GitSyncApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # 작업표시줄 아이콘 분리 설정 (Windows)
        try:
            import ctypes
            myappid = "gitsync.desktop.app.1.2"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass

        self.title(APP_WINDOW_TITLE)
        self.geometry("880x900")
        self.minsize(820, 820)

        # 창 아이콘 설정
        self.icon_path = self._get_app_icon_path()
        if os.path.exists(self.icon_path):
            try:
                self.iconbitmap(self.icon_path)
            except Exception:
                pass

        self.config_data = load_config()
        self.git_engine = GitEngine()
        self.repos_list = []  # GitHub에서 가져온 저장소 목록
        self.is_syncing = False
        self.auto_sync_timer = None
        self.tray_icon = None
        self._first_tray_notify = True

        self._build_ui()
        self._load_saved_settings()
        self._check_git_status()
        self._setup_tray_icon()

        # 창 닫기 버튼 이벤트 가로채기 (트레이 최소화 처리)
        self.protocol("WM_DELETE_WINDOW", self._on_close_window)

    def _get_app_icon_path(self):
        if getattr(sys, "frozen", False):
            base_dir = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))

        icon_path = os.path.join(base_dir, "app_icon.ico")
        if not os.path.exists(icon_path):
            icon_path = os.path.join(os.path.dirname(sys.executable), "app_icon.ico")
        return icon_path

    def _build_ui(self):
        # 메인 그리드 레이아웃
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(5, weight=1)

        # 1. 헤더 영역 (Row 0)
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, padx=22, pady=(16, 8), sticky="ew")
        header_frame.grid_columnconfigure(0, weight=1)

        title_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_box.pack(side="left")

        title_row = ctk.CTkFrame(title_box, fg_color="transparent")
        title_row.pack(anchor="w")

        logo_lbl = ctk.CTkLabel(
            title_row,
            text="🐙 깃싱크  GitSync",
            font=ctk.CTkFont(family=FONT_FAMILY, size=22, weight="bold")
        )
        logo_lbl.pack(side="left")

        self.version_badge = ctk.CTkButton(
            title_row,
            text=APP_VERSION,
            width=55,
            height=22,
            corner_radius=11,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            fg_color=SUB_BTN_BG,
            text_color=SUB_BTN_TEXT,
            border_width=1,
            border_color=SUB_BTN_BORDER,
            hover_color=SUB_BTN_HOVER,
            command=self._manual_check_update
        )
        self.version_badge.pack(side="left", padx=(10, 0))

        sub_lbl = ctk.CTkLabel(
            title_box,
            text="컴퓨터 폴더와 GitHub 저장소를 클릭 한 번으로 안전하게 동기화합니다.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color=("#64748b", "#94a3b8")
        )
        sub_lbl.pack(anchor="w", pady=(2, 0))

        # 헤더 우측 컨트롤 (Git 상태 뱃지 + 테마 스위치)
        header_right = ctk.CTkFrame(header_frame, fg_color="transparent")
        header_right.pack(side="right")

        self.git_status_btn = ctk.CTkButton(
            header_right,
            text="Git 상태 확인 중...",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            height=34,
            corner_radius=17,
            border_width=1,
            command=self._on_git_status_btn_click
        )
        self.git_status_btn.pack(side="left", padx=(0, 10))

        # 테마 스위치
        self.theme_btn = ctk.CTkSegmentedButton(
            header_right,
            values=["시스템", "다크", "라이트"],
            height=34,
            corner_radius=8,
            command=self._change_theme
        )
        self.theme_btn.set("시스템")
        self.theme_btn.pack(side="left")

        # 새 버전 업데이트 알림 배너 (Row 1)
        self.update_banner_frame = ctk.CTkFrame(
            self,
            corner_radius=10,
            fg_color=("#eff6ff", "#172554"),
            border_color=("#60a5fa", "#2563eb"),
            border_width=1
        )
        self.update_banner_frame.grid_columnconfigure(0, weight=1)

        banner_inner = ctk.CTkFrame(self.update_banner_frame, fg_color="transparent")
        banner_inner.pack(fill="x", padx=16, pady=8)

        self.update_msg_lbl = ctk.CTkLabel(
            banner_inner,
            text="🎉 새로운 업데이트가 있습니다!",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=("#1d4ed8", "#93c5fd")
        )
        self.update_msg_lbl.pack(side="left")

        update_btn_box = ctk.CTkFrame(banner_inner, fg_color="transparent")
        update_btn_box.pack(side="right")

        self.update_download_btn = ctk.CTkButton(
            update_btn_box,
            text="🌐 다운로드 페이지 열기",
            height=28,
            corner_radius=6,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            fg_color="#2563eb",
            hover_color="#1d4ed8"
        )
        self.update_download_btn.pack(side="left", padx=(0, 6))

        close_update_btn = ctk.CTkButton(
            update_btn_box,
            text="✕",
            width=28,
            height=28,
            corner_radius=6,
            fg_color=SUB_BTN_BG,
            text_color=SUB_BTN_TEXT,
            hover_color=SUB_BTN_HOVER,
            command=self.update_banner_frame.grid_remove
        )
        close_update_btn.pack(side="left")

        # Git 미설치 알림 배너 (Row 2 - 미설치 시에만 표시)
        self.git_banner_frame = ctk.CTkFrame(
            self,
            corner_radius=12,
            fg_color=("#fffbeb", "#2a1b05"),
            border_color="#f59e0b",
            border_width=1
        )
        self.git_banner_frame.grid_columnconfigure(0, weight=1)

        banner_top = ctk.CTkFrame(self.git_banner_frame, fg_color="transparent")
        banner_top.grid(row=0, column=0, padx=18, pady=(12, 2), sticky="ew")

        ctk.CTkLabel(
            banner_top,
            text="⚠️ 컴퓨터에 Git이 설치되어 있지 않습니다!",
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"),
            text_color=("#b45309", "#fbbf24")
        ).pack(side="left")

        ctk.CTkLabel(
            self.git_banner_frame,
            text="GitHub과 폴더를 동기화하려면 Git 엔진이 필요합니다.\n아래 [원클릭 자동 설치]를 누르시면 별도 설정 없이 바로 자동 설치됩니다.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            justify="left",
            text_color=("#78350f", "#fef3c7")
        ).grid(row=1, column=0, padx=18, pady=(0, 12), sticky="w")

        banner_btn_row = ctk.CTkFrame(self.git_banner_frame, fg_color="transparent")
        banner_btn_row.grid(row=0, column=1, rowspan=2, padx=18, pady=12, sticky="e")

        self.install_git_btn = ctk.CTkButton(
            banner_btn_row,
            text="⚡ Git 원클릭 자동 설치",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            fg_color=ACCENT_GREEN,
            hover_color=ACCENT_GREEN_HOVER,
            height=38,
            corner_radius=8,
            command=self._install_git_clicked
        )
        self.install_git_btn.pack(side="left", padx=(0, 6))

        web_git_btn = ctk.CTkButton(
            banner_btn_row,
            text="🌐 웹에서 받기",
            width=90,
            height=38,
            corner_radius=8,
            fg_color=SUB_BTN_BG,
            text_color=SUB_BTN_TEXT,
            border_width=1,
            border_color=SUB_BTN_BORDER,
            hover_color=SUB_BTN_HOVER,
            command=lambda: webbrowser.open("https://git-scm.com/download/win")
        )
        web_git_btn.pack(side="left")

        # 2. 계정 설정 영역 (Card 1 - Row 3)
        acc_frame = ctk.CTkFrame(
            self,
            corner_radius=14,
            fg_color=CARD_BG,
            border_color=CARD_BORDER,
            border_width=1
        )
        acc_frame.grid(row=3, column=0, padx=22, pady=5, sticky="ew")
        acc_frame.grid_columnconfigure(1, weight=1)

        acc_title = ctk.CTkLabel(
            acc_frame,
            text="1. GitHub 계정 연결",
            font=ctk.CTkFont(family=FONT_FAMILY, size=15, weight="bold")
        )
        acc_title.grid(row=0, column=0, columnspan=3, padx=18, pady=(12, 6), sticky="w")

        # 사용자명
        ctk.CTkLabel(
            acc_frame,
            text="GitHub 아이디",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=("#475569", "#cbd5e1")
        ).grid(row=1, column=0, padx=18, pady=4, sticky="w")

        self.username_entry = ctk.CTkEntry(
            acc_frame,
            placeholder_text="GitHub 사용자 이름 (예: myid)",
            height=36,
            corner_radius=8,
            fg_color=INPUT_BG,
            border_color=INPUT_BORDER
        )
        self.username_entry.grid(row=1, column=1, padx=(0, 10), pady=4, sticky="ew")

        # 토큰 발급 가이드 버튼
        guide_btn = ctk.CTkButton(
            acc_frame,
            text="🔑 토큰 발급 가이드",
            width=135,
            height=36,
            corner_radius=8,
            fg_color=("#f5f3ff", "#2e1065"),
            text_color=("#7c3aed", "#c4b5fd"),
            border_width=1,
            border_color=("#ddd6fe", "#5b21b6"),
            hover_color=("#ede9fe", "#3b0764"),
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            command=self._show_token_guide
        )
        guide_btn.grid(row=1, column=2, padx=(0, 18), pady=4, sticky="e")

        # 토큰 입력창 (비밀번호 대체)
        ctk.CTkLabel(
            acc_frame,
            text="개인 토큰 (비밀번호)",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=("#475569", "#cbd5e1")
        ).grid(row=2, column=0, padx=18, pady=4, sticky="w")

        token_subframe = ctk.CTkFrame(acc_frame, fg_color="transparent")
        token_subframe.grid(row=2, column=1, padx=(0, 10), pady=4, sticky="ew")
        token_subframe.grid_columnconfigure(0, weight=1)

        self.token_entry = ctk.CTkEntry(
            token_subframe,
            placeholder_text="ghp_로 시작하는 개인 액세스 토큰 붙여넣기",
            show="*",
            height=36,
            corner_radius=8,
            fg_color=INPUT_BG,
            border_color=INPUT_BORDER
        )
        self.token_entry.grid(row=0, column=0, sticky="ew")

        self.show_token_btn = ctk.CTkButton(
            token_subframe,
            text="👁️",
            width=36,
            height=36,
            corner_radius=8,
            fg_color=SUB_BTN_BG,
            text_color=SUB_BTN_TEXT,
            border_width=1,
            border_color=SUB_BTN_BORDER,
            hover_color=SUB_BTN_HOVER,
            command=self._toggle_token_visibility
        )
        self.show_token_btn.grid(row=0, column=1, padx=(6, 0))

        # 연결 테스트 및 저장소 불러오기 버튼
        self.connect_btn = ctk.CTkButton(
            acc_frame,
            text="🔗 연결 & 저장소 불러오기",
            width=165,
            height=36,
            corner_radius=8,
            fg_color=ACCENT_PRIMARY,
            hover_color=ACCENT_PRIMARY_HOVER,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            command=self._on_click_connect
        )
        self.connect_btn.grid(row=2, column=2, padx=(0, 18), pady=4, sticky="e")

        # 계정 상태 문구 및 3대 시스템 옵션 체크박스
        status_row = ctk.CTkFrame(acc_frame, fg_color="transparent")
        status_row.grid(row=3, column=0, columnspan=3, padx=18, pady=(6, 12), sticky="ew")
        status_row.grid_columnconfigure(0, weight=1)

        self.account_status_lbl = ctk.CTkLabel(
            status_row,
            text="⚠️ GitHub 토큰을 입력하고 [연결 & 저장소 불러오기]를 눌러주세요.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color="#d97706"
        )
        self.account_status_lbl.grid(row=0, column=0, sticky="w")

        options_box = ctk.CTkFrame(status_row, fg_color="transparent")
        options_box.grid(row=0, column=1, sticky="e")

        self.remember_var = ctk.BooleanVar(value=True)
        self.remember_chk = ctk.CTkCheckBox(
            options_box,
            text="토큰 저장",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            variable=self.remember_var,
            command=self._save_current_settings
        )
        self.remember_chk.pack(side="left", padx=5)

        self.tray_var = ctk.BooleanVar(value=True)
        self.tray_chk = ctk.CTkCheckBox(
            options_box,
            text="트레이 최소화",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            variable=self.tray_var,
            command=self._save_current_settings
        )
        self.tray_chk.pack(side="left", padx=5)

        self.autostart_var = ctk.BooleanVar(value=False)
        self.autostart_chk = ctk.CTkCheckBox(
            options_box,
            text="부팅 시 자동실행",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            variable=self.autostart_var,
            command=self._on_toggle_autostart
        )
        self.autostart_chk.pack(side="left", padx=5)

        # 3. 동기화 대상 설정 (Card 2 - Row 4: 다중 프로필 관리 탑재)
        target_frame = ctk.CTkFrame(
            self,
            corner_radius=14,
            fg_color=CARD_BG,
            border_color=CARD_BORDER,
            border_width=1
        )
        target_frame.grid(row=4, column=0, padx=22, pady=5, sticky="ew")
        target_frame.grid_columnconfigure(1, weight=1)

        target_title = ctk.CTkLabel(
            target_frame,
            text="2. 동기화 대상 설정 (내 컴퓨터 폴더 ↔ GitHub 저장소)",
            font=ctk.CTkFont(family=FONT_FAMILY, size=15, weight="bold")
        )
        target_title.grid(row=0, column=0, columnspan=3, padx=18, pady=(12, 6), sticky="w")

        # [신규 기능] 프로필 전환/추가/삭제 줄 (Row 1)
        profile_row = ctk.CTkFrame(target_frame, fg_color="transparent")
        profile_row.grid(row=1, column=0, columnspan=3, padx=18, pady=(0, 6), sticky="ew")
        profile_row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            profile_row,
            text="📁 프로젝트 프로필",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=("#475569", "#cbd5e1")
        ).grid(row=0, column=0, padx=(0, 10), sticky="w")

        self.profile_combo = ctk.CTkComboBox(
            profile_row,
            values=["기본 작업"],
            height=34,
            corner_radius=8,
            fg_color=INPUT_BG,
            border_color=INPUT_BORDER,
            command=self._on_profile_change
        )
        self.profile_combo.grid(row=0, column=1, padx=(0, 8), sticky="ew")

        profile_btn_box = ctk.CTkFrame(profile_row, fg_color="transparent")
        profile_btn_box.grid(row=0, column=2, sticky="e")

        add_profile_btn = ctk.CTkButton(
            profile_btn_box,
            text="➕ 새 프로필",
            width=85,
            height=34,
            corner_radius=8,
            fg_color=SUB_BTN_BG,
            text_color=SUB_BTN_TEXT,
            border_width=1,
            border_color=SUB_BTN_BORDER,
            hover_color=SUB_BTN_HOVER,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            command=self._add_profile
        )
        add_profile_btn.pack(side="left", padx=(0, 4))

        rename_profile_btn = ctk.CTkButton(
            profile_btn_box,
            text="✏️ 이름 변경",
            width=85,
            height=34,
            corner_radius=8,
            fg_color=SUB_BTN_BG,
            text_color=SUB_BTN_TEXT,
            border_width=1,
            border_color=SUB_BTN_BORDER,
            hover_color=SUB_BTN_HOVER,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            command=self._rename_profile
        )
        rename_profile_btn.pack(side="left", padx=(0, 4))

        del_profile_btn = ctk.CTkButton(
            profile_btn_box,
            text="🗑️ 삭제",
            width=60,
            height=34,
            corner_radius=8,
            fg_color=SUB_BTN_BG,
            text_color=("#ef4444", "#f87171"),
            border_width=1,
            border_color=SUB_BTN_BORDER,
            hover_color=SUB_BTN_HOVER,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            command=self._delete_profile
        )
        del_profile_btn.pack(side="left")

        # 로컬 폴더 (Row 2)
        ctk.CTkLabel(
            target_frame,
            text="내 컴퓨터 폴더",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=("#475569", "#cbd5e1")
        ).grid(row=2, column=0, padx=18, pady=4, sticky="w")

        self.folder_entry = ctk.CTkEntry(
            target_frame,
            placeholder_text="동기화할 컴퓨터 폴더 경로 (예: C:\\Users\\...\\Desktop\\내폴더)",
            height=36,
            corner_radius=8,
            fg_color=INPUT_BG,
            border_color=INPUT_BORDER
        )
        self.folder_entry.grid(row=2, column=1, padx=(0, 10), pady=4, sticky="ew")

        folder_btn_row = ctk.CTkFrame(target_frame, fg_color="transparent")
        folder_btn_row.grid(row=2, column=2, padx=(0, 18), pady=4, sticky="e")

        browse_btn = ctk.CTkButton(
            folder_btn_row,
            text="📁 폴더 선택...",
            width=100,
            height=36,
            corner_radius=8,
            fg_color=SUB_BTN_BG,
            text_color=SUB_BTN_TEXT,
            border_width=1,
            border_color=SUB_BTN_BORDER,
            hover_color=SUB_BTN_HOVER,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            command=self._browse_folder
        )
        browse_btn.pack(side="left", padx=(0, 5))

        open_folder_btn = ctk.CTkButton(
            folder_btn_row,
            text="📂 열기",
            width=58,
            height=36,
            corner_radius=8,
            fg_color=SUB_BTN_BG,
            text_color=SUB_BTN_TEXT,
            border_width=1,
            border_color=SUB_BTN_BORDER,
            hover_color=SUB_BTN_HOVER,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            command=self._open_local_folder
        )
        open_folder_btn.pack(side="left")

        # GitHub 저장소 (Row 3)
        ctk.CTkLabel(
            target_frame,
            text="GitHub 저장소",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=("#475569", "#cbd5e1")
        ).grid(row=3, column=0, padx=18, pady=4, sticky="w")

        self.repo_combo = ctk.CTkComboBox(
            target_frame,
            values=["[계정을 연결하여 저장소 목록을 불러오세요]"],
            height=36,
            corner_radius=8,
            fg_color=INPUT_BG,
            border_color=INPUT_BORDER,
            command=self._on_repo_selected
        )
        self.repo_combo.grid(row=3, column=1, padx=(0, 10), pady=(4, 12), sticky="ew")

        repo_btn_row = ctk.CTkFrame(target_frame, fg_color="transparent")
        repo_btn_row.grid(row=3, column=2, padx=(0, 18), pady=(4, 12), sticky="e")

        new_repo_btn = ctk.CTkButton(
            repo_btn_row,
            text="➕ 새 저장소",
            width=100,
            height=36,
            corner_radius=8,
            fg_color=ACCENT_GREEN,
            hover_color=ACCENT_GREEN_HOVER,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            command=self._open_new_repo_dialog
        )
        new_repo_btn.pack(side="left", padx=(0, 5))

        open_repo_web_btn = ctk.CTkButton(
            repo_btn_row,
            text="🌐 웹",
            width=58,
            height=36,
            corner_radius=8,
            fg_color=SUB_BTN_BG,
            text_color=SUB_BTN_TEXT,
            border_width=1,
            border_color=SUB_BTN_BORDER,
            hover_color=SUB_BTN_HOVER,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            command=self._open_repo_in_browser
        )
        open_repo_web_btn.pack(side="left")

        # 4. 동기화 실행 및 복원 영역 (Card 3 - Row 5)
        action_frame = ctk.CTkFrame(
            self,
            corner_radius=14,
            fg_color=CARD_BG,
            border_color=CARD_BORDER,
            border_width=1
        )
        action_frame.grid(row=5, column=0, padx=22, pady=(5, 14), sticky="nsew")
        action_frame.grid_columnconfigure(0, weight=2)
        action_frame.grid_columnconfigure(1, weight=1)
        action_frame.grid_columnconfigure(2, weight=1)
        action_frame.grid_rowconfigure(7, weight=1)

        # Card 3 헤더: 제목 + [신규 기능] 과거 시점 버전 복원 뷰어 열기 버튼
        action_header = ctk.CTkFrame(action_frame, fg_color="transparent")
        action_header.grid(row=0, column=0, columnspan=3, padx=18, pady=(12, 6), sticky="ew")

        ctk.CTkLabel(
            action_header,
            text="3. 동기화 실행",
            font=ctk.CTkFont(family=FONT_FAMILY, size=15, weight="bold")
        ).pack(side="left")

        # [신규 기능] 어제 버전으로 되돌리기 (버전 복원 뷰어) 버튼
        history_btn = ctk.CTkButton(
            action_header,
            text="🕒 버전 히스토리 & 백업 복원 (되돌리기)",
            height=32,
            corner_radius=8,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            fg_color=("#f3e8ff", "#3b0764"),
            text_color=("#7e22ce", "#e9d5ff"),
            border_width=1,
            border_color=("#d8b4fe", "#6b21a8"),
            hover_color=("#e9d5ff", "#581c87"),
            command=self._open_history_dialog
        )
        history_btn.pack(side="right")

        # 스마트 동기화 상태 감지 배너 (Row 1)
        self.sync_status_banner = ctk.CTkFrame(
            action_frame,
            corner_radius=10,
            border_width=1,
            fg_color=("#f8fafc", "#0f172a"),
            border_color=("#e2e8f0", "#1e293b")
        )
        self.sync_status_banner.grid(row=1, column=0, columnspan=3, padx=18, pady=(0, 8), sticky="ew")
        self.sync_status_banner.grid_columnconfigure(0, weight=1)

        banner_content = ctk.CTkFrame(self.sync_status_banner, fg_color="transparent")
        banner_content.pack(fill="x", padx=14, pady=8)

        status_text_box = ctk.CTkFrame(banner_content, fg_color="transparent")
        status_text_box.pack(side="left", fill="x", expand=True)

        self.status_title_lbl = ctk.CTkLabel(
            status_text_box,
            text="🔍 동기화 상태를 확인하는 중...",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            text_color=("#334155", "#94a3b8")
        )
        self.status_title_lbl.pack(anchor="w")

        self.status_desc_lbl = ctk.CTkLabel(
            status_text_box,
            text="컴퓨터와 GitHub 저장소의 최신 변경사항을 비교합니다.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=("#64748b", "#64748b")
        )
        self.status_desc_lbl.pack(anchor="w", pady=(1, 0))

        banner_actions = ctk.CTkFrame(banner_content, fg_color="transparent")
        banner_actions.pack(side="right")

        self.status_quick_pull_btn = ctk.CTkButton(
            banner_actions,
            text="⬇️ 지금 내려받기",
            height=30,
            corner_radius=6,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            fg_color="#0969da",
            hover_color="#0860ca",
            command=lambda: self._start_git_task("pull")
        )

        self.status_refresh_btn = ctk.CTkButton(
            banner_actions,
            text="🔄 상태 새로고침",
            width=95,
            height=30,
            corner_radius=6,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            fg_color=SUB_BTN_BG,
            text_color=SUB_BTN_TEXT,
            border_width=1,
            border_color=SUB_BTN_BORDER,
            hover_color=SUB_BTN_HOVER,
            command=self._trigger_inspect_status
        )
        self.status_refresh_btn.pack(side="right")

        # 동기화 메모 / 제목 입력창 (Row 2)
        memo_frame = ctk.CTkFrame(action_frame, fg_color="transparent")
        memo_frame.grid(row=2, column=0, columnspan=3, padx=18, pady=(0, 8), sticky="ew")
        memo_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            memo_frame,
            text="📝 동기화 메모/제목",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=("#475569", "#cbd5e1")
        ).grid(row=0, column=0, padx=(0, 10), sticky="w")

        self.commit_msg_entry = ctk.CTkEntry(
            memo_frame,
            placeholder_text="예: 메인 시안 수정, 문서 1차 정리 등 (선택 사항, 비워두면 자동 기본값)",
            height=36,
            corner_radius=8,
            fg_color=INPUT_BG,
            border_color=INPUT_BORDER
        )
        self.commit_msg_entry.grid(row=0, column=1, sticky="ew")

        ctk.CTkLabel(
            memo_frame,
            text="*시각은 메모 앞에 자동 기록됨",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=("#94a3b8", "#64748b")
        ).grid(row=0, column=2, padx=(10, 0), sticky="e")

        # 3대 동기화 버튼 (Row 3)
        self.sync_btn = ctk.CTkButton(
            action_frame,
            text="🚀  원클릭 전체 동기화\n(내려받기 + 올리기 일괄 처리)",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            height=52,
            corner_radius=10,
            fg_color=("#4f46e5", "#4f46e5"),
            hover_color=("#4338ca", "#4338ca"),
            command=lambda: self._start_git_task("sync")
        )
        self.sync_btn.grid(row=3, column=0, padx=(18, 5), pady=5, sticky="ew")

        self.pull_btn = ctk.CTkButton(
            action_frame,
            text="⬇️  내려받기만 (Pull)\n(GitHub 최신 파일 가져오기)",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            height=52,
            corner_radius=10,
            fg_color=SUB_BTN_BG,
            text_color=SUB_BTN_TEXT,
            border_width=1,
            border_color=SUB_BTN_BORDER,
            hover_color=SUB_BTN_HOVER,
            command=lambda: self._start_git_task("pull")
        )
        self.pull_btn.grid(row=3, column=1, padx=5, pady=5, sticky="ew")

        self.push_btn = ctk.CTkButton(
            action_frame,
            text="⬆️  올리기만 (Push)\n(내 컴퓨터 파일 업로드)",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            height=52,
            corner_radius=10,
            fg_color=SUB_BTN_BG,
            text_color=SUB_BTN_TEXT,
            border_width=1,
            border_color=SUB_BTN_BORDER,
            hover_color=SUB_BTN_HOVER,
            command=lambda: self._start_git_task("push")
        )
        self.push_btn.grid(row=3, column=2, padx=(5, 18), pady=5, sticky="ew")

        # 자동 동기화 설정 (Row 4)
        auto_frame = ctk.CTkFrame(action_frame, fg_color="transparent")
        auto_frame.grid(row=4, column=0, columnspan=3, padx=18, pady=(6, 4), sticky="ew")

        self.auto_sync_var = ctk.BooleanVar(value=False)
        self.auto_sync_chk = ctk.CTkCheckBox(
            auto_frame,
            text="주기적 자동 동기화 활성화",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            variable=self.auto_sync_var,
            command=self._on_toggle_auto_sync
        )
        self.auto_sync_chk.pack(side="left", padx=(0, 10))

        ctk.CTkLabel(
            auto_frame,
            text="주기:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color=("#64748b", "#94a3b8")
        ).pack(side="left", padx=(5, 5))

        self.interval_combo = ctk.CTkComboBox(
            auto_frame,
            values=["3분", "5분", "10분", "30분", "60분"],
            width=85,
            height=30,
            corner_radius=6,
            fg_color=INPUT_BG,
            border_color=INPUT_BORDER,
            command=lambda v: self._save_current_settings()
        )
        self.interval_combo.set("10분")
        self.interval_combo.pack(side="left")

        self.auto_status_lbl = ctk.CTkLabel(
            auto_frame,
            text="",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=("#64748b", "#94a3b8")
        )
        self.auto_status_lbl.pack(side="left", padx=15)

        # 4. 실시간 로그 영역 (Row 5)
        log_header_frame = ctk.CTkFrame(action_frame, fg_color="transparent")
        log_header_frame.grid(row=5, column=0, columnspan=3, padx=18, pady=(8, 4), sticky="ew")

        ctk.CTkLabel(
            log_header_frame,
            text="실시간 진행 상태 및 한글 로그",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            text_color=("#334155", "#e2e8f0")
        ).pack(side="left")

        clear_log_btn = ctk.CTkButton(
            log_header_frame,
            text="로그 지우기",
            width=75,
            height=26,
            corner_radius=6,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            fg_color=SUB_BTN_BG,
            text_color=SUB_BTN_TEXT,
            border_width=1,
            border_color=SUB_BTN_BORDER,
            hover_color=SUB_BTN_HOVER,
            command=self._clear_log
        )
        clear_log_btn.pack(side="right")

        # 프로그레스 바 (Row 6)
        self.progress_bar = ctk.CTkProgressBar(action_frame, height=4, corner_radius=2)
        self.progress_bar.grid(row=6, column=0, columnspan=3, padx=18, pady=(0, 6), sticky="ew")
        self.progress_bar.set(0)

        # 터미널 스타일 로그 텍스트 박스 (Row 7)
        self.log_textbox = ctk.CTkTextbox(
            action_frame,
            height=125,
            corner_radius=8,
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color=("#0f172a", "#020617"),
            text_color="#38bdf8",
            border_width=1,
            border_color=("#1e293b", "#0f172a")
        )
        self.log_textbox.grid(row=7, column=0, columnspan=3, padx=18, pady=(0, 16), sticky="nsew")

    # 테마 변경
    def _change_theme(self, value):
        mode_map = {"시스템": "System", "다크": "Dark", "라이트": "Light"}
        ctk.set_appearance_mode(mode_map.get(value, "System"))

    # 가이드 & 서브 다이얼로그
    def _show_token_guide(self):
        TokenGuideDialog(self)

    def _toggle_token_visibility(self):
        if self.token_entry.cget("show") == "*":
            self.token_entry.configure(show="")
            self.show_token_btn.configure(text="🔒")
        else:
            self.token_entry.configure(show="*")
            self.show_token_btn.configure(text="👁️")

    def _browse_folder(self):
        initial = self.folder_entry.get().strip()
        if not initial or not os.path.isdir(initial):
            initial = os.path.expanduser("~")
        path = filedialog.askdirectory(initialdir=initial, title="동기화할 컴퓨터 폴더 선택")
        if path:
            norm_path = os.path.normpath(path)
            self.folder_entry.delete(0, "end")
            self.folder_entry.insert(0, norm_path)
            self._save_current_settings()
            self._log(f"📁 대상 폴더가 설정되었습니다: {norm_path}")
            self._trigger_inspect_status()

    def _open_local_folder(self):
        path = self.folder_entry.get().strip()
        if path and os.path.isdir(path):
            os.startfile(path)
        else:
            messagebox.showwarning("폴더 확인", "선택된 폴더가 없거나 존재하지 않는 경로입니다.")

    def _open_repo_in_browser(self):
        url = self._get_selected_repo_url()
        if url:
            webbrowser.open(url)
        else:
            messagebox.showinfo("알림", "선택된 GitHub 저장소가 없습니다.")

    def _open_new_repo_dialog(self):
        token = self.token_entry.get().strip()
        if not token:
            messagebox.showwarning("토큰 필요", "새 저장소를 만들려면 먼저 GitHub 토큰을 입력해야 합니다.")
            return

        def _on_created(repo_info):
            self.repos_list.insert(0, repo_info)
            self._update_repo_combobox()
            self.repo_combo.set(repo_info["full_name"])
            self._save_current_settings()
            self._log(f"➕ 새 저장소가 생성되어 자동 선택되었습니다: {repo_info['full_name']}")

        NewRepoDialog(self, token, _on_created)

    def _open_history_dialog(self):
        local_folder = self.folder_entry.get().strip()
        if not local_folder or not os.path.isdir(local_folder):
            messagebox.showwarning("폴더 확인", "먼저 동기화 대상 폴더를 선택해주세요.")
            return

        if not self.git_engine.is_git_repo(local_folder):
            messagebox.showinfo(
                "동기화 이력 없음",
                "이 폴더는 아직 Git 동기화가 진행된 적이 없습니다.\n\n먼저 [원클릭 전체 동기화]를 1회 실행하시면 그때부터 과거 시점 기록이 저장되고 언제든 복원할 수 있습니다!"
            )
            return

        HistoryDialog(self, self.git_engine, local_folder)

    def _log(self, message):
        now = datetime.now().strftime("%H:%M:%S")
        line = f"[{now}] {message}\n"
        self.log_textbox.insert("end", line)
        self.log_textbox.see("end")

    def _clear_log(self):
        self.log_textbox.delete("1.0", "end")

    # Git 설치 및 상태
    def _check_git_status(self):
        if not self.git_engine.is_git_available():
            self.git_banner_frame.grid(row=2, column=0, padx=22, pady=5, sticky="ew")
            if hasattr(self, "git_status_btn"):
                self.git_status_btn.configure(
                    text="⚠️  Git 미설치",
                    fg_color=("#fffbeb", "#451a03"),
                    text_color=("#d97706", "#fbbf24"),
                    border_color=("#fde68a", "#b45309"),
                    hover_color=("#fef3c7", "#78350f")
                )
            self._log("⚠️ 경고: 시스템에 Git이 설치되어 있지 않습니다.")
            self._log("   상단의 [⚡ Git 원클릭 자동 설치] 버튼을 누르시면 바로 설치됩니다.")
            self._set_git_ready(False)
        else:
            self.git_banner_frame.grid_remove()
            if hasattr(self, "git_status_btn"):
                self.git_status_btn.configure(
                    text="✓  Git 준비 완료",
                    fg_color=("#ecfdf5", "#064e3b"),
                    text_color=("#059669", "#34d399"),
                    border_color=("#a7f3d0", "#047857"),
                    hover_color=("#d1fae5", "#065f46")
                )
            self._log(f"✅ Git 엔진 준비 완료: {self.git_engine.git_path}")
            self._set_git_ready(True)

    def _on_git_status_btn_click(self):
        if self.git_engine.is_git_available():
            messagebox.showinfo(
                "Git 설치 확인",
                f"✅ Git이 정상적으로 설치되어 동기화 준비가 완료되었습니다!\n\n"
                f"• 감지된 경로:\n  {self.git_engine.git_path}\n\n"
                f"• 상태: 정상 작동 중"
            )
        else:
            self._install_git_clicked()

    def _set_git_ready(self, is_ready):
        state = "normal" if is_ready else "disabled"
        if hasattr(self, "sync_btn"):
            self.sync_btn.configure(state=state)
            self.pull_btn.configure(state=state)
            self.push_btn.configure(state=state)

    def _install_git_clicked(self):
        if not is_winget_available():
            messagebox.showinfo(
                "안내",
                "이 컴퓨터에는 winget 패키지 관리자가 설치되어 있지 않습니다.\n공식 Git 다운로드 웹페이지로 이동합니다."
            )
            webbrowser.open("https://git-scm.com/download/win")
            return

        self.install_git_btn.configure(state="disabled", text="Git 설치 진행 중...")
        self.progress_bar.start()
        self._log("⚡ [Git 자동 설치] 설치 프로세스를 시작합니다. 1~2분 정도 소요될 수 있습니다...")

        def _worker():
            def safe_log(msg):
                self.after(0, lambda: self._log(msg))

            ok, res = install_git_via_winget(logger=safe_log)
            self.after(0, lambda: self._on_git_install_finished(ok, res))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_git_install_finished(self, ok, res):
        self.progress_bar.stop()
        self.progress_bar.set(0)
        self.install_git_btn.configure(state="normal", text="⚡ Git 원클릭 자동 설치")

        if ok:
            self.git_engine.refresh_git_path()
            self._check_git_status()
            messagebox.showinfo(
                "설치 완료",
                "🎉 Git 설치가 성공적으로 완료되었습니다!\n이제 동기화 기능을 자유롭게 사용하실 수 있습니다."
            )
        else:
            self._log(f"❌ Git 설치 실패: {res}")
            res_box = messagebox.askyesno(
                "설치 안내",
                f"자동 설치 중 문제가 발생했습니다:\n{res}\n\n공식 Git 웹사이트에서 직접 다운로드하시겠습니까?"
            )
            if res_box:
                webbrowser.open("https://git-scm.com/download/win")

    # 스마트 동기화 상태 감지
    def _trigger_inspect_status(self):
        if self.is_syncing:
            return

        local_folder = self.folder_entry.get().strip() if hasattr(self, "folder_entry") else ""
        raw_repo_url = self._get_selected_repo_url() if hasattr(self, "repo_combo") else ""
        token = self.token_entry.get().strip() if hasattr(self, "token_entry") else ""
        username = self.username_entry.get().strip() if hasattr(self, "username_entry") else ""
        branch = self._get_selected_branch() if hasattr(self, "_get_selected_branch") else "main"

        if not local_folder or not os.path.isdir(local_folder):
            self._update_status_ui("NO_SETUP", "폴더 미선택", "동기화할 컴퓨터 폴더를 선택해주세요.", False)
            return

        if not raw_repo_url or not token:
            self._update_status_ui("NO_SETUP", "저장소 연결 필요", "GitHub 계정 연결 및 저장소를 선택해주세요.", False)
            return

        auth_url = GitEngine.build_authenticated_url(raw_repo_url, username, token)

        self.status_title_lbl.configure(text="🔍 동기화 상태 확인 중...", text_color=("#334155", "#94a3b8"))
        self.status_desc_lbl.configure(text="GitHub과 로컬의 최신 변경사항을 비교하고 있습니다.")
        self.status_refresh_btn.configure(state="disabled", text="확인 중...")

        def _worker():
            try:
                code, title, desc, has_new = self.git_engine.inspect_sync_status(local_folder, auth_url, branch)
                self.after(0, lambda: self._update_status_ui(code, title, desc, has_new))
            except Exception as e:
                self.after(0, lambda: self._update_status_ui("ERROR", "확인 실패", f"오류: {str(e)}", False))

        threading.Thread(target=_worker, daemon=True).start()

    def _update_status_ui(self, code, title, desc, has_remote_new):
        self.status_refresh_btn.configure(state="normal", text="🔄 상태 새로고침")

        if code == "BEHIND":
            self.sync_status_banner.configure(
                fg_color=("#eff6ff", "#172554"),
                border_color=("#93c5fd", "#1d4ed8")
            )
            self.status_title_lbl.configure(text=f"🔔 {title}", text_color=("#1d4ed8", "#93c5fd"))
            self.status_desc_lbl.configure(text=desc, text_color=("#2563eb", "#bfdbfe"))
            self.status_quick_pull_btn.pack(side="left", padx=(0, 8))
            self.status_quick_pull_btn.configure(
                text="⬇️ 지금 바로 내려받기",
                fg_color="#0969da",
                hover_color="#0860ca",
                command=lambda: self._start_git_task("pull")
            )

        elif code == "UP_TO_DATE":
            self.status_quick_pull_btn.pack_forget()
            self.sync_status_banner.configure(
                fg_color=("#f0fdf4", "#052e16"),
                border_color=("#86efac", "#15803d")
            )
            self.status_title_lbl.configure(text=f"✅ {title}", text_color=("#15803d", "#86efac"))
            self.status_desc_lbl.configure(text=desc, text_color=("#16a34a", "#bbf7d0"))

        elif code in ("LOCAL_MODIFIED", "AHEAD"):
            self.status_quick_pull_btn.pack_forget()
            self.sync_status_banner.configure(
                fg_color=("#eef2ff", "#1e1b4b"),
                border_color=("#a5b4fc", "#4338ca")
            )
            self.status_title_lbl.configure(text=f"⬆️ {title}", text_color=("#4338ca", "#a5b4fc"))
            self.status_desc_lbl.configure(text=desc, text_color=("#4f46e5", "#c7d2fe"))

        elif code == "DIVERGED":
            self.sync_status_banner.configure(
                fg_color=("#fffbeb", "#451a03"),
                border_color=("#fde68a", "#b45309")
            )
            self.status_title_lbl.configure(text=f"⚠️ {title}", text_color=("#b45309", "#fde68a"))
            self.status_desc_lbl.configure(text=desc, text_color=("#92400e", "#fef3c7"))
            self.status_quick_pull_btn.pack(side="left", padx=(0, 8))
            self.status_quick_pull_btn.configure(
                text="🚀 지금 전체 동기화",
                fg_color="#d97706",
                hover_color="#b45309",
                command=lambda: self._start_git_task("sync")
            )

        else:
            self.status_quick_pull_btn.pack_forget()
            self.sync_status_banner.configure(
                fg_color=("#f8fafc", "#0f172a"),
                border_color=("#e2e8f0", "#1e293b")
            )
            self.status_title_lbl.configure(text=f"ℹ️ {title}", text_color=("#475569", "#cbd5e1"))
            self.status_desc_lbl.configure(text=desc, text_color=("#64748b", "#94a3b8"))

    # 다중 프로필 관리
    def _on_profile_change(self, new_profile):
        old_profile = self.config_data.get("active_profile", "기본 작업")
        if old_profile in self.config_data.get("profiles", {}):
            self.config_data["profiles"][old_profile]["local_folder"] = self.folder_entry.get().strip()
            self.config_data["profiles"][old_profile]["selected_repo"] = self.repo_combo.get().strip()
            self.config_data["profiles"][old_profile]["branch"] = self._get_selected_branch()

        self.config_data["active_profile"] = new_profile
        new_data = self.config_data["profiles"].get(new_profile, {})

        self.folder_entry.delete(0, "end")
        if new_data.get("local_folder"):
            self.folder_entry.insert(0, new_data["local_folder"])

        saved_repo = new_data.get("selected_repo", "")
        if saved_repo:
            matched = False
            vals = self.repo_combo.cget("values")
            for v in vals:
                if saved_repo.split()[0] in v:
                    self.repo_combo.set(v)
                    matched = True
                    break
            if not matched and vals:
                self.repo_combo.set(saved_repo)
        elif self.repos_list:
            self._update_repo_combobox()

        self._save_current_settings()
        self._log(f"📁 프로필이 전환되었습니다: '{new_profile}'")
        self._trigger_inspect_status()

    def _add_profile(self):
        dialog = ctk.CTkInputDialog(
            text="새 동기화 프로필 이름을 입력하세요:\n(예: 회사 문서, 블로그, 개인 프로젝트)",
            title="새 프로필 추가"
        )
        name = dialog.get_input()
        if not name or not name.strip():
            return
        name = name.strip()

        if "profiles" not in self.config_data:
            self.config_data["profiles"] = {}

        if name in self.config_data["profiles"]:
            messagebox.showwarning("중복", f"'{name}' 프로필이 이미 존재합니다.")
            return

        curr = self.config_data.get("active_profile", "기본 작업")
        if curr in self.config_data["profiles"]:
            self.config_data["profiles"][curr]["local_folder"] = self.folder_entry.get().strip()
            self.config_data["profiles"][curr]["selected_repo"] = self.repo_combo.get().strip()
            self.config_data["profiles"][curr]["branch"] = self._get_selected_branch()

        self.config_data["profiles"][name] = {
            "local_folder": "",
            "selected_repo": "",
            "branch": "main"
        }
        self.config_data["active_profile"] = name

        p_names = list(self.config_data["profiles"].keys())
        self.profile_combo.configure(values=p_names)
        self.profile_combo.set(name)

        self.folder_entry.delete(0, "end")
        if self.repos_list:
            self._update_repo_combobox()

        self._save_current_settings()
        self._log(f"➕ 새 프로필이 생성되었습니다: '{name}'")
        self._trigger_inspect_status()

    def _rename_profile(self):
        curr = self.profile_combo.get().strip()
        if not curr:
            return

        dialog = ctk.CTkInputDialog(
            text=f"현재 선택된 '{curr}' 프로필의 새 이름을 입력하세요:",
            title="프로필 이름 변경"
        )
        new_name = dialog.get_input()
        if not new_name or not new_name.strip():
            return
        new_name = new_name.strip()

        if new_name == curr:
            return

        if "profiles" not in self.config_data:
            self.config_data["profiles"] = {}

        if new_name in self.config_data["profiles"]:
            messagebox.showwarning("중복", f"'{new_name}' 프로필이 이미 존재합니다.")
            return

        # 기존 프로필 데이터 유지하면서 키 이름 변경
        curr_data = self.config_data["profiles"].pop(curr, {
            "local_folder": self.folder_entry.get().strip(),
            "selected_repo": self.repo_combo.get().strip(),
            "branch": self._get_selected_branch()
        })
        curr_data["local_folder"] = self.folder_entry.get().strip()
        curr_data["selected_repo"] = self.repo_combo.get().strip()
        curr_data["branch"] = self._get_selected_branch()

        self.config_data["profiles"][new_name] = curr_data
        self.config_data["active_profile"] = new_name

        p_names = list(self.config_data["profiles"].keys())
        self.profile_combo.configure(values=p_names)
        self.profile_combo.set(new_name)

        self._save_current_settings()
        self._log(f"✏️ 프로필 이름이 '{curr}'에서 '{new_name}'(으)로 변경되었습니다.")

    def _delete_profile(self):
        profiles = self.config_data.get("profiles", {})
        if len(profiles) <= 1:
            messagebox.showwarning("삭제 불가", "최소 1개 이상의 프로필이 유지되어야 하므로 삭제할 수 없습니다.")
            return

        active = self.profile_combo.get().strip()
        ans = messagebox.askyesno(
            "프로필 삭제 확인",
            f"'{active}' 프로필 설정을 정말 삭제하시겠습니까?\n\n(실제 컴퓨터 폴더나 GitHub 저장소의 파일은 삭제되지 않습니다.)"
        )
        if not ans:
            return

        if active in self.config_data["profiles"]:
            del self.config_data["profiles"][active]

        remaining = list(self.config_data["profiles"].keys())
        new_active = remaining[0]
        self.config_data["active_profile"] = new_active

        self.profile_combo.configure(values=remaining)
        self.profile_combo.set(new_active)

        new_data = self.config_data["profiles"][new_active]
        self.folder_entry.delete(0, "end")
        if new_data.get("local_folder"):
            self.folder_entry.insert(0, new_data["local_folder"])

        saved_repo = new_data.get("selected_repo", "")
        if saved_repo:
            self.repo_combo.set(saved_repo)

        self._save_current_settings()
        self._log(f"🗑️ 프로필 '{active}'이(가) 삭제되었습니다. '{new_active}'(으)로 전환되었습니다.")
        self._trigger_inspect_status()

    # 설정 불러오기 및 저장
    def _load_saved_settings(self):
        c = self.config_data
        if c.get("username"):
            self.username_entry.insert(0, c["username"])
        if c.get("token") and c.get("remember_token", True):
            self.token_entry.insert(0, c["token"])

        self.remember_var.set(c.get("remember_token", True))
        self.tray_var.set(c.get("minimize_to_tray", True))
        self.autostart_var.set(win_autostart.is_autostart_enabled())

        if c.get("auto_sync_interval"):
            self.interval_combo.set(f"{c['auto_sync_interval']}분")

        # 프로필 로드
        profiles = c.get("profiles", {})
        if not profiles:
            profiles = {"기본 작업": {"local_folder": "", "selected_repo": "", "branch": "main"}}
            c["profiles"] = profiles

        p_names = list(profiles.keys())
        self.profile_combo.configure(values=p_names)

        active = c.get("active_profile", p_names[0])
        if active not in profiles:
            active = p_names[0]
        self.profile_combo.set(active)

        active_data = profiles[active]
        if active_data.get("local_folder"):
            self.folder_entry.insert(0, active_data["local_folder"])

        # 토큰이 저장되어 있다면 백그라운드 자동 연결
        if c.get("token"):
            self.after(500, self._on_click_connect)

        self.after(1500, self._trigger_inspect_status)

        # 3초 후 백그라운드 새 버전 업데이트 확인
        self.after(3000, self._check_update_in_background)

    def _save_current_settings(self):
        interval_str = self.interval_combo.get().replace("분", "").strip()
        try:
            interval_val = int(interval_str)
        except ValueError:
            interval_val = 10

        active_p = self.profile_combo.get().strip() if hasattr(self, "profile_combo") else "기본 작업"
        if "profiles" not in self.config_data:
            self.config_data["profiles"] = {}

        if active_p in self.config_data["profiles"]:
            self.config_data["profiles"][active_p]["local_folder"] = self.folder_entry.get().strip() if hasattr(self, "folder_entry") else ""
            self.config_data["profiles"][active_p]["selected_repo"] = self.repo_combo.get().strip() if hasattr(self, "repo_combo") else ""
            self.config_data["profiles"][active_p]["branch"] = self._get_selected_branch()

        c = {
            "username": self.username_entry.get().strip() if hasattr(self, "username_entry") else "",
            "token": self.token_entry.get().strip() if hasattr(self, "token_entry") else "",
            "remember_token": self.remember_var.get() if hasattr(self, "remember_var") else True,
            "minimize_to_tray": self.tray_var.get() if hasattr(self, "tray_var") else True,
            "autostart": self.autostart_var.get() if hasattr(self, "autostart_var") else False,
            "auto_sync_enabled": self.auto_sync_var.get() if hasattr(self, "auto_sync_var") else False,
            "auto_sync_interval": interval_val,
            "active_profile": active_p,
            "profiles": self.config_data["profiles"]
        }
        self.config_data = c
        save_config(c)

    def _on_toggle_autostart(self):
        val = self.autostart_var.get()
        ok = win_autostart.set_autostart(val)
        if ok:
            self._log(f"🚀 윈도우 시작 시 자동 실행이 {'활성화' if val else '비활성화'}되었습니다.")
        else:
            self._log("⚠️ 윈도우 시작 레지스트리 설정 변경에 실패했습니다.")
        self._save_current_settings()

    # 시스템 트레이
    def _setup_tray_icon(self):
        try:
            if os.path.exists(self.icon_path):
                img = Image.open(self.icon_path)
            else:
                img = Image.new("RGBA", (64, 64), color=(59, 130, 246))

            menu = pystray.Menu(
                item("깃싱크 열기", lambda: self.after(0, self._restore_from_tray), default=True),
                item("원클릭 전체 동기화 실행", lambda: self.after(0, lambda: self._start_git_task("sync"))),
                pystray.Menu.SEPARATOR,
                item("프로그램 종료", lambda: self.after(0, self._quit_app))
            )
            self.tray_icon = pystray.Icon("GitSync", img, APP_WINDOW_TITLE, menu)
            threading.Thread(target=self.tray_icon.run, daemon=True).start()
        except Exception as e:
            print(f"시스템 트레이 초기화 실패: {e}")

    def _on_close_window(self):
        if self.tray_var.get():
            self.withdraw()
            if self.tray_icon and self._first_tray_notify:
                self._first_tray_notify = False
                try:
                    self.tray_icon.notify(
                        "깃싱크가 시스템 트레이(시계 옆)에서 계속 실행 중입니다.\n아이콘을 더블클릭하면 다시 열립니다.",
                        "깃싱크 (GitSync)"
                    )
                except Exception:
                    pass
        else:
            self._quit_app()

    def _restore_from_tray(self):
        self.deiconify()
        self.state("normal")
        self.lift()
        self.focus_force()

    def _quit_app(self):
        if self.tray_icon:
            try:
                self.tray_icon.visible = False
                self.tray_icon.stop()
            except Exception:
                pass
        self.destroy()
        sys.exit(0)

    # 새 버전 업데이트 알림
    def _check_update_in_background(self):
        token = self.token_entry.get().strip() if hasattr(self, "token_entry") else ""
        repo_url = self._get_selected_repo_url()
        repo_name = "izax8839/gith"
        if repo_url and "github.com/" in repo_url:
            parts = repo_url.split("github.com/")[-1].replace(".git", "").split("/")
            if len(parts) >= 2:
                repo_name = f"{parts[0]}/{parts[1]}"

        def _worker():
            ok, release = GitHubAPI.check_latest_release(token, repo_name)
            if ok and release:
                tag = release.get("tag_name", "").strip()
                if tag and is_newer_version(tag, APP_VERSION):
                    self.after(0, lambda: self._show_update_banner(release))

        threading.Thread(target=_worker, daemon=True).start()

    def _show_update_banner(self, release):
        tag = release.get("tag_name", "새 버전")
        url = release.get("html_url", "")
        self.update_msg_lbl.configure(text=f"🎉 새로운 버전({tag})이 출시되었습니다! 최신 기능과 개선사항을 받아보세요.")
        self.update_download_btn.configure(command=lambda: webbrowser.open(url))
        self.update_banner_frame.grid(row=1, column=0, padx=22, pady=(0, 6), sticky="ew")

    def _manual_check_update(self):
        token = self.token_entry.get().strip() if hasattr(self, "token_entry") else ""
        self._log("🔍 최신 버전 업데이트를 확인하는 중...")
        def _worker():
            ok, release = GitHubAPI.check_latest_release(token, "izax8839/gith")
            if ok and release:
                tag = release.get("tag_name", "").strip()
                if tag and is_newer_version(tag, APP_VERSION):
                    self.after(0, lambda: self._show_update_banner(release))
                    self.after(0, lambda: messagebox.showinfo("새 버전 발견", f"새로운 버전({tag})이 있습니다!\n상단 다운로드 배너를 확인하세요."))
                    return
            self.after(0, lambda: messagebox.showinfo("최신 버전", f"현재 최신 버전({APP_VERSION})을 사용하고 계십니다!"))

        threading.Thread(target=_worker, daemon=True).start()

    # 계정 연결
    def _on_click_connect(self):
        token = self.token_entry.get().strip()
        if not token:
            self.account_status_lbl.configure(text="❌ 토큰을 입력해주세요.", text_color="#dc2626")
            return

        self.connect_btn.configure(state="disabled", text="확인 중...")
        self.account_status_lbl.configure(text="⏳ GitHub 연결을 확인하고 저장소 목록을 조회하는 중...", text_color="#2563eb")

        def _task():
            ok, user_res = GitHubAPI.test_connection(token)
            if not ok:
                self.after(0, lambda: self._on_connect_failed(user_res))
                return

            ok_repo, repos_res = GitHubAPI.get_user_repos(token)
            self.after(0, lambda: self._on_connect_success(user_res, repos_res if ok_repo else []))

        threading.Thread(target=_task, daemon=True).start()

    def _on_connect_failed(self, error_msg):
        self.connect_btn.configure(state="normal", text="🔗 연결 & 저장소 불러오기")
        self.account_status_lbl.configure(text=f"❌ {error_msg}", text_color="#dc2626")
        self._log(f"계정 연결 실패: {error_msg}")

    def _on_connect_success(self, user_info, repos):
        self.connect_btn.configure(state="normal", text="🔗 연결 & 저장소 불러오기")
        uname = user_info.get("login", "")
        name = user_info.get("name") or uname

        if not self.username_entry.get().strip():
            self.username_entry.delete(0, "end")
            self.username_entry.insert(0, uname)

        self.account_status_lbl.configure(
            text=f"✅ 로그인 성공: {name} (@{uname}) | 총 저장소 {len(repos)}개 조회됨",
            text_color="#16a34a"
        )
        self._log(f"GitHub 계정 연결 성공! 로그인 ID: {uname} ({name})")

        self.repos_list = repos
        self._update_repo_combobox()
        self._save_current_settings()
        self.after(500, self._trigger_inspect_status)

    def _update_repo_combobox(self):
        if not self.repos_list:
            self.repo_combo.configure(values=["[저장소가 없습니다. 새 저장소를 만들어보세요]"])
            return

        names = [f"{r['full_name']} {'(🔒비공개)' if r.get('private') else '(🌐공개)'}" for r in self.repos_list]
        self.repo_combo.configure(values=names)

        active = self.config_data.get("active_profile", "기본 작업")
        saved = self.config_data.get("profiles", {}).get(active, {}).get("selected_repo", "")
        matched = False
        if saved:
            for item in names:
                if saved.split()[0] in item:
                    self.repo_combo.set(item)
                    matched = True
                    break
        if not matched and names:
            self.repo_combo.set(names[0])

    def _on_repo_selected(self, choice):
        self._save_current_settings()
        self._log(f"선택된 저장소: {choice}")
        self._trigger_inspect_status()

    def _get_selected_repo_url(self):
        choice = self.repo_combo.get().strip()
        if not choice or choice.startswith("["):
            return None

        clean_name = choice.split()[0]
        for r in self.repos_list:
            if r.get("full_name") == clean_name:
                return r.get("clone_url") or r.get("html_url")

        if clean_name.startswith("http://") or clean_name.startswith("https://"):
            return clean_name
        return f"https://github.com/{clean_name}.git"

    def _get_selected_branch(self):
        choice = self.repo_combo.get().strip()
        if choice and not choice.startswith("["):
            clean_name = choice.split()[0]
            for r in self.repos_list:
                if r.get("full_name") == clean_name:
                    return r.get("default_branch") or "main"
        return "main"

    def _set_ui_syncing_state(self, is_syncing):
        self.is_syncing = is_syncing
        state = "disabled" if is_syncing else "normal"
        self.sync_btn.configure(state=state)
        self.pull_btn.configure(state=state)
        self.push_btn.configure(state=state)
        self.connect_btn.configure(state=state)

        if is_syncing:
            self.progress_bar.start()
        else:
            self.progress_bar.stop()
            self.progress_bar.set(0)

    # 동기화 실행 메인 (100MB 사전 감지 포함)
    def _start_git_task(self, task_type):
        if self.is_syncing:
            messagebox.showinfo("알림", "이미 동기화 작업이 진행 중입니다.")
            return

        local_folder = self.folder_entry.get().strip()
        if not local_folder or not os.path.isdir(local_folder):
            messagebox.showerror("오류", "유효한 컴퓨터 폴더를 선택해주세요.")
            return

        raw_repo_url = self._get_selected_repo_url()
        if not raw_repo_url:
            messagebox.showerror("오류", "동기화할 GitHub 저장소를 선택하거나 입력해주세요.")
            return

        token = self.token_entry.get().strip()
        if not token:
            messagebox.showerror("오류", "GitHub 토큰을 입력해주세요.")
            return

        # 100MB 대용량 파일 사전 감지 (sync, push 작업 시)
        if task_type in ("sync", "push"):
            large_files = self.git_engine.check_large_files(local_folder, max_size_mb=98)
            if large_files:
                def on_ignore():
                    rel_paths = [f["rel_path"] for f in large_files]
                    self.git_engine.ignore_large_files(local_folder, rel_paths)
                    self._log(f"⚡ 100MB 초과 파일 {len(large_files)}개를 .gitignore에 등록하여 안전하게 제외했습니다.")
                    self._run_actual_git_task(task_type, local_folder, raw_repo_url, token)

                def on_cancel():
                    self._log("⚠️ 100MB 초과 파일 감지로 인해 동기화 작업이 취소되었습니다.")

                LargeFileDialog(self, large_files, on_ignore, on_cancel)
                return

        self._run_actual_git_task(task_type, local_folder, raw_repo_url, token)

    def _run_actual_git_task(self, task_type, local_folder, raw_repo_url, token):
        username = self.username_entry.get().strip()
        branch = self._get_selected_branch()
        auth_url = GitEngine.build_authenticated_url(raw_repo_url, username, token)

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        user_title = self.commit_msg_entry.get().strip() if hasattr(self, "commit_msg_entry") else ""
        if user_title:
            commit_msg = f"[{now_str}] {user_title}"
        else:
            commit_msg = f"[{now_str}] 컴퓨터 파일 동기화"

        self._save_current_settings()
        self._set_ui_syncing_state(True)

        def _worker():
            try:
                def safe_log(msg):
                    self.after(0, lambda: self._log(msg))

                if task_type == "sync":
                    ok, msg = self.git_engine.sync(
                        folder_path=local_folder,
                        auth_url=auth_url,
                        branch=branch,
                        commit_msg=commit_msg,
                        username=username,
                        logger=safe_log
                    )
                elif task_type == "pull":
                    self.git_engine.init_and_set_remote(local_folder, auth_url, branch, username)
                    ok, msg = self.git_engine.pull(local_folder, branch, logger=safe_log)
                elif task_type == "push":
                    self.git_engine.init_and_set_remote(local_folder, auth_url, branch, username)
                    ok, msg = self.git_engine.push(local_folder, branch, commit_msg=commit_msg, logger=safe_log)

                self.after(0, lambda: self._on_git_task_finished(task_type, ok, msg))
            except Exception as e:
                self.after(0, lambda: self._on_git_task_finished(task_type, False, f"예외 오류: {str(e)}"))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_git_task_finished(self, task_type, ok, msg):
        self._set_ui_syncing_state(False)
        task_names = {"sync": "전체 동기화", "pull": "내려받기", "push": "올리기"}
        tname = task_names.get(task_type, "작업")

        if ok:
            if hasattr(self, "commit_msg_entry"):
                self.commit_msg_entry.delete(0, "end")
            self._log(f"🎉 {tname} 작업이 성공적으로 완료되었습니다!")
        else:
            self._log(f"❌ {tname} 실패: {msg}")
            messagebox.showerror(f"{tname} 오류", f"작업 중 오류가 발생했습니다:\n\n{msg}")

        self.after(500, self._trigger_inspect_status)

    # 주기적 자동 동기화
    def _on_toggle_auto_sync(self):
        enabled = self.auto_sync_var.get()
        self._save_current_settings()
        if enabled:
            interval_str = self.interval_combo.get().replace("분", "").strip()
            self._log(f"⏱️ 자동 동기화가 활성화되었습니다. ({interval_str}분 간격)")
            self._schedule_next_auto_sync()
        else:
            if self.auto_sync_timer:
                self.after_cancel(self.auto_sync_timer)
                self.auto_sync_timer = None
            self.auto_status_lbl.configure(text="")
            self._log("⏱️ 자동 동기화가 비활성화되었습니다.")

    def _schedule_next_auto_sync(self):
        if not self.auto_sync_var.get():
            return

        interval_str = self.interval_combo.get().replace("분", "").strip()
        try:
            mins = int(interval_str)
        except ValueError:
            mins = 10

        ms = mins * 60 * 1000
        self.auto_status_lbl.configure(text=f"다음 자동 동기화: {mins}분 후")
        self.auto_sync_timer = self.after(ms, self._run_auto_sync)

    def _run_auto_sync(self):
        if not self.auto_sync_var.get():
            return

        self._log("⏱️ [자동 동기화] 주기적 동기화 작업을 시작합니다...")
        if not self.is_syncing:
            self._start_git_task("sync")
        self._schedule_next_auto_sync()


def check_single_instance():
    """
    프로그램이 중복 실행되지 않도록 Windows Mutex를 확인합니다.
    이미 실행 중이면 기존 창을 맨 앞으로 띄우고 새 실행을 방지합니다.
    """
    if os.name != "nt":
        return None

    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32

        mutex = kernel32.CreateMutexW(None, False, APP_MUTEX_NAME)
        ERROR_ALREADY_EXISTS = 183

        if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            hwnd = user32.FindWindowW(None, APP_WINDOW_TITLE)
            if hwnd:
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE (9)
                user32.SetForegroundWindow(hwnd)
            return False

        return mutex
    except Exception:
        return None


def main():
    mutex = check_single_instance()
    if mutex is False:
        sys.exit(0)

    app = GitSyncApp()
    app.mainloop()

if __name__ == "__main__":
    main()
