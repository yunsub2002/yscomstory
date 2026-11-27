#!/usr/bin/env python3
"""이야기 장면 그림 그리기 — SD-Turbo (Stability AI Community License: 연 매출 100만 달러 미만 상업 이용 무료)
GitHub Actions CPU 에서 한 장 약 8~10초. API 키 필요 없음.
make(prompts, out_dir) → [jpg 경로, …] (1920×1080, 어둡고 차가운 필름 톤으로 보정)
"""
import hashlib, os, sys, time
from pathlib import Path

STYLE = (', cinematic film still, 35mm photograph, night, deep shadows, low key lighting, moody, dark horror atmosphere, '
         'muted desaturated colors, film grain, realistic, highly detailed, no text')
VIVID = (', cinematic film still, 35mm photograph, night, deep shadows, high contrast, cold blue moonlight with a hint of red, '
         'dark horror atmosphere, film grain, realistic, highly detailed, sharp focus, no text')
NEG = 'text, watermark, logo, cartoon, anime, bright colors, cheerful, blood, gore'


def grade(im, sat=.55):
    """공포 영상 톤: 채도↓, 어둡게, 차가운 그림자, 대비, 비네트 → 1920×1080"""
    import numpy as np
    from PIL import Image, ImageFilter
    im = im.convert('RGB').resize((1920, 1080), Image.LANCZOS).filter(ImageFilter.UnsharpMask(radius=2, percent=60, threshold=2))
    a = np.asarray(im).astype('float32') / 255
    g = a.mean(axis=2, keepdims=True); a = g + (a - g) * sat                      # 채도 (기본 55%, vivid 85%)
    a = np.clip((a - .5) * 1.12 + .5, 0, 1) ** 1.35 * .92                           # 대비↑, 어둡게
    a = a * np.array([.92, .97, 1.06])                                               # 차가운 색
    h, w = a.shape[:2]; y, x = np.ogrid[:h, :w]
    v = 1 - .55 * (((x - w / 2) / (w * .62)) ** 2 + ((y - h / 2) / (h * .62)) ** 2)  # 비네트
    a = a * np.clip(v, .25, 1)[..., None]
    return Image.fromarray((np.clip(a, 0, 1) * 255).astype('uint8'))


def make(prompts, out_dir, seed=7, w=768, h=448, log=print, look=''):
    style, sat = (VIVID, .85) if look == 'vivid' else (STYLE, .55)
    photo = look == 'photo'
    if look == 'occult':   # 장면마다 질감을 바꿔 다채롭고 기괴하게 (옛 사진·VHS·CCTV·꿈·촛불·달빛)
        sat = .6
        OCC = [', grainy 1990s VHS found footage still, chromatic aberration, dark horror, eerie, no text',
               ', faded sepia 1910s photograph, scratches, dust, vignette, uncanny, horror, no text',
               ', cinematic film still, candlelight, deep red and black, occult ritual atmosphere, unsettling, no text',
               ', cold blue moonlight, heavy shadows, surreal nightmare, distorted perspective, horror, no text',
               ', japanese horror film still, desaturated green tint, damp, eerie silence, film grain, no text',
               ', extreme close-up, shallow depth of field, dark, creepy texture, highly detailed, no text']
    steps = 2
    if not photo and look in ('', 'occult', 'webtoon'):   # 2026.11.27: 기본 그림체 = 웹툰 느낌의 실사풍 그림, 장면마다 6가지 화풍을 돌려 다채롭게 ('photo' 로 예전 사진풍)
        look, sat, steps = 'webtoon', .72, 3
        OCC = [', dark semi-realistic korean webtoon illustration, digital painting, realistic proportions, soft shading, cinematic night lighting, muted colors, horror',
               ', realistic horror manhwa panel, detailed digital art, dramatic shadows, desaturated blue tones, eerie',
               ', painterly realistic digital illustration, dark concept art, volumetric light, eerie atmosphere',
               ', semi-realistic animated film still, detailed background art, cold night lighting, eerie, horror',
               ', realistic graphic novel illustration, gritty texture, heavy shadows, muted palette, horror',
               ', dark digital painting, deep red and black palette, horror illustration, cinematic']
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    import torch
    from diffusers import AutoPipelineForText2Image
    torch.set_num_threads(max(1, os.cpu_count() or 2))
    t0 = time.time()
    pipe = AutoPipelineForText2Image.from_pretrained('stabilityai/sd-turbo', torch_dtype=torch.float32, safety_checker=None)
    pipe.set_progress_bar_config(disable=True)
    log(f'  그림 모델 준비 {time.time() - t0:.0f}초')
    paths = []
    for i, p in enumerate(prompts):
        f = out_dir / f'scene_{i:02d}_{hashlib.md5((p + str(seed) + look).encode()).hexdigest()[:8]}.jpg'
        if not f.exists():
            g = torch.Generator().manual_seed(seed * 100 + i)
            im = pipe(prompt=p + (OCC[i % len(OCC)] if look in ('occult', 'webtoon') else style), negative_prompt=NEG, num_inference_steps=steps, guidance_scale=0.0, width=w, height=h, generator=g).images[0]
            grade(im, sat).save(f, quality=90)
        paths.append(f)
        if i % 5 == 0: log(f'  그림 {i + 1}/{len(prompts)} ({time.time() - t0:.0f}초)')
    return paths


if __name__ == '__main__':
    import json
    meta = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    n = int(sys.argv[3]) if len(sys.argv) > 3 else None; seed = int(sys.argv[4]) if len(sys.argv) > 4 else 7
    ps = make(meta['images'][:n], sys.argv[2], seed=seed, log=lambda x: print(x, flush=True), look=meta.get('look', ''))
    (Path(sys.argv[2]) / 'list.txt').write_text('\n'.join(str(p.resolve()) for p in ps), encoding='utf-8')
