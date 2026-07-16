# 오산디에스치과 스레드 자동화 (GitHub Actions 버전)

**매일 저녁 17~19시(KST) 사이 매번 다른 시각**에 GitHub Actions가 클라우드에서 실행되어,
Claude로 스레드 글을 작성하고 Threads에 자동 게시하는 무료 자동화입니다.
**내 맥이 꺼져 있어도 동작합니다.**

- 리포지토리: `scalemaker-ship-it/osan-threads`
- 스케줄: 매일 1회, 17~19시 KST 6개 슬롯(17:03·17:27·17:44·18:09·18:31·18:52) 중 날짜별로 하나
- 콘텐츠: 60일치 주제 캘린더를 날짜 순서대로 하나씩 순환 (일상 30 · 정보 24 · 홍보 6)

## 구조

| 경로 | 역할 |
|---|---|
| `threads_post.py` | 오늘 슬롯 확인 → 60일 캘린더에서 오늘 주제 선택 → Claude 글 생성 → Threads 게시 |
| `.github/workflows/threads-daily.yml` | 17~19시 6개 슬롯 크론 + 수동 실행(드라이런 옵션) |
| `requirements.txt` | 파이썬 패키지 (anthropic, requests) |
| `.env.example` | 로컬 실행용 환경변수 예시 |

### 발행 시각이 매일 달라지는 방식
비공개 레포라 Actions 사용시간을 아끼기 위해, 긴 `sleep` 대신 **여러 시간 슬롯을 크론으로 등록**하고
스크립트가 날짜 해시로 오늘의 슬롯 하나만 골라 그때만 발행합니다(`SCHEDULE_CRON`으로 판별).
나머지 슬롯 실행은 몇 초 만에 종료됩니다.

## 환경변수 (= GitHub Secrets)

| 이름 | 값 | 필수 |
|---|---|---|
| `ANTHROPIC_API_KEY` | Anthropic 콘솔 API 키 (`console.anthropic.com`) | ✅ |
| `THREADS_USER_ID` | Threads 사용자 ID | 실제 발행 시 |
| `THREADS_ACCESS_TOKEN` | Threads 장기(long-lived) 액세스 토큰 | 실제 발행 시 |
| `DRY_RUN` | `1`이면 글만 생성하고 발행은 건너뜀 (테스트용) | ⬜ |

> 세 Secret은 리포지토리 → **Settings → Secrets and variables → Actions → New repository secret** 에 등록합니다.

## 동작 테스트

리포지토리 → **Actions** 탭 → "오산 스레드 자동 게시" → **Run workflow**:
- **드라이런 체크 ON**: `ANTHROPIC_API_KEY`만 있으면 글 생성까지만 검증 (Threads 발행 안 함).
- **드라이런 OFF**: 세 Secret이 모두 있어야 실제로 Threads에 게시됩니다.

로그에 "게시 완료. Threads 게시물 ID: ..."가 뜨면 성공입니다.

CLI로도 가능:
```bash
# 드라이런
gh workflow run "오산 스레드 자동 게시" --repo scalemaker-ship-it/osan-threads -f dry_run=true
# 실제 발행
gh workflow run "오산 스레드 자동 게시" --repo scalemaker-ship-it/osan-threads
# 결과 확인
gh run list --repo scalemaker-ship-it/osan-threads --limit 3
```

## 로컬에서 직접 실행

```bash
cp .env.example .env      # 값 채우기
pip install -r requirements.txt
set -a && source .env && set +a
python threads_post.py
```
`DRY_RUN=1`을 넣으면 Threads 자격증명 없이 글 생성만 확인할 수 있습니다.

## 참고

- 모델: `claude-opus-4-8`.
- Claude API는 사용량 과금이나 하루 1회 짧은 글만 생성하므로 비용은 매우 적습니다. Threads API는 무료.
- 시간대·슬롯 변경은 `.github/workflows/threads-daily.yml`의 `cron` 값과 `threads_post.py`의 `SLOT_CRONS`를 **같이** 수정 (문자열이 정확히 일치해야 함, UTC 기준).
- 주제 캘린더는 `threads_post.py`의 `CALENDAR`(60개) 수정. 시작일은 `ANCHOR`.
- Threads 액세스 토큰은 약 60일 후 만료됩니다(60일치 캘린더와 주기가 맞음). 만료 시 `THREADS_ACCESS_TOKEN` Secret을 갱신하세요.
