import os
import glob
import shutil
import subprocess
from datetime import datetime
from urllib.parse import urlparse, urlunparse

# Windows에서 콘솔 창 안 뜨게 하는 플래그
CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0

def find_git_executable():
    """
    시스템 PATH, GitHub Desktop 설치 경로 등에서 git.exe를 자동으로 탐색합니다.
    """
    which_git = shutil.which("git")
    if which_git:
        return which_git

    candidates = [
        r"C:\Program Files\Git\cmd\git.exe",
        r"C:\Program Files\Git\bin\git.exe",
        r"C:\Program Files (x86)\Git\cmd\git.exe",
        r"C:\Program Files (x86)\Git\bin\git.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Git\bin\git.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Git\cmd\git.exe")
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c

    # GitHub Desktop 내장 Git 탐색
    gh_desktop = os.path.expandvars(r"%LOCALAPPDATA%\GitHubDesktop")
    if os.path.isdir(gh_desktop):
        matches = glob.glob(os.path.join(gh_desktop, "app-*", "resources", "app", "git", "cmd", "git.exe"))
        if matches:
            return matches[-1]
        matches = glob.glob(os.path.join(gh_desktop, "**", "git.exe"), recursive=True)
        if matches:
            return matches[0]

    return None


def is_winget_available():
    """Windows 패키지 관리자(winget) 사용 가능 여부 확인"""
    return bool(shutil.which("winget"))


def install_git_via_winget(logger=None):
    """
    winget을 통해 공식 Git for Windows를 무인/자동 설치합니다.
    """
    def log(msg):
        if logger:
            logger(msg)

    if not is_winget_available():
        return False, "이 컴퓨터에서는 winget(Windows 패키지 관리자)을 사용할 수 없습니다."

    log("⚡ 공식 Git for Windows 자동 설치를 시작합니다...")
    log("   (화면에 관리자 권한 확인 창이 나타나면 [예]를 눌러주세요)")

    cmd = [
        "winget", "install",
        "--id", "Git.Git",
        "-e",
        "--source", "winget",
        "--accept-source-agreements",
        "--accept-package-agreements"
    ]

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=CREATE_NO_WINDOW,
            text=True,
            encoding="utf-8",
            errors="replace"
        )

        for line in iter(proc.stdout.readline, ""):
            line_str = line.strip()
            if line_str and not line_str.startswith("-") and not line_str.startswith("\\"):
                # 진행률 또는 주요 메시지만 선별 로그
                if any(k in line_str for k in ["다운로드", "설치", "Download", "Install", "성공", "Successfully", "기다려"]):
                    log(f"   {line_str}")

        proc.stdout.close()
        proc.wait()

        # 설치 후 새로 생긴 git.exe 경로 탐색
        new_git = find_git_executable()
        if new_git:
            log(f"🎉 Git 설치 완료! 감지된 경로: {new_git}")
            return True, new_git
        else:
            if proc.returncode == 0:
                log("Git 설치 명령이 종료되었습니다. 시스템 경로를 갱신합니다.")
                return True, find_git_executable()
            return False, f"설치 중 문제가 발생했습니다 (종료 코드: {proc.returncode})"

    except Exception as e:
        return False, f"Git 자동 설치 중 오류: {str(e)}"


class GitEngine:
    def __init__(self, git_path=None):
        self.git_path = git_path or find_git_executable()

    def refresh_git_path(self):
        """새로 설치된 Git 경로를 재탐색하여 갱신합니다."""
        self.git_path = find_git_executable()
        return self.is_git_available()

    def is_git_available(self):
        return bool(self.git_path and os.path.isfile(self.git_path))

    def _run_git(self, cwd, args, timeout=60):
        if not self.is_git_available():
            return False, "Git 실행 파일을 찾을 수 없습니다. Git 또는 GitHub Desktop이 설치되어 있는지 확인해주세요."

        cmd = [self.git_path] + args
        try:
            proc = subprocess.run(
                cmd,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=CREATE_NO_WINDOW,
                timeout=timeout
            )
            # UTF-8 시도 후 실패 시 cp949 디코딩
            try:
                out = proc.stdout.decode("utf-8")
            except UnicodeDecodeError:
                out = proc.stdout.decode("cp949", errors="replace")

            try:
                err = proc.stderr.decode("utf-8")
            except UnicodeDecodeError:
                err = proc.stderr.decode("cp949", errors="replace")

            if proc.returncode == 0:
                return True, out.strip()
            else:
                combined_err = (err or out).strip()
                return False, combined_err
        except subprocess.TimeoutExpired:
            return False, "작업 시간이 초과되었습니다 (네트워크 지연 또는 서버 무응답)."
        except Exception as e:
            return False, f"실행 중 예외 발생: {str(e)}"

    @staticmethod
    def build_authenticated_url(raw_url: str, username: str, token: str) -> str:
        """
        https://github.com/owner/repo.git 형태의 URL에 토큰을 포함한 인증 URL을 만듭니다.
        """
        raw_url = raw_url.strip()
        if not token:
            return raw_url

        parsed = urlparse(raw_url)
        if parsed.scheme in ("http", "https"):
            # 토큰을 사용자/비밀번호 영역에 주입
            netloc = f"{token}@github.com"
            path = parsed.path
            return urlunparse((parsed.scheme, netloc, path, "", "", ""))
        return raw_url

    def is_git_repo(self, folder_path):
        git_dir = os.path.join(folder_path, ".git")
        return os.path.isdir(git_dir)

    def ensure_git_identity(self, folder_path, username):
        """
        커밋 시 필요한 user.name과 user.email이 누락되어 커밋이 실패하지 않도록 로컬 저장소에 설정합니다.
        """
        uname = username.strip() if username else "GitSyncUser"
        uemail = f"{uname}@users.noreply.github.com"

        # 로컬 config 확인
        ok_name, name_val = self._run_git(folder_path, ["config", "--get", "user.name"])
        if not ok_name or not name_val:
            self._run_git(folder_path, ["config", "user.name", uname])

        ok_email, email_val = self._run_git(folder_path, ["config", "--get", "user.email"])
        if not ok_email or not email_val:
            self._run_git(folder_path, ["config", "user.email", uemail])

    def setup_safe_directory(self, folder_path):
        """
        Git의 safe.directory 제한으로 인한 에러 방지
        """
        norm_path = os.path.abspath(folder_path).replace("\\", "/")
        self._run_git(folder_path, ["config", "--global", "--add", "safe.directory", norm_path])

    def create_default_gitignore(self, folder_path):
        """
        불필요한 윈도우 캐시 파일이 깃에 올라가지 않도록 기본 .gitignore 생성 (없는 경우에만)
        """
        gitignore_path = os.path.join(folder_path, ".gitignore")
        if not os.path.exists(gitignore_path):
            content = (
                "# Windows\n"
                "Thumbs.db\n"
                "ehthumbs.db\n"
                "Desktop.ini\n"
                "$RECYCLE.BIN/\n"
                "\n"
                "# macOS\n"
                ".DS_Store\n"
                "\n"
                "# App config\n"
                "config.json\n"
            )
            try:
                with open(gitignore_path, "w", encoding="utf-8") as f:
                    f.write(content)
            except Exception:
                pass

    def init_and_set_remote(self, folder_path, auth_url, branch="main", username=""):
        """
        폴더에 .git이 없으면 초기화하고 원격 저장소를 연결합니다.
        """
        self.setup_safe_directory(folder_path)

        if not self.is_git_repo(folder_path):
            # git init
            ok, msg = self._run_git(folder_path, ["init", "-b", branch])
            if not ok:
                # 구버전 git 대응 (-b 옵션 미지원 시)
                ok, msg = self._run_git(folder_path, ["init"])
                if not ok:
                    return False, f"Git 초기화 실패: {msg}"
                self._run_git(folder_path, ["branch", "-M", branch])

        self.ensure_git_identity(folder_path, username)
        self.create_default_gitignore(folder_path)

        # 원격 저장소 origin 확인 및 설정
        ok, current_origin = self._run_git(folder_path, ["remote", "get-url", "origin"])
        if ok:
            # 기존 origin URL 변경
            ok, msg = self._run_git(folder_path, ["remote", "set-url", "origin", auth_url])
        else:
            # 새로 등록
            ok, msg = self._run_git(folder_path, ["remote", "add", "origin", auth_url])

        if not ok:
            return False, f"원격 저장소 연결 실패: {msg}"

        return True, "원격 저장소 설정 완료"

    def has_remote_branch(self, folder_path, branch="main"):
        """
        GitHub에 해당 브랜치가 실제로 존재하는지 확인합니다.
        """
        ok, out = self._run_git(folder_path, ["ls-remote", "--heads", "origin", branch])
        if ok and branch in out:
            return True
        return False

    def pull(self, folder_path, branch="main", logger=None):
        """
        GitHub 원격 저장소의 최신 파일들을 내 컴퓨터로 내려받습니다.
        """
        def log(text):
            if logger:
                logger(text)

        log(f"GitHub에서 최신 파일 확인 중 ({branch} 브랜치)...")

        # 원격에 브랜치가 없으면 (완전 빈 저장소인 경우) 풀 불필요
        if not self.has_remote_branch(folder_path, branch):
            log("원격 저장소가 아직 비어있습니다 (첫 업로드 대기 중).")
            return True, "원격 저장소에 아직 브랜치가 없습니다."

        log("원격 저장소의 파일들을 내려받고 병합하는 중...")
        # unrelated histories 허용하여 로컬 파일과 원격 파일 안전하게 병합
        ok, out = self._run_git(folder_path, ["pull", "origin", branch, "--allow-unrelated-histories", "--no-rebase"])
        if not ok:
            # 충돌 발생 시
            if "conflict" in out.lower() or "충돌" in out:
                return False, f"파일 충돌이 발생했습니다. 같은 파일이 로컬과 GitHub에서 서로 다르게 수정되었습니다.\n세부 정보: {out}"
            return False, f"내려받기 실패: {out}"

        log("최신 파일 내려받기 완료!")
        return True, out

    def push(self, folder_path, branch="main", commit_msg=None, logger=None):
        """
        내 컴퓨터 폴더의 파일 변경사항을 GitHub에 올립니다.
        """
        def log(text):
            if logger:
                logger(text)

        log("내 컴퓨터 폴더의 변경된 파일들을 스캔하는 중...")
        # 1. git add
        ok, out = self._run_git(folder_path, ["add", "-A"])
        if not ok:
            return False, f"파일 스테이징 실패: {out}"

        # 2. 상태 확인
        ok, status_out = self._run_git(folder_path, ["status", "--porcelain"])
        if not status_out.strip():
            log("변경된 파일이 없습니다. (이미 최신 상태)")
            return True, "변경된 파일이 없습니다."

        # 3. 커밋
        if not commit_msg:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            commit_msg = f"컴퓨터 파일 동기화 [{now_str}]"

        log(f"변경사항 커밋 중: '{commit_msg}'")
        ok, out = self._run_git(folder_path, ["commit", "-m", commit_msg])
        if not ok:
            return False, f"커밋 생성 실패: {out}"

        # 4. 푸시
        log(f"GitHub에 업로드(Push) 중... ({branch} 브랜치)")
        ok, out = self._run_git(folder_path, ["push", "-u", "origin", branch])
        if not ok:
            # 원격에 새로운 커밋이 있어서 푸시가 거부된 경우 (non-fast-forward)
            if "rejected" in out or "fetch first" in out:
                return False, "GitHub에 먼저 올라간 새 파일이 있어 업로드가 거부되었습니다. [내려받기] 또는 [동기화]를 먼저 실행해주세요."
            return False, f"업로드 실패: {out}"

        log("GitHub 업로드 성공!")
        return True, "GitHub 업로드 완료"

    def sync(self, folder_path, auth_url, branch="main", commit_msg=None, username="", logger=None):
        """
        전체 동기화: 원격 저장소 연결 -> 원격 변경사항 풀 -> 로컬 변경사항 커밋 & 푸시
        """
        def log(text):
            if logger:
                logger(text)

        log("=== 동기화 시작 ===")
        # 1. 초기화 및 원격 URL 설정
        log("로컬 Git 저장소 설정 확인 중...")
        ok, msg = self.init_and_set_remote(folder_path, auth_url, branch, username)
        if not ok:
            return False, msg

        # 2. 원격에 브랜치가 있다면 먼저 pull
        if self.has_remote_branch(folder_path, branch):
            log("GitHub의 최신 변경사항을 확인하여 병합합니다...")
            ok, msg = self.pull(folder_path, branch, logger)
            if not ok:
                return False, msg

        # 3. 로컬 변경사항 푸시
        log("로컬 컴퓨터의 변경사항을 GitHub에 업로드합니다...")
        ok, msg = self.push(folder_path, branch, commit_msg, logger)
        if not ok:
            return False, msg

        log("=== 모든 동기화가 성공적으로 완료되었습니다! ===")
        return True, "동기화 완료"

    def inspect_sync_status(self, folder_path, auth_url, branch="main"):
        """
        로컬 폴더와 GitHub 원격 저장소의 최신 상태를 비교하여
        어느 쪽이 더 최신인지, 내려받기 또는 업로드가 필요한지 진단합니다.
        반환: (status_code, title_text, detail_text, has_remote_new)
        """
        if not folder_path or not os.path.isdir(folder_path):
            return "NO_FOLDER", "폴더 미선택", "동기화할 컴퓨터 폴더를 선택해주세요.", False

        if not self.is_git_available():
            return "NO_GIT", "Git 미설치", "Git 엔진이 필요합니다.", False

        if not self.is_git_repo(folder_path):
            # 아직 .git이 없는 일반 폴더인 경우
            return "NOT_INITIALIZED", "신규 연동 대기", "동기화 버튼을 누르면 이 폴더와 GitHub이 처음으로 연결됩니다.", False

        # 1. 로컬에 커밋되지 않은 새/수정 파일이 있는지 확인
        ok, status_out = self._run_git(folder_path, ["status", "--porcelain"])
        has_local_changes = bool(ok and status_out.strip())

        # 2. 로컬 최신 커밋 해시 확인
        ok_l, local_head = self._run_git(folder_path, ["rev-parse", "HEAD"])
        local_head = local_head.strip() if ok_l else None

        # 3. 원격 최신 커밋 해시 가볍게 확인 (ls-remote)
        ok_r, remote_out = self._run_git(folder_path, ["ls-remote", "--heads", auth_url, branch], timeout=15)
        remote_head = None
        if ok_r and remote_out.strip():
            # 출력 형식: "<hash>\trefs/heads/<branch>"
            for line in remote_out.strip().splitlines():
                parts = line.split()
                if len(parts) >= 2 and branch in parts[1]:
                    remote_head = parts[0]
                    break

        # 4. 상태 판정
        if not remote_head and not local_head:
            return "EMPTY", "저장소 비어있음", "GitHub과 로컬 폴더 모두 비어 있는 상태입니다.", False

        if remote_head and not local_head:
            return "BEHIND", "GitHub에 최신 파일 있음", "GitHub에 파일이 있습니다. 작업 전 먼저 [내려받기]를 해주세요!", True

        if not remote_head and local_head:
            return "AHEAD", "첫 업로드 대기 중", "내 컴퓨터의 파일들을 GitHub에 처음 올릴 준비가 되었습니다.", False

        if remote_head == local_head:
            if has_local_changes:
                return "LOCAL_MODIFIED", "컴퓨터에 수정된 파일 있음", "내 컴퓨터에서 작업한 새 변경사항이 있습니다. [올리기]를 진행하세요.", False
            else:
                return "UP_TO_DATE", "완벽 동기화 완료", "내 컴퓨터와 GitHub의 파일이 완벽하게 일치합니다.", False

        # 해시가 다를 때: 로컬 저장소에 remote_head가 이미 존재하는지 검사
        ok_cat, _ = self._run_git(folder_path, ["cat-file", "-e", remote_head])
        if ok_cat:
            # 원격 커밋이 이미 로컬 역사에 포함되어 있음 -> 내 컴퓨터가 원격보다 앞섬
            return "AHEAD", "컴퓨터에 새 커밋 있음", "내 컴퓨터의 최신 작업을 GitHub에 올릴 준비가 되었습니다.", False
        else:
            # 원격 커밋이 로컬에 없음 -> GitHub에 새 내용이 먼저 올라간 상태!
            if has_local_changes:
                return "DIVERGED", "양쪽 모두 수정됨 (주의)", "GitHub과 컴퓨터 양쪽에 모두 새 파일이 있습니다. [원클릭 전체 동기화]로 병합하세요.", True
            return "BEHIND", "GitHub에 새로운 최신 파일 있음", "GitHub에 새 작업이 있습니다! 컴퓨터로 먼저 내려받으세요.", True
