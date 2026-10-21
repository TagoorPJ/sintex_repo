// client side image checks, palette + background sampling

export const ACCEPTED_TYPES = ['image/png', 'image/jpeg', 'image/webp'];
export const MAX_UPLOAD_BYTES = 15 * 1024 * 1024;
export const WHATSAPP_MAX_BYTES = 5 * 1024 * 1024;

export interface ImageNotice {
  level: 'error' | 'warning' | 'info';
  message: string;
}

export interface CheckedImage {
  width: number;
  height: number;
  notices: ImageNotice[];
}

const mb = (bytes: number) => `${(bytes / 1024 / 1024).toFixed(bytes > 10 * 1024 * 1024 ? 0 : 1)} MB`;

const RATIOS: Array<[number, string]> = [
  [1, '1:1 · Square'],
  [4 / 5, '4:5 · Portrait'],
  [2 / 3, '2:3 · Portrait'],
  [9 / 16, '9:16 · Story'],
  [3 / 4, '3:4 · Portrait'],
  [16 / 9, '16:9 · Landscape'],
];

export function ratioLabel(width: number, height: number): string {
  const r = width / height;
  const hit = RATIOS.find(([v]) => Math.abs(v - r) < 0.01);
  return hit ? hit[1] : `${(r >= 1 ? r : 1 / r).toFixed(2)}:1 · ${r >= 1 ? 'Landscape' : 'Portrait'}`;
}

// every rejection comes with a reason the admin can act on
export async function checkImage(file: File): Promise<CheckedImage> {
  const notices: ImageNotice[] = [];
  const ext = file.name.split('.').pop()?.toUpperCase() ?? 'This';
  if (!ACCEPTED_TYPES.includes(file.type)) {
    return { width: 0, height: 0, notices: [{ level: 'error', message: `${ext} files aren't supported. Export as JPG or PNG and try again.` }] };
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return { width: 0, height: 0, notices: [{ level: 'error', message: `This image is ${mb(file.size)}. Use one under 15 MB.` }] };
  }
  let width = 0;
  let height = 0;
  try {
    const bitmap = await createImageBitmap(file);
    width = bitmap.width;
    height = bitmap.height;
    bitmap.close();
  } catch {
    return { width: 0, height: 0, notices: [{ level: 'error', message: "We couldn't read this image. It may be damaged — try re-exporting it." }] };
  }
  if (file.size > WHATSAPP_MAX_BYTES) {
    notices.push({ level: 'warning', message: `WhatsApp limits images to 5 MB. This one (${mb(file.size)}) will be compressed when sent.` });
  }
  if (Math.min(width, height) < 720) {
    notices.push({ level: 'warning', message: `This image is ${Math.min(width, height)} px on its short side and may look blurry on phones. 1080 px or more is recommended.` });
  }
  if (Math.max(width, height) > 4096) {
    notices.push({ level: 'info', message: 'Large image: it will be scaled down to 4096 px on its long side.' });
  }
  const r = width / height;
  if (r < 1 / 2.2 || r > 2) {
    notices.push({ level: 'warning', message: 'Very tall or wide images are cropped in WhatsApp chat previews.' });
  }
  if (file.type === 'image/webp') {
    notices.push({ level: 'info', message: 'WEBP is converted to JPG when the greeting is sent on WhatsApp.' });
  }
  return { width, height, notices };
}

// fit long side to max px and re-encode. used for big uploads and thumbnails
export async function resizeImage(blob: Blob, max: number, type = 'image/jpeg', quality = 0.85): Promise<Blob> {
  const bitmap = await createImageBitmap(blob);
  const scale = Math.min(1, max / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext('2d')!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  return new Promise((resolve, reject) => canvas.toBlob((b) => (b ? resolve(b) : reject(new Error('encode failed'))), type, quality));
}

// colour analysis

export interface ImageAnalysis {
  palette: string[]; // most common first
  /** avg luminance 0..1 of a region, coords in image px */
  sample: (x: number, y: number, w: number, h: number) => number;
  darkAccent: string | null;
}

const toHex = (r: number, g: number, b: number) => `#${[r, g, b].map((v) => v.toString(16).padStart(2, '0')).join('')}`.toUpperCase();
const luminance = (r: number, g: number, b: number) => (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;

export async function analyseImage(url: string, naturalWidth: number): Promise<ImageAnalysis> {
  const img = new Image();
  img.crossOrigin = 'anonymous';
  img.src = url;
  await img.decode();
  const scale = Math.min(1, 96 / Math.max(img.naturalWidth, img.naturalHeight));
  const w = Math.max(1, Math.round(img.naturalWidth * scale));
  const h = Math.max(1, Math.round(img.naturalHeight * scale));
  const canvas = document.createElement('canvas');
  canvas.width = w;
  canvas.height = h;
  const c = canvas.getContext('2d', { willReadFrequently: true })!;
  c.drawImage(img, 0, 0, w, h);
  const data = c.getImageData(0, 0, w, h).data;

  // 4 bits per channel buckets
  const buckets = new Map<number, { n: number; r: number; g: number; b: number }>();
  for (let i = 0; i < data.length; i += 4) {
    const key = ((data[i] >> 4) << 8) | ((data[i + 1] >> 4) << 4) | (data[i + 2] >> 4);
    const bucket = buckets.get(key) ?? { n: 0, r: 0, g: 0, b: 0 };
    bucket.n++;
    bucket.r += data[i];
    bucket.g += data[i + 1];
    bucket.b += data[i + 2];
    buckets.set(key, bucket);
  }
  const colours = [...buckets.values()]
    .sort((a, b) => b.n - a.n)
    .map((b) => [Math.round(b.r / b.n), Math.round(b.g / b.n), Math.round(b.b / b.n)] as const);
  const palette: Array<readonly [number, number, number]> = [];
  for (const col of colours) {
    if (palette.every((p) => Math.abs(p[0] - col[0]) + Math.abs(p[1] - col[1]) + Math.abs(p[2] - col[2]) > 90)) palette.push(col);
    if (palette.length === 6) break;
  }
  const saturation = ([r, g, b]: readonly number[]) => (Math.max(r, g, b) - Math.min(r, g, b)) / 255;
  const dark = palette.filter((p) => luminance(...p) < 0.35 && saturation(p) > 0.25).sort((a, b) => luminance(...a) - luminance(...b))[0];

  const k = w / naturalWidth;
  return {
    palette: palette.map((p) => toHex(...p)),
    darkAccent: dark ? toHex(...dark) : null,
    sample: (x, y, sw, sh) => {
      const x0 = Math.max(0, Math.floor(x * k));
      const y0 = Math.max(0, Math.floor(y * k));
      const x1 = Math.min(w, Math.ceil((x + sw) * k));
      const y1 = Math.min(h, Math.ceil((y + sh) * k));
      let sum = 0;
      let n = 0;
      for (let yy = y0; yy < y1; yy++) {
        for (let xx = x0; xx < x1; xx++) {
          const i = (yy * w + xx) * 4;
          sum += luminance(data[i], data[i + 1], data[i + 2]);
          n++;
        }
      }
      return n ? sum / n : 0.5;
    },
  };
}

// WCAG contrast of a hex colour against a sampled background luminance
export function contrastRatio(a: string, bLuminance: number): number {
  const v = (hex: string, i: number) => parseInt(hex.slice(1 + i * 2, 3 + i * 2), 16) / 255;
  const lin = (c: number) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  const la = 0.2126 * lin(v(a, 0)) + 0.7152 * lin(v(a, 1)) + 0.0722 * lin(v(a, 2));
  const lb = bLuminance ** 2.2; // rough linearise, the sample is gamma encoded
  const [hi, lo] = la > lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
}
