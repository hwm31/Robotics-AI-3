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


def _extract_table_number(text: str) -> int | None:
    match = re.search(
        r'(?:(\d+)\s*번\s*테이블|테이블\s*(\d+)|table\s*(\d+))',
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    return int(match.group(1) or match.group(2) or match.group(3))


def _extract_items(text: str, valid_items: set[str]) -> list[str]:
    found: list[str] = []
    lower = text.lower()

    for item_id, aliases in MENU_ALIASES.items():
        if item_id not in valid_items:
            continue
        for alias in aliases:
            if alias.isascii():
                if re.search(rf'\b{re.escape(alias)}\b', lower):
                    if item_id not in found:
                        found.append(item_id)
                    break
            elif alias in text:
                if item_id not in found:
                    found.append(item_id)
                break

    return found


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

    items = _extract_items(line, valid_items)
    if not items:
        return None

    if table is None:
        return json.dumps(
            {
                'action': 'unknown',
                'table': 0,
                'destination': 'kitchen',
                'items': items,
                'reason': 'table number is unclear',
            },
            ensure_ascii=False,
        )

    return json.dumps(
        {
            'action': 'order',
            'table': table,
            'destination': 'kitchen',
            'items': items,
            'reason': '',
        },
        ensure_ascii=False,
    )
