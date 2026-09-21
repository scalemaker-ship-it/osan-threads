#!/usr/bin/env python3
"""오산디에스치과 스레드 자동 게시 — 화·목·토 19시대, 하루 1건, 텍스트만(이미지 없음).

트랙(요일로 결정):
  화·토  info   정보성 — 생활 치아관리 꿀팁 (info_queue.json)
  목     daily  일상·소통 — 오산/동탄/평택/수원 이웃 대상 수다글 (daily_queue.json)
  그 외  발행 안 함

큐 형식: {"items": [{"date", "topic", "main", "reply"?}, ...]}  맨 앞부터 소진.
날짜 예약글: pinned_posts.json (같은 형식). 요일 무관하게 date == 오늘인 글을 그 날짜 전용 크론에서 발행.
  main  = 본문(텍스트 게시물)
  reply = 있으면 본문에 이어 답글로 게시(마무리 질문·부연). 없으면 본문만.

발행 시각: GitHub 크론은 수 시간까지 지연되므로 '크론 시각'을 믿지 않는다.
워크플로는 KST 15~21시대에 15분 간격으로 넓게 깔아두고, 이 스크립트가
'실제 KST 시각이 발행 창(19:00~20:30) 안인가' + '오늘 이미 발행했는가'로 게이팅한다.
→ 지연이 있든 없든 창 안에 들어온 첫 실행 한 번만 발행된다(발행 분은 매번 달라짐).

환경변수:
  THREADS_ACCESS_TOKEN  필수(드라이런 제외)   THREADS_USER_ID 선택(기본 "me")
  DRY_RUN=1             발행 없이 출력만
  TRACK_OVERRIDE        info / daily / pinned 로 요일 판단을 덮어씀(수동 실행용)
  GITHUB_EVENT_NAME, SCHEDULE_CRON  Actions가 주입(슬롯 게이팅)
로컬: python post.py --dry-run [--track info|daily]
"""
from __future__ import annotations

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

# 실제 KST 시각 기준 발행 창. 이 안에 들어온 첫 예약 실행에서만 발행한다.
WINDOW_START = (19, 0)    # 19:00 KST
WINDOW_END = (20, 30)     # 20:30 KST (크론 지연 여유)

# 발행 기록 — 하루 1건 보장. 창 안에 여러 실행이 들어와도 두 번 올라가지 않는다.
POSTED_LOG = os.path.join(HERE, "posted_log.json")

# weekday(): 월0 화1 수2 목3 금4 토5 일6
TRACK_BY_WEEKDAY = {1: "info", 5: "info", 3: "daily"}
QUEUE_FILES = {
    "info": os.path.join(HERE, "info_queue.json"),
    "daily": os.path.join(HERE, "daily_queue.json"),
}
TRACK_LABEL = {"info": "정보성(치아관리 꿀팁)", "daily": "일상·소통", "pinned": "날짜 예약글"}

# 날짜 예약글(요일 무관, 명절 등): pinned_posts.json 의 date == 오늘 항목을 발행한다.
# 워크플로에 그 날짜 전용 크론(예: "23 10 25 9 *")을 추가하면 슬롯 검사를 건너뛰고 바로 발행한다.
PINNED_FILE = os.path.join(HERE, "pinned_posts.json")


def in_window(now: datetime) -> bool:
    """실제 KST 시각이 발행 창 안인가."""
    return WINDOW_START <= (now.hour, now.minute) <= WINDOW_END


def load_posted() -> list[dict]:
    if not os.path.exists(POSTED_LOG):
        return []
    with open(POSTED_LOG, encoding="utf-8") as f:
        return json.load(f).get("posted", [])


def mark_posted(now: datetime, track: str, item: dict, root_id: str) -> None:
    posted = load_posted()
    posted.append({
        "date": now.strftime("%Y-%m-%d"),
        "at": now.strftime("%Y-%m-%d %H:%M KST"),
        "track": track,
        "topic": item.get("topic", "-"),
        "id": root_id,
    })
    with open(POSTED_LOG, "w", encoding="utf-8") as f:
        json.dump({"posted": posted[-120:]}, f, ensure_ascii=False, indent=2)
        f.write("\n")


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


def publish(uid: str, tok: str, cid: str, tries: int = 5) -> str:
    """컨테이너를 실제 게시한다.

    컨테이너가 FINISHED 여도 publish 가 곧바로 'Media Not Found'(code 24,
    subcode 4279009) 로 실패하는 일이 있다(2026-09-17 목요일 미발행 원인).
    서버 쪽 전파 지연이라 잠깐 기다렸다 다시 부르면 대개 통과한다.
    """
    delay = 5
    for i in range(tries):
        r = requests.post(
            f"{API}/{uid}/threads_publish",
            json={"creation_id": cid, "access_token": tok},
            timeout=60,
        )
        if r.ok:
            return r.json()["id"]

        body = r.text[:400]
        try:
            err = r.json().get("error", {})
        except ValueError:
            err = {}
        transient = err.get("error_subcode") == 4279009 or err.get("is_transient") or r.status_code >= 500
        if not transient or i == tries - 1:
            sys.exit(f"[publish 실패] {r.status_code} {body}")
        print(f"  publish 일시 실패({i + 1}/{tries}), {delay}초 후 재시도: {body}")
        time.sleep(delay)
        delay *= 2
    raise AssertionError("unreachable")


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

    today = now.strftime("%Y-%m-%d")
    pinned = load_items(PINNED_FILE)
    pinned_today = [p for p in pinned if p.get("date") == today]

    # 예약 실행 게이팅 — 크론 시각이 아니라 '실제 KST 시각'으로 판단한다.
    # GitHub 크론은 수 시간까지 밀리므로, 창(19:00~20:30) 안에 들어온 첫 실행에서만 발행한다.
    # 수동 실행(workflow_dispatch)·로컬은 검사 없이 바로 진행한다.
    if os.environ.get("GITHUB_EVENT_NAME", "") == "schedule":
        already = [p for p in load_posted() if p.get("date") == today]
        if already:
            print(f"[{now:%Y-%m-%d %H:%M KST}] 오늘({today}) 이미 발행했습니다 "
                  f"({already[-1].get('at')} · {already[-1].get('topic')}). 종료합니다.")
            return
        if not in_window(now):
            print(f"[{now:%Y-%m-%d %H:%M KST}] 발행 창"
                  f"({WINDOW_START[0]:02d}:{WINDOW_START[1]:02d}~"
                  f"{WINDOW_END[0]:02d}:{WINDOW_END[1]:02d} KST) 밖입니다. 종료합니다.")
            return
        print(f"[{now:%Y-%m-%d %H:%M KST}] 발행 창 안이고 오늘 미발행. 진행합니다.")

    # 날짜 예약글이 있으면 요일 트랙보다 우선한다(명절 인사 등).
    if not track and pinned_today:
        track = "pinned"
    if not track:
        track = TRACK_BY_WEEKDAY.get(now.weekday(), "")
    if track != "pinned" and track not in QUEUE_FILES:
        print(f"[{now:%Y-%m-%d %a}] 발행 요일이 아닙니다(화·토=정보, 목=일상). 종료합니다.")
        return

    if track == "pinned":
        if not pinned_today:
            sys.exit(f"[예약글 없음] pinned_posts.json 에 {today} 항목이 없습니다.")
        path, items, item = PINNED_FILE, pinned, pinned_today[0]
    else:
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

    root_id = post_one(uid, tok, item)
    remaining = [i for i in items if i is not item]
    save_items(path, remaining)
    mark_posted(now, track, item, root_id)
    print(f"[큐] 1건 소진. 남은 글 {len(remaining)}건.")


if __name__ == "__main__":
    main()
