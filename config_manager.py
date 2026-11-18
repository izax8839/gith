import json
import os

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

DEFAULT_CONFIG = {
    "username": "",
    "token": "",
    "remember_token": True,
    "local_folder": "",
    "selected_repo": "",
    "branch": "main",
    "auto_sync_enabled": False,
    "auto_sync_interval": 10,  # 분 단위
    "commit_message_prefix": "컴퓨터 파일 동기화"
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            config = DEFAULT_CONFIG.copy()
            config.update(data)
            return config
    except Exception:
        return DEFAULT_CONFIG.copy()

def save_config(config_dict):
    try:
        to_save = config_dict.copy()
        if not to_save.get("remember_token", True):
            to_save["token"] = ""
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(to_save, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"설정 저장 실패: {e}")
        return False
