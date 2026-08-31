#!/usr/bin/env python3
"""치아관리 팁 정보 카드(1:1 PNG)를 PIL로 렌더한다.

이미지 모델 대신 PIL을 쓰는 이유: 한글이 100% 정확하게 나오고, 30장을 반복 생성해도
결과가 흔들리지 않으며 비용이 0이다.

사용:
  python3 tips/make_card.py --title "양치에 대한 흔한 오해 5" \
      --items "며칠 바짝 닦으면 된다" "안 아프면 괜찮다" ... \
      --mark x --out tips/images/tips-01.png
"""
import argparse
import os

from PIL import Image, ImageDraw, ImageFont

W = H = 1080
BG = (255, 255, 255)
INK = (26, 28, 30)
MINT = (0, 176, 155)
GRAY = (155, 160, 165)
RED = (232, 74, 68)

FONT_DIR = os.path.expanduser("~/Library/Fonts")


def font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(os.path.join(FONT_DIR, f"Pretendard-{weight}.ttf"), size)


def fit(draw, text, weight, size, max_w):
    """max_w 안에 들어올 때까지 폰트 크기를 줄인다."""
    while size > 20:
        f = font(weight, size)
        if draw.textlength(text, font=f) <= max_w:
            return f
        size -= 2
    return font(weight, size)


def render(title: str, items: list[str], out: str, mark: str = "x", footer: str = "오산디에스치과"):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    pad = 88
    max_w = W - pad * 2

    # 제목 (길면 자동 축소, 필요하면 두 줄)
    tf = fit(d, title, "Bold", 74, max_w)
    y = 118
    d.text((pad, y), title, font=tf, fill=INK)
    y += tf.size + 34

    # 민트 구분선
    d.rounded_rectangle([pad, y, pad + 132, y + 8], radius=4, fill=MINT)
    y += 74

    # 항목 5줄
    n = len(items)
    gap = (H - 190 - y) // n
    badge_r = 27
    for i, text in enumerate(items):
        cy = y + gap * i + gap // 2 - 14
        # 번호 배지
        d.ellipse([pad, cy - badge_r + 6, pad + badge_r * 2, cy + badge_r + 6], fill=MINT)
        nf = font("Bold", 30)
        nw = d.textlength(str(i + 1), font=nf)
        d.text((pad + badge_r - nw / 2, cy - 9), str(i + 1), font=nf, fill=(255, 255, 255))
        # 본문
        tx = pad + badge_r * 2 + 30
        avail = W - tx - pad - (54 if mark else 0)
        f = fit(d, text, "SemiBold", 46, avail)
        d.text((tx, cy - f.size // 2 + 4), text, font=f, fill=INK)
        # 오른쪽 표시
        if mark == "x":
            mx, my, s = W - pad - 34, cy + 4, 15
            for dx, dy in ((-1, 1), (1, 1)):
                d.line([mx - s * dx, my - s, mx + s * dx, my + s], fill=RED, width=7)
        elif mark == "check":
            mx, my = W - pad - 40, cy + 4
            d.line([mx, my + 2, mx + 12, my + 15], fill=MINT, width=8)
            d.line([mx + 12, my + 15, mx + 34, my - 16], fill=MINT, width=8)

    ff = font("Medium", 30)
    d.text((pad, H - 100), footer, font=ff, fill=GRAY)

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    img.save(out, "PNG")
    print(out)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--title", required=True)
    p.add_argument("--items", nargs="+", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--mark", default="x", choices=["x", "check", "none"])
    a = p.parse_args()
    render(a.title, a.items, a.out, None if a.mark == "none" else a.mark)
