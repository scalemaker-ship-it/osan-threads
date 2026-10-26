#!/bin/zsh
# 이 맥 launchd 가 화·목·토 19:00 KST 에 호출. GitHub 크론 지연 보완용.
# 원격 posted_log 에 오늘 날짜가 있으면 건너뛰고, 없으면 workflow_dispatch 로 발행 워크플로우를 깨운다.
# (post.py 도 자체적으로 '오늘 이미 발행' 검사를 하므로 이중 안전장치.)
export PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin
REPO=scalemaker-ship-it/osan-threads
LOG=$HOME/Library/Logs/osan-threads-dispatch.log
TODAY=$(TZ=Asia/Seoul date +%Y-%m-%d)
DOW=$(TZ=Asia/Seoul date +%u)   # 1=월 ... 6=토 7=일
HM=$(TZ=Asia/Seoul date +%H%M)
{
  echo "[$(date '+%F %T')] 시작 (KST $TODAY, 요일 $DOW)"
  # 잠자기에서 늦게 깨어 실행될 때 새벽 발행을 막는다: 19:00~22:00 KST 에만 호출.
  if (( HM < 1900 || HM > 2200 )); then
    echo "  허용 시간(19:00~22:00 KST) 밖($HM). 건너뜀."; exit 0
  fi
  if gh api repos/$REPO/contents/posted_log.json --jq .content 2>/dev/null | base64 -d | grep -q "\"date\": \"$TODAY\""; then
    echo "  오늘 이미 발행됨. 건너뜀."; exit 0
  fi
  if ! gh api repos/$REPO/contents/pinned_posts.json --jq .content 2>/dev/null | base64 -d | grep -q "\"date\": \"$TODAY\"" \
     && [[ "$DOW" != "2" && "$DOW" != "4" && "$DOW" != "6" ]]; then
    echo "  발행일 아님(화·목·토 또는 예약글 날짜 아님). 건너뜀."; exit 0
  fi
  if gh workflow run threads-weekly.yml -R $REPO; then
    echo "  workflow_dispatch 호출 성공."
  else
    echo "  workflow_dispatch 호출 실패(exit $?)."
  fi
} >> "$LOG" 2>&1
