import requests

GITHUB_API_BASE = "https://api.github.com"

class GitHubAPI:
    @staticmethod
    def _get_headers(token: str):
        token = token.strip()
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "GitSync-Desktop-App"
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    @classmethod
    def test_connection(cls, token: str):
        """
        토큰으로 GitHub 연결 및 사용자 정보를 확인합니다.
        성공 시 (True, user_dict) 반환
        실패 시 (False, error_message) 반환
        """
        token = token.strip()
        if not token:
            return False, "토큰(비밀번호 대체키)을 입력해주세요."

        url = f"{GITHUB_API_BASE}/user"
        try:
            res = requests.get(url, headers=cls._get_headers(token), timeout=10)
            if res.status_code == 200:
                data = res.json()
                return True, data
            elif res.status_code == 401:
                return False, "인증 실패: GitHub 토큰이 유효하지 않거나 만료되었습니다."
            else:
                return False, f"오류 코드 {res.status_code}: {res.text}"
        except requests.exceptions.Timeout:
            return False, "연결 시간 초과: 인터넷 연결 상태를 확인해주세요."
        except requests.exceptions.RequestException as e:
            return False, f"네트워크 오류: {str(e)}"

    @classmethod
    def get_user_repos(cls, token: str):
        """
        사용자의 저장소(Repository) 목록을 가져옵니다.
        최대 100개, 최근 수정 순 정렬.
        """
        token = token.strip()
        if not token:
            return False, "토큰을 입력해주세요."

        url = f"{GITHUB_API_BASE}/user/repos?per_page=100&sort=updated"
        try:
            res = requests.get(url, headers=cls._get_headers(token), timeout=12)
            if res.status_code == 200:
                repos = res.json()
                parsed = []
                for r in repos:
                    parsed.append({
                        "name": r.get("name"),
                        "full_name": r.get("full_name"),
                        "clone_url": r.get("clone_url"),
                        "html_url": r.get("html_url"),
                        "private": r.get("private", False),
                        "description": r.get("description") or "",
                        "default_branch": r.get("default_branch") or "main"
                    })
                return True, parsed
            elif res.status_code == 401:
                return False, "인증 실패: 토큰을 확인해주세요."
            else:
                return False, f"저장소 목록 조회 실패 ({res.status_code})"
        except Exception as e:
            return False, f"오류 발생: {str(e)}"

    @classmethod
    def create_repository(cls, token: str, name: str, description: str = "", is_private: bool = True):
        """
        GitHub에 새 저장소를 만듭니다.
        """
        token = token.strip()
        name = name.strip()
        if not token:
            return False, "토큰이 필요합니다."
        if not name:
            return False, "저장소 이름을 입력해주세요."

        url = f"{GITHUB_API_BASE}/user/repos"
        payload = {
            "name": name,
            "description": description,
            "private": is_private,
            "auto_init": False  # 로컬 파일과 직접 동기화할 수 있도록 빈 저장소로 생성
        }
        try:
            res = requests.post(url, headers=cls._get_headers(token), json=payload, timeout=12)
            if res.status_code == 201:
                data = res.json()
                return True, {
                    "name": data.get("name"),
                    "full_name": data.get("full_name"),
                    "clone_url": data.get("clone_url"),
                    "html_url": data.get("html_url"),
                    "default_branch": "main"
                }
            elif res.status_code == 422:
                return False, "이미 존재하는 저장소 이름이거나 잘못된 이름입니다."
            else:
                return False, f"생성 실패 ({res.status_code}): {res.text}"
        except Exception as e:
            return False, f"저장소 생성 중 오류: {str(e)}"

    @classmethod
    def check_latest_release(cls, token: str = "", repo_full_name: str = "izax8839/gith"):
        """
        GitHub Releases에서 최신 배포 버전을 확인합니다.
        """
        if not repo_full_name:
            return False, None

        url = f"{GITHUB_API_BASE}/repos/{repo_full_name}/releases/latest"
        try:
            res = requests.get(url, headers=cls._get_headers(token), timeout=8)
            if res.status_code == 200:
                data = res.json()
                return True, {
                    "tag_name": data.get("tag_name", ""),
                    "name": data.get("name", ""),
                    "html_url": data.get("html_url", ""),
                    "body": data.get("body", "")
                }
            return False, None
        except Exception:
            return False, None
