#!/bin/bash
# Pre-commit hook — 提交前检查

set -e

echo "[Hook] 运行 pre-commit 检查..."

# 1. 检查是否有 .env 文件被意外提交
if git diff --cached --name-only | grep -q "\.env$"; then
    echo "[Error] 检测到 .env 文件！请勿提交敏感信息。"
    exit 1
fi

# 2. 检查 JSON 格式
for f in $(git diff --cached --name-only -- '*.json'); do
    if [ -f "$f" ]; then
        python3 -m json.tool "$f" > /dev/null 2>&1 || {
            echo "[Error] JSON 格式错误: $f"
            exit 1
        }
    fi
done

# 3. 运行安全模块的基础测试
if command -v pytest &> /dev/null; then
    pytest tests/eval_test.py::TestSecurity -x -q 2>/dev/null || {
        echo "[Warning] 安全测试未通过，请检查"
    }
fi

echo "[Hook] pre-commit 检查通过"
