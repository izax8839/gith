import os
import shutil
import subprocess

desktop = os.path.join(os.path.expanduser("~"), "Desktop")
shortcut_path = os.path.join(desktop, "깃싱크 (GitHub 동기화).lnk")
work_dir = os.path.abspath(".")

# dist에서 상위 폴더로 복사
dist_exe = os.path.join(work_dir, "dist", "깃싱크.exe")
target_exe = os.path.join(work_dir, "깃싱크.exe")

if os.path.exists(dist_exe):
    shutil.copy2(dist_exe, target_exe)
    print("Copied 깃싱크.exe to root folder:", target_exe)

# 바탕화면 바로가기를 깃싱크.exe로 직접 연결
vbs_code = f"""
Set oWS = WScript.CreateObject("WScript.Shell")
sLinkFile = "{shortcut_path}"
Set oLink = oWS.CreateShortcut(sLinkFile)
oLink.TargetPath = "{target_exe}"
oLink.WorkingDirectory = "{work_dir}"
oLink.Description = "GitHub 초간편 폴더 동기화 매니저 (EXE)"
oLink.IconLocation = "{target_exe},0"
oLink.Save
"""

vbs_file = "make_link.vbs"
with open(vbs_file, "w", encoding="cp949") as f:
    f.write(vbs_code.strip())

subprocess.run(["cscript", "//nologo", vbs_file], check=True)
if os.path.exists(vbs_file):
    os.remove(vbs_file)

# 셸 새로고침
import ctypes
SHCNE_ASSOCCHANGED = 0x08000000
SHCNF_IDLIST = 0x0000
ctypes.windll.shell32.SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST, None, None)

print("Desktop shortcut updated directly to 깃싱크.exe!")
