#!/usr/bin/env python3
"""오산디에스치과 스레드 자동 게시.

n8n 워크플로우(오산디에스치과_스레드_자동화_최종.json)를 그대로 이식한 스크립트.
매일 오전 9시(KST, 월~토)에 GitHub Actions 크론으로 실행된다.

흐름: 요일별 주제 선택 → Claude로 글 생성 → Threads 컨테이너 생성 → 30초 대기 → 발행

환경변수(= GitHub Secrets):
  ANTHROPIC_API_KEY     Claude API 키
  THREADS_USER_ID       Threads 사용자 ID
  THREADS_ACCESS_TOKEN  Threads 액세스 토큰
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

SYSTEM_PROMPT = """당신은 오산디에스치과의 SNS 담당자입니다.
스레드(Threads)에 올릴 포스트를 작성합니다.

[글쓰기 규칙]
1. 부드러운 존댓말을 사용하세요.
2. 아래 4가지 후킹 방식 중 하나를 랜덤으로 선택하여 글을 시작하세요:
   - "절대 [내용]하지 마세요"
   - "제발 [내용]하세요"
   - "[내용]해야 하는 이유 N가지" 로 시작 후 1, 2, 3, 4, 5 넘버링
   - "소신발언합니다." 로 시작
3. 글자 수는 150자 내외로 작성하세요.
4. 약 15자마다 자연스럽게 줄바꿈하여 가독성을 높이세요.
5. 해시태그는 사용하지 마세요.
6. 이모지는 글 전체에 딱 1개만 사용하세요.
7. 많은 사람들이 공감할 수 있는 내용으로 작성하세요.
8. 간결하지만 임팩트 있는 글을 쓰세요. 읽는 사람이 멈추고 생각하게 만들어야 합니다.
9. 한국어로 작성하세요."""

# 요일별 주제 (isoweekday: 월=1 ... 토=6, 일=7)
TOPICS = {
    1: {
        "name": "지역 주민 소통",
        "detail": "오산, 동탄, 평택 지역 주민들과 소통하는 따뜻하고 친근한 포스트를 작성해주세요. 지역 주민들이 공감할 수 있는 내용으로, 치과에 대한 부담감을 줄여주는 이야기를 담아주세요.",
    },
    2: {
        "name": "치아 상식",
        "detail": "일반인이 잘 모르는 흥미로운 치아 상식이나 구강 건강 정보를 작성해주세요. 실용적이고 유익한 정보를 쉽게 전달해주세요.",
    },
    3: {
        "name": "유아 치아 관리",
        "detail": "영유아, 어린이 치아 관리법에 대한 유익한 포스트를 작성해주세요. 부모님들이 꼭 알아야 할 실전 팁을 포함해주세요.",
    },
    4: {
        "name": "임산부 치아 주의사항",
        "detail": "임신 중 치아 관리와 주의사항에 대한 포스트를 작성해주세요. 임산부와 태아에게 안전한 정보를 전문적이면서도 따뜻하게 전달해주세요.",
    },
    5: {
        "name": "칫솔·치약의 진실",
        "detail": "칫솔이나 치약에 대한 오해, 올바른 선택법, 사용법 등 실용적인 정보를 작성해주세요. 소비자들이 제품을 현명하게 선택하는 데 도움이 되는 내용을 포함해주세요.",
    },
    6: {
        "name": "오산디에스치과 홍보",
        "detail": "오산디에스치과를 자연스럽게 홍보하는 포스트를 작성해주세요. 주요 특징: 월수금 야간진료 운영, 토요일 진료, 교정전문의 상주, 경기 남부 라미네이트 전문, 임플란트 보험 상담 가능한 설계사 직원 상주. 광고스럽지 않고 환자 입장에서 유용하게 작성해주세요.",
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


def main() -> None:
    api_key = require_env("ANTHROPIC_API_KEY")  # noqa: F841  (SDK가 환경변수로 읽음)
    user_id = require_env("THREADS_USER_ID")
    access_token = require_env("THREADS_ACCESS_TOKEN")

    now = datetime.now(KST)
    weekday = now.isoweekday()  # 월=1 ... 일=7
    topic = TOPICS.get(weekday)
    if topic is None:
        print(f"오늘({now:%Y-%m-%d %A})은 게시일이 아닙니다. 종료합니다.")
        return

    print(f"[{now:%Y-%m-%d %H:%M KST}] 주제: {topic['name']}")
    text = generate_post(topic)
    print("=== 생성된 글 ===")
    print(text)
    print("=================")

    post_id = post_to_threads(user_id, access_token, text)
    print(f"게시 완료. Threads 게시물 ID: {post_id}")


if __name__ == "__main__":
    main()
