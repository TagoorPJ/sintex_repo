import { useEffect, useRef, useState, type ReactNode } from 'react';
import type { Canvas, TextField, Values } from '../model/types';
import { FieldText, useFieldLayout } from './FieldText';

// scales an image-px stage down to fit the container width
export function ScaledStage({
  canvas,
  children,
  className,
  maxHeight,
  contain,
}: {
  canvas: Canvas;
  children: ReactNode;
  className?: string;
  maxHeight?: number;
  // also fit the container height, not just width
  contain?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () => {
      const byWidth = el.clientWidth / canvas.width;
      const limit = contain ? el.clientHeight : maxHeight;
      const byHeight = limit ? limit / canvas.height : Infinity;
      setScale(Math.min(byWidth, byHeight));
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, [canvas.width, canvas.height, maxHeight, contain]);
  return (
    <div ref={ref} className={className}>
      <div className="relative mx-auto overflow-hidden" style={{ width: canvas.width * scale, height: canvas.height * scale }}>
        {scale > 0 && (
          <div style={{ width: canvas.width, height: canvas.height, transform: `scale(${scale})`, transformOrigin: '0 0', position: 'absolute', left: 0, top: 0 }}>
            {children}
          </div>
        )}
      </div>
    </div>
  );
}

function StaticField({ field, values }: { field: TextField; values: Values }) {
  const { layout } = useFieldLayout(field, values);
  return layout ? <FieldText field={field} layout={layout} box={field.box} /> : null;
}

// read-only render for thumbnails, quick look and preview
export function StaticRender({ canvas, backgroundUrl, fields, values }: { canvas: Canvas; backgroundUrl: string | null; fields: TextField[]; values: Values }) {
  return (
    <div className="relative size-full bg-white" style={{ width: canvas.width, height: canvas.height }}>
      {backgroundUrl && <img src={backgroundUrl} alt="" draggable={false} className="absolute inset-0 size-full select-none" />}
      {fields.map((f) => (
        <StaticField key={f.id} field={f} values={values} />
      ))}
    </div>
  );
}
