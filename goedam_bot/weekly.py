#!/usr/bin/env python3
"""GitHub Actions 에서 실행 (기본: 월·목 저녁)
- goedam_bot/scripts 의 원고(한 주제 · 약 30분 · 한 사람 낭독) 중 아직 안 만든 것 1편 → 영상
- 원고가 다 떨어지면 아무것도 만들지 않고 끝냄 (엉터리 영상 대신)
만든 영상 → 릴리스(보관) → 유튜브 자동 업로드(설정했을 때) → 보관함 페이지 갱신
환경변수: GH_TOKEN, GITHUB_REPOSITORY, MODE(auto/episode/short), EP_DAYS(모음 요일, 0=월 … 6=일, 기본 0,3),
         MINUTES(목표 길이 분, 기본 25), CHANNEL, YT_CLIENT_ID/YT_CLIENT_SECRET/YT_REFRESH_TOKEN, YT_PRIVACY
"""
import datetime as dt, hashlib, html, json, os, random, re, subprocess, sys
from pathlib import Path

BOT = Path(__file__).resolve().parent
REPO_DIR = BOT.parent
sys.path.insert(0, str(BOT))
import make_video as mv, youtube_upload as yu, hookshort as HS  # noqa: E402

REPO = os.environ.get('GITHUB_REPOSITORY', 'yunsub2002/yscomstory')
MODE = (os.environ.get('MODE') or 'episode').strip()
SHORTS = (os.environ.get('SHORTS') or '0').strip() == '1'
EP_DAYS = [int(x) for x in (os.environ.get('EP_DAYS') or '0,3').split(',') if x.strip().isdigit()]
MINUTES = max(20, min(30, int(os.environ.get('MINUTES') or 25)))
CHANNEL = os.environ.get('CHANNEL', '')



GD_SUB_LINE = '[쉼:1]\n잠깐만요. 이런 이야기 좋아하신다면, 구독과 알림 설정 꼭 눌러 주세요.\n매주 월요일과 목요일 저녁, 새로운 이야기를 들려 드립니다.\n[쉼:1.5]\n'
GD_SUB_DESC = ('🔔 매주 월·목 저녁 8시 반, 새 괴담이 올라옵니다. 구독하고 알림 설정해 두세요!\n'
               '👉 https://www.youtube.com/channel/UCTGBcatcPQOoK4NsiHCukuw?sub_confirmation=1\n')
GD_FAMILY = ('\n\n📺 같이 보면 좋은 채널\n'
             '· Dreamcore Sleep — 괴담 듣고 잠 안 올 때, 잠 오는 음악 https://www.youtube.com/@Moonsleep-g1c\n'
             '· 세상의 모든 이야기 — 매일 1분 경제·생활 뉴스 https://www.youtube.com/@세상의모든이야기g1-c')


def add_sub_line(txt):
    """대본에서 두 번째 [챕터:] 바로 앞에 구독 부탁 멘트 (챕터가 2개 미만이면 전체 4분의 1 지점)"""
    L = txt.splitlines(keepends=True); idx = [i for i, l in enumerate(L) if l.lstrip().startswith('[챕터')]
    at = idx[1] if len(idx) >= 2 else max(1, len(L) // 4)
    return ''.join(L[:at]) + GD_SUB_LINE + ''.join(L[at:])


def add_sub_desc(desc):
    """설명: 이야기 소개·목차 다음(※ 안내 앞)에 구독 링크와 다른 채널"""
    if 'sub_confirmation' in desc: return desc
    blk = '\n\n' + GD_SUB_DESC + '\n' + GD_FAMILY.lstrip('\n')
    cut = desc.find('\n\n※')
    return desc[:cut] + blk + desc[cut:] if cut > 0 else desc + blk


def sh(*cmd, cwd=None, check=True, out=False):
    print('  >', ' '.join(str(c) for c in cmd), flush=True)
    r = subprocess.run([str(c) for c in cmd], cwd=cwd, check=check, text=True, capture_output=out)
    return r.stdout.strip() if out else r


def push_safe(root, br):
    """제작 중에 저장소가 바뀌었어도(업데이트 등) 최신 상태를 받아 합친 뒤 올림"""
    for i in range(5):
        if subprocess.run(['git', 'push', 'origin', f'HEAD:{br}'], cwd=root).returncode == 0: return
        print(f'  ! 저장소가 그새 바뀌어서 최신 내용과 합칩니다 ({i + 1}/5)', flush=True)
        sh('git', 'pull', '--rebase', '--autostash', '-X', 'theirs', 'origin', br, cwd=root, check=False)
    raise RuntimeError('git push 실패')


def pages_dir():
    """Pages 가 어디서 나가는지(브랜치·폴더) 확인해서 goedam/ 을 그 아래에 둠"""
    try:
        info = json.loads(sh('gh', 'api', f'repos/{REPO}/pages', out=True))
        br, path = info['source']['branch'], info['source']['path'].strip('/')
    except Exception:
        br, path = sh('git', 'rev-parse', '--abbrev-ref', 'HEAD', cwd=REPO_DIR, out=True), ''
    cur = sh('git', 'rev-parse', '--abbrev-ref', 'HEAD', cwd=REPO_DIR, out=True)
    if br == cur: root = REPO_DIR
    else:
        root = REPO_DIR / '_pages'
        if not root.exists():
            sh('git', 'fetch', 'origin', br, cwd=REPO_DIR); sh('git', 'worktree', 'add', root, f'origin/{br}', cwd=REPO_DIR)
            sh('git', 'checkout', '-B', br, cwd=root)
        else: sh('git', 'pull', '--rebase', 'origin', br, cwd=root, check=False)
    return root, br, (root / path / 'goedam' if path else root / 'goedam')


PAGE = r'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>괴담 영상 보관함</title><style>
body{margin:0;background:#0e0f11;color:#e8e4dc;font:15px/1.6 -apple-system,"Noto Sans KR",sans-serif}main{max-width:720px;margin:0 auto;padding:18px 16px 60px}
h1{font-size:22px;margin:6px 0 4px}p.s{color:#9aa0a8;margin:0 0 18px;font-size:13px}
.v{background:#16181b;border:1px solid #2b2f35;border-radius:14px;overflow:hidden;margin-bottom:16px}.v img{display:block;width:100%;aspect-ratio:16/9;object-fit:cover;background:#000}
.b{padding:12px 14px 14px;display:grid;gap:8px}.b h2{margin:0;font-size:17px}.m{color:#9aa0a8;font-size:12.5px}
.r{display:flex;gap:8px;flex-wrap:wrap}.r a,.r button{flex:1;min-width:120px;text-align:center;font:inherit;font-weight:700;font-size:14px;color:#fff;background:#b3261e;border:0;border-radius:10px;padding:11px;text-decoration:none;cursor:pointer}
.r button,.r a.t{background:#2a2e34}details{font-size:12.5px;color:#9aa0a8}details pre{white-space:pre-wrap;font:inherit;background:#0b0c0e;padding:10px;border-radius:8px}
.tabs{display:flex;gap:8px;margin:0 0 16px;position:sticky;top:0;background:#0e0f11;padding:8px 0;z-index:2}.tabs a{flex:1;text-align:center;font-weight:700;font-size:14.5px;color:#e8e4dc;background:#16181b;border:1px solid #2b2f35;border-radius:999px;padding:10px;text-decoration:none}
.tabs a.on{background:#b3261e;border-color:#b3261e;color:#fff}.sec{display:none}.sec.on{display:block}
.sg{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.sv{background:#16181b;border:1px solid #2b2f35;border-radius:14px;overflow:hidden}.sv img{display:block;width:100%;aspect-ratio:9/16;object-fit:cover;background:#000}
.sv .b{padding:10px}.sv h2{font-size:14px;line-height:1.4}.sv .r{gap:6px}.sv .r a,.sv .r button{min-width:0;padding:9px 2px;font-size:12.5px;white-space:nowrap}
</style></head><body><main><h1>괴담 영상 보관함</h1><p class="s">매주 월·목 저녁, 한 주제를 30분 동안 들려주는 미스터리·괴담 영상이 자동으로 만들어집니다. 유튜브 연결을 해 두면 유튜브에도 자동으로 올라갑니다 (구글 심사 전에는 비공개 → 「유튜브 공개 설정」 눌러서 공개로 바꾸기).</p>
<nav class="tabs"><a href="#long" data-t="long" class="on">🎬 30분 이야기</a><a href="#shorts" data-t="shorts">📱 숏츠</a></nav>
<section class="sec on" id="long">
__LIST__
</section><section class="sec" id="shorts"><p class="s">이야기마다 가장 무서운 도입부를 세로로 다시 만든 숏츠입니다. ⬇ 숏츠 받기 → 사진 앱에 저장 → YouTube 앱 [＋] → 쇼츠 → 영상 고르기 → 제목·설명·태그 버튼으로 복사해서 붙여 넣기</p>
<div class="sg">__SHORTS__</div></section>
</main><script>document.querySelectorAll('button[data-c]').forEach(b=>b.onclick=()=>{const o=b.textContent;navigator.clipboard.writeText(document.getElementById(b.dataset.c).textContent).then(()=>{b.textContent='복사됨 ✓';setTimeout(()=>b.textContent=o,1500)})});
function tab(t){document.querySelectorAll('.tabs a').forEach(a=>a.classList.toggle('on',a.dataset.t===t));document.querySelectorAll('.sec').forEach(s=>s.classList.toggle('on',s.id===t))}
document.querySelectorAll('.tabs a').forEach(a=>a.onclick=e=>{e.preventDefault();tab(a.dataset.t);history.replaceState(null,'','#'+a.dataset.t)});if(location.hash==='#shorts')tab('shorts');</script></body></html>'''



def render_page(gd, db):
    items = []
    for k, v in enumerate(db):
        if v.get('kind') == 'short': continue  # 1분 숏츠는 숏츠 탭에만
        m, s = divmod(int(v['sec']), 60); kind = {'short': '숏츠', 'mix': '몰아듣기'}.get(v.get('kind'), '30분 이야기')
        yt = ''.join(f'<a href="https://studio.youtube.com/video/{html.escape(i)}/edit">▶ 유튜브{lab} 공개 설정</a>' for i, lab in ((v.get('yt_id'), ''), (v.get('short_yt_id'), ' 숏츠')) if i)
        dl = ((f'<a class="t" href="{html.escape(v["url"])}">⬇ 영상</a>' if v.get('url') else '')
              + (f'<a class="t" href="{html.escape(v["short_url"])}">⬇ 숏츠</a>' if v.get('short_url') else '')
              + (f'<a class="t" href="{html.escape(v["thumb_url"])}">⬇ 썸네일</a>' if v.get('thumb_url') else ''))
        up = ' · 유튜브에 올라감' if yt else ''
        items.append(f'<div class="v"><img src="thumbs/{html.escape(v["thumb"])}" alt="" loading="lazy"><div class="b"><h2>{html.escape(v["title"])}</h2>\n'
                     f'<div class="m">{v["date"]} · {kind} · {m}분 {s:02d}초{up}</div><div class="r">{yt}{dl}<button data-c="d{k}">📋 설명 복사</button></div>\n'
                     f'<details><summary>제목·설명·태그 보기</summary><pre id="d{k}">{html.escape(v["yt"])}</pre></details></div></div>')
    shorts = []
    for k, v in enumerate(db):
        if not v.get('short_url'): continue
        syt = v.get('short_yt') or v['yt']; part = lambda key: (syt.split(f'[{key}]\n', 1)[1].split('\n\n[', 1)[0].strip() if f'[{key}]' in syt else '')
        img = v.get('short_thumb') or v['thumb']; sec = v.get('short_sec') or (v['sec'] if v['sec'] <= 180 else 0)
        ytl = f'<a href="https://studio.youtube.com/video/{html.escape(v["short_yt_id"])}/edit">▶ 유튜브 공개 설정</a>' if v.get('short_yt_id') else ''
        shorts.append(f'<div class="sv"><img src="thumbs/{html.escape(img)}" alt="" loading="lazy"><div class="b"><h2>{html.escape(part("제목") or v["title"])}</h2>'
                      f'<div class="m">{v["date"]}' + (f' · {sec}초' if sec else '') + f'</div><div class="r"><a href="{html.escape(v["short_url"])}">⬇ 숏츠 받기</a>{ytl}</div>'
                      f'<div class="r"><button data-c="st{k}">제목</button><button data-c="sd{k}">설명</button><button data-c="sg{k}">태그</button></div>'
                      f'<span id="st{k}" hidden>{html.escape(part("제목"))}</span><span id="sd{k}" hidden>{html.escape(part("설명"))}</span><span id="sg{k}" hidden>{html.escape(part("태그"))}</span></div></div>')
    page = PAGE.replace('__LIST__', '\n'.join(items) or '<p>아직 영상이 없습니다.</p>').replace('__SHORTS__', '\n'.join(shorts) or '<p class="s">아직 숏츠가 없습니다.</p>')
    (gd / 'index.html').write_text(page, encoding='utf-8')


def short_text(title, place):
    tags = ['괴담', '무서운 이야기', '공포', '괴담 낭독', '쇼츠 괴담', 'shorts'] + ([place] if place else [])
    return (f'[제목]\n{title} | {place} 괴담 #shorts #괴담 #무서운이야기\n\n[설명]\n{title} — {place}에서 생긴 짧은 괴담.\n'
            '전체 이야기와 작성자 후기는 채널의 「괴담 모음」 영상에서 들으실 수 있어요.\n\n'
            '※ 창작한 이야기(픽션)입니다. 낭독: AI 음성(Supertonic)\n\n#shorts #괴담 #무서운이야기 #공포\n\n[태그]\n' + ', '.join(tags))


def make_short(seed, place, out, name):
    """3분 이하 세로 숏츠 1개 → (mp4 경로, 제목, 길이) / 실패하면 None"""
    try:
        st = sh('node', BOT / 'gen_cli.js', seed, 'short', place, out=True); title = st.splitlines()[0].lstrip('# ').strip()
        ssp = out / f'{name}_s.txt'; ssp.write_text(st, encoding='utf-8'); print(f'\n  --- 숏츠: {title} ({place}) ---', flush=True)
        tab = mv.synth(mv.parse(st), BOT / '.tts_cache')
        sec = mv.render(ssp, tab, BOT / '.tts_cache', out / f'{name}_s.mp4', 1080, CHANNEL, 3.5e6, main=False, short=True)
        f = out / f'{name}_s_short.mp4'
        if not f.exists(): return None
        dst = out / f'{name}_short.mp4'; f.rename(dst); return dst, title, sec
    except Exception as e:
        print('  숏츠는 건너뜀:', e, flush=True); return None


def yt_up(video, yt_txt, thumb=None):
    if not yu.enabled(): return ''
    try:
        t, d, g = yu.parse_yt(yt_txt); return yu.upload(video, t, d, g, thumb=thumb, log=lambda x: print(x, flush=True))
    except Exception as e:
        print('  ! 유튜브 업로드 실패 (영상은 보관함에 있습니다):', e, flush=True); return ''


def all_places():
    src = (BOT / 'gen.js').read_text(encoding='utf-8') + (BOT / 'gen_long.js').read_text(encoding='utf-8')
    return list(dict.fromkeys(re.findall(r"place: '([^']+)'", src)))


def main():
    sh('git', 'config', '--global', 'user.name', 'goedam-bot'); sh('git', 'config', '--global', 'user.email', 'goedam-bot@users.noreply.github.com')
    root, br, gd = pages_dir(); (gd / 'thumbs').mkdir(parents=True, exist_ok=True)
    db = json.loads((gd / 'videos.json').read_text(encoding='utf-8')) if (gd / 'videos.json').exists() else []
    used = json.loads((gd / 'used.json').read_text(encoding='utf-8')) if (gd / 'used.json').exists() else []
    out = REPO_DIR / '_out'; out.mkdir(exist_ok=True)
    stamp = dt.datetime.utcnow() + dt.timedelta(hours=9); tag = 'goedam-' + stamp.strftime('%Y%m%d-%H%M'); name = f'goedam_{stamp:%Y%m%d_%H%M}'
    mode = MODE if MODE in ('episode', 'short') else ('episode' if stamp.weekday() in EP_DAYS else 'short')
    print(f'오늘({stamp:%Y-%m-%d}) 만들 것: {"괴담 모음 + 숏츠" if mode == "episode" else "숏츠"} · 유튜브 자동 업로드: {"켜짐" if yu.enabled() else "꺼짐(설정 전)"}', flush=True)
    rnd = random.Random(); seed = rnd.randrange(1, 2**31)
    base = f'https://github.com/{REPO}/releases/download/{tag}/'
    entry = {'date': f'{stamp:%Y-%m-%d}', 'kind': mode}
    if mode == 'episode':
        # 1) 원고 대기열(goedam_bot/scripts)에서 아직 안 만든 원고 하나 — 한 주제 30분, 한 사람이 끝까지 읽는 이야기
        done = {v.get('script') for v in db}
        order_f = BOT / 'scripts' / '순서.txt'
        order = [l.strip() for l in order_f.read_text(encoding='utf-8').splitlines() if l.strip() and not l.startswith('#')] if order_f.exists() else []
        allp = [p for p in sorted((BOT / 'scripts').glob('*.txt')) if p.name != '순서.txt']
        allp.sort(key=lambda p: (order.index(p.name) if p.name in order else 999, p.name))
        queue = [p for p in allp if p.name not in done]
        if not queue:
            print('\n새 원고가 없습니다. 대화창에서 "괴담 원고 더 써줘"라고 하면 새 원고를 받아 업데이트_적용.bat 로 넣을 수 있습니다.', flush=True); return
        src = queue[0]; meta = json.loads(src.with_suffix('.json').read_text(encoding='utf-8')) if src.with_suffix('.json').exists() else {}
        print(f'남은 원고 {len(queue)}편 (이번 편 포함)', flush=True)
        txt = src.read_text(encoding='utf-8'); h = src.name
        title = next((l.lstrip('# ').strip() for l in txt.splitlines() if l.startswith('#')), src.stem); places = []
        if os.environ.get('SUB_LINE', '1') == '1': txt = add_sub_line(txt)            # 앞부분 끝(2부 시작 전)에 구독 부탁 한 줄
        sp = out / f'{name}.txt'; sp.write_text(txt, encoding='utf-8')
        print(f'\n===== {title} ({src.name}) =====', flush=True)
        if meta.get('rate'): mv.EDGE_RATE = meta['rate']   # 원고마다 말 속도를 따로 정할 수도 있음
        items = mv.parse(txt); print(f'  문장 {len(items)}개 음성 합성 (속도 {mv.EDGE_RATE})', flush=True); table = mv.synth(items, BOT / '.tts_cache', src=txt)
        imgs = []
        if meta.get('images'):   # 이야기 장면 그림 (AI 생성, 무료) — 실패하면 기본 화면으로
            try:   # 별도 프로세스로 그려서, 끝나면 메모리를 깨끗이 비움 (영상 인코딩에 메모리 필요)
                print(f'  장면 그림 {len(meta["images"])}장 그리기', flush=True)
                subprocess.run([sys.executable, str(BOT / 'images.py'), str(src.with_suffix('.json')), str(out / 'imgs'), str(len(meta['images'])), str(sum(map(ord, src.name)) % 97)], check=True, timeout=3600)
                imgs = [Path(l) for l in (out / 'imgs' / 'list.txt').read_text(encoding='utf-8').splitlines() if l.strip()]
            except Exception as e: print('  ! 장면 그림 실패 → 기본 화면으로:', e, flush=True); imgs = []
        total = mv.render(sp, table, BOT / '.tts_cache', out / f'{name}.mp4', 1080, CHANNEL, 2.6e6, main=True, short=False, thumb=meta.get('thumb'), images=imgs)
        thumb = out / f'{name}_thumb.png'; (out / f'{name}_썸네일.png').rename(thumb)
        eng = (out / f'{name}_유튜브.txt').read_text(encoding='utf-8')
        chap = ['0:00 시작'] + [re.sub(r'^(\d+:\d\d) 제\d+화 (\S+부) — ', r'\1 \2. ', l) for l in eng.splitlines() if re.match(r'^\d+:\d\d 제\d+화', l)]
        desc = meta.get('desc', title); cut = desc.find('\n\n※')
        desc = (desc[:cut] if cut > 0 else desc) + '\n\n📖 목차\n' + '\n'.join(chap) + (desc[cut:] if cut > 0 else '')
        desc = add_sub_desc(desc)
        yt = f"[제목]\n{meta.get('yt_title', title)}\n\n[설명]\n{desc}\n\n[태그]\n{', '.join(meta.get('tags', ['괴담', '미스터리']))}"
        sv = None; splace = ''
        files = [out / f'{name}.mp4', thumb]
        entry.update(title=meta.get('yt_title', title), sec=round(total), yt=yt, places=places, script=src.name, url=base + f'{name}.mp4', thumb_url=base + thumb.name, short_url='')
        hs = None
        if os.environ.get('HOOK_SHORT', '1') == '1':                                  # 도입부 세로 숏츠도 함께 (같은 장면 그림 재사용)
            try:
                print('\n  --- 도입부 숏츠 ---', flush=True); hs = HS.from_script(src, out, name, CHANNEL, imgs=imgs[:4], log=lambda s: print(s, flush=True))
            except Exception as e: print('  ! 도입부 숏츠 건너뜀:', e, flush=True); hs = None
        if hs:
            files.append(hs['file']); sj = gd / 'thumbs' / f'{name}_s.jpg'; HS.frame_jpg(hs['file'], sj)
            entry.update(short_url=base + hs['file'].name, short_yt=hs['yt'], short_thumb=sj.name, short_sec=hs['sec'])
    else:
        recent = [p for v in db[:6] if v.get('kind') == 'short' for p in (v.get('places') or [])]
        allp = all_places(); splace = rnd.choice([p for p in allp if p not in recent] or allp)
        sv = make_short(seed, splace, out, name)
        if not sv: raise RuntimeError('숏츠를 만들지 못했습니다')
        h = f'short-{seed}'; title = sv[1]
        thumb = out / f'{name}_thumb.jpg'
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-ss', '4', '-i', str(sv[0]), '-frames:v', '1', str(thumb)], check=True)
        files = [sv[0]]; yt = short_text(title, splace)
        entry.update(title=title, sec=round(sv[2]), yt=yt, places=[splace], short_url=base + sv[0].name)
    # 2) 릴리스에 보관 (영상은 100MB가 넘어서 저장소 대신 릴리스)
    sh('gh', 'release', 'create', tag, *files, '--repo', REPO, '--title', f'괴담 {entry["date"]} {title}', '--notes', f'- {title} ({entry["sec"] // 60}분 {entry["sec"] % 60:02d}초)')
    # 3) 유튜브 자동 업로드 (설정했을 때만)
    if mode == 'episode':
        entry['yt_id'] = yt_up(out / f'{name}.mp4', yt, thumb=thumb)
        if sv: entry['short_yt_id'] = yt_up(sv[0], short_text(sv[1], splace))
        elif hs: entry['short_yt_id'] = yt_up(hs['file'], hs['yt'])
    else:
        entry['short_yt_id'] = yt_up(sv[0], yt)
    # 4) 보관함 페이지 갱신
    jpg = gd / 'thumbs' / f'{name}.jpg'
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(thumb), '-vf', 'scale=640:-1', '-q:v', '4', str(jpg)], check=True)
    entry['thumb'] = jpg.name; db.insert(0, entry); used.append(h)
    (gd / 'videos.json').write_text(json.dumps(db, ensure_ascii=False, indent=1), encoding='utf-8')
    (gd / 'used.json').write_text(json.dumps(used[-500:]), encoding='utf-8'); render_page(gd, db)
    sh('git', 'add', gd, cwd=root); sh('git', 'commit', '-m', f'괴담 {"모음" if mode == "episode" else "숏츠"} 추가 ({stamp:%Y-%m-%d})', cwd=root); push_safe(root, br)
    user, rn = REPO.split('/'); print(f'\n완료 → https://{user}.github.io/{rn}/goedam/')


if __name__ == '__main__':
    if MODE == 'backfill':                                          # 지금까지 만든 영상 전부 → 숏츠
        import backfill_shorts; backfill_shorts.run(); sys.exit(0)
    if MODE == 'onemin':                                            # 1분 완결 숏츠만 (본편 없이)
        import onemin; onemin.run(); sys.exit(0)
    if MODE == 'mix':                                               # 지난 이야기 몰아듣기 (1시간 반~2시간)
        import mix; mix.main(); sys.exit(0)
    n = max(1, min(4, int(os.environ.get('COUNT') or 1)))   # 한 번 실행에 몇 편 (최대 4)
    for k in range(n):
        print(f'\n########## {k + 1}/{n}편 ##########', flush=True)
        main()
