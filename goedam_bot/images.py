#!/usr/bin/env python3
"""이야기 장면 그림 그리기 — SD-Turbo (Stability AI Community License: 연 매출 100만 달러 미만 상업 이용 무료)
GitHub Actions CPU 에서 한 장 약 8~10초. API 키 필요 없음.
make(prompts, out_dir) → [jpg 경로, …] (1920×1080, 어둡고 차가운 필름 톤으로 보정)
"""
import hashlib, os, sys, time
from pathlib import Path

STYLE = (', cinematic film still, 35mm photograph, night, deep shadows, low key lighting, moody, dark horror atmosphere, '
         'muted desaturated colors, film grain, realistic, highly detailed, no text')
NEG = 'text, watermark, logo, cartoon, anime, bright colors, cheerful, blood, gore'


def grade(im):
    """공포 영상 톤: 채도↓, 어둡게, 차가운 그림자, 대비, 비네트 → 1920×1080"""
    import numpy as np
    from PIL import Image, ImageFilter
    im = im.convert('RGB').resize((1920, 1080), Image.LANCZOS).filter(ImageFilter.UnsharpMask(radius=2, percent=60, threshold=2))
    a = np.asarray(im).astype('float32') / 255
    g = a.mean(axis=2, keepdims=True); a = g + (a - g) * .55                      # 채도 55%
    a = np.clip((a - .5) * 1.12 + .5, 0, 1) ** 1.35 * .92                           # 대비↑, 어둡게
    a = a * np.array([.92, .97, 1.06])                                               # 차가운 색
    h, w = a.shape[:2]; y, x = np.ogrid[:h, :w]
    v = 1 - .55 * (((x - w / 2) / (w * .62)) ** 2 + ((y - h / 2) / (h * .62)) ** 2)  # 비네트
    a = a * np.clip(v, .25, 1)[..., None]
    return Image.fromarray((np.clip(a, 0, 1) * 255).astype('uint8'))


def make(prompts, out_dir, seed=7, w=768, h=448, log=print):
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
        f = out_dir / f'scene_{i:02d}_{hashlib.md5((p + str(seed)).encode()).hexdigest()[:8]}.jpg'
        if not f.exists():
            g = torch.Generator().manual_seed(seed * 100 + i)
            im = pipe(prompt=p + STYLE, negative_prompt=NEG, num_inference_steps=2, guidance_scale=0.0, width=w, height=h, generator=g).images[0]
            grade(im).save(f, quality=90)
        paths.append(f)
        if i % 5 == 0: log(f'  그림 {i + 1}/{len(prompts)} ({time.time() - t0:.0f}초)')
    return paths


if __name__ == '__main__':
    import json
    meta = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    n = int(sys.argv[3]) if len(sys.argv) > 3 else None; seed = int(sys.argv[4]) if len(sys.argv) > 4 else 7
    ps = make(meta['images'][:n], sys.argv[2], seed=seed, log=lambda x: print(x, flush=True))
    (Path(sys.argv[2]) / 'list.txt').write_text('\n'.join(str(p.resolve()) for p in ps), encoding='utf-8')
