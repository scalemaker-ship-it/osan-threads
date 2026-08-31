#!/usr/bin/env python3
"""오산디에스치과 치아관리 꿀팁 스레드 — 큐에서 1건 발행 (본문 + 이어지는 답글).

레퍼런스(chikwauisa_jjin / tuna__dental / dentist_in_christ) 패턴:
  본문 = 훅 1줄 + 넘버링 1~3   → 답글 = 4~5 + 마무리 질문
일부러 끊어서 답글로 넘겨야 체류·댓글이 붙는다.

큐 형식 tips_queue.json:
  {"items": [{"date","topic","main","reply","image"?}, ...]}
  image 가 있으면 본문을 이미지 게시물로 올린다(레포 raw URL).

환경변수: THREADS_ACCESS_TOKEN (필수), THREADS_USER_ID (선택, 기본 "me")
         DRY_RUN=1 이면 발행 없이 출력만
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

KST = ZoneInfo("Asia/Seoul")

# ── 발행 시간 슬롯 (KST 20~22시) ────────────────────────────────────
# GitHub Actions 크론은 UTC 기준(KST = UTC + 9). 워크플로 yml 의 cron 값과 정확히 일치해야 한다.
# 각 실행은 자신을 트리거한 크론이 '오늘 배정된 슬롯'과 같을 때만 발행한다(발행 시각이 매일 달라짐).
SLOT_CRONS = [
    "7 11 * * *",    # 20:07 KST
    "33 11 * * *",   # 20:33 KST
    "2 12 * * *",    # 21:02 KST
    "26 12 * * *",   # 21:26 KST
    "48 12 * * *",   # 21:48 KST
    "58 12 * * *",   # 21:58 KST
]


def chosen_slot_cron(now: datetime) -> str:
    """오늘 발행할 시간 슬롯을 날짜 해시로 정한다. 기존 트랙과 겹치지 않도록 별도 시드를 쓴다."""
    h = int(hashlib.sha256(("tips-" + now.strftime("%Y-%m-%d")).encode()).hexdigest(), 16)
    return SLOT_CRONS[h % len(SLOT_CRONS)]

API = "https://graph.threads.net/v1.0"
HERE = os.path.dirname(os.path.abspath(__file__))
QUEUE = os.path.join(HERE, "tips_queue.json")
RAW_BASE = "https://raw.githubusercontent.com/scalemaker-ship-it/osan-threads/main/tips/images/"


def load_items() -> list[dict]:
    if not os.path.exists(QUEUE):
        return []
    with open(QUEUE, encoding="utf-8") as f:
        return json.load(f).get("items", [])


def save_items(items: list[dict]) -> None:
    with open(QUEUE, "w", encoding="utf-8") as f:
        json.dump({"items": items}, f, ensure_ascii=False, indent=2)
        f.write("\n")


def create(uid: str, tok: str, fields: dict) -> str:
    r = requests.post(f"{API}/{uid}/threads", json={**fields, "access_token": tok}, timeout=60)
    if not r.ok:
        sys.exit(f"[create 실패] {r.status_code} {r.text[:400]}")
    return r.json()["id"]


def wait_ready(cid: str, tok: str, tries: int = 12) -> None:
    """이미지 게시물은 컨테이너가 FINISHED 될 때까지 기다려야 한다."""
    for i in range(tries):
        r = requests.get(
            f"{API}/{cid}", params={"fields": "status,error_message", "access_token": tok}, timeout=30
        )
        s = r.json()
        st = s.get("status")
        print(f"  컨테이너 상태[{i}]: {st} {s.get('error_message', '')}")
        if st == "FINISHED":
            return
        if st == "ERROR":
            sys.exit(f"[컨테이너 ERROR] {s}")
        time.sleep(5)


def publish(uid: str, tok: str, cid: str) -> str:
    r = requests.post(
        f"{API}/{uid}/threads_publish", json={"creation_id": cid, "access_token": tok}, timeout=60
    )
    if not r.ok:
        sys.exit(f"[publish 실패] {r.status_code} {r.text[:400]}")
    return r.json()["id"]


def post_one(uid: str, tok: str, item: dict) -> str:
    image = item.get("image")
    if image:
        url = image if image.startswith("http") else RAW_BASE + image
        print(f"  이미지: {url}")
        fields = {"media_type": "IMAGE", "image_url": url, "text": item["main"]}
    else:
        fields = {"media_type": "TEXT", "text": item["main"]}

    cid = create(uid, tok, fields)
    wait_ready(cid, tok)
    root = publish(uid, tok, cid)
    print(f"  본문 게시 완료: {root}")

    reply = (item.get("reply") or "").strip()
    if reply:
        time.sleep(5)
        rcid = create(uid, tok, {"media_type": "TEXT", "text": reply, "reply_to_id": root})
        wait_ready(rcid, tok)
        rid = publish(uid, tok, rcid)
        print(f"  답글 게시 완료: {rid}")
    return root


def main() -> None:
    dry = os.environ.get("DRY_RUN", "").strip().lower() in {"1", "true", "yes", "y"}

    now = datetime.now(KST)
    # 예약 실행이면 오늘 배정된 슬롯 한 번에서만 발행한다(수동 실행은 검사 없이 바로 진행).
    if os.environ.get("GITHUB_EVENT_NAME", "") == "schedule":
        target = chosen_slot_cron(now)
        current = os.environ.get("SCHEDULE_CRON", "").strip()
        if current != target:
            print(f"[{now:%Y-%m-%d %H:%M KST}] 오늘 발행 슬롯이 아닙니다 "
                  f"(이 실행 {current!r} ≠ 오늘 배정 {target!r}). 종료합니다.")
            return
        print(f"[{now:%Y-%m-%d %H:%M KST}] 오늘의 발행 슬롯 {current!r} 매칭. 진행합니다.")

    items = load_items()
    if not items:
        print("[큐 비어 있음] 발행할 글이 없습니다.")
        return

    item = items[0]
    print(f"[예정일 {item.get('date', '-')}] 주제: {item.get('topic', '-')}"
          f" · 이미지 {'있음' if item.get('image') else '없음'} · 남은 글 {len(items)}건")
    print("=== 본문 ===\n" + item["main"])
    print("=== 답글 ===\n" + (item.get("reply") or "(없음)"))

    if dry:
        print("[DRY_RUN] 발행을 건너뜁니다.")
        return

    tok = os.environ.get("THREADS_ACCESS_TOKEN")
    if not tok:
        sys.exit("[오류] THREADS_ACCESS_TOKEN 이 없습니다.")
    uid = os.environ.get("THREADS_USER_ID") or "me"

    post_one(uid, tok, item)
    save_items(items[1:])
    print(f"[큐] 1건 소진. 남은 글 {len(items) - 1}건.")


if __name__ == "__main__":
    main()
