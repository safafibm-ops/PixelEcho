"""Generate clearly labeled synthetic files for the offline comparison demo."""
from pathlib import Path
import cv2
import numpy as np


def scene(seed):
    random = np.random.default_rng(seed)
    image = np.full((480, 640, 3), 230, np.uint8)
    for i in range(90):
        x, y = random.integers([5, 5], [620, 460])
        color = tuple(int(v) for v in random.integers(15, 200, 3))
        cv2.circle(image, (int(x), int(y)), int(random.integers(4, 24)), color, -1)
        cv2.putText(image, str(i), (int(x), int(y)), cv2.FONT_HERSHEY_SIMPLEX, .4, (15, 15, 15), 1)
    cv2.putText(image, 'SYNTHETIC DEMO FIXTURE', (30, 250), cv2.FONT_HERSHEY_SIMPLEX, .8, (0, 0, 0), 2)
    return image


if __name__ == '__main__':
    folder = Path(__file__).resolve().parent / 'demo'
    folder.mkdir(exist_ok=True)
    original = scene(42)
    cv2.imwrite(str(folder / '01-original.png'), original)
    cv2.imwrite(str(folder / '02-cropped.png'), original[60:420, 70:570])
    cv2.imwrite(str(folder / '03-compressed.jpg'), original, [cv2.IMWRITE_JPEG_QUALITY, 65])
    canvas = np.full((650, 800, 3), 245, np.uint8)
    canvas[80:560, 80:720] = original
    cv2.imwrite(str(folder / '04-simulated-canvas.png'), canvas)
    cv2.imwrite(str(folder / '05-unrelated.png'), scene(982))
    print('Created five synthetic comparison fixtures in demo/. These are not public-web search examples or genuine screenshots.')
