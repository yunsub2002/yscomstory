#!/usr/bin/env python3
"""1분 완결 괴담 숏츠 — 본편 없이, 줄거리와 결말까지 1분 안에 끝나는 세로 숏츠만 만듦 (MODE=onemin)
- 원고: goedam_bot/shorts/*.txt (+ 같은 이름 .json: 제목·썸네일 문구·장면 그림 6~7장)
- 아직 안 만든 원고만 차례로 (한 번에 최대 ONEMIN_MAX 편, 기본 5) → 릴리스 보관 → 보관함 「숏츠」 탭 → (설정 시) 유튜브 자동 업로드
"""
import datetime as dt, json, os, sys
from pathlib import Path

BOT = Path(__file__).resolve().parent; sys.path.insert(0, str(BOT))
import weekly as W, hookshort as HS, make_video as mv  # noqa: E402

MAXN = int(os.environ.get('ONEMIN_MAX') or 5)


def yt_text(meta, title):
    desc = meta.get('desc', '') + '\n\n' + W.GD_SUB_DESC
    tags = meta.get('tags', ['일본 괴담', '1분 괴담', 'shorts'])
    return f"[제목]\n{meta.get('yt_title', title + ' #shorts')}\n\n[설명]\n{desc}\n" + ' '.join('#' + t.replace(' ', '') for t in tags[:6]) + f"\n\n[태그]\n{', '.join(tags)}"


def run():
    W.sh('git', 'config', '--global', 'user.name', 'goedam-bot'); W.sh('git', 'config', '--global', 'user.email', 'goedam-bot@users.noreply.github.com')
    root, br, gd = W.pages_dir(); (gd / 'thumbs').mkdir(parents=True, exist_ok=True)
    dbp = gd / 'videos.json'; db = json.loads(dbp.read_text(encoding='utf-8')) if dbp.exists() else []
    done = {v.get('script') for v in db}
    todo = [p for p in sorted((BOT / 'shorts').glob('*.txt')) if f'shorts/{p.name}' not in done][:MAXN]
    print(f'1분 완결 숏츠 {len(todo)}편을 만듭니다: ' + ', '.join(p.stem for p in todo), flush=True)
    if not todo: return
    stamp = dt.datetime.utcnow() + dt.timedelta(hours=9); tag = 'goedam-1min-' + stamp.strftime('%Y%m%d-%H%M')
    W.sh('gh', 'release', 'create', tag, '--repo', W.REPO, '--title', f'1분 괴담 숏츠 {stamp:%Y-%m-%d}', '--notes', '줄거리와 결말까지 1분 안에 끝나는 괴담 숏츠')
    base = f'https://github.com/{W.REPO}/releases/download/{tag}/'; out = W.REPO_DIR / '_out' / 'onemin'; out.mkdir(parents=True, exist_ok=True)
    for i, src in enumerate(todo, 1):
        meta = json.loads(src.with_suffix('.json').read_text(encoding='utf-8')) if src.with_suffix('.json').exists() else {}
        txt = src.read_text(encoding='utf-8'); title = next((l.lstrip('# ').strip() for l in txt.splitlines() if l.startswith('#')), src.stem)
        name = f'onemin_{stamp:%m%d}_{i:02d}'; print(f'\n===== [{i}/{len(todo)}] {title} =====', flush=True)
        try:
            imgs = HS.gen_images(src.with_suffix('.json'), out / f'{name}_imgs', len(meta.get('images', [])) or 6, lambda s: print(s, flush=True))
            mv.EDGE_RATE = meta.get('rate') or mv.EDGE_RATE
            sp = out / f'{name}.txt'; sp.write_text(txt, encoding='utf-8')
            tab = mv.synth(mv.parse(txt), BOT / '.tts_cache', src=txt)
            label = meta.get('thumb', {}).get('label') or '1분 괴담'
            sec = mv.render(sp, tab, BOT / '.tts_cache', out / f'{name}.mp4', 1080, W.CHANNEL, 3.5e6, main=False, short=True, images=imgs or None,
                            opts={'shortLabel': label, 'shortHook': '결말까지 1분, 끝까지 들어 보세요', 'shortOutro': ['구독하고', '매일 밤 1분 괴담']})
            f = out / f'{name}_short.mp4'
            if not f.exists(): print('  ! 숏츠가 만들어지지 않았습니다', flush=True); continue
            print(f'  길이 {sec:.0f}초' + ('  ⚠ 60초를 넘었습니다' if sec > 60 else ''), flush=True)
            jpg = gd / 'thumbs' / f'{name}_s.jpg'; HS.frame_jpg(f, jpg, 3.0)
            W.sh('gh', 'release', 'upload', tag, f, '--repo', W.REPO, '--clobber')
            yt = yt_text(meta, title)
            e = dict(date=f'{stamp:%Y-%m-%d}', kind='short', title=meta.get('yt_title', title), sec=round(sec), yt=yt, places=[], script=f'shorts/{src.name}',
                     short_url=base + f.name, short_yt=yt, short_thumb=jpg.name, short_sec=round(sec), thumb=jpg.name)
            e['short_yt_id'] = W.yt_up(f, yt)
            db.insert(0, e); dbp.write_text(json.dumps(db, ensure_ascii=False, indent=1), encoding='utf-8'); W.render_page(gd, db)
        except Exception as ex:
            print(f'  ! {src.name} 건너뜀: {ex}', flush=True)
    W.sh('git', 'add', gd, cwd=root); W.sh('git', 'commit', '-m', f'1분 괴담 숏츠 ({stamp:%Y-%m-%d})', cwd=root, check=False); W.push_safe(root, br)
    user, rn = W.REPO.split('/'); print(f'\n완료 → https://{user}.github.io/{rn}/goedam/#shorts', flush=True)


if __name__ == '__main__':
    run()
