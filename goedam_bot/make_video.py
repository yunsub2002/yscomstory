#!/usr/bin/env python3
"""괴담 낭독 영상 자동 제작
사용: python3 pipeline/make_video.py stories/01_제목.txt [--res 1080] [--channel 이름]
1) 원고 문장마다 Supertonic-3 한국어 음성으로 읽기 — 진행·본문은 낮고 잔잔한 남자 목소리(M2)
2) web/index.html(장면·자막·배경음·효과음 엔진)을 헤드리스 크롬으로 돌려 MP4 만들기
3) 오디오를 AAC로 바꿔 아이폰·유튜브 호환 MP4로 저장 + 썸네일 + 유튜브 설명문
"""
import argparse, hashlib, json, os, re, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
# 진행자·본문: M2 (가장 낮고 차분한 남자 목소리, 약 86Hz) / 댓글: M3 / 남자 대사: M1 / 여자 대사: F2
VOICE = {'main': ('M2', .86), '댓글': ('M3', .95), '여': ('F2', .86), '남': ('M1', .9)}
STEPS = 14
# 기본 목소리: 마이크로소프트 신경망 음성 InJoon (무료 · 키 필요 없음, edge-tts). 실패하면 Supertonic 으로 자동 전환
ENGINE = os.environ.get('VOICE_ENGINE', 'edge')
EDGE_VOICE, EDGE_RATE, EDGE_PITCH = os.environ.get('EDGE_VOICE', 'ko-KR-InJoonNeural'), os.environ.get('EDGE_RATE', '-6%'), os.environ.get('EDGE_PITCH', '-2Hz')


def sentences(text):
    parts = [p.strip() for p in re.findall(r'[^.?!…。]+[.?!…。]*["\'”’)]*\s*', text) if p.strip()] or [text]
    out = []
    for p in parts:
        if out and len(p) < 6: out[-1] += ' ' + p
        else: out.append(p)
    fin = []
    for s in out:
        if len(s) <= 70: fin.append(s); continue
        cur = ''
        for seg in re.split(r'(?<=,)\s*', s):
            if len(cur + seg) > 70 and cur: fin.append(cur.strip()); cur = ''
            cur += seg + ' '
        if cur.strip(): fin.append(cur.strip())
    return fin


def parse(src):  # web/app.js 의 parse 와 같은 규칙
    items = []
    for raw in src.splitlines():
        L = raw.strip()
        if not L or L.startswith('#') or re.match(r'^\[(장면|효과|쉼|챕터)\s*:', L): continue
        who, text = 'main', L
        m = re.match(r'^(댓글|남|여)\s*:\s*(.*)$', L)
        if m: who, text = m.group(1), m.group(2)
        for s in sentences(text): items.append((who, s))
    return items


def synth_edge(items, cache):
    """한 사람 목소리(InJoon)로 문장마다 mp3 만들기 — 동시에 4개씩"""
    import asyncio
    if os.path.exists('/root/.ccr/ca-bundle.crt'):  # (테스트 환경용 인증서)
        import certifi; certifi.where = lambda: '/root/.ccr/ca-bundle.crt'
    import edge_tts
    cache.mkdir(parents=True, exist_ok=True); table = {}; todo = []
    for who, s in items:
        key = hashlib.md5(f'edge|{EDGE_VOICE}|{EDGE_RATE}|{EDGE_PITCH}|{s}'.encode()).hexdigest()[:16]; f = cache / f'{key}.mp3'
        table.setdefault(s, f.name)
        if not f.exists() or f.stat().st_size < 500: todo.append((s, f))
    async def one(sem, s, f):
        async with sem:
            for k in range(5):
                try:
                    await edge_tts.Communicate(s, EDGE_VOICE, rate=EDGE_RATE, pitch=EDGE_PITCH).save(str(f))
                    if f.stat().st_size > 500: return
                except Exception as e:
                    if k == 4: raise
                await asyncio.sleep(2 + k * 3)
    async def run():
        sem = asyncio.Semaphore(4); done = 0
        for i in range(0, len(todo), 40):
            await asyncio.gather(*(one(sem, s, f) for s, f in todo[i:i + 40])); done += len(todo[i:i + 40]); print(f'  음성 {done}/{len(todo)}', flush=True)
    asyncio.run(run()); return table


def synth(items, cache):
    if ENGINE == 'edge':
        try: return synth_edge(items, cache)
        except Exception as e: print('  ! InJoon 음성 실패 → Supertonic 으로 대신 만듭니다:', e, flush=True)
    import numpy as np, soundfile as sf
    from supertonic import TTS
    tts = TTS(); styles = {}
    cache.mkdir(parents=True, exist_ok=True); table = {}
    for i, (who, s) in enumerate(items):
        v, sp = VOICE.get(who, VOICE['main'])
        # 짧은 문장·말줄임·마지막 반전 문장은 천천히, 긴 설명 문장은 살짝 빠르게 (사람이 읽는 리듬)
        if len(s) < 12 or s.endswith(('...', '…')): sp *= .93
        elif len(s) > 45: sp *= 1.03
        sp = round(max(.7, min(1.2, sp)), 3)
        key = hashlib.md5(f'{v}|{sp}|{STEPS}|{s}'.encode()).hexdigest()[:16]; f = cache / f'{key}.wav'
        if not f.exists():
            if v not in styles: styles[v] = tts.get_voice_style(v)
            wav, _ = tts.synthesize(s, voice_style=styles[v], lang='ko', speed=sp, total_steps=STEPS)
            w = np.asarray(wav, dtype='float32').squeeze()
            # 앞뒤 무음 정리 + 끝 살짝 페이드
            nz = np.where(np.abs(w) > .01)[0]
            if len(nz): w = w[max(0, nz[0] - 600): nz[-1] + 2200]
            fade = min(len(w), 1200); w[-fade:] *= np.linspace(1, 0, fade)
            sf.write(f, w, 44100, subtype='PCM_16')
        table.setdefault(s, f.name)
        if i % 50 == 0: print(f'  음성 {i + 1}/{len(items)}', flush=True)
    return table


def render(story_path, table, cache, out_mp4, res, channel, vbr, main=True, short='auto', thumb=None):
    """main: 가로 영상 · short: 'auto'(3분 이하일 때)/True/False"""
    from playwright.sync_api import sync_playwright
    src = story_path.read_text(encoding='utf-8')
    with sync_playwright() as pw:
        b = pw.chromium.launch(args=['--autoplay-policy=no-user-gesture-required'])
        ctx = b.new_context(viewport={'width': 1400, 'height': 900}, accept_downloads=True)
        page = ctx.new_page(); errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))
        def serve(r):
            n = r.request.url.rsplit('/', 1)[1]
            if n == '__bgm': return r.fulfill(path=str(ROOT / 'web' / 'bgm_mystery.mp3'), content_type='audio/mpeg')
            r.fulfill(path=str(cache / n), content_type='audio/mpeg' if n.endswith('.mp3') else 'audio/wav')
        page.route('http://aud.local/**', serve)
        page.goto((ROOT / 'web' / 'index.html').as_uri()); page.wait_for_timeout(1500)
        page.evaluate("""([src, table, res, channel, vbr, thumb]) => {
          S.engine = 'ext'; S.res = res; S.channel = channel; S.vbr = vbr; S.bgm = .2; S.reverb = .1; S.bgmUrl = 'http://aud.local/__bgm'; S.noBreath = true; S.thumb = thumb; S.scenes = '숲,복도,창문,골목,방,터널'; S.voiceCredit = 'AI 음성 — 이 영상의 목소리는 AI가 생성했습니다'; window.showSaveFilePicker = undefined;
          TTS.get = async (text, voice) => { const f = table[text]; if (!f) throw new Error('음성 없음: ' + text);
            const ab = await (await fetch('http://aud.local/' + f)).arrayBuffer(); return await ac().decodeAudioData(ab); };
          document.querySelector('#script').value = src; }""", [src, table, res, channel, vbr, thumb])
        page.click('#bMake'); page.wait_for_selector('#after:not([hidden])', timeout=1800000)
        total = page.evaluate('PROJ.total'); print(f'  길이 {total / 60:.1f}분', flush=True)
        if main:
            page.evaluate('S.fps = PROJ.total > 600 ? 24 : 30')   # 긴 영상은 24fps (화면이 천천히 움직여서 차이 없음, 인코딩 빨라짐)
            t1 = time.time(); print('  가로 영상 인코딩 시작', flush=True)
            with page.expect_download(timeout=14400000) as dl: page.click('#bMP4')
            dl.value.save_as(str(out_mp4) + '.tmp.mp4'); print(f'  인코딩 {time.time() - t1:.0f}초', flush=True)
        short_tmp = None
        if (short is True or short == 'auto') and total <= 180:  # 유튜브 숏츠는 3분 이하
            page.evaluate('S.fps = 30')
            print('  숏츠(세로) 인코딩', flush=True)
            with page.expect_download(timeout=7200000) as d3: page.click('#bShort')
            short_tmp = str(out_mp4.with_name(out_mp4.stem + '_short.tmp.mp4')); d3.value.save_as(short_tmp)
        if main:
            with page.expect_download() as d2: page.click('#bThumb')
            d2.value.save_as(str(out_mp4.with_name(out_mp4.stem + '_썸네일.png')))
        yt = page.evaluate('ytText()'); srt = page.evaluate('srt()')
        b.close()
        if errs: print('  페이지 경고:', errs[:3])
    if main:
        out_mp4.with_name(out_mp4.stem + '_유튜브.txt').write_text(yt, encoding='utf-8')
        out_mp4.with_name(out_mp4.stem + '.srt').write_text(srt, encoding='utf-8')
    # 오디오 AAC 로 (아이폰 사진앱·유튜브 호환), 영상은 그대로
    def aac(src, dst):  # 오디오 AAC 로 (아이폰 사진앱·유튜브 호환), 영상은 그대로
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', src, '-c:v', 'copy', '-af', 'loudnorm=I=-16:TP=-1.5:LRA=11', '-ar', '48000', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', dst], check=True)
        os.remove(src)
    if main: aac(str(out_mp4) + '.tmp.mp4', str(out_mp4))
    if short_tmp: aac(short_tmp, str(out_mp4.with_name(out_mp4.stem + '_short.mp4')))
    return total


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('story'); ap.add_argument('--res', type=int, default=1080); ap.add_argument('--channel', default='')
    ap.add_argument('--vbr', type=float, default=3.5e6); ap.add_argument('--out', default=str(ROOT / 'out'))
    a = ap.parse_args(); sp = Path(a.story); src = sp.read_text(encoding='utf-8')
    title = next((l.lstrip('# ').strip() for l in src.splitlines() if l.startswith('#')), sp.stem)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True); cache = ROOT / '.tts_cache'
    t0 = time.time(); items = parse(src); print(f'[{title}] 문장 {len(items)}개 — 음성 합성', flush=True)
    table = synth(items, cache)
    mp4 = out / (re.sub(r'[\\/:*?"<>|]', '_', title).replace(' ', '_') + '.mp4')
    total = render(sp, table, cache, mp4, a.res, a.channel, a.vbr)
    print(f'완료: {mp4} ({total / 60:.1f}분, {mp4.stat().st_size / 1e6:.0f}MB, {time.time() - t0:.0f}초 걸림)')


if __name__ == '__main__':
    main()
