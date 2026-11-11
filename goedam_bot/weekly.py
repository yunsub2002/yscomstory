#!/usr/bin/env python3
"""GitHub Actions 에서 매주 실행: 새 괴담 N편 쓰기 → AI 목소리 영상 → 릴리스 업로드 → 보관함 페이지 갱신
환경변수: GH_TOKEN, GITHUB_REPOSITORY, COUNT(기본 3), CHANNEL(채널 이름)
"""
import datetime as dt, hashlib, html, json, os, random, re, subprocess, sys
from pathlib import Path

BOT = Path(__file__).resolve().parent
REPO_DIR = BOT.parent
sys.path.insert(0, str(BOT))
import make_video as mv  # noqa: E402

REPO = os.environ.get('GITHUB_REPOSITORY', 'yunsub2002/yscomstory')
COUNT = int(os.environ.get('COUNT') or 3)
CHANNEL = os.environ.get('CHANNEL', '')


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
        sh('git', 'fetch', 'origin', br, cwd=REPO_DIR); sh('git', 'worktree', 'add', root, f'origin/{br}', cwd=REPO_DIR)
        sh('git', 'checkout', '-B', br, cwd=root)
    return root, br, (root / path / 'goedam' if path else root / 'goedam')


PAGE = r'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>괴담 영상 보관함</title><style>
body{margin:0;background:#0e0f11;color:#e8e4dc;font:15px/1.6 -apple-system,"Noto Sans KR",sans-serif}main{max-width:720px;margin:0 auto;padding:18px 16px 60px}
h1{font-size:22px;margin:6px 0 4px}p.s{color:#9aa0a8;margin:0 0 18px;font-size:13px}
.v{background:#16181b;border:1px solid #2b2f35;border-radius:14px;overflow:hidden;margin-bottom:16px}.v img{display:block;width:100%;aspect-ratio:16/9;object-fit:cover;background:#000}
.b{padding:12px 14px 14px;display:grid;gap:8px}.b h2{margin:0;font-size:17px}.m{color:#9aa0a8;font-size:12.5px}
.r{display:flex;gap:8px;flex-wrap:wrap}.r a,.r button{flex:1;min-width:120px;text-align:center;font:inherit;font-weight:700;font-size:14px;color:#fff;background:#b3261e;border:0;border-radius:10px;padding:11px;text-decoration:none;cursor:pointer}
.r button,.r a.t{background:#2a2e34}details{font-size:12.5px;color:#9aa0a8}details pre{white-space:pre-wrap;font:inherit;background:#0b0c0e;padding:10px;border-radius:8px}
</style></head><body><main><h1>괴담 영상 보관함</h1><p class="s">매주 월요일 밤 새 영상이 자동으로 올라옵니다. 숏츠(세로) 또는 가로 영상 받기 → 사진 앱에 저장 → YouTube 앱에서 업로드 · 제목·설명은 "설명 복사"</p>
__LIST__
</main><script>document.querySelectorAll('button[data-c]').forEach(b=>b.onclick=()=>{navigator.clipboard.writeText(document.getElementById(b.dataset.c).textContent).then(()=>{b.textContent='복사됨 ✓';setTimeout(()=>b.textContent='📋 설명 복사',1500)})});</script></body></html>'''


def render_page(gd, db):
    items = []
    for k, v in enumerate(db):
        m, s = divmod(int(v['sec']), 60)
        items.append(f'''<div class="v"><img src="thumbs/{html.escape(v['thumb'])}" alt="" loading="lazy"><div class="b"><h2>{html.escape(v['title'])}</h2>
<div class="m">{v['date']} · {m}분 {s:02d}초</div><div class="r">{f'<a href="{html.escape(v["short_url"])}">⬇ 숏츠(세로)</a>' if v.get('short_url') else ''}<a href="{html.escape(v['url'])}">⬇ 가로 영상</a><a class="t" href="{html.escape(v['thumb_url'])}">⬇ 썸네일</a><button data-c="d{k}">📋 설명 복사</button></div>
<details><summary>제목·설명·태그 보기</summary><pre id="d{k}">{html.escape(v['yt'])}</pre></details></div></div>''')
    (gd / 'index.html').write_text(PAGE.replace('__LIST__', '\n'.join(items) or '<p>아직 영상이 없습니다.</p>'), encoding='utf-8')


def main():
    sh('git', 'config', '--global', 'user.name', 'goedam-bot'); sh('git', 'config', '--global', 'user.email', 'goedam-bot@users.noreply.github.com')
    root, br, gd = pages_dir(); (gd / 'thumbs').mkdir(parents=True, exist_ok=True)
    db = json.loads((gd / 'videos.json').read_text(encoding='utf-8')) if (gd / 'videos.json').exists() else []
    used = json.loads((gd / 'used.json').read_text(encoding='utf-8')) if (gd / 'used.json').exists() else []
    out = REPO_DIR / '_out'; out.mkdir(exist_ok=True); stories = []
    # 1) 새 괴담 쓰기 — 예전에 쓴 이야기와 겹치지 않게
    rnd = random.Random()
    for tries in range(400):
        if len(stories) >= COUNT: break
        txt = sh('node', BOT / 'gen_cli.js', rnd.randrange(1, 2**31), out=True)
        h = hashlib.md5(txt.encode()).hexdigest()[:12]; title = txt.splitlines()[0].lstrip('# ').strip()
        if h in used or any(title == s[1] for s in stories): continue
        stories.append((txt, title, h))
    stamp = dt.datetime.utcnow() + dt.timedelta(hours=9); tag = 'goedam-' + stamp.strftime('%Y%m%d-%H%M'); made = []
    # 2) 영상 만들기
    for i, (txt, title, h) in enumerate(stories, 1):
        name = f'goedam_{stamp:%Y%m%d}_{i:02d}'; sp = out / f'{name}.txt'; sp.write_text(txt, encoding='utf-8')
        print(f'\n===== [{i}/{len(stories)}] {title} =====', flush=True)
        items = mv.parse(txt); table = mv.synth(items, BOT / '.tts_cache')
        total = mv.render(sp, table, BOT / '.tts_cache', out / f'{name}.mp4', 1080, CHANNEL, 3.5e6)
        made.append((name, title, total, h))
    if not made: print('만든 영상이 없습니다.'); return
    # 3) 릴리스에 영상·썸네일 올리기 (영상은 100MB가 넘어서 저장소 대신 릴리스)
    files = []
    for name, *_ in made:
        png = out / f'{name}_썸네일.png'; tp = out / f'{name}_thumb.png'; png.rename(tp); files += [out / f'{name}.mp4', tp] + ([out / f'{name}_short.mp4'] if (out / f'{name}_short.mp4').exists() else [])
    notes = '\n'.join(f'- {t} ({int(s) // 60}분 {int(s) % 60:02d}초)' for _, t, s, _ in made)
    sh('gh', 'release', 'create', tag, *files, '--repo', REPO, '--title', f'괴담 영상 {stamp:%Y-%m-%d}', '--notes', notes)
    # 4) 보관함 페이지 갱신
    for name, title, total, h in made:
        jpg = gd / 'thumbs' / f'{name}.jpg'
        subprocess.run([mv.ffmpeg_exe() if hasattr(mv, 'ffmpeg_exe') else 'ffmpeg', '-y', '-loglevel', 'error', '-i', str(out / f'{name}_thumb.png'), '-vf', 'scale=640:-1', '-q:v', '4', str(jpg)], check=True)
        yt = (out / f'{name}_유튜브.txt').read_text(encoding='utf-8')
        base = f'https://github.com/{REPO}/releases/download/{tag}/'
        db.insert(0, {'title': title, 'sec': round(total), 'date': f'{stamp:%Y-%m-%d}', 'thumb': jpg.name, 'yt': yt, 'url': base + f'{name}.mp4', 'thumb_url': base + f'{name}_thumb.png', 'short_url': base + f'{name}_short.mp4' if (out / f'{name}_short.mp4').exists() else ''})
        used.append(h)
    (gd / 'videos.json').write_text(json.dumps(db, ensure_ascii=False, indent=1), encoding='utf-8')
    (gd / 'used.json').write_text(json.dumps(used[-500:]), encoding='utf-8'); render_page(gd, db)
    sh('git', 'add', gd, cwd=root); sh('git', 'commit', '-m', f'괴담 영상 {len(made)}편 추가 ({stamp:%Y-%m-%d})', cwd=root); push_safe(root, br)
    user, rn = REPO.split('/'); print(f'\n완료 → https://{user}.github.io/{rn}/goedam/')


if __name__ == '__main__':
    main()
