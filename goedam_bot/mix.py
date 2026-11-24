#!/usr/bin/env python3
"""괴담 몰아듣기 (1시간 반~2시간 모음) — 이미 만든 25분 이야기들을 이어 붙여 긴 영상 1편으로
- 새로 그리거나 읽지 않음: 릴리스에 보관된 본편 mp4 를 내려받아 그대로 이어 붙임 (화질·소리 그대로, 몇 분이면 끝)
- 아직 모음에 안 들어간 이야기부터 골라 목표 길이(기본 120분)를 채움 → compiled.json 에 기록
- 썸네일: 첫 이야기 썸네일 위에 '2시간 몰아듣기' 큰 글씨
- 설명: 이야기별 시작 시각(목차) + 구독 링크 + AI 낭독 고지
환경변수: COMPILE_MIN(목표 분, 기본 120), YT_* (weekly.py 와 같음)
"""
import datetime as dt, json, os, re, subprocess, sys
from pathlib import Path

BOT = Path(__file__).resolve().parent
sys.path.insert(0, str(BOT))
import weekly as W, youtube_upload as yu, hookshort as HS  # noqa: E402

TARGET = max(60, min(180, int(os.environ.get('COMPILE_MIN') or 100))) * 60
CAP = 1.95e9          # 릴리스 파일 한 개 최대 2GB → 넘지 않게


def probe(f):
    r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels:format=duration',
                        '-of', 'json', str(f)], capture_output=True, text=True, check=True)
    j = json.loads(r.stdout); dur = float(j['format']['duration'])
    sig = tuple(sorted(tuple(sorted((k, str(v)) for k, v in s.items())) for s in j['streams']))
    return dur, sig


def hms(s):
    s = int(s); return f'{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}' if s >= 3600 else f'{s // 60}:{s % 60:02d}'


def short_name(title, script=''):
    """제목에서 짧은 이름 ('… | 키사라기역 [일본 괴담]' → '키사라기역'), 길거나 쉼표가 있으면 원고 파일 이름에서"""
    right = title.split(' | ', 1)[1] if ' | ' in title else title
    right = re.sub(r'\s*\[[^\]]+\]\s*$', '', right).strip()
    m = re.search(r"[‘'](.+?)[’']", right); n = m.group(1) if m else right
    if (len(n) > 10 or ',' in n) and script:
        n = re.sub(r'^\d+[a-z]?_', '', Path(script).stem).replace('_', ' ')
    return n[:14]


def main():
    W.sh('git', 'config', '--global', 'user.name', 'goedam-bot'); W.sh('git', 'config', '--global', 'user.email', 'goedam-bot@users.noreply.github.com')
    root, br, gd = W.pages_dir()
    db = json.loads((gd / 'videos.json').read_text(encoding='utf-8')) if (gd / 'videos.json').exists() else []
    cf = gd / 'compiled.json'; comp = json.loads(cf.read_text(encoding='utf-8')) if cf.exists() else []
    used = {s for c in comp for s in c.get('scripts', [])}
    alive = {p.name for p in (BOT / 'scripts').glob('*.txt')}
    eps = [v for v in db if v.get('kind') == 'episode' and v.get('script') in alive and str(v.get('url', '')).endswith('.mp4')]
    eps.reverse()                                                    # 오래된 것부터
    fresh = [v for v in eps if v['script'] not in used]; old = [v for v in eps if v['script'] in used]
    pick, tot = [], 0
    # 괴담 라디오: radio.json 에 적은 원고를 그 순서대로 (이미 만든 회차면 건너뜀)
    RADIO = None; rp = BOT / 'radio.json'
    if rp.exists():
        R_ = json.loads(rp.read_text(encoding='utf-8'))
        if not any(c.get('radio') == R_['no'] for c in comp):
            RADIO = R_; byname = {v['script']: v for v in eps}
            miss = [s_ for s_ in R_['pick'] if s_ not in byname]
            if miss: print('라디오에 넣을 본편이 아직 없습니다:', miss, flush=True); return
            pick = [byname[s_] for s_ in R_['pick']]
    for v in ([] if RADIO else fresh + old):
        if tot >= TARGET - 8 * 60: break
        if any(p['script'] == v['script'] for p in pick): continue
        pick.append(v); tot += v.get('sec', 1500)
    if len(pick) < 3:
        print('모음으로 묶을 본편이 3편 미만입니다. 본편이 더 쌓이면 다시 실행해 주세요.', flush=True); return
    out = W.REPO_DIR / '_out' / 'compile'; out.mkdir(parents=True, exist_ok=True)
    files, sig0 = [], None
    for v in pick:
        tag, fn = v['url'].split('/releases/download/', 1)[1].split('/', 1)
        print(f'  내려받기: {v["title"][:50]} ({tag})', flush=True)
        W.sh('gh', 'release', 'download', tag, '--repo', W.REPO, '-p', fn, '-D', str(out), '--clobber')
        f = out / fn; dur, sig = probe(f)
        if sig0 is None: sig0 = sig
        if sig != sig0: print('    형식이 달라 건너뜀', flush=True); f.unlink(); continue
        if sum(x[1].stat().st_size for x in files) + f.stat().st_size > CAP: print('    2GB 넘어서 여기까지', flush=True); f.unlink(); break
        files.append((v, f, dur))
    if len(files) < 3:
        print('이어 붙일 수 있는 본편이 3편 미만입니다.', flush=True); return
    lst = out / 'list.txt'; lst.write_text(''.join(f"file '{f.as_posix()}'\n" for _, f, _ in files), encoding='utf-8')
    stamp = dt.datetime.utcnow() + dt.timedelta(hours=9); name = f'goedam_mix_{stamp:%Y%m%d_%H%M}'
    mp4 = out / f'{name}.mp4'
    print(f'\n  {len(files)}편 이어 붙이는 중…', flush=True)
    W.sh('ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', str(lst), '-c', 'copy', '-movflags', '+faststart', str(mp4))
    total = sum(d for _, _, d in files); hrs = round(total / 3600 * 2) / 2
    hlabel = f'{hrs:g}시간'.replace('.5시간', '시간 반')
    names = [short_name(v['title'], v.get('script', '')) for v, _, _ in files]
    # 썸네일: 첫 편 썸네일 + 큰 글씨
    t0 = files[0][0]; th_src = out / 'th_src.png'
    try:
        ttag, tfn = t0['thumb_url'].split('/releases/download/', 1)[1].split('/', 1)
        W.sh('gh', 'release', 'download', ttag, '--repo', W.REPO, '-p', tfn, '-D', str(out), '--clobber'); (out / tfn).rename(th_src)
    except Exception as e:
        print('  ! 썸네일 원본 없음 → 첫 화면 사용', e, flush=True)
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-ss', '20', '-i', str(files[0][1]), '-frames:v', '1', str(th_src)], check=True)
    thumb = out / f'{name}_thumb.png'; font = (next((p for p in ['/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc'] if os.path.exists(p)), None) or HS.FONT or '').replace(':', r'\:')
    big = f'잠들기 전 {hlabel}'; sub = '괴담 몰아듣기'; small = ' · '.join(names[:3]) + ' 외'; top = '불 끄고 · 이어폰 필수'
    if RADIO: big = f'잘 때 듣는 라디오 #{RADIO["no"]}'; sub = f'불 끄고 {hlabel}'; small = ' · '.join(names[:4])
    tf = {}
    for k, txt in (('big', big), ('sub', sub), ('small', small), ('top', top)):
        tf[k] = out / f'th_{k}.txt'; tf[k].write_text(txt, encoding='utf-8')
    q = lambda p: str(p).replace('\\', '/').replace(':', r'\:')
    bs = 150 if len(big) <= 9 else 128
    vf = ('scale=1280:720,boxblur=10:2,eq=brightness=-0.12:saturation=0.7,'
          f"drawtext=fontfile='{font}':textfile='{q(tf['top'])}':fontcolor=#d8d2c4:fontsize=40:x=(w-tw)/2:y=h*0.14:borderw=3:bordercolor=black,"
          f"drawtext=fontfile='{font}':textfile='{q(tf['big'])}':fontcolor=#ff3b30:fontsize={bs}:x=(w-tw)/2:y=h*0.27:borderw=8:bordercolor=black,"
          f"drawtext=fontfile='{font}':textfile='{q(tf['sub'])}':fontcolor=white:fontsize=118:x=(w-tw)/2:y=h*0.52:borderw=7:bordercolor=black,"
          'drawbox=x=0:y=ih*0.82:w=iw:h=ih*0.18:color=black@0.6:t=fill,'
          f"drawtext=fontfile='{font}':textfile='{q(tf['small'])}':fontcolor=#f0ebe0:fontsize=44:x=(w-tw)/2:y=h*0.86")
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(th_src), '-vf', vf, '-frames:v', '1', str(thumb)], check=True)
    # 제목·설명·태그
    title = f'잠들기 전 듣는 괴담 {hlabel} 몰아듣기 | {", ".join(names[:3])} 외 {len(names) - 3}편 [불 끄고 · 이어폰 필수]' if len(names) > 3 else \
            f'잠들기 전 듣는 괴담 {hlabel} 몰아듣기 | {", ".join(names)} [불 끄고 · 이어폰 필수]'
    if len(title) > 100: title = f'잠들기 전 듣는 괴담 {hlabel} 몰아듣기 | {", ".join(names[:2])} 외 [이어폰 필수]'
    if RADIO:
        title = RADIO.get('title') or f'잘 때 듣는 라디오 #{RADIO["no"]} | 잠들기 전 {hlabel} 괴담 — {", ".join(names[:3])} 외 [이어폰 필수]'
        title = title[:100]
    chap, t = [], 0
    for (v, _, d), n in zip(files, names):
        chap.append(f'{hms(t)} {n} — {v["title"].split(" | ")[0][:60]}'); t += d
    notes = sorted({l for v, _, _ in files for l in str(v.get('yt', '')).splitlines() if l.startswith('※')})
    head = (f'귀담 잘 때 듣는 라디오 #{RADIO["no"]}. 지난 화제작 한 편과 신작 {len(files) - 1}편을 {hlabel} 동안 이어서 들려 드립니다.\n' if RADIO else
            f'불 끄고 누워서, 끝까지 들어 보세요. 귀담의 이야기 {len(files)}편을 {hlabel} 동안 이어서 들려 드립니다.\n')
    desc = (head +
            f'중간에 잠들어도 괜찮아요. 내일 밤, 멈춘 곳부터 다시 들으면 됩니다.\n\n'
            + W.GD_SUB_DESC + '\n📖 목차\n' + '\n'.join(chap) + '\n\n'
            + ('\n'.join(notes) + '\n' if notes else '※ 낭독: AI 음성 · 배경음·화면: 자체 제작\n')
            + W.GD_FAMILY + '\n\n#괴담 #무서운이야기 #괴담모음 #잠잘때듣는 #공포라디오 #일본괴담 #미스터리')
    tags = ['괴담 모음', '괴담 몰아듣기', '잠잘때 듣는 괴담', '무서운 이야기', '공포 라디오', '괴담 낭독', '일본 괴담', '한국 괴담',
            '미스터리', '미제사건', '수면용 괴담', f'{hlabel} 괴담'] + names
    yt = f'[제목]\n{title}\n\n[설명]\n{desc}\n\n[태그]\n' + ', '.join(tags)
    (out / f'{name}_유튜브.txt').write_text(yt, encoding='utf-8')
    print(f'\n  {title}\n  길이 {hms(total)} · {mp4.stat().st_size / 1e9:.2f}GB', flush=True)
    tag = 'goedam-' + stamp.strftime('%Y%m%d-%H%M') + '-mix'; base = f'https://github.com/{W.REPO}/releases/download/{tag}/'
    W.sh('gh', 'release', 'create', tag, str(mp4), str(thumb), '--repo', W.REPO, '--title', f'괴담 몰아듣기 {stamp:%Y-%m-%d} ({hlabel})',
         '--notes', f'- {len(files)}편 · {hms(total)}')
    vid = W.yt_up(mp4, yt, thumb=thumb)
    jpg = gd / 'thumbs' / f'{name}.jpg'; (gd / 'thumbs').mkdir(parents=True, exist_ok=True)
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(thumb), '-vf', 'scale=640:-1', '-q:v', '4', str(jpg)], check=True)
    db.insert(0, {'date': f'{stamp:%Y-%m-%d}', 'kind': 'mix', 'title': title, 'sec': round(total), 'yt': yt, 'places': [], 'url': base + mp4.name,
                  'thumb_url': base + thumb.name, 'short_url': '', 'yt_id': vid, 'thumb': jpg.name})
    (gd / 'videos.json').write_text(json.dumps(db, ensure_ascii=False, indent=1), encoding='utf-8'); W.render_page(gd, db)
    comp.insert(0, {'date': f'{stamp:%Y-%m-%d}', 'title': title, 'sec': round(total), 'yt_id': vid, 'scripts': [v['script'] for v, _, _ in files], 'radio': RADIO['no'] if RADIO else None})
    cf.write_text(json.dumps(comp, ensure_ascii=False, indent=1), encoding='utf-8')
    W.sh('git', 'add', gd, cwd=root); W.sh('git', 'commit', '-m', f'괴담 몰아듣기 ({stamp:%Y-%m-%d})', cwd=root); W.push_safe(root, br)
    print(f'\n완료 → https://youtu.be/{vid}' if vid else '\n완료 (유튜브 업로드 꺼짐)', flush=True)


if __name__ == '__main__':
    main()
