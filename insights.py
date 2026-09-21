#!/usr/bin/env python3
"""오산디에스치과 스레드 성과 수집 — 글별 지표 + 팔로워 도시 분포.

무엇을 위해 있나:
  "반응이 없다"를 감이 아니라 숫자로 본다. 조회수는 나오는데 좋아요가 0이면 글 문제,
  조회수 자체가 두 자릿수면 도달 문제다. 처방이 정반대라 이 구분이 먼저다.

무엇을 뽑나:
  1) 글별  views / likes / replies / reposts / quotes  (graph.threads.net/{media-id}/insights)
  2) 계정  followers_count + 팔로워 도시 분포 (오산·동탄·평택·수원이 실제 몇 %인가)

결과물:
  insights.json        원자료(재분석용)
  insights_report.md   사람이 읽는 요약 — 상위/하위 글, 트랙별 평균, 도시 분포

환경변수: THREADS_ACCESS_TOKEN 필수, THREADS_USER_ID 선택(기본 "me")
로컬 실행: THREADS_ACCESS_TOKEN=... python3 insights.py
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

KST = ZoneInfo("Asia/Seoul")
HERE = os.path.dirname(os.path.abspath(__file__))
API = "https://graph.threads.net/v1.0"

POST_METRICS = "views,likes,replies,reposts,quotes"
# 우리 타겟 상권. 팔로워 도시 분포에서 이 비율이 곧 '지역 계정인가'의 답이다.
TARGET_CITIES = ("오산", "Osan", "동탄", "Dongtan", "화성", "Hwaseong",
                 "평택", "Pyeongtaek", "수원", "Suwon")


def get(path: str, tok: str, **params) -> dict:
    r = requests.get(f"{API}/{path}", params={**params, "access_token": tok}, timeout=60)
    if not r.ok:
        return {"_error": f"{r.status_code} {r.text[:300]}"}
    return r.json()


def fetch_posts(uid: str, tok: str, cap: int = 300) -> list[dict]:
    """내 글 전부(최신순). 답글도 같이 오므로 나중에 구분한다."""
    out: list[dict] = []
    params = {"fields": "id,text,timestamp,permalink,media_type,is_quote_post", "limit": 100}
    url = f"{uid}/threads"
    while url and len(out) < cap:
        data = get(url, tok, **params)
        if "_error" in data:
            sys.exit(f"[글 목록 실패] {data['_error']}")
        out.extend(data.get("data", []))
        nxt = (data.get("paging") or {}).get("cursors", {}).get("after")
        if not nxt:
            break
        params = {**params, "after": nxt}
    return out[:cap]


def post_insights(media_id: str, tok: str) -> dict:
    data = get(f"{media_id}/insights", tok, metric=POST_METRICS)
    if "_error" in data:
        return {"_error": data["_error"]}
    vals = {}
    for m in data.get("data", []):
        name = m.get("name")
        if m.get("values"):
            vals[name] = m["values"][0].get("value", 0)
        else:
            vals[name] = m.get("total_value", {}).get("value", 0)
    return vals


def follower_demographics(uid: str, tok: str) -> dict:
    """팔로워 도시 분포. 권한/최소 팔로워 수 조건을 못 채우면 에러가 나므로 그대로 담아둔다."""
    data = get(f"{uid}/threads_insights", tok,
               metric="follower_demographics", breakdown="city")
    if "_error" in data:
        return {"_error": data["_error"]}
    out: dict[str, int] = {}
    for m in data.get("data", []):
        tv = m.get("total_value", {})
        for b in tv.get("breakdowns", []):
            for r in b.get("results", []):
                key = ", ".join(r.get("dimension_values", [])) or "?"
                out[key] = r.get("value", 0)
    return out


def followers_count(uid: str, tok: str) -> int | str:
    data = get(f"{uid}/threads_insights", tok, metric="followers_count")
    if "_error" in data:
        return data["_error"]
    for m in data.get("data", []):
        return m.get("total_value", {}).get("value", 0)
    return 0


def classify(text: str) -> str:
    """본문 성격을 대충 나눠 트랙별 평균을 본다(큐 파일이 이미 소진돼 역추적이 안 되므로)."""
    t = text or ""
    if any(k in t for k in ("오산", "동탄", "평택", "수원", "오색시장", "연휴", "명절")):
        return "지역·일상"
    return "치과정보"


def main() -> None:
    tok = os.environ.get("THREADS_ACCESS_TOKEN")
    if not tok:
        sys.exit("[오류] THREADS_ACCESS_TOKEN 이 없습니다.")
    uid = os.environ.get("THREADS_USER_ID") or "me"
    now = datetime.now(KST)

    posts = fetch_posts(uid, tok)
    print(f"글 {len(posts)}건 수집. 지표 조회 중...")

    rows = []
    for p in posts:
        ins = post_insights(p["id"], tok)
        rows.append({
            "id": p["id"],
            "timestamp": p.get("timestamp", ""),
            "permalink": p.get("permalink", ""),
            "text": (p.get("text") or "").strip(),
            "kind": classify(p.get("text") or ""),
            **{k: v for k, v in ins.items() if not k.startswith("_")},
            **({"error": ins["_error"]} if "_error" in ins else {}),
        })

    demo = follower_demographics(uid, tok)
    fc = followers_count(uid, tok)

    payload = {
        "collected_at": now.strftime("%Y-%m-%d %H:%M KST"),
        "followers_count": fc,
        "follower_cities": demo,
        "posts": rows,
    }
    with open(os.path.join(HERE, "insights.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")

    write_report(payload)
    print("insights.json / insights_report.md 작성 완료")


def write_report(payload: dict) -> None:
    # 본문이 빈 항목(삭제된 글 등)은 조회수 0으로 잡혀 평균을 망친다. 제외한다.
    rows = [r for r in payload["posts"] if "error" not in r and (r.get("text") or "").strip()]
    scored = sorted(rows, key=lambda r: r.get("views", 0), reverse=True)

    def eng(r: dict) -> int:
        return r.get("likes", 0) + r.get("replies", 0) + r.get("reposts", 0) + r.get("quotes", 0)

    def line(r: dict) -> str:
        head = (r["text"].splitlines() or [""])[0][:38]
        rate = (eng(r) / r["views"] * 100) if r.get("views") else 0
        return (f"| {r['timestamp'][:10]} | {head} | {r.get('views', 0):,} | "
                f"{r.get('likes', 0)} | {r.get('replies', 0)} | {r.get('reposts', 0)} | {rate:.1f}% |")

    L = [f"# 스레드 성과 리포트", "", f"수집 시각: {payload['collected_at']}",
         f"팔로워: {payload['followers_count']}", f"분석 대상 글: {len(rows)}건", ""]

    if rows:
        tv = sum(r.get("views", 0) for r in rows)
        te = sum(eng(r) for r in rows)
        L += ["## 전체 요약", "",
              f"- 평균 조회수: **{tv / len(rows):,.0f}**",
              f"- 평균 참여(좋아요+댓글+리포스트+인용): **{te / len(rows):.1f}**",
              f"- 참여율: **{(te / tv * 100) if tv else 0:.2f}%**",
              f"- 댓글 0개인 글: **{sum(1 for r in rows if not r.get('replies'))}건 / {len(rows)}건**", ""]

        by_kind: dict[str, list] = defaultdict(list)
        for r in rows:
            by_kind[r["kind"]].append(r)
        L += ["## 성격별 평균", "", "| 성격 | 글 수 | 평균 조회 | 평균 참여 |", "|---|---|---|---|"]
        for k, v in sorted(by_kind.items()):
            L.append(f"| {k} | {len(v)} | {sum(x.get('views', 0) for x in v) / len(v):,.0f} "
                     f"| {sum(eng(x) for x in v) / len(v):.1f} |")
        L.append("")

        hdr = ["| 날짜 | 첫 줄 | 조회 | 좋아요 | 댓글 | 리포스트 | 참여율 |", "|---|---|---|---|---|---|---|"]
        L += ["## 조회수 상위 10", ""] + hdr + [line(r) for r in scored[:10]] + [""]
        L += ["## 조회수 하위 10", ""] + hdr + [line(r) for r in scored[-10:]] + [""]

    cities = payload["follower_cities"]
    L += ["## 팔로워 도시 분포", ""]
    if isinstance(cities, dict) and "_error" in cities:
        L += [f"조회 실패: `{cities['_error']}`",
              "", "(팔로워가 일정 수 미만이면 Meta가 인구통계를 주지 않습니다.)", ""]
    elif cities:
        total = sum(cities.values()) or 1
        near = sum(v for k, v in cities.items() if any(c in k for c in TARGET_CITIES))
        L += [f"**타겟 상권(오산·동탄·화성·평택·수원) 비중: {near / total * 100:.1f}%** "
              f"({near} / {total})", "", "| 도시 | 팔로워 | 비중 |", "|---|---|---|"]
        for k, v in sorted(cities.items(), key=lambda kv: kv[1], reverse=True)[:15]:
            L.append(f"| {k} | {v} | {v / total * 100:.1f}% |")
        L.append("")
    else:
        L += ["데이터 없음", ""]

    with open(os.path.join(HERE, "insights_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))


if __name__ == "__main__":
    main()
