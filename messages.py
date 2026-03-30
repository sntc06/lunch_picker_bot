# messages.py — all user-facing strings in Traditional Chinese (zh-TW, 繁體中文)
# No Simplified Chinese characters. Taiwan-region phrasing throughout.

ADD_SUCCESS = "✅ 已新增餐廳：{name}"
ADD_DUPLICATE = "⚠️ 「{name}」已在清單中了。"
ADD_USAGE = "用法：/add <餐廳名稱> [餐廳名稱2 ...] 使用空格分隔"
ADD_INVALID_NAME = "⚠️ 餐廳名稱格式不正確，名稱不可包含換行或斜線：{name}"

REMOVE_SUCCESS = "✅ 已移除餐廳：{name}"
REMOVE_NOT_FOUND = "⚠️ 找不到「{name}」，請確認名稱是否正確。"
REMOVE_USAGE = "用法：/remove <餐廳名稱>"

REMOVEALL_CONFIRM = "⚠️ 確定要清空整個餐廳清單嗎？"
REMOVEALL_YES = "是，清空"
REMOVEALL_NO = "否，取消"
REMOVEALL_SUCCESS = "✅ 已清空餐廳清單。"
REMOVEALL_CANCEL = "已取消，清單保持不變。"
REMOVEALL_EMPTY = "清單已經是空的了。"

ROLL_RESULT = "🎲 今天去吃：{name}"
ROLL_EMPTY = "清單是空的，請先用 /add 新增餐廳。"

LIST_HEADER = "📋 目前的餐廳清單：\n{items}"
LIST_ITEM = "{index}. {name}（由 {added_by} 於 {added_at} 新增）"
LIST_EMPTY = "清單是空的，請先用 /add 新增餐廳。"

STORAGE_ERROR = "⚠️ 操作失敗，請稍後再試。"

HELP_TEXT = (
    "可用指令：\n"
    "/add <餐廳名稱> [餐廳名稱2 ...] — 新增一或多間餐廳\n"
    "/remove <餐廳名稱> — 移除餐廳\n"
    "/removeall — 清空整個清單\n"
    "/list — 查看清單\n"
    "/roll — 隨機選一間"
)
