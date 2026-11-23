#!/usr/bin/env bash
# 失敗就重試：tools/retry.sh <次數> <第一次等待秒數> <指令...>
# 失敗後等「秒數 × 第幾次」再試（例：3 30 → 失敗後等 30 秒、再失敗等 60 秒）；全部失敗回傳最後一次的 exit code。
set -u
if [ "$#" -lt 3 ]; then echo "用法：tools/retry.sh <次數> <第一次等待秒數> <指令...>" >&2; exit 2; fi
n="$1"; wait="$2"; shift 2
i=1
while :; do
  "$@"; rc=$?
  if [ "$rc" -eq 0 ]; then exit 0; fi
  if [ "$i" -ge "$n" ]; then echo "第 $i 次失敗（exit $rc），已達 $n 次，不再重試" >&2; exit "$rc"; fi
  s=$((wait * i))
  echo "第 $i 次失敗（exit $rc），$s 秒後重試" >&2
  sleep "$s"
  i=$((i + 1))
done
