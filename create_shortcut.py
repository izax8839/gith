import os
import subprocess
import shutil

desktop = os.path.join(os.path.expanduser("~"), "Desktop")
shortcut_path = os.path.join(desktop, "깃싱크 (GitHub 동기화).lnk")
work_dir = os.path.abspath(".")
icon_path = os.path.abspath("app_icon.ico")

# pythonw.exe 경로 찾기
pythonw_path = shutil.which("pythonw")
if not pythonw_path or not os.path.isfile(pythonw_path):
    pythonw_path = os.path.expandvars(r"%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe")

vbs_code = f"""
Set oWS = WScript.CreateObject("WScript.Shell")
sLinkFile = "{shortcut_path}"
Set oLink = oWS.CreateShortcut(sLinkFile)
oLink.TargetPath = "{pythonw_path}"
oLink.Arguments = "app.py"
oLink.WorkingDirectory = "{work_dir}"
oLink.Description = "GitHub 초간편 폴더 동기화 매니저"
oLink.IconLocation = "{icon_path},0"
oLink.Save
"""

vbs_file = "make_link.vbs"
with open(vbs_file, "w", encoding="cp949") as f:
    f.write(vbs_code.strip())

subprocess.run(["cscript", "//nologo", vbs_file], check=True)
if os.path.exists(vbs_file):
    os.remove(vbs_file)

print("Shortcut target set directly to pythonw.exe at:", shortcut_path)
