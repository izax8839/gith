import math
import os
from PIL import Image, ImageDraw

def create_app_icon():
    size = 512  # 고해상도 슈퍼샘플링
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 1. 배경: 세련된 다크 테마 라운드 스퀘어
    margin = 24
    radius = 110
    bg_color = (22, 27, 34, 255)  # GitHub Dark Background #161b22
    border_color = (48, 54, 61, 255)  # #30363d
    accent_blue = (88, 166, 255, 255)  # #58a6ff
    accent_green = (63, 185, 80, 255)  # #3fb950

    draw.rounded_rectangle(
        [margin, margin, size - margin, size - margin],
        radius=radius,
        fill=bg_color,
        outline=border_color,
        width=8
    )

    # 2. 부드러운 내부 글로우 원
    center = size // 2
    glow_r = 180
    draw.ellipse(
        [center - glow_r, center - glow_r, center + glow_r, center + glow_r],
        fill=(33, 38, 45, 200)
    )

    # 3. 세련된 동기화(Sync) 링 & 화살표
    ring_r = 135
    ring_width = 30

    # 상단 아크 (블루)
    bbox = [center - ring_r, center - ring_r, center + ring_r, center + ring_r]
    draw.arc(bbox, start=215, end=350, fill=accent_blue, width=ring_width)

    # 하단 아크 (그린)
    draw.arc(bbox, start=35, end=170, fill=accent_green, width=ring_width)

    # 화살표 머리 1 (우측 상단 블루)
    tip1 = (center + ring_r, center - 20)
    draw.polygon([
        tip1,
        (tip1[0] - 38, tip1[1] - 46),
        (tip1[0] + 46, tip1[1] - 38)
    ], fill=accent_blue)

    # 화살표 머리 2 (좌측 하단 그린)
    tip2 = (center - ring_r, center + 20)
    draw.polygon([
        tip2,
        (tip2[0] + 38, tip2[1] + 46),
        (tip2[0] - 46, tip2[1] + 38)
    ], fill=accent_green)

    # 4. 중앙 Git 브랜치 노드 심볼 (화이트 & 블루)
    # 수직 줄기
    draw.line([(center - 32, center - 60), (center - 32, center + 60)], fill=(240, 246, 252, 255), width=16)
    # 오른쪽 분기 곡선
    draw.arc([center - 32, center - 45, center + 55, center + 45], start=270, end=360, fill=(240, 246, 252, 255), width=16)
    draw.line([(center + 12, center), (center + 45, center - 30)], fill=(240, 246, 252, 255), width=16)

    # 노드 원 3개
    nodes = [
        (center - 32, center - 60),
        (center - 32, center + 60),
        (center + 45, center - 30)
    ]
    for nx, ny in nodes:
        draw.ellipse([nx - 24, ny - 24, nx + 24, ny + 24], fill=(240, 246, 252, 255))
        draw.ellipse([nx - 12, ny - 12, nx + 12, ny + 12], fill=(22, 27, 34, 255))

    # 5. 멀티 해상도 아이콘 생성 및 저장
    ico_path = os.path.abspath("app_icon.ico")
    png_path = os.path.abspath("app_icon.png")

    # PNG 저장 (256x256 리사이즈)
    img_256 = img.resize((256, 256), Image.Resampling.LANCZOS)
    img_256.save(png_path, "PNG")

    # ICO 저장 (모든 윈도우 표준 사이즈 포함)
    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    img.save(ico_path, format="ICO", sizes=sizes)

    print("Created:", ico_path)
    return ico_path

if __name__ == "__main__":
    create_app_icon()
