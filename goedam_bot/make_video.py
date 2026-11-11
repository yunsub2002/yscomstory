#!/usr/bin/env python3
"""괴담 낭독 영상 자동 제작
사용: python3 pipeline/make_video.py stories/01_제목.txt [--res 1080] [--channel 이름]
1) 원고 문장마다 Supertonic-3 한국어 여성 음성(동화구연 톤)으로 읽기
2) web/index.html(장면·자막·배경음·효과음 엔진)을 헤드리스 크롬으로 돌려 MP4 만들기
3) 오디오를 AAC로 바꿔 아이폰·유튜브 호환 MP4로 저장 + 썸네일 + 유튜브 설명문
"""
import argparse, hashlib, json, os, re, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VOICE = {'main': ('F2', .85), '댓글': ('F4', .92), '여': ('F2', .85), '남': ('M1', .9)}


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
        if not L or L.startswith('#') or re.match(r'^\[(장면|효과|쉼)\s*:', L): continue
        who, text = 'main', L
        m = re.match(r'^(댓글|남|여)\s*:\s*(.*)$', L)
        if m: who, text = m.group(1), m.group(2)
        for s in sentences(text): items.append((who, s))
    return items


def synth(items, cache):
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
        key = hashlib.md5(f'{v}|{sp}|{s}'.encode()).hexdigest()[:16]; f = cache / f'{key}.wav'
        if not f.exists():
            if v not in styles: styles[v] = tts.get_voice_style(v)
            wav, _ = tts.synthesize(s, voice_style=styles[v], lang='ko', speed=sp, total_steps=12)
            w = np.asarray(wav, dtype='float32').squeeze()
            # 앞뒤 무음 정리 + 끝 살짝 페이드
            nz = np.where(np.abs(w) > .01)[0]
            if len(nz): w = w[max(0, nz[0] - 600): nz[-1] + 2200]
            fade = min(len(w), 1200); w[-fade:] *= np.linspace(1, 0, fade)
            sf.write(f, w, 44100, subtype='PCM_16')
        table.setdefault(s, f.name)
        if i % 10 == 0: print(f'  음성 {i + 1}/{len(items)}', flush=True)
    return table


def render(story_path, table, cache, out_mp4, res, channel, vbr):
    from playwright.sync_api import sync_playwright
    src = story_path.read_text(encoding='utf-8')
    with sync_playwright() as pw:
        b = pw.chromium.launch(args=['--autoplay-policy=no-user-gesture-required'])
        ctx = b.new_context(viewport={'width': 1400, 'height': 900}, accept_downloads=True)
        page = ctx.new_page(); errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))
        page.route('http://aud.local/**', lambda r: r.fulfill(path=str(cache / r.request.url.rsplit('/', 1)[1]), content_type='audio/wav'))
        page.goto((ROOT / 'web' / 'index.html').as_uri()); page.wait_for_timeout(1500)
        page.evaluate("""([src, table, res, channel, vbr]) => {
          S.engine = 'ext'; S.res = res; S.channel = channel; S.vbr = vbr; S.bgm = .2; S.reverb = .18; S.voiceCredit = 'AI 음성(Supertonic) — 이 영상의 목소리는 AI가 생성했습니다'; window.showSaveFilePicker = undefined;
          TTS.get = async (text, voice) => { const f = table[text]; if (!f) throw new Error('음성 없음: ' + text);
            const ab = await (await fetch('http://aud.local/' + f)).arrayBuffer(); return await ac().decodeAudioData(ab); };
          document.querySelector('#script').value = src; }""", [src, table, res, channel, vbr])
        page.click('#bMake'); page.wait_for_selector('#after:not([hidden])', timeout=900000)
        total = page.evaluate('PROJ.total'); print(f'  길이 {total / 60:.1f}분 — 영상 인코딩 시작', flush=True)
        with page.expect_download(timeout=7200000) as dl: page.click('#bMP4')
        dl.value.save_as(str(out_mp4) + '.tmp.mp4')
        short_tmp = None
        if total <= 180:  # 유튜브 숏츠는 3분 이하
            print('  숏츠(세로) 인코딩', flush=True)
            with page.expect_download(timeout=7200000) as d3: page.click('#bShort')
            short_tmp = str(out_mp4.with_name(out_mp4.stem + '_short.tmp.mp4')); d3.value.save_as(short_tmp)
        with page.expect_download() as d2: page.click('#bThumb')
        d2.value.save_as(str(out_mp4.with_name(out_mp4.stem + '_썸네일.png')))
        yt = page.evaluate('ytText()'); srt = page.evaluate('srt()')
        b.close()
        if errs: print('  페이지 경고:', errs[:3])
    out_mp4.with_name(out_mp4.stem + '_유튜브.txt').write_text(yt, encoding='utf-8')
    out_mp4.with_name(out_mp4.stem + '.srt').write_text(srt, encoding='utf-8')
    # 오디오 AAC 로 (아이폰 사진앱·유튜브 호환), 영상은 그대로
    def aac(src, dst):  # 오디오 AAC 로 (아이폰 사진앱·유튜브 호환), 영상은 그대로
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', src, '-c:v', 'copy', '-af', 'loudnorm=I=-16:TP=-1.5:LRA=11', '-ar', '48000', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', dst], check=True)
        os.remove(src)
    aac(str(out_mp4) + '.tmp.mp4', str(out_mp4))
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
