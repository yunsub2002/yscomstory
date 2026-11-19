#!/usr/bin/env python3
"""30분 이야기 → 세로 숏츠 (1080x1920)
1) 원고가 있는 영상: 원고 첫 부분(가장 무서운 장면을 먼저 보여 주는 '도입부', 첫 [챕터] 전까지)을
   같은 AI 목소리로 다시 읽고, 장면 그림 몇 장 + 큰 자막으로 세로 숏츠를 만듦. 끝 화면: '전체 이야기는 채널에서 ▶'
2) 원고가 없는 예전 영상: 가로 영상을 세로 화면 가운데에 놓고 위아래는 흐린 배경 + 제목 (3분 넘으면 앞 58초만)
숏츠마다 유튜브 제목·설명·태그도 함께 만듦 (weekly.py 의 [제목]/[설명]/[태그] 형식 그대로)
"""
import json, os, re, subprocess, sys
from pathlib import Path

BOT = Path(__file__).resolve().parent
sys.path.insert(0, str(BOT))
FONT = next((p for p in ['/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc', '/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc', 'C:/Windows/Fonts/malgunbd.ttf'] if os.path.exists(p)), None)
REAL = ('실화', '미제', '사건', '미스터리', '컨저링')
LABEL = os.environ.get('SHORT_LABEL', '이상한 이야기 귀담')


def series(meta):
    """'… | 일본 최악의 괴담 '팔척귀신' 포포포 [괴담 파일]' → ('일본 최악의 괴담 '팔척귀신' 포포포', '괴담 파일')"""
    t = meta.get('yt_title', ''); right = t.split(' | ', 1)[1] if ' | ' in t else t
    m = re.search(r'\[([^\]]+)\]\s*$', right); tag = m.group(1) if m else ''
    return re.sub(r'\s*\[[^\]]+\]\s*$', '', right).strip(), tag


def is_real(meta):
    return any(k in (meta.get('thumb', {}).get('label', '') + series(meta)[1]) for k in REAL)


def hook_script(txt, meta):
    """원고에서 도입부만 떼어 숏츠 원고로"""
    lines = txt.splitlines(); hook = []
    for l in lines[1:]:
        if l.startswith('[챕터'): break
        hook.append(l)
    while hook and (not hook[-1].strip() or hook[-1].startswith('[쉼')): hook.pop()
    head = ' '.join(meta.get('thumb', {}).get('lines', [])) or lines[0].lstrip('# ').strip()
    end = ('이 사건의 전체 기록은, 채널의 본편 영상에서 이어집니다.' if is_real(meta) else '이 이야기의 끝은, 채널의 본편 영상에서 들으실 수 있습니다.')
    return f'# {head}\n' + '\n'.join(hook) + f'\n[쉼:1.2]\n{end}\n', head


def short_yt(meta, head):
    name, tag = series(meta)
    title = f'{head} | {name} #shorts'
    if len(title) > 100: title = f'{head} #shorts'
    desc = meta.get('desc', ''); first = desc.split('\n\n')[0].strip()
    sents = re.split(r'(?<=[.!?。])\s+', first); lead = ' '.join(sents[:2]).strip()
    notes = '\n'.join(l for l in desc.splitlines() if l.startswith('※'))
    tags = list(dict.fromkeys(meta.get('tags', [])[:10] + ['shorts', '쇼츠', '괴담 쇼츠']))
    body = (f'{lead}\n\n▶ 전체 이야기(30분)는 채널 영상에서 이어서 들을 수 있어요.\n\n' + (notes + '\n\n' if notes else '') +
            ' '.join('#' + t.replace(' ', '') for t in ['shorts'] + tags[:6]))
    return f'[제목]\n{title}\n\n[설명]\n{body}\n\n[태그]\n' + ', '.join(tags), title


def gen_images(meta_json, out_dir, n=4, log=print):
    """이야기 장면 그림 n장 (images.py, SD-Turbo) — 실패하면 빈 목록"""
    meta = json.loads(Path(meta_json).read_text(encoding='utf-8'))
    if not meta.get('images'): return []
    tmp = Path(out_dir) / 'meta_short.json'; tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json.dumps(dict(meta, images=meta['images'][:n]), ensure_ascii=False), encoding='utf-8')
    try:
        subprocess.run([sys.executable, str(BOT / 'images.py'), str(tmp), str(out_dir), str(n), str(sum(map(ord, Path(meta_json).name)) % 97)], check=True, timeout=1800)
        return [Path(l) for l in (Path(out_dir) / 'list.txt').read_text(encoding='utf-8').splitlines() if l.strip()]
    except Exception as e:
        log(f'  ! 장면 그림 실패 → 기본 화면으로: {e}'); return []


def from_script(src, out, name, channel='', imgs=None, log=print):
    """원고(.txt + .json) → 도입부 세로 숏츠. 반환: dict(file, title, sec, yt) 또는 None"""
    import make_video as mv
    src = Path(src); meta = json.loads(src.with_suffix('.json').read_text(encoding='utf-8')) if src.with_suffix('.json').exists() else {}
    st, head = hook_script(src.read_text(encoding='utf-8'), meta)
    sp = out / f'{name}_h.txt'; sp.write_text(st, encoding='utf-8')
    if meta.get('rate'): mv.EDGE_RATE = meta['rate']
    if imgs is None: imgs = gen_images(src.with_suffix('.json'), out / f'{name}_imgs', 4, log)
    log(f'  숏츠 원고: {head} ({len(st)}자)')
    tab = mv.synth(mv.parse(st), BOT / '.tts_cache', src=st)
    label = meta.get('thumb', {}).get('label') or series(meta)[1] or '괴담'
    sec = mv.render(sp, tab, BOT / '.tts_cache', out / f'{name}_h.mp4', 1080, channel, 3.5e6, main=False, short=True, images=imgs[:4] or None,
                    opts={'shortLabel': label, 'shortHook': '끝까지 들으면 소름 돋는 이야기', 'shortOutro': ['전체 이야기는', '채널에서 ▶']})
    f = out / f'{name}_h_short.mp4'
    if not f.exists(): log('  ! 숏츠가 만들어지지 않았습니다 (3분 초과?)'); return None
    yt, title = short_yt(meta, head)
    return dict(file=f, title=title, sec=round(sec), yt=yt)


def from_video(url, title, out, name, log=print):
    """원고 없는 예전 영상 → 세로 숏츠 (가로 영상을 가운데, 위아래 흐린 배경 + 제목). 3분 넘으면 앞 58초"""
    if str(url).startswith('http'):                                       # 먼저 내려받기 (스트리밍은 중간에 끊길 수 있음)
        import time, urllib.request
        local = out / f'{name}_src.mp4'
        for k in range(4):
            try: urllib.request.urlretrieve(url, local); break
            except Exception as e:
                if k == 3: raise
                log(f'  내려받기 다시 시도 ({e})'); time.sleep(5 * (k + 1))
        url = str(local)
    dur = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', url], capture_output=True, text=True).stdout.strip() or 0)
    cut = ['-t', '58'] if dur > 178 else []
    tf = out / f'{name}_title.txt'; tf.write_text(title, encoding='utf-8')
    tf2 = out / f'{name}_sub.txt'; tf2.write_text('전체 이야기는 채널에서 ▶' if cut else '구독하고 다음 괴담 듣기', encoding='utf-8')
    font = f":fontfile='{FONT}'" if FONT else ''
    vf = (f"[0:v]split[a][b];[a]scale=-2:1920,crop=1080:1920,boxblur=22:3,eq=brightness=-0.22[bg];[b]crop=ih*4/3:ih,scale=1080:-2[fg];"
          f"[bg][fg]overlay=(W-w)/2:(H-h)/2-60[v];"
          f"[v]drawtext=textfile='{tf}'{font}:fontsize=74:fontcolor=0xf2ede2:borderw=8:bordercolor=black:x=(w-text_w)/2:y=330,"
          f"drawtext=text='{LABEL}'{font}:fontsize=46:fontcolor=0xe0302a:borderw=4:bordercolor=black:x=(w-text_w)/2:y=240,"
          f"drawtext=textfile='{tf2}'{font}:fontsize=54:fontcolor=white:borderw=6:bordercolor=black:x=(w-text_w)/2:y=1560[o]")
    f = out / f'{name}_v_short.mp4'
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', url, *cut, '-filter_complex', vf, '-map', '[o]', '-map', '0:a?', '-c:v', 'libx264', '-preset', 'medium', '-crf', '21',
                    '-maxrate', '6M', '-bufsize', '12M', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '160k', '-ar', '48000', '-movflags', '+faststart', str(f)], check=True)
    sec = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(f)], capture_output=True, text=True).stdout.strip() or 0)
    if str(url).endswith('_src.mp4'): Path(url).unlink(missing_ok=True)
    tags = ['괴담', '무서운 이야기', '공포', '괴담 낭독', '2ch 괴담', '쇼츠 괴담', 'shorts']
    yt = (f'[제목]\n{title} | 잠들기 전 괴담 #shorts #괴담 #무서운이야기\n\n[설명]\n{title} — 짧은 괴담 한 편.\n'
          + ('▶ 전체 이야기는 채널 영상에서 이어서 들을 수 있어요.\n' if cut else '') +
          '\n※ 창작한 이야기(픽션)입니다. 낭독: AI 음성\n\n#shorts #괴담 #무서운이야기 #공포\n\n[태그]\n' + ', '.join(tags))
    return dict(file=f, title=f'{title} #shorts', sec=round(sec), yt=yt)


def frame_jpg(mp4, jpg, at=3.0):
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-ss', str(at), '-i', str(mp4), '-frames:v', '1', '-vf', 'scale=360:-1', '-q:v', '4', str(jpg)], check=True)
