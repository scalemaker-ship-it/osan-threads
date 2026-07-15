# 오산디에스치과 스레드 자동화 (GitHub Actions 버전)

n8n Cloud를 대체하는 무료 자동화입니다. 매일 오전 9시(KST, 월~토)에
GitHub Actions가 클라우드에서 실행되어, Claude로 스레드 글을 작성하고 Threads에 자동 게시합니다.
**내 맥이 꺼져 있어도 동작합니다.**

## 구조

| 파일 | 역할 |
|---|---|
| `threads_post.py` | 요일별 주제 선택 → Claude 글 생성 → Threads 게시 (n8n 6단계를 그대로 이식) |
| `.github/workflows/threads-daily.yml` | 월~토 09:00 KST 크론 스케줄 |
| `requirements.txt` | 파이썬 패키지 (anthropic, requests) |

요일별 주제: 월=지역 소통 / 화=치아 상식 / 수=유아 치아 / 목=임산부 / 금=칫솔·치약 / 토=병원 홍보

## 최초 설정 (1회만)

### 1. GitHub 저장소 만들기
1. github.com 에 로그인 → **New repository** → 이름 자유(예: `osan-threads`), **Private** 권장 → Create.
2. 이 `오산스레드자동화` 폴더의 파일들을 그 저장소에 올립니다. (드래그 업로드 또는 git push)

### 2. Secrets 등록 (API 키를 코드에 넣지 않고 안전하게 보관)
저장소 → **Settings → Secrets and variables → Actions → New repository secret** 에서 3개 등록:

| 이름 | 값 |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic 콘솔의 API 키 (`console.anthropic.com`) |
| `THREADS_USER_ID` | Threads 사용자 ID |
| `THREADS_ACCESS_TOKEN` | Threads 액세스 토큰 |

> 기존 n8n에서 쓰던 값 그대로 넣으면 됩니다.

### 3. 동작 테스트
저장소 → **Actions** 탭 → "오산 스레드 자동 게시" → **Run workflow** 버튼으로 즉시 1회 실행해 봅니다.
로그에 "게시 완료"가 뜨고 Threads에 글이 올라오면 성공입니다.

### 4. n8n 결제 중지
위 테스트가 잘 되는 것을 확인한 **뒤에** `app.n8n.cloud → Settings → Billing`에서 구독을 해지하세요.

## 참고
- 모델: `claude-opus-4-8` (기존 n8n은 `claude-opus-4-5`였고 최신으로 갱신).
- Claude API는 사용량 과금이라, 이 워크플로우가 하루 1회 짧은 글만 생성하므로 비용은 매우 적습니다.
- Threads API는 무료입니다.
- 스케줄을 바꾸려면 `.github/workflows/threads-daily.yml`의 `cron` 값을 수정하세요 (UTC 기준).

## 로컬에서 직접 실행해 보려면
```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...
export THREADS_USER_ID=...
export THREADS_ACCESS_TOKEN=...
python threads_post.py
```
