# 오산디에스치과 스레드 자동화 (GitHub Actions)

**화·목·토 저녁 19~20시(KST), 하루 1건, 텍스트만(이미지 카드 없음).**
미리 작성해둔 큐에서 1건씩 꺼내 Threads에 자동 게시합니다. Anthropic 크레딧 0으로 동작하며, 내 맥이 꺼져 있어도 돌아갑니다.

- 리포지토리: `scalemaker-ship-it/osan-threads`
- 트랙(요일로 결정)

| 요일 | 트랙 | 큐 파일 | 내용 |
|---|---|---|---|
| 화·토 | `info` 정보성 | `info_queue.json` | 생활 치아관리 꿀팁. 친근한 궁금증형(제로콜라 vs 오렌지주스, 떡은 치아에 안 좋을까, 임신 중 치아관리…) |
| 목 | `daily` 일상·소통 | `daily_queue.json` | 오산/동탄/평택/수원 이웃 타겟 완전 소통글. 월수금 야간진료·토요일 진료, 병원 분위기, 동네 맛집 질문 등 |
| 그 외 | 발행 없음 | | |

- 발행 시각: 19:02·19:14·19:23·19:35·19:47·19:56 여섯 슬롯 중 날짜 해시로 하나 → 매번 분이 달라짐 (GitHub 크론 자체 지연 수 분 추가될 수 있음)
- 글 형식: 본문(`main`) + 선택 답글(`reply`, 마무리 질문·부연). 해시태그 없음, 이모지 최대 1개, 부드러운 존댓말

## 구조

| 경로 | 역할 |
|---|---|
| `post.py` | 오늘 슬롯 확인 → 요일로 트랙 결정 → 해당 큐 맨 앞 1건 게시(본문→답글) → 큐 소진 |
| `info_queue.json` | 정보성 큐 `{"items":[{"date","topic","main","reply"}]}` |
| `daily_queue.json` | 일상·소통 큐 (같은 형식) |
| `pinned_posts.json` | **날짜 예약글**(명절 등, 요일 무관). `date == 오늘` 항목을 그 날짜 전용 크론(예: `"23 10 25 9 *"` = 9/25 19:23)에서 발행. 예약글 추가 시 워크플로에 전용 크론도 함께 추가 |
| `.github/workflows/threads-weekly.yml` | 화·목·토 19시대 6슬롯 크론 + 수동 실행(드라이런·트랙 강제) |
| `archive/` | 이전 트랙(매일 17~19시 `threads_post.py`+`queue.json`, 20~22시 꿀팁 `tips/`) 보관. 워크플로 없음 = 실행 안 됨 |

## 환경변수 (= GitHub Secrets)

| 이름 | 값 | 필수 |
|---|---|---|
| `THREADS_ACCESS_TOKEN` | Threads 장기 액세스 토큰(약 60일 만료) | 실제 발행 시 |
| `THREADS_USER_ID` | Threads 사용자 ID (없으면 `me`) | ⬜ |
| `DRY_RUN` | `1`이면 출력만 하고 발행 안 함 | ⬜ |
| `TRACK_OVERRIDE` | `info`/`daily` 로 요일 판단 덮어쓰기(수동 실행용) | ⬜ |

## 테스트 / 수동 실행

```bash
# 로컬 드라이런 (자격증명 불필요)
python3 post.py --dry-run --track info
python3 post.py --dry-run --track daily

# Actions 드라이런 / 실제 발행
gh workflow run "오산 스레드 게시 (화·목·토 19시)" --repo scalemaker-ship-it/osan-threads -f dry_run=true -f track=info
gh workflow run "오산 스레드 게시 (화·목·토 19시)" --repo scalemaker-ship-it/osan-threads -f track=daily
gh run list --repo scalemaker-ship-it/osan-threads --limit 3
```
수동 실행은 슬롯 검사 없이 즉시 발행합니다. `track`을 비우면 오늘 요일로 판단하며 화·목·토가 아니면 발행하지 않습니다.

## 큐 채우기 규칙

- `date`는 표시용(발행은 항상 맨 앞부터). 화·토 날짜만 `info_queue.json`에, 목 날짜만 `daily_queue.json`에 넣어 순서가 어긋나지 않게 유지
- 정보 트랙 두 형식(`format` 필드), **월 3회는 `list`** 나머지는 `deep`
  - `deep`: 첫 줄 궁금증 훅 → 이유 2~3문장 → 실천 한 줄(본문 100~140자) → 답글에 부연+질문
  - `list`: 본문은 짧은 훅 2~3줄(40~70자)로 "댓글에 3가지 적어둘게요" 식 예고 → 답글에 `1. / 2. / 3.` 각 항목 = **결론 한 줄 + 설명 3~5줄**, 끝에 마무리 한 줄. 답글 전체 500자 이내(Threads 한도)
  - 공통: 의학적 단정("100%", "완치") 금지, 필요 시 "상담받아 보세요"로 마무리
- 일상 트랙: 치과 정보 넣지 않음. 지역명(오산·동탄·평택·수원)·계절·질문으로 댓글 유도. 병원 사실은 **월수금 야간진료·토요일 진료·교정 전문 원장** 범위 안에서만
- 잔량 확인: `python3 -c "import json;[print(f,len(json.load(open(f))['items'])) for f in ('info_queue.json','daily_queue.json')]"`
- 큐가 비면 워크플로가 실패로 표시됨(알림 겸용). 현재 큐: 2026-09-15 ~ 12-05 (12주) + 예약글 9/25 추석

## 참고

- 시간대·슬롯 변경은 `threads-weekly.yml`의 `cron`과 `post.py`의 `SLOT_CRONS`를 **같이** 수정(문자열이 정확히 일치해야 함, UTC 기준)
- Threads 토큰 만료 시 `THREADS_ACCESS_TOKEN` Secret 갱신(재발급 절차는 메모리 `osan-threads-token` 참고)
