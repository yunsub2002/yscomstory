#!/usr/bin/env python3
"""유튜브 자동 업로드 (YouTube Data API v3 · 무료, 추가 설치 없음)
GitHub 저장소 Secrets 에 YT_CLIENT_ID / YT_CLIENT_SECRET / YT_REFRESH_TOKEN 이 있으면 동작합니다.
(유튜브_자동업로드_설정.bat 가 한 번에 넣어 줍니다.)
YT_PRIVACY: private(기본) / unlisted / public
  ※ 구글 심사(무료) 전의 개인 프로젝트로 올린 영상은 유튜브가 '비공개'로 잠급니다 → 폰 YouTube 앱에서 공개로 바꾸면 됩니다.
"""
import json, os, subprocess, urllib.error, urllib.parse, urllib.request
from pathlib import Path


def enabled():
    return all(os.environ.get(k) for k in ('YT_CLIENT_ID', 'YT_CLIENT_SECRET', 'YT_REFRESH_TOKEN'))


def _req(url, data=None, headers=None, method=None, timeout=120):
    r = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as res:
            return res.status, dict(res.headers), res.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', 'replace')
        raise RuntimeError(f'유튜브 API 오류 {e.code}: {body[:600]}') from None


def token():
    data = urllib.parse.urlencode({'client_id': os.environ['YT_CLIENT_ID'], 'client_secret': os.environ['YT_CLIENT_SECRET'],
                                   'refresh_token': os.environ['YT_REFRESH_TOKEN'], 'grant_type': 'refresh_token'}).encode()
    _, _, b = _req('https://oauth2.googleapis.com/token', data, {'Content-Type': 'application/x-www-form-urlencoded'})
    return json.loads(b)['access_token']


def parse_yt(txt):
    """'[제목] … [설명] … [태그] …' 형식의 텍스트 → (제목, 설명, 태그 목록)"""
    sec, cur = {}, None
    for line in txt.splitlines():
        s = line.strip()
        if s in ('[제목]', '[설명]', '[태그]'): cur = s[1:-1]; sec[cur] = []; continue
        if cur: sec[cur].append(line)
    title = ' '.join(x.strip() for x in sec.get('제목', []) if x.strip())[:100]
    desc = '\n'.join(sec.get('설명', [])).strip()[:4900]
    tags, n = [], 0
    for t in ','.join(sec.get('태그', [])).split(','):
        t = t.strip().replace('<', '').replace('>', '')
        if t and t not in tags and n + len(t) + 3 < 480: tags.append(t); n += len(t) + 3
    return title, desc, tags


def upload(video, title, desc, tags, privacy=None, thumb=None, log=print):
    privacy = privacy or os.environ.get('YT_PRIVACY', 'private') or 'private'
    at = token(); size = Path(video).stat().st_size
    meta = {'snippet': {'title': title, 'description': desc, 'tags': tags, 'categoryId': '24', 'defaultLanguage': 'ko', 'defaultAudioLanguage': 'ko'},
            'status': {'privacyStatus': privacy, 'selfDeclaredMadeForKids': False, 'embeddable': True}}
    _, h, _ = _req('https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status', json.dumps(meta).encode(),
                   {'Authorization': f'Bearer {at}', 'Content-Type': 'application/json; charset=UTF-8', 'X-Upload-Content-Length': str(size), 'X-Upload-Content-Type': 'video/mp4'})
    loc = h.get('Location') or h.get('location')
    log(f'  유튜브 업로드 중… {size / 1e6:.0f}MB ({privacy})')
    for attempt in range(3):
        try:
            with open(video, 'rb') as f:
                _, _, b = _req(loc, f, {'Content-Length': str(size), 'Content-Type': 'video/mp4'}, 'PUT', timeout=3600)
            break
        except Exception as e:
            if attempt == 2: raise
            log(f'  다시 시도 ({e})'); at = token()
    vid = json.loads(b)['id']; log(f'  업로드 완료 → https://youtu.be/{vid}')
    if thumb and Path(thumb).exists():
        try:
            jpg = str(Path(thumb).with_suffix('.yt.jpg'))
            subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(thumb), '-vf', 'scale=1280:720', '-q:v', '3', jpg], check=True)
            _req(f'https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={vid}&uploadType=media', Path(jpg).read_bytes(),
                 {'Authorization': f'Bearer {token()}', 'Content-Type': 'image/jpeg'})
            log('  썸네일 지정 완료')
        except Exception as e:
            log(f'  썸네일은 지정하지 못했습니다 (채널 전화번호 인증이 필요할 수 있어요): {e}')
    return vid


if __name__ == '__main__':  # 연결 확인: python youtube_upload.py
    at = token()
    _, _, b = _req('https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true', headers={'Authorization': f'Bearer {at}'})
    items = json.loads(b).get('items', [])
    print('연결된 채널:', items[0]['snippet']['title'] if items else '(채널 없음)')
