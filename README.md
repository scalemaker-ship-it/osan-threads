# 오산디에스치과 스레드 자동화 (GitHub Actions 버전)

n8n Cloud를 대체하는 무료 자동화입니다. **매일 저녁 5시(17:00 KST)** 에
GitHub Actions가 클라우드에서 실행되어, Claude로 스레드 글을 작성하고 Threads에 자동 게시합니다.
**내 맥이 꺼져 있어도 동작합니다.**

- 리포지토리: `scalemaker-ship-it/osan-threads`
- 스케줄: 매일 17:00 KST (`cron: "0 8 * * *"`, UTC 08:00)

## 구조

| 경로 | 역할 |
|---|---|
| `threads_post.py` | 요일별 주제 선택 → Claude 글 생성 → Threads 게시 |
| `.github/workflows/threads-daily.yml` | 매일 17:00 KST 크론 + 수동 실행(드라이런 옵션) |
| `requirements.txt` | 파이썬 패키지 (anthropic, requests) |
| `.env.example` | 로컬 실행용 환경변수 예시 |
| `legacy/` | 원본 n8n 워크플로우 JSON (참고용 보관) |

요일별 주제: 월=지역 소통 / 화=치아 상식 / 수=유아 치아 / 목=임산부 /
금=칫솔·치약 / 토=병원 홍보 / 일=주말 자가점검 (매일 발행하도록 일요일 주제 추가)

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

- 모델: `claude-opus-4-8` (기존 n8n은 `claude-opus-4-5`, 최신으로 갱신).
- Claude API는 사용량 과금이나 하루 1회 짧은 글만 생성하므로 비용은 매우 적습니다. Threads API는 무료.
- 스케줄 변경은 `.github/workflows/threads-daily.yml`의 `cron` 값 수정 (UTC 기준, KST −9시간).
- Threads 액세스 토큰은 만료될 수 있습니다(장기 토큰 약 60일). 만료 시 Secret을 갱신하세요.
