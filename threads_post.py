#!/usr/bin/env python3
"""오산디에스치과 스레드 자동 게시.

GitHub Actions 크론이 매일 저녁 17~19시(KST) 사이 여러 시간 슬롯에서 실행되며,
그중 오늘 배정된 슬롯 한 번에서만 실제로 글을 올린다(매일 발행 시각이 달라짐).
주제는 60일치 콘텐츠 캘린더를 날짜 순서대로 하나씩 돌아가며 사용한다.

흐름: 오늘 슬롯 확인 → 오늘의 주제 선택 → Claude 글 생성 → 컨테이너 생성 → 30초 대기 → 발행

환경변수(= GitHub Secrets / Actions 기본 변수):
  ANTHROPIC_API_KEY     Claude API 키                         (필수)
  THREADS_ACCESS_TOKEN  Threads 액세스 토큰                   (실제 발행 시 필수)
  THREADS_USER_ID       Threads 사용자 ID                     (선택, 없으면 "me")
  DRY_RUN               "1"/"true"면 글만 생성하고 발행은 건너뜀 (테스트용)
  GITHUB_EVENT_NAME     "schedule"/"workflow_dispatch" 등     (Actions 기본 제공)
  SCHEDULE_CRON         이 실행을 트리거한 크론 문자열         (Actions에서 주입)
"""

import hashlib
import os
import sys
import time
from datetime import date, datetime
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

# ── 60일 콘텐츠 캘린더 ──────────────────────────────────────────────
# ANCHOR 날짜부터 하루에 한 항목씩 순서대로 사용하고, 60일이 지나면 다시 처음으로 순환한다.
# 유형: [일상] 가벼운 대화 / [정보] 치과 상식 / [홍보] 병원 소개(가볍게)
ANCHOR = date(2026, 7, 17)

CALENDAR = [
    {"name": "월요일 안부 (일상)", "detail": "치과 얘기 없이, 한 주의 시작에 이웃에게 가볍게 안부를 건네고 주말 잘 보냈는지 소소하게 물어보는 수다 글."},
    {"name": "양치 타이밍 (정보)", "detail": "식후 바로보다 살짝 뒤에 양치하는 게 좋은 이유를 임팩트 있게 딱 한 줄 상식으로."},
    {"name": "오산 고기 맛집 (일상)", "detail": "오산·동탄 고기 맛집 추천을 부탁하며 오늘따라 고기가 당긴다는 소소한 기분을 곁들인 수다 글. 치과 얘기 금지."},
    {"name": "잇몸 출혈 신호 (정보)", "detail": "양치할 때 피가 나면 그냥 넘기지 말라는 잇몸 건강 경고를 짧고 임팩트 있게."},
    {"name": "커피 취향 (일상)", "detail": "원장님의 커피 취향(아아/따아 등)을 가볍게 나누고 이웃들의 취향도 물어보는 일상 수다. 치과 얘기 금지."},
    {"name": "야간진료 안내 (홍보)", "detail": "월수금 야간진료를 직장인 입장에서 유용하게 가볍게 소개. 광고 티는 최대한 빼기."},
    {"name": "동네 산책 풍경 (일상)", "detail": "오산 동네 산책이나 요즘 계절 풍경에 대한 소소한 감상을 편하게 나누는 일상 글. 치과 얘기 금지."},
    {"name": "치실 습관 (정보)", "detail": "칫솔만으로는 치아 사이가 안 닦인다는 점과 치실의 필요성을 짧게, 부담 없이."},
    {"name": "비 오는 날 칼국수 (일상)", "detail": "비 오는 날 뜨끈한 국물 생각난다며 오산 칼국수 맛집 추천을 부탁하는 수다 글. 치과 얘기 금지."},
    {"name": "유아 젖병충치 (정보)", "detail": "아기 재우며 젖병 물리는 습관이 충치를 부른다는 점을 부모님께 따뜻하게 딱 하나 팁으로."},
    {"name": "주말 계획 질문 (일상)", "detail": "다가오는 주말 계획이나 하고 싶은 것을 가볍게 나누고 팔로워들의 계획도 물어보는 일상 글. 치과 얘기 금지."},
    {"name": "스케일링 보험 (정보)", "detail": "스케일링이 1년에 한 번 건강보험 적용된다는 실용 정보를 짧고 반갑게."},
    {"name": "오산 살면서 좋은 점 (일상)", "detail": "오산에서 지내며(진료하며) 느낀 좋은 점을 솔직한 개인 생각으로 편하게 말하고 '여러분은 어떠세요?'로 마무리. 가벼운 유머(ㅎㅎ)."},
    {"name": "혀 닦기 (정보)", "detail": "입냄새의 큰 원인이 혀라는 점, 혀 닦기의 중요성을 짧고 임팩트 있게."},
    {"name": "디저트·카페 추천 (일상)", "detail": "요즘 단 게 당긴다며 오산 디저트나 카페 추천을 부탁하는 수다 글. 치과 얘기 금지."},
    {"name": "토요일 진료 안내 (홍보)", "detail": "평일에 시간 내기 힘든 분들을 위한 토요일 진료를 가볍게 소개. 광고 티 빼기."},
    {"name": "환절기 안부 (일상)", "detail": "환절기 날씨에 감기 조심하라는 따뜻한 안부를 건네는 소소한 일상 글. 치과 얘기 금지."},
    {"name": "사랑니 (정보)", "detail": "사랑니를 꼭 빼야 하는 경우와 아닌 경우를 짧고 쉽게 정리해 궁금증을 풀어주기."},
    {"name": "해장 국밥 수다 (일상)", "detail": "속 풀리는 국밥이나 해장 음식 이야기로 이웃에게 말 걸듯 추천을 부탁하는 수다 글. 치과 얘기 금지."},
    {"name": "어린이 불소·실란트 (정보)", "detail": "아이 충치 예방에 좋은 불소 도포·실란트를 부모님께 짧게 소개하는 정보 글."},
    {"name": "요즘 근황 (일상)", "detail": "요즘 보는 것이나 소소한 근황을 편하게 나누고 이웃들의 요즘은 어떤지 물어보는 일상 글. 치과 얘기 금지."},
    {"name": "시린 이 원인 (정보)", "detail": "찬물에 이가 시린 흔한 원인을 짧고 쉽게 알려주고 방치하지 말라는 팁."},
    {"name": "시장·장보기 (일상)", "detail": "오산 전통시장이나 장보기 소소한 이야기로 이웃과 수다 떠는 일상 글. 치과 얘기 금지."},
    {"name": "임산부 치과 시기 (정보)", "detail": "임신 중 안정기(4~6개월)에 치과 치료가 안전하다는 점을 따뜻하게 딱 하나 팁으로."},
    {"name": "오늘 날씨·기분 (일상)", "detail": "오늘 날씨와 기분을 원장님 시점에서 편하게 나누고 이웃들의 하루도 물어보는 일상 글. 치과 얘기 금지."},
    {"name": "교정전문의 안내 (홍보)", "detail": "교정전문의가 상주한다는 점을 안심 포인트로 가볍게 소개. 광고 티 빼기."},
    {"name": "분식·떡볶이 수다 (일상)", "detail": "갑자기 떡볶이가 당긴다며 오산 분식 맛집 추천을 부탁하는 소소한 수다 글. 치과 얘기 금지."},
    {"name": "칫솔 교체주기 (정보)", "detail": "칫솔은 3개월마다, 털이 벌어지면 바로 바꿔야 한다는 점을 짧고 임팩트 있게."},
    {"name": "운동·건강 습관 (일상)", "detail": "요즘 하는 운동이나 건강 습관을 가볍게 나누고 이웃들의 루틴을 물어보는 일상 글. 치과 얘기 금지."},
    {"name": "단 음식과 초기충치 (정보)", "detail": "단 음식 자체보다 자주 먹는 게 충치에 더 안 좋다는 상식을 짧게, 겁주지 않게."},
    {"name": "야식의 유혹 (일상)", "detail": "밤에 야식 참기 힘들다는 공감 수다로 이웃들은 어떻게 참는지 물어보는 일상 글. 치과 얘기 금지."},
    {"name": "치약 양·불소 (정보)", "detail": "치약은 콩알만큼이면 충분하고 불소 함유를 확인하라는 실용 팁을 짧게."},
    {"name": "오산 숨은 명소 (일상)", "detail": "오산에 이런 좋은 곳이 있다며 숨은 명소나 장소 추천을 이웃에게 부탁하는 수다 글. 치과 얘기 금지."},
    {"name": "이갈이·턱관절 (정보)", "detail": "자면서 이 가는 습관이 치아·턱에 주는 부담을 짧게 알려주고 방치하지 말라는 팁."},
    {"name": "제철 음식 수다 (일상)", "detail": "요즘 제철 음식이 뭐가 맛있는지 이웃과 나누며 추천을 부탁하는 일상 수다 글. 치과 얘기 금지."},
    {"name": "라미네이트 안내 (홍보)", "detail": "경기 남부 라미네이트 전문이라는 점을 가볍게 소개하되 광고 티 빼고 환자 눈높이로."},
    {"name": "아침 루틴 (일상)", "detail": "원장님의 아침 루틴을 소소하게 나누고 이웃들의 모닝 루틴을 물어보는 일상 글. 치과 얘기 금지."},
    {"name": "미백치약 오해 (정보)", "detail": "미백치약만으로 치아가 하얘지지 않는다는 오해를 짧고 솔직하게 풀어주기."},
    {"name": "카페에서 작업 (일상)", "detail": "카페에서 일하거나 쉬는 소소한 이야기로 이웃과 수다 떠는 일상 글. 치과 얘기 금지."},
    {"name": "잇몸 내려앉음 (정보)", "detail": "잇몸이 내려앉아 이가 길어 보이는 치주 문제를 짧게 알려주고 조기 관리 권하기."},
    {"name": "주말 나들이 (일상)", "detail": "주말 오산 근처 나들이 갈 만한 곳 추천을 이웃에게 부탁하는 수다 글. 치과 얘기 금지."},
    {"name": "유치 관리 (정보)", "detail": "어차피 빠질 유치도 관리가 중요한 이유를 부모님께 짧고 따뜻하게."},
    {"name": "비·눈 오는 날 감성 (일상)", "detail": "비나 눈 오는 날의 소소한 감성을 편하게 나누고 이웃들의 하루를 물어보는 일상 글. 치과 얘기 금지."},
    {"name": "정기검진 주기 (정보)", "detail": "증상 없어도 6개월마다 검진이 필요한 이유를 부담 없이 짧게."},
    {"name": "소소한 일상 (일상)", "detail": "반려동물, 화분, 취미 등 원장님의 소소한 일상 한 조각을 편하게 나누는 글. 치과 얘기 금지."},
    {"name": "임플란트 보험 상담 (홍보)", "detail": "임플란트 보험 상담이 가능한 직원이 상주한다는 점을 안심 포인트로 가볍게 소개. 광고 티 빼기."},
    {"name": "점심 메뉴 고민 (일상)", "detail": "점심 뭐 먹을지 고민이라며 이웃에게 메뉴 추천을 부탁하는 소소한 수다 글. 치과 얘기 금지."},
    {"name": "입냄새 관리 (정보)", "detail": "입냄새를 줄이는 간단한 습관(물, 혀 닦기 등) 하나를 짧게 알려주기."},
    {"name": "오산 사람들 인상 (일상)", "detail": "오산 분들이 왠지 정 많고 친절한 느낌이라는 솔직한 개인 생각을 가벼운 유머(ㅎㅎ)와 함께 나누고 '여러분은 어떠세요?'로 마무리. 치과 얘기 금지."},
    {"name": "아이 교정 시기 (정보)", "detail": "아이 교정을 언제 시작하면 좋은지 부모님이 궁금해할 포인트를 짧게 정리."},
    {"name": "퇴근길 기분 (일상)", "detail": "하루를 마치는 저녁 시간의 소소한 기분을 편하게 나누고 이웃들의 저녁을 물어보는 일상 글. 치과 얘기 금지."},
    {"name": "신경치료 오해 (정보)", "detail": "신경치료가 무조건 아프고 무섭다는 오해를 솔직하게 풀어주는 짧은 글."},
    {"name": "취미·힐링 (일상)", "detail": "요즘 힐링하는 취미를 가볍게 나누고 이웃들의 힐링 방법을 물어보는 일상 글. 치과 얘기 금지."},
    {"name": "임플란트 관리 (정보)", "detail": "임플란트도 관리가 필요하다는 점(정기 점검·양치)을 짧고 실용적으로."},
    {"name": "동네 빵집·카페 (일상)", "detail": "오산 맛있는 빵집이나 카페 추천을 이웃에게 부탁하는 소소한 수다 글. 치과 얘기 금지."},
    {"name": "직장인 야간진료 (홍보)", "detail": "퇴근 후에도 갈 수 있는 야간진료(월수금)를 직장인 눈높이로 가볍게 다시 안내. 광고 티 빼기."},
    {"name": "금요일 마무리 (일상)", "detail": "한 주 잘 버틴 이웃들에게 금요일의 소소한 응원과 안부를 건네는 일상 글. 치과 얘기 금지."},
    {"name": "투명교정 상식 (정보)", "detail": "투명교정(눈에 잘 안 띄는 교정)에 대한 짧은 상식과 장점을 부담 없이."},
    {"name": "주말 응원 (일상)", "detail": "주말엔 푹 쉬라는 따뜻한 응원과 함께 이웃들의 주말을 물어보는 일상 글. 치과 얘기 금지."},
    {"name": "치아 개수 상식 (정보)", "detail": "성인 치아 개수나 사랑니 관련 흥미로운 상식 하나를 가볍고 재밌게."},
]

# ── 발행 시간 슬롯 (KST 17~19시) ────────────────────────────────────
# GitHub Actions 크론은 UTC 기준(KST = UTC + 9). 아래 크론들을 워크플로우에 등록하고,
# 각 실행은 자신을 트리거한 크론(SCHEDULE_CRON)이 '오늘 배정된 슬롯'과 같을 때만 발행한다.
# 문자열은 워크플로우 yml의 cron 값과 정확히 일치해야 한다.
SLOT_CRONS = [
    "3 8 * * *",    # 17:03 KST
    "27 8 * * *",   # 17:27 KST
    "44 8 * * *",   # 17:44 KST
    "9 9 * * *",    # 18:09 KST
    "31 9 * * *",   # 18:31 KST
    "52 9 * * *",   # 18:52 KST
]

THREADS_API = "https://graph.threads.net/v1.0"


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(f"[오류] 환경변수 {name} 가 설정되지 않았습니다.")
    return value


def pick_topic(now: datetime) -> tuple[int, dict]:
    """오늘 날짜에 해당하는 캘린더 주제를 고른다 (60일 순환)."""
    idx = (now.date() - ANCHOR).days % len(CALENDAR)
    return idx, CALENDAR[idx]


def chosen_slot_cron(now: datetime) -> str:
    """오늘 발행할 시간 슬롯(크론 문자열)을 날짜 기반으로 결정한다 (매일 달라짐)."""
    key = now.strftime("%Y-%m-%d")
    h = int(hashlib.sha256(key.encode()).hexdigest(), 16)
    return SLOT_CRONS[h % len(SLOT_CRONS)]


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
    create = requests.post(
        f"{THREADS_API}/{user_id}/threads",
        json={"media_type": "TEXT", "text": text, "access_token": access_token},
        timeout=30,
    )
    create.raise_for_status()
    creation_id = create.json()["id"]

    time.sleep(30)  # Threads 권장 대기

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
    user_id = os.environ.get("THREADS_USER_ID") or "me"
    access_token = (
        os.environ.get("THREADS_ACCESS_TOKEN") if dry_run else require_env("THREADS_ACCESS_TOKEN")
    )

    now = datetime.now(KST)

    # 예약(schedule) 실행이면, 오늘 배정된 시간 슬롯 한 번에서만 발행한다.
    # (수동 실행·로컬 실행은 슬롯 검사 없이 바로 진행한다.)
    if os.environ.get("GITHUB_EVENT_NAME", "") == "schedule":
        target = chosen_slot_cron(now)
        current = os.environ.get("SCHEDULE_CRON", "").strip()
        if current != target:
            print(
                f"[{now:%Y-%m-%d %H:%M KST}] 오늘 발행 슬롯이 아닙니다 "
                f"(이 실행 {current!r} ≠ 오늘 배정 {target!r}). 종료합니다."
            )
            return
        print(f"[{now:%Y-%m-%d %H:%M KST}] 오늘의 발행 슬롯 {current!r} 매칭. 진행합니다.")

    idx, topic = pick_topic(now)
    print(f"[{now:%Y-%m-%d %H:%M KST}] Day {idx + 1}/{len(CALENDAR)} · 주제: {topic['name']}")

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
