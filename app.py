import os
import sys
import threading
import time
import webbrowser
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

from config_manager import load_config, save_config
from github_api import GitHubAPI
from git_engine import GitEngine, find_git_executable

# 기본 테마 설정
ctk.set_appearance_mode("System")  # System, Dark, Light
ctk.set_default_color_theme("blue")

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
        # repo 권한이 미리 체크된 URL
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


class GitSyncApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # 작업표시줄 아이콘 분리 설정 (Windows)
        try:
            import ctypes
            myappid = "gitsync.desktop.app.1.0"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass

        self.title("깃싱크 (GitSync) - 초간편 한글 GitHub 폴더 동기화")
        self.geometry("820x820")
        self.minsize(780, 750)

        # 창 아이콘 설정
        if getattr(sys, "frozen", False):
            base_dir = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))

        icon_path = os.path.join(base_dir, "app_icon.ico")
        if not os.path.exists(icon_path):
            icon_path = os.path.join(os.path.dirname(sys.executable), "app_icon.ico")

        if os.path.exists(icon_path):
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass

        self.config_data = load_config()
        self.git_engine = GitEngine()
        self.repos_list = []  # GitHub에서 가져온 저장소 목록
        self.is_syncing = False
        self.auto_sync_timer = None

        self._build_ui()
        self._load_saved_settings()
        self._check_git_status()

    def _build_ui(self):
        # 메인 스크롤 프레임 또는 단일 프레임
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        # 1. 헤더 영역
        header_frame = ctk.CTkFrame(self, corner_radius=10)
        header_frame.grid(row=0, column=0, padx=15, pady=(15, 8), sticky="ew")
        header_frame.grid_columnconfigure(1, weight=1)

        logo_lbl = ctk.CTkLabel(
            header_frame,
            text="🐙 깃싱크 (GitSync)",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        logo_lbl.grid(row=0, column=0, padx=15, pady=(10, 2), sticky="w")

        sub_lbl = ctk.CTkLabel(
            header_frame,
            text="내 컴퓨터의 폴더와 GitHub 저장소를 클릭 한 번으로 편하게 동기화합니다.",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        sub_lbl.grid(row=1, column=0, padx=15, pady=(0, 10), sticky="w")

        # 테마 스위치
        self.theme_btn = ctk.CTkSegmentedButton(
            header_frame,
            values=["시스템", "다크", "라이트"],
            command=self._change_theme
        )
        self.theme_btn.set("시스템")
        self.theme_btn.grid(row=0, column=2, rowspan=2, padx=15, pady=10, sticky="e")

        # 2. 계정 설정 영역 (Card 1)
        acc_frame = ctk.CTkFrame(self, corner_radius=10)
        acc_frame.grid(row=1, column=0, padx=15, pady=6, sticky="ew")
        acc_frame.grid_columnconfigure(1, weight=1)

        acc_title = ctk.CTkLabel(
            acc_frame,
            text="1. GitHub 계정 연결",
            font=ctk.CTkFont(size=15, weight="bold")
        )
        acc_title.grid(row=0, column=0, columnspan=3, padx=15, pady=(10, 5), sticky="w")

        # 사용자명
        ctk.CTkLabel(acc_frame, text="GitHub 아이디:", font=ctk.CTkFont(size=12)).grid(row=1, column=0, padx=15, pady=4, sticky="w")
        self.username_entry = ctk.CTkEntry(acc_frame, placeholder_text="GitHub 사용자 이름 (예: myid)")
        self.username_entry.grid(row=1, column=1, padx=(0, 10), pady=4, sticky="ew")

        # 토큰 발급 가이드 버튼
        guide_btn = ctk.CTkButton(
            acc_frame,
            text="🔑 토큰 발급 가이드",
            width=130,
            fg_color="#6f42c1",
            hover_color="#5a32a3",
            command=self._show_token_guide
        )
        guide_btn.grid(row=1, column=2, padx=(0, 15), pady=4, sticky="e")

        # 토큰 입력창 (비밀번호 대체)
        ctk.CTkLabel(acc_frame, text="개인 토큰 (비밀번호):", font=ctk.CTkFont(size=12)).grid(row=2, column=0, padx=15, pady=4, sticky="w")
        
        token_subframe = ctk.CTkFrame(acc_frame, fg_color="transparent")
        token_subframe.grid(row=2, column=1, padx=(0, 10), pady=4, sticky="ew")
        token_subframe.grid_columnconfigure(0, weight=1)

        self.token_entry = ctk.CTkEntry(token_subframe, placeholder_text="ghp_로 시작하는 개인 액세스 토큰 붙여넣기", show="*")
        self.token_entry.grid(row=0, column=0, sticky="ew")

        self.show_token_btn = ctk.CTkButton(
            token_subframe,
            text="👁️",
            width=35,
            fg_color="gray",
            hover_color="darkgray",
            command=self._toggle_token_visibility
        )
        self.show_token_btn.grid(row=0, column=1, padx=(5, 0))

        # 연결 테스트 및 저장소 불러오기 버튼
        self.connect_btn = ctk.CTkButton(
            acc_frame,
            text="🔗 연결 & 저장소 불러오기",
            width=150,
            command=self._on_click_connect
        )
        self.connect_btn.grid(row=2, column=2, padx=(0, 15), pady=4, sticky="e")

        # 계정 상태 문구 및 저장 옵션
        status_row = ctk.CTkFrame(acc_frame, fg_color="transparent")
        status_row.grid(row=3, column=0, columnspan=3, padx=15, pady=(6, 10), sticky="ew")
        status_row.grid_columnconfigure(0, weight=1)

        self.account_status_lbl = ctk.CTkLabel(
            status_row,
            text="⚠️ GitHub 토큰을 입력하고 [연결 & 저장소 불러오기]를 눌러주세요.",
            font=ctk.CTkFont(size=12),
            text_color="#d97706"
        )
        self.account_status_lbl.grid(row=0, column=0, sticky="w")

        self.remember_var = ctk.BooleanVar(value=True)
        self.remember_chk = ctk.CTkCheckBox(
            status_row,
            text="토큰 및 설정 자동 저장",
            font=ctk.CTkFont(size=12),
            variable=self.remember_var,
            command=self._save_current_settings
        )
        self.remember_chk.grid(row=0, column=1, sticky="e")

        # 3. 동기화 대상 설정 (Card 2)
        target_frame = ctk.CTkFrame(self, corner_radius=10)
        target_frame.grid(row=2, column=0, padx=15, pady=6, sticky="ew")
        target_frame.grid_columnconfigure(1, weight=1)

        target_title = ctk.CTkLabel(
            target_frame,
            text="2. 동기화 대상 설정 (내 컴퓨터 폴더 ↔ GitHub 저장소)",
            font=ctk.CTkFont(size=15, weight="bold")
        )
        target_title.grid(row=0, column=0, columnspan=3, padx=15, pady=(10, 5), sticky="w")

        # 로컬 폴더
        ctk.CTkLabel(target_frame, text="내 컴퓨터 폴더:", font=ctk.CTkFont(size=12)).grid(row=1, column=0, padx=15, pady=4, sticky="w")
        self.folder_entry = ctk.CTkEntry(target_frame, placeholder_text="동기화할 컴퓨터 폴더 경로 (예: C:\\Users\\...\\Desktop\\내폴더)")
        self.folder_entry.grid(row=1, column=1, padx=(0, 10), pady=4, sticky="ew")

        folder_btn_row = ctk.CTkFrame(target_frame, fg_color="transparent")
        folder_btn_row.grid(row=1, column=2, padx=(0, 15), pady=4, sticky="e")

        browse_btn = ctk.CTkButton(folder_btn_row, text="📁 폴더 선택...", width=95, command=self._browse_folder)
        browse_btn.pack(side="left", padx=(0, 4))

        open_folder_btn = ctk.CTkButton(folder_btn_row, text="📂 열기", width=50, fg_color="gray", hover_color="darkgray", command=self._open_local_folder)
        open_folder_btn.pack(side="left")

        # GitHub 저장소
        ctk.CTkLabel(target_frame, text="GitHub 저장소:", font=ctk.CTkFont(size=12)).grid(row=2, column=0, padx=15, pady=4, sticky="w")
        
        self.repo_combo = ctk.CTkComboBox(
            target_frame,
            values=["[계정을 연결하여 저장소 목록을 불러오세요]"],
            command=self._on_repo_selected
        )
        self.repo_combo.grid(row=2, column=1, padx=(0, 10), pady=4, sticky="ew")

        repo_btn_row = ctk.CTkFrame(target_frame, fg_color="transparent")
        repo_btn_row.grid(row=2, column=2, padx=(0, 15), pady=4, sticky="e")

        new_repo_btn = ctk.CTkButton(
            repo_btn_row,
            text="➕ 새 저장소",
            width=95,
            fg_color="#1f883d",
            hover_color="#1a7f37",
            command=self._open_new_repo_dialog
        )
        new_repo_btn.pack(side="left", padx=(0, 4))

        open_repo_web_btn = ctk.CTkButton(
            repo_btn_row,
            text="🌐 웹",
            width=50,
            fg_color="gray",
            hover_color="darkgray",
            command=self._open_repo_in_browser
        )
        open_repo_web_btn.pack(side="left")

        # 세부 옵션 (브랜치명, 커밋 안내)
        detail_row = ctk.CTkFrame(target_frame, fg_color="transparent")
        detail_row.grid(row=3, column=0, columnspan=3, padx=15, pady=(4, 10), sticky="ew")
        
        ctk.CTkLabel(detail_row, text="기본 브랜치:", font=ctk.CTkFont(size=11), text_color="gray").pack(side="left")
        self.branch_entry = ctk.CTkEntry(detail_row, width=80, height=24, font=ctk.CTkFont(size=11))
        self.branch_entry.insert(0, "main")
        self.branch_entry.pack(side="left", padx=(5, 20))

        # 4. 동기화 실행 및 자동화 영역 (Card 3)
        action_frame = ctk.CTkFrame(self, corner_radius=10)
        action_frame.grid(row=3, column=0, padx=15, pady=6, sticky="nsew")
        action_frame.grid_columnconfigure(0, weight=1)
        action_frame.grid_columnconfigure(1, weight=1)
        action_frame.grid_columnconfigure(2, weight=1)
        action_frame.grid_rowconfigure(3, weight=1)

        action_title = ctk.CTkLabel(
            action_frame,
            text="3. 동기화 실행",
            font=ctk.CTkFont(size=15, weight="bold")
        )
        action_title.grid(row=0, column=0, columnspan=3, padx=15, pady=(10, 5), sticky="w")

        # 3대 동기화 버튼
        self.sync_btn = ctk.CTkButton(
            action_frame,
            text="🚀 원클릭 전체 동기화\n(내려받기 + 올리기 일괄 처리)",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=50,
            fg_color="#0969da",
            hover_color="#0860ca",
            command=lambda: self._start_git_task("sync")
        )
        self.sync_btn.grid(row=1, column=0, padx=(15, 6), pady=6, sticky="ew")

        self.pull_btn = ctk.CTkButton(
            action_frame,
            text="⬇️ 내려받기만 (Pull)\n(GitHub 최신 파일 가져오기)",
            font=ctk.CTkFont(size=13),
            height=50,
            fg_color="#57606a",
            hover_color="#424a53",
            command=lambda: self._start_git_task("pull")
        )
        self.pull_btn.grid(row=1, column=1, padx=6, pady=6, sticky="ew")

        self.push_btn = ctk.CTkButton(
            action_frame,
            text="⬆️ 올리기만 (Push)\n(내 컴퓨터 파일 GitHub에 저장)",
            font=ctk.CTkFont(size=13),
            height=50,
            fg_color="#57606a",
            hover_color="#424a53",
            command=lambda: self._start_git_task("push")
        )
        self.push_btn.grid(row=1, column=2, padx=(6, 15), pady=6, sticky="ew")

        # 자동 동기화 설정
        auto_frame = ctk.CTkFrame(action_frame, fg_color="transparent")
        auto_frame.grid(row=2, column=0, columnspan=3, padx=15, pady=4, sticky="ew")

        self.auto_sync_var = ctk.BooleanVar(value=False)
        self.auto_sync_chk = ctk.CTkCheckBox(
            auto_frame,
            text="주기적 자동 동기화 활성화",
            font=ctk.CTkFont(size=12),
            variable=self.auto_sync_var,
            command=self._on_toggle_auto_sync
        )
        self.auto_sync_chk.pack(side="left", padx=(0, 10))

        ctk.CTkLabel(auto_frame, text="주기:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(5, 5))
        self.interval_combo = ctk.CTkComboBox(
            auto_frame,
            values=["3분", "5분", "10분", "30분", "60분"],
            width=80,
            command=lambda v: self._save_current_settings()
        )
        self.interval_combo.set("10분")
        self.interval_combo.pack(side="left")

        self.auto_status_lbl = ctk.CTkLabel(auto_frame, text="", font=ctk.CTkFont(size=11), text_color="gray")
        self.auto_status_lbl.pack(side="left", padx=15)

        # 4. 실시간 로그 영역
        log_header_frame = ctk.CTkFrame(action_frame, fg_color="transparent")
        log_header_frame.grid(row=3, column=0, columnspan=3, padx=15, pady=(8, 2), sticky="ew")
        
        ctk.CTkLabel(
            log_header_frame,
            text="실시간 진행 상태 및 한글 로그:",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(side="left")

        clear_log_btn = ctk.CTkButton(
            log_header_frame,
            text="로그 지우기",
            width=70,
            height=24,
            font=ctk.CTkFont(size=11),
            fg_color="gray",
            hover_color="darkgray",
            command=self._clear_log
        )
        clear_log_btn.pack(side="right")

        # 프로그레스 바
        self.progress_bar = ctk.CTkProgressBar(action_frame)
        self.progress_bar.grid(row=4, column=0, columnspan=3, padx=15, pady=(2, 4), sticky="ew")
        self.progress_bar.set(0)

        # 로그 텍스트 박스
        self.log_textbox = ctk.CTkTextbox(action_frame, height=140, font=ctk.CTkFont(family="Consolas", size=12))
        self.log_textbox.grid(row=5, column=0, columnspan=3, padx=15, pady=(0, 15), sticky="nsew")

    def _change_theme(self, value):
        mode_map = {"시스템": "System", "다크": "Dark", "라이트": "Light"}
        ctk.set_appearance_mode(mode_map.get(value, "System"))

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

    def _log(self, message):
        now = datetime.now().strftime("%H:%M:%S")
        line = f"[{now}] {message}\n"
        self.log_textbox.insert("end", line)
        self.log_textbox.see("end")

    def _clear_log(self):
        self.log_textbox.delete("1.0", "end")

    def _check_git_status(self):
        if not self.git_engine.is_git_available():
            self._log("⚠️ 경고: 시스템에서 Git을 찾을 수 없습니다.")
            self._log("   Git for Windows 또는 GitHub Desktop을 설치해주시면 자동으로 인식합니다.")
        else:
            self._log(f"✅ Git 엔진 준비 완료: {self.git_engine.git_path}")

    def _load_saved_settings(self):
        c = self.config_data
        if c.get("username"):
            self.username_entry.insert(0, c["username"])
        if c.get("token") and c.get("remember_token", True):
            self.token_entry.insert(0, c["token"])
        if c.get("local_folder"):
            self.folder_entry.insert(0, c["local_folder"])
        if c.get("branch"):
            self.branch_entry.delete(0, "end")
            self.branch_entry.insert(0, c["branch"])
        if c.get("auto_sync_interval"):
            self.interval_combo.set(f"{c['auto_sync_interval']}분")
        self.remember_var.set(c.get("remember_token", True))

        # 토큰이 저장되어 있다면 백그라운드에서 자동 연결 시도
        if c.get("token"):
            self.after(500, self._on_click_connect)

    def _save_current_settings(self):
        interval_str = self.interval_combo.get().replace("분", "").strip()
        try:
            interval_val = int(interval_str)
        except ValueError:
            interval_val = 10

        c = {
            "username": self.username_entry.get().strip(),
            "token": self.token_entry.get().strip(),
            "remember_token": self.remember_var.get(),
            "local_folder": self.folder_entry.get().strip(),
            "selected_repo": self.repo_combo.get().strip(),
            "branch": self.branch_entry.get().strip() or "main",
            "auto_sync_enabled": self.auto_sync_var.get(),
            "auto_sync_interval": interval_val
        }
        self.config_data = c
        save_config(c)

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
        public_repos = user_info.get("public_repos", 0)

        # username 입력창이 비어있으면 자동 기입
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

    def _update_repo_combobox(self):
        if not self.repos_list:
            self.repo_combo.configure(values=["[저장소가 없습니다. 새 저장소를 만들어보세요]"])
            return

        names = [f"{r['full_name']} {'(🔒비공개)' if r.get('private') else '(🌐공개)'}" for r in self.repos_list]
        self.repo_combo.configure(values=names)

        saved = self.config_data.get("selected_repo", "")
        # 저장된 값이 목록에 있으면 선택
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

    def _get_selected_repo_url(self):
        choice = self.repo_combo.get().strip()
        if not choice or choice.startswith("["):
            return None

        # 이름 추출 (예: 'owner/repo (🔒비공개)' -> 'owner/repo')
        clean_name = choice.split()[0]
        for r in self.repos_list:
            if r.get("full_name") == clean_name:
                return r.get("clone_url") or r.get("html_url")

        # 만약 직접 URL을 입력한 경우
        if clean_name.startswith("http://") or clean_name.startswith("https://"):
            return clean_name
        return f"https://github.com/{clean_name}.git"

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

    def _start_git_task(self, task_type):
        """
        task_type: 'sync', 'pull', 'push'
        """
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

        username = self.username_entry.get().strip()
        branch = self.branch_entry.get().strip() or "main"

        # 인증 URL 생성
        auth_url = GitEngine.build_authenticated_url(raw_repo_url, username, token)

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
                        username=username,
                        logger=safe_log
                    )
                elif task_type == "pull":
                    self.git_engine.init_and_set_remote(local_folder, auth_url, branch, username)
                    ok, msg = self.git_engine.pull(local_folder, branch, logger=safe_log)
                elif task_type == "push":
                    self.git_engine.init_and_set_remote(local_folder, auth_url, branch, username)
                    ok, msg = self.git_engine.push(local_folder, branch, logger=safe_log)

                self.after(0, lambda: self._on_git_task_finished(task_type, ok, msg))
            except Exception as e:
                self.after(0, lambda: self._on_git_task_finished(task_type, False, f"예외 오류: {str(e)}"))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_git_task_finished(self, task_type, ok, msg):
        self._set_ui_syncing_state(False)
        task_names = {"sync": "전체 동기화", "pull": "내려받기", "push": "올리기"}
        tname = task_names.get(task_type, "작업")

        if ok:
            self._log(f"🎉 {tname} 작업이 성공적으로 완료되었습니다!")
        else:
            self._log(f"❌ {tname} 실패: {msg}")
            messagebox.showerror(f"{tname} 오류", f"작업 중 오류가 발생했습니다:\n\n{msg}")

    # 자동 동기화 관련
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

        MUTEX_NAME = "GitSync_Desktop_App_Single_Instance_Mutex_Global"
        mutex = kernel32.CreateMutexW(None, False, MUTEX_NAME)
        ERROR_ALREADY_EXISTS = 183

        if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            window_title = "깃싱크 (GitSync) - 초간편 한글 GitHub 폴더 동기화"
            hwnd = user32.FindWindowW(None, window_title)
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
