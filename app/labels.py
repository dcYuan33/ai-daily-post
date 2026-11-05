from __future__ import annotations

CATEGORY_LABELS = {
    "模型与研究": "Models & Research",
    "产品与开发者工具": "Products & Developer Tools",
    "公司与资本": "Companies & Capital",
    "芯片与基础设施": "Compute & Infrastructure",
    "政策与监管": "Policy & Regulation",
    "安全与社会影响": "Security & Society",
    "开源生态": "Open Source Ecosystem",
    "其他": "Other",
    "Models & Research": "Models & Research",
    "Products & Developer Tools": "Products & Developer Tools",
    "Companies & Capital": "Companies & Capital",
    "Compute & Infrastructure": "Compute & Infrastructure",
    "Policy & Regulation": "Policy & Regulation",
    "Security & Society": "Security & Society",
    "Open Source Ecosystem": "Open Source Ecosystem",
    "Other": "Other",
}

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
WEEKDAY_ABBR = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")


def category_label(value: str) -> str:
    return CATEGORY_LABELS.get(value, value)
