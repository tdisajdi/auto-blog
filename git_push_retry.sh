#!/usr/bin/env bash
# 상태 파일 저장(push)을 재시도한다(2026-11-03: 깃허브 서버 500 오류 한 번에 글 기록이 통째로 날아감).
# 다른 작업이 먼저 저장했을 수 있어 매번 최신을 받아 위에 얹은 뒤 올린다. 10·20·30·40초 쉬며 최대 5번.
for i in 1 2 3 4 5; do
  if git pull --rebase --autostash -q && git push -q; then
    exit 0
  fi
  echo "⚠️ 저장 실패($i/5) - $((i * 10))초 뒤 다시 시도"
  sleep $((i * 10))
done
exit 1
