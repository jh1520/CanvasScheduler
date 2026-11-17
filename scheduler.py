from canvasapi import Canvas
from canvasapi.exceptions import CanvasException
import datetime
import re
import sys
import Keys

# 한국 시간 (한국은 서머타임이 없어서 +9시간 고정으로 충분함)
KST = datetime.timezone(datetime.timedelta(hours=9), 'KST')

# 어떤 날짜를 썼는지 일정 제목 뒤에 붙일 표시
TAGS = {
    'due': '',                  # 교수님이 마감일을 지정한 과제
    'lock': ' (종료일 기준)',    # 마감일 없이 제출 종료만 걸린 과제
    'unlock': ' (열림)',         # 열리는 시각만 있는 과제 (수업 중 퀴즈 등)
}


def parseDate(text):
    """Canvas의 UTC 시간 문자열(예: 2026-09-15T14:59:59Z)을 한국 시간으로 변환"""
    if not text:
        return None
    utc = datetime.datetime.fromisoformat(text.replace('Z', '+00:00'))
    return utc.astimezone(KST)


def pickDate(assignment):
    """마감일 → 제출 종료일 → 열리는 시각 순서로, 처음 있는 날짜를 사용"""
    for field, kind in (('due_at', 'due'), ('lock_at', 'lock'), ('unlock_at', 'unlock')):
        date = parseDate(getattr(assignment, field, None))
        if date:
            return date, kind
    return None, None


def shortName(courseName):
    """'딥러닝 01분반_주_2026201808' → '딥러닝' 처럼 분반 정보를 잘라 냄"""
    short = re.sub(r'\s*\(?\d+분반.*$', '', courseName).strip()
    return short or courseName


def getAssignments(includePast=False):
    API_URL, API_KEY = Keys.getAPIinfo()
    canvas = Canvas(API_URL, API_KEY)
    now = datetime.datetime.now(KST)

    assignments = []  # 캘린더에 넣을 과제
    undated = []      # 날짜 정보가 하나도 없는 과제

    # 원본: get_upcoming_events() → 마감일(due_at)이 있는 과제만 나옴
    # 개선: 이번 학기 과목을 모두 돌면서 과제 목록을 직접 가져옴
    for course in canvas.get_courses(enrollment_state='active'):
        label = shortName(getattr(course, 'name', str(course.id)))
        try:
            courseAssignments = list(course.get_assignments())
        except CanvasException as error:
            print('과제를 가져오지 못한 과목:', label, error)
            continue

        for a in courseAssignments:
            date, kind = pickDate(a)
            if date is None:
                undated.append((label, a.name))
            elif includePast or date >= now:
                assignments.append({'course': label, 'name': a.name, 'date': date, 'kind': kind})

    assignments.sort(key=lambda x: x['date'])
    return assignments, undated


def grabDescriptions(googCalendar):
    events = googCalendar.getEvents()
    descs = []
    for event in events:
        # 원본 버그: 캘린더에 앞으로의 일정이 없으면 getEvents()가 문자열을 돌려줘서 여기서 멈춤
        if not isinstance(event, dict):
            continue
        try:
            if event['description'] != 'description' and 'confidentiality notice' not in event['description'].lower():
                descs.append(event['description'])
        except KeyError:
            pass
    return descs


def main():
    dryRun = '--dry-run' in sys.argv   # 구글 캘린더에 넣지 않고 화면에만 출력
    includePast = '--all' in sys.argv  # 이미 지난 과제도 포함 (--dry-run과 함께 확인용으로 사용)

    assignments, undated = getAssignments(includePast)

    if dryRun:
        print(f'\n[테스트 모드] 캘린더에 등록할 과제 {len(assignments)}개')
        for a in assignments:
            print(f"  {a['date']:%m/%d %H:%M}  [{a['course']}] {a['name']}{TAGS[a['kind']]}")
    else:
        import googCalendar  # 구글 라이브러리는 실제로 등록할 때만 불러옴
        descs = grabDescriptions(googCalendar)
        for a in assignments:
            if a['name'] in descs:
                print('already made:', a['name'])
                continue
            if a['kind'] == 'unlock':
                start, end = a['date'], a['date'] + datetime.timedelta(minutes=30)
            else:
                start, end = a['date'] - datetime.timedelta(hours=1), a['date']
            summary = f"[{a['course']}] {a['name']}{TAGS[a['kind']]}"
            googCalendar.createEvent(summary, start.isoformat(), end.isoformat(),
                                     description=a['name'], timeZone='Asia/Seoul')

    if undated:
        print(f'\n날짜 미정 과제 {len(undated)}개 (캘린더에 등록하지 않음)')
        for course, name in undated:
            print(f'  [{course}] {name}')


if __name__ == '__main__':
    main()
