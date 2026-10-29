"""Explicit transcription of user images; no OCR or fuzzy runtime matching.

Run only when updating the reviewed transcription. Base JSONs remain untouched.
Each dependency below was entered separately; uncertain paths stay under review.
"""
import json
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT.parent / 'data'


def build(chart, image, rows, slots):
    base = json.loads((DATA / (chart + '.json')).read_text(encoding='utf-8'))['sheets']['courses']
    by_code = {c['course_code']: c for c in base if c.get('course_code')}
    nodes = []
    for row in rows:
        # term, base code, PRE codes, CO codes, optional overrides
        term, code, pre, co, *options = row
        override = options[0] if options else {}
        original = by_code.get(code)
        if original is None:
            assert override.get('course_name') and override.get('credits') is not None, code
        c = {k: original.get(k) for k in ('course_id','course_name','credits','course_type')} if original else {
            'course_id': f'VIS{image}-{code}', 'course_type': 'O'}
        c.update(course_code=code, suggested_semester=term, prerequisites=pre.split() if pre else [],
                 corequisites=co.split() if co else [], relationships_complete=True,
                 code_source='image' if image != 2 else 'existing_json_unverified_by_image',
                 source_image=f'image-{image}.png')
        c.update(override)
        c['base_course_code'] = code
        nodes.append(c)
    return {'chart': chart, 'image': f'image-{image}.png', 'sha256': hashlib.sha256((ROOT / f'image-{image}.png').read_bytes()).hexdigest(),
            'entry_year_from': {'1395-1400':1395,'1401-1402':1401,'1403-plus':1403}[chart],
            'entry_year_to': {'1395-1400':1400,'1401-1402':1402,'1403-plus':None}[chart],
            'year_source': 'user_confirmation_2026-10-28' if image == 2 else 'image_title',
            'nodes': nodes, 'slots': slots}


charts = []
charts.append(build('1401-1402', 1, [
    (1,'30004','','30005'), (1,'30005','','30004'), (1,'1107','',''), (1,'2101','',''),
    (1,'271477','',''), (1,'1101','',''), (1,'1109','',''), (1,'30001','',''),
    (2,'30006','2101 30004',''), (2,'30007','30004','30008'), (2,'30008','','30007'),
    (2,'2102','2101',''), (2,'231480','271477',''), (2,'30003','',''),
    (2,'1110','1109',''), (2,'30002','30001',''),
    (3,'30009','','30006 30010'), (3,'30010','','30009'), (3,'30011','30006 30007',''),
    (3,'2135','2101',''), (3,'30012','231480','2135 30013'), (3,'30013','','30012'),
    (3,'231484','231480',''), (3,'30014','30002',''), (3,'1102','1101',''),
    (4,'30015','30009','30016'), (4,'30016','','30015'), (4,'30017','30011',''),
    (4,'271463','2102',''), (4,'30018','2102',''), (4,'30029','30011 30006',''),
    (4,'272479','',''),
    (5,'30019','30015','30020'), (5,'30020','','30019'), (5,'30021','30015','30022'),
    (5,'30022','','30021'), (5,'30030','30011',''),
    (5,'30023','30015 271463','30021 30024'), (5,'30024','','30023'),
    (6,'30037','2135',''), (6,'30051','30011','30018'), (6,'30052','30029',''),
    (6,'30025','30007',''),
    (6,'30045','','', {'course_code':'30128','course_name':'برنامه‌نویسی وب','relationships_complete':False,
                       'review_reason':'کد تصویر 30128 با کد 30045 داده قبلی متفاوت است؛ مسیر پیش‌نیاز در تصویر نیازمند بررسی است'}),
    (6,'30026','30014','', {'minimum_semester':5,'course_name':'روش پژوهش و ارائه'}),
    (6,'30027','30026','', {'minimum_semester':7,'course_name':'کارآموزی'}),
    (7,'30054','30052',''), (7,'30035','30025',''), (7,'30033','30025',''),
    (7,'1139','',''), (7,'30028','30026',''),
    (8,'30036','30011 271463',''), (8,'30055','30037',''), (8,'1124','',''),
], [
    {'suggested_semester':5,'name':'انقلاب اسلامی / اندیشه سیاسی امام','kind':'alternative','course_codes':['272481','272459']},
    {'suggested_semester':6,'name':'تاریخ تحلیلی اسلام / تاریخ امامت','kind':'alternative','course_codes':['272483','272461']},
    {'suggested_semester':7,'name':'کنترل پروژه / کسب و کار نوپا','kind':'unresolved_option'},
    {'suggested_semester':7,'name':'مباحث ویژه / مبانی امنیت اطلاعات','kind':'unresolved_option'},
    {'suggested_semester':8,'name':'کنترل پروژه / کسب و کار نوپا','kind':'unresolved_option'},
    {'suggested_semester':8,'name':'اختیاری به انتخاب دانشجو','kind':'unresolved_option'},
]))

charts.append(build('1403-plus', 2, [
    (1,'SCI-106','',''), (1,'SCI-101','',''), (1,'CSE-102','','', {'credits':1}),
    (1,'CSE-100','','', {'credits':2}), (1,'CSE-101','',''),
    (2,'SCI-107','SCI-106',''), (2,'SCI-102','SCI-101',''), (2,'SCI-113','','', {'credits':2}),
    (2,'CSE-104','',''), (2,'CSE-106','CSE-101',''), (2,'CSE-103','',''),
    (3,'SCI-110','SCI-107',''), (3,'SCI-103','','SCI-102'),
    (3,'CSE-105','CSE-104',''), (3,'CSE-111','CSE-104',''), (3,'CSE-150','CSE-106',''),
    (3,'CSE-110','CSE-103','CSE-106'),
    (3,'CSE-107','CSE-102','', {'requires_unresolved_reference':'زبان انگلیسی؛ کد در تصویر درج نشده است'}),
    (4,'SCI-104','SCI-101',''), (4,'CSE-108','SCI-103 SCI-107',''),
    (4,'CSE-112','CSE-105 CSE-111',''), (4,'CSE-113','','CSE-111'),
    (4,'CSE-115','SCI-102',''), (4,'CSE-114','CSE-110',''),
    (5,'CSE-116','SCI-104 CSE-110',''), (5,'CSE-109','CSE-108',''),
    (5,'CSE-118','CSE-110 CSE-111',''), (5,'CSE-117','CSE-111',''),
    (5,'CSE-120','CSE-107','', {'credits':2}),
    (6,'CSE-119','CSE-118',''), (6,'CSE-122','','CSE-118'),
    (6,'CSE-121','CSE-120',''), (7,'CSE-123','CSE-122',''), (7,'CSE-124','CSE-122',''),
    (7,'CSE-200','CSE-120','', {'credits':2}),
    (8,'UNRESOLVED-PROJECT','CSE-120','', {'course_code':None,'course_name':'پروژه کارشناسی','credits':3,'course_type':'T',
                                          'requires_unresolved_reference':'کد درس پروژه در تصویر و داده قبلی موجود نیست'}),
], [
    *[{'suggested_semester':t,'name':'معارف اسلامی','kind':'unresolved_option'} for t in (1,4,5,6,7,8)],
    {'suggested_semester':1,'name':'زبان انگلیسی','kind':'missing_code'},
    {'suggested_semester':1,'name':'تربیت بدنی','kind':'missing_code'},
    {'suggested_semester':2,'name':'ورزش ۱','kind':'missing_code'},
    {'suggested_semester':3,'name':'زبان فارسی','kind':'missing_code'},
    {'suggested_semester':8,'name':'دانش خانواده و جمعیت','kind':'missing_code'},
    *[{'suggested_semester':t,'name':name,'kind':'unresolved_option'} for t,name in
      [(5,'تخصصی'),(6,'اختیاری'),(6,'تخصصی'),(6,'تخصصی'),(7,'اختیاری'),(7,'تخصصی'),(7,'تخصصی'),(8,'اختیاری'),(8,'تخصصی'),(8,'اختیاری'),(8,'تخصصی')]],
]))

charts.append(build('1395-1400', 3, [
    (1,'231478','',''), (1,'1108','',''), (1,'271477','',''), (1,'2101','',''), (1,'1107','',''),
    (1,'1109','','', {'course_name':'تربیت بدنی ۱','credits':1}), (1,'1101','',''),
    (2,'231458','231478',''), (2,'231457','','2101 231478'), (2,'231460','','231457'),
    (2,'231480','271477',''), (2,'2102','2101',''), (2,'271464','231478',''), (2,'1102','1101',''),
    (3,'231462','1108',''), (3,'231459','231457 231458',''), (3,'231465','231460',''),
    (3,'231475','231460','231465'), (3,'271463','2102',''), (3,'231484','231480',''),
    (3,'2135','2101',''), (3,'1103','','', {'course_name':'اخلاق و تربیت اسلامی','credits':2}),
    (4,'231467','231459',''), (4,'291458','231458',''),
    (4,'231466','231459 231465',''), (4,'231464','2102 2135',''), (4,'231456','2135',''),
    (4,'271478','1109',''),
    (5,'231463','231462',''), (5,'291494','291458',''), (5,'291492','291458 231459',''),
    (5,'231461','231459',''), (5,'231470','231465',''), (5,'231471','231466',''),
    (5,'231474','','231466'),
    (6,'1105','','', {'course_name':'تاریخ اسلام','credits':2}), (6,'291470','',''),
    (6,'231473','231461',''), (6,'231472','231459',''), (6,'231469','231464',''),
    (6,'231468','231465',''), (6,'231476','231470',''), (6,'231479','','231471'),
    (6,'291468','','', {'suggested_period':'summer_after_6','unresolved_credit_condition':'اخذ ۸۰ واحد طبق تصویر؛ تعریف اخذ باید تأیید شود'}),
    (7,'291474','','291458'), (7,'261479','','291492'), (7,'291493','231473',''),
    (7,'291495','231471','291492'), (7,'1124','',''),
    (8,'291496','','', {'unresolved_credit_condition':'اخذ ۱۰۰ واحد طبق تصویر؛ تعریف اخذ باید تأیید شود'}), (8,'291471','',''),
    (8,'291503','231468','', {'course_code':'291478','relationships_complete':False,
                             'review_reason':'کد تصویر 291478 با داده قبلی 291503 متفاوت است؛ رابطه آزمایشگاه باید بازبینی شود'}),
    (8,'1106','','', {'course_name':'آشنایی با منابع اسلامی','credits':2}),
], [
    {'suggested_semester':4,'name':'انقلاب اسلامی / اندیشه سیاسی امام','kind':'alternative','course_codes':[]},
    *[{'suggested_semester':t,'name':f'درس تمرکز {n}','kind':'unresolved_option'} for t,n in [(7,1),(7,2),(8,3),(8,4)]],
]))

(ROOT / 'catalog.json').write_text(json.dumps({'schema_version':'1.0','precedence':'visual_before_legacy',
  'note':'تصویر ۱ عنوان ۱۴۰۱ به بعد دارد؛ طبق تأیید کاربر تصویر ۲ برای ۱۴۰۳ به بعد مقدم است. روابط ناخوانا حدس زده نمی‌شوند.',
  'charts':charts},ensure_ascii=False,indent=2),encoding='utf-8')
print('Wrote catalog:', [(c['chart'],len(c['nodes']),len(c['slots'])) for c in charts])
