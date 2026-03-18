<!--
For Chinese contributors: 請直接用中文填寫。
For English contributors: please fill in English. All fields marked (EN) accept English.
-->

## PR Type

- [ ] fix
- [ ] feat
- [ ] refactor
- [ ] docs
- [ ] chore
- [ ] test

## Background And Problem

請描述當前問題、影響範圍與觸發場景。  
*(EN) Describe the problem, its impact, and what triggers it.*

## Scope Of Change

請列出本 PR 修改的模組和檔案範圍。  
*(EN) List the modules and files changed in this PR.*

## Issue Link

必須填寫以下之一 / Fill in one of:
- `Fixes #<issue_number>`
- `Refs #<issue_number>`
- 無 Issue 時說明原因與驗收標準 / If no issue, explain the motivation and acceptance criteria

## Verification Commands And Results

請填寫你實際執行過的命令和關鍵結果（不要只寫"已測試"）。  
*(EN) Paste the commands you actually ran and their key output (don't just write "tested"):*

```bash
# example
./scripts/ci_gate.sh
python -m pytest -m "not network"
```

關鍵輸出/結論 / Key output & conclusion:

## Compatibility And Risk

請說明相容性影響、潛在風險（如無請寫 `None`）。  
*(EN) Describe compatibility impact and potential risks (write `None` if not applicable).*

## Rollback Plan

請至少寫一句可執行的回滾方案（必填）。  
*(EN) Provide at least one actionable rollback step (required).*

## EXTRACT_PROMPT Change (if applicable)

若本 PR 修改了 `src/services/image_stock_extractor.py` 中的 `EXTRACT_PROMPT`，請在此處貼上完整變更後的 prompt。  
*If this PR changes `EXTRACT_PROMPT` in `src/services/image_stock_extractor.py`, paste the full updated prompt here:*

<details>
<summary>展開 / Expand: Full EXTRACT_PROMPT</summary>

```
(paste full prompt here)
```

</details>

## Checklist

- [ ] 本 PR 有明確動機和業務價值 / This PR has a clear motivation and value
- [ ] 已提供可復現的驗證命令與結果 / Reproducible verification commands and results are included
- [ ] 已評估相容性與風險 / Compatibility and risk have been assessed
- [ ] 已提供回滾方案 / A rollback plan is provided
- [ ] 若涉及使用者可見變更，已同步更新 `README.md` 與 `docs/CHANGELOG.md` / If user-visible changes are included, `README.md` and `docs/CHANGELOG.md` are updated
