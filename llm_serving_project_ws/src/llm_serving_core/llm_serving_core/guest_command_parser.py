"""자연어/간단 명령 → guest_command JSON 변환."""

import json
import re


def parse_guest_command(text: str) -> str | None:
    """손님 관련 명령이면 JSON 문자열, 아니면 None."""
    line = text.strip()
    if not line:
        return None

    # 테이블 상태 조회
    if re.search(r'(테이블\s*상태|table\s*status)', line, re.IGNORECASE):
        return json.dumps({'event': 'status'}, ensure_ascii=False)

    # N번 테이블 퇴장 / 비움
    leave_match = re.search(
        r'(?:(\d+)\s*번\s*테이블|table\s*(\d+)).*(?:퇴장|비움|나감|leave|clear)',
        line, re.IGNORECASE)
    if leave_match:
        table = int(leave_match.group(1) or leave_match.group(2))
        return json.dumps({'event': 'leave', 'table': table}, ensure_ascii=False)

    # N번 테이블에 손님 M명
    seat_specific = re.search(
        r'(?:(\d+)\s*번\s*테이블|table\s*(\d+)).*?(?:손님\s*)?(\d+)\s*명',
        line, re.IGNORECASE)
    if seat_specific:
        table = int(seat_specific.group(1) or seat_specific.group(2))
        count = int(seat_specific.group(3))
        return json.dumps(
            {'event': 'arrive', 'count': count, 'table': table},
            ensure_ascii=False)

    # 손님 M명 입장 (자동 배정)
    arrive_match = re.search(
        r'(?:손님\s*)?(\d+)\s*명.*(?:입장|도착|왔|arrive|seat)|'
        r'(?:seat|guest)\s*(\d+)',
        line, re.IGNORECASE)
    if arrive_match:
        count = int(arrive_match.group(1) or arrive_match.group(2))
        return json.dumps({'event': 'arrive', 'count': count}, ensure_ascii=False)

    return None
