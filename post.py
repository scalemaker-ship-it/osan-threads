#!/usr/bin/env python3
"""오산디에스치과 스레드 자동 게시 — 화·목·토 19시대, 하루 1건, 텍스트만(이미지 없음).

트랙(요일로 결정):
  화·토  info   정보성 — 생활 치아관리 꿀팁 (info_queue.json)
  목     daily  일상·소통 — 오산/동탄/평택/수원 이웃 대상 수다글 (daily_queue.json)
  그 외  발행 안 함

큐 형식: {"items": [{"date", "topic", "main", "reply"?}, ...]}  맨 앞부터 소진.
  main  = 본문(텍스트 게시물)
  reply = 있으면 본문에 이어 답글로 게시(마무리 질문·부연). 없으면 본문만.

발행 시각: 워크플로 크론이 19~20시 KST 사이 여러 분(分) 슬롯에서 실행되고,
날짜 해시로 정한 '오늘의 슬롯' 한 번에서만 발행한다 → 매번 분이 달라진다.

환경변수:
  THREADS_ACCESS_TOKEN  필수(드라이런 제외)   THREADS_USER_ID 선택(기본 "me")
  DRY_RUN=1             발행 없이 출력만
  TRACK_OVERRIDE        info / daily 로 요일 판단을 덮어씀(수동 실행용)
  GITHUB_EVENT_NAME, SCHEDULE_CRON  Actions가 주입(슬롯 게이팅)
로컬: python post.py --dry-run [--track info|daily]
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
HERE = os.path.dirname(os.path.abspath(__file__))
API = "https://graph.threads.net/v1.0"

# 워크플로 yml 의 cron 문자열과 정확히 일치해야 한다 (UTC, 19~20시 KST).
SLOT_CRONS = [
    "2 10 * * 2,4,6",    # 19:02 KST
    "14 10 * * 2,4,6",   # 19:14 KST
    "23 10 * * 2,4,6",   # 19:23 KST
    "35 10 * * 2,4,6",   # 19:35 KST
    "47 10 * * 2,4,6",   # 19:47 KST
    "56 10 * * 2,4,6",   # 19:56 KST
]

# weekday(): 월0 화1 수2 목3 금4 토5 일6
TRACK_BY_WEEKDAY = {1: "info", 5: "info", 3: "daily"}
QUEUE_FILES = {
    "info": os.path.join(HERE, "info_queue.json"),
    "daily": os.path.join(HERE, "daily_queue.json"),
}
TRACK_LABEL = {"info": "정보성(치아관리 꿀팁)", "daily": "일상·소통"}


def chosen_slot_cron(now: datetime) -> str:
    """오늘 발행할 분 슬롯을 날짜 해시로 정한다."""
    h = int(hashlib.sha256(("osan-" + now.strftime("%Y-%m-%d")).encode()).hexdigest(), 16)
    return SLOT_CRONS[h % len(SLOT_CRONS)]


def load_items(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("items", [])


def save_items(path: str, items: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"items": items}, f, ensure_ascii=False, indent=2)
        f.write("\n")


def create(uid: str, tok: str, fields: dict) -> str:
    r = requests.post(f"{API}/{uid}/threads", json={**fields, "access_token": tok}, timeout=60)
    if not r.ok:
        sys.exit(f"[create 실패] {r.status_code} {r.text[:400]}")
    return r.json()["id"]


def wait_ready(cid: str, tok: str, tries: int = 12) -> None:
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
    cid = create(uid, tok, {"media_type": "TEXT", "text": item["main"]})
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


def truthy(v: str | None) -> bool:
    return (v or "").strip().lower() in {"1", "true", "yes", "y"}


def main() -> None:
    args = sys.argv[1:]
    dry = truthy(os.environ.get("DRY_RUN")) or "--dry-run" in args
    track = (os.environ.get("TRACK_OVERRIDE") or "").strip()
    if "--track" in args:
        track = args[args.index("--track") + 1]

    now = datetime.now(KST)

    # 예약 실행이면 오늘 배정된 슬롯 한 번에서만 발행한다(수동·로컬 실행은 검사 없이 진행).
    if os.environ.get("GITHUB_EVENT_NAME", "") == "schedule":
        target = chosen_slot_cron(now)
        current = os.environ.get("SCHEDULE_CRON", "").strip()
        if current != target:
            print(f"[{now:%Y-%m-%d %H:%M KST}] 오늘 발행 슬롯이 아닙니다 "
                  f"(이 실행 {current!r} ≠ 오늘 배정 {target!r}). 종료합니다.")
            return
        print(f"[{now:%Y-%m-%d %H:%M KST}] 오늘의 발행 슬롯 {current!r} 매칭. 진행합니다.")

    if not track:
        track = TRACK_BY_WEEKDAY.get(now.weekday(), "")
    if track not in QUEUE_FILES:
        print(f"[{now:%Y-%m-%d %a}] 발행 요일이 아닙니다(화·토=정보, 목=일상). 종료합니다.")
        return

    path = QUEUE_FILES[track]
    items = load_items(path)
    if not items:
        sys.exit(f"[큐 비어 있음] {os.path.basename(path)} 에 발행할 글이 없습니다. 큐를 채워주세요.")

    item = items[0]
    print(f"[{TRACK_LABEL[track]}] 예정일 {item.get('date', '-')} · 주제: {item.get('topic', '-')}"
          f" · 남은 글 {len(items)}건")
    print("=== 본문 ===\n" + item["main"])
    print("=== 답글 ===\n" + ((item.get("reply") or "").strip() or "(없음)"))

    if dry:
        print("[DRY_RUN] 발행을 건너뜁니다.")
        return

    tok = os.environ.get("THREADS_ACCESS_TOKEN")
    if not tok:
        sys.exit("[오류] THREADS_ACCESS_TOKEN 이 없습니다.")
    uid = os.environ.get("THREADS_USER_ID") or "me"

    post_one(uid, tok, item)
    save_items(path, items[1:])
    print(f"[큐] 1건 소진. 남은 글 {len(items) - 1}건.")


if __name__ == "__main__":
    main()
