#!/usr/bin/env python3
"""오산디에스치과 스레드 자동 게시.

매일 저녁 5시(KST)에 GitHub Actions 크론으로 실행되는 스크립트.

흐름: 요일별 주제 선택 → Claude로 글 생성 → Threads 컨테이너 생성 → 30초 대기 → 발행

환경변수(= GitHub Secrets):
  ANTHROPIC_API_KEY     Claude API 키              (필수)
  THREADS_USER_ID       Threads 사용자 ID          (실제 발행 시 필수)
  THREADS_ACCESS_TOKEN  Threads 액세스 토큰        (실제 발행 시 필수)
  DRY_RUN               "1"/"true"면 글만 생성하고 Threads 발행은 건너뜀 (테스트용)
"""

import os
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import anthropic
import requests

KST = ZoneInfo("Asia/Seoul")
MODEL = "claude-opus-4-8"

SYSTEM_PROMPT = """당신은 오산에서 오래 진료해온 친근한 동네 치과(오산디에스치과) 원장님의 SNS 담당자입니다.
원장님이 이웃에게 말을 걸듯, 스레드(Threads)에 올릴 아주 짧은 글을 씁니다.

[글쓰기 규칙]
1. 부드럽고 친근한 존댓말을 사용하세요.
2. 글자 수는 70자 내외로 아주 짧게 쓰세요. 길어도 90자를 넘기지 마세요.
3. 약 12~15자마다 자연스럽게 줄바꿈하여 가독성을 높이세요.
4. 해시태그는 쓰지 마세요. 이모지는 최대 1개까지만.
5. 사람들이 댓글을 달고 싶어지게, 질문이나 공감 포인트로 마무리하면 좋습니다.
6. 정보성 글이면 첫 문장을 임팩트 있게(예: "절대 ~하지 마세요", "제발 ~하세요", "소신발언합니다.").
   일상 대화 글이면 후킹을 억지로 넣지 말고, 편하게 수다 떨듯 자연스럽게 쓰세요.
7. 가끔 "ㅎㅎ" 같은 가벼운 표현이나 솔직한 개인 생각을 넣어 사람 냄새를 더하세요.
8. 한국어로 작성하세요."""

# 요일별 주제 (isoweekday: 월=1 ... 토=6, 일=7)
# 정보성 글(화·목·토) + 가벼운 일상 대화 글(월·수·금·일)을 섞어 배치.
TOPICS = {
    1: {
        "name": "소소한 안부·질문 (일상)",
        "detail": "치과 이야기 없이, 오산 이웃에게 가볍게 안부를 건네는 일상 대화 글을 써주세요. 날씨·요일·계절·요즘 근황 같은 소재로 수다 떨듯 편하게, 소소한 질문으로 마무리해 댓글을 유도하세요. 예시 톤: '한 주 시작이네요. 다들 주말 잘 보내셨어요?'",
    },
    2: {
        "name": "치아 상식 (정보)",
        "detail": "일반인이 잘 모르는 흥미로운 치아 상식이나 구강 건강 정보를 딱 하나만, 아주 짧고 쉽게 알려주세요. 첫 문장을 임팩트 있게 시작하세요.",
    },
    3: {
        "name": "오산 맛집·음식 수다 (일상)",
        "detail": "치과 이야기 없이, 오산·동탄 지역 맛집이나 오늘 먹고 싶은 음식을 소재로 이웃에게 말 걸듯 가볍게 수다를 떠는 글을 써주세요. 추천을 부탁하는 질문으로 댓글을 유도하고, 원장님의 소소한 취향이나 기분을 살짝 곁들이세요. 예시 톤: '오산 고기 맛집 추천 받아요. 오늘따라 고기가 당기는 날이네요.'",
    },
    4: {
        "name": "임산부·유아 치아 관리 (정보)",
        "detail": "임산부 또는 영유아·어린이 치아 관리 팁을 딱 하나만, 부모님이 바로 실천할 수 있게 짧고 따뜻하게 알려주세요.",
    },
    5: {
        "name": "오산 동네 이야기 (일상)",
        "detail": "오산에서 진료하며(살며) 느낀 좋은 점이나 동네의 매력을, 솔직한 개인 생각으로 편하게 이야기하고 '여러분은 어떠세요?' 하고 질문으로 마무리하는 글을 써주세요. 소탈한 개인 의견과 가벼운 유머(ㅎㅎ)를 넣으세요. 예시 톤: '오산 분들이 왠지 좀 친절한 느낌...? 네, 전적으로 제 개인적인 생각입니다 ㅎㅎ'",
    },
    6: {
        "name": "오산디에스치과 홍보 (정보)",
        "detail": "오산디에스치과를 자연스럽고 가볍게 알리는 짧은 글을 써주세요. 특징 중 한두 개만 골라 환자 입장에서 유용하게: 월수금 야간진료, 토요일 진료, 교정전문의 상주, 경기 남부 라미네이트 전문, 임플란트 보험 상담 직원 상주. 광고 티는 최대한 빼세요.",
    },
    7: {
        "name": "주말·오늘 기분 (일상)",
        "detail": "치과 이야기 없이, 오늘이나 주말의 소소한 계획·기분을 원장님 시점에서 편하게 나누고, 팔로워들의 하루도 물어보는 일상 대화 글을 써주세요. 부담 없이 대화하듯, 사람 냄새나게.",
    },
}

THREADS_API = "https://graph.threads.net/v1.0"


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(f"[오류] 환경변수 {name} 가 설정되지 않았습니다.")
    return value


def generate_post(topic: dict) -> str:
    """Claude로 스레드 글을 생성한다."""
    client = anthropic.Anthropic()  # ANTHROPIC_API_KEY 환경변수 자동 사용
    user_message = (
        f"오늘의 주제: {topic['name']}\n\n"
        f"요청사항: {topic['detail']}\n\n"
        "위 글쓰기 규칙을 반드시 지켜서 스레드 포스트를 작성해주세요."
    )
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )
    text = next((b.text for b in response.content if b.type == "text"), "").strip()
    if not text:
        sys.exit("[오류] Claude 응답에서 본문 텍스트를 찾지 못했습니다.")
    return text


def post_to_threads(user_id: str, access_token: str, text: str) -> str:
    """Threads 컨테이너 생성 → 30초 대기 → 발행. 게시물 ID 반환."""
    # 1) 컨테이너 생성
    create = requests.post(
        f"{THREADS_API}/{user_id}/threads",
        json={"media_type": "TEXT", "text": text, "access_token": access_token},
        timeout=30,
    )
    create.raise_for_status()
    creation_id = create.json()["id"]

    # 2) 30초 대기 (Threads 권장)
    time.sleep(30)

    # 3) 발행
    publish = requests.post(
        f"{THREADS_API}/{user_id}/threads_publish",
        json={"creation_id": creation_id, "access_token": access_token},
        timeout=30,
    )
    publish.raise_for_status()
    return publish.json()["id"]


def is_dry_run() -> bool:
    return os.environ.get("DRY_RUN", "").strip().lower() in {"1", "true", "yes", "y"}


def main() -> None:
    dry_run = is_dry_run()

    require_env("ANTHROPIC_API_KEY")  # SDK가 환경변수로 읽음
    # 사용자 ID는 액세스 토큰만 있으면 "me" 별칭으로 대체 가능 (Threads Graph API).
    # 따라서 실제 발행에 필수인 시크릿은 THREADS_ACCESS_TOKEN 하나뿐이다.
    user_id = os.environ.get("THREADS_USER_ID") or "me"
    access_token = (
        os.environ.get("THREADS_ACCESS_TOKEN") if dry_run else require_env("THREADS_ACCESS_TOKEN")
    )

    now = datetime.now(KST)
    weekday = now.isoweekday()  # 월=1 ... 일=7
    topic = TOPICS.get(weekday)
    if topic is None:  # 모든 요일 주제가 정의돼 있어 정상적으로는 도달하지 않음
        print(f"오늘({now:%Y-%m-%d %A})은 게시일이 아닙니다. 종료합니다.")
        return

    print(f"[{now:%Y-%m-%d %H:%M KST}] 주제: {topic['name']}")
    text = generate_post(topic)
    print("=== 생성된 글 ===")
    print(text)
    print("=================")

    if dry_run:
        print("[DRY_RUN] Threads 발행을 건너뜁니다. (글 생성까지만 검증)")
        return

    post_id = post_to_threads(user_id, access_token, text)
    print(f"게시 완료. Threads 게시물 ID: {post_id}")


if __name__ == "__main__":
    main()
