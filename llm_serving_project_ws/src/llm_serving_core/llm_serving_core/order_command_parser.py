"""터미널 주문 문장 → order JSON 변환 (LLM 스텁용)."""

import json
import re


MENU_ALIASES: dict[str, list[str]] = {
    'coke': ['coke', '콜라', '코카콜라'],
    'water': ['water', '물', '생수'],
    'orange_juice': ['orange_juice', '오렌지주스', '오렌지'],
    'burger': ['burger', '버거', '햄버거'],
    'pizza': ['pizza', '피자'],
    'salad': ['salad', '샐러드'],
    'ice_cream': ['ice_cream', '아이스크림', '아이스'],
    'cake': ['cake', '케이크'],
}

COUNT_WORDS: dict[str, int] = {
    '한': 1,
    '하나': 1,
    '두': 2,
    '둘': 2,
    '세': 3,
    '셋': 3,
    '네': 4,
    '넷': 4,
}


def _extract_table_number(text: str) -> int | None:
    match = re.search(
        r'(?:(\d+)\s*번\s*테이블|테이블\s*(\d+)|table\s*(\d+))',
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    return int(match.group(1) or match.group(2) or match.group(3))


def _count_near_alias(text: str, alias: str) -> int:
    count_token = r'(\d+|한|하나|두|둘|세|셋|네|넷)'
    unit = r'\s*(?:개|잔|병|그릇|조각|인분)?'
    escaped = re.escape(alias)

    patterns = [
        rf'{escaped}\s*{count_token}{unit}',
        rf'{count_token}{unit}\s*{escaped}',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue

        token = match.group(1)
        if token.isdigit():
            return max(1, int(token))
        return COUNT_WORDS.get(token, 1)

    return 1


def _extract_item_counts(text: str, valid_items: set[str]) -> list[dict]:
    found: list[dict] = []
    seen: set[str] = set()
    lower = text.lower()

    for item_id, aliases in MENU_ALIASES.items():
        if item_id not in valid_items:
            continue
        for alias in aliases:
            if alias.isascii():
                if re.search(rf'\b{re.escape(alias)}\b', lower):
                    if item_id not in seen:
                        found.append({
                            'item': item_id,
                            'count': _count_near_alias(lower, alias),
                        })
                        seen.add(item_id)
                    break
            elif alias in text:
                if item_id not in seen:
                    found.append({
                        'item': item_id,
                        'count': _count_near_alias(text, alias),
                    })
                    seen.add(item_id)
                break

    return found


def _expand_items(item_counts: list[dict]) -> list[str]:
    items: list[str] = []
    for entry in item_counts:
        item = entry['item']
        count = int(entry.get('count', 1))
        items.extend([item] * max(1, count))
    return items


def _infer_table(guest_counts: list[int]) -> int | None:
    occupied = [
        i + 1 for i, count in enumerate(guest_counts) if count > 0
    ]
    if len(occupied) == 1:
        return occupied[0]
    return None


def parse_order_command(
    text: str,
    valid_items: set[str],
    guest_counts: list[int],
) -> str | None:
    """주문 문장이면 JSON 문자열, 아니면 None."""
    line = text.strip()
    if not line:
        return None

    table = _extract_table_number(line)
    if table is None:
        table = _infer_table(guest_counts)

    item_counts = _extract_item_counts(line, valid_items)
    if not item_counts:
        return None

    if table is None:
        return json.dumps(
            {
                'action': 'order',
                'intent': 'order',
                'table': None,
                'destination': 'kitchen',
                'items': _expand_items(item_counts),
                'item_counts': item_counts,
                'orders': [
                    {
                        'table': None,
                        'items': item_counts,
                    }
                ],
                'reason': 'table number is unclear',
            },
            ensure_ascii=False,
        )

    return json.dumps(
        {
            'action': 'order',
            'intent': 'order',
            'table': table,
            'destination': 'kitchen',
            'items': _expand_items(item_counts),
            'item_counts': item_counts,
            'orders': [
                {
                    'table': table,
                    'items': item_counts,
                }
            ],
            'reason': '',
        },
        ensure_ascii=False,
    )
