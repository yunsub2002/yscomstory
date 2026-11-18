#!/usr/bin/env python3
"""지금까지 만든 괴담 영상 전부 → 세로 숏츠 (GitHub Actions 에서 MODE=backfill 로 실행)
- 숏츠가 없는 영상만 골라 하나씩 만들고, 한 편 끝날 때마다 릴리스에 올리고 보관함(videos.json · index.html)을 저장 → 중간에 멈춰도 다음 실행에서 이어서
- 유튜브 자동 업로드는 기본으로 끔(BACKFILL_UPLOAD=0): 유튜브 API 하루 한도가 업로드 약 6개라서, 보관함 「숏츠」 탭에서 받아 직접 올리는 걸 권장
  BACKFILL_UPLOAD=1 이면 하루 최대 BACKFILL_LIMIT(기본 5)개까지 자동 업로드
"""
import datetime as dt, json, os, subprocess, sys
from pathlib import Path

BOT = Path(__file__).resolve().parent; sys.path.insert(0, str(BOT))
import weekly as W, hookshort as HS  # noqa: E402

UPLOAD = os.environ.get('BACKFILL_UPLOAD', '0') == '1'; LIMIT = int(os.environ.get('BACKFILL_LIMIT') or 5)
MAXN = int(os.environ.get('BACKFILL_MAX') or 40)


def run():
    W.sh('git', 'config', '--global', 'user.name', 'goedam-bot'); W.sh('git', 'config', '--global', 'user.email', 'goedam-bot@users.noreply.github.com')
    root, br, gd = W.pages_dir(); (gd / 'thumbs').mkdir(parents=True, exist_ok=True)
    dbp = gd / 'videos.json'; db = json.loads(dbp.read_text(encoding='utf-8'))
    todo = [v for v in db if not v.get('short_url') and (v.get('url') or v.get('script'))][:MAXN]
    print(f'숏츠가 없는 영상 {len(todo)}편 → 세로 숏츠로 만듭니다 (유튜브 자동 업로드: {"켜짐, 최대 " + str(LIMIT) + "개" if UPLOAD else "꺼짐"})', flush=True)
    if not todo: return
    stamp = dt.datetime.utcnow() + dt.timedelta(hours=9); tag = 'goedam-shorts-' + stamp.strftime('%Y%m%d-%H%M')
    W.sh('gh', 'release', 'create', tag, '--repo', W.REPO, '--title', f'괴담 숏츠 모음 {stamp:%Y-%m-%d}', '--notes', '지금까지 만든 괴담 영상의 세로 숏츠')
    base = f'https://github.com/{W.REPO}/releases/download/{tag}/'; out = W.REPO_DIR / '_out'; out.mkdir(exist_ok=True); up = 0; ok = 0
    for i, v in enumerate(todo, 1):
        name = f"s{stamp:%m%d}_{i:02d}"; print(f'\n===== [{i}/{len(todo)}] {v["title"][:60]} =====', flush=True)
        try:
            src = BOT / 'scripts' / v['script'] if v.get('script') else None
            if src and src.exists(): r = HS.from_script(src, out, name, W.CHANNEL, log=lambda s: print(s, flush=True))
            else: r = HS.from_video(v['url'], v['title'][:24], out, name, log=lambda s: print(s, flush=True))
            if not r: continue
            jpg = gd / 'thumbs' / f'{name}_s.jpg'; HS.frame_jpg(r['file'], jpg, 3.0 if r['sec'] > 6 else 1.0)
            W.sh('gh', 'release', 'upload', tag, r['file'], '--repo', W.REPO, '--clobber')
            v.update(short_url=base + r['file'].name, short_yt=r['yt'], short_thumb=jpg.name, short_sec=r['sec'])
            if UPLOAD and up < LIMIT:
                yid = W.yt_up(r['file'], r['yt'])
                if yid: v['short_yt_id'] = yid; up += 1
            dbp.write_text(json.dumps(db, ensure_ascii=False, indent=1), encoding='utf-8'); W.render_page(gd, db)
            W.sh('git', 'add', gd, cwd=root); W.sh('git', 'commit', '-q', '-m', f'숏츠 추가: {r["title"][:50]}', cwd=root); W.push_safe(root, br); ok += 1
            r['file'].unlink(missing_ok=True)
        except Exception as e:
            import traceback; traceback.print_exc(); print(f'  ✗ 건너뜀: {e}', flush=True)
    user, rn = W.REPO.split('/'); print(f'\n===== 숏츠 {ok}/{len(todo)}편 완료 → https://{user}.github.io/{rn}/goedam/#shorts', flush=True)


if __name__ == '__main__':
    run()
